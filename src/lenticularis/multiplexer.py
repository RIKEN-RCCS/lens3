"""Multiplexer.  It is a reverse-proxy and forwards a request/response
from/to MinIO.  It is a Gunicorn app.

"""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import errno
import time
import random
import posixpath
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import urllib.parse
from lenticularis.scheduler import Scheduler
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import Bkt_Policy
from lenticularis.poolutil import check_bucket_naming
from lenticularis.poolutil import parse_s3_auth
from lenticularis.poolutil import access_mux
from lenticularis.poolutil import ensure_bucket_policy
from lenticularis.poolutil import ensure_user_is_authorized
from lenticularis.poolutil import ensure_mux_is_running
from lenticularis.poolutil import ensure_pool_state
from lenticularis.poolutil import ensure_pool_owner
from lenticularis.poolutil import ensure_bucket_owner
from lenticularis.poolutil import ensure_secret_owner
from lenticularis.utility import host_port
from lenticularis.utility import Read1Reader
from lenticularis.utility import get_ip_addresses
from lenticularis.utility import make_typical_ip_address
from lenticularis.utility import host_port
from lenticularis.utility import log_access
from lenticularis.utility import logger
from lenticularis.utility import tracing


_connection_errors = [errno.ETIMEDOUT, errno.ECONNREFUSED,
                      errno.EHOSTDOWN, errno.EHOSTUNREACH]


def _no_buffering(headers):
    ##AHO
    if any(True for (k, v) in headers if k.upper() == "X-ACCEL-BUFFERING" and v.upper() == "NO"):
        return True
    if any(True for (k, _) in headers if k.upper() == "CONTENT-LENGTH"):
        return False
    return True


def _fake_user_id(access_key):
    """Returns a substitute of a user-id for logging."""
    if access_key is None:
        return f"pubic-access-user"
    else:
        return f"user-with-{access_key}"
    pass


def _check_url_error_is_connection_errors(x):
    if x.errno in _connection_errors:
        return x.errno
    elif x.reason is not None and x.reason.errno in _connection_errors:
        return x.reason.errno
    else:
        logger.debug(f"Cannot find errno in URLError={x}")
        return 0


def _get_pool_of_probe_key(probe_key, access_info):
    """Checks a key is a probe-key, and returns a pool-id for which it is
    created."""
    if (probe_key is not None
        and probe_key.get("use") == "access_key"
        and probe_key.get("secret_key") == ""):
        return probe_key.get("owner")
    else:
        return None
    pass


def _pick_bucket_in_path(path, access_info):
    request_url = access_info[3]
    assert path.startswith("/")
    pathc = path.split("/")
    pathc.pop(0)
    bucket = pathc[0]
    # Check a bucket name.
    if bucket == "":
        log_access("404", *access_info)
        raise Api_Error(404, f"Bad URL, accessing the root: url={request_url}")
    if not check_bucket_naming(bucket):
        log_access("400", *access_info)
        raise Api_Error(400, f"Bad URL, bad bucket: url={request_url}")
    return bucket


