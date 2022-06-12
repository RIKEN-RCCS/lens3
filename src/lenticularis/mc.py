"""MinIO MC control.  It runs MC command to set-up MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# NOTE: The error cause-code "BucketAlreadyOwnedByYou" returned MC
# command should be treated as not an error.

import tempfile
import json
from subprocess import Popen, DEVNULL, PIPE
from lenticularis.poolutil import Api_Error
from lenticularis.utility import remove_trailing_slash
from lenticularis.utility import list_diff3
from lenticularis.utility import logger
from lenticularis.utility import random_str

# MinIO MC command returns a json with keys that are specific to each
# command.  Some keys shall be recognized in Lens3 and are mapped.

_mc_user_info_json_keys = {
    # See the type userMessage in (mc/cmd/admin-user-add.go).
    "status": "status",
    "accessKey": "access_key",
    "secretKey": "secret_key",
    "policyName": "key_policy",
    "userStatus": "userStatus",
    "memberOf": "memberOf"}

_mc_list_entry_json_keys = {
    # See the type contentMessage in (mc/cmd/ls.go).  "key" is a
    # bucket/file name.  It has a tailing slash for a bucket.
    "status": "status",
    "type": "type",
    "lastModified": "lastModified",
    "size": "size",
    "key": "name",
    "etag": "etag",
    "url": "url",
    "versionId": "versionId",
    "versionOrdinal": "versionOrdinal",
    "versionIndex": "versionIndex",
    "isDeleteMarker": "isDeleteMarker",
    "storageClass": "storageClass"}


def intern_mc_user_info(json):
    """Maps key strings returned from MC to ones in Lens3."""
    mapping = _mc_user_info_json_keys
    return {mapping.get(k, k): v for (k, v) in json.items()}


def intern_mc_list_entry(json):
    """Maps key strings returned from MC to ones in Lens3.  It also drops
    a trailing slash in a bucket name."""
    mapping = _mc_list_entry_json_keys
    return {mapping.get(k, k): (remove_trailing_slash(v) if k == "key" else v)
            for (k, v) in json.items()}


def assert_mc_success(rr, op):
    """Checks MC command is successful.  It accepts an empty list, because
    MC-ls command may return an empty result.
    """
    if all("status" not in r or r["status"] == "success" for r in rr):
        return
    else:
        raise Api_Error(500, f"{op} failed with: {rr}")
    pass


def _make_mc_error(message):
    """Makes an error output similar to one from MC command."""
    return {"status": "error", "error": {"message": message}}


def _simplify_messages_in_mc_error(ee):
    """Extracts a message part from an MC error, by choosing one if some
    errors happened.  It returns a pair, (True, entire-messages) on a
    success, or (False, single-message) on a error.
    """
    # MC returns a json where the "Code" has useful information.
    # {"status": "error",
    #  "error": {"message", "...",
    #            "cause": {"error": {"Code": "error-description-string",
    for s in ee:
        if s.get("status") != "success":
            try:
                m0 = s["error"]["cause"]["error"]["Code"]
                return (False, [_make_mc_error(m0)])
            except Exception:
                pass
            try:
                _ = s["error"]["message"]
                return (False, [s])
            except Exception:
                pass
            return (False, [_make_mc_error("Unknown error")])
        else:
            pass
        pass
    return (True, ee)


class Mc():
    """MC command envirionment.  It works as a context in Python, but a
    context is created at alias_set().  It uses a pool-id+random as an
    alias name.
    """

    def __init__(self, bin_mc, env_mc, minio_ep, pool_id, mc_timeout):
        self._verbose = False
        self.mc = bin_mc
        self.env = env_mc
        self._minio_ep = minio_ep
        self._pool_id = pool_id
        self._mc_timeout = mc_timeout
        self._alias = None
        self._config_dir = None
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._alias is not None:
                self.alias_remove()
        except Exception as e:
            logger.error(f"MC alias-remove failed: exception={e}",
                         exc_info=True)
            pass
        finally:
            self._alias = None
            pass
        try:
            if self._config_dir is not None:
                self._config_dir.cleanup()
        except Exception as e:
            logger.error(f"TemporaryDirectory removal failed: exception={e}",
                         exc_info=True)
            pass
        finally:
            self._config_dir = None
            pass
        pass

    # MC COMMAND PRIMITIVES.

    def alias_set(self, root_user, root_secret):
        assert self._alias is None and self._config_dir is None
        url = f"http://{self._minio_ep}"
        self._config_dir = tempfile.TemporaryDirectory()
        self._alias = f"{self._pool_id}{random_str(12).lower()}"
        (p, r) = self._execute_cmd("alias_set", False,
                                   "alias", "set", self._alias, url,
                                   root_user, root_secret,
                                   "--api", "S3v4")
        assert p is None
        if r[0]["status"] != "success":
            self._alias = None
            raise Exception(r[0]["error"]["message"])
        return self

    def alias_remove(self):
        (p, r) = self._execute_cmd("alias_remove", False,
                                   "alias", "remove", self._alias)
        assert p is None
        self._alias = None
        if r[0]["status"] != "success":
            raise Exception(r[0]["error"]["message"])
        pass

    def admin_info(self):
        return self._execute_cmd("admin_info", False,
                                 "admin", "info", self._alias)

    def admin_policy_set(self, access_key, policy):
        (p, v) = self._execute_cmd("admin_policy_set", False,
                                   "admin", "policy", "set", self._alias,
                                   policy, f"user={access_key}")
        assert p is None
        return v

    def admin_service_stop(self):
        (p, v) = self._execute_cmd("admin_service_stop", False,
                                   "admin", "service", "stop", self._alias)
        assert p is None
        return v

    def admin_user_add(self, access_key, secret_access_key):
        (p, v) = self._execute_cmd("admin_user_add", False,
                                   "admin", "user", "add", self._alias,
                                   access_key, secret_access_key)
        assert p is None
        return v

    def admin_user_disable(self, access_key):
        (p, v) = self._execute_cmd("admin_user_disable", False,
                                   "admin", "user", "disable", self._alias,
                                   access_key)
        assert p is None
        return v

    def admin_user_enable(self, access_key):
        (p, v) = self._execute_cmd("admin_user_enable", False,
                                   "admin", "user", "enable", self._alias,
                                   access_key)
        assert p is None
        return v

    def admin_user_list(self):
        (p, v) = self._execute_cmd("admin_user_list", False,
                                   "admin", "user", "list", self._alias)
        assert p is None
        return v

    def admin_user_remove(self, access_key):
        assert isinstance(access_key, str)
        (p, v) = self._execute_cmd("admin_user_remove", False,
                                   "admin", "user", "remove", self._alias,
                                   access_key)
        assert p is None
        return v

    def list_buckets(self):
        (p, v) = self._execute_cmd("list_buckets", False,
                                   "ls", f"{self._alias}")
        assert p is None
        return v

    def make_bucket(self, bucket):
        (p, v) = self._execute_cmd("make_bucket", False,
                                   "mb", f"{self._alias}/{bucket}")
        assert p is None
        return v

    def remove_bucket(self, bucket):
        # NEVER USE THIS; The MC-rb command removes the bucket contents.
        assert False
        (p, v) = self._execute_cmd("remove_bucket", False,
                                   "rb", f"{self._alias}/{bucket}")
        assert p is None
        return v

    def policy_set(self, bucket, policy):
        (p, v) = self._execute_cmd("policy_set", False,
                                   "policy", "set", policy,
                                   f"{self._alias}/{bucket}")
        assert p is None
        return v

    def _execute_cmd(self, name, no_wait, *args):
        # (Currently, it does not check the exit code of MC command.)
        assert self._alias is not None and self._config_dir is not None
        cmd = ([self.mc, "--json", f"--config-dir={self._config_dir.name}"]
               + list(args))
        assert all(isinstance(i, str) for i in cmd)
        try:
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self.env)
            if no_wait:
                return (p, None)
            with p:
                (outs, errs) = p.communicate(timeout=self._mc_timeout)
                p_status = p.poll()
                if (self._verbose):
                    logger.debug(f"Running MC command: cmd={cmd};"
                                 f" status={p_status},"
                                 f" outs=({outs}), errs=({errs})")
                    pass
                if p_status is None:
                    logger.debug(f"Running MC command failed: cmd={cmd};"
                                 f" command does not finish.")
                    r = [_make_mc_error(f"Unfinished MC: ({outs})")]
                    return (None, r)
                try:
                    ss = outs.split(b"\n")
                    ee = [json.loads(e, parse_int=None)
                          for e in ss if e != b""]
                    (ok, rr) = _simplify_messages_in_mc_error(ee)
                    if ok:
                        if (self._verbose):
                            logger.debug(f"Running MC command OK: cmd={cmd}")
                        else:
                            logger.debug(f"Running MC command OK: cmd={name}")
                    else:
                        logger.debug(f"Running MC command failed: cmd={cmd};"
                                     f" error={rr}")
                        pass
                    return (None, rr)
                except Exception as e:
                    logger.error(f"json.loads failed: exception={e}",
                                 exc_info=True)
                    r = [_make_mc_error(f"Bad output from MC: ({outs})")]
                    return (None, r)
                pass
        except Exception as e:
            logger.error(f"Popen failed: cmd={cmd}; exception={e}")
            r = [_make_mc_error(f"Executing MC command failed:"
                                f" exception={e}")]
            return (None, r)
        pass

    # MC COMMAND UTILITIES (Combinations).

    def make_bucket_with_policy(self, name, policy):
        # Making a bucket may cause an error.  It is because Lens3
        # never removes buckets at all, but it just makes inaccessible.
        assert self._alias is not None
        try:
            r = self.make_bucket(name)
            assert_mc_success(r, "mc.make_bucket")
        except Exception:
            pass
        r = self.policy_set(name, policy)
        assert_mc_success(r, "mc.policy_set")
        pass

    def clean_minio_setting(self, pool_id):
        """Tries to delete all access-keys and set the "none"-policy to all
        buckets.  A pool_id is used only for printing messages.
        """
        failure_message = f"Cleaning MinIO state for pool={pool_id}"
        # Delete access-keys.
        try:
            keys0 = self.admin_user_list()
            assert_mc_success(keys0, "mc.admin_user_list")
            keys = [intern_mc_user_info(e) for e in keys0]
        except Exception as e:
            logger.info(failure_message
                        + f" failed (ignored): exception={e}")
            keys = []
            pass
        for k in keys:
            try:
                r = self.admin_user_remove(k.get("access_key"))
                assert_mc_success(r, "mc.admin_user_remove")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        # Delete buckets.
        try:
            bkts0 = self.list_buckets()
            assert_mc_success(bkts0, "mc.list_buckets")
            bkts = [intern_mc_list_entry(e) for e in bkts0]
        except Exception as e:
            logger.info(failure_message
                        + f" failed (ignored): exception={e}")
            bkts = []
            pass
        for b in bkts:
            try:
                r = self.policy_set(b.get("name"), "none")
                assert_mc_success(r, "mc.policy_set")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        pass

    def _drop_auxiliary_bucket_slots(self, desc):
        needed = {"name", "bkt_policy"}
        return {k: v for (k, v) in desc.items() if k in needed}

    def setup_minio_on_buckets(self, bkts):
        """Updates the MinIO state to the current pool description at a start
        of MinIO every time.  It does nothing usually.  Note that it
        sets a policy to every bucket, because MC-ls command output
        does not return a policy setting.
        """
        bkts = [self._drop_auxiliary_bucket_slots(b) for b in bkts]
        recorded = self.list_buckets()
        assert_mc_success(recorded, "mc.list_buckets")
        recorded = [intern_mc_list_entry(b) for b in recorded]
        recorded = [self._drop_auxiliary_bucket_slots(b) for b in recorded]
        (ll, pp, rr) = list_diff3(recorded, lambda b: b.get("name"),
                                  bkts, lambda b: b.get("name"))
        dels = ll
        adds = rr
        mods = [n for (_, n) in pp]
        if (dels == [] and adds == [] and mods == []):
            return
        delbkts = [b["name"] for b in dels]
        addbkts = [b["name"] for b in adds]
        modbkts = [b["name"] for b in mods]
        pool_id = self._pool_id
        logger.warning(f"Updating MinIO state on buckets"
                       f" for pool={pool_id}:"
                       f" delete={delbkts}, add={addbkts} change={modbkts}")
        failure_message = f"Updating MinIO state for pool={pool_id}"
        for b in dels:
            try:
                r = self.policy_set(b["name"], "none")
                assert_mc_success(r, "mc.policy_set")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        for b in adds:
            try:
                r = self.make_bucket(b["name"])
                assert_mc_success(r, "mc.make_bucket")
                r = self.policy_set(b["name"], b["bkt_policy"])
                assert_mc_success(r, "mc.policy_set")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        for b in mods:
            try:
                r = self.policy_set(b["name"], b["bkt_policy"])
                assert_mc_success(r, "mc.policy_set")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        pass

    pass

    def _drop_auxiliary_key_slots(self, desc):
        needed = {"access_key", "secret_key", "key_policy"}
        return {k: v for (k, v) in desc.items() if k in needed}

    def setup_minio_on_keys(self, keys):
        """Updates the MinIO state to the current pool description at a start
        of MinIO every time.  It does nothing usually.
        """

        # Comparison of keys in the pool and ones recorded in MinIO
        # always unequal because secret_key part is missing in the
        # MinIO side.

        keys = [self._drop_auxiliary_key_slots(k) for k in keys]
        recorded = self.admin_user_list()
        assert_mc_success(recorded, "mc.admin_user_list")
        recorded = [intern_mc_user_info(k) for k in recorded]
        recorded = [self._drop_auxiliary_key_slots(k) for k in recorded]
        (ll, pp, rr) = list_diff3(recorded, lambda k: k.get("access_key"),
                                  keys, lambda k: k.get("access_key"))
        mm = [n for (o, n) in pp if o != n]
        dels = ll + mm
        adds = rr + mm
        if (dels == [] and adds == []):
            return
        delkeys = [k["access_key"] for k in dels]
        addkeys = [k["access_key"] for k in adds]
        pool_id = self._pool_id
        logger.warning(f"Updating MinIO state on access-keys"
                       f" for pool={pool_id}:"
                       f" delete={delkeys}, add={addkeys}")
        failure_message = f"Updating MinIO state for pool={pool_id}"
        for k in dels:
            try:
                r = self.admin_user_remove(k["access_key"])
                assert_mc_success(r, "mc.admin_user_remove")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        for k in adds:
            try:
                r = self.admin_user_add(k["access_key"], k["secret_key"])
                assert_mc_success(r, "mc.admin_user_add")
                r = self.admin_policy_set(k["access_key"], k["key_policy"])
                assert_mc_success(r, "mc.admin_policy_set")
                r = self.admin_user_enable(k["access_key"])
                assert_mc_success(r, "mc.admin_user_enable")
            except Exception as e:
                logger.info(failure_message
                            + f" failed (ignored): exception={e}")
                pass
            pass
        pass

# # UNSED -- FOR FUTURE DEVELOPER --
# # THIS CODE IS USED TO EXECUTE MC, WITHOUT WAITING FOR FINISHING
# # EXECUTION. MANAGER DOES NOT RECEIVE FINISH STATUS FROM MC AND
# #ASK INIT PROCESS TO WAIT ZOMBIE PROCESS OF MC.
# def unwait(cmd, env):
#     try:
#         pid = os.fork()
#         if pid != 0:
#             (pid, status) = os.waitpid(pid, 0)
#             return status
#     except OSError as e:
#         logger.error(f"fork: {os.strerror(e.errno)}")
#         logger.exception(e)
#         return ERROR_FORK_FORK
#
#     try:
#         pid = os.fork()
#         if pid != 0:
#             sys.exit(0)
#     except OSError as e:
#         logger.error(f"fork: {os.strerror(e.errno)}")
#         logger.exception(e)
#         sys.exit(ERROR_EXIT_FORK)
#
#     try:
#         with Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env) as p:
#             (out, err) = p.communicate()
#             status = p.wait()
#             logger.debug(f"status: {status} out: {out} err: {err}")
#     finally:
#         sys.exit(0)
