"""Lens3-Mux implementation.  It is a reverse-proxy and forwards a
request/response from/to MinIO.  It is a Gunicorn app.
"""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import errno
import time
import random
import posixpath
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import urllib.parse
from lenticularis.pooldata import Api_Error
from lenticularis.pooldata import Bkt_Policy
from lenticularis.pooldata import check_bucket_naming
from lenticularis.pooldata import parse_s3_auth
from lenticularis.pooldata import access_mux
from lenticularis.pooldata import ensure_bucket_policy
from lenticularis.pooldata import ensure_user_is_authorized
from lenticularis.pooldata import ensure_mux_is_running
from lenticularis.pooldata import ensure_pool_state
from lenticularis.pooldata import ensure_secret_owner
from lenticularis.pooldata import get_manager_name_for_messages
from lenticularis.pooldata import tally_manager_expiry
from lenticularis.utility import host_port
from lenticularis.utility import Read1Reader
from lenticularis.utility import get_ip_addresses
from lenticularis.utility import make_typical_ip_address
from lenticularis.utility import host_port
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import log_access
from lenticularis.utility import logger
from lenticularis.utility import tracing


# MinIO returns ECONNRESET at a high load (not too high).

_connection_errors = [errno.ETIMEDOUT, errno.ECONNREFUSED,
                      errno.EHOSTDOWN, errno.EHOSTUNREACH,
                      errno.ECONNRESET]


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
    """Checks if a URLError is connection related, then it is logged as a
    warning, otherwise it is an error.
    """
    if x.errno in _connection_errors:
        return True
    elif x.reason is not None and x.reason.errno in _connection_errors:
        return True
    else:
        logger.debug(f"Unfamiliar error is returned URLError={x}")
        return False


def _get_pool_of_probe_key(keydesc, access_synopsis):
    """Checks a keydesc is a probe-key and returns a pool-id for which it
    is created.
    """
    if (keydesc is not None
        and keydesc.get("secret_key") == ""):
        return keydesc.get("owner")
    else:
        return None
    pass


def _pick_bucket_in_path(path, access_synopsis):
    request_url = access_synopsis[3]
    assert path.startswith("/")
    pathc = path.split("/")
    pathc.pop(0)
    bucket = pathc[0]
    # Check a bucket name.
    if bucket == "":
        log_access("404", *access_synopsis)
        raise Api_Error(404, f"Bad URL, accessing the root: url={request_url}")
    if not check_bucket_naming(bucket):
        log_access("400", *access_synopsis)
        raise Api_Error(400, f"Bad URL, bad bucket: url={request_url}")
    return bucket


