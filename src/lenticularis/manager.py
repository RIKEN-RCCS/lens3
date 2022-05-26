"""A sentinel process for a MinIO process."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import math
import os
import platform
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
from subprocess import Popen, DEVNULL, PIPE
import random
import select
import sys
import tempfile
import threading
import time
import contextlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from lenticularis.mc import Mc, map_admin_user_json_keys, assert_mc_success
from lenticularis.readconf import read_mux_conf
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables
from lenticularis.utility import ERROR_READCONF, ERROR_FORK, ERROR_START_MINIO
from lenticularis.utility import decrypt_secret, list_diff3
from lenticularis.utility import gen_access_key_id, gen_secret_access_key
from lenticularis.utility import make_clean_env, host_port
from lenticularis.utility import remove_trailing_shash, uniform_distribution_jitter
from lenticularis.utility import wait_one_line_on_stdout
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


class AlarmException(Exception):
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
        return

    def _sigalrm(self, n, stackframe):
        logger.debug(f"@@@ raise AlarmException [{self._alarm_section}]")
        raise AlarmException(self._alarm_section)

    def _sigterm(self, n, stackframe):
        logger.debug("Manager got a sigterm.")
        signal(SIGTERM, SIG_IGN)
        raise Termination("Manager got a sigterm.")

    def _tell_controller_minio_starts(self):
        # Note that a closure of stdout is not detected by the reader-side.
        sys.stdout.write(f"{self._minio_ep}\n")
        sys.stdout.flush()
        sys.stdout.close()
        sys.stderr.close()
        contextlib.redirect_stdout(None)
        contextlib.redirect_stderr(None)

    def _finish_subprocess(self, p):
        logger.debug(f"AHO _finish_subprocess unimplemented.")
        return

    def _set_pool_state(self, state, reason):
        logger.debug(f"AHO _set_pool_state unimplemented.")
        self._set_current_mode(self._pool_id, state, reason)
        return

    def _manager_main(self, pool_id, args, mux_conf):

        # Check the thread is main for using signals:
        assert threading.current_thread() == threading.main_thread()

        signal(SIGALRM, self._sigalrm)

        self._pool_id = pool_id
        ##use_pool_id_for_minio_root_user = args.useTrueAccount
        use_pool_id_for_minio_root_user = False
        self._mux_host = args.host
        self._mux_port = args.port
        port_min = int(args.port_min)
        port_max = int(args.port_max)
        self._mux_ep = args.host

        minio_param = mux_conf["minio"]
        self._bin_minio = minio_param["minio"]
        self._bin_mc = minio_param["mc"]

        controller_param = mux_conf["controller"]
        self.sudo = controller_param["sudo"]
        self._watch_interval = int(controller_param["watch_interval"])
        self._lock_timeout = int(controller_param["minio_startup_timeout"])
        ## NOTE: FIX VALUE of timeout_margin.
        self.timeout_margin = 2
        self.keepalive_limit = int(controller_param["keepalive_limit"])
        self.heartbeat_miss_tolerance = int(controller_param["heartbeat_miss_tolerance"])

        self.minio_user_install_timelimit = int(controller_param["minio_user_install_timelimit"])
        self._mc_info_timelimit = int(controller_param["mc_info_timelimit"])
        self._mc_stop_timelimit = int(controller_param["mc_stop_timelimit"])
        self.kill_supervisor_wait = int(controller_param["kill_supervisor_wait"])
        self.refresh_margin = int(controller_param["refresh_margin"])

        self.tables = get_tables(mux_conf)

        pooldesc = self.tables.storage_table.get_pool(pool_id)
        if pooldesc is None:
            logger.error(f"Manager failed: no pool found for pool={pool_id}")
            return False

        env = make_clean_env(os.environ)
        self._env_minio = env
        self._env_mc = env.copy()

        if use_pool_id_for_minio_root_user:
            self._MINIO_ROOT_USER = self._pool_id
            self._MINIO_ROOT_PASSWORD = decrypt_secret(pooldesc["root_secret"])
        else:
            self._MINIO_ROOT_USER = gen_access_key_id()
            self._MINIO_ROOT_PASSWORD = gen_secret_access_key()

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

        self.lock = LockDB(self.tables.process_table, "Man")
        lockprefix = self.tables.process_table.process_table_lock_prefix
        key = f"{lockprefix}{self._pool_id}"
        ok = False
        while True:
            self._lock_start = int(time.time())
            locked = self.lock.trylock(key, self._lock_timeout)
            if not locked:
                ## NOTE: FIX VALUE.
                delay = 0.2
                self.lock.wait_for_lock(key, delay)
                continue
            else:
                break
        try:
            ok = self._manage_minio(port_min, port_max)
        finally:
            if self.lock.key is not None:
                self.lock.unlock()
        return ok

    def _manage_minio(self, port_min, port_max):
        now = int(time.time())
        pooldesc = self.tables.storage_table.get_pool(self._pool_id)
        mode = self.tables.storage_table.get_mode(self._pool_id)

        assert pooldesc is not None

        user = pooldesc["owner_uid"]
        group = pooldesc["owner_gid"]
        directory = pooldesc["buckets_directory"]

        self._expiration_date = int(pooldesc["expiration_date"])
        unexpired = now < self._expiration_date
        permitted = pooldesc["permit_status"] == "allowed"
        online = pooldesc["online_status"] == "online"

        if not (unexpired and permitted and online):
            self._set_pool_state("disabled",
                                 f"Pool states:"
                                 f" expired={not unexpired},"
                                 f" permitted={permitted},"
                                 f" online={online}.")
            return False

        access_by_zoneID = False
        setup_only = (mode != "ready" or access_by_zoneID == True)
        logger.debug(f"@@@ setup_only = {setup_only}")

        need_initialize = (mode == "initial")
        logger.debug(f"@@@ need_initialize = {need_initialize}")

        procdesc = self.tables.process_table.get_minio_proc(self._pool_id)
        logger.debug(f"@@@ procdesc = {procdesc}")
        if procdesc:
            # Someone else has started MinIO in race.
            self._handle_existing_minio(setup_only, need_initialize)
            return

        if (setup_only and not need_initialize):
            return

        assert mode == "initial" or mode == "ready"

        ports = list(range(port_min, port_max + 1))
        random.shuffle(ports)
        p = self._try_start_minio(ports, mode, user, group,
                                  directory, setup_only, need_initialize)
        if p is None:
            return False

        ok = self._setup_and_watch_minio(p, pooldesc, setup_only, need_initialize)

        return ok

    def _try_start_minio(self, ports, mode, user, group,
                         directory, setup_only, need_initialize):
        p = None
        for port in ports:
            address = f":{port}"
            cmd = [self.sudo, "-u", user, "-g", group, self._bin_minio,
                   "server", "--anonymous", "--address", address, directory]
            logger.info(f"Starting minio with: {cmd}")
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
                logger.error(f"Starting minio failed with exception={e}")
                self._set_pool_state("inoperable", "MinIO does not start.")
                self._minio_ep = None
                return None
            pass
        assert p is None
        self._minio_ep = None
        return None

    def _wait_for_minio_to_come_up(self, p):
        """Checks a minio startup.  It assumes any subprocess outputs at least
        one line of a message or closes stdout.  Otherwise it may wait
        indefinitely.
        """

        # It expects that minio outputs the following lines at a
        # successful start (to stdout):
        # > "API: http://xx.xx.xx.xx:9000  http://127.0.0.1:9000"
        # > "RootUser: minioadmin"
        # > "RootPass: minioadmin"

        outs = b""
        while True:
            (outs, errs, closed) = wait_one_line_on_stdout(p, None)
            if closed:
                # A closure is presumably an error.
                self._finish_subprocess(p)
                p_status = p.wait()
                (e_, _) = _read_stream(p.stderr)
                errs += e_
                if outs.find(_minio_error_response) != -1:
                    if outs.find(_minio_response_port_in_use) != -1:
                        logger.debug(f"Starting minio failed with"
                                     f" wait-status={p_status}"
                                     f" outs=({outs}) errs=({errs})")
                        return (False, True)
                    elif outs.find(_minio_response_unwritable_storage) != -1:
                        reason = "Storage is unwritable."
                        self._set_pool_state("inoperable",
                                             "Storage is unwritable.")
                        logger.info(f"Starting minio failed with"
                                    f" wait-status={p_status}"
                                    f" outs=({outs}) errs=({errs})")
                        return (False, False)
                    else:
                        self._set_pool_state("inoperable",
                                             "MinIO failed with an error.")
                        logger.error(f"Starting minio failed with"
                                     f" wait-status={p_status}"
                                     f" outs=({outs}) errs=({errs})")
                        return (False, False)
                else:
                    self._set_pool_state("inoperable",
                                         "MinIO process failed.")
                    logger.error(f"Starting minio failed with"
                                 f" wait-status={p_status}"
                                 f" outs=({outs}) errs=({errs})")
                    return (False, False)
            if outs.startswith(_minio_expected_response):
                logger.info(f"Message on MinIO outs=({outs}) errs=({errs})")
                return (True, False)
            pass
        pass

    def _setup_and_watch_minio(self, p, pooldesc,
                               setup_only, need_initialize):
        assert self._minio_ep is not None
        self._mc = Mc(self._bin_mc, self._env_mc, self._minio_ep,
                      self._pool_id)
        try:
            if need_initialize:
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
            self.lock.unlock()
            pass

        try:
            self._check_elapsed_time()
            self._watch_minio(p)
        finally:
            self._deregister_minio_process()
            self._stop_minio(p)
            pass
        pass

    def _setup_minio(self, p, pooldesc):
        with self._mc.alias_set(self._MINIO_ROOT_USER,
                                self._MINIO_ROOT_PASSWORD):
            try:
                alarm(self.minio_user_install_timelimit)
                self._alarm_section = "initialize_minio"
                self._mc.setup_minio(p, pooldesc)
                self._set_current_mode(self._pool_id, "ready", None)
                alarm(0)
                self._alarm_section = None
            except AlarmException as e:
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
        logger.debug(f"Manager for {self._minio_ep} starts watching.")

        signal(SIGTERM, self._sigterm)
        signal(SIGCHLD, SIG_IGN)

        try:
            jitter = 0
            duration0 = self._watch_interval + self._mc_info_timelimit
            duration1 = duration0 + self.refresh_margin + jitter
            self._refresh_table_status(duration1)
            down_count = 0
            while True:
                timeo = self._watch_interval + jitter
                (readable, _, _) = select.select(
                    [p.stdout, p.stderr], [], [], timeo)
                now = int(time.time())

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

                self._check_table_status_and_expiration(now)
                if readable == []:
                    self._check_minio_health()
                    pass

                jitter = uniform_distribution_jitter()
                duration3 = self._watch_interval + self._mc_info_timelimit
                duration4 = duration3 + self.refresh_margin + jitter
                self._refresh_table_status(duration4)
                pass

        except Termination as e:
            pass

        except Exception as e:
            logger.error(f"Manager failed: exception={e}")
            logger.exception(e)
            pass

        logger.debug(f"Manager for {self._minio_ep} exits.")
        return

    def _register_minio_process(self, pid, pooldesc, timeout):
        self._minio_proc = {
            "minio_ep": self._minio_ep,
            "minio_pid": f"{pid}",
            "admin": self._MINIO_ROOT_USER,
            "password": self._MINIO_ROOT_PASSWORD,
            "mux_host": self._mux_host,
            "mux_port": self._mux_port,
            "manager_pid": f"{os.getpid()}",
        }

        ##self.route = zone_to_route(pooldesc)
        ##logger.debug(f"@ minioAddress: {self._minio_proc}")
        ##logger.debug(f"@ self.route: {self.route}")
        ##logger.debug(f"@ timeout: {timeout}")

        timeout = math.ceil(timeout)
        atime = f"{int(time.time())}"
        self.tables.routing_table.set_route_expiry(self._pool_id, timeout)
        self.tables.storage_table.set_atime(self._pool_id, atime)
        self.saved_atime = atime

        self.tables.process_table.set_minio_proc(self._pool_id, self._minio_proc, timeout)
        self.tables.routing_table.set_route(self._pool_id, self._minio_ep, timeout)
        return

    def _deregister_minio_process(self):
        try:
            procdesc = self.tables.process_table.get_minio_proc(self._pool_id)
            if procdesc is None:
                logger.debug("@@@ MinIO Address Not Found")
                return
            if self._minio_proc["manager_pid"] != procdesc.get("manager_pid"):
                logger.debug("@@@ NOT OWN ENTRY")
                return
            self.tables.process_table.delete_minio_proc(self._pool_id)
            atime = self.tables.routing_table.get_route_expiry(self._pool_id)
            if atime and atime != self.saved_atime:
                logger.debug("@@@ BACKUP ATIME")
                self.tables.storage_table.set_atime(self._pool_id, atime)
            self.tables.routing_table.delete_route_expiry(self._pool_id)
            self.tables.routing_table.delete_route(self._pool_id)
        except Exception as e:
            logger.info(f"IGNORE EXCEPTION: {e}")
            logger.exception(e)
            pass
        return

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
            except AlarmException as e:
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

    def _handle_existing_minio(self, setup_only, need_initialize):
        logger.debug("@@@ +++")
        if need_initialize:
            # Should not happen.
            logger.error("INTERNAL ERROR: may corrupt database.")
            logger.debug("@@@ return immidiately")
            return
        elif setup_only:
            # Stop a running MinIO
            procdesc = self.tables.process_table.get_minio_proc(self._pool_id)
            assert procdesc is not None
            ##AHO
            if procdesc["mux_host"] != self._mux_ep:
                logger.error("INTERNAL ERROR: "
                             "DATABASE OR SCHEDULER MAY CORRUPT. "
                             f"{procdesc['mux_host']} {self._mux_ep}")
                logger.debug("@@@ return immidiately")
                return
            else:
                logger.debug("@@@ kill sup pid")
                pid = procdesc.get("manager_pid")
                assert pid is not None
                manager_pid = int(pid)
                if os.getpid() != manager_pid:
                    self._kill_manager_process(manager_pid)
                else:
                    logger.error(f"KILL MYSELF?: {manager_pid}")
                return
        else:
            # MinIO is running.
            logger.debug("@@@ return immidiately")
            return
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
        return

    def _set_current_mode(self, pool_id, mode, reason):
        self.tables.storage_table.set_mode(pool_id, mode)
        return

    def _check_elapsed_time(self):
        now = int(time.time())
        elapsed_time = now - self._lock_start
        if elapsed_time + self.timeout_margin > self._lock_timeout:
            logger.warning("lock time exceeded")
            pass
        return

    def _check_table_status_and_expiration(self, now):
        # Check the existence of a pool description.
        pooldesc = self.tables.storage_table.get_pool(self._pool_id)
        if pooldesc is None:
            raise Termination("Pool removed.")
        if pooldesc["permit_status"] != "allowed":
            raise Termination("Pool disabled.")
        if pooldesc["online_status"] != "online":
            raise Termination("Pool not online.")
        # Check the existence of a process description.
        procdesc = self.tables.process_table.get_minio_proc(self._pool_id)
        if procdesc is None:
            raise Termination("MinIO process removed.")
        if self._minio_proc["manager_pid"] != procdesc.get("manager_pid"):
            logger.error("MinIO process restarted while a Manager is alive.")
            raise Termination("MinIO process maybe overtaken.")
        # Check the expiration of a pool.
        if now >= self._expiration_date:
            logger.info(f"Pool expired: {self._pool_id}")
            raise Termination("Pool expiration.")
        # Check the expiration of MinIO endpoint information.
        atime = self.tables.routing_table.get_route_expiry(self._pool_id)
        if atime is None:
            logger.error(f"MinIO endpoint update failed: pool={self._pool_id}.")
            raise Termination("MinIO endpoint update failure.")
        atime = int(atime)
        elapsed = now - atime
        if elapsed > self.keepalive_limit:
            logger.error(f"MinIO endpoint update failed: pool={self._pool_id}.")
            raise Termination("MinIO endpoint update failure.")
        return

    def _refresh_table_status(self, timeout):
        timeout = math.ceil(timeout)
        self.tables.routing_table.set_route_expiry(self._pool_id, timeout)
        self.tables.process_table.set_minio_proc_expiry(self._pool_id, timeout)
        atime = self.tables.routing_table.get_route_expiry(self._pool_id)
        if atime and atime != self.saved_atime:
            self.tables.storage_table.set_atime(self._pool_id, atime)
            self.saved_atime = atime
            pass
        return

    def _check_minio_health(self):
        status = self._heartbeat_minio()
        if (status == 200):
            self._heartbeat_misses = 0
        else:
            self._heartbeat_misses += 1
        if self._heartbeat_misses > self.heartbeat_miss_tolerance:
            logger.info(f"MinIO heartbeat failed: pool={self._pool_id},"
                        f" miss={self._heartbeat_misses}")
            raise Termination("MinIO heartbeat failure.")
        return

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
        return

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
        except AlarmException:
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

    ##access_by_zoneID = args.accessByZoneID

    try:
        (mux_conf, configfile) = read_mux_conf(args.configfile)
    except Exception as e:
        sys.stderr.write(f"manager:main: {e}\n")
        sys.exit(ERROR_READCONF)
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
        sys.exit(ERROR_FORK)
        pass

    # (A Manager be a session leader).

    logger.info(f"**** Starting a Manager process (pool={pool_id}). ****")

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
        logger.error(f"Manager for pool={pool_id} failed: exception={e}",
                     exc_info=True)
        ##logger.exception(e)
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
