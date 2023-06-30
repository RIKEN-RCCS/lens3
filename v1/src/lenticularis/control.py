"""Lens3-Api implementation.  This implements pool mangement API.
"""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import time
import posixpath
import inspect
import lenticularis
from lenticularis.mc import Mc
from lenticularis.table import get_table
from lenticularis.pooldata import Pool_State
from lenticularis.pooldata import Api_Error
from lenticularis.pooldata import Pool_State, Pool_Reason
from lenticularis.pooldata import set_pool_state
from lenticularis.pooldata import gather_pool_desc
from lenticularis.pooldata import check_user_naming
from lenticularis.pooldata import access_mux
from lenticularis.pooldata import ensure_user_is_authorized
from lenticularis.pooldata import ensure_mux_is_running
from lenticularis.pooldata import ensure_pool_state
from lenticularis.pooldata import ensure_pool_owner
from lenticularis.pooldata import ensure_bucket_owner
from lenticularis.pooldata import ensure_secret_owner_only
from lenticularis.pooldata import get_pool_owner_for_messages
from lenticularis.pooldata import check_pool_naming
from lenticularis.pooldata import check_bucket_naming
from lenticularis.pooldata import check_pool_is_well_formed
from lenticularis.utility import get_ip_addresses
from lenticularis.utility import copy_minimal_environ
from lenticularis.utility import generate_secret_key
from lenticularis.utility import pick_one
from lenticularis.utility import host_port
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger


def erase_minio_ep(tables, pool_id):
    """Clears a MinIO endpoint."""
    try:
        tables.delete_minio_ep(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"Api (pool={pool_id}) delete_minio_ep failed:"
                    f" exception=({m})")
        pass
    try:
        tables.delete_access_timestamp(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"Api (pool={pool_id}) delete_access_timestamp failed:"
                    f" exception=({m})")
        pass
    pass


def erase_pool_data(tables, pool_id):
    """Clears database about the pool."""
    path = tables.get_buckets_directory_of_pool(pool_id)
    bkts = tables.list_buckets(pool_id)
    keys = tables.list_secrets_of_pool(pool_id)
    logger.debug(f"Api (pool={pool_id}) Deleting buckets-directory: {path}")
    try:
        tables.delete_buckets_directory(path)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"Api (pool={pool_id}) delete_buckets_directory failed:"
                    f" exception=({m})")
        pass
    bktnames = [b["name"] for b in bkts]
    logger.debug(f"Api (pool={pool_id}) Deleting buckets: {bktnames}")
    for b in bktnames:
        try:
            tables.delete_bucket(b)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_bucket failed:"
                        f" exception=({m})")
            pass
        pass
    keynames = [k["access_key"] for k in keys]
    logger.debug(f"Api (pool={pool_id}) Deleting access-keys: {keynames}")
    for k in keynames:
        try:
            tables.delete_xid_unconditionally("akey", k)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_xid failed:"
                        f" exception=({m})")
            pass
        pass
    logger.debug(f"Api (pool={pool_id}) Deleting pool states")
    try:
        tables.delete_pool(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"Api (pool={pool_id}) delete_pool failed:"
                    f" exception=({m})")
        pass
    try:
        tables.delete_pool_state(pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"Api (pool={pool_id}) delete_pool_state failed:"
                    f" exception=({m})")
        pass
    try:
        tables.delete_xid_unconditionally("pool", pool_id)
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.info(f"Api (pool={pool_id}) delete_xid failed: exception=({m})")
        pass
    pass


def list_user_pools(tables, uid, pool_id):
    """Lists pools owned by a user.  It checks the owner of a pool if
    pooi-id is given.
    """
    pools = tables.list_pools(pool_id)
    pids = [pid for pid in pools
            for p in [tables.get_pool(pid)]
            if p is not None and p.get("owner_uid") == uid]
    return pids


