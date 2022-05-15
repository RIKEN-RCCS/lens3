"""A sentinel process for a minio process.  It is started by a
controller as a daemon (and exits immediately), and it informs the
caller about a successful start-up of a minio process by placing a
message in stdout and closing stdout/stderr.
"""

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
from lenticularis.mc import Mc
from lenticularis.readconf import read_mux_conf
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables, zone_to_route
from lenticularis.utility import ERROR_READCONF, ERROR_FORK, ERROR_START_MINIO
from lenticularis.utility import decrypt_secret, outer_join_list
from lenticularis.utility import gen_access_key_id, gen_secret_access_key
from lenticularis.utility import logger, openlog
from lenticularis.utility import make_clean_env, host_port
from lenticularis.utility import remove_trailing_shash, uniform_distribution_jitter
from lenticularis.utility import tracing


class TerminateException(Exception):
    pass


class AlarmException(Exception):
    pass


class LoopBreakException(Exception):
    pass


class NoStartRequiredException(Exception):
    pass


## Messages from a minio process at its start-up.

_minio_expected_response = b"API: "
_minio_error_response = b"ERROR"
_minio_response_port_in_use = b"Specified port is already in use"
_minio_response_unwritable_storage = b"Unable to write to the backend"
_minio_response_port_capability = b"Insufficient permissions to use specified port"


def _check_mc_status(r, e):
    if r and r[0].get("status") != "success":
        raise Exception(f"error: {e}: {r}")
    # raise Exception(f"error: {e}: mc output is empty")

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


