# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from lenticularis.utility import Read1Reader, parse_s3_auth
from lenticularis.utility import accesslog
from lenticularis.utility import get_ip_address
from lenticularis.utility import logger
from lenticularis.utility import normalize_address
import os
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class Multiplexer():
    def __init__(self, mux_conf, tables, controller, node):
        self.node = node
        self.mux_key = None  # dummy initial value
        self.tables = tables
        self.controller = controller
        self.start = time.time()
        lenticularis_conf = mux_conf["lenticularis"]
        multiplexer_param = lenticularis_conf["multiplexer"]
        delegate_hostnames = multiplexer_param["delegate_hostnames"]
        self.delegate_hostnames = [e.lower() for e in delegate_hostnames]

        trusted_hosts = multiplexer_param["trusted_hosts"]
        self.trusted_hosts = set([addr for h in trusted_hosts
                                       for addr in get_ip_address(h)])
        self.active_multiplexers = self.current_active_multiplexers()
        logger.debug(f"@@@ trusted_hosts = {self.trusted_hosts}")
        logger.debug(f"@@@ active_multiplexers = {self.active_multiplexers}")

        #XXXself.mux_reqest_timeout = 300  # XXX FIXME
        self.request_timeout = int(multiplexer_param["request_timeout"])

        # manager params
        controller_param = lenticularis_conf["controller"]
        self.watch_interval = int(controller_param["watch_interval"])
        self.mc_info_timelimit = int(controller_param["mc_info_timelimit"])
        self.refresh_margin = int(controller_param["refresh_margin"])

        mux_host = node
        mux_port = multiplexer_param["port"]
        self.mux_key = mux_host

        self.mux_conf_subset = {
            "lenticularis": {
                "multiplexer": {
                    "host": mux_host,
                    "port": mux_port,
                },
            },
        }

        # we do not need register mux_info here,
        # as muxmain is going to call timer_interrupt at once.
        # self.register_mux_info()

    def current_active_multiplexers(self):
        # logger.debug("@@@ +++")
        # logger.debug(f"@@@ RDS = {list(self.tables.processes.get_mux_list(None))}")
        mux_list = self.tables.processes.get_mux_list(None)
        muxs = [v["mux_conf"]["lenticularis"]["multiplexer"]["host"] for (e, v) in mux_list]
        # logger.debug(f"@@@ muxs = {muxs}")
        return set([addr for h in muxs for addr in get_ip_address(h)])

    def register_mux_info(self, next_sleep_time):
        # logger.debug("@@@ +++")
        now = time.time()
        mux_info = {"mux_conf": self.mux_conf_subset,
                    "start_time": f"{self.start}",
                    "last_interrupted_time": f"{now}"}
        self.tables.processes.set_mux(self.mux_key, mux_info,
                               int(next_sleep_time + self.refresh_margin))

    def timer_interrupt(self, next_sleep_time):
        # logger.debug("@@@ +++")
        self.register_mux_info(next_sleep_time)

    def __del__(self):
        logger.debug("@@@ MUX_MAIN: __DEL__")
        self.tables.processes.del_mux(self.mux_key)

    def __call__(self, environ, start_response):
        traceid = environ.get("HTTP_X_TRACEID")
        threading.currentThread().name = traceid
        logger.debug(f"@@@ MUX_MAIN: __CALL__")
        # logger.debug(f"@@@ environ = {environ}")

        peer_addr = environ.get("REMOTE_ADDR")

        # DO NOT RETURN HERE UNLESS `remote_addr` is not None.
        #if remote_addr is None:
        #    logger.error("missing 'REMOTE_ADDR'")
        #    return None

        logger.debug(f"@@@ PEER ADDR {peer_addr}")

        # x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        x_real_ip = environ.get("HTTP_X_REAL_IP")
        #if not x_real_ip:
        #    logger.warning(f"HTTP_X_REAL_IP is not set")
        client_addr = x_real_ip if x_real_ip else peer_addr

        path = environ.get("RAW_URI")
        request_method = environ.get("REQUEST_METHOD")
        request_proto = environ.get("HTTP_X_FORWARDED_PROTO")
        if not request_proto:
            logger.warning(f"HTTP_X_FORWARDED_PROTO is not set")
        # NOTUSED forwarded_host = environ.get("HTTP_X_FORWARDED_HOST")


