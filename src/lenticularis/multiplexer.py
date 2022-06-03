"""Multiplexer.  It forwards a request/response from/to MinIO.  It is
a Gunicorn app.
"""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import errno
import time
import random
import posixpath
import json
import http.client
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import urllib.parse
from lenticularis.scheduler import Scheduler
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import check_bucket_naming
from lenticularis.utility import access_mux, host_port
from lenticularis.utility import Read1Reader, parse_s3_auth
from lenticularis.utility import get_ip_addresses
from lenticularis.utility import make_typical_ip_address
from lenticularis.utility import host_port
from lenticularis.utility import log_access
from lenticularis.utility import logger
from lenticularis.utility import tracing


_connection_errors = [errno.ETIMEDOUT, errno.ECONNREFUSED,
                      errno.EHOSTDOWN, errno.EHOSTUNREACH]


def _uppercase_headers__(d):
    assert isinstance(d, http.client.HTTPMessage)
    return {k.upper(): d.get(k).upper() for k in d}


def _uppercase_dict__(d):
    assert isinstance(d, dict)
    return {k.upper(): v.upper() for (k, v) in d.items()}


def _no_buffering(headers):
    if any(True for (k, v) in headers if k.upper() == "X-ACCEL-BUFFERING" and v.upper() == "NO"):
        return True
    if any(True for (k, v) in headers if k.upper() == "CONTENT-LENGTH"):
        return False
    return True


def _fake_user_id(access_key):
    """Returns an access-key as a substitute of user-id for logging."""
    return f"access-key={access_key}"


def _check_url_error_is_connection_errors(x):
    if x.errno in _connection_errors:
        return x.errno
    elif x.reason is not None and x.reason.errno in _connection_errors:
        return x.reason.errno
    else:
        logger.debug(f"Cannot find errno in URLError={x}")
        return 0


def _get_pool_for_probe_key(probe_key, access_info):
    """Checks a key is a probe-key, and returns a pool-id for which it is
    created."""
    if (probe_key is not None
        and probe_key.get("use") == "access_key"
        and probe_key.get("secret_key") == ""):
        return probe_key.get("owner")
    log_access("401", *access_info)
    raise Api_Error(403, f"Bad access to the root path")