class MinioManager():
    alarm_cause = None

    def _sigalrm(self, n, stackframe):
        logger.debug(f"@@@ raise AlarmException [{self.alarm_cause}]")
        raise AlarmException(self.alarm_cause)

    def _sigterm(self, n, stackframe):
        logger.debug("@@@ raiseException TerminateException")
        signal(SIGTERM, SIG_IGN)
        raise TerminateException()

    def _tell_controller_minio_starts(self):
        ## Note it loses stdout/stderr messages after closing.
        sys.stdout.write(f"{self._minio_ep}\n")
        sys.stdout.flush()
        sys.stdout.close()
        sys.stderr.close()

    def _finish_subprocess(self, p):
        logger.debug(f"_finish_subprocess unimplemented.")
        pass

    def _set_pool_state(self, state, reason):
        logger.debug(f"_set_pool_state unimplemented.")
        self._set_current_mode(self.zoneID, state)


    def _manager_main(self, zoneID, access_by_zoneID, args, mux_conf):

        ## Check the thread is main for using signals.
        assert threading.current_thread() == threading.main_thread()

        signal(SIGALRM, self._sigalrm)

        self.zoneID = zoneID
        use_pool_id_for_minio_root_user = args.useTrueAccount
        port_min = int(args.port_min)
        port_max = int(args.port_max)
        logger.debug(f"zoneID = {self.zoneID}")
        logger.debug(f"PORT = [{port_min}, {port_max})")
        self.muxaddr = args.muxaddr

        lenticularis_conf = mux_conf["lenticularis"]
        self.host = args.node
        logger.debug("@@@ {args.node}")

        minio_param = lenticularis_conf["minio"]
        ##self.minio_http_trace = minio_param["minio_http_trace"]
        self.minio_bin = minio_param["minio"]
        self.mc_bin = minio_param["mc"]

        controller_param = lenticularis_conf["controller"]
        self.sudo = controller_param["sudo"]
        self.watch_interval = int(controller_param["watch_interval"])
        self._lock_timeout = int(controller_param["minio_startup_timeout"])
        ## NOTE: FIXED VALUE: timeout_margin
        self.timeout_margin = 2
        self.keepalive_limit = int(controller_param["keepalive_limit"])
        self.allowed_down_count = int(controller_param["allowed_down_count"])

        self.minio_user_install_timelimit = int(controller_param["minio_user_install_timelimit"])
        self.mc_info_timelimit = int(controller_param["mc_info_timelimit"])
        self.mc_stop_timelimit = int(controller_param["mc_stop_timelimit"])
        self.kill_supervisor_wait = int(controller_param["kill_supervisor_wait"])
        self.refresh_margin = int(controller_param["refresh_margin"])

        self.tables = get_tables(mux_conf)

        zone = self.tables.storage_table.get_zone(zoneID)
        if zone is None:
            logger.error(f"Manager failed: no pool found for pool={zoneID}")
            return

        env = make_clean_env(os.environ)
        self.minioenv = env
        self.mcenv = env.copy()

        if use_pool_id_for_minio_root_user:
            self.MINIO_ROOT_USER = self.zoneID
            self.MINIO_ROOT_PASSWORD = decrypt_secret(zone["rootSecret"])
        else:
            self.MINIO_ROOT_USER = gen_access_key_id()
            self.MINIO_ROOT_PASSWORD = gen_secret_access_key()

        self.minioenv["MINIO_ROOT_USER"] = self.MINIO_ROOT_USER
        self.minioenv["MINIO_ROOT_PASSWORD"] = self.MINIO_ROOT_PASSWORD
        ##if self.minio_http_trace != "":
        ##    self.minioenv["MINIO_HTTP_TRACE"] = self.minio_http_trace
        self.minioenv["MINIO_BROWSER"] = "off"

        ## self.minioenv["MINIO_CACHE_DRIVES"] = f"/tmp/{self.zoneID}"
        ## self.minioenv["MINIO_CACHE_EXCLUDE"] = ""
        ## self.minioenv["MINIO_CACHE_QUOTA"] = "80"
        ## self.minioenv["MINIO_CACHE_AFTER"] = "3"
        ## self.minioenv["MINIO_CACHE_WATERMARK_LOW"] = "70"
        ## self.minioenv["MINIO_CACHE_WATERMARK_HIGH"] = "90"

        self.lock = LockDB(self.tables.process_table)
        lockprefix = self.tables.process_table.process_table_lock_prefix
        key = f"{lockprefix}{self.zoneID}"
        lock_status = False
        try:
            lock_status = self.lock.trylock(key, self._lock_timeout)
            if lock_status:
                self._lock_start = int(time.time())
                self._manage_minio(port_min, port_max, access_by_zoneID)
        finally:
            if lock_status:
                self.lock.unlock()
            else:
                logger.debug(f"@@@ WAIT4_UNLOCK {self.zoneID}")
                delay = 0.2  # NOTE: FIXED VALUE
                self.lock.wait4_unlock(key, delay)
        return


    def _manage_minio(self, port_min, port_max, access_by_zoneID):
        now = int(time.time())
        zone = self.tables.storage_table.get_zone(self.zoneID)
        mode = self.tables.storage_table.get_mode(self.zoneID)

        assert zone is not None

        user = zone["user"]
        group = zone["group"]
        bucketsDir = zone["bucketsDir"]
        self.expDate = int(zone["expDate"])
        online = zone["online_status"]
        permission = zone["admission_status"]
        valid = now < self.expDate

        up_minio = ((online, permission, mode, valid, access_by_zoneID)
                    == ("online", "allowed", "ready", True, False))
        logger.debug(f"@@@ up_minio = {up_minio}")

        need_initialize = (permission, mode) == ("allowed", "initial")
        logger.debug(f"@@@ need_initialize = {need_initialize}")

        minioAddress = self.tables.process_table.get_minio_address(self.zoneID)
        logger.debug(f"@@@ minioAddress = {minioAddress}")
        if minioAddress:
            # zoneID exists in the storage-table. lost the race.
            self._handle_existing_minio(up_minio, need_initialize)
            return

        if not (up_minio or need_initialize):
            # Do nothing. MinIO stay stopped.
            logger.debug("@@@ return immidiately")
            return

        assert mode == "initial" or mode == "ready"

        ports = list(range(port_min, port_max + 1))
        random.shuffle(ports)
        p = self._try_start_minio(ports, mode, user, group,
                                  bucketsDir, zone, up_minio, need_initialize)
        if p is None:
            return
        else:
            self._setup_and_watch_minio(p, mode, user, group,
                                        bucketsDir, zone, up_minio, need_initialize)
        return


    def _try_start_minio(self, ports, mode, user, group,
                          bucketsDir, zone, up_minio, need_initialize):
        p = None
        for port in ports:
            address = f":{port}"
            cmd = [self.sudo, "-u", user, "-g", group, self.minio_bin,
                   "server", "--anonymous", "--address", address, bucketsDir]
            logger.debug(f"Starting minio with: {cmd}")
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self.minioenv)
            try:
                (ok, error_is_nonfatal) = self._wait_for_minio_to_come_up(p)
                if ok:
                    host = self.host
                    self._minio_ep = host_port(host, port)
                    return p
                elif error_is_nonfatal:
                    p = None
                    continue
                else:
                    self._minio_ep = None
                    return None
            except Exception as e:
                ## (e is SubprocessError, OSError, ValueError, usually).
                logger.error(f"Starting minio failed with exception={e}")
                self._set_pool_state("inoperable", "process_failure")
                self._minio_ep = None
                return None
        assert p is None
        self._minio_ep = None
        return None


    def _wait_for_minio_to_come_up(self, p):
        """Checks a minio startup.  It assumes any subprocess outputs at least
        one line of a message or closes stdout.  Otherwise it may wait
        indefinitely.
        """

        ## It also expects that minio outputs the following lines at a
        ## successful start (to stdout):
        ## > "API: http://xx.xx.xx.xx:9000  http://127.0.0.1:9000"
        ## > "RootUser: minioadmin"
        ## > "RootPass: minioadmin"

        outs = b""
        while True:
            try:
                r = p.stdout.readline()
                outs += r
            except Exception:
                r = b""
                pass
            if r == b"":
                ## Got an eof, presumably it is an error.
                self._finish_subprocess(p)
                p_status = p.wait()
                if outs.find(_minio_error_response) != -1:
                    if outs.find(_minio_response_port_in_use) != -1:
                        logger.debug(f"Starting minio failed with"
                                     f" wait-status={p_status} outs={outs}")
                        return (False, True)
                    elif outs.find(_minio_response_unwritable_storage) != -1:
                        self._set_pool_state("inoperable", "unwritable_storage")
                        logger.debug(f"Starting minio failed with"
                                     f" wait-status={p_status} outs={outs}")
                        return (False, False)
                    else:
                        self._set_pool_state("inoperable", "process_failure")
                        logger.error(f"Starting minio failed with"
                                     f" wait-status={p_status} outs={outs}")
                        return (False, False)
                else:
                    self._set_pool_state("inoperable", "process_failure")
                    logger.error(f"Starting minio failed with"
                                 f" wait-status={p_status} outs={outs}")
                    return (False, False)
            if r.startswith(_minio_expected_response):
                logger.debug(f"Message on MinIO stdout=({outs})")
                return (True, False)


    def _setup_and_watch_minio(self, p, mode, user, group,
                               bucketsDir, zone, up_minio, need_initialize):
        assert self._minio_ep is not None

        self.mc = Mc(self.mc_bin, self.mcenv)
        with tempfile.TemporaryDirectory() as confdir:
            with self.mc.alias_set(f"http://{self._minio_ep}",
                                   self.zoneID,
                                   self.MINIO_ROOT_USER,
                                   self.MINIO_ROOT_PASSWORD,
                                   confdir):

                if need_initialize:
                    try:
                        self._setup_minio(p, zone)
                    except Exception as e:
                        self._stop_minio(p)
                        raise

                if not up_minio:
                    self._stop_minio(p)
                    self._check_elapsed_time()
                    raise NoStartRequiredException(
                                         "Starting MinIO is not required (N)")
                jitter = 0
                initial_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit

                self._record_minio_process(p.pid, zone, initial_idle_duration + self.refresh_margin)

                ## Tell the caller that a MinIO started successfully.
                self._tell_controller_minio_starts()

                self._check_elapsed_time()
                self.lock.unlock()

                self._watch_minio(p)
                ## VIRTUALLY NOT REACHED
                assert False
                return True


    def _setup_minio(self, p, zone):
        try:
            alarm(self.minio_user_install_timelimit)
            self.alarm_cause = "initialize_minio"
            try:
                a_children = self._set_access_keys(zone)
            except Exception as e:
                raise Exception(f"manager:install_minio_access_keys: {e}")
            try:
                b_children = self._set_bucket_policy(zone)
            except Exception as e:
                raise Exception(f"manager:set_bucket_policy: {e}")

            for (p, c) in (a_children + b_children):
                status = p.wait()
                #_check_mc_status(r, c)

            self._set_current_mode(self.zoneID, "ready")
            alarm(0)
            self.alarm_cause = None
        except AlarmException as e:
            logger.debug("@@@ ALARM EXCEPTION")
            # logger.exception(e)  # do not record exception detail
            e = Exception("Initialize Failed (TIMEOUT)")
            self._set_current_mode(self.zoneID, f"error: {e}")
            raise
        except Exception as e:
            alarm(0)
            self.alarm_cause = None
            logger.debug(f"@@@ EXCEPTION {e}")
            logger.error(f"minio initialization failed for {self.zoneID}: {e}")
            logger.exception(e)
            self._set_current_mode(self.zoneID, f"error: {e}")
            raise


    def _watch_minio(self, p):
        logger.debug(f"Manager for {self._minio_ep} starts watching.")

        signal(SIGTERM, self._sigterm)
        signal(SIGCHLD, SIG_IGN)

        try:
            jitter = 0
            next_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit
            self._refresh_tables(next_idle_duration + self.refresh_margin)
            down_count = 0
            while True:
                # when a signal is delivered *here*, response will delay in
                # `watch_interval + jitter` seconds.

                timeo = self.watch_interval + jitter
                (readable, _, _) = select.select(
                    [p.stdout, p.stderr], [], [], timeo)
                ##logger.debug(f"@@@ READABLE = {readable}")

                now = int(time.time())

                self._check_status()
                self._check_authoritativeness()

                if p.stderr in readable:
                    (errs, closed) = _read_stream(p.stderr)
                    logger.info(f"Message on MinIO stderr=({errs})")

                if p.stdout in readable:
                    (outs, closed) = _read_stream(p.stdout)
                    logger.info(f"Message on MinIO stdout=({outs})")
                    if closed:
                        ## MinIO is now absent.  Quit the loop.
                        raise LoopBreakException("MinIO closed it's stdout")

                if readable == []:
                    # following funcall will take upto self.mc_info_timelimit
                    try:
                        self._check_minio_health()
                        logger.info(f"set down_count to 0")
                        down_count = 0
                    except Exception as e:
                        down_count += 1
                        if down_count > self.allowed_down_count:
                            logger.info(f"down_count > {self.allowed_down_count}, raise")
                            raise
                        logger.info(f"down_count is {down_count}")

                self._check_activity(now)
                self._check_key_validity(now)

                jitter = uniform_distribution_jitter()
                next_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit
                self._refresh_tables(next_idle_duration + self.refresh_margin)

        except LoopBreakException as e:
            logger.info(f"Break Watch Loop: {e}")
            # logger.exception(e)  # do not record exception detail
            pass

        except TerminateException as e:
            logger.debug("@@@ INTERUPPTED (SIGTERM)")
            # logger.exception(e)  # do not record exception detail
            pass

        except Exception as e:
            logger.info(f"EXCEPTION {e}")
            logger.exception(e)
            pass

        self._clear_tables()
        self._stop_minio(p)

        logger.debug(f"Manager for {self._minio_ep} exits.")
        sys.exit(0)


    def _check_elapsed_time(self):
        now = int(time.time())
        elapsed_time = now - self._lock_start
        if elapsed_time + self.timeout_margin > self._lock_timeout:
            logger.warning("lock time exceeded")

    def _check_status(self):
        zone = self.tables.storage_table.get_zone(self.zoneID)
        if zone is None:
            raise LoopBreakException("Access key table erased")
        if zone["admission_status"] != "allowed":
            raise LoopBreakException("Credential disabled (psermission denied)")
        if zone["online_status"] != "online":
            raise LoopBreakException("Credential disabled (status offline)")

    def _check_authoritativeness(self):
        minioAddress = self.tables.process_table.get_minio_address(self.zoneID)
        if minioAddress is None:
            # apotosis caused by self entry disappearance
            raise LoopBreakException("Address table erased")
        if self.minioAddress[
                        "supervisorPid"] != minioAddress.get("supervisorPid"):
            # apotosis caused by self entry disappearance
            raise LoopBreakException("Another controller owns address table")

    def _check_minio_health(self):
        # FIXME: XXX USE FOLLOWING METHOD IS RECOMMENDED:
        # curl -I https://minio.example.net:9000/minio/health/live
        logger.debug("@@@ CHECK IF MINIO IS ALIVE")
        r = None
        try:
            alarm(self.mc_info_timelimit)
            self.alarm_cause = "check_minio_info"
            (p, r) = self.mc.admin_info()
            assert p is None
            ##logger.debug(f"@@@ r = {r}")
            _check_mc_status(r, "mc.admin_info")
            alarm(0)
            self.alarm_cause = None
        except AlarmException:
            raise Exception("health check timeout")
        except Exception as e:
            logger.debug(f"@@@ exception = {e}")
            logger.exception(e)
            alarm(0)
            self.alarm_cause = None
            raise
        return r

    def _check_activity(self, now):
        # check inactive time
        atime = self.tables.routing_table.get_route_expiry(self.zoneID)

        if atime is None:
            raise LoopBreakException("Keepalive_limit exceeded")

        atime = int(atime)
        elapsed_time = now - atime
        logger.debug(f"@@@ timeleft = {self.keepalive_limit - elapsed_time}")
        if elapsed_time > self.keepalive_limit:
            raise LoopBreakException("Keepalive_limit exceeded")

    def _check_key_validity(self, now):
        if now >= self.expDate:
            logger.info(f"CHECK KEY VALIDITY: Access Key Expired: {self.zoneID}")
            raise LoopBreakException("Credential expired")

    def _record_minio_process(self, pid, zone, timeout):
        timeout = math.ceil(timeout)
        self.minioAddress = {
            "muxAddr": self.muxaddr,
            "minioAddr": self._minio_ep,
            "minioPid": f"{pid}",
            "supervisorPid": f"{os.getpid()}",
        }
        logger.debug(f"@ minioAddress: {self.minioAddress}")
        self.route = zone_to_route(zone)
        logger.debug(f"@ self.route: {self.route}")
        logger.debug(f"@ timeout: {timeout}")

        atime = f"{int(time.time())}"
        self.tables.routing_table.set_route_expiry(self.zoneID, timeout)
        self.tables.storage_table.set_atime(self.zoneID, atime)
        self.saved_atime = atime

        self.tables.routing_table.set_route(self.zoneID, self._minio_ep, timeout)
        self.tables.process_table.ins_minio_address(self.zoneID, self.minioAddress, timeout)

    def _refresh_tables(self, timeout):
        timeout = math.ceil(timeout)
        self.tables.routing_table.set_route_expiry(self.zoneID, timeout)
        self.tables.process_table.set_minio_address_expire(self.zoneID, timeout)
        atime = self.tables.routing_table.get_route_expiry(self.zoneID)
        if atime and atime != self.saved_atime:
            self.tables.storage_table.set_atime(self.zoneID, atime)
            self.saved_atime = atime

    def _clear_tables(self):
        try:
            minioAddress = self.tables.process_table.get_minio_address(self.zoneID)
            if minioAddress is None:
                logger.debug("@@@ MinIO Address Not Found")
                return
            if self.minioAddress[
                        "supervisorPid"] != minioAddress.get("supervisorPid"):
                logger.debug("@@@ NOT OWN ENTRY")
                return
            self.tables.process_table.del_minio_address(self.zoneID)
            atime = self.tables.routing_table.get_route_expiry(self.zoneID)
            if atime and atime != self.saved_atime:
                logger.debug("@@@ BACKUP ATIME")
                self.tables.storage_table.set_atime(self.zoneID, atime)
            self.tables.routing_table.delete_route_expiry(self.zoneID)
            self.tables.routing_table.delete_route(self.zoneID)
        except Exception as e:
            logger.info(f"IGNORE EXCEPTION: {e}")
            logger.exception(e)
            pass


    def _set_access_keys(self, zone):
        children = []

        access_keys = zone["accessKeys"]
        (p, existing) = self.mc.admin_user_list()
        assert p is None
        _check_mc_status(existing, "mc.admin_user_list")

        (ll, pp, rr) = outer_join_list(access_keys, lambda b: b.get("accessKeyID"),
                                       existing, lambda e: e.get("accessKey"))

        logger.debug(f"Setup MinIO on access-keys:"
                     f" add={ll}, delete={rr}, update={pp}")

        for x in ll:
            children.extend(self._set_access_keys_add(x))
        for x in rr:
            children.extend(self._set_access_keys_delete(x))
        for x in pp:
            children.extend(self._set_access_keys_update(x))
        return children

    def _set_access_keys_add(self, b):
        access_key_id = b["accessKeyID"]
        secret_access_key = b["secretAccessKey"]
        policy = b["policyName"]
        (p, r) = self.mc.admin_user_add(access_key_id, decrypt_secret(secret_access_key))
        assert p is None
        _check_mc_status(r, "mc.admin_user_add")
        (p, r) = self.mc.admin_policy_set(access_key_id, policy)
        assert p is None
        _check_mc_status(r, "mc.admin_policy_set")
        return []

    def _set_access_keys_delete(self, e):
        access_key_id = e["accessKey"]
        if False:
            ## NOTE: Do not delete unregistered user here.
            (p, r) = self.mc.admin_user_disable(access_key_id, no_wait=True)
            assert r is None
            return [(p, "mc.admin_user_disable")]
        else:
            (p, r) = self.mc.admin_user_remove(access_key_id)
            assert p is None
            _check_mc_status(r, "mc.admin_user_remove")
            return []

    def _set_access_keys_update(self, x):
        (b, e) = x
        access_key_id = b["accessKeyID"]
        secret_access_key = b["secretAccessKey"]
        policy = b["policyName"]

        (p, r) = self.mc.admin_user_remove(access_key_id)
        assert p is None
        _check_mc_status(r, "mc.admin_user_remove")

        secret = decrypt_secret(secret_access_key)
        (p, r) = self.mc.admin_user_add(access_key_id, secret)
        assert p is None
        _check_mc_status(r, "mc.admin_user_add")

        (p, r) = self.mc.admin_policy_set(access_key_id, policy)
        assert p is None
        _check_mc_status(r, "mc.admin_policy_set")

        (p, r) = self.mc.admin_user_enable(access_key_id)
        assert p is None
        _check_mc_status(r, "mc.admin_user_enable")
        return []


    def _set_bucket_policy(self, zone):
        logger.debug("@@@ +++")
        logger.debug("@@@ set_bucket_policy")
        children = []

        buckets = zone["buckets"]
        (p, existing) = self.mc.list_buckets()
        assert p is None
        _check_mc_status(existing, "mc.list_buckets")

        logger.debug(f"@@@ buckets = {buckets}")
        logger.debug(f"@@@ existing = {existing}")
        (ll, pp, rr) = outer_join_list(buckets, lambda b: b.get("key"),
                                       existing, lambda e: remove_trailing_shash(e.get("key")))

        logger.debug(f"Setup MinIO on bucket-policy:"
                     f" add={ll}, delete={rr}, update={pp}")

        for x in ll:
            children.extend(self._set_bucket_policy_add(x))
        for x in rr:
            children.extend(self._set_bucket_policy_delete(x))
        for x in pp:
            children.extend(self._set_bucket_policy_update(x))
        return children

    def _set_bucket_policy_add(self, b):
        name = b["key"]
        (p, r) = self.mc.make_bucket(name)
        assert p is None
        _check_mc_status(r, "mc.make_bucket")
        policy = b["policy"]
        (p, r) = self.mc.policy_set(name, policy)
        assert p is None
        _check_mc_status(r, "mc.policy_set")
        return []

    def _set_bucket_policy_delete(self, e):
        name = remove_trailing_shash(e["key"])
        policy = "none"
        (p, r) = self.mc.policy_set(name, policy, no_wait=True)
        assert r is None
        return [(p, "mc.policy_set")]

    def _set_bucket_policy_update(self, x):
        (b, e) = x
        name = b["key"]
        policy = b["policy"]
        (p, r) = self.mc.policy_set(name, policy)
        assert p is None
        _check_mc_status(r, "mc.policy_set")
        return []


    def _stop_minio(self, p):
        logger.debug("@@@ +++")
        logger.debug("@@@ stop_minio")
        try:
            alarm(self.mc_stop_timelimit)
            self.alarm_cause = "stop_minio"
            (p, r) = self.mc.admin_service_stop()
            assert p is None
            _check_mc_status(r, "mc.admin_service_stop")
            alarm(0)
            self.alarm_cause = None
        except AlarmException as e:
            logger.info(f"IGNORE EXCEPTION (service stop): {e}")
        except Exception as e:
            alarm(0)
            self.alarm_cause = None
            logger.error(f"IGNORE EXCEPTION (service stop): {e}")
            logger.exception(e)
            # pass  # ignore any exceptions
        try:
            p_status = p.wait()
            logger.debug(f"@@@ STATUS = {p_status}")
        except Exception as e:
            logger.error(f"IGNORE EXCEPTION (wait): {e}")
            logger.exception(e)
            # pass  # ignore any exceptions
        logger.debug("@@@ EXIT")

    def _handle_existing_minio(self, up_minio, need_initialize):
        logger.debug("@@@ +++")
        if need_initialize:
            # Should not happen.
            logger.error("INTERNAL ERROR: may corrupt database.")
            logger.debug("@@@ return immidiately")
            return
        elif not up_minio:
            # Stop a running MinIO
            minioAddress = self.tables.process_table.get_minio_address(self.zoneID)
            assert minioAddress is not None
            if minioAddress["muxAddr"] != self.muxaddr:
                logger.error("INTERNAL ERROR: "
                                  "DATABASE OR SCHEDULER MAY CORRUPT. "
                                  f"{minioAddress['muxAddr']} {self.muxaddr}")
                logger.debug("@@@ return immidiately")
                return
            else:
                logger.debug("@@@ kill sup pid")
                pid = minioAddress.get("supervisorPid")
                assert pid is not None
                supervisorPid = int(pid)
                if os.getpid() != supervisorPid:
                    self._kill_manager_process(supervisorPid)
                else:
                    logger.error(f"KILL MYSELF?: {supervisorPid}")
                return
        else:
            # MinIO is running.
            logger.debug("@@@ return immidiately")
            return

    def _kill_manager_process(self, supervisorPid):
        logger.debug("@@@ +++")
        os.kill(supervisorPid, SIGTERM)
        for i in range(self.kill_supervisor_wait):
            a = self.tables.process_table.get_minio_address(self.zoneID)
            if not a:
                break
            time.sleep(1)

    def _set_current_mode(self, zoneID, mode):
        self.tables.storage_table.set_mode(zoneID, mode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("node")
    parser.add_argument("port_min")
    parser.add_argument("port_max")
    parser.add_argument("muxaddr")
    parser.add_argument("--configfile")
    parser.add_argument("--useTrueAccount", type=bool, default=False)
        #action=argparse.BooleanOptionalAction  -- was introduced in Python3.9
    parser.add_argument("--accessByZoneID", type=bool, default=False)
        #action=argparse.BooleanOptionalAction  -- was introduced in Python3.9
    parser.add_argument("--traceid")
    args = parser.parse_args()

    zoneID = os.environ.get("LENTICULARIS_ZONE_ID")
    access_by_zoneID = args.accessByZoneID

    try:
        (mux_conf, configfile) = read_mux_conf(args.configfile)
    except Exception as e:
        sys.stderr.write(f"manager:main: {e}\n")
        sys.exit(ERROR_READCONF)

    #threading.current_thread().name = args.traceid
    tracing.set(args.traceid)
    openlog(mux_conf["lenticularis"]["log_file"],
            **mux_conf["lenticularis"]["log_syslog"])

    ##logger.debug("main")
    ##logger.debug(f"traceid: {args.traceid}")
    ##logger.debug(f"zoneID: {zoneID}")
    ##logger.debug(f"port_min: {args.port_min}")
    ##logger.debug(f"port_max: {args.port_max}")
    ##logger.debug(f"muxaddr: {args.muxaddr}")
    ##logger.debug(f"useTrueAccount: {args.useTrueAccount}")
    ##logger.debug(f"accessByZoneID: {args.accessByZoneID}")
    ##logger.debug(f"env: {os.environ}")

    try:
        pid = os.fork()
        if pid != 0:
            ## parent.
            sys.exit(0)
    except OSError as e:
        logger.error(f"fork failed: {os.strerror(e.errno)}")
        sys.exit(ERROR_FORK)

    ## child.

    logger.info(f"**** Starting a manager process (pool={zoneID}). ****")

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

    manager = MinioManager()
    try:
        manager._manager_main(zoneID, access_by_zoneID, args, mux_conf)
    except NoStartRequiredException as e:
        logger.debug(f"{zoneID} NoStartRequiredException: {e}")
        # logger.exception(e)  # do not record exception detail
        pass
    except Exception as e:
        logger.error(f"{zoneID} Exception: {e}")
        logger.exception(e)

    ## (Never here normally).
    sys.exit(ERROR_START_MINIO)


if __name__ == "__main__":
    main()
