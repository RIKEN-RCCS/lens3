"""Lens3-Api implementation. This implements pool mangement of
Lens3-Api.
"""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import inspect
import os
import sys
import time
import posixpath
import traceback
import lenticularis
from lenticularis.mc import Mc, assert_mc_success
from lenticularis.mc import intern_mc_user_info
from lenticularis.mc import intern_mc_list_entry
from lenticularis.table import get_table
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import Pool_State
from lenticularis.poolutil import gather_pool_desc
from lenticularis.poolutil import check_user_naming
from lenticularis.poolutil import access_mux
from lenticularis.poolutil import ensure_user_is_authorized
from lenticularis.poolutil import ensure_mux_is_running
from lenticularis.poolutil import ensure_pool_state
from lenticularis.poolutil import ensure_pool_owner
from lenticularis.poolutil import ensure_bucket_owner
from lenticularis.poolutil import ensure_secret_owner
from lenticularis.poolutil import get_pool_owner_for_messages
from lenticularis.poolutil import check_pool_naming
from lenticularis.poolutil import check_bucket_naming
from lenticularis.poolutil import check_pool_is_well_formed
from lenticularis.utility import get_ip_addresses
from lenticularis.utility import copy_minimal_env
from lenticularis.utility import generate_secret_key
from lenticularis.utility import pick_one
from lenticularis.utility import host_port
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger


def erase_minio_ep(tables, traceid, pool_id):
    # Clears a MinIO endpoint.
    try:
        tables.delete_minio_ep(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"delete_minio_ep failed: exception=({m})")
        pass
    try:
        tables.delete_access_timestamp(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"delete_access_timestamp failed:"
                    f" exception=({m})")
        pass
    pass


def erase_pool_data(tables, traceid, pool_id):
    # Clears database about the pool.
    path = tables.get_buckets_directory_of_pool(pool_id)
    bkts = tables.list_buckets(pool_id)
    keys = tables.list_access_keys_of_pool(pool_id)
    logger.debug(f"Deleting buckets-directory (pool={pool_id}): {path}")
    try:
        tables.delete_buckets_directory(path)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"delete_buckets_directory failed: exception=({m})")
        pass
    bktnames = [b["name"] for b in bkts]
    logger.debug(f"Deleting buckets (pool={pool_id}): {bktnames}")
    for b in bktnames:
        try:
            tables.delete_bucket(b)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_bucket failed: exception=({m})")
            pass
        pass
    keynames = [k["access_key"] for k in keys]
    logger.debug(f"Deleting access-keys pool={pool_id}: {keynames}")
    for k in keynames:
        try:
            tables.delete_id_unconditionally(k)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_id_unconditionally failed: exception=({m})")
            pass
        pass
    logger.debug(f"Deleting pool states (pool={pool_id})")
    try:
        tables.delete_pool(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"delete_pool failed: exception=({m})")
        pass
    try:
        tables.delete_pool_state(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"delete_pool_state failed: exception=({m})")
        pass
    try:
        tables.delete_id_unconditionally(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"delete_id_unconditionally failed: exception=({m})")
        pass
    pass


def make_new_pool(tables, traceid, user_id, owner_gid, path, expiration):
    now = int(time.time())
    pooldesc = {
        "pool_name": "(* given-later *)",
        "owner_uid": user_id,
        "owner_gid": owner_gid,
        "buckets_directory": path,
        "probe_key": "(* given-later *)",
        "expiration_time": expiration,
        "online_status": True,
        "modification_time": now,
    }
    pool_id = None
    probe_key = None
    try:
        pool_id = tables.make_unique_id("pool", user_id, {})
        pooldesc["pool_name"] = pool_id
        info = {"secret_key": "", "key_policy": "readwrite",
                "expiration_time": expiration}
        probe_key = tables.make_unique_id("key", pool_id, info)
        pooldesc["probe_key"] = probe_key
        (ok, holder) = tables.set_ex_buckets_directory(path, pool_id)
        if not ok:
            owner = get_pool_owner_for_messages(tables, holder)
            raise Api_Error(400, (f"Buckets-directory is already used:"
                                  f" path=({path}), holder={owner}"))
        try:
            tables.set_pool(pool_id, pooldesc)
        except Exception:
            tables.delete_buckets_directory(path)
            raise
        pass
    except Exception:
        if pool_id is not None:
            tables.delete_id_unconditionally(pool_id)
            pass
        if probe_key is not None:
            tables.delete_id_unconditionally(probe_key)
            pass
        raise
    return pool_id


