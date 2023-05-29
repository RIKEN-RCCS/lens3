"""Lens3-Api main started as a Gunicorn + Uvicorn + FastAPI service."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# NOTE: Maybe, consider adding a "Retry-After" header for 503 error.

import os
import sys
import time
import json
from typing import Union
from pydantic import BaseModel
from fastapi import FastAPI, Request, Header, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from lenticularis.control import Control_Api
from lenticularis.table import read_redis_conf
from lenticularis.table import get_conf
from lenticularis.utility import ERROR_EXIT_BADCONF
from lenticularis.utility import make_typical_ip_address
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import log_access
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing

# It initializes the app early, because the app and CsrfProtect are
# referenced at module loading (it initializes CsrfProtect at the call
# of get_csrf_config()).

_app = None
_api = None
_api_conf = None

def _make_app():
    global _app, _api,  _api_conf
    assert _api is None

    assert os.environ.get("LENS3_CONF") is not None
    conf_file = os.environ.get("LENS3_CONF")

    try:
        redis = read_redis_conf(conf_file)
        _api_conf = get_conf("api", None, redis)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Lens3 reading a conf file failed:"
                         f" exception=({m})\n")
        sys.exit(ERROR_EXIT_BADCONF)
        pass

    openlog(_api_conf["log_file"], **_api_conf["log_syslog"])
    logger.info("START Api.")

    _api = Control_Api(_api_conf, redis)

    _app = FastAPI()
    # with open(os.path.join(_api.pkg_dir, "ui2", "index.html")) as f:
    #     parameters = ('<script type="text/javascript">const base_path_="'
    #                   + _api.base_path + '";</script>')
    #     _setting_html = f.read().replace("PLACE_BASE_PATH_SETTING_HERE", parameters)
    #     pass
    pass

_make_app()

assert _app is not None
assert _api is not None
assert _api_conf is not None


def app():
    global _app
    assert _app is not None
    return _app


def _make_json_response(triple, user_id, client, request, csrf_protect):
    """Makes a response.  triple=(code, reason, values)."""
    access_synopsis = [client, user_id, request.method, request.url]
    (code, reason, values) = triple
    log_access(f"{code}", *access_synopsis)
    if reason is not None:
        body = {"status": "error", "reason": reason}
    else:
        body = {"status": "success"}
        pass
    if values is not None:
        # Append values to the content.
        body.update(values)
        pass
    body["time"] = str(int(time.time()))
    if csrf_protect:
        body["CSRF-Token"] = csrf_protect.generate_csrf()
        pass
    response = JSONResponse(status_code=code, content=body)
    # logger.debug(f"Api RESPONSE.CONTENT={body}")
    return response


async def _get_request_body(request):
    """Returns a request body as a pair (body, token), where a body is a
       dict and a token is a csrf-token.  It removes a csrf-token from
       the body.
    """
    buf_ = b""
    async for chunk in request.stream():
        buf_ += chunk
        pass
    body = json.loads((buf_ or "{}"))
    token = body.get("CSRF-Token")
    if token is not None:
        del body["CSRF-Token"]
        pass
    return (body, token)


class CsrfSettings(BaseModel):
    secret_key : str = _api_conf["controller"]["csrf_secret_key"]

    pass


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


@_app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request : Request, exc : CsrfProtectError):
    logger.error(f"CSRF error detected: {exc.message}")
    x_remote_user = request.headers.get("X-REMOTE-USER")
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = request.headers.get("X-REAL-IP")
    access_synopsis = [client, user_id, request.method, request.url]
    now = int(time.time())
    code = exc.status_code
    body = {"status": "error",
            "reason": f"CSRF protection error",
            "time": str(now)}
    log_access(f"{code}", *access_synopsis)
    time.sleep(_api._bad_response_delay)
    response = JSONResponse(status_code=code, content=body)
    return response


@_app.middleware("http")
async def validate_session(request : Request, call_next):
    """Validates a session early.  (Note it performs mapping of a user-id
    twice, once here and once later).
    """
    peer_addr = make_typical_ip_address(str(request.client.host))
    x_remote_user = request.headers.get("X-REMOTE-USER")
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = request.headers.get("X-REAL-IP")
    access_synopsis = [client, user_id, request.method, request.url]
    now = int(time.time())
    if peer_addr not in _api.trusted_proxies:
        logger.error(f"Untrusted proxy: proxy={peer_addr};"
                     f" Check trusted_proxies in configuration")
        body = {"status": "error",
                "reason": f"Configuration error (call administrator)",
                "time": str(now)}
        code = status.HTTP_403_FORBIDDEN
        log_access(f"{code}", *access_synopsis)
        time.sleep(_api._bad_response_delay)
        response = JSONResponse(status_code=code, content=body)
        return response
    if not _api.check_user_is_registered(user_id):
        logger.error(f"Access by an unregistered user:"
                     f" uid={user_id}, x_remote_user={x_remote_user}")
        body = {"status": "error",
                "reason": f"Unregistered user: user={user_id}",
                "time": str(now)}
        code = status.HTTP_401_UNAUTHORIZED
        log_access(f"{code}", *access_synopsis)
        time.sleep(_api._bad_response_delay)
        response = JSONResponse(status_code=code, content=body)
        return response
    response = await call_next(request)
    return response


@_app.get("/csrftoken")
async def get_csrf_token(csrf_protect : CsrfProtect = Depends()):
    response = JSONResponse(status_code=200, content={"csrf_token": "cookie"})
    csrf_protect.set_csrf_cookie(response)
    return response


@_app.get("/")
async def app_get_index(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    response = RedirectResponse("./ui/index.html")
    return response


@_app.get("/ui/index.html")
async def app_get_ui(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /ui/index.html")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    response = _get_ui("ui", "index.html", client, user_id, request)
    return response


@_app.get("/ui2/index.html")
async def app_get_ui2(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /ui2/index.html")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    response = _get_ui("ui2", "index.html", client, user_id, request)
    return response


# Note it mounts static files here after registering the specific
# paths of "/ui/index.html" and "/ui2/index.html" to take precedence
# over static ones.

_app.mount("/ui",
           StaticFiles(directory=os.path.join(_api.pkg_dir, "ui")),
           name="static")
_app.mount("/ui2",
           StaticFiles(directory=os.path.join(_api.pkg_dir, "ui2")),
           name="static")


def _get_ui(ui_dir, file, client, user_id, request):
    access_synopsis = [client, user_id, request.method, request.url]
    try:
        with open(os.path.join(_api.pkg_dir, ui_dir, file)) as f:
            parameters = ('<script type="text/javascript">const base_path_="'
                          + _api.base_path + '";</script>')
            html = f.read().replace("PLACE_BASE_PATH_SETTING_HERE", parameters)
            pass
        code = status.HTTP_200_OK
        log_access(f"{code}", *access_synopsis)
        response = HTMLResponse(status_code=code, content=html)
        return response
    except Exception as e:
        m = rephrase_exception_message(e)
        code = 500
        body = {"status": "error", "reason": m}
        logger.error(f"get_ui failed: user={user_id}; exception=({m})",
                     exc_info=True)
        log_access(f"{code}", *access_synopsis)
        time.sleep(_api._bad_response_delay)
        response = JSONResponse(status_code=code, content=body)
        return response
    pass


@_app.get("/user-info")
async def app_get_get_user_info(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    """Returns a user information."""
    logger.debug(f"APP.GET /user-info")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    triple = _api.api_get_user_info(user_id)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.get("/pool")
async def app_get_list_pools(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.GET /pool")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    triple = _api.api_list_pools(user_id, None)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.get("/pool/{pool_id}")
async def app_get_get_pool(
        request : Request,
        pool_id : str,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.GET /pool/{pool_id}")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    triple = _api.api_list_pools(user_id, pool_id)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.post("/pool")
async def app_post_make_pool(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.POST /pool")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    (body, token) = await _get_request_body(request)
    csrf_protect.validate_csrf(token)
    triple = _api.api_make_pool(user_id, body)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.delete("/pool/{pool_id}")
async def app_delete_delete_pool(
        request : Request,
        pool_id : str,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    (body, token) = await _get_request_body(request)
    csrf_protect.validate_csrf(token)
    triple = _api.api_delete_pool(user_id, pool_id)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.put("/pool/{pool_id}/bucket")
async def app_put_make_bucket(
        request : Request,
        pool_id : str,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/bucket")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    (body, token) = await _get_request_body(request)
    csrf_protect.validate_csrf(token)
    triple = _api.api_make_bucket(user_id, pool_id, body)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.delete("/pool/{pool_id}/bucket/{bucket}")
async def app_delete_delete_bucket(
        request : Request,
        pool_id : str,
        bucket : str,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}/bucket/{bucket}")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    (body, token) = await _get_request_body(request)
    csrf_protect.validate_csrf(token)
    triple = _api.api_delete_bucket(user_id, pool_id, bucket)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.post("/pool/{pool_id}/secret")
async def app_post_make_secret(
        request : Request,
        pool_id : str,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.POST /pool/{pool_id}/secret")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    (body, token) = await _get_request_body(request)
    csrf_protect.validate_csrf(token)
    triple = _api.api_make_secret(user_id, pool_id, body)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response


@_app.delete("/pool/{pool_id}/secret/{access_key}")
async def app_delete_delete_secret(
        request : Request,
        pool_id : str,
        access_key : str,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None),
        csrf_protect : CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}/secret/{access_key}")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    (body, token) = await _get_request_body(request)
    csrf_protect.validate_csrf(token)
    triple = _api.api_delete_secret(user_id, pool_id, access_key)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response
