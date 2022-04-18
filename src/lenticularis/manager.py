"""A sentinel of a MinIO instance."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import math
import os
import platform
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
from subprocess import Popen, PIPE
import random
import select
import sys
import tempfile
#import threading
import time
from lenticularis.mc import Mc
from lenticularis.readconf import read_mux_conf
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables, zone_to_route
from lenticularis.utility import ERROR_READCONF, ERROR_FORK, ERROR_START_MINIO
from lenticularis.utility import decrypt_secret, outer_join
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
    logger.info("***** START MANAGER *****")

    logger.debug("main")
    logger.debug(f"traceid: {args.traceid}")
    logger.debug(f"zoneID: {zoneID}")
    logger.debug(f"port_min: {args.port_min}")
    logger.debug(f"port_max: {args.port_max}")
    logger.debug(f"muxaddr: {args.muxaddr}")
    logger.debug(f"useTrueAccount: {args.useTrueAccount}")
    logger.debug(f"accessByZoneID: {args.accessByZoneID}")
    #logger.debug(f"env: {os.environ}")

    try:
        pid = os.fork()
        if pid != 0:
            # parent
            sys.exit(0)
    except OSError as e:
        logger.error(f"fork: {os.strerror(e.errno)}")
        logger.exception(e)
        sys.exit(ERROR_FORK)

    # child
    try:
        os.setsid()
    except OSError as e:
        logger.error(f"setsid: {os.strerror(e.errno)}")
        logger.exception(e)
        pass  # ignore any exception

    try:
        os.umask(0o077)
    except OSError as e:
        logger.error(f"umask: {os.strerror(e.errno)}")
        logger.exception(e)
        pass  # ignore any exception

    manager = MinioManager()
    try:
        manager.manager_main(zoneID, access_by_zoneID, args, mux_conf)
    except NoStartRequiredException as e:
        logger.debug(f"{zoneID} NoStartRequiredException: {e}")
        # logger.exception(e)  # do not record exception detail
        pass
    except Exception as e:
        logger.error(f"{zoneID} Exception: {e}")
        logger.exception(e)
        sys.exit(ERROR_START_MINIO)

    sys.exit(0)


class MinioManager():
    process_table_lock_pfx = "lk:"
    alarm_cause = None

    def _sigalrm(n, stackframe):
            logger.debug(f"@@@ raise AlarmException [{self.alarm_cause}]")
            raise AlarmException(self.alarm_cause)

    def manager_main(self, zoneID, access_by_zoneID, args, mux_conf):
        logger.debug("@@@ +++")

        signal(SIGALRM, self._sigalrm)

        self.zoneID = zoneID
        use_zone_id_as_minio_root_user = args.useTrueAccount
        port_min = int(args.port_min)
        port_max = int(args.port_max)
        logger.debug(f"zoneID = {self.zoneID}")
        logger.debug(f"PORT = [{port_min}, {port_max})")
        self.muxaddr = args.muxaddr

        lenticularis_conf = mux_conf["lenticularis"]
        self.host = args.node
        logger.debug("@@@ {args.node}")

        minio_param = lenticularis_conf["minio"]
        self.minio_bin = minio_param["minio"]
        self.minio_http_trace = minio_param["minio_http_trace"]
        self.mc_bin = minio_param["mc"]

        controller_param = lenticularis_conf["controller"]
        self.sudo = controller_param["sudo"]
        self.watch_interval = int(controller_param["watch_interval"])
        self.timeout = int(controller_param["max_lock_duration"])
        self.timeout_margin = 2  # NOTE: FIXED VALUE
        self.keepalive_limit = int(controller_param["keepalive_limit"])
        self.allowed_down_count = int(controller_param["allowed_down_count"])

        self.minio_user_install_timelimit = int(controller_param["minio_user_install_timelimit"])
        self.mc_info_timelimit = int(controller_param["mc_info_timelimit"])
        self.mc_stop_timelimit = int(controller_param["mc_stop_timelimit"])
        self.kill_supervisor_wait = int(controller_param["kill_supervisor_wait"])
        self.refresh_margin = int(controller_param["refresh_margin"])

        self.tables = get_tables(mux_conf)

        env = make_clean_env(os.environ)
        self.minioenv = env
        self.mcenv = env.copy()

        if use_zone_id_as_minio_root_user:
            self.MINIO_ROOT_USER = self.zoneID
            self.MINIO_ROOT_PASSWORD = decrypt_secret(self.entry["rootSecret"])
        else:
            self.MINIO_ROOT_USER = gen_access_key_id()
            self.MINIO_ROOT_PASSWORD = gen_secret_access_key()

        self.minioenv["MINIO_ROOT_USER"] = self.MINIO_ROOT_USER
        self.minioenv["MINIO_ROOT_PASSWORD"] = self.MINIO_ROOT_PASSWORD
        if self.minio_http_trace != "":
            self.minioenv["MINIO_HTTP_TRACE"] = self.minio_http_trace
        self.minioenv["MINIO_BROWSER"] = "off"

#        self.minioenv["MINIO_CACHE_DRIVES"] = f"/tmp/{self.zoneID}"
#        self.minioenv["MINIO_CACHE_EXCLUDE"] = ""
#        self.minioenv["MINIO_CACHE_QUOTA"] = "80"
#        self.minioenv["MINIO_CACHE_AFTER"] = "3"
#        self.minioenv["MINIO_CACHE_WATERMARK_LOW"] = "70"
#        self.minioenv["MINIO_CACHE_WATERMARK_HIGH"] = "90"

### XXX can we move following block to controller.py?
        self.lock = LockDB(self.tables.processes)
        key = f"{self.process_table_lock_pfx}{self.zoneID}"
        lock_status = False
        try:
            lock_status = self.lock.trylock(key, self.timeout)
            if lock_status:
                self.locked_time = int(time.time())
                logger.debug(f"@@@ LOCK SUCCEEDED: {self.zoneID}")
                self.manage_minio(port_min, port_max, access_by_zoneID)
        finally:
            if lock_status:
                logger.debug(f"@@@ UNLOCK {self.zoneID}")
                self.lock.unlock()  # don't mind that unlock may be called in manage_minio.
            else:
                logger.debug(f"@@@ WAIT4_UNLOCK {self.zoneID}")
                delay = 0.2  # NOTE: FIXED VALUE
                self.lock.wait4_unlock(key, delay)

    def manage_minio(self, port_min, port_max, access_by_zoneID):
        logger.debug(f"@@@ {self.zoneID}")
        now = int(time.time())
        zone = self.tables.zones.get_zone(self.zoneID)
        mode = self.tables.zones.get_mode(self.zoneID)

        user = zone["user"]
        group = zone["group"]
        bucketsDir = zone["bucketsDir"]
        self.expDate = int(zone["expDate"])
        status = zone["status"]
        permission = zone["permission"]
        valid = now < self.expDate

        logger.debug(f"@@@ zoneID = {self.zoneID}")
        logger.debug(f"@@@ zone = {zone}")
        logger.debug(f"@@@ mode = {mode}")
        logger.debug(f"@@@ status = {status}")
        logger.debug(f"@@@ permission = {permission}")
        logger.debug(f"@@@ expDate = {self.expDate} "
                          f"now = {now} timeleft = {self.expDate - now} valid = {valid}")

        logger.debug(f"@@@ access_by_zoneID = {access_by_zoneID}")

        up_minio = (status, permission, mode, valid, access_by_zoneID
                    ) == ("online", "allowed", "ready", True, False)
        logger.debug(f"@@@ up_minio = {up_minio}")

        need_initialize = (permission, mode) == ("allowed", "initial")
        logger.debug(f"@@@ need_initialize = {need_initialize}")

        minioAddress = self.tables.processes.get_minio_address(self.zoneID)
        logger.debug(f"@@@ minioAddress = {minioAddress}")
        if minioAddress:
            # zoneID exists in storage zone table (zones). lost the race.
            self.handle_running_minio(up_minio, need_initialize)
            return

        if not (up_minio or need_initialize):
            # Do nothing. MinIO stay stopped.
            logger.debug("@@@ return immidiately")
            return

        logger.debug("@@@ 4")

        ports = list(range(port_min, port_max + 1))
        random.shuffle(ports)

        for port in ports:
            if self.try_manage_minio(port, mode, user, group,
                                        bucketsDir, zone, up_minio, need_initialize):
                break
        # VIRTUALLY NOT REACHED

    def _check_elapsed_time(self):
            now = int(time.time())
            elapsed_time = now - self.locked_time
            if elapsed_time + self.timeout_margin > self.timeout:
                logger.warning("lock time exceeded")


    def try_manage_minio(self, port, mode, user, group,
                        bucketsDir, zone, up_minio, need_initialize):
        address = f":{port}"
        cmd = [self.sudo, "-u", user, "-g", group, self.minio_bin,
               "server", "--anonymous", "--address", address, bucketsDir]
        logger.debug(f"starting minio with: {cmd}")
        with Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                   env=self.minioenv) as p:
            try:
                if not self.wait_for_minio_to_come_up(p):
                    return False
            except Exception as e:
                self.set_current_mode(self.zoneID, f"error: {e}")
                raise

            host = self.host
            self.minioAddr = host_port(host, port)

            self.mc = Mc(self.mc_bin, self.mcenv)
            with tempfile.TemporaryDirectory() as confdir:
                with self.mc.alias_set(f"http://{self.minioAddr}",
                                       self.zoneID,
                                       self.MINIO_ROOT_USER,
                                       self.MINIO_ROOT_PASSWORD,
                                       confdir):

                    if need_initialize:
                        try:
                            self.initialize_minio(p, zone)
                        except Exception as e:
                            self.stop_minio(p)
                            raise

                    if not up_minio:
                        self.stop_minio(p)
                        self._check_elapsed_time()
                        raise NoStartRequiredException(
                                             "Starting MinIO is not required (N)")
                    jitter = 0
                    initial_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit

                    self.update_tables(p.pid, zone, initial_idle_duration + self.refresh_margin)

                    # Tell caller that MinIO started successfully.
                    sys.stdout.write(f"{self.minioAddr}\n")
                    sys.stdout.flush()
                    sys.stdout.close()

                    self._check_elapsed_time()
                    logger.debug(f"@@@ UNLOCK {self.zoneID}")
                    self.lock.unlock()  # unlock here. don't mind that unlock will called twice.
                    self.watch_minio(p)

                    # VIRTUALLY NOT REACHED
                    logger.error("SHOULD NOT HAPPEN")
                    return True

    def wait_for_minio_to_come_up(self, p):
        errs_port = b"Specified port is already in use"
        errs_perm = b"Insufficient permissions to use specified port"
        errs_priv = b"Unable to write to the backend"
        expected_response = b"API: "
        outs = b""
        while True:
            try:
                r = p.stdout.readline()
                logger.debug(f"@ r = {r}")
                outs += r
            except Exception:
                pass  # ignore any exceptions
            if r == b"":
                logger.debug("@ FAIL")
                p_status = p.wait()
                logger.debug(f"@ p_status = {p_status}")
                logger.debug(f"@ outs = {outs}")

                logger.debug(f"@ error_end = {outs.find(b'ERROR')}")
                if outs.find(b"ERROR") != -1:
                    if outs.find(errs_port) != -1:
                        logger.debug(f"@ {errs_port}")
                        return False
                    elif outs.find(errs_perm) != -1:
                        logger.debug("@ raise Exception")
                        raise Exception(f"ERROR: {errs_perm}")
                    elif outs.find(errs_priv) != -1:
                        logger.debug("@ raise Exception")
                        raise Exception(f"ERROR: {errs_priv}")

                return False
            if r.startswith(expected_response):
                urls = r.decode().split()[1:]
                logger.debug("@ SUCCESS")
                return True

    def _check_status(self):
            zone = self.tables.zones.get_zone(self.zoneID)
            if zone is None:
                raise LoopBreakException("Access key table erased")
            if zone["permission"] != "allowed":
                raise LoopBreakException("Credential disabled (psermission denied)")
            if zone["status"] != "online":
                raise LoopBreakException("Credential disabled (status offline)")

    def _check_authoritativeness(self):
            minioAddress = self.tables.processes.get_minio_address(self.zoneID)
            if minioAddress is None:
                # apotosis caused by self entry disappearance
                raise LoopBreakException("Address table erased")
            if self.minioAddress[
                            "supervisorPid"] != minioAddress.get("supervisorPid"):
                # apotosis caused by self entry disappearance
                raise LoopBreakException("Another controller owns address table")

    def _check_stdout(self, stdout_d):
            # do not gurad with try. let read raise exception.
            r = os.read(stdout_d, 512)
            if r == b"":                              # stdout closed.
                # MinIO is now absent. quit the loop.
                raise LoopBreakException("MinIO closed it's stdout")
            logger.debug(f"@@@ {r}")

    def _check_stderr(self, stderr_d):
            # do not guard with try. let read raise exception.
            r = os.read(stderr_d, 512)
            logger.debug(f"@@@ {r}")

    def _check_minio_info(self):
            # FIXME: XXX USE FOLLOWING METHOD IS RECOMMENDED:
            # curl -I https://minio.example.net:9000/minio/health/live
            logger.debug("@@@ CHECK IF MINIO IS ALIVE")
            r = None
            try:
                alarm(self.mc_info_timelimit)
                self.alarm_cause = "check_minio_info"
                r = self.mc.admin_info()
                logger.debug(f"@@@ r = {r}")
                check_mc_status(r, "mc.admin_info")
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
            atime = self.tables.routes.get_atime_by_addr(self.minioAddr)

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

    def _sigterm(n, stackframe):
            logger.debug("@@@ raiseException TerminateException")
            signal(SIGTERM, SIG_IGN)
            raise TerminateException()

    def watch_minio(self, p):
        # watch_minio body

        signal(SIGTERM, self._sigterm)
        signal(SIGCHLD, SIG_IGN)

        stdout_d = p.stdout.fileno()
        stderr_d = p.stderr.fileno()

        try:
            jitter = 0
            next_idle_duration = self.watch_interval + jitter + self.mc_info_timelimit
            self.refresh_tables(next_idle_duration + self.refresh_margin)
            down_count = 0
            while True:
                readfds = [stdout_d, stderr_d]

                # when a signal is delivered *here*, response will delay in
                # `watch_interval + jitter` seconds.

                readable, _, _ = select.select(
                                readfds, [], [], self.watch_interval + jitter)
                logger.debug(f"@@@ READABLE = {readable}")

                now = int(time.time())

                self._check_status()
                self._check_authoritativeness()

                if stdout_d in readable:
                    self._check_stdout(stdout_d)

                if stderr_d in readable:
                    self._check_stderr(stderr_d)

                if readable == []:
                    # following funcall will take upto self.mc_info_timelimit
                    try:
                        self._check_minio_info()
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
                self.refresh_tables(next_idle_duration + self.refresh_margin)

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

        self.clear_tables()
        self.stop_minio(p)
        logger.debug("@@@ exit")
        sys.exit(0)

        # NOT REACHED

    def update_tables(self, pid, zone, timeout):
        timeout = math.ceil(timeout)
        self.minioAddress = {
            "muxAddr": self.muxaddr,
            "minioAddr": self.minioAddr,
            "minioPid": f"{pid}",
            "supervisorPid": f"{os.getpid()}",
        }
        logger.debug(f"@ minioAddress: {self.minioAddress}")
        self.route = zone_to_route(zone)
        logger.debug(f"@ self.route: {self.route}")
        logger.debug(f"@ timeout: {timeout}")

        atime = f"{int(time.time())}"
        self.tables.routes.set_atime_by_addr(self.minioAddr, atime, timeout)
        self.tables.zones.set_atime(self.zoneID, atime)
        self.saved_atime = atime

        logger.debug(f"@@@ INSERT ROUTE: {self.minioAddress} {self.route}")
        self.tables.routes.ins_route(self.minioAddr, self.route, timeout)
        logger.debug(f"@@@ INSERT MINIO ADDRESS: {self.minioAddress}")
        self.tables.processes.ins_minio_address(self.zoneID, self.minioAddress, timeout)

    def refresh_tables(self, timeout):
        timeout = math.ceil(timeout)
        logger.debug(f"@@@ SET EXPIRE: minioAddress = {self.minioAddress}")
        logger.debug(f"@@@ SET EXPIRE: timeout = {timeout}")
        self.tables.routes.set_atime_expire(self.minioAddr, timeout)
        self.tables.routes.set_route_expire(self.route, timeout)
        self.tables.processes.set_minio_address_expire(self.zoneID, timeout)
        atime = self.tables.routes.get_atime_by_addr(self.minioAddr)
        if atime and atime != self.saved_atime:
            self.tables.zones.set_atime(self.zoneID, atime)
            self.saved_atime = atime

    def clear_tables(self):
        logger.debug("@@@ CLEAR TABLES")
        try:
            minioAddress = self.tables.processes.get_minio_address(self.zoneID)
            if minioAddress is None:
                logger.debug("@@@ MinIO Address Not Found")
                return
            if self.minioAddress[
                        "supervisorPid"] != minioAddress.get("supervisorPid"):
                logger.debug("@@@ NOT OWN ENTRY")
                return
            logger.debug(f"@@@ DELETE MINIO ADDRESS {self.minioAddress}")
            self.tables.processes.del_minio_address(self.zoneID)
            logger.debug("@@@ DELETE ROUTING TABLE")
            atime = self.tables.routes.get_atime_by_addr(self.minioAddr)
            if atime and atime != self.saved_atime:
                logger.debug("@@@ BACKUP ATIME")
                self.tables.zones.set_atime(self.zoneID, atime)
            logger.debug("@@@ DELETE ATIME")
            self.tables.routes.del_atime_by_addr(self.minioAddr)
            logger.debug("@@@ DELETE ROUTE")
            self.tables.routes.del_route(self.route)
            logger.debug("@@@ DONE")
        except Exception as e:
            logger.info(f"IGNORE EXCEPTION: {e}")
            logger.exception(e)
            pass

    def initialize_minio(self, p, zone):
        logger.debug("@@@ +++")
        logger.debug("@@@ manager:initialize_minio")
        try:
            alarm(self.minio_user_install_timelimit)
            self.alarm_cause = "initialize_minio"
            try:
                a_children = self.install_minio_access_keys(zone)
            except Exception as e:
                raise Exception(f"manager:install_minio_access_keys: {e}")
            try:
                b_children = self.set_bucket_policy(zone)
            except Exception as e:
                raise Exception(f"manager:set_bucket_policy: {e}")
            logger.debug("@@@ INITIALIZE DONE")

            for (p, c) in a_children + b_children:
                status = p.wait()
                logger.debug(f"@@@ {p} {c} {status}")
                #check_mc_status(r, c)

            self.set_current_mode(self.zoneID, "ready")
            alarm(0)
            self.alarm_cause = None
        except AlarmException as e:
            logger.debug("@@@ ALARM EXCEPTION")
            # logger.exception(e)  # do not record exception detail
            e = Exception("Initialize Failed (TIMEOUT)")
            self.set_current_mode(self.zoneID, f"error: {e}")
            raise
        except Exception as e:
            alarm(0)
            self.alarm_cause = None
            logger.debug(f"@@@ EXCEPTION {e}")
            logger.error(f"minio initialization failed for {self.zoneID}: {e}")
            logger.exception(e)
            self.set_current_mode(self.zoneID, f"error: {e}")
            raise


    def _install_minio_access_keys_body(self, b, e):
            logger.debug("@@@ install_minio_access_keys_body")
            if e is None:  # New Entry
                access_key_id = b["accessKeyID"]
                secret_access_key = b["secretAccessKey"]
                policy = b["policyName"]
                logger.debug(f"@@@ CREATE USER: {access_key_id}")
                r = self.mc.admin_user_add(access_key_id, decrypt_secret(secret_access_key))
                check_mc_status(r, "mc.admin_user_add")

                logger.debug(f"@@@ SET_USER_POLICY {access_key_id} {policy}")
                r = self.mc.admin_policy_set(access_key_id, policy)
                check_mc_status(r, "mc.admin_policy_set")

            elif b is None:  # Deleted Entry
                access_key_id = e["accessKey"]

                logger.debug(f"@@@ DISABLE_USER {access_key_id}")
                # NOTE: we do dot delete unregistered user here.
                # r = self.mc.admin_user_remove(access_key_id, no_wait=True)
                # check_mc_statusXXX(r, "mc.admin_user_remove")
                p = self.mc.admin_user_disable(access_key_id, no_wait=True)
                children.append((p, "mc.admin_user_disable"))
                #check_mc_status(r, "mc.admin_user_disable")

            else:  # Updated Entry
                access_key_id = b["accessKeyID"]
                secret_access_key = b["secretAccessKey"]
                policy = b["policyName"]

                logger.debug(f"@@@ REMOVE USER: {access_key_id}")
                r = self.mc.admin_user_remove(access_key_id)
                check_mc_status(r, "mc.admin_user_remove")

                logger.debug(f"@@@ CREATE USER: {access_key_id}")
                r = self.mc.admin_user_add(access_key_id, decrypt_secret(secret_access_key))
                check_mc_status(r, "mc.admin_user_add")

                logger.debug(f"@@@ SET_USER_POLICY {access_key_id} {policy}")
                r = self.mc.admin_policy_set(access_key_id, policy)
                check_mc_status(r, "mc.admin_policy_set")

                logger.debug(f"@@@ ENABLE_USER {access_key_id}")
                r = self.mc.admin_user_enable(access_key_id)
                check_mc_status(r, "mc.admin_user_enable")

    def install_minio_access_keys(self, zone):
        logger.debug("@@@ +++")
        logger.debug("@@@ install_minio_access_keys")
        children = []

        access_keys = zone["accessKeys"]
        existing = self.mc.admin_user_list()
        check_mc_status(existing, "mc.admin_user_list")

        logger.debug(f"@@@ access_keys = {access_keys}")
        logger.debug(f"@@@ existing = {existing}")
        outer_join(access_keys, lambda b: b.get("accessKeyID"),
                   existing, lambda e: e.get("accessKey"),
                   self._install_minio_access_keys_body)

        return children

    def _set_bucket_policy_body(self, b, e):
            logger.debug(f"@@@ set_bucket_policy_body: {b} {e}")
            if e is None:  # New Entry
                name = b["key"]
                logger.debug(f"@@@ MAKE BUCKET: {name}")
                r = self.mc.make_bucket(name)
                check_mc_status(r, "mc.make_bucket")
                policy = b["policy"]
                logger.debug(f"@@@ SET_BUCKET_POLICY {name} {policy}")
                r = self.mc.policy_set(name, policy)
                check_mc_status(r, "mc.policy_set")
            elif b is None:  # Deleted Entry
                logger.debug(f"@@@ ONLY IN E: {e}")
                name = remove_trailing_shash(e["key"])
                policy = "none"
                logger.debug(f"@@@ SET_BUCKET_POLICY {name} {policy}")
                p = self.mc.policy_set(name, policy, no_wait=True)
                children.append((p, "mc.policy_set"))
            else:  # Updated Entry
                logger.debug(f"@@@ BOTH: {b} {e}")
                name = b["key"]
                policy = b["policy"]
                logger.debug(f"@@@ SET_BUCKET_POLICY {name} {policy}")
                r = self.mc.policy_set(name, policy)
                check_mc_status(r, "mc.policy_set")

    def set_bucket_policy(self, zone):
        logger.debug("@@@ +++")
        logger.debug("@@@ set_bucket_policy")
        children = []

        buckets = zone["buckets"]
        existing = self.mc.list_buckets()
        check_mc_status(existing, "mc.list_buckets")

        logger.debug(f"@@@ buckets = {buckets}")
        logger.debug(f"@@@ existing = {existing}")
        outer_join(buckets, lambda b: b.get("key"),
                   existing, lambda e: remove_trailing_shash(e.get("key")),
                   self._set_bucket_policy_body)
        return children

    def stop_minio(self, p):
        logger.debug("@@@ +++")
        logger.debug("@@@ stop_minio")
        try:
            alarm(self.mc_stop_timelimit)
            self.alarm_cause = "stop_minio"
            r = self.mc.admin_service_stop()
            check_mc_status(r, "mc.admin_service_stop")
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

    def handle_running_minio(self, up_minio, need_initialize):
        logger.debug("@@@ +++")
        if need_initialize:
            # Should not happen.
            logger.error("INTERNAL ERROR: may corrupt database.")
            logger.debug("@@@ return immidiately")
            return
        elif not up_minio:
            # Stop a running MinIO
            minioAddress = self.tables.processes.get_minio_address(self.zoneID)
            if minioAddress["muxAddr"] != self.muxaddr:
                logger.error("INTERNAL ERROR: "
                                  "DATABASE OR SCHEDULER MAY CORRUPT. "
                                  f"{minioAddress['muxAddr']} {self.muxaddr}")
                logger.debug("@@@ return immidiately")
                return
            else:
                logger.debug("@@@ kill sup pid")
                supervisorPid = int(minioAddress.get("supervisorPid"))
                if os.getpid() != supervisorPid:
                    self.kill_supervisor(supervisorPid)
                else:
                    logger.error(f"KILL MYSELF?: {supervisorPid}")
                return
        else:
            # MinIO is running.
            logger.debug("@@@ return immidiately")
            return

    def kill_supervisor(self, supervisorPid):
        logger.debug("@@@ +++")
        os.kill(supervisorPid, SIGTERM)
        for i in range(self.kill_supervisor_wait):
            a = self.tables.processes.get_minio_address(self.zoneID)
            if not a:
                break
            time.sleep(1)

    def set_current_mode(self, zoneID, mode):
        self.tables.zones.set_mode(zoneID, mode)


def check_mc_status(r, e):
    if r and r[0].get("status") != "success":
        raise Exception(f"error: {e}: {r}")
    # raise Exception(f"error: {e}: mc output is empty")


if __name__ == "__main__":
    main()