class Multiplexer():
    """Mux.  It forwards requests to MinIO."""

    def __init__(self, mux_conf, tables, controller, host, port):
        self._verbose = False
        self._mux_host = host
        self._mux_port = int(port)
        self.tables = tables
        self._controller = controller
        self._bad_response_delay = 1
        self._start_time = int(time.time())
        ##gunicorn_conf = mux_conf["gunicorn"]
        ##lenticularis_conf = mux_conf["lenticularis"]

        mux_param = mux_conf["multiplexer"]
        self._facade_hostname = mux_param["facade_hostname"].lower()
        proxies = mux_param["trusted_proxies"]
        self._trusted_proxies = {addr for h in proxies
                                 for addr in get_ip_addresses(h)}
        self._forwarding_timeout = int(mux_param["forwarding_timeout"])
        timer = int(mux_param["mux_ep_update_interval"])
        self._periodic_work_interval = timer
        self._probe_access_timeout = int(mux_param["probe_access_timeout"])
        self._multiplexer_addrs = self._list_mux_ip_addresses()

        ctl_param = mux_conf["minio_manager"]
        self.heartbeat_interval = int(ctl_param["heartbeat_interval"])
        self.heartbeat_timeout = int(ctl_param["heartbeat_timeout"])
        self.scheduler = Scheduler(tables)
        return

    def __del__(self):
        ep = host_port(self._mux_host, self._mux_port)
        self.tables.process_table.delete_mux(ep)
        return

    def __call__(self, environ, start_response):
        # (MEMO: environ is a dict, and start_response is a method).
        try:
            return self._process_request(environ, start_response)
        except Api_Error as e:
            logger.error(f"Access in Mux (port={self._mux_port}) errs:"
                         f" exception=({e})",
                         exc_info=False)
            # Delay returning a response for a while.
            time.sleep(self._bad_response_delay)
            status = f"{e.code}"
            start_response(status, [])
            return []
        except Exception as e:
            logger.error(f"Unhandled exception in Mux (port={self._mux_port}):"
                         f" exception=({e})",
                         exc_info=True)
            pass
        start_response("500", [])
        return []

    def periodic_work(self):
        interval = self._periodic_work_interval
        logger.debug(f"Mux periodic_work started: interval={interval}.")
        assert self._periodic_work_interval >= 10
        time.sleep(10 * random.random())
        while True:
            try:
                self._register_mux()
            except Exception as e:
                logger.error(f"Mux periodic_work failed: exception={e}")
                pass
            jitter = ((interval * random.random()) / 8)
            time.sleep(interval + jitter)
            pass
        return

    def _list_mux_ip_addresses(self):
        muxs = self.tables.list_mux_eps()
        return {addr for (h, _) in muxs for addr in get_ip_addresses(h)}

    def _register_mux(self):
        if self._verbose:
            logger.debug(f"Updating Mux info (periodically).")
            pass
        now = int(time.time())
        mux_desc = {"host": self._mux_host, "port": self._mux_port,
                    "start_time": self._start_time,
                    "modification_time": now}
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
            (code, ep0) = self._controller.start_service(traceid, pool_id, probe_key)
            return (code, ep0)
        else:
            # Run MinIO on a remote host.
            assert probe_key is None
            pooldesc = self.tables.get_pool(pool_id)
            probe_key = pooldesc["probe_key"]
            facade_hostname = self._facade_hostname
            code = access_mux(traceid, ep, probe_key, facade_hostname,
                              self._probe_access_timeout)
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

        # server_name = environ.get("SERVER_NAME")
        # server_port = environ.get("SERVER_PORT")
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
        fake_user = _fake_user_id(access_key)

        ep = host_port(self._mux_host, self._mux_port)
        request_url = f"{request_proto}://{ep}{path_and_query}"
        u = urllib.parse.urlparse(request_url)
        path = posixpath.normpath(u.path)

        access_info = [client_addr, fake_user, request_method, request_url]
        failure_message = f"Bad URL, bad bucket: url={request_url}"

        logger.debug(f"Mux (port={self._mux_port}) got a request:"
                     f" {request_method} {request_url};"
                     f" remote=({client_addr}), auth=({authorization})")

        if not self._check_forwarding_host_trusted(peer_addr):
            logger.error(f"Untrusted proxy or unknonwn Mux: {peer_addr};"
                         f" Check configuration")
            log_access("403", *access_info)
            raise Api_Error(403, f"Bad access from remote={client_addr}")

        if path == "/":
            # Access to "/" is prohibited but for a probe-access from Adm.
            if access_key is None:
                log_access("401", *access_info)
                raise Api_Error(401, f"Bad access to the root path")
            probe_key = self.tables.get_id(access_key)
            pool_id = _get_pool_of_probe_key(probe_key, access_info)
            if pool_id is None:
                log_access("401", *access_info)
                raise Api_Error(401, f"Bad access to the root path")
            assert probe_key is not None
            logger.debug(f"Mux (port={self._mux_port}) probe-access"
                         f" for pool={pool_id}")
        else:
            try:
                probe_key = None
                bucket = _pick_bucket_in_path(path, access_info)
                desc = self.tables.get_bucket(bucket)
                if desc is None:
                    log_access("404", *access_info)
                    raise Api_Error(404, f"Bad URL, no bucket: {bucket}")
                pool_id = desc["pool"]
                pooldesc = self.tables.get_pool(pool_id)
                assert pooldesc is not None
                user_id = pooldesc.get("owner_uid")
                # ensure_mux_is_running(self.tables)
                ensure_user_is_authorized(self.tables, user_id)
                ensure_pool_state(self.tables, pool_id)
                # ensure_bucket_owner(self.tables, bucket, pool_id)
                ensure_secret_owner(self.tables, access_key, pool_id)
                ensure_bucket_policy(bucket, desc, access_key)
            except Api_Error as e:
                # Reraise an error with a less-informative message.
                logger.debug(f"Mux (port={self._mux_port}) access check"
                             f" failed: exception=({e})")
                log_access("401", *access_info)
                raise Api_Error(e.code, failure_message)
            logger.debug(f"Mux (port={self._mux_port}) access"
                         f" for bucket={path} for pool={pool_id}")
            pass

        assert pool_id is not None
        minio_ep = self.tables.get_minio_ep(pool_id)
        if minio_ep is None:
            (code, ep0) = self._start_service(traceid, pool_id, probe_key)
            if code == 200:
                assert ep0 is not None
                minio_ep = ep0
                pass
            pass

        # It is OK if an endpoint is found.  A check for an
        # enabled/disabled state of the pool is not checked here.

        if minio_ep is None:
            log_access("404", *access_info)
            raise Api_Error(404, failure_message)

        self.tables.set_access_timestamp(pool_id)

        if probe_key is not None:
            # A probe-access does not access MinIO.
            start_response("200", [])
            return []

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

        sniff = False

        if input and sniff:
            input = Read1Reader(input.reader, sniff=True, sniff_marker=">", use_read=True)
            pass

        req = Request(url, data=input, headers=q_headers,
                      method=request_method)
        failure_message = (f"urlopen failure: url={url}"
                           f" for {request_method} {request_url};")
        try:
            res = urlopen(req, timeout=self._forwarding_timeout)
            status = f"{res.status}"
            r_headers = res.getheaders()
            respiter = self._wrap_res(res, environ, r_headers, sniff=sniff, sniff_marker="<")

        except HTTPError as e:
            logger.error(failure_message + f" exception={e}")
            status = f"{e.code}"
            r_headers = [(k, e.headers[k]) for k in e.headers]
            respiter = self._wrap_res(e, environ, r_headers, sniff=sniff, sniff_marker="<E")

        except URLError as e:
            if _check_url_error_is_connection_errors(e):
                # "Connection refused" etc.
                logger.warning(failure_message + f" exception={e}")
            else:
                logger.error(failure_message + f" exception={e}")
                pass
            status = "503"
            r_headers = []
            respiter = []

        except Exception as e:
            logger.error(failure_message + f" exception={e}",
                         exc_info=True)
            status = "500"
            r_headers = []
            respiter = []

        if respiter != []:
            pass
        else:
            pass

        content_length_downstream = next((v for (k, v) in r_headers if k.lower() == "content-length"), None)

        log_access(status, *access_info,
                   upstream=content_length,
                   downstream=content_length_downstream)

        start_response(status, r_headers)
        return respiter

    pass
