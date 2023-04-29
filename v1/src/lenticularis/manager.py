"""A sentinel process for a MinIO process.  It is also responsible to
transition of the pool state."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import os
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
from subprocess import Popen, DEVNULL, PIPE, TimeoutExpired
import random
import select
import sys
import threading
import time
import contextlib
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from lenticularis.mc import Mc, assert_mc_success
from lenticularis.readconf import read_mux_conf
from lenticularis.table import get_table
from lenticularis.poolutil import Pool_State
from lenticularis.poolutil import gather_buckets, gather_keys
from lenticularis.poolutil import get_manager_name_for_messages
from lenticularis.poolutil import tally_manager_expiry
from lenticularis.utility import ERROR_EXIT_READCONF, ERROR_EXIT_FORK
from lenticularis.utility import generate_access_key
from lenticularis.utility import generate_secret_key
from lenticularis.utility import copy_minimal_env, host_port
from lenticularis.utility import uniform_distribution_jitter
from lenticularis.utility import wait_one_line_on_stdout
from lenticularis.utility import rephrase_exception_message
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


def _manager_info_string(desc):
    """Returns a print string for a Minio manager.  It accepts both
    records of minio_manager and minio_proc.
    """
    muxep = host_port(desc["mux_host"], desc["mux_port"])
    pid = desc["manager_pid"]
    return f"{muxep}/pid={pid}"


class Manager():
    """A sentinel for a MinIO process.  It is started by a Controller as a
    daemon (and exits immediately), and it informs the caller about a
    successful start-up of a MinIO by placing a one line message on
    stdout.  A Redis key for a manager record is used as a mutex with
    expiry, which protects the activity of a manager.
    """

    def __init__(self, pool_id, args, mux_conf):
        self._verbose = False
        self._alarm_section = None

        self._pool_id = pool_id
        self._mux_host = args.host
        self._mux_port = args.port
        self._mux_ep = host_port(self._mux_host, self._mux_port)
        self._port_min = int(args.port_min)
        self._port_max = int(args.port_max)
        self._pid = os.getpid()

        ctl_param = mux_conf["minio_manager"]
        self._bin_sudo = ctl_param["sudo"]
        self._minio_awake_duration = int(ctl_param["minio_awake_duration"])
        self._minio_setup_at_restart = ctl_param["minio_setup_at_restart"]
        self._heartbeat_interval = int(ctl_param["heartbeat_interval"])
        self._heartbeat_tolerance = int(ctl_param["heartbeat_miss_tolerance"])
        self._heartbeat_timeout = int(ctl_param["heartbeat_timeout"])
        self._minio_start_timeout = int(ctl_param["minio_start_timeout"])
        self._minio_setup_timeout = int(ctl_param["minio_setup_timeout"])
        self._minio_stop_timeout = int(ctl_param["minio_stop_timeout"])
        self._mc_timeout = int(ctl_param["minio_mc_timeout"])
        self._watch_gap_minimal = (self._heartbeat_interval / 8)
        self._manager_expiry = tally_manager_expiry(self._heartbeat_tolerance,
                                                    self._heartbeat_interval,
                                                    self._heartbeat_timeout)

        minio_param = mux_conf["minio"]
        self._bin_minio = minio_param["minio"]
        self._bin_mc = minio_param["mc"]

        self.tables = get_table(mux_conf)
        pass

    def _sigalrm(self, n, stackframe):
        logger.debug(f"Manager (pool={self._pool_id}) got a sigalrm.")
        raise Alarmed(self._alarm_section)

    def _sigterm(self, n, stackframe):
        logger.debug(f"Manager (pool={self._pool_id}) got a sigterm.")
        signal(SIGTERM, SIG_IGN)
        raise Termination("Manager got a sigterm.")

    def _tell_spawner_minio_starts(self):
        # Note that a closure of stdout is not detected at the reader side.
        sys.stdout.write(f"{self._minio_ep}\n")
        sys.stdout.flush()
        sys.stdout.close()
        sys.stderr.close()
        contextlib.redirect_stdout(None)
        contextlib.redirect_stderr(None)
        pass

    def _set_pool_state(self, poolstate, reason):
        pool_id = self._pool_id
        (o, _) = self.tables.get_pool_state(pool_id)
        logger.debug(f"Manager (pool={pool_id}):"
                     f" Pool-state change: {o} to {poolstate}")
        self.tables.set_pool_state(self._pool_id, poolstate, reason)
        pass

    def _check_pool_is_enabled(self):
        """Checks expiration, permit-status, and online-status of a pool, and
        updates the pool-state if it changes.  It returns a pair of OK
        status and a string for raising an exception.
        """
        now = int(time.time())
        pool_id = self._pool_id
        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            reason = "Pool removed"
            return (False, reason)
        (poolstate, currentreason) = self.tables.get_pool_state(pool_id)
        if poolstate is None:
            logger.error(f"Manager (pool={pool_id}): Pool-state not found.")
            reason = "No pool state"
            return (False, reason)
        if poolstate in {Pool_State.INOPERABLE}:
            return (False, currentreason)
        user_id = pooldesc["owner_uid"]
        unexpired = now < pooldesc["expiration_date"]
        u = self.tables.get_user(user_id)
        permitted = u["permitted"]
        online = pooldesc["online_status"]
        ok = (unexpired and permitted and online)
        # if not ok and poolstate in {}:
        #     reason = "Pool disabled initially"
        #     self._set_pool_state(Pool_State.INOPERABLE, reason)
        #     return (False, reason)
        if not ok and poolstate in {Pool_State.INITIAL, Pool_State.READY}:
            if not unexpired:
                reason = "Pool expired"
                self._set_pool_state(Pool_State.DISABLED, reason)
                return (False, reason)
            if not permitted:
                reason = "User disabled"
                self._set_pool_state(Pool_State.DISABLED, reason)
                return (False, reason)
            if not online:
                reason = "Pool offline"
                self._set_pool_state(Pool_State.DISABLED, reason)
                return (False, reason)
            return (False, "Pool in error")
        elif ok and poolstate in {Pool_State.DISABLED}:
            # Force to setup, without regard to minio_setup_at_restart.
            self._set_pool_state(Pool_State.INITIAL, "-")
            return (True, "-")
        else:
            # State unchanged.
            ok = poolstate in {Pool_State.INITIAL, Pool_State.READY}
            return (ok, currentreason)
        pass

    def _warn_inconsistent_record(self, record_name, active, stored):
        assert record_name in {"manager", "process", "endpoint"}
        pool_id = self._pool_id
        if stored is None:
            logger.warning(f"Manager (pool={pool_id}):"
                           f" A MinIO {record_name} record missing.")
        else:
            if record_name == "manager":
                oldname = _manager_info_string(active)
                newname = _manager_info_string(stored)
            elif record_name == "process":
                oldname = _manager_info_string(active)
                newname = _manager_info_string(stored)
            elif record_name == "endpoint":
                oldname = active
                newname = stored
            else:
                assert False
                pass
            logger.error(f"Manager (pool={pool_id}):"
                         f" Inconsistent MinIO {record_name} records:"
                         f" current={oldname}, new={newname}")
            pass
        pass

    def _warn_stale_record(self, record_name, active, stored):
        pool_id = self._pool_id
        assert record_name in {"manager", "process", "endpoint"}
        if record_name == "manager":
            newname = _manager_info_string(stored)
        elif record_name == "process":
            newname = _manager_info_string(stored)
        elif record_name == "endpoint":
            newname = stored
        else:
            assert False
            pass
        logger.warning(f"Manager (pool={pool_id}) removing"
                       f" a stale MinIO {record_name} record:"
                       f" entry={newname}")
        pass

    def manager_main(self):
        pool_id = self._pool_id

        # Check the thread is main for using signals:
        assert threading.current_thread() == threading.main_thread()

        signal(SIGALRM, self._sigalrm)

        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            logger.error(f"Manager (pool={pool_id}) failed: pool removed")
            return False

        # Record a manager entry of this manager.

        ma = self.tables.get_minio_manager(pool_id)
        if ma is None:
            logger.error(f"Manager (pool={pool_id}) failed: no manager entry")
            return False
        self._minio_manager = ma

        # Register a manager entry and exclude others.
        #
        # now = int(time.time())
        # ma = {
        #     "mux_host": self._mux_host,
        #     "mux_port": self._mux_port,
        #     "manager_pid": self._pid,
        #     "modification_time": now
        # }
        # self._minio_manager = ma
        # (ok, holder) = self.tables.set_ex_minio_manager(pool_id, ma)
        # if not ok:
        #     muxep0 = host_port(self._mux_host, self._mux_port)
        #     muxep1 = get_manager_name_for_messages(holder)
        #     logger.info(f"Manager (pool={pool_id}) yields work to another:"
        #                 f" Mux={muxep0} to Mux={muxep1}")
        #     return False
        #
        # This manager takes the role.
        #
        # ok = self.tables.set_minio_manager_expiry(pool_id, self._manager_expiry)
        # if not ok:
        #     logger.warning(f"Manager (pool={pool_id}) failed to set expiry.")
        #     pass

        try:
            self._deregister_minio_process(clean_stale_record=True)
            ok = self._manage_minio()
        finally:
            ma = self.tables.get_minio_manager(pool_id)
            if ma == self._minio_manager:
                self.tables.delete_minio_manager(pool_id)
            else:
                active = self._minio_manager
                stored = ma
                self._warn_inconsistent_record("manager", active, stored)
                pass
            pass
        return ok

    def _manage_minio(self):
        pool_id = self._pool_id
        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            logger.error(f"Manager (pool={pool_id}) failed: pool removed.")
            return False
        user_id = pooldesc["owner_uid"]
        group_id = pooldesc["owner_gid"]
        directory = pooldesc["buckets_directory"]

        (ok, reason) = self._check_pool_is_enabled()
        if not ok:
            logger.debug(f"Manager (pool={pool_id})"
                         f"Pool is not enabled: ({reason})")
            return False

        self._minio_root_user = generate_access_key()
        self._minio_root_password = generate_secret_key()
        env = copy_minimal_env(os.environ)
        self._env_minio = env
        self._env_mc = env.copy()
        self._env_minio["MINIO_ROOT_USER"] = self._minio_root_user
        self._env_minio["MINIO_ROOT_PASSWORD"] = self._minio_root_password
        self._env_minio["MINIO_BROWSER"] = "off"

        #  self._env_minio["MINIO_CACHE_DRIVES"] = f"/tmp/{self._pool_id}"
        #  self._env_minio["MINIO_CACHE_EXCLUDE"] = ""
        #  self._env_minio["MINIO_CACHE_QUOTA"] = "80"
        #  self._env_minio["MINIO_CACHE_AFTER"] = "3"
        #  self._env_minio["MINIO_CACHE_WATERMARK_LOW"] = "70"
        #  self._env_minio["MINIO_CACHE_WATERMARK_HIGH"] = "90"

        # (poolstate, _) = self.tables.get_pool_state(self._pool_id)
        # assert poolstate in {Pool_State.INITIAL, Pool_State.READY}
        # procdesc = self.tables.get_minio_proc(self._pool_id)
        # assert procdesc is None

        ports = list(range(self._port_min, self._port_max + 1))
        random.shuffle(ports)
        (p, nonfatal) = (None, True)
        for port in ports:
            (p, nonfatal) = self._try_start_minio(port, user_id, group_id,
                                                  directory)
            if p is not None:
                break
            if not nonfatal:
                break
            pass
        if p is None:
            if nonfatal:
                logger.error(f"Manager (pool={pool_id}) failed"
                             f" to start MinIO (all ports used).")
                pass
            return False
        ok = True
        try:
            logger.info(f"Manager (pool={pool_id}) starting.")
            self._setup_and_watch_minio(p, pooldesc)
        finally:
            logger.info(f"Manager (pool={pool_id}) exiting.")
            pass
        return ok

    def _try_start_minio(self, port, user, group, directory):
        pool_id = self._pool_id
        address = f":{port}"
        cmd = [self._bin_sudo, "-n", "-u", user, "-g", group,
               self._bin_minio, "server", "--anonymous",
               "--address", address, directory]
        assert all(isinstance(i, str) for i in cmd)
        p = None
        try:
            alarm(self._minio_start_timeout)
            logger.debug(f"Manager (pool={pool_id}) starting MinIO: {cmd}")
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self._env_minio)
            (ok, error_is_nonfatal) = self._wait_for_minio_to_come_up(p)
            alarm(0)
            if ok:
                logger.debug(f"Manager (pool={pool_id}) MinIO started.")
                self._minio_ep = host_port(self._mux_host, port)
                return (p, True)
            else:
                self._minio_ep = None
                return (None, error_is_nonfatal)
        except Exception as e:
            # (e is SubprocessError, OSError, ValueError, usually).
            m = rephrase_exception_message(e)
            logger.error(f"Manager (pool={pool_id}) failed to starting MinIO:"
                         f" command=({cmd}); exception=({m})",
                         exc_info=True)
            reason = "Start failed (exec failure)"
            self._set_pool_state(Pool_State.INOPERABLE, reason)
            self._minio_ep = None
            return (None, False)
        finally:
            alarm(0)
            pass
        assert p is None
        self._minio_ep = None
        return (None, True)

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
        pool_id = self._pool_id
        (outs, errs, closed) = wait_one_line_on_stdout(p, None)
        if outs.startswith(_minio_expected_response):
            logger.info(f"Manager (pool={pool_id})"
                        f" message on MinIO outs=({outs}) errs=({errs})")
            return (True, False)
        else:
            # A closure of stdout is presumably an error.  But, it
            # does not try to terminate a child since it is "sudo".
            try:
                (o_, e_) = p.communicate(timeout=15)
                outs += o_
                errs += e_
            except TimeoutExpired:
                pass
            p_status = p.poll()
            m0 = f"Manager (pool={pool_id}) starting MinIO failed with"
            m1 = (f" exit={p_status}" f" outs=({outs}) errs=({errs})")
            if outs.find(_minio_error_response) != -1:
                if outs.find(_minio_response_port_in_use) != -1:
                    reason = "port-in-use (transient)"
                    logger.debug(f"{m0} {reason}: {m1}")
                    return (False, True)
                elif outs.find(_minio_response_unwritable_storage) != -1:
                    reason = "Storage unwritable"
                    self._set_pool_state(Pool_State.INOPERABLE, reason)
                    logger.info(f"{m0} {reason}: {m1}")
                    return (False, False)
                else:
                    reason = "Start failed"
                    self._set_pool_state(Pool_State.INOPERABLE, reason)
                    logger.error(f"{m0} {reason}: {m1}")
                    return (False, False)
                pass
            else:
                reason = "Start failed (no error)"
                self._set_pool_state(Pool_State.INOPERABLE, reason)
                logger.error(f"{m0} {reason}: {m1}")
                return (False, False)
            pass
        pass

    def _setup_and_watch_minio(self, p, pooldesc):
        assert self._minio_ep is not None
        pool_id = self._pool_id
        self._mc = Mc(self._bin_mc, self._env_mc, self._minio_ep,
                      self._pool_id, self._mc_timeout)
        (poolstate, _) = self.tables.get_pool_state(pool_id)
        assert poolstate in {Pool_State.INITIAL, Pool_State.READY}
        try:
            if (poolstate in {Pool_State.INITIAL}
                or self._minio_setup_at_restart):
                self._setup_minio(p, pooldesc)
                pass
            self._register_minio_process(p.pid, pooldesc)
        except Exception:
            self._stop_minio(p)
            raise
        finally:
            self._tell_spawner_minio_starts()
            pass

        self._set_pool_state(Pool_State.READY, "-")
        try:
            self._watch_minio(p)
        finally:
            self._deregister_minio_process(clean_stale_record=False)
            self._stop_minio(p)
            pass
        pass

    def _setup_minio(self, p, pooldesc):
        pool_id = self._pool_id
        with self._mc.alias_set(self._minio_root_user,
                                self._minio_root_password):
            try:
                alarm(self._minio_setup_timeout)
                self._alarm_section = "alarm-set-in-setup-minio"
                bkts = gather_buckets(self.tables, pool_id)
                self._mc.setup_minio_on_buckets(bkts)
                keys = gather_keys(self.tables, pool_id)
                self._mc.setup_minio_on_keys(keys)
                alarm(0)
                self._alarm_section = None
            except Alarmed as e:
                alarm(0)
                self._alarm_section = None
                reason = "Initialization failed (timeout)"
                self._set_pool_state(Pool_State.INOPERABLE, reason)
                raise Exception(reason)
            except Exception as e:
                alarm(0)
                self._alarm_section = None
                m = rephrase_exception_message(e)
                reason = f"{m}"
                self._set_pool_state(Pool_State.INOPERABLE, reason)
                logger.error(f"Manager (pool={pool_id})"
                             f" failed to initialize MinIO:"
                             f" exception=({m})",
                             exc_info=True)
                raise
            pass
        pass

    def _watch_minio(self, p):
        """Watches a MinIO process.  MinIO usually outputs nothing on
           stdout/stderr, and this does a periodic work of
           heartbeating.
        """
        pool_id = self._pool_id
        logger.debug(f"Manager (pool={pool_id}) starts watching:"
                     f" MinIO={self._minio_ep}.")

        signal(SIGTERM, self._sigterm)
        signal(SIGCHLD, SIG_IGN)

        try:
            self._last_check_ts = 0
            self._last_access_ts = 0
            while True:
                jitter = uniform_distribution_jitter()
                timeo = self._heartbeat_interval + jitter
                (readable, _, _) = select.select(
                    [p.stdout, p.stderr], [], [], timeo)

                if p.stderr in readable:
                    (errs, closed) = _read_stream(p.stderr)
                    if errs != b"":
                        logger.info(f"Manager (pool={pool_id}):"
                                    f" Message on MinIO stderr=({errs})")
                        pass
                    pass
                if p.stdout in readable:
                    (outs, closed) = _read_stream(p.stdout)
                    if outs != b"":
                        logger.info(f"Manager (pool={pool_id}):"
                                    f" Message on MinIO stdout=({outs})")
                        pass
                    if closed:
                        raise Termination("MinIO closed stdout.")
                    pass

                now = int(time.time())
                if self._last_check_ts + self._watch_gap_minimal < now:
                    self._last_check_ts = now
                    self._check_pool_status()
                    self._check_record_expiry()
                    self._check_minio_health()
                    pass
                pass
        except Termination as e:
            logger.debug(f"Manager (pool={pool_id}) terminating with=({e})")
            pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Manager (pool={pool_id}) errs in a watch loop:"
                         f" MinIO={self._minio_ep}; exception=({m})",
                         exc_info=True)
            pass
        pass

    def _register_minio_process(self, pid, pooldesc):
        self._minio_proc = {
            "minio_ep": self._minio_ep,
            "minio_pid": pid,
            "admin": self._minio_root_user,
            "password": self._minio_root_password,
            "mux_host": self._mux_host,
            "mux_port": self._mux_port,
            "manager_pid": self._pid,
            "modification_time": int(time.time()),
        }
        self.tables.set_minio_proc(self._pool_id, self._minio_proc)
        self.tables.set_minio_ep(self._pool_id, self._minio_ep)
        self._check_record_expiry()
        pass

    def _check_record_expiry(self):
        # It may happen to extend expiry for other managers (ignored).
        pool_id = self._pool_id
        ok = self.tables.set_minio_manager_expiry(pool_id, self._manager_expiry)
        if not ok:
            logger.warning(f"Manager (pool={pool_id}) failed to set expiry.")
            pass
        ma = self.tables.get_minio_manager(pool_id)
        if ma == self._minio_manager:
            pass
        elif ma is None:
            oldma = _manager_info_string(self._minio_manager)
            logger.warning(f"Manager (pool={pool_id}): MinIO entry expired; "
                           f" current={oldma}.")
            raise Termination("Entry expired")
        else:
            active = self._minio_manager
            stored = ma
            self._warn_inconsistent_record("manager", active, stored)
            raise Termination("Entry overtaken")
        pass

    def _deregister_minio_process(self, *, clean_stale_record):
        pool_id = self._pool_id
        inconsistent = False
        try:
            # Check for a MinIO process record.
            mn = self.tables.get_minio_proc(pool_id)
            if not clean_stale_record:
                if mn == self._minio_proc:
                    pass
                else:
                    active = self._minio_proc
                    stored = mn
                    inconsistent = (mn is not None)
                    self._warn_inconsistent_record("process", active, stored)
                    pass
            else:
                if mn is None:
                    pass
                else:
                    active = self._minio_proc
                    stored = mn
                    self._warn_stale_record("process", active, stored)
                    pass
                pass
            # Check for a MinIO endpoint record.
            ep = self.tables.get_minio_ep(pool_id)
            if not clean_stale_record:
                if ep == self._minio_ep:
                    pass
                else:
                    active = self._minio_ep
                    stored = ep
                    inconsistent = (ep is not None)
                    self._warn_inconsistent_record("endpoint", active, stored)
                    pass
                pass
            else:
                if ep is None:
                    pass
                else:
                    active = self._minio_ep
                    stored = ep
                    self._warn_stale_record("endpoint", active, stored)
                    pass
                pass
            if mn is not None and not inconsistent:
                self.tables.delete_minio_proc(pool_id)
                pass
            if ep is not None and not inconsistent:
                self.tables.delete_minio_ep(pool_id)
                pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Manager (pool={pool_id}) failed in"
                         f" removing MinIO records (ignored):"
                         f" exception=({m})",
                         exc_info=True)
            pass
        pass

    def _stop_minio(self, p):
        # Note raising an exception at a signal does not wake-up the
        # Python waiting for a MC command.  Instead, a timeout of MC
        # command will be in effect.  Note also it is impossible to
        # kill the subprocess here because it is run via sudo.
        pool_id = self._pool_id
        # logger.debug(f"Manager (pool={pool_id}) stopping MinIO: {p}.")
        with self._mc.alias_set(self._minio_root_user,
                                self._minio_root_password):
            try:
                alarm(self._minio_stop_timeout)
                self._alarm_section = "alarm-set-in-stop-minio"
                r = self._mc.admin_service_stop()
                assert_mc_success(r, "mc.admin_service_stop")
                # p_status = p.wait()
            except Alarmed as e:
                logger.error(f"Manager (pool={pool_id})"
                             f" stopping MinIO timed out:"
                             f" exception ignored: exception=({e})")
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.error(f"Manager (pool={pool_id})"
                             f" stopping MinIO failed:"
                             f" exception ignored: exception=({m})",
                             exc_info=True)
            finally:
                alarm(0)
                self._alarm_section = None
                pass
            pass
        try:
            (outs, errs) = p.communicate(timeout=self._minio_stop_timeout)
            if errs != b"":
                logger.info(f"Manager (pool={pool_id}):"
                            f" Message on MinIO stderr=({errs})")
                pass
            if outs != b"":
                logger.info(f"Manager (pool={pool_id}):"
                            f" Message on MinIO stdout=({outs})")
                pass
        except TimeoutExpired:
            pass
        p_status = p.poll()
        if p_status is None:
            logger.warning(f"Manager (pool={pool_id}): MinIO does not stop.")
            pass
        pass

    def _check_pool_status(self):
        """Checks the status and shutdown the work when inappropriate.  Some
        logging output is done at deregistering.
        """
        pool_id = self._pool_id
        now = int(time.time())
        # Check the status of a pool.
        (ok, reason) = self._check_pool_is_enabled()
        if not ok:
            raise Termination(reason)
        # Check the lifetime is expired.
        elapsed = now - self._last_access_ts
        if elapsed > self._minio_awake_duration:
            ts = self.tables.get_access_timestamp(pool_id)
            if ts is None:
                logger.warning(f"Manager (pool={pool_id}):"
                               f" timestamp missing (pool removed).")
                raise Termination("Timestamp removed")
            self._last_access_ts = ts
            elapsed = now - ts
            if elapsed > self._minio_awake_duration:
                logger.debug(f"Manager (pool={pool_id}):"
                             f" keep-awake expired.")
                raise Termination("Keep-awake expired")
            pass
        pass

    def _check_minio_health(self):
        pool_id = self._pool_id
        status = self._heartbeat_minio()
        if (status == 200):
            self._heartbeat_misses = 0
        else:
            self._heartbeat_misses += 1
            pass
        if self._heartbeat_misses > self._heartbeat_tolerance:
            logger.info(f"Manager (pool={pool_id})"
                        f" failed to heartbeat MinIO:"
                        f" misses={self._heartbeat_misses}")
            raise Termination("MinIO heartbeat failure")
        pass

    def _heartbeat_minio(self):
        pool_id = self._pool_id
        url = f"http://{self._minio_ep}/minio/health/live"
        failure_message = (f"Manager (pool={pool_id})"
                           f" failed to heartbeat MinIO, urlopen error:"
                           f" url=({url});")
        try:
            res = urlopen(url, timeout=self._heartbeat_timeout)
            if self._verbose:
                logger.debug(f"Manager (pool={pool_id}) heartbeats MinIO.")
                pass
            return res.status
        except HTTPError as e:
            logger.warning(failure_message + f" exception=({e})")
            return e.code
        except URLError as e:
            logger.warning(failure_message + f" exception=({e})")
            return 503
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.warning(failure_message + f" exception=({m})")
            return 500
        pass

    def _heartbeat_minio_via_mc_(self):
        # NOT USED.
        # Use of the following method is recommended by MinIO:
        # curl -I https://minio.example.net:9000/minio/health/live
        pool_id = self._pool_id
        r = None
        try:
            with self._mc.alias_set(self._minio_root_user,
                                    self._minio_root_password):
                alarm(self._heartbeat_timeout)
                self._alarm_section = "alarm-set-in-heartbeat-minio"
                (p_, r) = self._mc.admin_info()
                assert p_ is None
                assert_mc_success(r, "mc.admin_info")
                alarm(0)
                self._alarm_section = None
                pass
            if self._verbose:
                logger.debug(f"Manager (pool={pool_id}) heartbeats MinIO.")
                pass
        except Alarmed:
            raise Exception("Hearbeat timeout")
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Hearbeat failed: exception=({m})")
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
    parser.add_argument("pool_id")
    parser.add_argument("--configfile")
    # parser.add_argument("--useTrueAccount", type=bool, default=False,
    #                     action=argparse.BooleanOptionalAction)
    # parser.add_argument("--accessByZoneID", type=bool, default=False,
    #                     action=argparse.BooleanOptionalAction)
    parser.add_argument("--traceid")
    args = parser.parse_args()

    # pool_id = os.environ.get("LENS3_POOL_ID")
    # if pool_id is None:
    #    sys.stderr.write(f"Manager failed: No pool-ID.\n")
    #    sys.exit(ERROR_EXIT_READCONF)
    #    pass

    pool_id = args.pool_id
    try:
        (mux_conf, _) = read_mux_conf(args.configfile)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Manager (pool={pool_id}) failed"
                         f" in reading a config file: exception=({m})\n")
        sys.exit(ERROR_EXIT_READCONF)
        pass

    tracing.set(args.traceid)
    openlog(mux_conf["log_file"], **mux_conf["log_syslog"])

    try:
        pid = os.fork()
        if pid != 0:
            # (parent).
            sys.exit(0)
    except OSError as e:
        logger.error(f"Manager (pool={pool_id}) failed to fork:"
                     f" {os.strerror(e.errno)}")
        sys.exit(ERROR_EXIT_FORK)
        pass

    # Let a manager be a session leader.

    try:
        os.setsid()
    except OSError as e:
        logger.error(f"Manager (pool={pool_id}) setsid failed (ignored):"
                     f" {os.strerror(e.errno)}")
        pass
    try:
        os.umask(0o077)
    except OSError as e:
        logger.error(f"Manager (pool={pool_id}) set umask failed (ignored):"
                     f" {os.strerror(e.errno)}")
        pass

    manager = Manager(pool_id, args, mux_conf)
    ok = False
    try:
        ok = manager.manager_main()
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.error(f"Manager (pool={pool_id}) failed:"
                     f" exception=({m})",
                     exc_info=True)
        pass
    sys.exit(0)
    pass


if __name__ == "__main__":
    main()