class Multiplexer():
    """Mux.  It forwards requests to MinIO."""

    def __init__(self, mux_conf, tables, controller, host, port):
        self._verbose = False
        ##self.node = host
        self._mux_host = host
        self._mux_port = port
        self.tables = tables
        self.controller = controller
        self.start = time.time()
        ##gunicorn_conf = mux_conf["gunicorn"]
        ##lenticularis_conf = mux_conf["lenticularis"]

        mux_param = mux_conf["multiplexer"]
        self._facade_hostname = mux_param["facade_hostname"].lower()
        proxies = mux_param["trusted_proxies"]
        self._trusted_proxies = {addr for h in proxies
                                 for addr in get_ip_addresses(h)}
        self._forwarding_timeout = int(mux_param["forwarding_timeout"])
        timer = int(mux_param["mux_endpoint_update"])
        self.periodic_work_interval = timer
        self.probe_access_timeout = int(mux_param["probe_access_timeout"])

        self._multiplexer_addrs = self._list_mux_ip_addresses()

        ctl_param = mux_conf["controller"]
        self.watch_interval = int(ctl_param["watch_interval"])
        self.heartbeat_timeout = int(ctl_param["heartbeat_timeout"])
        self.scheduler = Scheduler(tables)
        return

    def __del__(self):
        logger.debug("@@@ MUX_MAIN: __DEL__")
        self.tables.process_table.delete_mux(self._mux_host)
        return

    def __call__(self, environ, start_response):
        try:
            return self._process_request(environ, start_response)
        except Api_Error as e:
            port = environ.get("SERVER_PORT")
            logger.error(f"Unhandled exception in MUX(port={port}) processing:"
                         f" exception={e}",
                         exc_info=True)
            status = f"{e.code}"
            start_response(status, [])
            return []

        except Exception as e:
            port = environ.get("SERVER_PORT")
            logger.error(f"Unhandled exception in MUX(port={port}) processing:"
                         f" exception={e}",
                         exc_info=True)
            pass
        start_response("500", [])
        return []

    def periodic_work(self):
        interval = self.periodic_work_interval
        logger.debug(f"Mux periodic_work started: interval={interval}.")
        assert self.periodic_work_interval >= 10
        time.sleep(random.random() * interval)
        while True:
            try:
                self._register_mux()
            except Exception as e:
                logger.error(f"Mux periodic_work failed: exception={e}")
                pass
            jitter = (2 * random.random())
            time.sleep(interval + jitter)
            pass
        return

    def _list_mux_ip_addresses(self):
        muxs = self.tables.process_table.list_mux_eps()
        return {addr for (h, p) in muxs for addr in get_ip_addresses(h)}

    def _register_mux(self):
        if self._verbose:
            logger.debug(f"Updating Mux info (periodically).")
            pass
        now = int(time.time())
        mux_desc = {"host": self._mux_host, "port": self._mux_port,
                    "start_time": f"{self.start}",
                    "last_interrupted_time": f"{now}"}
        ep = host_port(self._mux_host, self._mux_port)
        self.tables.set_mux(ep, mux_desc)
        return

    def _wrap_res(self, res, environ, headers, sniff=False, sniff_marker=""):
        if _no_buffering(headers) or sniff:
            return Read1Reader(res, sniff=sniff, sniff_marker=sniff_marker, thunk=res)
        else:
            file_wrapper = environ["wsgi.file_wrapper"]
            return file_wrapper(res)

    def _check_forwarding_host_trusted(self, peer_addr):
        if peer_addr is None:
            return False
        ip = make_typical_ip_address(peer_addr)
        if (ip in self._trusted_proxies or ip in self._multiplexer_addrs):
            return True
        self._multiplexer_addrs = self._list_mux_ip_addresses()
        if ip in self._multiplexer_addrs:
            return True
        return False

    def _find_pool_for_bucket(self, path, access_key, access_info):
        """Returns a pool-id for a bucket in a path.  It just checks
        bucket-policy is not none, but does not check the access-key
        is read/write.
        """
        request_url = access_info[3]
        assert path.startswith("/")
        pathc = path.split("/")
        pathc.pop(0)
        bucket = pathc[0]
        # Check a bucket name.
        if bucket == "":
            log_access("404", *access_info)
            raise Api_Error(404, f"Bad URL, no bucket name: url={request_url}")
        if not check_bucket_naming(bucket):
            log_access("400", *access_info)
            raise Api_Error(400, f"Bad URL, bad bucket name: url={bucket}")
        desc = self.tables.routing_table.get_bucket(bucket)
        if desc is None:
            log_access("404", *access_info)
            raise Api_Error(404, f"No bucket: url={request_url}")
        # Check the policy in desc["bkt_policy"].
        pool_id = desc["pool"]
        policy = desc["bkt_policy"]
        if policy != "none":
            return pool_id
        key = self.tables.pickone_table.get_id(access_key)
        if (key is not None
            and key.get("use") == "access_key"
            and key.get("owner") == pool_id
            and key.get("secret_key") is not None):
            return pool_id
        log_access("401", *access_info)
        raise Api_Error(401, f"Bad bucket policy: url={request_url}")

    def _start_service(self, traceid, pool_id, probe_key):
        # CURRENTLY, IT STARTS A SERVICE ON A LOCAL HOST.
        """Runs MinIO on a local or remote host.  Use of probe_key forces to
        run on a local host.  Otherwise, the chooser chooses a host to
        run.
        """
        if probe_key is not None:
            ep = None
        else:
            # ep = self._choose_server_host(pool_id)
            ep = None
            pass
        if ep is None:
            # Run MinIO on a local host.
            (code, ep0) = self.controller.start_service(traceid, pool_id, probe_key)
            logger.debug(f"AHOAHO MUX start_service returned: code={code}, ep={ep0}")
            return (code, ep0)
        else:
            # Run MinIO on a remote host.
            assert probe_key is None
            pooldesc = self.tables.storage_table.get_pool(pool_id)
            probe_key = pooldesc["probe_access"]
            facade_hostname = self._facade_hostname
            code = access_mux(traceid, ep, probe_key, facade_hostname,
                              self.probe_access_timeout)
            return (code, ep)
        pass

    def _choose_server_host(self, pool_id):
        # THIS IS NOT USED NOW.
        """Chooses a host to run a MinIO.  It returns None to mean the
        localhost.
        """
        (host, port) = self.scheduler.schedule(pool_id)
        if host is None:
            return None
        elif host == self._mux_host:
            return None
        else:
            return host_port(host, port)
        pass

    def _process_request(self, environ, start_response):
        """Processes a request from Gunicorn.  It forwards a request/response
        from/to MinIO."""

        # "HTTP_X-Remote-User" is not set in environ.  Refer for the
        # environ keys (except for HTTP_) to
        # https://wsgi.readthedocs.io/en/latest/definitions.html

        traceid = environ.get("HTTP_X_TRACEID")
        tracing.set(traceid)

        server_name = environ.get("SERVER_NAME")
        server_port = environ.get("SERVER_PORT")
        request_method = environ.get("REQUEST_METHOD")
        peer_addr = environ.get("REMOTE_ADDR")
        path_and_query = environ.get("RAW_URI")
        ##x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        ##x_forwarded_host = environ.get("HTTP_X_FORWARDED_HOST")

        client_addr = environ.get("HTTP_X_REAL_IP")
        #client_addr = x_real_ip if x_real_ip else peer_addr

        request_proto = environ.get("HTTP_X_FORWARDED_PROTO")
        request_proto = request_proto if request_proto else "?"

        host = environ.get("HTTP_HOST")
        host = host if host else "-"

        authorization = environ.get("HTTP_AUTHORIZATION")
        access_key = parse_s3_auth(authorization)
        user_id = _fake_user_id(access_key)

        ep = host_port(self._mux_host, self._mux_port)
        request_url = f"{request_proto}://{ep}{path_and_query}"
        u = urllib.parse.urlparse(request_url)
        path = posixpath.normpath(u.path)

        access_info = [client_addr, user_id, request_method, request_url]

        logger.debug(f"MUX(port={server_port}) got a request:"
                     f" {request_method} {request_url};"
                     f" remote=({client_addr}), auth=({authorization})")

        if not self._check_forwarding_host_trusted(peer_addr):
            logger.error(f"Untrusted proxy or unknonwn Mux: {peer_addr};"
                         f" Check configuration")
            log_access("403", *access_info)
            raise Api_Error(403, f"Bad access from remote={client_addr}")

        if path == "/":
            # Access to "/" is only allowed for probing access from Adm.
            probe_key = self.tables.pickone_table.get_id(access_key)
            pool_id = _get_pool_for_probe_key(probe_key, access_info)
            assert probe_key is not None
            logger.debug(f"MUX probing-access for pool={pool_id}")
        else:
            probe_key = None
            pool_id = self._find_pool_for_bucket(path, access_key, access_info)
            logger.debug(f"MUX access for bucket={path} in pool={pool_id}")
            pass

        assert pool_id is not None
        minio_ep = self.tables.routing_table.get_route(pool_id)

        if minio_ep is None:
            (code, ep0) = self._start_service(traceid, pool_id, probe_key)
            if code == 200:
                assert ep0 is not None and id == pool_id
                minio_ep = ep0
                pass
            pass

        # It is OK if an endpoint is found.  A check for an
        # enabled/disabled state of the pool is not checked here.

        if minio_ep is None:
            log_access("404", *access_info)
            raise Api_Error(404, f"Bucket inaccessible: url={request_url}")

        self.tables.set_access_timestamp(pool_id)

        # Copy request headers.

        q_headers = {h[5:].replace("_", "-"): environ.get(h)
                     for h in environ if h.startswith("HTTP_")}
        content_type = environ.get("CONTENT_TYPE")
        if content_type:
            q_headers["CONTENT-TYPE"] = content_type
        else:
            pass
        content_length = environ.get("CONTENT_LENGTH")
        if content_length:
            q_headers["CONTENT-LENGTH"] = content_length
        else:
            pass

        proto = "http"
        url = f"{proto}://{minio_ep}{path_and_query}"
        input = environ.get("wsgi.input")

        logger.debug(f"AHO url={url}")

        sniff = False

        if input and sniff:
            input = Read1Reader(input.reader, sniff=True, sniff_marker=">", use_read=True)
        else:
            pass

        req = Request(url, data=input, headers=q_headers, method=request_method)
        try:
            res = urlopen(req, timeout=self._forwarding_timeout)
            status = f"{res.status}"
            r_headers = res.getheaders()
            respiter = self._wrap_res(res, environ, r_headers, sniff=sniff, sniff_marker="<")

        except HTTPError as e:
            logger.error(f"urlopen error: url={url} for {request_method} {request_url}; exception={e}")
            ## logger.exception(e)
            status = f"{e.code}"
            r_headers = [(k, e.headers[k]) for k in e.headers]
            respiter = self._wrap_res(e, environ, r_headers, sniff=sniff, sniff_marker="<E")

        except URLError as e:
            logger.error(f"urlopen error: url={url} for {request_method} {request_url}; exception={e}")
            if _check_url_error_is_connection_errors(e):
                # "Connection refused" etc.
                logger.debug(f"CLEAR TABLE AND RETRY")
            else:
                pass
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
            initial_idle_duration = self.watch_interval + jitter + self.heartbeat_timeout
            ##atime_timeout = initial_idle_duration + self.refresh_margin
            ##atime = f"{int(time.time())}"
            ##self.tables.routing_table.set_atime_by_addr_(dest_addr, atime, atime_timeout)
            ##self.tables.routing_table.set_route_expiry(pool_id, atime_timeout)
        else:
            pass

        ##user_id = self._zone_to_user(pool_id)

        content_length_downstream = next((v for (k, v) in r_headers if k.lower() == "content-length"), None)

        log_access(status, *access_info,
                   upstream=content_length,
                   downstream=content_length_downstream)

        logger.debug(f"(MUX) DONE")
        start_response(status, r_headers)
        return respiter

    pass
