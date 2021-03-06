# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from fastapi.staticfiles import StaticFiles
from fastapi import Body, Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
import inspect
import lenticularis
from lenticularis.api import Api
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import ERROR_READCONF
from lenticularis.utility import accesslog
from lenticularis.utility import logger, openlog
from lenticularis.utility import normalize_address
from lenticularis.utility import safe_json_loads
import os
import sys
import threading
import time
from pydantic import BaseModel


try:
    (adm_conf, configfile) = read_adm_conf()
except Exception as e:
    sys.stderr.write(f"{e}\n")
    sys.exit(ERROR_READCONF)

openlog(**adm_conf["lenticularis"]["syslog"])
logger.info("***** START RESTAPI *****")

pkgdir = os.path.dirname(inspect.getfile(lenticularis))
webui_dir = os.path.join(pkgdir, "webui")
api = Api(adm_conf)
app = FastAPI()
app.mount("/scripts/",
          StaticFiles(directory=os.path.join(webui_dir, "scripts")),
          name="scripts")
with open(os.path.join(webui_dir, "create.html")) as f:
    create_html = f.read()


class CsrfSettings(BaseModel):
    secret_key: str = adm_conf["webui"]["CSRF_secret_key"]


@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings()


@app.exception_handler(CsrfProtectError)
def csrf_protect_exception_handler(request: Request, 
                                   exc: CsrfProtectError):
                                   #user_id: str = Depends(get_authorized_user),
                                   #client_addr: str = Depends(get_client_addr)):
    #logger.debug(f"@@@ {exc.message}")
    logger.error(f"{exc.message}")
    content = {"detail":  exc.message}
    user_id = request.headers.get("X-REMOTE-USER")
    client_addr = request.headers.get("X-REAL-IP")
    accesslog(f"{exc.status_code}", client_addr, user_id, request.method, request.url)
    return JSONResponse(status_code=exc.status_code, content=content)


async def get_authorized_user(request: Request):
    remote_user = request.headers.get("X-REMOTE-USER")
    logger.debug(f"@@@ X_REMOTE_USER = {remote_user}")
    return remote_user


async def get_client_addr(request: Request):
    real_ip = request.headers.get("X-REAL-IP")
    #forwarded_for = request.headers.get("X-FORWARDED-FOR")
    return real_ip
    # return request.headers.get("X-FORWARDED-FOR")


async def get_traceid(request: Request):
    traceid = request.headers.get("X-TRACEID")
    threading.currentThread().name = traceid
    logger.debug(f"@@@ traceid = {traceid}")
    return traceid


@app.get("/")
async def show_html_file(request: Request,
                         user_id: str = Depends(get_authorized_user),
                         traceid: str = Depends(get_traceid),
                         client_addr: str = Depends(get_client_addr)):
    logger.debug(f"@@@ GET /")
    status_code = status.HTTP_200_OK
    accesslog(f"{status_code}", client_addr, user_id, request.method, request.url)
    response = HTMLResponse(status_code=status_code, content=create_html)
    return response


@app.get("/template")
async def func_zone_template(request: Request,
                         user_id: str = Depends(get_authorized_user),
                         traceid: str = Depends(get_traceid),
                         client_addr: str = Depends(get_client_addr),
                         csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ GET /template")
    (zone_list, err) = api.api_get_template(traceid, user_id)
    return respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request)


@app.get("/zone")
async def func_zone_list(request: Request,
                         user_id: str = Depends(get_authorized_user),
                         traceid: str = Depends(get_traceid),
                         client_addr: str = Depends(get_client_addr),
                         csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@  GET /zone")
    (zone_list, err) = api.api_zone_list(traceid, user_id, None)
    return respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request)


@app.get("/zone/{zone_id}")
async def func_zone_get(zone_id: str,
                         request: Request,
                         user_id: str = Depends(get_authorized_user),
                         traceid: str = Depends(get_traceid),
                         client_addr: str = Depends(get_client_addr),
                         csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ GET /zone/{zone_id}")
    (zone_list, err) = api.api_zone_list(traceid, user_id, zone_id)
    return respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request)