def _make_new_pool(tables, path, user_id, owner_gid, expiration):
    now = int(time.time())
    desc = {
        "pool_name": "(* given-later *)",
        "buckets_directory": path,
        "owner_uid": user_id,
        "owner_gid": owner_gid,
        "probe_key": "(* given-later *)",
        "expiration_time": expiration,
        "online_status": True,
        "modification_time": now,
    }
    pool_id = None
    probe_key = None
    try:
        pool_id = tables.make_unique_xid("pool", user_id, {})
        desc["pool_name"] = pool_id
        info = {"secret_key": "", "key_policy": "readwrite",
                "expiration_time": expiration}
        probe_key = tables.make_unique_xid("akey", pool_id, info)
        desc["probe_key"] = probe_key
        (ok, holder) = tables.set_ex_buckets_directory(path, pool_id)
        if not ok:
            owner = get_pool_owner_for_messages(tables, holder)
            raise Api_Error(400, (f"Buckets-directory is already used:"
                                  f" path=({path}), holder={owner}"))
        try:
            tables.set_pool(pool_id, desc)
        except Exception:
            tables.delete_buckets_directory(path)
            raise
        pass
    except Exception:
        if pool_id is not None:
            tables.delete_xid_unconditionally("pool", pool_id)
            pass
        if probe_key is not None:
            tables.delete_xid_unconditionally("akey", probe_key)
            pass
        raise
    assert pool_id is not None
    set_pool_state(tables, pool_id, Pool_State.INITIAL, Pool_Reason.NORMAL)
    return pool_id