class Control_Api():
    """Setting Web-API."""

    def __init__(self, api_conf):
        self._api_conf = api_conf
        assert api_conf["version"] == "v1.2"
        self._api_version = "v1.2"

        api_param = api_conf["controller"]
        self._front_hostname = api_param["front_host"]
        self._front_host_ip = get_ip_addresses(self._front_hostname)[0]
        proxies = api_param["trusted_proxies"]
        self.trusted_proxies = {addr for h in proxies
                                for addr in get_ip_addresses(h)}
        self.base_path = api_param["base_path"]
        self.claim_uid_map = api_param["claim_uid_map"]
        self._probe_access_timeout = int(api_param["probe_access_timeout"])
        self._mc_timeout = int(api_param["minio_mc_timeout"])
        self._max_pool_expiry = int(api_param["max_pool_expiry"])

        pkgdir = os.path.dirname(inspect.getfile(lenticularis))
        self.webui_dir = os.path.join(pkgdir, "webui")

        self.csrf_key = api_param["CSRF_secret_key"]

        minio_param = api_conf["minio"]
        self._bin_mc = minio_param["mc"]
        env = copy_minimal_env(os.environ)
        self._env_mc = env

        self._bad_response_delay = 1
        self.tables = get_table(api_conf["redis"])
        pass

    def _ensure_make_pool_arguments(self, user_id, pooldesc):
        """Checks the entires of buckets_directory and owner_gid.  It
        normalizes (in the posix sense) the path of a
        buckets-directory.
        """
        u = self.tables.get_user(user_id)
        assert u is not None
        groups = u.get("groups")
        # Check GID.  UID is not in the arguments.
        assert "owner_gid" in pooldesc
        gid = pooldesc["owner_gid"]
        if gid not in groups:
            raise Api_Error(403, (f"Bad group : {gid}"))
        # Check bucket-directory path.
        assert "buckets_directory" in pooldesc
        bd = pooldesc["buckets_directory"]
        path = posixpath.normpath(bd)
        if not posixpath.isabs(path):
            raise Api_Error(400, (f"Buckets-directory is not absolute:"
                                  f" path=({path})"))
        pooldesc["buckets_directory"] = path
        pass

    def _make_mc_for_pool(self, traceid, pool_id):
        """Returns an MC command instance.  It accesses a Mux to start a
        MinIO, or to keep it running for a while even when a MinIO is
        running.
        """
        logger.debug(f"Access a Mux to start Minio for pool={pool_id}.")
        status = self.access_mux_for_pool(traceid, pool_id)
        if status != 200:
            logger.error(f"Access a Mux by Api failed for pool={pool_id}:"
                         f" status={status}")
        else:
            pass
        minioproc = self.tables.get_minio_proc(pool_id)
        if minioproc is None:
            raise Api_Error(500, (f"Cannot start MinIO for pool={pool_id}:"
                                  f" status={status}"))
        else:
            pass
        ep = minioproc["minio_ep"]
        admin = minioproc["admin"]
        password = minioproc["password"]
        mc = Mc(self._bin_mc, self._env_mc, ep, pool_id, self._mc_timeout)
        try:
            mc.alias_set(admin, password)
            return mc
        except Exception:
            mc.__exit__(None, None, None)
            raise
        pass

    def map_claim_to_uid(self, claim):
        """Converts a claim data passed by REMOTE-USER to a uid.  It returns
        None if a claim is ill-formed.  It is identity if it is a
        basic-authetication data.
        """
        if self.claim_uid_map == "id":
            return claim
        elif self.claim_uid_map == "email-name":
            name, atmark, domain = claim.partition("@")
            if atmark is None:
                return None
            else:
                return name
        elif self.claim_uid_map == "map":
            return None
        else:
            assert self.claim_uid_map in {"id", "email-name", "map"}
            pass
        pass

    def check_user_is_registered(self, user_id):
        """Checks a user is known.  It does not reject disabled users to allow
        them to view the setting.
        """
        if user_id is None:
            return False
        elif not check_user_naming(user_id):
            return False
        elif self.tables.get_user(user_id) is None:
            return False
        else:
            return True
        pass

    def _set_pool_state(self, pool_id, state, reason):
        (o, _) = self.tables.get_pool_state(pool_id)
        logger.debug(f"Pool-state change pool={pool_id}: {o} to {state}")
        self.tables.set_pool_state(pool_id, state, reason)
        pass

    def _get_pool_state(self, pool_id):
        (poolstate, _) = self.tables.get_pool_state(pool_id)
        return poolstate

    def _determine_expiration_time(self):
        now = int(time.time())
        duration = self._max_pool_expiry
        return (now + duration)

    def _check_expiration_range(self, expiration):
        now = int(time.time())
        return (((now - 10) <= expiration)
                and (expiration <= (now + self._max_pool_expiry)))

    def access_mux_for_pool(self, traceid, pool_id):
        """Tries to access a Mux from Api for a pool.  It accesses an
        arbitrary Mux when no MinIO is running, which will start a new
        MinIO.
        """
        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            raise Api_Error(500, (f"Pool removed: pool={pool_id}"))

        procdesc = self.tables.get_minio_proc(pool_id)
        if procdesc is not None:
            mux_host = procdesc.get("mux_host")
            mux_port = procdesc.get("mux_port")
            ep = host_port(mux_host, mux_port)
        else:
            # Choose an arbitrary Mux.
            muxs = self.tables.list_mux_eps()
            if len(muxs) == 0:
                raise Api_Error(500, (f"No Mux services in Lens3"))
            pair = pick_one(muxs)
            assert pair is not None
            ep = host_port(pair[0], pair[1])
            pass
        assert ep is not None
        # Use probe-access key.
        access_key = pooldesc["probe_key"]
        assert access_key is not None
        status = access_mux(traceid, ep, access_key,
                            self._front_hostname, self._front_host_ip,
                            self._probe_access_timeout)
        logger.debug(f"Access Mux for pool={pool_id}: status={status}")
        return status

    # API interfaces.

    def api_return_user_info(self, traceid, user_id):
        try:
            t = self._return_user_info(user_id)
            return (200, None, {"pool_list": [t]})
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"get_user_info failed: user={user_id};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # Pools interface.

    def api_make_pool(self, traceid, user_id, body):
        pooldesc = body.get("pool")
        try:
            triple = self._api_make_pool(traceid, user_id, pooldesc)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_pool failed: user={user_id},"
                          f" pool=({pooldesc}); exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_delete_pool(self, traceid, user_id, pool_id):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool={pool_id}", None)
            self._api_delete_pool(traceid, user_id, pool_id)
            return (200, None, None)
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"delete_pool failed: user={user_id},"
                          f" pool={pool_id}; exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_list_pools(self, traceid, user_id, pool_id):
        try:
            if pool_id is None:
                pass
            elif not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", None)
            triple = self._api_list_pools(traceid, user_id, pool_id)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"list_pools failed: user={user_id}, pool={pool_id};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # Buckets interface.

    def api_make_bucket(self, traceid, user_id, pool_id, body):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", None)
            d = body.get("bucket")
            bucket = d.get("name")
            policy = d.get("bkt_policy")
            if not check_bucket_naming(bucket):
                return (403, f"Bad bucket name={bucket}", None)
            if policy not in {"none", "public", "upload", "download"}:
                return (403, f"Bad bucket policy={policy}", None)
            # assert name == bucket
        except Exception as e:
            m = rephrase_exception_message(e)
            time.sleep(self._bad_response_delay)
            return (400, m, None)
        try:
            logger.debug(f"Adding a bucket to pool={pool_id}"
                         f": name={bucket}, policy={policy}")
            triple = self._api_make_bucket(traceid, user_id, pool_id,
                                           bucket, policy)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_bucket failed: user={user_id},"
                          f" pool={pool_id}, name={bucket},"
                          f" policy={policy}; exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_delete_bucket(self, traceid, user_id, pool_id, bucket):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool={pool_id}", None)
            if not check_bucket_naming(bucket):
                return (403, f"Bad bucket name={bucket}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Deleting a bucket: {bucket}")
            triple = self._api_delete_bucket(traceid, user_id, pool_id, bucket)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"delete_bucket failed: user={user_id}"
                          f" pool={pool_id} bucket={bucket};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # Secrets interface.

    def api_make_secret(self, traceid, user_id, pool_id, body):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", None)
            rw = body.get("key_policy")
            if rw not in {"readwrite", "readonly", "writeonly"}:
                return (403, f"Bad access policy={rw}", None)
            tv = body.get("expiration_time")
            if tv is None:
                return (403, f"Bad expiration={tv}", None)
            try:
                expiration = int(tv)
            except ValueError:
                return (403, f"Bad expiration={tv}", None)
            if not self._check_expiration_range(expiration):
                return (403, f"Bad expiration={tv}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Adding a new secret: {rw}")
            triple = self._api_make_secret(traceid, user_id, pool_id, rw, expiration)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_secret failed: user={user_id},"
                          f" pool={pool_id}, policy={rw}; exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_delete_secret(self, traceid, user_id, pool_id, access_key):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", None)
            if not check_pool_naming(access_key):
                return (403, f"Bad access-key={access_key}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Deleting a secret: {access_key}")
            triple = self._api_delete_secret(traceid, user_id, pool_id,
                                                    access_key)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"delete_secret failed: user={user_id},"
                          f" pool={pool_id}, access-key={access_key};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # API implementation.

    def _return_user_info(self, user_id):
        """Returns basic information on the user needed by Web-API."""
        ensure_user_is_authorized(self.tables, user_id)
        u = self.tables.get_user(user_id)
        assert u is not None
        groups = u.get("groups")
        template = {
            "api_version": self._api_version,
            "owner_uid": user_id,
            "owner_gid": groups[0],
            "groups": groups,
        }
        return template

    # Pools handling implementation.

    def _api_make_pool(self, traceid, user_id, makepool):
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        self._ensure_make_pool_arguments(user_id, makepool)
        path = makepool["buckets_directory"]
        owner_gid = makepool["owner_gid"]
        pool_id = self.do_make_pool(traceid, user_id, owner_gid, path)
        # Return a pool description for Web-API.
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        assert pooldesc1 is not None
        try:
            check_pool_is_well_formed(pooldesc1, None)
            return (200, None, {"pool_list": [pooldesc1]})
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Created pool is not well-formed (internal error):"
                         f" pool={pool_id}; exception=({m})",
                         exc_info=True)
            raise
        pass

    def do_make_pool(self, traceid, user_id, owner_gid, path):
        expiration = self._determine_expiration_time()
        # pool_id = self.make_new_pool(tables, traceid, user_id, owner_gid, path, expiration)
        pool_id = make_new_pool(self.tables, traceid, user_id, owner_gid, path, expiration)
        self._activate_pool(traceid, pool_id)
        return pool_id

    def make_new_pool__(self, traceid, user_id, owner_gid, path, expiration):
        now = int(time.time())
        pooldesc = {
            "pool_name": "(* given-later *)",
            "owner_uid": user_id,
            "owner_gid": owner_gid,
            "buckets_directory": path,
            "probe_key": "(* given-later *)",
            "expiration_time": expiration,
            "online_status": True,
            "modification_time": now,
        }
        pool_id = None
        probe_key = None
        try:
            pool_id = self.tables.make_unique_id("pool", user_id, {})
            pooldesc["pool_name"] = pool_id
            info = {"secret_key": "", "key_policy": "readwrite",
                    "expiration_time": expiration}
            probe_key = self.tables.make_unique_id("key", pool_id, info)
            pooldesc["probe_key"] = probe_key
            (ok, holder) = self.tables.set_ex_buckets_directory(path, pool_id)
            if not ok:
                owner = get_pool_owner_for_messages(self.tables, holder)
                raise Api_Error(400, (f"Buckets-directory is already used:"
                                      f" path=({path}), holder={owner}"))
            try:
                self.tables.set_pool(pool_id, pooldesc)
            except Exception:
                self.tables.delete_buckets_directory(path)
                raise
            pass
        except Exception:
            if pool_id is not None:
                self.tables.delete_id_unconditionally(pool_id)
                pass
            if probe_key is not None:
                self.tables.delete_id_unconditionally(probe_key)
                pass
            raise
        return pool_id

    def _activate_pool(self, traceid, pool_id):
        assert pool_id is not None
        try:
            self._set_pool_state(pool_id, Pool_State.INITIAL, "-")
            self.tables.set_access_timestamp(pool_id)
        except Exception:
            self.tables.delete_pool(pool_id)
            self.tables.delete_pool_state(pool_id)
            self.tables.delete_access_timestamp(pool_id)
            raise
        try:
            status = self.access_mux_for_pool(traceid, pool_id)
        except Exception:
            self.tables.delete_pool_state(pool_id)
            self.tables.delete_pool(pool_id)
            self.tables.delete_access_timestamp(pool_id)
            raise
        else:
            pass
        self._set_pool_state(pool_id, Pool_State.READY, "-")
        poolstate = self._get_pool_state(pool_id)
        if poolstate not in {Pool_State.READY}:
            logger.error(f"Initialization error: pool-state is not ready:"
                         f" {poolstate}")
            raise Exception(f"Initialization error: pool-state is not ready:"
                            f" {poolstate}")
        pass

    def _api_delete_pool(self, traceid, user_id, pool_id):
        """Deletes a pool.  It clears buckets and access-keys set in MinIO.
        It can delete despite of the ensure_pool_state() state.
        """
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        ensure_pool_owner(self.tables, pool_id, user_id)
        # ensure_pool_state(self.tables, pool_id)
        ok = self.do_delete_pool(traceid, pool_id)
        return (200, None, None)

    def do_delete_pool(self, traceid, pool_id):
        self._clean_minio(traceid, pool_id)
        # self.erase_minio_ep(traceid, pool_id)
        # self.erase_pool_data(traceid, pool_id)
        erase_minio_ep(self.tables, traceid, pool_id)
        erase_pool_data(self.tables, traceid, pool_id)
        return True

    def _clean_minio(self, traceid, pool_id):
        # Cleans MinIO status.
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                mc.clean_minio_setting(pool_id)
                # (p_, r) = mc.admin_service_stop()
                # assert p_ is None
                # assert_mc_success(r, "mc.admin_service_stop")
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"clean_minio failed: exception=({m})",
                         exc_info=True)
            pass
        pass

    def erase_minio_ep__(self, traceid, pool_id):
        # Clears a MinIO endpoint.
        try:
            self.tables.delete_minio_ep(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_minio_ep failed: exception=({m})")
            pass
        try:
            self.tables.delete_access_timestamp(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_access_timestamp failed:"
                        f" exception=({m})")
            pass
        pass

    def erase_pool_data__(self, traceid, pool_id):
        # Clears database about the pool.
        path = self.tables.get_buckets_directory_of_pool(pool_id)
        bkts = self.tables.list_buckets(pool_id)
        keys = self.tables.list_access_keys_of_pool(pool_id)
        logger.debug(f"Deleting buckets-directory (pool={pool_id}): {path}")
        try:
            self.tables.delete_buckets_directory(path)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_buckets_directory failed: exception=({m})")
            pass
        bktnames = [b["name"] for b in bkts]
        logger.debug(f"Deleting buckets (pool={pool_id}): {bktnames}")
        for b in bktnames:
            try:
                self.tables.delete_bucket(b)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(f"delete_bucket failed: exception=({m})")
                pass
            pass
        keynames = [k["access_key"] for k in keys]
        logger.debug(f"Deleting access-keys pool={pool_id}: {keynames}")
        for k in keynames:
            try:
                self.tables.delete_id_unconditionally(k)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(f"delete_id_unconditionally failed: exception=({m})")
                pass
            pass
        logger.debug(f"Deleting pool states (pool={pool_id})")
        try:
            self.tables.delete_pool(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_pool failed: exception=({m})")
            pass
        try:
            self.tables.delete_pool_state(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_pool_state failed: exception=({m})")
            pass
        try:
            self.tables.delete_id_unconditionally(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"delete_id_unconditionally failed: exception=({m})")
            pass
        pass

    def _api_list_pools(self, traceid, user_id, pool_id):
        """It lists all pools of the user when pool-id is None."""
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        pool_list = []
        for pid in self.tables.list_pools(pool_id):
            pooldesc = gather_pool_desc(self.tables, pid)
            if pooldesc is None:
                logger.debug(f"Pool removed in race; list-pools runs"
                             f" without a lock (ignored): {pid}")
                continue
            if pooldesc["owner_uid"] != user_id:
                continue
            pool_list.append(pooldesc)
            pass
        pool_list = sorted(pool_list, key=lambda k: k["buckets_directory"])
        return (200, None, {"pool_list": pool_list})

    # Buckets handling implementation.

    def _api_make_bucket(self, traceid, user_id, pool_id, bucket, policy):
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        ensure_pool_owner(self.tables, pool_id, user_id)
        ensure_pool_state(self.tables, pool_id)
        self.do_make_bucket(traceid, pool_id, bucket, policy)
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return (200, None, {"pool_list": [pooldesc1]})

    def do_make_bucket(self, traceid, pool_id, bucket, bkt_policy):
        now = int(time.time())
        desc = {"pool": pool_id, "bkt_policy": bkt_policy,
                "modification_time": now}
        (ok, holder) = self.tables.set_ex_bucket(bucket, desc)
        if not ok:
            owner = get_pool_owner_for_messages(self.tables, holder)
            raise Api_Error(403, f"Bucket name taken: owner={owner}")
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                mc.make_bucket_with_policy(bucket, bkt_policy)
                pass
        except Exception:
            self.tables.delete_bucket(bucket)
            raise
        pass

    def _api_delete_bucket(self, traceid, user_id, pool_id, bucket):
        """Deletes a bucket.  Deleting ignores errors occur in MC commands in
        favor of disabling accesses to buckets.
        """
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        ensure_pool_owner(self.tables, pool_id, user_id)
        ensure_pool_state(self.tables, pool_id)
        ensure_bucket_owner(self.tables, bucket, pool_id)
        pooldesc1 = self.do_delete_bucket(traceid, pool_id, bucket)
        return (200, None, {"pool_list": [pooldesc1]})

    def do_delete_bucket(self, traceid, pool_id, bucket):
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                bkts0 = mc.list_buckets()
                assert_mc_success(bkts0, "mc.list_buckets")
                bkts = [intern_mc_list_entry(e) for e in bkts0]
                entry = [d for d in bkts
                         if d.get("name") == bucket]
                if entry == []:
                    logger.error(f"Inconsistency is found in MinIO and Lens3"
                                 f" in deleting a bucket:"
                                 f" pool={pool_id}, bucket={bucket}")
                else:
                    r = mc.policy_set(bucket, "none")
                    assert_mc_success(r, "mc.policy_set")
                    pass
                pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"delete_bucket failed: exception=({m})",
                         exc_info=True)
            pass
        self.tables.delete_bucket(bucket)
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    # Secrets handling implementation.

    def _api_make_secret(self, traceid, user_id, pool_id, key_policy, expiration):
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        ensure_pool_owner(self.tables, pool_id, user_id)
        ensure_pool_state(self.tables, pool_id)
        secret = generate_secret_key()
        info = {"secret_key": secret, "key_policy": key_policy,
                "expiration_time": expiration}
        key = self.tables.make_unique_id("key", pool_id, info)
        pooldesc1 = self.do_record_secret(traceid, pool_id,
                                          key, secret, key_policy)
        return (200, None, {"pool_list": [pooldesc1]})

    def do_record_secret(self, traceid, pool_id, key, secret, key_policy):
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                r = mc.admin_user_add(key, secret)
                assert_mc_success(r, "mc.admin_user_add")
                r = mc.admin_policy_set(key, key_policy)
                assert_mc_success(r, "mc.admin_policy_set")
                r = mc.admin_user_enable(key)
                assert_mc_success(r, "mc.admin_user_enable")
            pass
        except Exception:
            self.tables.delete_id_unconditionally(key)
            raise
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    def _api_delete_secret(self, traceid, user_id, pool_id, access_key):
        """Deletes a secret.  Deleting will fail when errors occur in MC
        commands.
        """
        ensure_mux_is_running(self.tables)
        ensure_user_is_authorized(self.tables, user_id)
        ensure_pool_owner(self.tables, pool_id, user_id)
        ensure_pool_state(self.tables, pool_id)
        ensure_secret_owner(self.tables, access_key, pool_id)
        pooldesc1 = self.do_delete_secret(traceid, pool_id, access_key)
        return (200, None, {"pool_list": [pooldesc1]})

    def do_delete_secret(self, traceid, pool_id, access_key):
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                keys0 = mc.admin_user_list()
                assert_mc_success(keys0, "mc.admin_user_list")
                keys = [intern_mc_user_info(e) for e in keys0]
                entry = [d for d in keys
                         if d.get("access_key") == access_key]
                if entry == []:
                    logger.error(f"Inconsistency is found in MinIO and Lens3"
                                 f" in deleting an access-key:"
                                 f" pool={pool_id}, access-key={access_key}")
                else:
                    r = mc.admin_user_remove(access_key)
                    assert_mc_success(r, "mc.admin_user_remove")
                    pass
                pass
            self.tables.delete_id_unconditionally(access_key)
        except Exception:
            raise
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    pass
