"""A sentinel process for a MinIO process."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import math
import os
import platform
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
from subprocess import Popen, DEVNULL, PIPE, TimeoutExpired
import random
import select
import sys
import threading
import time
import contextlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from lenticularis.mc import Mc, assert_mc_success
from lenticularis.readconf import read_mux_conf
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables
from lenticularis.utility import ERROR_EXIT_READCONF, ERROR_EXIT_FORK, ERROR_EXIT_START_MINIO
from lenticularis.utility import decrypt_secret, list_diff3
from lenticularis.utility import gen_access_key_id, gen_secret_access_key
from lenticularis.utility import make_clean_env, host_port
from lenticularis.utility import uniform_distribution_jitter
from lenticularis.utility import wait_one_line_on_stdout
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


class Alarmed(Exception):
    pass


class Termination(Exception):
    pass


# Messages from a MinIO process at its start-up.

_minio_expected_response = b"API: "
_minio_error_response = b"ERROR"
_minio_response_port_in_use = b"Specified port is already in use"
_minio_response_unwritable_storage = b"Unable to write to the backend"
_minio_response_port_capability = b"Insufficient permissions to use specified port"


def _read_stream(s):
    """Reads a stream if some is available.  It returns a pair of the
    readout and the state of a stream.
    """
    outs = b""
    while (s in select.select([s], [], [], 0)[0]):
        r = s.read1()
        if r == b"":
            return (outs, True)
        outs += r
    return (outs, False)


class Manager():
    """A sentinel for a MinIO process.  It is started by a Controller as a
    daemon (and exits immediately), and it informs the caller about a
    successful start-up of a MinIO by placing a one line message on
    stdout.
    """

    def __init__(self):
        self._verbose = False
        self._alarm_section = None
        pass

    def _sigalrm(self, n, stackframe):
        logger.debug(f"@@@ raise Alarmed [{self._alarm_section}]")
        raise Alarmed(self._alarm_section)

    def _sigterm(self, n, stackframe):
        logger.debug("Manager got a sigterm.")
        signal(SIGTERM, SIG_IGN)
        raise Termination("Manager got a sigterm.")

    def _tell_controller_minio_starts(self):
        # Note that a closure of stdout is not detected at the reader side.
        sys.stdout.write(f"{self._minio_ep}\n")
        sys.stdout.flush()
        sys.stdout.close()
        sys.stderr.close()
        contextlib.redirect_stdout(None)
        contextlib.redirect_stderr(None)

    def _terminate_subprocess(self, p):
        logger.debug(f"AHO _terminate_subprocess unimplemented.")
        pass

    def _set_pool_state(self, state, reason):
        logger.debug(f"AHO _set_pool_state unimplemented.")
        self._set_current_mode(self._pool_id, state, reason)
        pass

    def _manager_main(self, pool_id, args, mux_conf):
        logger.info(f"Starting a Manager process for pool={pool_id}.")

        # Check the thread is main for using signals:
        assert threading.current_thread() == threading.main_thread()

        signal(SIGALRM, self._sigalrm)

        self._pool_id = pool_id
        self._mux_host = args.host
        self._mux_port = args.port
        self._mux_ep = host_port(self._mux_host, self._mux_port)
        port_min = int(args.port_min)
        port_max = int(args.port_max)

        minio_param = mux_conf["minio"]
        self._bin_minio = minio_param["minio"]
        self._bin_mc = minio_param["mc"]

        ctl_param = mux_conf["controller"]
        self._bin_sudo = ctl_param["sudo"]
        self._watch_interval = int(ctl_param["watch_interval"])
        self._heartbeat_tolerance = int(ctl_param["heartbeat_miss_tolerance"])
        self._expiry = self._heartbeat_tolerance * self._watch_interval
        self._lock_timeout = int(ctl_param["minio_startup_timeout"])

        ## NOTE: FIX VALUE of timeout_margin.
        self.timeout_margin = 2
        self.keepalive_limit = int(ctl_param["keepalive_limit"])
        self.minio_user_install_timelimit = int(ctl_param["minio_user_install_timelimit"])
        self._mc_info_timelimit = int(ctl_param["mc_info_timelimit"])
        self._mc_stop_timelimit = int(ctl_param["mc_stop_timelimit"])
        self.kill_supervisor_wait = int(ctl_param["kill_supervisor_wait"])
        self.refresh_margin = int(ctl_param["refresh_margin"])

        self.tables = get_tables(mux_conf)

        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            logger.error(f"Manager failed: no pool found for pool={pool_id}")
            return False

        # Register a manager entry and exclude others.

        now = int(time.time())
        manager = {
            "mux_host": self._mux_host,
            "mux_port": self._mux_port,
            "manager_pid": os.getpid(),
            "modification_date": now
        }
        self._minio_manager = manager
        (ok, holder) = self.tables.set_ex_minio_manager(pool_id, manager)
        if not ok:
            muxep = host_port(holder["host"], holder["port"])
            logger.info(f"Manager yields its work to another:"
                        f" pool={pool_id} to Mux={muxep}")
            return False
        ok = self.tables.set_minio_manager_expiry(pool_id, self._expiry)
        if not ok:
            logger.error(f"A Manager entry expires instantly:"
                         f" pool={pool_id} at Mux={self._mux_ep}")
            return False

        try:
            self._deregister_minio_process(clean_stale_entries=True)
            ok = self._manage_minio(port_min, port_max)
        finally:
            ma = self.tables.get_minio_manager(pool_id)
            if ma == self._minio_manager:
                self.tables.delete_minio_manager(pool_id)
            else:
                logger.error(f"Inconsistent mutex state of MinIO processes:"
                             f" pool={pool_id} at Mux={self._mux_ep}")
                pass
            pass
        return ok

    def _manage_minio(self, port_min, port_max):
        pooldesc = self.tables.get_pool(self._pool_id)
        if pooldesc is None:
            logger.error(f"Manager failed: pool deleted: pool={self._pool_id}")
            return False

        use_pool_id_for_minio_root_user = False
        if use_pool_id_for_minio_root_user:
            self._MINIO_ROOT_USER = self._pool_id
            self._MINIO_ROOT_PASSWORD = decrypt_secret(pooldesc["root_secret"])
        else:
            self._MINIO_ROOT_USER = gen_access_key_id()
            self._MINIO_ROOT_PASSWORD = gen_secret_access_key()
            pass

        env = make_clean_env(os.environ)
        self._env_minio = env
        self._env_mc = env.copy()
        self._env_minio["MINIO_ROOT_USER"] = self._MINIO_ROOT_USER
        self._env_minio["MINIO_ROOT_PASSWORD"] = self._MINIO_ROOT_PASSWORD
        self._env_minio["MINIO_BROWSER"] = "off"
        ##if self.minio_http_trace != "":
        ##    self._env_minio["MINIO_HTTP_TRACE"] = self.minio_http_trace
        ## self._env_minio["MINIO_CACHE_DRIVES"] = f"/tmp/{self._pool_id}"
        ## self._env_minio["MINIO_CACHE_EXCLUDE"] = ""
        ## self._env_minio["MINIO_CACHE_QUOTA"] = "80"
        ## self._env_minio["MINIO_CACHE_AFTER"] = "3"
        ## self._env_minio["MINIO_CACHE_WATERMARK_LOW"] = "70"
        ## self._env_minio["MINIO_CACHE_WATERMARK_HIGH"] = "90"

        now = int(time.time())
        mode = self.tables.storage_table.get_mode(self._pool_id)

        assert pooldesc is not None

        user = pooldesc["owner_uid"]
        group = pooldesc["owner_gid"]
        directory = pooldesc["buckets_directory"]

        unexpired = now < int(pooldesc["expiration_date"])
        permitted = pooldesc["permit_status"] == "allowed"
        online = pooldesc["online_status"] == "online"

        if not (unexpired and permitted and online):
            self._set_pool_state("disabled",
                                 f"Pool states:"
                                 f" expired={not unexpired},"
                                 f" permitted={permitted},"
                                 f" online={online}.")
            return False

        procdesc = self.tables.get_minio_proc(self._pool_id)
        assert procdesc is None
        assert mode == "initial" or mode == "ready"

        ports = list(range(port_min, port_max + 1))
        random.shuffle(ports)
        p = self._try_start_minio(ports, mode, user, group, directory)
        if p is None:
            return False
        ok = self._setup_and_watch_minio(p, pooldesc)
        return ok

    def _try_start_minio(self, ports, mode, user, group, directory):
        p = None
        for port in ports:
            address = f":{port}"
            cmd = [self._bin_sudo, "-u", user, "-g", group, self._bin_minio,
                   "server", "--anonymous", "--address", address, directory]
            logger.info(f"Starting MinIO: {cmd}")
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self._env_minio)
            try:
                (ok, error_is_nonfatal) = self._wait_for_minio_to_come_up(p)
                if ok:
                    host = self._mux_host
                    self._minio_ep = host_port(host, port)
                    return p
                elif error_is_nonfatal:
                    p = None
                    continue
                else:
                    self._minio_ep = None
                    return None
            except Exception as e:
                # (e is SubprocessError, OSError, ValueError, usually).
                logger.error(f"Starting MinIO failed with exception={e}",
                             exc_info=True)
                self._set_pool_state("inoperable", "MinIO does not start.")
                self._minio_ep = None
                return None
            pass
        assert p is None
        self._minio_ep = None
        return None

    def _wait_for_minio_to_come_up(self, p):
        """Checks a MinIO startup.  It assumes any subprocess outputs at least
        one line of a message or closes stdout.  Otherwise it may wait
        indefinitely.
        """

        # It expects that MinIO outputs the following lines at a
        # successful start (to stdout):
        # > "API: http://xx.xx.xx.xx:9000  http://127.0.0.1:9000"
        # > "RootUser: minioadmin"
        # > "RootPass: minioadmin"

        (outs, errs, closed) = wait_one_line_on_stdout(p, None)
        if outs.startswith(_minio_expected_response):
            logger.info(f"Message on MinIO outs=({outs}) errs=({errs})")
            return (True, False)
        else:
            # A closure of stdout is presumably an error.  Or,
            # terminate the process on an unexpected message.
            try:
                (o_, e_) = p.communicate(timeout=15)
            except TimeoutExpired:
                p.kill()
                (o_, e_) = p.communicate()
                pass
            p_status = p.wait()
            outs += o_
            errs += e_
            m0 = f"Starting MinIO failed with"
            m1 = (f" exit={p_status}" f" outs=({outs}) errs=({errs})")
            if outs.find(_minio_error_response) != -1:
                if outs.find(_minio_response_port_in_use) != -1:
                    reason = "port-in-use (transient)"
                    logger.debug(f"{m0} {reason}: {m1}")
                    return (False, True)
                elif outs.find(_minio_response_unwritable_storage) != -1:
                    reason = "storage unwritable"
                    self._set_pool_state("inoperable", reason)
                    logger.info(f"{m0} {reason}: {m1}")
                    return (False, False)
                else:
                    reason = "start failed"
                    self._set_pool_state("inoperable", reason)
                    logger.error(f"{m0} {reason}: {m1}")
                    return (False, False)
                pass
            else:
                reason = "start failed (no error)"
                self._set_pool_state("inoperable", reason)
                logger.error(f"{m0} {reason}: {m1}")
                return (False, False)
            pass
        pass

    def _setup_and_watch_minio(self, p, pooldesc):
        assert self._minio_ep is not None
        self._mc = Mc(self._bin_mc, self._env_mc, self._minio_ep,
                      self._pool_id)
        try:
            self._setup_minio(p, pooldesc)
        except Exception as e:
            self._stop_minio(p)
            raise
        else:
            jitter = 0
            duration0 = self._watch_interval + self._mc_info_timelimit
            timeo = duration0 + self.refresh_margin + jitter
            self._register_minio_process(p.pid, pooldesc, timeo)
        finally:
            self._tell_controller_minio_starts()
            pass

        self._set_current_mode(self._pool_id, "ready", None)

        try:
            self._watch_minio(p)
        finally:
            self._deregister_minio_process(clean_stale_entries=False)
            self._stop_minio(p)
            pass
        pass

    def _setup_minio(self, p, pooldesc):
        with self._mc.alias_set(self._MINIO_ROOT_USER,
                                self._MINIO_ROOT_PASSWORD):
            try:
                alarm(self.minio_user_install_timelimit)
                self._alarm_section = "setup_minio"
                self._mc.setup_minio(p, pooldesc)
                alarm(0)
                self._alarm_section = None
            except Alarmed as e:
                x = Exception("MinIO initialization failed (timeout)")
                self._set_current_mode(self._pool_id, "error", f"{x}")
                raise x
            except Exception as e:
                alarm(0)
                self._alarm_section = None
                self._set_current_mode(self._pool_id, "error", f"{e}")
                logger.error(f"MinIO initialization failed for"
                             f" pool={self._pool_id}: exception=({e})")
                logger.exception(e)
                raise
            pass
        pass

    def _watch_minio(self, p):
        """Watches a MinIO process.  MinIO usually outputs nothing on
           stdout/stderr, and this does a periodic work of
           heartbeating.
        """
        logger.debug(f"Manager for {self._minio_ep} starts watching.")

        signal(SIGTERM, self._sigterm)
        signal(SIGCHLD, SIG_IGN)

        try:
            jitter = 0
            duration0 = self._watch_interval + self._mc_info_timelimit
            duration1 = duration0 + self.refresh_margin + jitter
            ##self._refresh_table_status(duration1)
            lastcheck = 0
            while True:
                jitter = uniform_distribution_jitter()
                timeo = self._watch_interval + jitter
                (readable, _, _) = select.select(
                    [p.stdout, p.stderr], [], [], timeo)

                if p.stderr in readable:
                    (errs, closed) = _read_stream(p.stderr)
                    if errs != b"":
                        logger.info(f"Message on MinIO stderr=({errs})")
                        pass
                    pass
                if p.stdout in readable:
                    (outs, closed) = _read_stream(p.stdout)
                    if outs != b"":
                        logger.info(f"Message on MinIO stdout=({outs})")
                        pass
                    if closed:
                        raise Termination("MinIO closed stdout.")
                    pass

                now = int(time.time())
                if lastcheck + (self._watch_interval / 8) < now:
                    lastcheck = now
                    self._check_pool_status()
                    self._check_minio_health()
                    self._refresh_minio_ep()
                    pass

                duration3 = self._watch_interval + self._mc_info_timelimit
                duration4 = duration3 + self.refresh_margin + jitter
                ##self._refresh_table_status(duration4)
                pass

        except Termination as e:
            pass

        except Exception as e:
            logger.error(f"Manager failed: exception={e}")
            logger.exception(e)
            pass

        logger.debug(f"Manager for {self._minio_ep} exits.")
        pass

    def _register_minio_process(self, pid, pooldesc, timeout):
        now = int(time.time())
        self._minio_proc = {
            "minio_ep": self._minio_ep,
            "minio_pid": pid,
            "admin": self._MINIO_ROOT_USER,
            "password": self._MINIO_ROOT_PASSWORD,
            "mux_host": self._mux_host,
            "mux_port": self._mux_port,
            "manager_pid": os.getpid(),
            "modification_date": now
        }
        timeout = math.ceil(timeout)
        self.tables.set_minio_proc(self._pool_id, self._minio_proc, timeout)
        self.tables.set_route(self._pool_id, self._minio_ep)
        self._refresh_minio_ep()
        pass

    def _refresh_minio_ep(self):
        ok = self.tables.set_minio_manager_expiry(self._pool_id, self._expiry)
        ma = self.tables.get_minio_manager(self._pool_id)
        if ma != self._minio_manager:
            logger.error(f"Inconsistent mutex state of MinIO processes:"
                         f" pool={self._pool_id} at Mux={self._mux_ep}")
            raise Termination("Inconsistent mutex state")
        pass

    def _deregister_minio_process(self, *, clean_stale_entries):
        pool_id = self._pool_id
        try:
            mn = self.tables.get_minio_proc(pool_id)
            if not clean_stale_entries and mn != self._minio_proc:
                logger.error(f"Inconsistent mutex state of MinIO processes:"
                             f" pool={self._pool_id} at Mux={self._mux_ep}")
                pass
            elif clean_stale_entries and mn is not None:
                logger.info(f"A stale MinIO process entry:"
                            f" pool={pool_id} ep={mn['minio_ep']}")
                pass
            ep = self.tables.delete_route(pool_id)
            if not clean_stale_entries and ep != self._minio_ep:
                logger.error(f"Inconsistent mutex state of MinIO processes:"
                             f" pool={self._pool_id} at Mux={self._mux_ep}")
                pass
            elif clean_stale_entries and ep is not None:
                logger.info(f"A stale MinIO endpoint entry:"
                            f" pool={pool_id}, ep={ep}")
                pass
            self.tables.delete_minio_proc(pool_id)
            self.tables.delete_route(pool_id)
        except Exception as e:
            logger.exception(f"Exception in deleting Redis entries (ignored):"
                             f" exception={e}")
            pass
        pass

    def _stop_minio(self, p):
        with self._mc.alias_set(self._MINIO_ROOT_USER,
                                self._MINIO_ROOT_PASSWORD):
            try:
                alarm(self._mc_stop_timelimit)
                self._alarm_section = "stop_minio"
                (p_, r) = self._mc.admin_service_stop()
                assert p_ is None
                assert_mc_success(r, "mc.admin_service_stop")
                p_status = p.wait()
            except Alarmed as e:
                logger.error(f"Stopping MinIO timed out:"
                             f" exception ignored: exception=({e})")
            except Exception as e:
                logger.error(f"Stopping MinIO failed:"
                             f" exception ignored: exception=({e})")
                logger.exception(e)
            finally:
                alarm(0)
                self._alarm_section = None
                pass
            pass

    def _kill_manager_process(self, manager_pid):
        logger.debug("@@@ +++")
        os.kill(manager_pid, SIGTERM)
        for i in range(self.kill_supervisor_wait):
            a = self.tables.process_table.get_minio_proc(self._pool_id)
            if not a:
                break
            time.sleep(1)
            pass
        pass

    def _set_current_mode(self, pool_id, mode, reason):
        self.tables.storage_table.set_mode(pool_id, mode)
        pass

    def _check_pool_status(self):
        """Checks the status and shutdown the work when inappropriate.  Some
	logging output is done at deregistering.
        """
        now = int(time.time())
        # Check the status of a pool.
        pooldesc = self.tables.storage_table.get_pool(self._pool_id)
        if pooldesc is None:
            raise Termination("Pool removed")
        ##AHO
        if now >= int(pooldesc["expiration_date"]):
            raise Termination("Pool expired")
        if pooldesc["permit_status"] != "allowed":
            raise Termination("Pool disabled")
        if pooldesc["online_status"] != "online":
            raise Termination("Pool offline")
        # Check the status of a process.
        procdesc = self.tables.get_minio_proc(self._pool_id)
        if procdesc != self._minio_proc:
            raise Termination("MinIO process overtaken")
        pass

    def _check_minio_health(self):
        status = self._heartbeat_minio()
        if (status == 200):
            self._heartbeat_misses = 0
        else:
            self._heartbeat_misses += 1
            pass
        if self._heartbeat_misses > self._heartbeat_tolerance:
            logger.info(f"MinIO heartbeat failed: pool={self._pool_id},"
                        f" miss={self._heartbeat_misses}")
            raise Termination("MinIO heartbeat failure")
        pass

    def _heartbeat_minio(self):
        url = f"http://{self._minio_ep}/minio/health/live"
        try:
            res = urlopen(url, timeout=self._mc_info_timelimit)
            if self._verbose:
                logger.debug(f"Heartbeat MinIO OK: url={url}")
                pass
            return res.status
        except HTTPError as e:
            logger.error(f"Heartbeat MinIO failed, urlopen error:"
                         f" url=({url}); exception={e}")
            return e.code
        except URLError as e:
            logger.error(f"Heartbeat MinIO failed, urlopen error:"
                         f" url=({url}); exception={e}")
            return 503
        except Exception as e:
            logger.error(f"Heartbeat MinIO failed, urlopen error:"
                         f" url=({url}); exception={e}")
            logger.exception(e)
            return 500
        pass

    def _heartbeat_minio_via_mc_(self):
        # NOT USED.
        # Use of the following method is recommended by MinIO:
        # curl -I https://minio.example.net:9000/minio/health/live
        if self._verbose:
            logger.debug("Check MinIO is alive pool={self._pool_id}.")
            pass
        r = None
        try:
            alarm(self._mc_info_timelimit)
            self._alarm_section = "check_minio_info"
            (p_, r) = self._mc.admin_info()
            assert p_ is None
            assert_mc_success(r, "mc.admin_info")
            alarm(0)
            self._alarm_section = None
        except Alarmed:
            raise Exception("health check timeout")
        except Exception as e:
            logger.exception(e)
            alarm(0)
            self._alarm_section = None
            raise
        return r

    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("port")
    parser.add_argument("port_min")
    parser.add_argument("port_max")
    parser.add_argument("--configfile")
    parser.add_argument("--useTrueAccount", type=bool, default=False)
    ##action=argparse.BooleanOptionalAction  -- was introduced in Python3.9
    parser.add_argument("--accessByZoneID", type=bool, default=False)
    ##action=argparse.BooleanOptionalAction  -- was introduced in Python3.9
    parser.add_argument("--traceid")
    args = parser.parse_args()

    pool_id = os.environ.get("LENTICULARIS_POOL_ID")

    try:
        (mux_conf, configfile) = read_mux_conf(args.configfile)
    except Exception as e:
        sys.stderr.write(f"manager:main: {e}\n")
        sys.exit(ERROR_EXIT_READCONF)
        pass

    tracing.set(args.traceid)
    openlog(mux_conf["log_file"],
            **mux_conf["log_syslog"])

    try:
        pid = os.fork()
        if pid != 0:
            # (parent).
            sys.exit(0)
    except OSError as e:
        logger.error(f"fork failed: {os.strerror(e.errno)}")
        sys.exit(ERROR_EXIT_FORK)
        pass

    # (A Manager be a session leader).

    try:
        os.setsid()
    except OSError as e:
        logger.error(f"setsid failed (ignored): {os.strerror(e.errno)}")
        pass

    try:
        os.umask(0o077)
    except OSError as e:
        logger.error(f"set umask failed (ignored): {os.strerror(e.errno)}")
        pass

    manager = Manager()
    ok = False
    try:
        ok = manager._manager_main(pool_id, args, mux_conf)
    except Exception as e:
        logger.error(f"A Manager for pool={pool_id} failed:"
                     f" exception={e}",
                     exc_info=True)
        pass

    sys.exit(0)
    pass


if __name__ == "__main__":
    main()
