"""MinIO control.  It runs the mc command to set-up MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import json
from subprocess import Popen, PIPE
from lenticularis.utility import logger
from lenticularis.utility import random_str


class Mc():
    def __init__(self, mc, env):
        self.mc = mc
        self.env = env

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        self.alias_remove()


    def alias_set(self, url, zoneID, minioRootUser, minioRootSecret, confdir):
        logger.debug("@@@ ALIAS SET")
        logger.debug(f"@@@ ALIAS SET {minioRootUser}")
        logger.debug(f"@@@ ALIAS SET {minioRootSecret}")
        #tmpdir = "/tmp"
        if len(zoneID) > 0:
            sortkey = f"{ord(zoneID[0]):02x}"
        else:
            sortkey = "00"
        self._alias = f"{zoneID}{random_str(12).lower()}"
        #self._config_dir = f"{tmpdir}/.mc/{sortkey}/{self._alias}"
        self._config_dir = confdir
        logger.debug(f"@@@ CONFDIR: {self._config_dir}, ALIAS: {self._alias}")
        (p, r) = self._execute_cmd(False, "alias", "set", self._alias, url,
                                   minioRootUser, minioRootSecret, "--api", "S3v4")
        assert p is None
        if r[0]["status"] != "success":
            self._alias = None
            self._config_dir = None
            raise Exception(r[0]["error"]["message"])
        return self

    def alias_remove(self):
        (p, r) = self._execute_cmd(False, "alias", "remove", self._alias)
        assert p is None
        self._alias = None
        if r[0]["status"] != "success":
            raise Exception(r[0]["error"]["message"])

    def admin_info(self):
        logger.debug("@@@ ADMIN INFO")
        return self._execute_cmd(False, "admin", "info", self._alias)

    def admin_policy_set(self, access_key_id, policy):
        logger.debug("@@@ SET USER POLICY")
        return self._execute_cmd(False, "admin", "policy", "set", self._alias,
                                policy, f"user={access_key_id}")

    def admin_service_stop(self):
        logger.debug("@@@ ADMIN STOP MINIO")
        return self._execute_cmd(False, "admin", "service", "stop", self._alias)

    def admin_user_add(self, access_key_id, secret_access_key):
        logger.debug("@@@ ADMIN USER ADD")
        return self._execute_cmd(False, "admin", "user", "add", self._alias,
                                access_key_id, secret_access_key)

    def admin_user_disable(self, access_key_id, no_wait=False):
        logger.debug("@@@ ADMIN USER DISABLE")
        return self._execute_cmd(no_wait, "admin", "user", "disable", self._alias,
                                access_key_id)

    def admin_user_enable(self, access_key_id):
        logger.debug("@@@ ADMIN USER ENABLE")
        return self._execute_cmd(False, "admin", "user", "enable", self._alias,
                                access_key_id)

    def admin_user_list(self):
        logger.debug("@@@ ADMIN USER LIST")
        return self._execute_cmd(False, "admin", "user", "list", self._alias)

    def admin_user_remove(self, access_key_id):
        logger.debug("@@@ ADMIN USER REMOVE")
        return self._execute_cmd(False, "admin", "user", "remove", self._alias,
                                access_key_id)

    def list_buckets(self):
        logger.debug("@@@ LIST BUCKETS")
        return self._execute_cmd(False, "ls", f"{self._alias}")

    def make_bucket(self, bucket):
        logger.debug("@@@ MAKE BUCKET")
        return self._execute_cmd(False, "mb", f"{self._alias}/{bucket}")

    def policy_set(self, bucket, policy, no_wait=False):
        logger.debug("@@@ POLICY SET")
        return self._execute_cmd(no_wait, "policy", "set", policy,
                                f"{self._alias}/{bucket}")


    def _make_mc_error_list(self, message):
        ee = [{"status": "error", "error": {"message": message}}]
        logger.debug(f"@@@ ERROR: {ee}")
        return ee

    def _mc_reduce_error_message(self, ee):
        for e in ee:
            if e.get("status") != "success":
                m = e.get("error")
                if m is None:
                    logger.debug("@@@ UNKNOWN ERROR 1")
                    return self._make_mc_error_list("Unknown error")
                message = m.get("message")
                if message is None:
                    logger.debug("@@@ UNKNOWN ERROR 2")
                    return self._make_mc_error_list("Unknown error")
                logger.debug(f"@@@ COMMAND ERROR {e}")
                return [e]
        ##logger.debug(f"@@@ SUCCESS: {ee}")
        return ee

    def _execute_cmd(self, no_wait, *args):
        if self._alias is None or self._config_dir is None:
            raise Exception("mc command called without setting an alias.")
        cmd = [self.mc, "--json", f"--config-dir={self._config_dir}"] + list(args)
        ##logger.debug(f"@@@ CMD {cmd} ({no_wait})")

        if no_wait:
            logger.debug(f"@@@ no wait!")
            p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=self.env)
            #status = unwait(cmd, self.env)
            #if status != 0:
            #    logger.error(f"unwait exited with non-zero status: {status}")
            #    return [{"status": "error", "casuse": "unwait failed", "exit_code": f"{status}"}]
            #return [{"status": "success"}]
            return (p, None)

        try:
            logger.debug(f"@@@ Popen({cmd})")
            with Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                       env=self.env) as p:
                (outs, errs) = p.communicate()
                status = p.wait()
                logger.debug(f"Run mc command: cmd={cmd}; status={status}, outs=({outs}), errs=({errs})")
                try:
                    s = outs.split(b'\n')
                    j = [json.loads(e, parse_int=None) for e in s if e != b""]
                    r = self._mc_reduce_error_message(j)
                    return (None, r)
                except Exception as e:
                    logger.debug(f"@@@ EXCEPTION: {e}")
                    logger.exception(e)
                    r = self._make_mc_error_list(f"{e}")
                    return (None, r)
                # NOTREACHED
        except Exception as e:
            logger.debug(f"@@@ EXCEPTION: {e}")
            logger.exception(e)  # [, AlarmException]
            r = self._make_mc_error_list(f"{e}")
            return (None, r)


## UNSED -- FOR FUTURE DEVELOPER --
## THIS CODE IS USED TO EXECUTE MC, WITHOUT WAITING FOR FINISHING
## EXECUTION. MANAGER DOES NOT RECEIVE FINISH STATUS FROM MC AND
## ASK INIT PROCESS TO WAIT ZOMBIE PROCESS OF MC.
#def unwait(cmd, env):
#    try:
#        pid = os.fork()
#        if pid != 0:
#            (pid, status) = os.waitpid(pid, 0)
#            return status
#    except OSError as e:
#        logger.error(f"fork: {os.strerror(e.errno)}")
#        logger.exception(e)
#        return ERROR_FORK
#
#    try:
#        pid = os.fork()
#        if pid != 0:
#            sys.exit(0)
#    except OSError as e:
#        logger.error(f"fork: {os.strerror(e.errno)}")
#        logger.exception(e)
#        sys.exit(ERROR_FORK)
#
#    try:
#        with Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env) as p:
#            (out, err) = p.communicate()
#            status = p.wait()
#            logger.debug(f"status: {status} out: {out} err: {err}")
#    finally:
#        sys.exit(0)
