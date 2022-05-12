"""Multiplexer.  It is a gunicorn app."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import errno
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from lenticularis.utility import Read1Reader, parse_s3_auth
from lenticularis.utility import accesslog
from lenticularis.utility import get_ip_address
from lenticularis.utility import logger
from lenticularis.utility import normalize_address
from lenticularis.utility import tracing


_connection_errors = [errno.ETIMEDOUT, errno.ECONNREFUSED,
                      errno.EHOSTDOWN, errno.EHOSTUNREACH]


def _fake_user_id(access_key_id):
    return f"access-key-id={access_key_id}"

def _check_url_error_is_connection_errors(x):
    if x.errno in _connection_errors:
        return x.errno
    elif x.reason is not None and x.reason.errno in _connection_errors:
        return x.reason.errno
    else:
        logger.debug(f"Cannot find errno in URLError={x}")
        return 0


class Multiplexer():

    def __init__(self, mux_conf, tables, controller, node):
        self.node = node
        self.mux_key = None  # dummy initial value
        self.tables = tables
        self.controller = controller
        self.start = time.time()
        gunicorn_conf = mux_conf["gunicorn"]
        lenticularis_conf = mux_conf["lenticularis"]
        multiplexer_param = lenticularis_conf["multiplexer"]
        self.facade_hostname = multiplexer_param["facade_hostname"].lower()
        #self.facade_hostnames = [e.lower() for e in facade_hostnames]

        trusted_proxies = multiplexer_param["trusted_proxies"]
        self.trusted_proxies = set([addr for h in trusted_proxies
                                       for addr in get_ip_address(h)])
        self.active_multiplexers = self.current_active_multiplexers()
        logger.debug(f"@@@ trusted_proxies = {self.trusted_proxies}")
        logger.debug(f"@@@ active_multiplexers = {self.active_multiplexers}")

        #XXXself.mux_reqest_timeout = 300  # XXX FIXME
        self.request_timeout = int(multiplexer_param["request_timeout"])

        # manager params
        controller_param = lenticularis_conf["controller"]
        self.watch_interval = int(controller_param["watch_interval"])
        self.mc_info_timelimit = int(controller_param["mc_info_timelimit"])
        self.refresh_margin = int(controller_param["refresh_margin"])

        mux_host = node
        mux_port = gunicorn_conf["port"]
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
        # logger.debug(f"@@@ RDS = {list(self.tables.process_table.get_mux_list(None))}")
        mux_list = self.tables.process_table.get_mux_list(None)
        muxs = [v["mux_conf"]["lenticularis"]["multiplexer"]["host"] for (e, v) in mux_list]
        # logger.debug(f"@@@ muxs = {muxs}")
        return set([addr for h in muxs for addr in get_ip_address(h)])


    def register_mux_info(self, next_sleep_time):
        # logger.debug("@@@ +++")
        now = time.time()
        mux_info = {"mux_conf": self.mux_conf_subset,
                    "start_time": f"{self.start}",
                    "last_interrupted_time": f"{now}"}
        self.tables.process_table.set_mux(self.mux_key, mux_info,
                               int(next_sleep_time + self.refresh_margin))

    def timer_interrupt(self, next_sleep_time):
        # logger.debug("@@@ +++")
        self.register_mux_info(next_sleep_time)


    def __del__(self):
        logger.debug("@@@ MUX_MAIN: __DEL__")
        self.tables.process_table.del_mux(self.mux_key)


    def __call__(self, environ, start_response):
        try:
            return self.process_request(environ, start_response)
        except Exception as e:
            port = environ.get("SERVER_PORT")
            logger.error(f"Unhandled exception in MUX(port={port}) processing:"
                         f" exception={e}")
        start_response("500", [])
        return []


    def process_request(self, environ, start_response):
        """Processes a request from gunicorn.  It forwards a request/response
        to/from MinIO."""

        traceid = environ.get("HTTP_X_TRACEID")
        tracing.set(traceid)

        ##server_name = environ.get("SERVER_NAME")
        server_port = environ.get("SERVER_PORT")
        peer_addr = environ.get("REMOTE_ADDR")

        ##x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        ##x_forwarded_host = environ.get("HTTP_X_FORWARDED_HOST")
        x_real_ip = environ.get("HTTP_X_REAL_IP")
        client_addr = x_real_ip if x_real_ip else peer_addr

        path = environ.get("RAW_URI")
        request_method = environ.get("REQUEST_METHOD")
        request_proto = environ.get("HTTP_X_FORWARDED_PROTO")
        request_proto = request_proto if request_proto else "?"

        ### X-Remote-User is not set!
        ### AuthKey? << mandatory!!!

        host = environ.get("HTTP_HOST")
        host = host if host else "-"

        auth = environ.get("HTTP_AUTHORIZATION")

        request_url = f"{request_proto}://{host}{path}"

        logger.debug(f"MUX(port={server_port}) got a request:"
                     f" {request_method} {request_url};"
                     f" remote=({peer_addr}),"
                     f" auth=({auth})")

        access_key_id = self.get_access_key_id(auth)

        if not self.check_accesser(peer_addr):
            user_id = _fake_user_id(access_key_id)
            status = "403"
            accesslog(status, client_addr, user_id, request_method, request_url)
            logger.debug(f"Deny access from remote={peer_addr}")
            start_response(status, [])
            return []

        q_headers = {h[5:].replace('_', '-'): environ.get(h)
                     for h in environ if h.startswith("HTTP_")}
        content_type = environ.get("CONTENT_TYPE")
        if content_type:
            q_headers["CONTENT-TYPE"] = content_type
        content_length = environ.get("CONTENT_LENGTH")
        if content_length:
            q_headers["CONTENT-LENGTH"] = content_length

        logger.debug(f"(MUX)#1")

        (dest_addr, zone_id) = self._get_dest_addr(traceid, q_headers)

        ## The pair (dest_addr, zone_id) is:
        ## - (string, string) => success
        ## - (string, None)   => never
        ## - (int, None)      => failure in resolving pool-id
        ## - (int, string)    => failure in starting MinIO

        logger.debug(f"(MUX)#2")

        if isinstance(dest_addr, int):
            ## we are here becasuse
            # 1. cannot resolve access key id nor direct name, so that could not get zone_id.
            # 2. succeeded to resolve zone_id, but failed to start minio.
            status = f"{dest_addr}"
            logger.debug(f"@@@ FAIL: status(dest_addr) = {status}")
            user_id = self._zone_to_user(zone_id) if zone_id else None
            user_id = user_id if user_id else _fake_user_id(access_key_id)
            accesslog(status, client_addr, user_id, request_method, request_url)
            logger.debug(f"(MUX) FAILED")
            start_response(status, [])
            return []

        proto = "http"
        url = f"{proto}://{dest_addr}{path}"
        input = environ.get("wsgi.input")

        sniff = False

        if input and sniff:
            input = Read1Reader(input.reader, sniff=True, sniff_marker=">", use_read=True)

        req = Request(url, data=input, headers=q_headers, method=request_method)
        try:
            res = urlopen(req, timeout=self.request_timeout)
            status = f"{res.status}"
            r_headers = res.getheaders()
            respiter = self._wrap_res(environ, res, r_headers, sniff=sniff, sniff_marker="<")

        except HTTPError as e:
            logger.error(f"urlopen error: url={url} for {request_method} {request_url}; exception={e}")
            ## logger.exception(e)  # do not record exception detail
            status = f"{e.code}"
            r_headers = [(k, e.headers[k]) for k in e.headers]
            respiter = self._wrap_res(environ, e, r_headers, sniff=sniff, sniff_marker="<E")

        except URLError as e:
            logger.error(f"urlopen error: url={url} for {request_method} {request_url}; exception={e}")
            if _check_url_error_is_connection_errors(e):
                ## "Connection refused" etc.
                logger.debug(f"CLEAR TABLE AND RETRY")

            status = "503"
            r_headers = []
            respiter = []

        except Exception as e:
            logger.error(f"urlopen error: url={url} for {request_method} {request_url}; exception={e}")
            logger.exception(e)
            try:
                status = f"{e.code}"
            except:
                status = "500"
            r_headers = []
            respiter = []

        if respiter != []:
            # update atime
            jitter = 0  # NOTE: fixed to 0
            initial_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit
            atime_timeout = initial_idle_duration + self.refresh_margin
            atime = f"{int(time.time())}"
            self.tables.routing_table.set_atime_by_addr_(dest_addr, atime, atime_timeout)
            self.tables.routing_table.set_route_expiry(zone_id, atime_timeout)

        user_id = self._zone_to_user(zone_id)

        content_length_downstream = next((v for (k, v) in r_headers if k.lower() == "content-length"), None)

        accesslog(status, client_addr, user_id, request_method, request_url,
            content_length_upstream=content_length,
            content_length_downstream=content_length_downstream)

        logger.debug(f"(MUX) DONE")
        start_response(status, r_headers)
        return respiter


    def _zone_to_user(self, zoneID):  # CODE CLONE @ zoneadm.py
            zone = self.tables.storage_table.get_zone(zoneID)
            if zone is None:
                return None
            return zone["user"]


    def _wrap_res(self, environ, res, headers, sniff=False, sniff_marker=""):
        if self.unbufferp(headers) or sniff:
            return Read1Reader(res, sniff=sniff, sniff_marker=sniff_marker, thunk=res)
        else:
            file_wrapper = environ["wsgi.file_wrapper"]
            return file_wrapper(res)


    def check_accesser(self, peer_addr):
        if peer_addr is None:
            return False
        addr = normalize_address(peer_addr)
        if (addr in self.trusted_proxies or
            addr in self.active_multiplexers):
            return True
        self.active_mutilpexers = self.current_active_multiplexers()
        if addr in self.active_mutilpexers:
            return True
        return False


    def unbufferp(self, headers):
        if any(True for (k, v) in headers if k.lower() == "x-accel-buffering" and v.lower() == "no"):
            return True
        if any(True for (k, v) in headers if k.lower() == "content-length"):
            return False
        return True


    def _get_dest_addr(self, traceid, headers):
        ## (It drops a host if it is attached by the facade).
        ## (A host may include a port, a facade may not).

        host = headers.get("HOST")
        if host:
            host = host.lower()
        if host == self.facade_hostname:
            host = None

        #logger.debug(f"@@@ HOST: {headers.get('HOST')}")
        #logger.debug(f"@@@ host: {host}")
        #logger.debug(f"authorization-header={headers.get('AUTHORIZATION')}")

        ## TEMPORARILY BAN HOST ACCESSES.
        host = None
        if host:
            access_key_id = None
            r = self.tables.routing_table.get_route_by_direct_hostname_(host)
            zone_id = self.tables.storage_table.get_zoneID_by_directHostname(host)
            r = self.tables.routing_table.get_route(zone_id)
        else:
            auth = headers.get("AUTHORIZATION")
            access_key_id = self.get_access_key_id(auth)
            r = self.tables.routing_table.get_route_by_access_key_(access_key_id)
            zone_id = self.tables.storage_table.get_pool_by_access_key(access_key_id)
            r = self.tables.routing_table.get_route(zone_id)

        if r is not None:
            ## A route to minio found if r != None.
            return (r, zone_id)
        else:
            ## A route to minio not found.
            (r, zone_id) = self.controller.route_request(traceid, host, access_key_id)
            return (r, zone_id)


    def get_access_key_id(self, authorization):
        if authorization is None:
            return None
        return parse_s3_auth(authorization)
