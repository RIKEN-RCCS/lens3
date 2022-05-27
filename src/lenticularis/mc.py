"""MinIO MC control.  It runs MC command to set-up MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import tempfile
import json
from subprocess import Popen, DEVNULL, PIPE
from signal import signal, alarm, SIGTERM, SIGCHLD, SIGALRM, SIG_IGN
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
    "policyName": "policy_name",
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


def _intern_user_info(json):
    """Maps key strings returned from MC to ones in Lens3."""
    map = _mc_user_info_json_keys
    return {map.get(k, k): v for (k, v) in json.items()}


def _intern_list_entry(json):
    """Maps key strings returned from MC to ones in Lens3.  It also drops
    a trailing slash in a bucket name."""
    map = _mc_list_entry_json_keys
    return {map.get(k, k): (remove_trailing_slash(v) if k == "key" else v)
            for (k, v) in json.items()}


def assert_mc_success(r, e):
    if r and r[0].get("status") != "success":
        raise Exception(f"error: {e}: {r}")
    # raise Exception(f"error: {e}: mc output is empty")
    return


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

    def admin_policy_set(self, access_key_id, policy):
        return self._execute_cmd("admin_policy_set",
                                 False, "admin", "policy", "set", self._alias,
                                 policy, f"user={access_key_id}")

    def admin_service_stop(self):
        return self._execute_cmd("admin_service_stop", False,
                                 "admin", "service", "stop", self._alias)

    def admin_user_add(self, access_key_id, secret_access_key):
        return self._execute_cmd("admin_user_add", False,
                                 "admin", "user", "add", self._alias,
                                 access_key_id, secret_access_key)

    def admin_user_disable(self, access_key_id, no_wait=False):
        return self._execute_cmd("admin_user_disable", no_wait,
                                 "admin", "user", "disable", self._alias,
                                 access_key_id)

    def admin_user_enable(self, access_key_id):
        return self._execute_cmd("admin_user_enable", False,
                                 "admin", "user", "enable", self._alias,
                                 access_key_id)

    def admin_user_list(self):
        return self._execute_cmd("admin_user_list", False,
                                 "admin", "user", "list", self._alias)

    def admin_user_remove(self, access_key_id):
        return self._execute_cmd("admin_user_remove", False,
                                 "admin", "user", "remove", self._alias,
                                 access_key_id)

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

    def _make_mc_error(self, message):
        return {"status": "error", "error": {"message": message}}

    def _simplify_mc_messages(self, ee):
        """Simplifies messages from mc, by choosing one if some errors
        happened."""
        for s in ee:
            if s.get("status") != "success":
                e = s.get("error")
                if e is None:
                    return [self._make_mc_error("Unknown error")]
                m = e.get("message")
                if m is None:
                    return [self._make_mc_error("Unknown error")]
                return ([s], False)
            pass
        return (ee, True)

    def _execute_cmd(self, name, no_wait, *args):
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
                    logger.debug(f"Running mc command: cmd={cmd};"
                                 f" status={status},"
                                 f" outs=({outs}), errs=({errs})")
                    pass
                try:
                    s = outs.split(b"\n")
                    ee = [json.loads(e, parse_int=None) for e in s if e != b""]
                    (r, ok) = self._simplify_mc_messages(ee)
                    if ok:
                        if (self._verbose):
                            logger.debug(f"Running mc command OK: cmd={cmd}")
                        else:
                            logger.debug(f"Running mc command OK: cmd={name}")
                    else:
                        logger.debug(f"Running mc command failed: cmd={cmd};"
                                     f" error={r}")
                        pass
                    return (None, r)
                except Exception as e:
                    logger.error(f"json.loads failed: exception={e}")
                    logger.exception(e)
                    r = [self._make_mc_error(f"{outs}")]
                    return (None, r)
                pass
        except Exception as e:
            logger.error(f"Popen failed: cmd={cmd}; exception={e}")
            logger.exception(e)
            r = [self._make_mc_error(f"{e}")]
            return (None, r)
        pass

    def setup_minio(self, p, pooldesc):
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
        children = []

        access_keys = pooldesc["access_keys"]
        (p_, existing) = self.admin_user_list()
        assert p_ is None
        assert_mc_success(existing, "mc.admin_user_list")
        existing = [_intern_user_info(e) for e in existing]

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
        access_key_id = b["access_key"]
        secret_access_key = b["secret_key"]
        policy = b["policy_name"]
        (p_, r) = self.admin_user_add(access_key_id, decrypt_secret(secret_access_key))
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_add")
        (p_, r) = self.admin_policy_set(access_key_id, policy)
        assert p_ is None
        assert_mc_success(r, "mc.admin_policy_set")
        return []

    def _set_access_keys_delete(self, e):
        access_key_id = e["access_key"]
        if False:
            # NOTE: Do not delete the unregistered key here.
            (p, r_) = self.admin_user_disable(access_key_id, no_wait=True)
            assert r_ is None
            return [(p, "mc.admin_user_disable")]
        else:
            (p_, r) = self.admin_user_remove(access_key_id)
            assert p_ is None
            assert_mc_success(r, "mc.admin_user_remove")
            return []
        pass

    def _set_access_keys_update(self, x):
        (b, e) = x
        access_key_id = b["access_key"]
        secret_access_key = b["secret_key"]
        policy = b["policy_name"]

        (p_, r) = self.admin_user_remove(access_key_id)
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_remove")

        secret = decrypt_secret(secret_access_key)
        (p_, r) = self.admin_user_add(access_key_id, secret)
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_add")

        (p_, r) = self.admin_policy_set(access_key_id, policy)
        assert p_ is None
        assert_mc_success(r, "mc.admin_policy_set")

        (p_, r) = self.admin_user_enable(access_key_id)
        assert p_ is None
        assert_mc_success(r, "mc.admin_user_enable")
        return []

    def _set_bucket_policy(self, pooldesc):
        logger.debug("@@@ +++")
        logger.debug("@@@ set_bucket_policy")
        children = []

        buckets = pooldesc["buckets"]
        (p_, existing) = self.list_buckets()
        assert p_ is None
        assert_mc_success(existing, "mc.list_buckets")
        existing = [_intern_list_entry(e) for e in existing]

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
        policy = b["policy"]
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
        policy = b["policy"]
        (p_, r) = self.policy_set(name, policy)
        assert p_ is None
        assert_mc_success(r, "mc.policy_set")
        return []

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
