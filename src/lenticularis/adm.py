"""Adm service by Gunicorn + Uvicorn + FastAPI."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import inspect
import os
import sys
import time
import json
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi import Body, Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
import lenticularis
from lenticularis.api import Api
from lenticularis.pooladm import ZoneAdm
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


async def _get_authorized_user(request: Request):
    remote_user = request.headers.get("X-REMOTE-USER")
    return remote_user


async def _get_client_addr(request: Request):
    real_ip = request.headers.get("X-REAL-IP")
    # forwarded_for = request.headers.get("X-FORWARDED-FOR")
    return real_ip


async def _get_traceid(request: Request):
    traceid = request.headers.get("X-TRACEID")
    tracing.set(traceid)
    return traceid


def _make_json_response(status_code, reason, values, csrf_protect,
                        client_addr, user_id, request):
    # > HTTP_503_SERVICE_UNAVAILABLE
    # > Retry-After
    if reason is not None:
        content = {"status": "error", "reason": reason}
        ##status_code = status.HTTP_400_BAD_REQUEST
    else:
        content = {"status": "success"}
        ##status_code = status.HTTP_200_OK
        pass
    if values is not None:
        ##content["pool_list"] = values
        content.update(values)
        pass
    content["time"] = str(int(time.time()))
    if csrf_protect:
        content["CSRF-Token"] = csrf_protect.generate_csrf()
        pass
    log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
    response = JSONResponse(status_code=status_code, content=content)
    logger.debug(f"Adm RESPONSE.CONTENT={content}")
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
    return JSONResponse(status_code=exc.status_code, content=content)


@app.get("/")
async def app_get_show_ui(request: Request,
                          user_id: str = Depends(_get_authorized_user),
                          traceid: str = Depends(_get_traceid),
                          client_addr: str = Depends(_get_client_addr)):
    logger.debug(f"APP.GET /")
    code = status.HTTP_200_OK
    log_access(f"{code}", client_addr, user_id, request.method, request.url)
    with open(os.path.join(_webui_dir, "setting.html")) as f:
        _setting_html_nocache = f.read()
    response = HTMLResponse(status_code=code, content=_setting_html_nocache)
    return response


@app.get("/template")
async def app_get_get_template(request: Request,
                               user_id: str = Depends(_get_authorized_user),
                               traceid: str = Depends(_get_traceid),
                               client_addr: str = Depends(_get_client_addr),
                               csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /template")
    (code, reason, values) = api.api_get_template(traceid, user_id)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.get("/pool")
async def app_get_list_pools(request: Request,
                             user_id: str = Depends(_get_authorized_user),
                             traceid: str = Depends(_get_traceid),
                             client_addr: str = Depends(_get_client_addr),
                             csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /pool")
    (code, reason, values) = api.api_list_pools(traceid, user_id, None)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.get("/pool/{pool_id}")
async def app_get_get_pool(pool_id: str,
                           request: Request,
                           user_id: str = Depends(_get_authorized_user),
                           traceid: str = Depends(_get_traceid),
                           client_addr: str = Depends(_get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /pool/{pool_id}")
    (code, reason, values) = api.api_list_pools(traceid, user_id, pool_id)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.post("/pool")
async def app_post_create_pool(request: Request,
                               user_id: str = Depends(_get_authorized_user),
                               traceid: str = Depends(_get_traceid),
                               client_addr: str = Depends(_get_client_addr),
                               csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.POST /pool")
    body = await _get_request_body(request)
    ##return pool_update(traceid, None, body, client_addr, user_id, request, csrf_protect, "create_pool")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    pooldesc = body.get("pool")
    (code, reason, values) = api.api_create_pool(traceid, user_id, pooldesc)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.put("/pool/{pool_id}")
async def app_put_update_pool(pool_id: str,
                              request: Request,
                              user_id: str = Depends(_get_authorized_user),
                              traceid: str = Depends(_get_traceid),
                              client_addr: str = Depends(_get_client_addr),
                              csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}")
    body = await _get_request_body(request)
    ##return pool_update(traceid, pool_id, body, client_addr, user_id, request, csrf_protect, "update_pool")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    pooldesc = body.get("pool")
    (code, reason, values) = api.api_update_pool(traceid, user_id, pool_id, pooldesc)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


##@app.put("/pool/{pool_id}/buckets")
async def app_put_update_buckets(pool_id: str,
                                 request: Request,
                                 user_id: str = Depends(_get_authorized_user),
                                 traceid: str = Depends(_get_traceid),
                                 client_addr: str = Depends(_get_client_addr),
                                 csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/buckets")
    body = await _get_request_body(request)
    ##return pool_update(traceid, pool_id, body, client_addr, user_id, request, csrf_protect, "update_buckets")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    pooldesc = body.get("pool")
    (code, reason, values) = api.api_update_buckets(traceid, user_id, pool_id, pooldesc)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.put("/pool/{pool_id}/bucket")
async def app_put_make_bucket(pool_id: str,
                              request: Request,
                              user_id: str = Depends(_get_authorized_user),
                              traceid: str = Depends(_get_traceid),
                              client_addr: str = Depends(_get_client_addr),
                              csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/bucket")
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    (code, reason, values) = api.api_make_bucket(traceid, user_id, pool_id, body)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.put("/pool/{pool_id}/accessKeys")
async def app_put_change_secret(pool_id: str,
                                request: Request,
                                user_id: str = Depends(_get_authorized_user),
                                traceid: str = Depends(_get_traceid),
                                client_addr: str = Depends(_get_client_addr),
                                csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/accessKeys")
    body = await _get_request_body(request)
    ##return pool_update(traceid, pool_id, body, client_addr, user_id, request, csrf_protect, "change_secret_key")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    pooldesc = body.get("pool")
    (code, reason, values) = api.api_change_secret(traceid, user_id, pool_id, pooldesc)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


## 'how' is one of {"create_zone", "update_zone", "update_buckets",
## "change_secret_key"}.  If how="create_zone" then zone_id=None.

##def _zone_update_(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, how):
##    csrf_token = body.get("CSRF-Token")
##    csrf_protect.validate_csrf(csrf_token)
##    zone = body.get("zone")
##    (code, zone_list, err) = api.api_upsert(how, traceid, user_id, zone_id, zone)
##    return _make_json_response(zone_list, err, None, client_addr, user_id, request)


@app.delete("/pool/{pool_id}")
async def app_delete_pool(pool_id: str,
                          request: Request,
                          user_id: str = Depends(_get_authorized_user),
                          traceid: str = Depends(_get_traceid),
                          client_addr: str = Depends(_get_client_addr),
                          csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /pool/{pool_id}")
    body = await _get_request_body(request)
    csrf_token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(csrf_token)
    (code, reason, values) = api.api_delete(traceid, user_id, pool_id)
    return _make_json_response(code, reason, values, csrf_protect,
                               client_addr, user_id, request)


@app.middleware("http")
async def validate_session(request: Request, call_next):
    peer_addr = str(request.client.host)
    peer_addr = make_typical_ip_address(peer_addr)
    #logger.debug(f"@@@: {request}")
    #logger.debug(f"@@@: {request.headers}")
    #logger.debug(f"@@@: {request.method}")
    #logger.debug(f"@@@: {request.url}")
    #logger.debug(f"@@@: {request.base_url}")
    #logger.debug(f"@@@: {request.query_params}")
    #logger.debug(f"@@@: {request.path_params}")

    user_id = await _get_authorized_user(request)
    client_addr = await _get_client_addr(request)
    #logger.debug(f"@@@ api_check_user: {user_id} {client_addr}")

    if peer_addr not in api.trusted_proxies:
        logger.error(f"Proxy {peer_addr} is not trusted.")
        content = {"status": "error", "reason": f"Configuration error (trusted_proxies)."}
        status_code = status.HTTP_403_FORBIDDEN
        # Access log contains client_addr, but peer_addr.
        log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)

    if not api.check_user(user_id):
        logger.error(f"access denied: user: {user_id}")
        content = {"status": "error", "reason": f"{user_id}: no such user"}
        content["time"] = str(int(time.time()))
        status_code = status.HTTP_401_UNAUTHORIZED
        log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)

    #logger.debug(f"request={request} method={request.method} url={request.url}")

    response = await call_next(request)

    return response
