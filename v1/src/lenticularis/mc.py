"""MinIO MC command.  It runs MC command to manage MinIO."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# NOTES. (1) It depends on the versions of MinIO and MC.  It is
# necessary to rewrite this code when updating MinIO and MC.  This is
# tested on MINIO RELEASE.2023-06-09T07-32-12Z and MC
# RELEASE.2023-06-06T13-48-56Z.  (2) The error-cause code
# "BucketAlreadyOwnedByYou" returned by an MC command should be
# treated as not an error.

# Listing commands (such as of buckets or secrets) return records that
# are separated by newlines.  Each record includes a status=success.

# A record returned in "ls" listing:
# {
#     "status": "success",
#     "type": "folder",
#     "lastModified": "2023-01-01T00:00:00.00+00:00",
#     "size": 0,
#     "key": "bkt0/",
#     "etag": "",
#     "url": "http://lens3.example.com:9001/",
#     "versionOrdinal": 1
# }

# A record returned in "user list" listing:
# {
#     "status": "success",
#     "accessKey": "jfD9kB3tlr19eLILERno",
#     "policyName": "readwrite",
#     "userStatus": "enabled"
# }

import tempfile
import json
from subprocess import Popen, DEVNULL, PIPE
from lenticularis.pooldata import Api_Error
from lenticularis.utility import remove_trailing_slash
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger
from lenticularis.utility import random_str

# MinIO MC command returns a json with keys that are specific to each
# command.  Some keys shall be recognized in Lens3 and are mapped.

_mc_secret_json_keys = {
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


def _intern_secret_record(record):
    """Maps key strings returned from MC to ones in Lens3."""
    mapping = _mc_secret_json_keys
    return {mapping.get(k, k): v for (k, v) in record.items()}


def _intern_list_entry_record(record):
    """Maps key strings returned from MC to ones in Lens3.  It also drops
    a trailing slash in a bucket name."""
    mapping = _mc_list_entry_json_keys
    return {mapping.get(k, k): (remove_trailing_slash(v) if k == "key" else v)
            for (k, v) in record.items()}


def _assert_mc_success(vv, op):
    """Checks MC command is successful."""
    (ok, values, message) = vv
    if ok == True:
        return
    else:
        raise Api_Error(500, f"{op} failed with: {message}")
    pass


def _make_mc_error(message):
    """Makes an error record with a message, which is returned as an error
    in _simplify_mc_message().
    """
    return (False, [], message)


def _simplify_mc_message(ee):
    """Extracts a message part from an MC error.  It returns a 3-tuple
    {True, [value,...], "") on success, or {False, [], message) on
    failure.  It packs the values to a single record.  Note that MC
    returns multiple values as separate json records.  Each record is
    {"status": "success", ...}, containing a value.  A listing command
    returns nothing for an empty list.  Thus, empty list is considered
    as a success.  An error record is {"status": "error", ...},
    containing a message.  It may include useful information in the
    "Code" slot if it exists.  An error record looks like: {"status":
    "error", "error": {"message", "...", "cause": {"error": {"Code":
    "...", ...}}}}.
    """
    for s in ee:
        if s.get("status") == "success":
            pass
        elif s.get("status") == "error":
            if len(ee) != 1:
                logger.warning(f"MC command with multiple errors: ({ee})")
                pass
            try:
                m1 = s["error"]["cause"]["error"]["Code"]
                return _make_mc_error(m1)
            except Exception:
                pass
            try:
                m2 = s["error"]["message"]
                return _make_mc_error(m2)
            except Exception:
                pass
            return _make_mc_error(f"{s}")
        else:
            return _make_mc_error(f"{s}")
        pass
    return (True, ee, "")


class Mc():
    """MC command envirionment.  It is an MC alias setting.  It works as a
    context in Python (i.e., it is used in "with"), but a context is
    created at mc_alias_set().  It uses a pool-id + random as an alias
    name.  Set self._verbose true to take execution logs.
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
                vv = self._mc_alias_remove()
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"MC alias-remove failed: exception=({m})",
                         exc_info=True)
            pass
        finally:
            self._alias = None
            pass
        try:
            if self._config_dir is not None:
                self._config_dir.cleanup()
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"TemporaryDirectory removal failed: exception=({m})",
                         exc_info=True)
            pass
        finally:
            self._config_dir = None
            pass
        pass

    # MC COMMAND PRIMITIVES.

    def mc_alias_set(self, root_user, root_secret):
        assert self._alias is None and self._config_dir is None
        url = f"http://{self._minio_ep}"
        self._config_dir = tempfile.TemporaryDirectory()
        self._alias = f"{self._pool_id}-{random_str(12).lower()}"
        vv = self._execute_cmd("alias_set",
                               ["alias", "set", self._alias, url,
                                root_user, root_secret,
                                "--api", "S3v4"])
        (ok, values, message) = vv
        if not ok == True:
            self._alias = None
            raise Exception(message)
        return self

    def _mc_alias_remove(self):
        vv = self._execute_cmd("alias_remove",
                               ["alias", "remove", self._alias])
        self._alias = None
        (ok, values, message) = vv
        if not ok == True:
            raise Exception(message)
        pass

    def _mc_admin_info(self):
        vv = self._execute_cmd("admin_info",
                               ["admin", "info", self._alias])
        return vv

    def _mc_admin_service_stop(self):
        vv = self._execute_cmd("admin_service_stop",
                               ["admin", "service", "stop", self._alias])
        return vv

    def _mc_admin_user_add(self, access_key, secret_key):
        vv = self._execute_cmd("admin_user_add",
                               ["admin", "user", "add", self._alias,
                                access_key, secret_key])
        return vv

    def _mc_admin_user_remove(self, access_key):
        assert isinstance(access_key, str)
        vv = self._execute_cmd("admin_user_remove",
                               ["admin", "user", "remove", self._alias,
                                access_key])
        return vv

    def _mc_admin_user_enable(self, access_key):
        vv = self._execute_cmd("admin_user_enable",
                               ["admin", "user", "enable", self._alias,
                                access_key])
        return vv

    def _mc_admin_user_disable(self, access_key):
        vv = self._execute_cmd("admin_user_disable",
                               ["admin", "user", "disable", self._alias,
                                access_key])
        return vv

    def _mc_admin_user_list(self):
        vv = self._execute_cmd("admin_user_list",
                               ["admin", "user", "list", self._alias])
        return vv

    def _mc_admin_policy_attach_user(self, access_key, policy):
        vv = self._execute_cmd("admin_policy_attach",
                               ["admin", "policy", "attach", self._alias,
                                policy, "--user", f"{access_key}"])
        return vv

    def _mc_admin_policy_detach_user(self, access_key, policy):
        vv = self._execute_cmd("admin_policy_detach",
                               ["admin", "policy", "detach", self._alias,
                                policy, "--user", f"{access_key}"])
        return vv

    def _mc_list_buckets(self):
        vv = self._execute_cmd("list_buckets",
                               ["ls", f"{self._alias}"])
        return vv

    def _mc_make_bucket(self, bucket):
        vv = self._execute_cmd("make_bucket",
                               ["mb", f"{self._alias}/{bucket}"])
        return vv

    def _mc_remove_bucket(self, bucket):
        # NEVER USE THIS; THE MC-RB COMMAND REMOVES BUCKET CONTENTS.
        assert False
        vv = self._execute_cmd("remove_bucket",
                               ["rb", f"{self._alias}/{bucket}"])
        return vv

    def _mc_anonymous_set(self, bucket, policy):
        # Sets a policy for anonymous accesses to a bucket.
        vv = self._execute_cmd("anonymous_set",
                               ["anonymous", "set", policy,
                                f"{self._alias}/{bucket}"])
        return vv

    def _execute_cmd(self, name, args):
        # (Currently, it does not check the exit code of MC command.)
        assert self._alias is not None and self._config_dir is not None
        cmd = ([self.mc, f"--config-dir={self._config_dir.name}", "--json"]
               + list(args))
        assert all(isinstance(i, str) for i in cmd)
        try:
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self.env)
            with p:
                (o_, e_) = p.communicate(timeout=self._mc_timeout)
                outs = str(o_, "latin-1").strip()
                errs = str(e_, "latin-1").strip()
                p_status = p.poll()
                if (self._verbose):
                    logger.debug(f"MC command done: cmd={cmd};"
                                 f" status={p_status}"
                                 f" stdout=({outs}) stderr=({errs})")
                    pass
                if p_status is None:
                    logger.error(f"MC command unfinished: cmd={cmd};"
                                 f" stdout=({outs}) stderr=({errs})")
                    vv = _make_mc_error(f"MC command unfinished: ({outs})")
                    return vv
                try:
                    ee = [json.loads(e)
                          for e in outs.splitlines()]
                    vv = _simplify_mc_message(ee)
                    (ok, values, message) = vv
                    if ok == True:
                        if (self._verbose):
                            logger.debug(f"MC command OK: cmd={cmd}")
                        else:
                            logger.debug(f"MC command OK: cmd={name}")
                    else:
                        logger.error(f"MC command failed: cmd={cmd};"
                                     f" error={message}"
                                     f" stdout=({outs}) stderr=({errs})")
                        pass
                    return vv
                except Exception as e:
                    m = rephrase_exception_message(e)
                    logger.error(f"json.loads failed: exception=({m})",
                                 exc_info=True)
                    vv = _make_mc_error(f"MC command returned a bad json:"
                                        f" ({outs})")
                    return vv
                pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Popen failed: cmd={cmd}; exception=({m})")
            vv = _make_mc_error(f"MC command failed: exception=({m})")
            return vv
        pass

    # MC COMMAND WRAPPERS (Combinations).

    def get_minio_info(self):
        vv = self._mc_admin_info()
        _assert_mc_success(vv, "mc.mc_admin_info")
        pass

    def stop_minio(self):
        vv = self._mc_admin_service_stop()
        _assert_mc_success(vv, "mc.mc_admin_service_stop")
        pass

    def make_bucket(self, bucket, policy):
        """Makes a bucket in MinIO.  Making a bucket may cause an error.  It
        is because Lens3 never removes buckets but makes it
        inaccessible.  Note that it does not delete a bucket on an
        exception in policy-set, because the bucket policy should be
        none.
        """
        assert self._alias is not None
        vv = self._mc_make_bucket(bucket)
        _assert_mc_success(vv, "mc.mc_make_bucket")
        vv = self._mc_anonymous_set(bucket, policy)
        _assert_mc_success(vv, "mc.mc_policy_set")
        pass

    def set_bucket_policy(self, bucket, policy):
        vv = self._mc_anonymous_set(bucket, policy)
        _assert_mc_success(vv, "mc.mc_policy_set")
        pass


    def delete_bucket(self, bucket):
        """Makes a bucket inaccessible."""
        vv = self._mc_anonymous_set(bucket, "none")
        _assert_mc_success(vv, "mc.mc_policy_set")
        pass

    def list_buckets(self):
        vv = self._mc_list_buckets()
        _assert_mc_success(vv, "mc.mc_list_buckets")
        (ok, values, message) = vv
        bkts = [_intern_list_entry_record(e)
                for e in values]
        return bkts

    def make_secret(self, key, secret, policy):
        """Makes an access key in MinIO.  Note it does not rollback on a
        failure in the middle.
        """
        vv = self._mc_admin_user_add(key, secret)
        _assert_mc_success(vv, "mc.mc_admin_user_add")
        vv = self._mc_admin_policy_attach_user(key, policy)
        _assert_mc_success(vv, "mc.mc_admin_policy_attach")
        # vv = self._mc_admin_user_enable(key)
        # _assert_mc_success(vv, "mc.mc_admin_user_enable")
        pass

    def delete_secret(self, key):
        vv = self._mc_admin_user_remove(key)
        _assert_mc_success(vv, "mc.mc_admin_user_remove")
        pass

    def list_secrets(self):
        vv = self._mc_admin_user_list()
        _assert_mc_success(vv, "mc.mc_admin_user_list")
        (ok, values, message) = vv
        keys = [_intern_secret_record(e)
                for e in values]
        return keys

    def clean_minio_setting(self, pool_id):
        """Tries to delete all access-keys and set the "none"-policy to all
        buckets.  A pool_id is used only for printing messages.
        """
        failure_message = f"Cleaning MinIO state for pool={pool_id}"
        # Delete access-keys.
        try:
            keys = self.list_secrets()
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(failure_message
                        + f" failed (ignored): exception=({m})")
            keys = []
            pass
        for k in keys:
            try:
                self.delete_secret(k["access_key"])
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        # Set none-policy to buckets.
        try:
            bkts = self.list_buckets()
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(failure_message
                        + f" failed (ignored): exception=({m})")
            bkts = []
            pass
        for b in bkts:
            try:
                self.delete_bucket(b["name"])
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        pass

    def setup_minio_on_buckets(self, existingset):
        """Updates the MinIO state to match the pool state at a start of
        MinIO.  Note that the list from MinIO lacks the policy part.
        See also setup_minio_on_secrets().
        """
        force_refresh_all = False
        recordedset = self.list_buckets()
        existing = {d.get("name") for d in existingset}
        recorded = {d.get("name") for d in recordedset}
        if not force_refresh_all:
            dels = (recorded - existing)
            adds = (existing - recorded)
        else:
            dels = recorded
            adds = existing
            pass
        if (len(dels) == 0 and len(adds) == 0):
            return
        pool_id = self._pool_id
        logger.warning(f"Updating MinIO state on buckets"
                       f" for pool={pool_id}:"
                       f" delete={dels}, add={adds}")
        failure_message = f"Updating MinIO state for pool={pool_id}"
        for b in dels:
            try:
                self.delete_bucket(b)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        addset = [d for d in existingset
                  if d["name"] in adds]
        for d in addset:
            name = d["name"]
            policy = d["bkt_policy"]
            try:
                self.make_bucket(name, policy)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        pass

    def setup_minio_on_secrets(self, existingset):
        """Updates the MinIO state to match the pool state at a start of
        MinIO.  Note the list from MinIO lacks the secret-key part.
        It compares the list in MinIO and the list in the pool, and
        adds the missing ones and deletes the excess ones.  It assumes
        the association of access-key and secret-key is unchanged.
        """
        force_refresh_all = False
        recordedset = self.list_secrets()
        existing = {d.get("access_key") for d in existingset}
        recorded = {d.get("access_key") for d in recordedset}
        if not force_refresh_all:
            dels = (recorded - existing)
            adds = (existing - recorded)
        else:
            dels = recorded
            adds = existing
            pass
        if (len(dels) == 0 and len(adds) == 0):
            return
        pool_id = self._pool_id
        logger.warning(f"Updating MinIO state on access-keys"
                       f" for pool={pool_id}:"
                       f" delete={dels}, add={adds}")
        failure_message = f"Updating MinIO state for pool={pool_id}"
        for k in dels:
            try:
                self.delete_secret(k)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        addset = [d for d in existingset
                  if d["access_key"] in adds]
        for d in addset:
            key = d["access_key"]
            secret = d["secret_key"]
            policy = d["key_policy"]
            try:
                self.make_secret(key, secret, policy)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        pass

    pass
