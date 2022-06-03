"""Adm service by Gunicorn + Uvicorn + FastAPI."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# NOTE: Maybe, consider adding a "Retry-After" header for 503 error.

import inspect
import os
import sys
import time
import json
from typing import Union
from pydantic import BaseModel
import starlette
from fastapi import Request
from fastapi import Header
from fastapi import Body, Depends, FastAPI, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
import lenticularis
from lenticularis.api import Api
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import ERROR_EXIT_READCONF
from lenticularis.utility import make_typical_ip_address
from lenticularis.utility import log_access
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


try:
    (_adm_conf, _) = read_adm_conf()
except Exception as e:
    sys.stderr.write(f"Lens3 reading config file failed: {e}\n")
    sys.exit(ERROR_EXIT_READCONF)
    pass

openlog(_adm_conf["log_file"],
        **_adm_conf["log_syslog"])
logger.info("**** START ADM ****")

_pkgdir = os.path.dirname(inspect.getfile(lenticularis))
_webui_dir = os.path.join(_pkgdir, "webui")
api = Api(_adm_conf)
app = FastAPI()
app.mount("/scripts/",
          StaticFiles(directory=os.path.join(_webui_dir, "scripts")),
          name="scripts")
with open(os.path.join(_webui_dir, "setting.html")) as f:
    _setting_html = f.read()
    pass


async def _get_authorized_user_(request: Request):
    remote_user = request.headers.get("X-REMOTE-USER")
    return remote_user


async def _get_client_addr_(request: Request):
    real_ip = request.headers.get("X-REAL-IP")
    # forwarded_for = request.headers.get("X-FORWARDED-FOR")
    return real_ip


async def _get_traceid_(request: Request):
    traceid = request.headers.get("X-TRACEID")
    tracing.set(traceid)
    return traceid


def _make_json_response(status_code, reason, values, csrf_protect,
                        client_addr, user_id, request):
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
    log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
    response = JSONResponse(status_code=status_code, content=content)
    # logger.debug(f"Adm RESPONSE.CONTENT={content}")
    return response


async def _get_request_body(request):
    body = b""
    async for chunk in request.stream():
        body += chunk
        pass
    return json.loads(body, parse_int=None)


class CsrfSettings(BaseModel):
    secret_key: str = _adm_conf["webui"]["CSRF_secret_key"]
    pass


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


@app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
    logger.error(f"CSRF error detected: {exc.message}")
    content = {"detail": exc.message}
    user_id = request.headers.get("X-REMOTE-USER")
    client_addr = request.headers.get("X-REAL-IP")
    log_access(f"{exc.status_code}", client_addr, user_id, request.method, request.url)
    response = JSONResponse(status_code=exc.status_code, content=content)
    return response


@app.middleware("http")
async def validate_session(request: Request, call_next):
    peer_addr = make_typical_ip_address(str(request.client.host))
    user_id = request.headers.get("X-REMOTE-USER")
    client_addr = request.headers.get("X-REAL-IP")
    now = int(time.time())

    if peer_addr not in api.trusted_proxies:
        logger.error(f"Untrusted proxy: {peer_addr};"
                     f" Check configuration")
        content = {"status": "error",
                   "reason": f"Configuration error (check trusted_proxies)",
                   "time": str(now)}
        status_code = status.HTTP_403_FORBIDDEN
        # Access log contains client_addr but peer_addr.
        log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)
    if (not api.zone_adm.check_user_is_registered(user_id)):
        logger.info(f"Accessing Adm by a bad user: ({user_id})")
        content = {"status": "error", "reason": f"Bad user: ({user_id})",
                   "time": str(now)}
        status_code = status.HTTP_401_UNAUTHORIZED
        log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)
    response = await call_next(request)
    return response


@app.get("/")
async def app_get_show_ui(
        request: Request,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None)):
    logger.debug(f"APP.GET /")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    code = status.HTTP_200_OK
    log_access(f"{code}", client_addr, user_id, request.method, request.url)
    with open(os.path.join(_webui_dir, "setting.html")) as f:
        _setting_html_nocache = f.read()
        pass
    response = HTMLResponse(status_code=code, content=_setting_html_nocache)
    return response


@app.get("/template")
async def app_get_get_template(
        request: Request,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    """Returns a user information for Web-UI."""
    logger.debug(f"APP.GET /template")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    (code, reason, values) = api.api_get_template(traceid, user_id)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.get("/pool")
async def app_get_list_pools(
        request: Request,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /pool")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    (code, reason, values) = api.api_list_pools(traceid, user_id, None)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.get("/pool/{pool_id}")
async def app_get_get_pool(
        request: Request,
        pool_id: str,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /pool/{pool_id}")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    (code, reason, values) = api.api_list_pools(traceid, user_id, pool_id)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.post("/pool")
async def app_post_make_pool(
        request: Request,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.POST /pool")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    pooldesc = body.get("pool")
    (code, reason, values) = api.api_make_pool(traceid, user_id, pooldesc)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.delete("/pool/{pool_id}")
async def app_delete_delete_pool(
        request: Request,
        pool_id: str,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    body = await _get_request_body(request)
    csrf_token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(csrf_token)
    (code, reason, values) = api.api_delete_pool(traceid, user_id, pool_id)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.put("/pool/{pool_id}/bucket")
async def app_put_make_bucket(
        request: Request,
        pool_id: str,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/bucket")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    (code, reason, values) = api.api_make_bucket(traceid, user_id, pool_id, body)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.delete("/pool/{pool_id}/bucket/{bucket}")
async def app_delete_delete_bucket(
        request: Request,
        pool_id: str,
        bucket: str,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}/bucket/{bucket}")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    (code, reason, values) = api.api_delete_bucket(traceid, user_id, pool_id, bucket)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response


@app.put("/pool/{pool_id}/secret")
async def app_put_make_secret(
        request: Request,
        pool_id: str,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/secret")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    (code, reason, values) = api.api_make_secret(traceid, user_id, pool_id, body)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response

@app.delete("/pool/{pool_id}/secret/{access_key}")
async def app_delete_delete_secret(
        request: Request,
        pool_id: str,
        access_key: str,
        x_remote_user: Union[str, None] = Header(default=None),
        x_real_ip: Union[str, None] = Header(default=None),
        x_traceid: Union[str, None] = Header(default=None),
        csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}/secret/{access_key}")
    (user_id, client_addr, traceid) = (x_remote_user, x_real_ip, x_traceid)
    tracing.set(traceid)
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    (code, reason, values) = api.api_delete_secret(traceid, user_id, pool_id, access_key)
    response = _make_json_response(code, reason, values, csrf_protect,
                                   client_addr, user_id, request)
    return response
