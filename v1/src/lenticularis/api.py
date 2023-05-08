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
from fastapi.responses import JSONResponse, HTMLResponse
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
    _app.mount("/scripts/",
               StaticFiles(directory=os.path.join(_api.webui_dir, "scripts")),
               name="scripts")
    with open(os.path.join(_api.webui_dir, "setting.html")) as f:
        parameters = ('<script type="text/javascript">const base_path="'
                      + _api.base_path + '";</script>')
        _setting_html = f.read().replace("PLACE_PARAMETERS_HERE", parameters)
        pass
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
    (status_code, reason, values) = triple
    if reason is not None:
        content = {"status": "error", "reason": reason}
    else:
        content = {"status": "success"}
        pass
    if values is not None:
        # Append values to content.
        content.update(values)
        pass
    content["time"] = str(int(time.time()))
    if csrf_protect:
        content["CSRF-Token"] = csrf_protect.generate_csrf()
        pass
    log_access(f"{status_code}", client, user_id, request.method, request.url)
    response = JSONResponse(status_code=status_code, content=content)
    # logger.debug(f"Api RESPONSE.CONTENT={content}")
    return response


async def _get_request_body(request):
    body = b""
    async for chunk in request.stream():
        body += chunk
        pass
    return json.loads(body, parse_int=None)


class CsrfSettings(BaseModel):
    secret_key : str = _api_conf["controller"]["CSRF_secret_key"]

    pass


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


@_app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request : Request, exc : CsrfProtectError):
    logger.error(f"CSRF error detected: {exc.message}")
    content = {"detail": exc.message}
    user_id = request.headers.get("X-REMOTE-USER")
    client = request.headers.get("X-REAL-IP")
    log_access(f"{exc.status_code}", client, user_id, request.method, request.url)
    response = JSONResponse(status_code=exc.status_code, content=content)
    return response


@_app.middleware("http")
async def validate_session(request : Request, call_next):
    peer_addr = make_typical_ip_address(str(request.client.host))
    x_remote_user = request.headers.get("X-REMOTE-USER")
    client = request.headers.get("X-REAL-IP")
    user_id = _api.map_claim_to_uid(x_remote_user)
    now = int(time.time())
    if peer_addr not in _api.trusted_proxies:
        logger.error(f"Untrusted proxy: {peer_addr};"
                     f" Check configuration")
        content = {"status": "error",
                   "reason": f"Configuration error (check trusted_proxies)",
                   "time": str(now)}
        status_code = status.HTTP_403_FORBIDDEN
        # Access log contains client_addr but peer_addr.
        log_access(f"{status_code}", client, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)
    if (not _api.check_user_is_registered(user_id)):
        logger.info(f"Accessing Api by a bad user: ({user_id})")
        content = {"status": "error", "reason": f"Bad user: ({user_id})",
                   "time": str(now)}
        status_code = status.HTTP_401_UNAUTHORIZED
        log_access(f"{status_code}", client, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)
    response = await call_next(request)
    return response


@_app.get("/csrftoken/")
async def get_csrf_token(csrf_protect : CsrfProtect = Depends()):
    response = JSONResponse(status_code=200, content={"csrf_token": "cookie"})
    csrf_protect.set_csrf_cookie(response)
    return response


@_app.get("/")
async def app_get_ui(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    response = _app_get_ui("setting.html", request, user_id, client)
    return response

@_app.get("/setting.html")
async def app_get_ui(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /setting.html")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    response = _app_get_ui("setting.html", request, user_id, client)
    return response


@_app.get("/setting-debug.html")
async def app_get_debug_ui(
        request : Request,
        x_remote_user : Union[str, None] = Header(default=None),
        x_real_ip : Union[str, None] = Header(default=None),
        x_traceid : Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /setting-debug.html")
    tracing.set(x_traceid)
    user_id = _api.map_claim_to_uid(x_remote_user)
    client = x_real_ip
    response = _app_get_ui("setting-debug.html", request, user_id, client)
    return response


def _app_get_ui(file, request, user_id, client):
    code = status.HTTP_200_OK
    log_access(f"{code}", client, user_id, request.method, request.url)
    with open(os.path.join(_api.webui_dir, "setting-debug.html")) as f:
        parameters = ('<script type="text/javascript">const base_path="'
                      + _api.base_path + '";</script>')
        html = f.read().replace("PLACE_PARAMETERS_HERE", parameters)
        pass
    response = HTMLResponse(status_code=code, content=html)
    return response


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
    triple = _api.api_get_user_info(x_traceid, user_id)
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
    triple = _api.api_list_pools(x_traceid, user_id, None)
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
    triple = _api.api_list_pools(x_traceid, user_id, pool_id)
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
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    triple = _api.api_make_pool(x_traceid, user_id, body)
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
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    triple = _api.api_delete_pool(x_traceid, user_id, pool_id)
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
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    triple = _api.api_make_bucket(x_traceid, user_id, pool_id, body)
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
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    triple = _api.api_delete_bucket(x_traceid, user_id, pool_id, bucket)
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
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    triple = _api.api_make_secret(x_traceid, user_id, pool_id, body)
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
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    triple = _api.api_delete_secret(x_traceid, user_id, pool_id, access_key)
    response = _make_json_response(triple, user_id, client, request,
                                   csrf_protect)
    return response
