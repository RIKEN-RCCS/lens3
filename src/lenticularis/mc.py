"""MinIO MC control.  It runs MC command to set-up MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# NOTE: The error cause-code "BucketAlreadyOwnedByYou" returned MC
# command should be treated as not an error.

import os
import sys
import tempfile
import json
from subprocess import Popen, DEVNULL, PIPE
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
from lenticularis.poolutil import Api_Error
from lenticularis.utility import remove_trailing_slash
from lenticularis.utility import decrypt_secret, list_diff3
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
    map = _mc_user_info_json_keys
    return {map.get(k, k): v for (k, v) in json.items()}


def intern_mc_list_entry(json):
    """Maps key strings returned from MC to ones in Lens3.  It also drops
    a trailing slash in a bucket name."""
    map = _mc_list_entry_json_keys
    return {map.get(k, k): (remove_trailing_slash(v) if k == "key" else v)
            for (k, v) in json.items()}


def assert_mc_success(r, op):
    # It accepts an empty list, because MC command may return an empty
    # result for listing commands.
    if r == []:
        return
    elif r[0].get("status") != "success":
        raise Api_Error(500, f"{op} failed with: {r}")
    else:
        return
    pass


def _make_mc_error(message):
    """Makes an error output similar to one from MC command."""
    return {"status": "error", "error": {"message": message}}


def _simplify_message_in_mc_error(ee):
    """Extracts a message part from an MC error, by choosing one if some
        errors happened.
    """
    # MC returns a json where the "Code" is of useful information.
    # {"status": "error",
    #  "error": {"message", "...",
    #            "cause": {"error": {"Code": "error-description-string",
    for s in ee:
        if s.get("status") != "success":
            try:
                m0 = s["error"]["cause"]["error"]["Code"]
                return ([_make_mc_error(m0)], False)
            except:
                pass
            try:
                m1 = s["error"]["message"]
                return ([s], False)
            except:
                pass
            return ([_make_mc_error("Unknown error")], False)
        else:
            pass
        pass
    return (ee, True)


class Mc():
    """MC command envirionment.  It works as a context, but a context is
    created at alias_set().  It uses a pool-id+random as an alias
    name.
    """

    def __init__(self, bin_mc, env_mc, minio_ep, pool_id):
        self._verbose = False
        self.mc = bin_mc
        self.env = env_mc
        self._minio_ep = minio_ep
        self._pool_id = pool_id
        self._alias = None
        self._config_dir = None
        return

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._alias is not None:
                self.alias_remove()
        except Exception as e:
            logger.error(f"MC alias-remove failed: exception={e}")
            logger.exception(e)
            pass
        finally:
            self._alias = None
            pass
        try:
            if self._config_dir is not None:
                self._config_dir.cleanup()
        except Exception as e:
            logger.error(f"TemporaryDirectory removal failed: exception={e}")
            logger.exception(e)
            pass
        finally:
            self._config_dir = None
            pass
        return

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
        return

    def admin_info(self):
        return self._execute_cmd("admin_info", False,
                                 "admin", "info", self._alias)

    def admin_policy_set(self, access_key, policy):
        return self._execute_cmd("admin_policy_set",
                                 False, "admin", "policy", "set", self._alias,
                                 policy, f"user={access_key}")

    def admin_service_stop(self):
        return self._execute_cmd("admin_service_stop", False,
                                 "admin", "service", "stop", self._alias)

    def admin_user_add(self, access_key, secret_access_key):
        return self._execute_cmd("admin_user_add", False,
                                 "admin", "user", "add", self._alias,
                                 access_key, secret_access_key)

    def admin_user_disable(self, access_key, no_wait=False):
        return self._execute_cmd("admin_user_disable", no_wait,
                                 "admin", "user", "disable", self._alias,
                                 access_key)

    def admin_user_enable(self, access_key):
        return self._execute_cmd("admin_user_enable", False,
                                 "admin", "user", "enable", self._alias,
                                 access_key)

    def admin_user_list(self):
        return self._execute_cmd("admin_user_list", False,
                                 "admin", "user", "list", self._alias)

    def admin_user_remove(self, access_key):
        assert isinstance(access_key, str)
        return self._execute_cmd("admin_user_remove", False,
                                 "admin", "user", "remove", self._alias,
                                 access_key)

    def list_buckets(self):
        return self._execute_cmd("list_buckets", False,
                                 "ls", f"{self._alias}")

    def make_bucket(self, bucket):
        return self._execute_cmd("make_bucket", False,
                                 "mb", f"{self._alias}/{bucket}")

    def remove_bucket(self, bucket):
        # NEVER USE THIS; The command rb removes the whole bucket contents.
        assert False
        return self._execute_cmd("remove_bucket", False,
                                 "rb", f"{self._alias}/{bucket}")

    def policy_set(self, bucket, policy, no_wait=False):
        return self._execute_cmd("policy_set", no_wait,
                                 "policy", "set", policy,
                                 f"{self._alias}/{bucket}")

    def _execute_cmd(self, name, no_wait, *args):
        # AHO (Check the exit code of MC command.)
        assert self._alias is not None and self._config_dir is not None
        cmd = ([self.mc, "--json", f"--config-dir={self._config_dir.name}"]
               + list(args))
        try:
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self.env)
            if no_wait:
                return (p, None)
            with p:
                (outs, errs) = p.communicate()
                status = p.wait()
                if (self._verbose):
                    logger.debug(f"Running MC command: cmd={cmd};"
                                 f" status={status},"
                                 f" outs=({outs}), errs=({errs})")
                    pass
                try:
                    ss = outs.split(b"\n")
                    ee = [json.loads(e, parse_int=None)
                          for e in ss if e != b""]
                    (r, ok) = _simplify_message_in_mc_error(ee)
                    if ok:
                        if (self._verbose):
                            logger.debug(f"Running MC command OK: cmd={cmd}")
                        else:
                            logger.debug(f"Running MC command OK: cmd={name}")
                    else:
                        logger.debug(f"Running MC command failed: cmd={cmd};"
                                     f" error={r}")
                        pass
                    return (None, r)
                except Exception as e:
                    logger.error(f"json.loads failed: exception={e}",
                                 exc_info=True)
                    r = [_make_mc_error(f"Bad output from MC: ({outs})")]
                    return (None, r)
                pass
        except Exception as e:
            logger.error(f"Popen failed: cmd={cmd}; exception={e}",
                         exc_info=True)
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
            (p_, r) = self.make_bucket(name)
            assert p_ is None
            assert_mc_success(r, "mc.make_bucket")
        except Exception:
            pass
        (p_, r) = self.policy_set(name, policy)
        assert p_ is None
        assert_mc_success(r, "mc.policy_set")
        return

    def clean_minio_setting(self, user_id, pool_id):
        """Tries to delete all access-keys and set "none"-policy to all
        buckets.
        """
        # Delete access-keys.
        try:
            (p_, keys0) = self.admin_user_list()
            assert p_ is None
            assert_mc_success(keys0, "mc.admin_user_list")
            keys = [intern_mc_user_info(e) for e in keys0]
        except Exception as e:
            logger.info(f": mc.admin_user_list for pool={pool_id}"
                        f" failed (ignored): exception={e}")
            keys = []
            pass
        for k in keys:
            try:
                (p_, r) = self.admin_user_remove(k.get("access_key"))
                assert p_ is None
                assert_mc_success(r, "mc.admin_user_remove")
            except Exception as e:
                logger.info(f": mc.admin_user_remove on key={k}"
                            f" failed (ignored): exception={e}")
                pass
            pass
        # Delete buckets.
        try:
            (p_, bkts0) = self.list_buckets()
            assert p_ is None
            assert_mc_success(bkts0, "mc.list_buckets")
            bkts = [intern_mc_list_entry(e) for e in bkts0]
        except Exception as e:
            logger.info(f": mc.admin_user_list on pool={pool_id}"
                        f" failed (ignored): exception={e}")
            bkts = []
            pass
        for b in bkts:
            try:
                (p_, r) = self.policy_set(b.get("name"), "none")
                assert p_ is None
                assert_mc_success(r, "mc.policy_set")
            except Exception as e:
                logger.info(f": mc.policy_set on bucket={b}"
                            f" failed (ignored): exception={e}")
                pass
            pass
        pass

    def setup_minio(self, p, pooldesc):
        ##AHO
        try:
            a_children = self._set_access_keys(pooldesc)
        except Exception as e:
            raise Exception(f"manager:install_minio_access_keys: {e}")
        try:
            b_children = self._set_bucket_policy(pooldesc)
        except Exception as e:
            raise Exception(f"manager:set_bucket_policy: {e}")

        for (p, c) in (a_children + b_children):
            status = p.wait()
            # _assert_mc_success(r, c)
            pass
        return

    def _set_access_keys(self, pooldesc):
        if "access_keys" not in pooldesc:
            return []

        children = []

        access_keys = pooldesc["access_keys"]
        (p_, existing) = self.admin_user_list()
        assert p_ is None
        assert_mc_success(existing, "mc.admin_user_list")
        existing = [intern_mc_user_info(e) for e in existing]

        (ll, pp, rr) = list_diff3(access_keys, lambda b: b.get("access_key"),
                                  existing, lambda e: e.get("access_key"))

        logger.debug(f"Setup MinIO on access-keys:"
                     f" add={ll}, delete={rr}, update={pp}")

        for x in ll:
            children.extend(self._set_access_keys_add(x))
            pass
        for x in rr:
            children.extend(self._set_access_keys_delete(x))
            pass
        for x in pp:
            children.extend(self._set_access_keys_update(x))
            pass
        return children

    def _set_access_keys_add(self, b):
        access_key = b["access_key"]
        secret_access_key = b["secret_key"]
        policy = b["key_policy"]
        (p_, r) = self.admin_user_add(access_key, decrypt_secret(secret_access_key))
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_add")
        (p_, r) = self.admin_policy_set(access_key, policy)
        assert p_ is None
        assert_mc_success(r, "mc.admin_policy_set")
        return []

    def _set_access_keys_delete(self, e):
        access_key = e["access_key"]
        if False:
            # NOTE: Do not delete the unregistered key here.
            (p, r_) = self.admin_user_disable(access_key, no_wait=True)
            assert r_ is None
            return [(p, "mc.admin_user_disable")]
        else:
            (p_, r) = self.admin_user_remove(access_key)
            assert p_ is None
            assert_mc_success(r, "mc.admin_user_remove")
            return []
        pass

    def _set_access_keys_update(self, x):
        (b, e) = x
        access_key = b["access_key"]
        secret_access_key = b["secret_key"]
        policy = b["key_policy"]

        (p_, r) = self.admin_user_remove(access_key)
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_remove")

        secret = decrypt_secret(secret_access_key)
        (p_, r) = self.admin_user_add(access_key, secret)
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_add")

        (p_, r) = self.admin_policy_set(access_key, policy)
        assert p_ is None
        assert_mc_success(r, "mc.admin_policy_set")

        (p_, r) = self.admin_user_enable(access_key)
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_enable")
        return []

    def _set_bucket_policy(self, pooldesc):
        if "buckets" not in pooldesc:
            return []

        children = []

        buckets = pooldesc["buckets"]
        (p_, existing) = self.list_buckets()
        assert p_ is None
        assert_mc_success(existing, "mc.list_buckets")
        existing = [intern_mc_list_entry(e) for e in existing]

        logger.debug(f"@@@ buckets = {buckets}")
        logger.debug(f"@@@ existing = {existing}")
        (ll, pp, rr) = list_diff3(buckets, lambda b: b.get("name"),
                                  existing, lambda e: e.get("name"))

        logger.debug(f"Setup MinIO on bucket-policy:"
                     f" add={ll}, delete={rr}, update={pp}")

        for x in ll:
            children.extend(self._set_bucket_policy_add(x))
            pass
        for x in rr:
            children.extend(self._set_bucket_policy_delete(x))
            pass
        for x in pp:
            children.extend(self._set_bucket_policy_update(x))
            pass
        return children

    def _set_bucket_policy_add(self, b):
        name = b["name"]
        (p_, r) = self.make_bucket(name)
        assert p_ is None
        assert_mc_success(r, "mc.make_bucket")
        policy = b["bkt_policy"]
        (p_, r) = self.policy_set(name, policy)
        assert p_ is None
        assert_mc_success(r, "mc.policy_set")
        return []

    def _set_bucket_policy_delete(self, e):
        name = remove_trailing_slash(e["name"])
        policy = "none"
        (p, r_) = self.policy_set(name, policy, no_wait=True)
        assert r_ is None
        return [(p, "mc.policy_set")]

    def _set_bucket_policy_update(self, x):
        (b, e) = x
        name = b["name"]
        policy = b["bkt_policy"]
        (p_, r) = self.policy_set(name, policy)
        assert p_ is None
        assert_mc_success(r, "mc.policy_set")
        return []

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