class Multiplexer():
    """Mux.  It forwards requests to MinIO."""

    def __init__(self, mux_conf, tables, spawner, host, port):
        self._verbose = False
        self._mux_conf = mux_conf
        self.tables = tables
        self._spawner = spawner
        self._mux_host = host
        self._mux_port = int(port)
        self._start_time = int(time.time())

        assert mux_conf["version"] == "v1.2"
        self._mux_version = "v1.2"

        mux_param = mux_conf["multiplexer"]
        self._front_host = mux_param["front_host"].lower()
        self._front_host_ip = get_ip_addresses(self._front_host)[0]
        proxies = mux_param["trusted_proxies"]
        self._trusted_proxies = {addr for h in proxies
                                 for addr in get_ip_addresses(h)}
        timer = int(mux_param["mux_ep_update_interval"])
        self._periodic_work_interval = timer
        self._mux_expiry = 3 * timer

        self._forwarding_timeout = int(mux_param["forwarding_timeout"])
        self._probe_access_timeout = int(mux_param["probe_access_timeout"])
        self._bad_response_delay = int(mux_param["bad_response_delay"])

        ctl_param = mux_conf["minio_manager"]
        self._minio_start_timeout = int(ctl_param["minio_start_timeout"])
        self._minio_setup_timeout = int(ctl_param["minio_setup_timeout"])
        self._service_starts_check_interval = 0.1

        self._heartbeat_interval = int(ctl_param["heartbeat_interval"])
        self._heartbeat_tolerance = int(ctl_param["heartbeat_miss_tolerance"])
        self._heartbeat_timeout = int(ctl_param["heartbeat_timeout"])
        self._manager_expiry = tally_manager_expiry(self._heartbeat_tolerance,
                                                    self._heartbeat_interval,
                                                    self._heartbeat_timeout)

        self._mux_addrs = self._list_mux_ip_addresses()
        # self.scheduler = Scheduler(tables)
        pass

    def __del__(self):
        ep = host_port(self._mux_host, self._mux_port)
        self.tables.delete_mux(ep)
        pass

    def __call__(self, environ, start_response):
        # (MEMO: environ is a dict, and start_response is a method).
        try:
            return self._process_request(environ, start_response)
        except Api_Error as e:
            logger.error(f"Access in Mux (port={self._mux_port}) errs:"
                         f" exception=({e})",
                         exc_info=self._verbose)
            # Delay returning a response for a while.
            time.sleep(self._bad_response_delay)
            status = f"{e.code}"
            start_response(status, [])
            return []
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Unhandled exception in Mux (port={self._mux_port}):"
                         f" exception=({m})",
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
                m = rephrase_exception_message(e)
                logger.error(f"Mux periodic_work failed: exception=({m})")
                pass
            jitter = ((interval * random.random()) / 8)
            time.sleep(interval + jitter)
            pass
        pass

    def _list_mux_ip_addresses(self):
        muxs = self.tables.list_mux_eps()
        return {addr for (h, _) in muxs for addr in get_ip_addresses(h)}

    def _register_mux(self):
        if self._verbose:
            logger.debug(f"Updating Mux info (periodically).")
            pass
        ep = host_port(self._mux_host, self._mux_port)
        ok = self.tables.set_mux_expiry(ep, self._mux_expiry)
        if ok:
            return
        now = int(time.time())
        mux_desc = {"host": self._mux_host, "port": self._mux_port,
                    "start_time": self._start_time,
                    "modification_time": now}
        self.tables.set_mux(ep, mux_desc)
        self.tables.set_mux_expiry(ep, self._mux_expiry)
        pass

    # def _wrap_res(self, res, environ, headers, sniff=False, sniff_marker=""):
    #     if _no_buffering(headers) or sniff:
    #         return Read1Reader(res, sniff=sniff)
    #     else:
    #         file_wrapper = environ["wsgi.file_wrapper"]
    #         return file_wrapper(res)
    #     pass

    def _response_output(self, res, environ):
        """Returns an iterator of a response body."""
        # The file wrapper can be "wsgiref.util.FileWrapper" or
        # "gunicorn.http.wsgi.FileWrapper".
        file_wrapper = environ["wsgi.file_wrapper"]
        return file_wrapper(res)

    # def _request_input(self, environ):
    #     rinput = environ.get("wsgi.input")
    #     if rinput and sniff:
    #         rinput = Read1Reader(rinput.reader)
    #         pass
    #     return rinput

    def _request_input(self, environ):
        """Returns a stream of a request body."""
        rinput = environ.get("wsgi.input")
        return rinput

    def _check_forwarding_host_trusted(self, peer_addr):
        if peer_addr is None:
            return False
        ip = make_typical_ip_address(peer_addr)
        if (ip in self._trusted_proxies or ip in self._mux_addrs):
            return True
        self._mux_addrs = self._list_mux_ip_addresses()
        if ip in self._mux_addrs:
            return True
        return False

    def _start_service(self, pool_id, probing):
        """Runs a MinIO service.  It returns 200 and an endpoint, or 500 when
        starting a service fails.  It waits until a service to start
        when multiple accesses happen simultaneously.  That is,
        starting a service has a race when multiple accesses come here
        at the same time.  And then, it excludes others by registering
        a manager entry.  When probing=True, it forces to run a
        service on the local host.  Otherwise, the chooser chooses a
        host to run.
        """
        # CURRENTLY, IT STARTS A SERVICE ON A LOCAL HOST.

        now = int(time.time())
        ma = {
            "mux_host": self._mux_host,
            "mux_port": self._mux_port,
            "start_time": now
        }
        self._minio_manager = ma
        (ok, _) = self.tables.set_ex_manager(pool_id, ma)
        if not ok:
            (code, ep0) = self._wait_for_service_starts(pool_id)
            return (code, ep0)

        # This request takes the role to start a manager.

        ok = self.tables.set_manager_expiry(pool_id, self._manager_expiry)
        if not ok:
            logger.warning(f"Manager (pool={pool_id}) failed to set expiry.")
            pass

        pooldesc = self.tables.get_pool(pool_id)
        user_id = pooldesc.get("owner_uid")
        self.tables.set_user_timestamp(user_id)

        if probing:
            ep = None
        else:
            # ep = self._choose_server_host(pool_id)
            ep = None
            pass

        if ep is None:
            # Run MinIO on a local host.
            (code, ep0) = self._spawner.start_spawner(pool_id)
            return (code, ep0)
        else:
            # THIS PART IS NOT USED NOW.
            # Run MinIO on a remote host.
            assert probing == False
            pooldesc = self.tables.get_pool(pool_id)
            probe_key = pooldesc["probe_key"]
            code = access_mux(ep, probe_key,
                              self._front_host, self._front_host_ip,
                              self._probe_access_timeout)
            return (code, ep)
        pass

    def _wait_for_service_starts(self, pool_id):
        logger.debug(f"Mux (port={self._mux_port}) waits for service starts.")
        limit = (int(time.time()) + self._minio_start_timeout
                 + self._minio_setup_timeout)
        while int(time.time()) < limit:
            ep = self.tables.get_minio_ep(pool_id)
            if ep is not None:
                logger.debug(f"Mux (port={self._mux_port})"
                             f" got service started.")
                return (200, ep)
            time.sleep(self._service_starts_check_interval)
            pass
        logger.warning(f"Mux (port={self._mux_port})"
                       f" failed in waiting for service starts.")
        return (500, None)

    def _choose_server_host__(self, pool_id):
        """Chooses a host to run a MinIO.  It returns None to mean the
        localhost.
        """
        # THIS IS NOT USED NOW.
        # (host, port) = self.scheduler.schedule(pool_id)
        (host, port) = (None, None)
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
        request_proto = environ.get("HTTP_X_FORWARDED_PROTO")
        # ?request_proto = request_proto if request_proto else "?"
        request_method = environ.get("REQUEST_METHOD")
        path_and_query = environ.get("RAW_URI")
        peer_addr = environ.get("REMOTE_ADDR")
        client_addr = environ.get("HTTP_X_REAL_IP")
        # ?client_addr = x_real_ip if x_real_ip else peer_addr
        # x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        # x_forwarded_host = environ.get("HTTP_X_FORWARDED_HOST")
        host_ = environ.get("HTTP_HOST") or "-"

        assert request_proto is not None
        assert request_method is not None
        assert path_and_query is not None
        assert peer_addr is not None
        assert client_addr is not None

        authorization = environ.get("HTTP_AUTHORIZATION")
        access_key = parse_s3_auth(authorization)
        fake_user = _fake_user_id(access_key)

        ep = host_port(self._mux_host, self._mux_port)
        request_url = f"{request_proto}://{ep}{path_and_query}"
        u = urllib.parse.urlparse(request_url)
        path = posixpath.normpath(u.path)

        access_synopsis = [client_addr, fake_user, request_method, request_url]
        failure_message = f"Bad URL, bad bucket: url={request_url}"

        logger.debug(f"Mux (port={self._mux_port}) got a request:"
                     f" {request_method} {request_url};"
                     f" remote=({client_addr}), auth=({authorization})")

        if not self._check_forwarding_host_trusted(peer_addr):
            logger.error(f"Untrusted proxy or unknonwn Mux: {peer_addr};"
                         f" Check configuration")
            log_access("403", *access_synopsis)
            raise Api_Error(403, f"Bad access from remote={client_addr}")

        if path == "/":
            # Access to "/" is prohibited but for a probe-access from Api.
            if access_key is None:
                log_access("401", *access_synopsis)
                raise Api_Error(401, "Bad access to /: (no access-key)")
            probe_key = self.tables.get_xid("akey", access_key)
            pool_id = _get_pool_of_probe_key(probe_key, access_synopsis)
            if pool_id is None:
                log_access("401", *access_synopsis)
                raise Api_Error(401, "Bad access to /: (not a probe-key)")
            assert probe_key is not None
            if self._verbose:
                logger.debug(f"Mux (port={self._mux_port}) probe-access"
                             f" for pool={pool_id}")
                pass
        else:
            try:
                probe_key = None
                bucket = _pick_bucket_in_path(path, access_synopsis)
                bucketdesc = self.tables.get_bucket(bucket)
                if bucketdesc is None:
                    log_access("404", *access_synopsis)
                    raise Api_Error(404, f"Bad URL, no bucket: {bucket}")
                pool_id = bucketdesc["pool"]
                pooldesc = self.tables.get_pool(pool_id)
                assert pooldesc is not None
                user_id = pooldesc.get("owner_uid")
                ensure_user_is_authorized(self.tables, user_id)
                ensure_pool_state(self.tables, pool_id)
                ensure_secret_owner(self.tables, access_key, pool_id)
                ensure_bucket_policy(bucket, bucketdesc, access_key)
            except Api_Error as e:
                # Reraise an error with a less-informative message.
                logger.debug(f"Mux (port={self._mux_port}) access check"
                             f" failed: exception=({e})")
                log_access("401", *access_synopsis)
                raise Api_Error(e.code, failure_message)
            if self._verbose:
                logger.debug(f"Mux (port={self._mux_port}) access"
                             f" for bucket={path} for pool={pool_id}")
                pass
            pass

        # Set a timestamp here, as early as possible, not to stop the
        # service during processing a request.

        assert pool_id is not None
        self.tables.set_access_timestamp(pool_id)

        minio_ep = self.tables.get_minio_ep(pool_id)
        if minio_ep is None:
            (code, ep0) = self._start_service(pool_id, True)
            if code == 200:
                assert ep0 is not None
                minio_ep = ep0
            else:
                assert code == 500
                log_access("404", *access_synopsis)
                raise Api_Error(404, failure_message)
                pass
            pass

        # It is OK if an endpoint is found.  A check for an
        # enabled/disabled state of the pool is not checked here.

        assert minio_ep is not None
        # log_access("404", *access_synopsis)
        # raise Api_Error(404, failure_message)

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
            pass
        content_length = environ.get("CONTENT_LENGTH")
        if content_length:
            q_headers["CONTENT-LENGTH"] = content_length
            pass

        url = f"http://{minio_ep}{path_and_query}"

        rinput = self._request_input(environ)

        req = Request(url, data=rinput, headers=q_headers,
                      method=request_method)
        failure_message = (f"urlopen failure: url={url}"
                           f" for {request_method} {request_url};")
        try:
            res = urlopen(req, timeout=self._forwarding_timeout)
            status = f"{res.status}"
            r_headers = res.getheaders()
            response = self._response_output(res, environ)
        except HTTPError as e:
            logger.error(failure_message + f" exception=({e})")
            status = f"{e.code}"
            r_headers = [(k, e.headers[k]) for k in e.headers]
            response = self._response_output(e, environ)
        except URLError as e:
            if _check_url_error_is_connection_errors(e):
                # "Connection refused" etc.
                logger.warning(failure_message + f" exception=({e})")
            else:
                logger.error(failure_message + f" exception=({e})")
                pass
            status = "503"
            r_headers = []
            response = []
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(failure_message + f" exception=({m})",
                         exc_info=True)
            status = "500"
            r_headers = []
            response = []
            pass

        content_length_downstream = next((v for (k, v) in r_headers if k.lower() == "content-length"), None)

        log_access(status, *access_synopsis,
                   upstream=content_length,
                   downstream=content_length_downstream)

        start_response(status, r_headers)
        return response

    pass
