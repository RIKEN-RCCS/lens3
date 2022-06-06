"""Pool mangement.  This implements operations of Adm."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import time
import posixpath
import traceback
from lenticularis.mc import Mc, assert_mc_success
from lenticularis.mc import intern_mc_user_info
from lenticularis.mc import intern_mc_list_entry
from lenticularis.table import get_tables
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import Pool_State
from lenticularis.poolutil import gather_pool_desc
from lenticularis.poolutil import check_user_naming
from lenticularis.utility import copy_minimal_env
from lenticularis.utility import generate_secret_key
from lenticularis.utility import logger
from lenticularis.utility import pick_one
from lenticularis.utility import access_mux, host_port
from lenticularis.poolutil import check_pool_is_well_formed


def rephrase_exception_message(e):
    """Returns an error message of an AssertionError.  It is needed
    because simply printing an AssertionError returns an empty string.
    """
    if not isinstance(e, AssertionError):
        return f"{e}"
    else:
        (_, _, tb) = sys.exc_info()
        tr = traceback.extract_tb(tb)
        (_, _, _, text) = tr[-1]
        return f"AssertionError: {text}"
    pass


class Pool_Admin():

    def __init__(self, adm_conf):
        self.adm_conf = adm_conf

        mux_param = adm_conf["multiplexer"]
        self._facade_hostname = mux_param["facade_hostname"]
        self._probe_access_timeout = int(mux_param["probe_access_timeout"])

        # ctl_param = adm_conf["minio_manager"]

        settings = adm_conf["system"]
        self._max_pool_expiry = int(settings["max_pool_expiry"])

        self.tables = get_tables(adm_conf)

        minio_param = adm_conf["minio"]
        self._bin_mc = minio_param["mc"]
        env = copy_minimal_env(os.environ)
        self._env_mc = env
        return

    def _get_pool_owner_for_messages(self, pool_id):
        """Finds an owner of a pool for printing a error message.  It returns
        unknown-user, when not owner is found.
        """
        if pool_id is None:
            return "unknown-user"
        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            return "unknown-user"
        return pooldesc.get("owner_uid")

    def _ensure_user_is_authorized(self, user_id):
        u = self.tables.get_user(user_id)
        assert u is not None
        if not u.get("permitted"):
            raise Api_Error(403, (f"A user disabled: {user_id}"))
        pass

    def _ensure_mux_is_running(self):
        muxs = self.tables.list_mux_eps()
        if len(muxs) == 0:
            raise Api_Error(500, (f"No Mux services in Lens3"))
        pass

    def _ensure_pool_state(self, pool_id):
        (poolstate, _) = self.tables.get_pool_state(pool_id)
        if poolstate != Pool_State.READY:
            if poolstate == Pool_State.DISABLED:
                raise Api_Error(403, f"Pool is disabled")
            elif poolstate == Pool_State.INOPERABLE:
                raise Api_Error(500, f"Pool is inoperable")
            else:
                raise Api_Error(500, f"Pool is in {poolstate}")
            pass
        pass

    def _ensure_pool_owner(self, pool_id, user_id):
        # owner = self._get_pool_owner_for_messages(pool_id)
        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            raise Api_Error(403, (f"Non-existing pool: {pool_id}"))
        if pooldesc.get("owner_uid") != user_id:
            raise Api_Error(403, (f"Not an owner of the pool: {pool_id}"))
        pass

    def _ensure_bucket_owner(self, bucket, pool_id):
        desc = self.tables.get_bucket(bucket)
        if desc is None:
            raise Api_Error(403, f"Non-exisiting bucket: {bucket}")
        if desc.get("pool") != pool_id:
            raise Api_Error(403, (f"A bucket for a wrong pool: {bucket}"))
        pass

    def _ensure_secret_owner(self, access_key, pool_id):
        desc = self.tables.get_id(access_key)
        if desc is None:
            raise Api_Error(403, f"Non-existing access-key: {access_key}")
        if not (desc.get("use") == "access_key"
                and desc.get("owner") == pool_id):
            raise Api_Error(403, f"A wrong access-key: {access_key}")
        pass

    def _ensure_make_pool_arguments(self, user_id, pooldesc):
        """It normalizes the bucket-directory path."""
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
        MinIO, even when a MinIO is running, to keep it running for a
        while.
        """
        logger.debug(f"Access a Mux to start Minio for pool={pool_id}.")
        status = self.access_mux_for_pool(traceid, pool_id)
        if status != 200:
            logger.error(f"Access a Mux by Adm failed for pool={pool_id}:"
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
        mc = Mc(self._bin_mc, self._env_mc, ep, pool_id)
        try:
            mc.alias_set(admin, password)
            return mc
        except Exception:
            mc.__exit__(None, None, None)
            raise
        pass

    def check_user_is_registered(self, user_id):
        """Checks a user is known.  It does not reject disabled-state users to
        allow them to view the setting.
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
        logger.debug(f"pool-state change pool={pool_id}: {o} to {state}")
        self.tables.set_pool_state(pool_id, state, reason)
        pass

    def _get_pool_state(self, pool_id):
        (poolstate, _) = self.tables.get_pool_state(pool_id)
        return poolstate

    def _determine_expiration_date(self):
        now = int(time.time())
        duration = self._max_pool_expiry
        return (now + duration)

    def access_mux_for_pool(self, traceid, pool_id):
        """Tries to access a Mux of the pool.  It accesses an arbitrary Mux
        when no MinIO is running, which will start a new MinIO.
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
        access_key = pooldesc["probe_access"]
        assert access_key is not None
        facade_hostname = self._facade_hostname
        status = access_mux(traceid, ep, access_key, facade_hostname,
                            self._probe_access_timeout)
        logger.debug(f"Access Mux for pool={pool_id}: status={status}")
        return status

    # Web-UI Interface.

    def return_user_template(self, user_id):
        """Returns basic information on the user needed by Web-UI."""
        self._ensure_user_is_authorized(user_id)
        u = self.tables.get_user(user_id)
        assert u is not None
        groups = u.get("groups")
        template = {
            "owner_uid": user_id,
            "owner_gid": groups[0],
            "groups": groups,
            "buckets_directory": "",
            "buckets": [],
            "access_keys": [
                   {"key_policy": "readwrite"},
                   {"key_policy": "readonly"},
                   {"key_policy": "writeonly"}],
            "expiration_date": self._determine_expiration_date(),
            "permit_status": True,
            "online_status": True,
            "atime": "0",
        }
        return template

    # POOLS.

    def make_pool_ui(self, traceid, user_id, makepool):
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        self._ensure_make_pool_arguments(user_id, makepool)
        path = makepool["buckets_directory"]
        owner_gid = makepool["owner_gid"]
        pool_id = self.do_make_pool(traceid, user_id, owner_gid, path)
        # Return a pool description for Web-UI.
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        assert pooldesc1 is not None
        try:
            check_pool_is_well_formed(pooldesc1, None)
            return (200, None, {"pool_list": [pooldesc1]})
        except Exception as e:
            logger.error(f"Created pool is not well-formed (internal error):"
                         f" pool={pool_id} exception=({e})",
                         exc_info=True)
            raise
        pass

    def do_make_pool(self, traceid, user_id, owner_gid, path):
        now = int(time.time())
        newpool = {
            "pool_name": "(* given-later *)",
            "owner_uid": user_id,
            "owner_gid": owner_gid,
            "buckets_directory": path,
            "probe_access": "(* given-later *)",
            "expiration_date": self._determine_expiration_date(),
            "online_status": True,
            "modification_time": now,
        }
        pool_id = None
        probe_key = None
        try:
            pool_id = self.tables.make_unique_id("pool", user_id)
            newpool["pool_name"] = pool_id
            info = {"secret_key": "", "key_policy": "readwrite"}
            probe_key = self.tables.make_unique_id("access_key", pool_id, info)
            newpool["probe_access"] = probe_key
            (ok, holder) = self.tables.set_ex_buckets_directory(path, pool_id)
            if not ok:
                owner = self._get_pool_owner_for_messages(holder)
                raise Api_Error(400, (f"Buckets-directory is already used:"
                                      f" path=({path}), holder={owner}"))
            try:
                self._store_pool(traceid, user_id, newpool)
            except:
                self.tables.delete_buckets_directory(path)
                raise
            pass
        except:
            if pool_id is not None:
                self.tables.delete_id_unconditionally(pool_id)
                pass
            if probe_key is not None:
                self.tables.delete_id_unconditionally(probe_key)
                pass
            raise
        return pool_id

    def _store_pool(self, traceid, user_id, pooldesc0):
        pool_id = pooldesc0["pool_name"]
        assert pool_id is not None
        try:
            self.tables.set_pool(pool_id, pooldesc0)
            self._set_pool_state(pool_id, Pool_State.INITIAL, "-")
            self.tables.set_access_timestamp(pool_id)
        except:
            self.tables.delete_pool(pool_id)
            self.tables.delete_pool_state(pool_id)
            self.tables.delete_access_timestamp(pool_id)
            raise
        try:
            status = self.access_mux_for_pool(traceid, pool_id)
        except:
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

    def delete_pool_ui(self, traceid, user_id, pool_id):
        """Deletes a pool.  It clears buckets and access-keys set in MinIO.
        """
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        self._ensure_pool_owner(pool_id, user_id)
        self._ensure_pool_state(pool_id)
        ok = self.do_delete_pool(traceid, pool_id)
        return (200, None, {})

    def do_delete_pool(self, traceid, pool_id):
        self._clean_minio(traceid, pool_id)
        self._clean_database(traceid, pool_id)
        return True

    def _clean_minio(self, traceid, pool_id):
        # Clean MinIO and stop.
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                mc.clean_minio_setting(pool_id)
                # (p_, r) = mc.admin_service_stop()
                # assert p_ is None
                # assert_mc_success(r, "mc.admin_service_stop")
        except Exception as e:
            logger.error(f"Exception in delete_pool: exception={e}",
                         exc_info=True)
            pass
        # Delete a route.
        try:
            self.tables.delete_route(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_route: exception={e}")
            pass
        try:
            self.tables.delete_access_timestamp(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_access_timestamp: exception={e}")
            pass
        pass

    def _clean_database(self, traceid, pool_id):
        # Clean database.
        path = self.tables.get_buckets_directory_of_pool(pool_id)
        bkts = self.tables.list_buckets(pool_id)
        keys = self.tables.list_access_keys_of_pool(pool_id)
        logger.debug(f"Deleting buckets-directory: {path}")
        try:
            self.tables.delete_buckets_directory(path)
        except Exception as e:
            logger.info(f"Exception in delete_buckets_directory: {e}")
            pass
        bktnames = [b["name"] for b in bkts]
        logger.debug(f"Deleting buckets: {bktnames}")
        for b in bktnames:
            try:
                self.tables.delete_bucket(b)
            except Exception as e:
                logger.info(f"Exception in delete_bucket: {e}")
                pass
            pass
        keynames = [k["access_key"] for k in keys]
        logger.debug(f"Deleting access-keys: {keynames}")
        for k in keynames:
            try:
                self.tables.delete_id_unconditionally(k)
            except Exception as e:
                logger.info(f"Exception in delete_id_unconditionally: {e}")
                pass
            pass
        logger.debug(f"Deleting pool states")
        try:
            self.tables.delete_pool(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_pool: {e}")
            pass
        try:
            self.tables.delete_pool_state(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_pool_state: {e}")
            pass
        try:
            self.tables.delete_id_unconditionally(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_id_unconditionally: {e}")
            pass
        pass

    def list_pools_ui(self, traceid, user_id, pool_id):
        """It lists all pools of the user when pool-id is None."""
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        pool_list = []
        for id in self.tables.list_pools(pool_id):
            pooldesc = gather_pool_desc(self.tables, id)
            if pooldesc is None:
                logger.debug(f"Pool removed in race; list-pools runs"
                             f" without a lock (ignored): {id}")
                continue
            if pooldesc["owner_uid"] != user_id:
                continue
            pool_list.append(pooldesc)
            pass
        pool_list = sorted(pool_list, key=lambda k: k["buckets_directory"])
        return (200, None, {"pool_list": pool_list})

    # BUCKETS.

    def make_bucket_ui(self, traceid, user_id, pool_id, bucket, policy):
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        self._ensure_pool_owner(pool_id, user_id)
        self._ensure_pool_state(pool_id)
        self.do_make_bucket(traceid, pool_id, bucket, policy)
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return (200, None, {"pool_list": [pooldesc1]})

    def do_make_bucket(self, traceid, pool_id, bucket, bkt_policy):
        now = int(time.time())
        desc = {"pool": pool_id, "bkt_policy": bkt_policy,
                "modification_time": now}
        (ok, holder) = self.tables.set_ex_bucket(bucket, desc)
        if not ok:
            owner = self._get_pool_owner_for_messages(holder)
            raise Api_Error(403, f"Bucket name taken: owner={owner}")
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                #lock = LockDB(self.tables.storage_table, "Adm")
                #self._lock_pool_entry(lock, pool_id)
                try:
                    mc.make_bucket_with_policy(bucket, bkt_policy)
                    #pooldesc = self.tables.storage_table.get_pool(pool_id)
                    #_add_bucket_to_pool(pooldesc, bucket, bkt_policy)
                    #check_pool_is_well_formed(pooldesc, None)
                    #self.tables.storage_table.set_pool(pool_id, pooldesc)
                finally:
                    #self._unlock_pool_entry(lock, pool_id)
                    pass
                pass
            pass
        except:
            self.tables.delete_bucket(bucket)
            raise
        pass

    def delete_bucket_ui(self, traceid, user_id, pool_id, bucket):
        """Deletes a bucket.  Deleting ignores errors occur in MC commands in
        favor of disabling accesses to buckets.
        """
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        self._ensure_pool_owner(pool_id, user_id)
        self._ensure_pool_state(pool_id)
        self._ensure_bucket_owner(bucket, pool_id)
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
            logger.error(f"Exception in delete_bucket: exception={e}",
                         exc_info=True)
            pass
        self.tables.delete_bucket(bucket)
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    # SECRETS.

    def make_secret_ui(self, traceid, user_id, pool_id, key_policy):
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        self._ensure_pool_owner(pool_id, user_id)
        self._ensure_pool_state(pool_id)
        secret = generate_secret_key()
        info = {"secret_key": secret, "key_policy": key_policy}
        key = self.tables.make_unique_id("access_key", pool_id, info)
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
        except:
            self.tables.delete_id_unconditionally(key)
            raise
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    def delete_secret_ui(self, traceid, user_id, pool_id, access_key):
        """Deletes a secret.  Deleting will fail when errors occur in MC
        commands.
        """
        self._ensure_mux_is_running()
        self._ensure_user_is_authorized(user_id)
        self._ensure_pool_owner(pool_id, user_id)
        self._ensure_pool_state(pool_id)
        self._ensure_secret_owner(access_key, pool_id)
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
        except:
            raise
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    pass
