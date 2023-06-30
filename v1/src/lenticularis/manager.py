"""A sentinel for a MinIO process."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

"""A manager process is spawned and it forks again to be a session
leader.  It is responsible for watching the process state and the
output from MinIO, although MinIO usually does not output anything but
start and end messages.
"""

import argparse
import os
import errno
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
from subprocess import Popen, DEVNULL, PIPE, TimeoutExpired
import random
import select
import sys
import threading
import time
import contextlib
import json
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from lenticularis.mc import Mc
from lenticularis.table import get_table
from lenticularis.table import read_redis_conf
from lenticularis.table import get_conf
from lenticularis.pooldata import Pool_State, Pool_Reason
from lenticularis.pooldata import set_pool_state, update_pool_state
from lenticularis.pooldata import gather_buckets, gather_keys
from lenticularis.pooldata import tally_manager_expiry
from lenticularis.utility import ERROR_EXIT_BADCONF, ERROR_EXIT_FORK
from lenticularis.utility import generate_access_key
from lenticularis.utility import generate_secret_key
from lenticularis.utility import copy_minimal_environ, host_port
from lenticularis.utility import uniform_distribution_jitter
from lenticularis.utility import wait_line_on_stdout
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


class Alarmed(Exception):
    pass


class Termination(Exception):
    pass


# Messages from a MinIO process at its start-up.

_minio_expected_response = "S3-API:"
_minio_error_response__ = "ERROR"
_minio_response_port_in_use = "Specified port is already in use"
_minio_response_nonwritable_storage = "Unable to write to the backend"
_minio_response_failure = "Unable to initialize backend"
_minio_response_port_capability = "Insufficient permissions to use specified port"

def _read_stream(s):
    """Reads a stream while some is available.  It returns a pair of the
    readout and the state of a stream after reading, true on EOF.  It
    decodes the readout in Latin-1.
    """
    buf_ = b""
    while (s in select.select([s], [], [], 0)[0]):
        r = s.read1()
        if r == b"":
            break
        buf_ += r
        pass
    buf = str(buf_, "latin-1")
    return (buf, False)


def _manager_info_string(desc):
    """Returns a print string for a Minio manager.  It accepts both
    records of minio_manager and minio_proc.
    """
    muxep = host_port(desc["mux_host"], desc["mux_port"])
    pid = desc["manager_pid"]
    return f"{muxep}/pid={pid}"


def _json_loads_no_errors(s):
    """json.loads(), but ignores an error and returns an empty dict."""
    try:
        d = json.loads(s)
        return d
    except json.JSONDecodeError as e:
        return dict()
    pass


def _diagnose_minio_message(s):
    """Diagnoses messages returned at a MinIO start.  It returns 0 for a
    successful run, EAGAIN for no expected messages, EADDRINUSE for
    port-in-use, (EACCES for non-writable storage), or EIO or ENOENT
    on unknown errors.  It judges only level=FATAL as an error but
    level=ERROR not an error.
    """
    # if not in_json:
    #     m = s
    #     if m.startswith(_minio_expected_response):
    #         return (0, m)
    #     elif m.find(_minio_error_response) != -1:
    #         if m.find(_minio_response_port_in_use) != -1:
    #             return (errno.EADDRINUSE, m)
    #         elif m.find(_minio_response_nonwritable_storage) != -1:
    #             return (errno.EACCES, m)
    #         else:
    #             return (errno.EIO, m)
    #     else:
    #         return (errno.ENOENT, m)
    mm = [_json_loads_no_errors(x) for x in s.splitlines()]
    if len(mm) == 0:
        return (errno.EAGAIN, "MinIO output is empty")
    elif all(m.get("level", "") != "FATAL" for m in mm):
        m1 = next((m for m in mm
                   if (m.get("message", "")
                       .startswith(_minio_expected_response))),
                  None)
        if m1 is not None:
            msg1 = m1.get("message", "")
            return (0, msg1)
        else:
            return (errno.EAGAIN, "MinIO output contains no expected message")
    else:
        # Judge the result using the first FATAL message.
        m2 = next((m for m in mm if (m.get("level", "") == "FATAL")), None)
        assert m2 is not None
        msg2 = m2.get("message", None)
        assert msg2 is not None
        if msg2.find(_minio_response_port_in_use) != -1:
            return (errno.EADDRINUSE, msg2)
        elif msg2.find(_minio_response_nonwritable_storage) != -1:
            # This case won't happen (2023-06-14).
            return (errno.EACCES, ("MinIO error: " + msg2))
        else:
            return (errno.EIO, ("MinIO error: " + msg2))
        pass
    pass


class Manager():
    """A sentinel for a MinIO process.  It is started as a daemon by a
    Spawner, and a Spawner exits immediately.  It informs the caller
    about a successful start-up of MinIO by placing a one line message
    on stdout.  A Redis key for a manager record is used as a mutex
    with expiry, which protects the activity of a manager.
    """

    def __init__(self, pool_id, args, mux_conf, redis):
        self._verbose = False
        self._alarm_section = None

        self._pool_id = pool_id
        self._mux_host = args.host
        self._mux_port = args.port
        self._mux_ep = host_port(self._mux_host, self._mux_port)
        self._port_min = int(args.port_min)
        self._port_max = int(args.port_max)
        self._manager_pid = os.getpid()

        ctl_param = mux_conf["minio_manager"]
        self._bin_sudo = ctl_param["sudo"]
        self._minio_awake_duration = int(ctl_param["minio_awake_duration"])
        self._minio_setup_at_start = ctl_param["minio_setup_at_start"]
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

        # self.tables = get_table(mux_conf["redis"])
        self._tables = get_table(redis)
        pass

    def _sigalrm(self, n, stackframe):
        logger.debug(f"Manager (pool={self._pool_id}) got a sigalrm.")
        raise Alarmed(self._alarm_section)

    def _sigterm(self, n, stackframe):
        logger.debug(f"Manager (pool={self._pool_id}) got a sigterm.")
        signal(SIGTERM, SIG_IGN)
        raise Termination("Manager got a sigterm.")

    def _set_alarm(self, t, name):
        """Sets an alarm.  A given name is stored in an exception raised at an
        alarm.
        """
        if t == 0:
            alarm(0)
            self._alarm_section = name
        else:
            self._alarm_section = name
            alarm(t)
            pass
        pass

    def _list_minio_ports(self):
        mns = self._tables.list_minio_procs(None)
        return [int(m["minio_ep"].split(":")[1]) for (pid, m) in mns]

    def _tell_spawner_minio_starts(self):
        # Note that a closure of stdout is not detected at the reader side.
        sys.stdout.write(f"{self._minio_ep}\n")
        sys.stdout.flush()
        sys.stdout.close()
        sys.stderr.close()
        contextlib.redirect_stdout(None)
        contextlib.redirect_stderr(None)
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
        tables = self._tables

        # Check this thread is main to use signals.

        assert threading.current_thread() == threading.main_thread()
        signal(SIGALRM, self._sigalrm)

        desc = tables.get_pool(pool_id)
        if desc is None:
            logger.error(f"Manager (pool={pool_id}) failed: pool removed")
            return False

        # Take a manager record for this.

        ma1 = tables.get_manager(pool_id)
        if ma1 is None:
            logger.error(f"Manager (pool={pool_id}) failed: no manager entry")
            return False
        self._minio_manager = ma1

        try:
            self._deregister_minio_process(clean_stale_record=True)
            ok = self._manage_minio()
        finally:
            ma2 = tables.get_manager(pool_id)
            if ma2 == self._minio_manager:
                tables.delete_manager(pool_id)
            else:
                active = self._minio_manager
                stored = ma2
                self._warn_inconsistent_record("manager", active, stored)
                pass
            pass
        return ok

    def _manage_minio(self):
        """Starts MinIO and watches a state change of its process.  It does
        not return until MinIO finishes or returns on failure.  It
        returns false on failure.
        """
        pool_id = self._pool_id
        tables = self._tables
        desc = tables.get_pool(pool_id)
        if desc is None:
            logger.error(f"Manager (pool={pool_id}) failed: pool removed")
            return False
        user_id = desc["owner_uid"]
        group_id = desc["owner_gid"]
        directory = desc["buckets_directory"]

        (state, reason) = update_pool_state(tables, pool_id)
        if not state in {Pool_State.INITIAL, Pool_State.READY}:
            logger.debug(f"Manager (pool={pool_id})"
                         f"Pool is not enabled: ({reason})")
            return False

        self._minio_root_user = generate_access_key()
        self._minio_root_password = generate_secret_key()
        env = copy_minimal_environ(os.environ)
        self._env_minio = env
        self._env_mc = env.copy()
        self._env_minio["MINIO_ROOT_USER"] = self._minio_root_user
        self._env_minio["MINIO_ROOT_PASSWORD"] = self._minio_root_password
        self._env_minio["MINIO_BROWSER"] = "off"

        # self._env_minio["MINIO_CACHE_DRIVES"] = f"/tmp/{self._pool_id}"
        # self._env_minio["MINIO_CACHE_EXCLUDE"] = ""
        # self._env_minio["MINIO_CACHE_QUOTA"] = "80"
        # self._env_minio["MINIO_CACHE_AFTER"] = "3"
        # self._env_minio["MINIO_CACHE_WATERMARK_LOW"] = "70"
        # self._env_minio["MINIO_CACHE_WATERMARK_HIGH"] = "90"

        # (poolstate, _, _) = tables.get_pool_state(self._pool_id)
        # assert poolstate in {Pool_State.INITIAL, Pool_State.READY}
        # procdesc = tables.get_minio_proc(self._pool_id)
        # assert procdesc is None

        availables = set(range(self._port_min, self._port_max + 1))
        used = set(self._list_minio_ports())
        ports = list(availables - used)
        random.shuffle(ports)
        if self._verbose:
            logger.debug(f"Manager (pool={pool_id}) tries to start MinIO:"
                         f" ports={ports}")
            pass
        (p, continuable) = (None, True)
        for port in ports:
            (p, continuable) = self._try_start_minio(port, user_id, group_id,
                                                     directory)
            if p is not None:
                break
            if not continuable:
                break
            pass
        if p is None:
            if continuable:
                logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
                             f" (all ports used)")
                reason = Pool_Reason.BACKEND_BUSY
                set_pool_state(tables, pool_id, Pool_State.SUSPENDED, reason)
                pass
            return False
        try:
            logger.info(f"Manager (pool={pool_id}) starting.")
            self._setup_and_watch_minio(p)
        finally:
            logger.info(f"Manager (pool={pool_id}) exiting.")
            pass
        return True

    def _try_start_minio(self, port, user, group, directory):
        pool_id = self._pool_id
        tables = self._tables
        address = f":{port}"
        cmd = [self._bin_sudo, "-n", "-u", user, "-g", group,
               self._bin_minio, "--json", "--anonymous", "server",
               "--address", address, directory]
        assert all(isinstance(i, str) for i in cmd)
        p = None
        try:
            self._set_alarm(self._minio_start_timeout, "start-minio")
            logger.debug(f"Manager (pool={pool_id}) starting MinIO: {cmd}")
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self._env_minio)
            (ok, continuable) = self._wait_for_minio_to_come_up(p)
            self._set_alarm(0, None)
            if ok:
                logger.debug(f"Manager (pool={pool_id}) MinIO started.")
                self._minio_ep = host_port(self._mux_host, port)
                return (p, True)
            else:
                self._minio_ep = None
                return (None, continuable)
        except Exception as e:
            # (e is SubprocessError, OSError, ValueError, usually).
            m = rephrase_exception_message(e)
            logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
                         f" command=({cmd}); exception=({m})",
                         exc_info=True)
            reason = Pool_Reason.EXEC_FAILED + f"{m}"
            set_pool_state(tables, pool_id, Pool_State.INOPERABLE, reason)
            self._minio_ep = None
            return (None, False)
        finally:
            self._set_alarm(0, None)
            pass
        assert p is None
        self._minio_ep = None
        return (None, True)

    def _wait_for_minio_to_come_up(self, p):
        """Checks a MinIO start by messages it outputs.  It looks for a
        message with "S3-API:" or one with level=FATAL.  Or, it
        detects a closure of stdout (a process exit) or a timeout.
        "S3-API:" is an expected message at a successful start:
        "S3-API: http://xx.xx.xx.xx:9000 http://127.0.0.1:9000".  Note
        it does not try to terminate a process on an error since it is
        under sudo.  So, it may leave a process.
        """
        pool_id = self._pool_id
        tables = self._tables
        limit = int(time.time()) + self._minio_start_timeout
        (code, message) = (0, "")
        (o1, e1, closed, timeout) = (b"", b"", False, False)
        while True:
            (o1, e1, closed, timeout) = wait_line_on_stdout(p, o1, e1, limit)
            (code, message) = _diagnose_minio_message(str(o1, "latin-1"))
            if code != errno.EAGAIN or closed or timeout:
                break
            pass
        outs1 = str(o1, "latin-1").strip()
        errs1 = str(e1, "latin-1").strip()
        p_status1 = p.poll()
        if code == 0:
            logger.info(f"Manager (pool={pool_id}) MinIO outputs message:"
                        f" outs=({outs1}) errs=({errs1})")
            return (True, True)
        elif code == errno.EAGAIN:
            # IT IS NOT AN EXPECTED STATE NOR AN ERROR.  BUT, LET IT
            # CONTINUE THE WORK IF THE PROCESS IS RUNNING.
            if p_status1 is not None:
                logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
                             f"exit={p_status1} outs=({outs1}) errs=({errs1})")
                set_pool_state(tables, pool_id, Pool_State.INOPERABLE, message)
                return (False, False)
            else:
                logger.error(f"Manager (pool={pool_id}) starting MinIO"
                             f" gets in a dubious state (work continues):"
                             f"exit={p_status1} outs=({outs1}) errs=({errs1})")
                return (True, True)
        else:
            # Terminate the process after extra time to collect messages.
            try:
                (o_, e_) = p.communicate(timeout=1)
                o1 += o_
                e1 += e_
            except TimeoutExpired:
                pass
            outs2 = str(o1, "latin-1").strip()
            errs2 = str(e1, "latin-1").strip()
            p_status2 = p.poll()
            if code == errno.EADDRINUSE:
                logger.debug(f"Manager (pool={pool_id}) Starting MinIO failed:"
                             f" port-in-use (transient);"
                             f" exit={p_status2}"
                             f" outs=({outs2}) errs=({errs2})")
                return (False, True)
            else:
                logger.error(f"Manager (pool={pool_id}) Starting MinIO failed:"
                             f" exit={p_status2}"
                             f" outs=({outs2}) errs=({errs2})")
                set_pool_state(tables, pool_id, Pool_State.INOPERABLE, message)
                return (False, False)
            pass
        pass

    def _setup_and_watch_minio(self, p):
        assert self._minio_ep is not None
        pool_id = self._pool_id
        tables = self._tables
        self._mc = Mc(self._bin_mc, self._env_mc, self._minio_ep,
                      self._pool_id, self._mc_timeout)
        (state, _, _) = tables.get_pool_state(pool_id)
        assert state in {Pool_State.INITIAL, Pool_State.READY}
        try:
            if (state in {Pool_State.INITIAL} or self._minio_setup_at_start):
                self._setup_minio(p)
                pass
            self._register_minio_process(p.pid)
        except Exception:
            self._stop_minio(p)
            raise
        finally:
            self._tell_spawner_minio_starts()
            pass

        set_pool_state(tables, pool_id, Pool_State.READY, Pool_Reason.NORMAL)
        try:
            self._watch_minio(p)
        finally:
            self._deregister_minio_process(clean_stale_record=False)
            self._stop_minio(p)
            pass
        pass

    def _setup_minio(self, p):
        pool_id = self._pool_id
        tables = self._tables
        with self._mc.mc_alias_set(self._minio_root_user,
                                   self._minio_root_password):
            try:
                self._set_alarm(self._minio_setup_timeout, "setup-minio")
                bkts = gather_buckets(tables, pool_id)
                self._mc.setup_minio_on_buckets(bkts)
                keys = gather_keys(tables, pool_id)
                self._mc.setup_minio_on_secrets(keys)
                self._set_alarm(0, None)
            except Alarmed as e:
                self._set_alarm(0, None)
                reason = Pool_Reason.SETUP_FAILED + "timeout"
                set_pool_state(tables, pool_id, Pool_State.INOPERABLE, reason)
                logger.error((f"Manager (pool={pool_id})"
                              f" Initializing MinIO failed: timeout"),
                             exc_info=False)
                raise Exception(reason)
            except Exception as e:
                self._set_alarm(0, None)
                m = rephrase_exception_message(e)
                reason = Pool_Reason.SETUP_FAILED + f"{m}"
                set_pool_state(tables, pool_id, Pool_State.INOPERABLE, reason)
                logger.error((f"Manager (pool={pool_id})"
                              f" Initializing MinIO failed:"
                              f" exception=({m})"),
                             exc_info=True)
                raise
            pass
        pass

    def _watch_minio(self, p):
        """Watches a MinIO process.  MinIO usually outputs nothing on
        stdout/stderr, and this does a periodic work of heartbeating.
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
                    if errs != "":
                        logger.info(f"Manager (pool={pool_id}):"
                                    f" MinIO outputs: stderr=({errs})")
                        pass
                    pass
                if p.stdout in readable:
                    (outs, closed) = _read_stream(p.stdout)
                    if outs != "":
                        logger.info(f"Manager (pool={pool_id}):"
                                    f" MinIO outputs: stdout=({outs})")
                        pass
                    if closed:
                        raise Termination("MinIO closed stdout.")
                    pass

                now = int(time.time())
                if self._last_check_ts + self._watch_gap_minimal < now:
                    self._last_check_ts = now
                    self._check_pool_lifetime()
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

    def _register_minio_process(self, pid):
        self._minio_proc = {
            "minio_ep": self._minio_ep,
            "minio_pid": pid,
            "admin": self._minio_root_user,
            "password": self._minio_root_password,
            "mux_host": self._mux_host,
            "mux_port": self._mux_port,
            "manager_pid": self._manager_pid,
            "modification_time": int(time.time()),
        }
        self._tables.set_minio_proc(self._pool_id, self._minio_proc)
        self._tables.set_minio_ep(self._pool_id, self._minio_ep)
        self._check_record_expiry()
        pass

    def _check_record_expiry(self):
        # It may happen to extend expiry for other managers (ignored).
        pool_id = self._pool_id
        tables = self._tables
        ok = tables.set_manager_expiry(pool_id, self._manager_expiry)
        if not ok:
            logger.warning(f"Manager (pool={pool_id}) Setting expiry failed.")
            pass
        ma = tables.get_manager(pool_id)
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
        tables = self._tables
        inconsistent = False
        try:
            # Check for a MinIO process record.
            mn = tables.get_minio_proc(pool_id)
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
            ep = tables.get_minio_ep(pool_id)
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
                tables.delete_minio_proc(pool_id)
                pass
            if ep is not None and not inconsistent:
                tables.delete_minio_ep(pool_id)
                pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Manager (pool={pool_id})"
                         f" Removing MinIO record failed (ignored):"
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
        with self._mc.mc_alias_set(self._minio_root_user,
                                   self._minio_root_password):
            try:
                self._set_alarm(self._minio_stop_timeout, "stop-minio")
                self._mc.stop_minio()
                # p_status = p.wait()
            except Alarmed as e:
                logger.error(f"Manager (pool={pool_id})"
                             f" stopping MinIO timed out:"
                             f" exception ignored: exception=({e})")
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.error(f"Manager (pool={pool_id})"
                             f" Stopping MinIO failed:"
                             f" exception ignored: exception=({m})",
                             exc_info=True)
            finally:
                self._set_alarm(0, None)
                pass
            pass
        try:
            (outs_, errs_) = p.communicate(timeout=self._minio_stop_timeout)
            outs = str(outs_, "latin-1")
            errs = str(errs_, "latin-1")
            if errs != "":
                logger.info(f"Manager (pool={pool_id}):"
                            f" MinIO outputs: stderr=({errs})")
                pass
            if outs != "":
                logger.info(f"Manager (pool={pool_id}):"
                            f" MinIO outputs: stdout=({outs})")
                pass
        except TimeoutExpired:
            pass
        p_status = p.poll()
        if p_status is None:
            logger.warning(f"Manager (pool={pool_id}): MinIO does not stop.")
            pass
        pass

    def _check_pool_lifetime(self):
        """Checks the status and shutdown the work when inappropriate.  Some
        logging output is done at deregistering.
        """
        pool_id = self._pool_id
        tables = self._tables
        now = int(time.time())
        # Check the status of a pool.
        (state, reason) = update_pool_state(tables, pool_id)
        if not state in {Pool_State.INITIAL, Pool_State.READY}:
            raise Termination(reason)
        # Check the lifetime is expired.
        elapsed = now - self._last_access_ts
        if elapsed > self._minio_awake_duration:
            ts = tables.get_access_timestamp(pool_id)
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
                        f" Heartbeating MinIO failed:"
                        f" misses={self._heartbeat_misses}")
            raise Termination("MinIO heartbeat failure")
        pass

    def _heartbeat_minio(self):
        pool_id = self._pool_id
        url = f"http://{self._minio_ep}/minio/health/live"
        failure_message = (f"Manager (pool={pool_id})"
                           f" Heartbeating MinIO failed: urlopen error,"
                           f" url=({url});")
        try:
            res = urlopen(url, timeout=self._heartbeat_timeout)
            if self._verbose:
                logger.debug(f"Manager (pool={pool_id}) Heartbeat MinIO.")
                pass
            return res.status
        except HTTPError as e:
            logger.warning(failure_message + f" exception=({e})")
            return e.code
        except URLError as e:
            logger.warning(failure_message + f" exception=({e})")
            return 500
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
            with self._mc.mc_alias_set(self._minio_root_user,
                                       self._minio_root_password):
                self._set_alarm(self._heartbeat_timeout, "heartbeat-minio")
                rr = self._mc.get_minio_info()
                self._set_alarm(0, None)
                pass
            if self._verbose:
                logger.debug(f"Manager (pool={pool_id}) Heartbeat MinIO.")
                pass
        except Alarmed:
            raise Exception("Hearbeat timeout")
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Hearbeat failed: exception=({m})")
            self._set_alarm(0, None)
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
    parser.add_argument("--conf")
    # parser.add_argument("--useTrueAccount", type=bool, default=False,
    #                     action=argparse.BooleanOptionalAction)
    # parser.add_argument("--accessByZoneID", type=bool, default=False,
    #                     action=argparse.BooleanOptionalAction)
    parser.add_argument("--traceid")
    args = parser.parse_args()

    # pool_id = os.environ.get("LENS3_POOL_ID")
    # if pool_id is None:
    #    sys.stderr.write(f"Manager failed: No pool-ID.\n")
    #    sys.exit(ERROR_EXIT_BADCONF)
    #    pass

    assert os.environ.get("LENS3_CONF") is not None
    conf_file = os.environ.get("LENS3_CONF")
    mux_name = os.environ.get("LENS3_MUX_NAME")

    assert(conf_file == args.conf)

    pool_id = args.pool_id
    try:
        redis = read_redis_conf(conf_file)
        mux_conf = get_conf("mux", mux_name, redis)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Manager (pool={pool_id})"
                         f" Reading config file failed: exception=({m})\n")
        sys.exit(ERROR_EXIT_BADCONF)
        pass

    tracing.set(args.traceid)
    openlog(mux_conf["log_file"], **mux_conf["log_syslog"])

    try:
        pid = os.fork()
        if pid != 0:
            # (parent).
            sys.exit(0)
    except OSError as e:
        logger.error(f"Manager (pool={pool_id}) fork failed:"
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

    manager = Manager(pool_id, args, mux_conf, redis)
    ok = False
    try:
        ok = manager.manager_main()
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.error(f"Manager (pool={pool_id}) Main failed:"
                     f" exception=({m})",
                     exc_info=True)
        pass
    sys.exit(0)
    pass


if __name__ == "__main__":
    main()
