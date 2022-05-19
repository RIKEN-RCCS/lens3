"""Multiplexer.  It is a gunicorn app."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import errno
import time
import random
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from lenticularis.utility import Read1Reader, parse_s3_auth
from lenticularis.utility import get_ip_address
from lenticularis.utility import normalize_address
from lenticularis.utility import host_port
from lenticularis.utility import log_access
from lenticularis.utility import logger
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

    def __init__(self, mux_conf, tables, controller, host, port):
        self._verbose = False
        ##self.node = host
        self._mux_host = host
        self._mux_port = port
        self.tables = tables
        self.controller = controller
        self.start = time.time()
        gunicorn_conf = mux_conf["gunicorn"]
        lenticularis_conf = mux_conf["lenticularis"]

        multiplexer_conf = lenticularis_conf["multiplexer"]
        self.facade_hostname = multiplexer_conf["facade_hostname"].lower()
        trusted_proxies = multiplexer_conf["trusted_proxies"]
        self.trusted_proxies = set([addr for h in trusted_proxies
                                       for addr in get_ip_address(h)])
        self.request_timeout = int(multiplexer_conf["request_timeout"])
        timer = int(multiplexer_conf["timer_interval"])
        self.periodic_work_interval = timer

        self.active_multiplexers = self._list_mux_ip_addresses()

        controller_conf = lenticularis_conf["controller"]
        self.watch_interval = int(controller_conf["watch_interval"])
        self.mc_info_timelimit = int(controller_conf["mc_info_timelimit"])
        self.refresh_margin = int(controller_conf["refresh_margin"])

        # we do not need register mux_info here,
        # as muxmain is going to call timer_interrupt at once.
        # self._register_mux_info()


    def __del__(self):
        logger.debug("@@@ MUX_MAIN: __DEL__")
        self.tables.process_table.delete_mux(self._mux_host)


    def __call__(self, environ, start_response):
        try:
            return self._process_request(environ, start_response)
        except Exception as e:
            port = environ.get("SERVER_PORT")
            logger.error(f"Unhandled exception in MUX(port={port}) processing:"
                         f" exception={e}")
        start_response("500", [])
        return []


    def periodic_work(self):
        interval = self.periodic_work_interval
        logger.debug(f"Mux periodic_work started: interval={interval}.")
        assert interval >= 10
        time.sleep(random.random() * interval)
        while True:
            try:
                self._register_mux_info(interval)
            except Exception as e:
                logger.error(f"Mux periodic_work failed: exception={e}")
                pass
            jitter = (2 * random.random())
            time.sleep(interval + jitter)


    def _list_mux_ip_addresses(self):
        muxs = self.tables.process_table.list_mux_eps()
        return set([addr for (h, p) in muxs for addr in get_ip_address(h)])


    def _register_mux_info(self, sleeptime):
        if self._verbose:
            logger.debug(f"Updating Mux info periodically, interval={sleeptime}.")
        now = time.time()
        mux_desc = {"host": self._mux_host, "port": self._mux_port,
                    "start_time": f"{self.start}",
                    "last_interrupted_time": f"{now}"}
        ep = host_port(self._mux_host, self._mux_port)
        self.tables.process_table.set_mux(ep, mux_desc,
                                          int(sleeptime + self.refresh_margin))

    def _process_request(self, environ, start_response):
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

        access_key_id = self._get_access_key_id(auth)

        if not self._check_accesser(peer_addr):
            user_id = _fake_user_id(access_key_id)
            status = "403"
            log_access(status, client_addr, user_id, request_method, request_url)
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

        (dest_addr, code, zone_id) = self._get_dest_addr(traceid, q_headers)

        logger.debug(f"(MUX)#2")

        if dest_addr is None:
            status = f"{code}"
            logger.debug(f"@@@ FAIL: status(dest_addr) = {status}")
            user_id = self._zone_to_user(zone_id) if zone_id else None
            user_id = user_id if user_id else _fake_user_id(access_key_id)
            log_access(status, client_addr, user_id, request_method, request_url)
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
            status = "500"
            r_headers = []
            respiter = []

        if respiter != []:
            # update atime
            jitter = 0  # NOTE: fixed to 0
            initial_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit
            atime_timeout = initial_idle_duration + self.refresh_margin
            ##atime = f"{int(time.time())}"
            ##self.tables.routing_table.set_atime_by_addr_(dest_addr, atime, atime_timeout)
            self.tables.routing_table.set_route_expiry(zone_id, atime_timeout)

        user_id = self._zone_to_user(zone_id)

        content_length_downstream = next((v for (k, v) in r_headers if k.lower() == "content-length"), None)

        log_access(status, client_addr, user_id, request_method, request_url,
                   upstream=content_length,
                   downstream=content_length_downstream)

        logger.debug(f"(MUX) DONE")
        start_response(status, r_headers)
        return respiter


    def _zone_to_user(self, zoneID):  # CODE CLONE @ zoneadm.py
        zone = self.tables.storage_table.get_zone(zoneID)
        if zone is None:
            return None
        return zone["owner_uid"]


    def _wrap_res(self, environ, res, headers, sniff=False, sniff_marker=""):
        if self._unbufferp(headers) or sniff:
            return Read1Reader(res, sniff=sniff, sniff_marker=sniff_marker, thunk=res)
        else:
            file_wrapper = environ["wsgi.file_wrapper"]
            return file_wrapper(res)


    def _check_accesser(self, peer_addr):
        if peer_addr is None:
            return False
        addr = normalize_address(peer_addr)
        if (addr in self.trusted_proxies or
            addr in self.active_multiplexers):
            return True
        self.active_mutilpexers = self._list_mux_ip_addresses()
        if addr in self.active_mutilpexers:
            return True
        return False


    def _unbufferp(self, headers):
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
            access_key_id = self._get_access_key_id(auth)
            ##r = self.tables.routing_table.get_route_by_access_key_(access_key_id)
            zone_id = self.tables.storage_table.get_pool_by_access_key(access_key_id)
            r = self.tables.routing_table.get_route(zone_id)

        if r is not None:
            ## A MinIO endpoint exists.
            return (r, 200, zone_id)
        else:
            ## A route to minio is not found.
            (r, code, zone_id) = self.controller.start_minio_service(traceid, host, access_key_id)
            return (r, code, zone_id)


    def _get_access_key_id(self, authorization):
        if authorization is None:
            return None
        return parse_s3_auth(authorization)
