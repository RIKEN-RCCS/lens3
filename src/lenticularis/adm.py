"""Adm service by Gunicorn + Uvicorn + FastAPI."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import inspect
import os
import sys
#import threading
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
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import ERROR_READCONF
from lenticularis.utility import make_typical_ip_address
from lenticularis.utility import log_access
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


try:
    (adm_conf, configfile) = read_adm_conf()
except Exception as e:
    sys.stderr.write(f"Lens3 reading conf failed: {e}\n")
    sys.exit(ERROR_READCONF)

openlog(adm_conf["log_file"],
        **adm_conf["log_syslog"])
logger.info("**** START ADM ****")

pkgdir = os.path.dirname(inspect.getfile(lenticularis))
webui_dir = os.path.join(pkgdir, "webui")
api = Api(adm_conf)
app = FastAPI()
app.mount("/scripts/",
          StaticFiles(directory=os.path.join(webui_dir, "scripts")),
          name="scripts")
with open(os.path.join(webui_dir, "setting.html")) as f:
    setting_html = f.read()


async def _get_authorized_user(request: Request):
    remote_user = request.headers.get("X-REMOTE-USER")
    #logger.debug(f"@@@ X_REMOTE_USER = {remote_user}")
    return remote_user


async def _get_client_addr(request: Request):
    real_ip = request.headers.get("X-REAL-IP")
    #forwarded_for = request.headers.get("X-FORWARDED-FOR")
    #return request.headers.get("X-FORWARDED-FOR")
    return real_ip


async def _get_traceid(request: Request):
    traceid = request.headers.get("X-TRACEID")
    #threading.current_thread().name = traceid
    tracing.set(traceid)
    return traceid


def _respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request):
    ##HTTP_503_SERVICE_UNAVAILABLE
    ##Retry-After
    if err is not None:
        content = {"status": "error", "reason": err}
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        content = {"status": "success"}
        status_code = status.HTTP_200_OK
    if zone_list is not None:
        content["zonelist"] = zone_list
    if csrf_protect:
        content["CSRF-Token"] = csrf_protect.generate_csrf()
    content["time"] = str(int(time.time()))
    log_access(f"{status_code}", client_addr, user_id, request.method, request.url)
    response = JSONResponse(status_code=status_code, content=content)
    ##logger.debug(f"@@@ RESPONSE.CONTENT {content}")
    return response


async def _get_request_body(request):
    body = b""
    async for chunk in request.stream():
        body += chunk
    return json.loads(body, parse_int=None)


async def _check_pool_naming(id, csrf_protect, request):
    if (len(id) == 20 and id[0].isalpha() and id.isalnum()):
        return None
    else:
        user_id = await _get_authorized_user(request)
        client = await _get_client_addr(request)
        content = {"status": "error", "reason": "Bad pool-id",
                   "time": str(int(time.time())),}
        code = status.HTTP_400_BAD_REQUEST
        response = JSONResponse(status_code=code, content=content)
        log_access(f"{code}", client, user_id, request.method, request.url)
        return response


class CsrfSettings(BaseModel):
    secret_key: str = adm_conf["webui"]["CSRF_secret_key"]


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


@app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request: Request,
                                   exc: CsrfProtectError):
                                   #user_id: str = Depends(_get_authorized_user),
                                   #client_addr: str = Depends(_get_client_addr)):
    #logger.debug(f"@@@ {exc.message}")
    logger.error(f"{exc.message}")
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
    logger.debug(f"traceid={traceid}")
    code = status.HTTP_200_OK
    log_access(f"{code}", client_addr, user_id, request.method, request.url)
    ##traceid = traceid if traceid is not None else "12345"
    ##headers = {"X-TRACEID": traceid}
    ##(headers=headers,)
    with open(os.path.join(webui_dir, "setting.html")) as f:
        setting_html_nocache = f.read()
    response = HTMLResponse(status_code=code, content=setting_html_nocache)
    return response


@app.get("/template")
async def app_get_get_template(request: Request,
                               user_id: str = Depends(_get_authorized_user),
                               traceid: str = Depends(_get_traceid),
                               client_addr: str = Depends(_get_client_addr),
                               csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /template")
    (code, zone_list, err) = api.api_get_template(traceid, user_id)
    return _respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request)


@app.get("/zone")
async def app_get_list_pools(request: Request,
                             user_id: str = Depends(_get_authorized_user),
                             traceid: str = Depends(_get_traceid),
                             client_addr: str = Depends(_get_client_addr),
                             csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /zone")
    (code, zone_list, err) = api.api_list_pools(traceid, user_id, None)
    return _respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request)


@app.get("/zone/{zone_id}")
async def app_get_get_pool(zone_id: str,
                           request: Request,
                           user_id: str = Depends(_get_authorized_user),
                           traceid: str = Depends(_get_traceid),
                           client_addr: str = Depends(_get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.GET /zone/{zone_id}")
    ##ng_response = _check_pool_naming(zone_id, csrf_protect, request)
    ##if ng_response is not None:
    ##    return ng_response
    (code, zone_list, err) = api.api_list_pools(traceid, user_id, zone_id)
    return _respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request)


@app.post("/zone")
async def app_post_create_pool(request: Request,
                               user_id: str = Depends(_get_authorized_user),
                               traceid: str = Depends(_get_traceid),
                               client_addr: str = Depends(_get_client_addr),
                               csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.POST /zone")
    body = await _get_request_body(request)
    ##return zone_update(traceid, None, body, client_addr, user_id, request, csrf_protect, "create_zone")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    zone = body.get("zone")
    (code, zone_list, err) = api.api_create_pool(traceid, user_id, None, zone)
    return _respond_zone(zone_list, err, None, client_addr, user_id, request)


@app.put("/zone/{zone_id}")
async def app_put_update_pool(zone_id: str,
                              request: Request,
                              user_id: str = Depends(_get_authorized_user),
                              traceid: str = Depends(_get_traceid),
                              client_addr: str = Depends(_get_client_addr),
                              csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /zone/{zone_id}")
    ##ng_response = _check_pool_naming(zone_id, csrf_protect, request)
    ##if ng_response is not None:
    ##    return ng_response
    body = await _get_request_body(request)
    ##return zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, "update_zone")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    zone = body.get("zone")
    (code, zone_list, err) = api.api_update_pool(traceid, user_id, zone_id, zone)
    return _respond_zone(zone_list, err, None, client_addr, user_id, request)


##@app.put("/zone/{zone_id}/buckets")
async def app_put_update_buckets(zone_id: str,
                                 request: Request,
                                 user_id: str = Depends(_get_authorized_user),
                                 traceid: str = Depends(_get_traceid),
                                 client_addr: str = Depends(_get_client_addr),
                                 csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /zone/{zone_id}/buckets")
    ##ng_response = _check_pool_naming(zone_id, csrf_protect, request)
    ##if ng_response is not None:
    ##    return ng_response
    body = await _get_request_body(request)
    ##return zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, "update_buckets")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    zone = body.get("zone")
    (code, zone_list, err) = api.api_update_buckets(traceid, user_id, zone_id, zone)
    return _respond_zone(zone_list, err, None, client_addr, user_id, request)


@app.put("/pool/{pool_id}/bucket/{bucket}")
async def app_put_make_bucket(pool_id: str,
                              bucket: str,
                              request: Request,
                              user_id: str = Depends(_get_authorized_user),
                              traceid: str = Depends(_get_traceid),
                              client_addr: str = Depends(_get_client_addr),
                              csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /pool/{pool_id}/bucket/{bucket}")
    ##ng_response = _check_pool_naming(pool_id, csrf_protect, request)
    ##if ng_response is not None:
    ##    return ng_response
    body = await _get_request_body(request)
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    (code, zone_list, err) = api.api_make_bucket(traceid, user_id, pool_id, bucket, body)
    return _respond_zone(zone_list, err, None, client_addr, user_id, request)


@app.put("/zone/{zone_id}/accessKeys")
async def app_put_change_secret(zone_id: str,
                                request: Request,
                                user_id: str = Depends(_get_authorized_user),
                                traceid: str = Depends(_get_traceid),
                                client_addr: str = Depends(_get_client_addr),
                                csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.PUT /zone/{zone_id}/accessKeys")
    ##ng_response = _check_pool_naming(zone_id, csrf_protect, request)
    ##if ng_response is not None:
    ##    return ng_response
    body = await _get_request_body(request)
    ##return zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, "change_secret_key")
    token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(token)
    zone = body.get("zone")
    (code, zone_list, err) = api.api_change_secret(traceid, user_id, zone_id, zone)
    return _respond_zone(zone_list, err, None, client_addr, user_id, request)


## 'how' is one of {"create_zone", "update_zone", "update_buckets",
## "change_secret_key"}.  If how="create_zone" then zone_id=None.

##def _zone_update_(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, how):
##    csrf_token = body.get("CSRF-Token")
##    csrf_protect.validate_csrf(csrf_token)
##    zone = body.get("zone")
##    (code, zone_list, err) = api.api_upsert(how, traceid, user_id, zone_id, zone)
##    return _respond_zone(zone_list, err, None, client_addr, user_id, request)


@app.delete("/zone/{zone_id}")
async def app_delete_zone(zone_id: str,
                           request: Request,
                           user_id: str = Depends(_get_authorized_user),
                           traceid: str = Depends(_get_traceid),
                           client_addr: str = Depends(_get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"APP.DELETE /zone/{zone_id}")
    ##ng_response = _check_pool_naming(zone_id, csrf_protect, request)
    ##if ng_response is not None:
    ##    return ng_response
    body = await _get_request_body(request)
    csrf_token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(csrf_token)
    (_, _, err) = api.api_delete(traceid, user_id, zone_id)
    return _respond_zone(None, err, None, client_addr, user_id, request)


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