@app.post("/zone")
async def func_create_zone(request: Request,
                           user_id: str = Depends(get_authorized_user),
                           traceid: str = Depends(get_traceid),
                           client_addr: str = Depends(get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ POST /zone")
    body = await get_request_body(request)
    return zone_update(traceid, None, body, client_addr, user_id, request, csrf_protect, "create_zone")


@app.put("/zone/{zone_id}")
async def func_upsert_zone(zone_id: str,
                           request: Request,
                           user_id: str = Depends(get_authorized_user),
                           traceid: str = Depends(get_traceid),
                           client_addr: str = Depends(get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ PUT /zone/{zone_id}")
    body = await get_request_body(request)
    return zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, "update_zone")


@app.put("/zone/{zone_id}/buckets")
async def func_upsert_zone_buckets(zone_id: str,
                           request: Request,
                           user_id: str = Depends(get_authorized_user),
                           traceid: str = Depends(get_traceid),
                           client_addr: str = Depends(get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ PUT /zone/{zone_id}/buckets")
    body = await get_request_body(request)
    return zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, "update_buckets")


@app.put("/zone/{zone_id}/accessKeys")
async def func_upsert_zone_secret(zone_id: str,
                           request: Request,
                           user_id: str = Depends(get_authorized_user),
                           traceid: str = Depends(get_traceid),
                           client_addr: str = Depends(get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ PUT /zone/{zone_id}/accessKeys")
    body = await get_request_body(request)
    return zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, "change_secret_key")


def zone_update(traceid, zone_id, body, client_addr, user_id, request, csrf_protect, how):
    logger.debug(f"@@@ traceid: {traceid}")
    logger.debug(f"@@@ zone_id: {zone_id}")
    logger.debug(f"@@@ body: {body}")
    logger.debug(f"@@@ user_id: {user_id}")
    logger.debug(f"@@@ how: {how}")
    logger.debug(f"@@@ csrf_protect: {csrf_protect}")
    csrf_token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(csrf_token)
    zone = body.get("zone")
    logger.debug(f"@@@ api_upsert: {user_id} {zone_id} {zone}")
    (zone_list, err) = api.api_upsert(traceid, user_id, zone_id, zone, how)
    return respond_zone(zone_list, err, None, client_addr, user_id, request)


@app.delete("/zone/{zone_id}")
async def func_delete_zone(zone_id: str,
                           request: Request,
                           user_id: str = Depends(get_authorized_user),
                           traceid: str = Depends(get_traceid),
                           client_addr: str = Depends(get_client_addr),
                           csrf_protect: CsrfProtect = Depends()):
    logger.debug(f"@@@ DELETE /zone/{zone_id}")
    body = await get_request_body(request)
    csrf_token = body.get("CSRF-Token")
    csrf_protect.validate_csrf(csrf_token)
    err = api.api_delete(traceid, user_id, zone_id)
    return respond_zone(None, err, None, client_addr, user_id, request)


def respond_zone(zone_list, err, csrf_protect, client_addr, user_id, request):

#HTTP_503_SERVICE_UNAVAILABLE
#Retry-After

    if err:
        content = {"status": "error", "reason": err}
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        content = {"status": "success"}
        status_code = status.HTTP_200_OK
    if zone_list is not None:  # do not miss []
        content["zonelist"] = zone_list
    if csrf_protect:
        content["CSRF-Token"] = csrf_protect.generate_csrf()
    content["time"] = str(int(time.time()))
    accesslog(f"{status_code}", client_addr, user_id, request.method, request.url)
    response = JSONResponse(status_code=status_code, content=content)
    logger.debug(f"@@@ RESPONSE.CONTENT {content}")
    return response


async def get_request_body(request):
    body = b""
    async for chunk in request.stream():
        body += chunk
    return safe_json_loads(body, parse_int=str)


@app.middleware("http")
async def validate_session(request: Request, call_next):
    peer_addr = str(request.client.host)
    peer_addr = normalize_address(peer_addr)
    #logger.debug(f"@@@: {request}")
    #logger.debug(f"@@@: {request.headers}")
    #logger.debug(f"@@@: {request.method}")
    #logger.debug(f"@@@: {request.url}")
    #logger.debug(f"@@@: {request.base_url}")
    #logger.debug(f"@@@: {request.query_params}")
    #logger.debug(f"@@@: {request.path_params}")

    user_id = await get_authorized_user(request)
    client_addr = await get_client_addr(request)
    #logger.debug(f"@@@ api_check_user: {user_id} {client_addr}")

    if peer_addr not in api.trusted_hosts:
        logger.error(f"IP {peer_addr} is not allowed to access this resource.")
        # This error is a server configuration error. As end users cannot address this
        # error. So that, our error message will provide information that there
        # was an error, simply and hiding {peer_addr} from end-user.
        #  DONT TELL END USERS THAT REAL ERROR WAS: 
        #  "IP {peer_addr} is not allowed to access this resource."
        content = {"status": "error", "reason": f"Internal configuration error. (forbidded)"}
        status_code = status.HTTP_403_FORBIDDEN
        # Access log contains client_addr, but peer_addr.
        accesslog(f"{status_code}", client_addr, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)

    if not api.api_check_user(user_id):
        logger.error(f"access denied: user: {user_id}")
        content = {"status": "error", "reason": f"{user_id}: no such user"}
        content["time"] = str(int(time.time()))
        status_code = status.HTTP_401_UNAUTHORIZED
        accesslog(f"{status_code}", client_addr, user_id, request.method, request.url)
        return JSONResponse(status_code=status_code, content=content)

    logger.info(f"allowed: user: {user_id}")

    return await call_next(request)
