"""MinIO MC command.  It runs MC command to manage MinIO."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

"""It depends on the version of MinIO and MC.  This is for
RELEASE.2022-03-31T04-55-30Z.
"""

# NOTE: The error cause-code "BucketAlreadyOwnedByYou" returned MC
# command should be treated as not an error.

# Listing commands (such as of buckets or secrets) return records that
# are separated by newlines.  Each record includes a status=success.

# A record used in bucket listing:
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

# A record used in secret listing:
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
from lenticularis.utility import list_diff3
from lenticularis.utility import rephrase_exception_message
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


def intern_mc_user_info(record):
    """Maps key strings returned from MC to ones in Lens3."""
    mapping = _mc_user_info_json_keys
    return {mapping.get(k, k): v for (k, v) in record.items()}


def intern_mc_list_entry(record):
    """Maps key strings returned from MC to ones in Lens3.  It also drops
    a trailing slash in a bucket name."""
    mapping = _mc_list_entry_json_keys
    return {mapping.get(k, k): (remove_trailing_slash(v) if k == "key" else v)
            for (k, v) in record.items()}


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


def _get_message_in_mc_error(e):
    try:
        return e["error"]["message"]
    except Exception:
        return "(unknown error)"


class Mc():
    """MC command envirionment.  It works as a context in Python, but a
    context is created at mc_alias_set().  It uses a pool-id + random
    as an alias name.
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
                self._mc_alias_remove()
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
        self._alias = f"{self._pool_id}{random_str(12).lower()}"
        rr = self._execute_cmd("alias_set",
                               ["alias", "set", self._alias, url,
                                root_user, root_secret,
                                "--api", "S3v4"])
        if rr[0]["status"] != "success":
            self._alias = None
            raise Exception(_get_message_in_mc_error(rr[0]))
        return self

    def _mc_alias_remove(self):
        rr = self._execute_cmd("alias_remove",
                               ["alias", "remove", self._alias])
        self._alias = None
        if rr[0]["status"] != "success":
            raise Exception(_get_message_in_mc_error(rr[0]))
        pass

    def _mc_admin_info(self):
        rr = self._execute_cmd("admin_info",
                               ["admin", "info", self._alias])
        return rr

    def _mc_admin_policy_set(self, access_key, policy):
        rr = self._execute_cmd("admin_policy_set",
                               ["admin", "policy", "set", self._alias,
                                policy, f"user={access_key}"])
        return rr

    def _mc_admin_service_stop(self):
        rr = self._execute_cmd("admin_service_stop",
                               ["admin", "service", "stop", self._alias])
        return rr

    def _mc_admin_user_add(self, access_key, secret_access_key):
        rr = self._execute_cmd("admin_user_add",
                               ["admin", "user", "add", self._alias,
                                access_key, secret_access_key])
        return rr

    def _mc_admin_user_disable(self, access_key):
        rr = self._execute_cmd("admin_user_disable",
                               ["admin", "user", "disable", self._alias,
                                access_key])
        return rr

    def _mc_admin_user_enable(self, access_key):
        rr = self._execute_cmd("admin_user_enable",
                               ["admin", "user", "enable", self._alias,
                                access_key])
        return rr

    def _mc_admin_user_list(self):
        rr = self._execute_cmd("admin_user_list",
                               ["admin", "user", "list", self._alias])
        return rr

    def _mc_admin_user_remove(self, access_key):
        assert isinstance(access_key, str)
        rr = self._execute_cmd("admin_user_remove",
                               ["admin", "user", "remove", self._alias,
                                access_key])
        return rr

    def _mc_list_buckets(self):
        rr = self._execute_cmd("list_buckets",
                               ["ls", f"{self._alias}"])
        return rr

    def _mc_make_bucket(self, bucket):
        rr = self._execute_cmd("make_bucket",
                               ["mb", f"{self._alias}/{bucket}"])
        return rr

    def _mc_remove_bucket(self, bucket):
        # NEVER USE THIS; THE MC-RB COMMAND REMOVES BUCKET CONTENTS.
        assert False
        rr = self._execute_cmd("remove_bucket",
                               ["rb", f"{self._alias}/{bucket}"])
        return rr

    def _mc_policy_set(self, bucket, policy):
        rr = self._execute_cmd("policy_set",
                               ["policy", "set", policy,
                                f"{self._alias}/{bucket}"])
        return rr

    def _execute_cmd(self, name, args):
        # (Currently, it does not check the exit code of MC command.)
        assert self._alias is not None and self._config_dir is not None
        cmd = ([self.mc, "--json", f"--config-dir={self._config_dir.name}"]
               + list(args))
        assert all(isinstance(i, str) for i in cmd)
        try:
            p = Popen(cmd, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                      env=self.env)
            # if no_wait:
            #     return (p, None)
            with p:
                (outs_, errs_) = p.communicate(timeout=self._mc_timeout)
                outs = str(outs_, "latin-1")
                errs = str(errs_, "latin-1")
                p_status = p.poll()
                if (self._verbose):
                    logger.debug(f"MC command done: cmd={cmd};"
                                 f" status={p_status},"
                                 f" outs=({outs}), errs=({errs})")
                    pass
                if p_status is None:
                    logger.error(f"MC command unfinished: cmd={cmd};"
                                 f" outs=({outs}), errs=({errs})")
                    rr = [_make_mc_error(f"MC command unfinished: ({outs})")]
                    return rr
                try:
                    ss = outs.split("\n")
                    ee = [json.loads(e)
                          for e in ss if e != ""]
                    (ok, rr) = _simplify_messages_in_mc_error(ee)
                    if ok:
                        if (self._verbose):
                            logger.debug(f"MC command OK: cmd={cmd}")
                        else:
                            logger.debug(f"MC command OK: cmd={name}")
                    else:
                        logger.debug(f"MC command failed: cmd={cmd};"
                                     f" error={rr}")
                        pass
                    return rr
                except Exception as e:
                    m = rephrase_exception_message(e)
                    logger.error(f"json.loads failed: exception=({m})",
                                 exc_info=True)
                    rr = [_make_mc_error(f"Bad output from MC: ({outs})")]
                    return rr
                pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Popen failed: cmd={cmd}; exception=({m})")
            rr = [_make_mc_error(f"MC command failed:"
                                 f" exception=({m})")]
            return rr
        pass

    # MC COMMAND UTILITIES (Combinations).

    def get_minio_info(self):
        rr = self._mc_admin_info()
        assert_mc_success(rr, "mc.mc_admin_info")
        pass

    def stop_minio(self):
        rr = self._mc_admin_service_stop()
        assert_mc_success(rr, "mc.mc_admin_service_stop")
        pass

    def make_bucket(self, bucket, policy):
        """Makes a bucket in MinIO.  Making a bucket may cause an error.  It
        is because Lens3 never removes buckets but makes it
        inaccessible.
        """
        assert self._alias is not None
        try:
            r = self._mc_make_bucket(bucket)
            assert_mc_success(r, "mc.mc_make_bucket")
        except Exception:
            pass
        r = self._mc_policy_set(bucket, policy)
        assert_mc_success(r, "mc.mc_policy_set")
        pass

    def set_bucket_policy(self, bucket, policy):
        r = self._mc_policy_set(bucket, policy)
        assert_mc_success(r, "mc.mc_policy_set")
        pass


    def delete_bucket(self, bucket):
        """Makes a bucket inaccessible."""
        r = self._mc_policy_set(bucket, "none")
        assert_mc_success(r, "mc.mc_policy_set")
        pass

    def list_buckets(self):
        bkts0 = self._mc_list_buckets()
        assert_mc_success(bkts0, "mc.mc_list_buckets")
        bkts = [intern_mc_list_entry(e) for e in bkts0]
        return bkts

    def make_secret(self, key, secret, policy):
        """Makes an access key in MinIO.  Note it does not rollback on a
        failure in the middle.
        """
        r = self._mc_admin_user_add(key, secret)
        assert_mc_success(r, "mc.mc_admin_user_add")
        r = self._mc_admin_policy_set(key, policy)
        assert_mc_success(r, "mc.mc_admin_policy_set")
        r = self._mc_admin_user_enable(key)
        assert_mc_success(r, "mc.mc_admin_user_enable")
        pass

    def delete_secret(self, key):
        r = self._mc_admin_user_remove(key)
        assert_mc_success(r, "mc.mc_admin_user_remove")
        pass

    def list_secrets(self):
        keys0 = self._mc_admin_user_list()
        assert_mc_success(keys0, "mc.mc_admin_user_list")
        keys = [intern_mc_user_info(e) for e in keys0]
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
        recorded1 = self.list_buckets()
        recorded = [self._drop_auxiliary_bucket_slots(b) for b in recorded1]
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
                self.delete_bucket(b["name"])
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        for b in adds:
            try:
                self.make_bucket(b["name"], b["bkt_policy"])
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        for b in mods:
            try:
                self.set_bucket_policy(b["name"], b["bkt_policy"])
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
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
        recorded1 = self.list_secrets()
        recorded = [self._drop_auxiliary_key_slots(k) for k in recorded1]
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
                self.delete_secret(k["access_key"])
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(failure_message
                            + f" failed (ignored): exception=({m})")
                pass
            pass
        for k in adds:
            key = k["access_key"]
            secret = k["secret_key"]
            policy = k["key_policy"]
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