class Control_Api():
    """Management Web-API."""

    def __init__(self, api_conf, redis):
        self._api_conf = api_conf
        assert api_conf["version"] == "v1.2"
        self._lens3_version = "v1.2.1"
        self._api_version = "v1.2"

        self.pkg_dir = os.path.dirname(inspect.getfile(lenticularis))

        api_param = api_conf["controller"]
        self._front_host = api_param["front_host"]
        self._front_host_ip = get_ip_addresses(self._front_host)[0]
        proxies = api_param["trusted_proxies"]
        self.trusted_proxies = {addr for h in proxies
                                for addr in get_ip_addresses(h)}
        self.base_path = api_param["base_path"]
        self.claim_uid_map = api_param["claim_uid_map"]
        self._probe_access_timeout = int(api_param["probe_access_timeout"])
        self._mc_timeout = int(api_param["minio_mc_timeout"])
        self._max_pool_expiry = int(api_param["max_pool_expiry"])
        self.csrf_key = api_param["csrf_secret_seed"]

        ui_param = api_conf["ui"]
        self._s3_url = ui_param.get("s3_url", "")
        self._footer_banner = ui_param.get("footer_banner", "").strip()

        minio_param = api_conf["minio"]
        self._bin_mc = minio_param["mc"]
        env = copy_minimal_environ(os.environ)
        self._env_mc = env

        self._bad_response_delay = 1
        self.tables = get_table(redis)
        pass

    def _check_make_pool_arguments(self, user_id, pooldesc):
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

    def map_claim_to_uid(self, claim):
        """Converts a claim data passed by REMOTE-USER to a uid.  It returns
        None if a claim is badly formed or not found.  It is an
        identity map if configured with claim_uid_map=id.
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
            uid = self.tables.get_claim_user(claim)
            return uid
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

    # def _set_pool_state(self, pool_id, state, reason):
    #     (o, _, _) = self.tables.get_pool_state(pool_id)
    #     logger.debug(f"Pool-state change pool={pool_id}: {o} to {state}")
    #     self.tables.set_pool_state(pool_id, state, reason)
    #     pass

    # def _get_pool_state(self, pool_id):
    #     (state, _, _) = self.tables.get_pool_state(pool_id)
    #     return state

    def _determine_expiration_time(self):
        now = int(time.time())
        duration = self._max_pool_expiry
        return (now + duration)

    def _check_expiration_range(self, expiration):
        now = int(time.time())
        return (((now - 10) <= expiration)
                and (expiration <= (now + self._max_pool_expiry)))

    def _grant_access(self, user_id, pool_id, check_pool_state):
        """Checks an access to a pool is granted.  It does not check the
        pool-state on deleting a pool.
        """
        tables = self.tables
        ensure_mux_is_running(tables)
        ensure_user_is_authorized(tables, user_id)
        if pool_id is not None:
            ensure_pool_owner(tables, pool_id, user_id)
            pass
        if pool_id is not None and check_pool_state:
            ensure_pool_state(tables, pool_id, True)
            pass
        pass

    def access_mux_by_pool(self, pool_id):
        """Tries to access a Mux from Api for a pool.  It will start MinIO as
        a result.  It accesses an arbitrary Mux when no MinIO is
        running, which will start a new MinIO.
        """
        pooldesc = self.tables.get_pool(pool_id)
        if pooldesc is None:
            raise Api_Error(404, (f"Pool removed: pool={pool_id}"))

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
        # Use a probe-access key.
        access_key = pooldesc["probe_key"]
        assert access_key is not None
        status = access_mux(ep, access_key,
                            self._front_host, self._front_host_ip,
                            self._probe_access_timeout)
        logger.debug(f"Api (pool={pool_id}) Accessing a Mux done:"
                     f" status={status}")
        if status != 200:
            logger.error(f"Api (pool={pool_id}) Accessing a Mux failed:"
                         f" status={status}")
            pass
        return status

    def _activate_minio(self, pool_id, accept_failure):
        """Starts MinIO by accessing a Mux.  Failing to start MinIO is
        accepted in creating a pool, and a failure is indicated in the
        pool-state.  Otherwise, starting MinIO is a precondition to
        command execution, and a failure triggers an exception with
        code=503.
        """
        tables = self.tables
        status = self.access_mux_by_pool(pool_id)
        if accept_failure:
            (state, _, _) = tables.get_pool_state(pool_id)
            if state not in {Pool_State.READY}:
                logger.warn(f"Api (pool={pool_id}) Initialization failed:"
                            f" pool-state is not ready: {state}")
                pass
            pass
        else:
            minio = tables.get_minio_proc(pool_id)
            if minio is None:
                logger.error(f"Api (pool={pool_id}) Starting MinIO failed:"
                             f" status={status}")
                raise Api_Error(503, (f"Cannot start MinIO for pool={pool_id}:"
                                      f" status={status}"))
            pass
        pass

    # def _activate_minio__(self, pool_id):
    #     """Starts MinIO as it is a precondition to command execution.  A
    #     failure to start MinIO raises an exception with code=503.
    #     """
    #     tables = self.tables
    #     logger.debug(f"Api (pool={pool_id}) Accessing a Mux to start Minio.")
    #     status = self.access_mux_by_pool(pool_id)
    #     minioproc = tables.get_minio_proc(pool_id)
    #     if minioproc is None:
    #         logger.error(f"Api (pool={pool_id}) Starting MinIO failed:"
    #                      f" status={status}"))
    #         raise Api_Error(503, (f"Cannot start MinIO for pool={pool_id}:"
    #                               f" status={status}"))
    #     pass

    def _make_mc_for_pool(self, pool_id):
        """Returns an MC command instance.  It assumes MinIO is already
        started by _activate_minio().
        """
        # """Returns an MC command instance.  It first accesses a Mux to start
        # MinIO or to keep it running for a while.  A failure to start
        # MinIO raises an exception with code=503.
        # """
        # logger.debug(f"Api (pool={pool_id}) Accessing a Mux to start Minio.")
        # status = self.access_mux_by_pool(pool_id)
        minioproc = self.tables.get_minio_proc(pool_id)
        if minioproc is None:
            raise Api_Error(503, f"Cannot start MinIO for pool={pool_id}")
        else:
            pass
        ep = minioproc["minio_ep"]
        admin = minioproc["admin"]
        password = minioproc["password"]
        mc = Mc(self._bin_mc, self._env_mc, ep, pool_id, self._mc_timeout)
        try:
            mc.mc_alias_set(admin, password)
            return mc
        except Exception:
            mc.__exit__(None, None, None)
            raise
        pass

    # Query interface.

    def api_get_user_info(self, user_id):
        """Returns group information of a user."""
        try:
            info = self._api_get_user_info(user_id)
            return (200, None, info)
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api () get_user_info failed:"
                          f" user={user_id}; exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # Pools interface.

    def api_list_pools(self, user_id, pool_id):
        """Returns a pool or a list of pools of a user when pool-id is None.
        """
        try:
            if pool_id is None:
                pass
            elif not check_pool_naming(pool_id):
                raise Api_Error(403, f"Bad pool-id={pool_id}", None)
            triple = self._api_list_pools(user_id, pool_id)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (pool={pool_id}) list_pools failed:"
                          f" user={user_id}; exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_make_pool(self, user_id, body):
        argument_keys = {"buckets_directory", "owner_gid"}
        try:
            if (set(body.keys()) != argument_keys):
                raise Api_Error(403, f"Bad make_pool argument={body}", None)
            triple = self._api_make_pool(user_id, body)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (user={user_id}) make_pool failed:"
                          f" args=({body}); exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_delete_pool(self, user_id, pool_id):
        """Deletes a pool.  It clears buckets and access-keys set in MinIO.
        It deletes a pool despite of the ensure_pool_state() state.
        """
        try:
            if not check_pool_naming(pool_id):
                raise Api_Error(403, f"Bad pool={pool_id}", None)
            self._api_delete_pool(user_id, pool_id)
            return (200, None, None)
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (pool={pool_id}) delete_pool failed:"
                          f" user={user_id}; exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # Buckets interface.

    def api_make_bucket(self, user_id, pool_id, body):
        argument_keys = {"name", "bkt_policy"}
        bucket = None
        policy = None
        try:
            if not check_pool_naming(pool_id):
                raise Api_Error(403, f"Bad pool-id={pool_id}", None)
            if (set(body.keys()) != argument_keys):
                raise Api_Error(403, f"Bad make_bucket argument={body}", None)
            bucket = body.get("name")
            policy = body.get("bkt_policy")
            if not check_bucket_naming(bucket):
                raise Api_Error(403, f"Bad bucket name={bucket}", None)
            if policy not in {"none", "public", "upload", "download"}:
                raise Api_Error(403, f"Bad bucket policy={policy}", None)
            logger.debug(f"Api (pool={pool_id}) Adding a bucket:"
                         f" name={bucket}, policy={policy}")
            triple = self._api_make_bucket(user_id, pool_id, bucket, policy)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (pool={pool_id}) make_bucket failed:"
                          f" user={user_id}, args={body};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_delete_bucket(self, user_id, pool_id, bucket):
        """Deletes a bucket.  Deleting ignores errors occur in MC commands in
        favor of disabling accesses to buckets.
        """
        try:
            if not check_pool_naming(pool_id):
                raise Api_Error(403, f"Bad pool={pool_id}", None)
            if not check_bucket_naming(bucket):
                raise Api_Error(403, f"Bad bucket name={bucket}", None)
            logger.debug(f"Api (pool={pool_id}) Deleting a bucket: {bucket}")
            triple = self._api_delete_bucket(user_id, pool_id, bucket)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (pool={pool_id}) delete_bucket failed:"
                          f" user={user_id}, bucket={bucket};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # Secrets interface.

    def api_make_secret(self, user_id, pool_id, body):
        argument_keys = {"key_policy", "expiration_time"};
        rw = None
        expiration = None
        try:
            if not check_pool_naming(pool_id):
                raise Api_Error(403, f"Bad pool-id={pool_id}", None)
            if (set(body.keys()) != argument_keys):
                raise Api_Error(403, f"Bad make_secret argument={body}", None)
            rw = body.get("key_policy")
            if rw not in {"readwrite", "readonly", "writeonly"}:
                raise Api_Error(403, f"Bad access policy={rw}", None)
            tv = body.get("expiration_time")
            if tv is None:
                raise Api_Error(403, f"Bad expiration={tv}", None)
            try:
                expiration = int(tv)
            except ValueError:
                raise Api_Error(403, f"Bad expiration={tv}", None)
            if not self._check_expiration_range(expiration):
                raise Api_Error(403, f"Bad range expiration={tv}", None)
            logger.debug(f"Api (pool={pool_id}) Adding a new secret: {rw}")
            triple = self._api_make_secret(user_id, pool_id, rw, expiration)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (pool={pool_id}) make_secret failed:"
                          f" user={user_id}, args={body};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    def api_delete_secret(self, user_id, pool_id, access_key):
        """Deletes a secret.  Deleting will fail when errors occur in MC
        commands.
        """
        try:
            if not check_pool_naming(pool_id):
                raise Api_Error(403, f"Bad pool-id={pool_id}", None)
            if not check_pool_naming(access_key):
                raise Api_Error(403, f"Bad access-key={access_key}", None)
            logger.debug(f"Api (pool={pool_id}) Deleting a secret:"
                         f" {access_key}")
            triple = self._api_delete_secret(user_id, pool_id, access_key)
            return triple
        except Api_Error as e:
            time.sleep(self._bad_response_delay)
            return (e.code, f"{e}", None)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"Api (pool={pool_id}) delete_secret failed:"
                          f" user={user_id}, key={access_key};"
                          f" exception=({m})"),
                         exc_info=True)
            time.sleep(self._bad_response_delay)
            return (500, m, None)
        pass

    # API implementation.

    def _api_get_user_info(self, user_id):
        self._grant_access(user_id, None, False)
        u = self.tables.get_user(user_id)
        assert u is not None
        groups = u.get("groups")
        info = {
            "api_version": self._api_version,
            "uid": user_id,
            "groups": groups,
            "lens3_version": self._lens3_version,
            "s3_url": self._s3_url,
            "footer_banner": self._footer_banner,
        }
        return {"user_info": info}

    # Pools handling implementation.

    def _api_make_pool(self, user_id, makepool):
        self._grant_access(user_id, None, False)
        self._check_make_pool_arguments(user_id, makepool)
        path = makepool["buckets_directory"]
        owner_gid = makepool["owner_gid"]
        pool_id = self._do_make_pool(path, user_id, owner_gid)
        # Return a pool description for Web-API.
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        assert pooldesc1 is not None
        try:
            check_pool_is_well_formed(pooldesc1, None)
            return (200, None, {"pool_desc": pooldesc1})
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Api (pool={pool_id})"
                         f" Created pool is not well-formed (internal error):"
                         f" exception=({m})",
                         exc_info=True)
            raise
        pass

    def _do_make_pool(self, path, uid, gid):
        tables = self.tables
        expiration = self._determine_expiration_time()
        pool_id = _make_new_pool(tables, path, uid, gid, expiration)
        self._activate_minio(pool_id, True)
        return pool_id

    def _api_delete_pool(self, user_id, pool_id):
        self._grant_access(user_id, pool_id, False)
        ok = self._do_delete_pool(pool_id)
        return (200, None, None)

    def _do_delete_pool(self, pool_id):
        self._clean_minio(pool_id)
        erase_minio_ep(self.tables, pool_id)
        erase_pool_data(self.tables, pool_id)
        return True

    def _clean_minio(self, pool_id):
        """Cleans MinIO status."""
        try:
            self._activate_minio(pool_id, False)
            mc = self._make_mc_for_pool(pool_id)
            assert mc is not None
            with mc:
                mc.clean_minio_setting(pool_id)
                # (p_, r) = mc.admin_service_stop()
                # assert p_ is None
                # assert_mc_success(r, "mc.admin_service_stop")
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Api (pool={pool_id}) clean_minio failed:"
                         f" exception=({m})",
                         exc_info=True)
            pass
        pass

    def erase_minio_ep__(self, pool_id):
        """Clears a MinIO endpoint."""
        try:
            self.tables.delete_minio_ep(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_minio_ep failed:"
                        f" exception=({m})")
            pass
        try:
            self.tables.delete_access_timestamp(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_access_timestamp failed:"
                        f" exception=({m})")
            pass
        pass

    def erase_pool_data__(self, pool_id):
        # Clears database about the pool.
        path = self.tables.get_buckets_directory_of_pool(pool_id)
        bkts = self.tables.list_buckets(pool_id)
        keys = self.tables.list_secrets_of_pool(pool_id)
        logger.debug(f"Api (pool={pool_id}) Deleting buckets-directory:"
                     f" {path}")
        try:
            self.tables.delete_buckets_directory(path)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_buckets_directory"
                        f" failed: exception=({m})")
            pass
        bktnames = [b["name"] for b in bkts]
        logger.debug(f"Api (pool={pool_id}) Deleting buckets: {bktnames}")
        for b in bktnames:
            try:
                self.tables.delete_bucket(b)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(f"Api (pool={pool_id}) delete_bucket failed:"
                            f" exception=({m})")
                pass
            pass
        keynames = [k["access_key"] for k in keys]
        logger.debug(f"Api (pool={pool_id}) Deleting access-keys: {keynames}")
        for k in keynames:
            try:
                self.tables.delete_xid_unconditionally("akey", k)
            except Exception as e:
                m = rephrase_exception_message(e)
                logger.info(f"Api (pool={pool_id}) delete_xid failed:"
                            f" exception=({m})")
                pass
            pass
        logger.debug(f"Api (pool={pool_id}) Deleting pool states")
        try:
            self.tables.delete_pool(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_pool failed:"
                        f" exception=({m})")
            pass
        try:
            self.tables.delete_pool_state(pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_pool_state failed:"
                        f" exception=({m})")
            pass
        try:
            self.tables.delete_xid_unconditionally("pool", pool_id)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.info(f"Api (pool={pool_id}) delete_xid failed:"
                        f" exception=({m})")
            pass
        pass

    def _api_list_pools(self, user_id, pool_id):
        self._grant_access(user_id, None, False)
        pool_list = []
        pools = list_user_pools(self.tables, user_id, pool_id)
        for pid in pools:
            pooldesc = gather_pool_desc(self.tables, pid)
            if pooldesc is None:
                logger.debug(f"Api (pool={pool_id}) Removing a pool in race;"
                             f" list-pools runs without a lock (ignored).")
                continue
            assert pooldesc["owner_uid"] == user_id
            pool_list.append(pooldesc)
            pass
        pool_list = sorted(pool_list, key=lambda k: k["buckets_directory"])
        return (200, None, {"pool_list": pool_list})

    # Buckets handling implementation.

    def _api_make_bucket(self, user_id, pool_id, bucket, policy):
        self._activate_minio(pool_id, False)
        self._grant_access(user_id, pool_id, True)
        self._do_make_bucket(pool_id, bucket, policy)
        pooldesc = gather_pool_desc(self.tables, pool_id)
        return (200, None, {"pool_desc": pooldesc})

    def _do_make_bucket(self, pool_id, bucket, bkt_policy):
        now = int(time.time())
        desc = {"pool": pool_id, "bkt_policy": bkt_policy,
                "modification_time": now}
        (ok, holder) = self.tables.set_ex_bucket(bucket, desc)
        if not ok:
            owner = get_pool_owner_for_messages(self.tables, holder)
            raise Api_Error(403, f"Bucket name taken: owner={owner}")
        try:
            mc = self._make_mc_for_pool(pool_id)
            assert mc is not None
            with mc:
                mc.make_bucket(bucket, bkt_policy)
                pass
        except Exception:
            self.tables.delete_bucket(bucket)
            raise
        pass

    def _api_delete_bucket(self, user_id, pool_id, bucket):
        self._grant_access(user_id, pool_id, False)
        ensure_bucket_owner(self.tables, bucket, pool_id)
        pooldesc = self._do_delete_bucket(pool_id, bucket)
        return (200, None, {"pool_desc": pooldesc})

    def _do_delete_bucket(self, pool_id, bucket):
        """Deletes a bucket.  Deletion will be done even if starting MinIO
        failed.
        """
        try:
            self._activate_minio(pool_id, False)
            mc = self._make_mc_for_pool(pool_id)
            assert mc is not None
            with mc:
                bkts = mc.list_buckets()
                entry = [d for d in bkts
                         if d.get("name") == bucket]
                if entry == []:
                    logger.error(f"Api (pool={pool_id}) Inconsistency found"
                                 f" in MinIO and Lens3 in deleting a bucket:"
                                 f" bucket={bucket}")
                else:
                    mc.delete_bucket(bucket)
                    pass
                pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Api (pool={pool_id}) delete_bucket failed:"
                         f" exception=({m})",
                         exc_info=True)
            pass
        self.tables.delete_bucket(bucket)
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    # Secrets handling implementation.

    def _api_make_secret(self, user_id, pool_id, key_policy, expiration):
        self._activate_minio(pool_id, False)
        self._grant_access(user_id, pool_id, True)
        pooldesc = self._do_make_secret(pool_id, key_policy, expiration)
        return (200, None, {"pool_desc": pooldesc})

    def _do_make_secret(self, pool_id, key_policy, expiration):
        secret = generate_secret_key()
        info = {"secret_key": secret, "key_policy": key_policy,
                "expiration_time": expiration}
        key = self.tables.make_unique_xid("akey", pool_id, info)
        try:
            mc = self._make_mc_for_pool(pool_id)
            assert mc is not None
            with mc:
                mc.make_secret(key, secret, key_policy)
                pass
        except Exception:
            self.tables.delete_xid_unconditionally("akey", key)
            raise
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    def _api_delete_secret(self, user_id, pool_id, access_key):
        self._grant_access(user_id, pool_id, False)
        ensure_secret_owner_only(self.tables, access_key, pool_id)
        pooldesc = self._do_delete_secret(pool_id, access_key)
        return (200, None, {"pool_desc": pooldesc})

    def _do_delete_secret(self, pool_id, access_key):
        """Deletes a secret.  Deletion will be done even if starting MinIO
        failed.
        """
        try:
            self._activate_minio(pool_id, False)
            mc = self._make_mc_for_pool(pool_id)
            assert mc is not None
            with mc:
                keys = mc.list_secrets()
                entry = [d for d in keys
                         if d.get("access_key") == access_key]
                if entry == []:
                    logger.error(f"Api (pool={pool_id}) Inconsistency found"
                                 f" in MinIO and Lens3"
                                 f" in deleting an access-key:"
                                 f" pool={pool_id}, access-key={access_key}")
                else:
                    mc.delete_secret(access_key)
                    pass
                pass
            self.tables.delete_xid_unconditionally("akey", access_key)
        except Exception:
            raise
        pooldesc1 = gather_pool_desc(self.tables, pool_id)
        return pooldesc1

    pass