### X-Remote-User is not set!
### AuthKey? << mandatory!!!
### 
        #logger.debug(f"@@@ environ {type(environ)}")
        #logger.debug(f"@@@ environ {environ}")
        #user_id = zone_adm.zone_to_user(zone_id)
        host = environ.get("HTTP_HOST")
        host = host if host else "-"
        access_key_id = self.get_access_key_id(environ.get("HTTP_AUTHORIZATION"))

        request_url = f"{request_proto}://{host}{path}"

        # assert('client_addr' in vars())
        # assert(client_addr != None)
        # assert('access_key_id' in vars())
        # assert('request_method' in vars())
        # assert('host' in vars())
        # assert('path' in vars())

        if not self.check_access(peer_addr):
            status = "400"  # 400 Bad Request
            logger.info(f"DENY: {peer_addr}")
            user_id = f"Access_Key_ID:{access_key_id}"
            accesslog(status, client_addr, user_id, request_method, request_url)
            start_response(status, [])
            return []

        logger.info(f"ALLOW: {peer_addr}")

        #logger.debug(f"@@@ MATCH    {peer_addr}")

        headers = [(h[5:].replace('_', '-'), environ.get(h))
                   for h in environ if h.startswith("HTTP_")]

        # logger.debug(f"@@@ > HEADERS FROM ENVIRON {headers}")
        headers = dict(headers)

        content_type = environ.get("CONTENT_TYPE")
        if content_type:
            headers["CONTENT-TYPE"] = content_type

        content_length = environ.get("CONTENT_LENGTH")
        if content_length:
            headers["CONTENT-LENGTH"] = content_length

        def zone_to_user(zoneID):  # CODE CLONE @ zoneadm.py
            zone = self.tables.zones.get_zone(zoneID)
            if zone is None:
                return None
            return zone["user"]

        # now, lookup the routing table
        (dest_addr, zone_id) = self.get_dest_addr(traceid, headers)  # minioAddr or muxAddr
        # (int, None)      => could not resolve zone
        # (int, string)    => zone successfuly resolved, but could not start minio
        # (string, string) => success
        # (string, None)   => should not happen
        if isinstance(dest_addr, int):
            ## we are here becasuse 
            # 1. cannot resolve access key id nor direct name, so that could not get zone_id.
            # 2. succeeded to resolve zone_id, but failed to start minio.
            status = f"{dest_addr}"
            logger.debug(f"@@@ FAIL: status(dest_addr) = {status}")
            user_id = zone_to_user(zone_id) if zone_id else None
            user_id = user_id if user_id else f"Access_Key_ID:{access_key_id}"
            accesslog(status, client_addr, user_id, request_method, request_url)
            start_response(status, [])
            return []
        logger.debug(f"@@@ SUCCESS: dest_addr = {dest_addr} node = {self.node}")

        proto = "http"
        url = f"{proto}://{dest_addr}{path}"

        input = environ.get("wsgi.input")
        file_wrapper = environ["wsgi.file_wrapper"]

        def wrap_res(res, headers, sniff=False, sniff_marker=""):
            if self.unbufferp(headers) or sniff:
                logger.debug("@@@ READ1READER")
                return Read1Reader(res, sniff=sniff, sniff_marker=sniff_marker, thunk=res)
            else:
                logger.debug("@@@ FILE_WRAPPER")
                return file_wrapper(res)

        #sniff = True  # DEBUG FLAG FOR DEVELOPER
        #              # WARNING: turning on `sniff` makes logger to emit sensitive information. use with grate care.
        sniff = False

        logger.debug(f"@@@ > REQUEST {request_method} {url}")
        logger.debug(f"@@@ > HEADERS {headers}")

        if input and sniff:
            input = Read1Reader(input.reader, sniff=True, sniff_marker=">", use_read=True)

        req = Request(url, data=input, headers=headers, method=request_method)
        try:
            res = urlopen(req, timeout=self.request_timeout)
            status = f"{res.status}"
            headers = res.getheaders()
            logger.debug(f"@@@ < HEADERS {headers}")
            logger.debug(f"@@@ res = {res}")
            respiter = wrap_res(res, headers, sniff=sniff, sniff_marker="<")

        except HTTPError as e:
            logger.error(f"HTTP ERROR: {request_method} {request_url} => {url} {e}")
            # logger.exception(e)  # do not record exception detail
            status = f"{e.status}"
            headers = [(k, e.headers[k]) for k in e.headers]
            respiter = wrap_res(e, headers, sniff=sniff, sniff_marker="<E")
            #respiter = file_wrapper(e, sniff=sniff)

        except URLError as e:
            logger.error(f"URL Error {request_method} {request_url} => {url} {e}")
            # logger.exception(e)  # do not record exception detail
            status = "400"
            headers = []
            respiter = []

        except Exception as e:
            logger.error(f"EXCEPTION {request_method} {request_url} => {url} {e}")
            logger.exception(e)
            try:
                status = f"{e.status}"
            except:
                status = "500"  # 500 Internal Server Error
            headers = []
            respiter = []

        if respiter != []:
            # update atime
            jitter = 0  # NOTE: fixed to 0
            initial_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit
            atime_timeout = initial_idle_duration + self.refresh_margin
            atime = f"{int(time.time())}"
            self.tables.routes.set_atime_by_addr(dest_addr, atime, atime_timeout)

        logger.debug(f"@@@ ZONE_ID {zone_id}")
        user_id = zone_to_user(zone_id)
        logger.debug(f"@@@ ZONE_OWNER {user_id}")

        content_length_downstream = next((v for (k, v) in headers if k.lower() == "content-length"), None)

        accesslog(status, client_addr, user_id, request_method, request_url, 
            content_length_upstream=content_length,
            content_length_downstream=content_length_downstream)

        logger.debug(f"@@@ < STATUS {status}")
        # logger.debug(f"@@@ < HEADERS {headers}")
        # logger.debug(f"@@@ < RESPITER {respiter}")
        start_response(status, headers)
        return respiter

    def check_access(self, peer_addr):
        if peer_addr is None:
            logger.error("missing 'REMOTE_ADDR'")  # enviornment variable's name is "REMOTE_ADDR", not "PEER_ADDR"
            return False
        peer_addr = normalize_address(peer_addr)
        # logger.debug("@@@ +++")
        # logger.debug(f"@@@ {peer_addr} {self.trusted_hosts}")
        # logger.debug(f"@@@ {peer_addr} {self.active_multiplexers}")
        if (peer_addr in self.trusted_hosts or
            peer_addr in self.active_multiplexers):
            return True
        self.active_mutilpexers = self.current_active_multiplexers()
        # logger.debug(f"@@@ TRUSTED_HOSTS = {self.active_mutilpexers}")
        # logger.debug(f"@@@ peer_addr = {peer_addr}")
        if peer_addr in self.active_mutilpexers:
            return True
        return False


    def unbufferp(self, headers):
        if any(True for (k, v) in headers if k.lower() == "x-accel-buffering" and v.lower() == "no"):
            return True
        if any(True for (k, v) in headers if k.lower() == "content-length"):
            return False
        return True

    def get_dest_addr(self, traceid, headers):
        # logger.debug("@@@ +++")
        # logger.debug(f"@@@ get_dest_addr")

        host = headers.get("HOST")
        if host:  # do not pick up host here, if it's a empty string. "" => false
            host = host.lower()
            if host in self.delegate_hostnames:
                host = None
        # logger.debug(f"@@@ HOST: {headers.get('HOST')}")
        # logger.debug(f"@@@ host: {host}")
        # logger.debug(f"@@@ AUTHORIZATION: {headers.get('AUTHORIZATION')}")

        if host:
            access_key_id = None
            r = self.tables.routes.get_route_by_direct_hostname(host)
            zone_id = self.tables.zones.get_zoneID_by_directHostname(host)
        else:
            access_key_id = self.get_access_key_id(headers.get("AUTHORIZATION"))
            # logger.debug(f"@@@ access_key_id: {access_key_id}")
            r = self.tables.routes.get_route_by_access_key(access_key_id)
            zone_id = self.tables.zones.get_zoneID_by_access_key_id(access_key_id)

        if r:  # a route to minio found!
            logger.debug(f"@@@ SUCCESS: {r}")
            # assert(zone_id is not None)
            if not zone_id:
                # raise Exception("SHOULD NOT HAPPEN: zone_id must defined here")
                logger.error("SHOULD NOT HAPPEN: zone_id must defined here")
                return (500, None)
            return (r, zone_id)

        return self.controller.route_request(traceid, host, access_key_id)

    def get_access_key_id(self, authorization):
        if authorization is None:
            return None
        return parse_s3_auth(authorization)
