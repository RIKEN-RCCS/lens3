"""Pool mangement.  This implements operations of Adm."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import string
import sys
import time
import posixpath
import traceback
from lenticularis.mc import Mc, assert_mc_success
from lenticularis.mc import intern_mc_user_info
from lenticularis.mc import intern_mc_list_entry
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables
from lenticularis.table import Storage_Table
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import check_user_naming
from lenticularis.poolutil import check_bucket_naming
from lenticularis.utility import make_clean_env
from lenticularis.utility import decrypt_secret, encrypt_secret
from lenticularis.utility import gen_access_key_id, gen_secret_access_key
from lenticularis.utility import logger
from lenticularis.utility import pick_one, check_permission
from lenticularis.utility import access_mux, host_port
from lenticularis.utility import uniq_d
from lenticularis.poolutil import check_pool_is_well_formed, check_pool_dict_is_sound
from lenticularis.poolutil import merge_pool_descriptions, check_conflict
from lenticularis.poolutil import compare_access_keys, compare_buckets_directory
from lenticularis.poolutil import compare_buckets, check_policy
from lenticularis.utility import tracing


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


## Main pool operations are one of the followings and is specified as
## the HOW argument:
## - how = "create_zone"
## - how = "restore_zone"
## - how = "delete_zone"
## - how = "update_zone"
## - how = "disable_zone"
## - how = "enable_zone"
## - how = "update_buckets"
## - how = "change_secret_key"

def _check_bucket_fmt(bucket):
    bucket_keys = set(bucket.keys())
    return bucket_keys == {"name", "bkt_policy"}


def _check_access_key_fmt(access_key):
    access_key_keys = set(access_key.keys())
    return ({"access_key"}.issubset(access_key_keys) and
            access_key_keys.issubset({"access_key", "secret_key", "key_policy"}))


def _check_create_bucket_keys(zone):
    """ _ ::= {"buckets": [{"name": bucket_name,
                            "bkt_policy": policy}]}
    """
    if zone.keys() != {"buckets"}:
        raise Exception(f"update_buckets: invalid key set: {set(zone.keys())}")
    if not all(_check_bucket_fmt(bucket) for bucket in zone["buckets"]):
        raise Exception(f"update_buckets: invalid bucket: {zone}")


def _check_change_secret_keys(zone):
    """ _ ::= {"access_keys": [accessKey]}
        accessKey ::= {"access_key": access_key_id,
                       "secret_key": secret (optional),
                       "key_policy": policy (optional) }
    """
    if zone.keys() != {"access_keys"}:
        raise Exception(f"update_secret_keys: invalid key set: {set(zone.keys())}")
    if not all(_check_access_key_fmt(access_key) for access_key in zone["access_keys"]):
        raise Exception(f"change_secret_key: invalid accessKey: {zone}")
    pass


def _check_zone_keys(zone):
    given_keys = set(zone.keys())
    mandatory_keys = Storage_Table.pool_desc_required_keys
    optional_keys = Storage_Table.pool_desc_optional_keys
    allowed_keys = mandatory_keys.union(optional_keys)
    ##mandatory_keys = {"owner_gid", "buckets_directory", "buckets", "access_keys",
    ##                  "direct_hostnames", "expiration_date", "online_status"}
    ##allowed_keys = mandatory_keys.union({"user", "root_secret", "permit_status"})
    if not mandatory_keys.issubset(given_keys):
        raise Exception(f"upsert_zone: invalid key set: missing {mandatory_keys - given_keys}")
    if not given_keys.issubset(allowed_keys):
        raise Exception(f"upsert_zone: invalid key set {given_keys - allowed_keys}")
    pass


def check_pool_owner(user_id, pool_id, pool):
    ## It uses a user-id as an owner if it is undefined.
    ##AHO
    owner = pool.get("owner_uid", user_id)
    if owner != user_id:
        raise Exception(f"Mismatch in pool owner and authenticated user:"
                        f" owner={owner} to user={user_id}")
    pass


def _gen_unique_key(key_generator, allkeys):
    while True:
        key = key_generator()
        if key not in allkeys:
            break
    allkeys.add(key)
    return key


def _encrypt_or_generate(dic, key):
    val = dic.get(key)
    dic[key] = encrypt_secret(val if val else gen_secret_access_key())
    pass


def _check_bucket_names(zone):
    for bucket in zone.get("buckets", []):
        ##_check_bucket_name(zone, bucket)
        name = bucket["name"]
        if not check_bucket_naming(name):
            raise Exception(f"Bad bucket name: {name}")
        pass
    pass


def _check_bucket_name__(zone, bucket):
    name = bucket["name"]
    if len(name) < 3:
        raise Exception(f"too short bucket name: {name}")
    if len(name) > 63:
        raise Exception(f"too long bucket name: {name}")

    logger.debug("@@@ CHECK_BUCKET_NAME: FIXME XXX ")

    #    if not name ~ "[a-z0-9][-\.a-z0-9][a-z0-9]":
    #        raise Exception(f"")
    #    if strstr(name, ".."):
    #        raise Exception(f"")
    #    # buckets: 3..63, [a-z0-9][-\.a-z0-9][a-z0-9]
    #    #          no .. , not ip-address form

    # {"none", "upload", "download", "public"}
    check_policy(bucket["bkt_policy"])
    pass


def _check_direct_hostname_flat(host_label):
    logger.error(f"@@@ check_direct_hostname_flat")
    # logger.error(f"@@@ check_direct_hostname_flat XXX FIXME")
    if "." in host_label:
        raise Exception(f"invalid direct hostname: {host_label}: only one level label is allowed")
    _check_rfc1035_label(host_label)
    _check_rfc1122_hostname(host_label)
    pass


def _check_rfc1035_label(label):
    if len(label) > 63:
        raise Exception(f"{label}: too long")
    if len(label) < 1:
        raise Exception(f"{label}: too short")
    pass

def _check_rfc1122_hostname(label):
    alnum = string.ascii_lowercase + string.digits
    if not all(c in alnum + "-" for c in label):
        raise Exception(f"{label}: contains invalid char(s)")
    if not label[0] in alnum:
        raise Exception(f"{label}: must start with a letter or a digit")
    if not label[-1] in alnum:
        raise Exception(f"{label}: must end with a letter or a digit")
    pass


def _is_subdomain(host_fqdn, domain):
    return host_fqdn.endswith("." + domain)


def _strip_domain(host_fqdn, domain):
    domain_len = 1 + len(domain)
    return host_fqdn[:-domain_len]


def _choose_any_access_key(pooldesc):
    """Accesses pooldesc["access_keys"][0]["access_key"], but checks are
    inserted for Pyright.
    """
    keys = pooldesc.get("access_keys", [])
    pair = keys[0] if keys else None
    return pair.get("access_key", None) if pair else None


def _list_access_keys(pooldesc):
    keys = pooldesc.get("access_keys", [])
    ids = [pair.get("access_key", None) if pair else None
           for pair in keys]
    return [k for k in ids if k is not None]


def _add_bucket_to_pool(pooldesc, name, policy):
    v = {"name": name, "bkt_policy": policy}
    buckets = pooldesc.get("buckets")
    one = next((b for b in buckets if b.get("name") == name), None)
    if one is not None:
        logger.debug(f"warning: Bucket name already exists (ignored):"
                     f" name={name}")
    else:
        pass
    buckets = [b for b in buckets if b.get("name") != name]
    buckets.append(v)
    pooldesc["buckets"] = buckets
    return


def _drop_non_ui_info_from_keys(access_key):
    # Drops unnecessary info to pass access-key info to Web-UI.
    # {"use", "owner", "modification_date"}.
    needed = {"access_key", "secret_key", "key_policy"}
    return {k: v for (k, v) in access_key.items() if k in needed}


class Pool_Admin():

    def __init__(self, adm_conf):
        self.adm_conf = adm_conf

        controller_param = adm_conf["controller"]
        self.timeout = int(controller_param["max_lock_duration"])

        multiplexer_param = adm_conf["multiplexer"]
        self.facade_hostname = multiplexer_param["facade_hostname"]

        system_settings_param = adm_conf["system_settings"]
        self.system_settings_param = system_settings_param
        self.direct_hostname_domains = [h.lower() for h in system_settings_param["direct_hostname_domains"]]
        self.reserved_hostnames = [h.lower() for h in self.system_settings_param["reserved_hostnames"]]
        self.max_zone_per_user = int(system_settings_param["max_zone_per_user"])
        self.max_direct_hostnames_per_user = int(system_settings_param["max_direct_hostnames_per_user"])
        self.probe_access_timeout = int(system_settings_param["probe_access_timeout"])

        self.tables = get_tables(adm_conf)

        minio_param = adm_conf["minio"]
        self._bin_mc = minio_param["mc"]
        env = make_clean_env(os.environ)
        self._env_mc = env
        return

    def _get_pool_owner_for_messages(self, pool_id):
        """Finds an owner of a pool for printing a error message.  It returns
        unknown-user, when not owner is found.
        """
        if pool_id is None:
            return "unknown-user"
        pooldesc = self.tables.storage_table.get_pool(pool_id)
        if pooldesc is None:
            return "unknown-user"
        return pooldesc.get("owner_uid")

    def _check_pool_owner(self, pool_id, user_id):
        # owner = self._get_pool_owner_for_messages(pool_id)
        pooldesc = self.tables.storage_table.get_pool(pool_id)
        if pooldesc is None:
            raise Api_Error(403, (f"Non-existing pool: {pool_id}"))
        if pooldesc.get("owner_uid") != user_id:
            raise Api_Error(403, (f"Not an owner of the pool: {pool_id}"))
        pass

    def _check_bucket_owner(self, bucket, pool_id):
        desc = self.tables.routing_table.get_bucket(bucket)
        if desc is None:
            raise Api_Error(403, f"Non-exisiting bucket: {bucket}")
        if desc.get("pool") != pool_id:
            raise Api_Error(403, (f"A bucket for a wrong pool: {bucket}"))
        pass

    def _check_secret_owner(self, access_key, pool_id):
        desc = self.tables.pickone_table.get_id(access_key)
        if desc is None:
            raise Api_Error(403, f"Non-existing access-key: {access_key}")
        if not (desc.get("use") == "access_key"
                and desc.get("owner") == pool_id):
            raise Api_Error(403, f"A wrong access-key: {access_key}")
        pass

    def _make_mc_for_pool(self, traceid, pool_id):
        """Returns an MC command instance.  It accesses a Mux to start a
        MinIO, even when a MinIO is running, to keep it running for a
        while.
        """
        logger.debug(f"Access a Mux to start Minio for pool={pool_id}.")
        status = self.access_mux_for_pool(traceid, pool_id, force=True)
        if status != 200:
            logger.error(f"Access a Mux by Adm failed for pool={pool_id}:"
                         f" status={status}")
        else:
            pass
        minioproc = self.tables.process_table.get_minio_proc(pool_id)
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

    def fix_affected_zone(self, traceid):
        allow_deny_rules = self.tables.storage_table.get_allow_deny_rules()
        fixed = []
        for z_id in self.tables.storage_table.list_pool_ids(None):
            logger.debug(f"@@@ z_id = {z_id}")
            zone = self.tables.storage_table.get_pool(z_id)
            assert zone is not None
            user_id = zone["owner_uid"]

            ui = self.tables.get_user(user_id)
            if ui:
                groups = ui.get("groups", [])
                group = zone.get("owner_gid")
            else:
                groups = []
                group = None

            permission = "allowed" if (
                ui and any(grp for grp in groups if grp == group)
                and check_permission(user_id, allow_deny_rules) == "allowed"
            ) else "denied"

            if zone["permit_status"] != "denied" and not permission:
                self.disable_zone(traceid, user_id, z_id)
                fixed.append(z_id)
                logger.debug(f"permission dropped: {z_id} {user_id} {zone['admission_status']} => {permission}")
        return fixed

    def store_allow_deny_rules(self, allow_deny_rules):
        self.tables.storage_table.ins_allow_deny_rules(allow_deny_rules)
        return

    def fetch_allow_deny_rules(self):
        return self.tables.storage_table.get_allow_deny_rules()

    def list_unixUsers__(self):
        return list(self.tables.storage_table.list_users())

    def store_user_info__(self, user_id, info):
        self.tables.set_user(user_id, info)
        return

    def fetch_user_info__(self, user_id):
        return self.tables.get_user(user_id)

    def delete_user__(self, user_id):
        self.tables.delete_user(user_id)
        return

    def check_user_is_registered(self, user_id):
        """Checks user is known to Lens3.  It does not reject disabled-state
        users to allow them to view the setting.
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

    def _check_user_is_authorized(self, user_id):
        u = self.tables.get_user(user_id)
        assert u is not None
        if not u.get("permitted"):
            raise Api_Error(403, (f"A user disabled: {user_id}"))
        pass

    # Web-UI Interface.

    def return_user_template(self, user_id):
        # It excludes "root_secret".
        self._check_user_is_authorized(user_id)
        ui = self.tables.get_user(user_id)
        assert ui is not None
        groups = ui.get("groups")
        return {
            "owner_uid": user_id,
            "owner_gid": groups[0],
            "groups": groups,
            "buckets_directory": "",
            "buckets": [],
            "access_keys": [
                   {"key_policy": "readwrite"},
                   {"key_policy": "readonly"},
                   {"key_policy": "writeonly"}],
            "direct_hostnames": [],
            "expiration_date": self.determine_expiration_date(),
            "permit_status": "allowed",
            "online_status": "online",
            "atime": "0",
            "directHostnameDomains": self.direct_hostname_domains,
            "facadeHostname": self.facade_hostname,
            "endpoint_url": self.endpoint_urls({"direct_hostnames": []})
        }

    # POOLS.

    def make_pool(self, traceid, user_id, pooldesc0):
        self._check_user_is_authorized(user_id)
        #assert "owner_uid" in pooldesc0
        assert "owner_gid" in pooldesc0
        #assert "root_secret" in pooldesc0
        assert "buckets_directory" in pooldesc0
        #assert "buckets", existing in pooldesc0
        #assert "access_keys" in pooldesc0
        #assert "direct_hostnames" in pooldesc0
        #assert "expiration_date" in pooldesc0
        #assert "online_status" in pooldesc0

        permit_list = self.tables.storage_table.get_allow_deny_rules()

        ui = self.tables.get_user(user_id)
        assert ui is not None
        groups = ui.get("groups")

        pooldesc0["pool_name"] = "(* given later *)"
        pooldesc0["root_secret"] = "(* FAKE VALUE *)"
        pooldesc0["owner_uid"] = user_id
        pooldesc0["buckets"] = []
        pooldesc0["access_keys"] = []
        pooldesc0["direct_hostnames"] = []
        pooldesc0["expiration_date"] = self.determine_expiration_date()
        pooldesc0["permit_status"] = check_permission(user_id, permit_list)
        pooldesc0["online_status"] = "online"
        #pooldesc0["groups"] = groups
        #pooldesc0["atime"] = "0"
        #pooldesc0["directHostnameDomains"] = self.direct_hostname_domains
        #pooldesc0["facadeHostname"] = self.facade_hostname
        #pooldesc0["endpoint_url"] = self.endpoint_urls({"direct_hostnames": []})

        _check_zone_keys(pooldesc0)

        bd = pooldesc0.get("buckets_directory")
        path = posixpath.normpath(bd)
        if not posixpath.isabs(path):
            raise Api_Error(400, (f"Buckets-directory is not absolute:"
                                  f" path=({path})"))

        #_encrypt_or_generate(zone, "root_secret")
        #check_pool_is_well_formed(zone, user_id)
        #check_pool_dict_is_sound(zone, user_id, self.adm_conf)
        #_check_zone_values(user_id, zone)

        pool_id = None
        probe_key = None
        try:
            pool_id = self.tables.make_unique_id("pool", user_id)
            pooldesc0["pool_name"] = pool_id
            info = {"secret_key": "", "key_policy": "readwrite"}
            probe_key = self.tables.make_unique_id("access_key", pool_id, info)
            pooldesc0["probe_access"] = probe_key
            ##self.tables.set_probe_key(probe_key, pool_id)

            (ok, holder) = self.tables.set_ex_buckets_directory(path, pool_id)
            if not ok:
                owner = self._get_pool_owner_for_messages(holder)
                raise Api_Error(400, (f"Buckets-directory is already used:"
                                      f" path=({path}), holder={owner}"))
            try:
                self._store_pool_in_lock(traceid, user_id, pooldesc0)
            except Exception as e:
                self.tables.delete_buckets_directory(path)
                raise
            pass
        except Exception as e:
            if pool_id is not None:
                self.tables.delete_id_unconditionally(pool_id)
                pass
            if probe_key is not None:
                self.tables.delete_id_unconditionally(probe_key)
                ##self.tables.delete_probe_key(probe_key)
                pass
            raise
        pooldesc1 = self._gather_pool_desc(traceid, pool_id)
        assert pooldesc1 is not None
        logger.debug(f"AHOAHO {pooldesc1}")
        check_pool_is_well_formed(pooldesc1, None)
        return pooldesc1

    def _store_pool_in_lock(self, traceid, user_id, pooldesc0):
        permission=None
        initialize=True
        decrypt=True

        pool_id = pooldesc0["pool_name"]
        assert pool_id is not None

        lock = LockDB(self.tables.storage_table, "Adm")
        lock_status = False
        try:
            lock_status = self._lock_pool_table(lock)
            self.tables.storage_table.set_pool(pool_id, pooldesc0)
            self.tables.storage_table.set_atime(pool_id, "0")
        finally:
            self._unlock_pool_table(lock)
            pass

        try:
            self.set_current_mode(pool_id, "initial")
            self._send_decoy_with_zoneid_ptr(traceid, pool_id)
        except Exception as e:
            logger.debug(f"@@@ ignore exception {e}")
            pass

        ##self.tables.storage_table.set_atime(pool_id, atime_from_arg)
        ##self.tables.storage_table.ins_ptr(pool_id, pooldesc0)

        mode = self.fetch_current_mode(pool_id)

        if mode not in {"ready"}:
            logger.error(f"initialize: error: mode is not ready: {mode}")
            raise Exception(f"initialize: error: mode is not ready: {mode}")
        else:
            pass
        pass

    def delete_pool(self, traceid, user_id, pool_id):
        """Deletes a pool.  It clears buckets and access-keys set in MinIO.
        """
        self._check_user_is_authorized(user_id)
        self._check_pool_owner(pool_id, user_id)
        self._clean_minio(traceid, user_id, pool_id)
        self._clean_database(traceid, user_id, pool_id)
        return (200, None, {})

    def _clean_minio(self, traceid, user_id, pool_id):
        # Clean MinIO and stop.
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                mc.clean_minio_setting(user_id, pool_id)
                # (p_, r) = mc.admin_service_stop()
                # assert p_ is None
                # assert_mc_success(r, "mc.admin_service_stop")
        except Exception as e:
            logger.error(f"Exception in delete_pool: exception={e}",
                         exc_info=True)
            pass
        # Delete a route.
        try:
            self.tables.routing_table.delete_route(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_route: exception={e}")
            pass
        try:
            self.tables.routing_table.delete_route_expiry(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_route_expiry: exception={e}")
            pass
        pass

    def _clean_database(self, traceid, user_id, pool_id):
        # Clean database.
        pooldesc = self.tables.storage_table.get_pool(pool_id)
        if pooldesc is not None:
            probe_key = pooldesc.get("probe_access") if pooldesc else None
        else:
            probe_key = None
            pass
        path = self.tables.storage_table.get_buckets_directory_of_pool(pool_id)
        bkts = self.tables.routing_table.list_buckets(pool_id)
        keys = self.tables.pickone_table.list_access_keys(pool_id)
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
                self.tables.routing_table.delete_bucket(b)
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
            self.tables.storage_table.delete_pool(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_pool: {e}")
            pass
        try:
            self.tables.storage_table.delete_pool_state(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_pool_state: {e}")
            pass
        try:
            self.tables.storage_table.del_atime(pool_id)
        except Exception as e:
            logger.info(f"Exception in del_atime: {e}")
            pass
        try:
            self.tables.delete_id_unconditionally(pool_id)
        except Exception as e:
            logger.info(f"Exception in delete_id_unconditionally: {e}")
            pass
        pass

    def list_pools(self, traceid, user_id, pool_id):
        """It lists all pools of the user when pool-id is None."""
        self._check_user_is_authorized(user_id)
        groups = None
        decrypt = True
        include_atime = True
        include_userinfo = True
        if include_userinfo:
            ui = self.tables.get_user(user_id)
            groups = ui.get("groups") if ui is not None else None
        extra_info = False
        if extra_info:
            (access_key_ptr, direct_host_ptr) = self.tables.storage_table.get_ptr_list()
        else:
            (access_key_ptr, direct_host_ptr) = (None, None)
            pass

        pool_list = []
        for id in self.tables.storage_table.list_pool_ids(pool_id):
            pooldesc = self._gather_pool_desc(traceid, id)
            if pooldesc is None:
                logger.debug(f"Pool deleted in race; list-pools runs"
                             f" without a lock (ignored): {id}")
                continue
            if pooldesc["owner_uid"] != user_id:
                continue
            pooldesc["pool_name"] = id

            if decrypt:
                #self.decrypt_access_keys(pooldesc)
                pass

            pooldesc["minio_state"] = self.fetch_current_mode(id)
            if include_atime:
                atime = self.tables.storage_table.get_atime(id)
                pooldesc["atime"] = atime
                pass

            if extra_info:
                self._pullup_ptr(id, pooldesc, access_key_ptr, direct_host_ptr)
                pass

            if include_userinfo:
                self._add_info_for_webui(id, pooldesc, groups)
                pass

            pool_list.append(pooldesc)
            pass
        return (200, None, {"pool_list": pool_list})

    def _gather_pool_desc(self, traceid, pool_id):
        """Returns a pool description to be displayed by Web-UI."""
        pooldesc = self.tables.storage_table.get_pool(pool_id)
        if pooldesc is None:
            return None
        bd = self.tables.storage_table.get_buckets_directory_of_pool(pool_id)
        pooldesc["buckets_directory"] = bd
        bkts = self.tables.routing_table.list_buckets(pool_id)
        pooldesc["buckets"] = bkts

        keys0 = self.tables.pickone_table.list_access_keys(pool_id)
        # Drop a probing access-key.  It is not visible to users.
        keys1 = [k for k in keys0
                if (k is not None and k.get("secret_key") != "")]
        # Drop unnecessary info to users.
        keys2 = [_drop_non_ui_info_from_keys(k) for k in keys1]

        logger.debug(f"AHO keys={keys2}")

        pooldesc["access_keys"] = keys2
        pooldesc.pop("probe_access")

        ##pooldesc["direct_hostnames"]
        ##pooldesc["expiration_date"]
        ##pooldesc["permit_status"]
        ##pooldesc["online_status"]
        ##pooldesc["minio_state"]
        check_pool_is_well_formed(pooldesc, None)
        return pooldesc

    # BUCKETS.

    def make_bucket(self, traceid, user_id, pool_id, bucket, policy):
        self._check_user_is_authorized(user_id)
        self._check_pool_owner(pool_id, user_id)
        now = int(time.time())
        desc = {"pool": pool_id, "bkt_policy": policy,
                "modification_date": now}
        (ok, holder) = self.tables.set_bucket(bucket, desc)
        if not ok:
            owner = self._get_pool_owner_for_messages(holder)
            raise Api_Error(403, f"Bucket name taken: owner={owner}")
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                lock = LockDB(self.tables.storage_table, "Adm")
                self._lock_pool_entry(lock, pool_id)
                try:
                    mc.make_bucket_with_policy(bucket, policy)
                    pooldesc = self.tables.storage_table.get_pool(pool_id)
                    _add_bucket_to_pool(pooldesc, bucket, policy)
                    check_pool_is_well_formed(pooldesc, None)
                    self.tables.storage_table.set_pool(pool_id, pooldesc)
                    return (200, None, {"pool_list": [pooldesc]})
                finally:
                    self._unlock_pool_entry(lock, pool_id)
                    pass
                pass
            pass
        except Exception as e:
            self.tables.routing_table.delete_bucket(bucket)
            raise
        pooldesc1 = self._gather_pool_desc(traceid, pool_id)
        return (200, None, {"pool_list": [pooldesc1]})

    def delete_bucket(self, traceid, user_id, pool_id, bucket):
        """Deletes a bucket.  Deleting ignores errors occur in MC commands in
        favor of disabling accesses.
        """
        self._check_user_is_authorized(user_id)
        self._check_pool_owner(pool_id, user_id)
        self._check_bucket_owner(bucket, pool_id)
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                (p_, bkts0) = mc.list_buckets()
                assert p_ is None
                assert_mc_success(bkts0, "mc.list_buckets")
                bkts = [intern_mc_list_entry(e) for e in bkts0]
                entry = [d for d in bkts
                         if d.get("name") == bucket]
                if entry == []:
                    logger.error(f"Inconsistency is found in MinIO and Lens3"
                                 f" in deleting a bucket:"
                                 f" pool={pool_id}, bucket={bucket}")
                else:
                    (p_, r) = mc.policy_set(bucket, "none")
                    assert p_ is None
                    assert_mc_success(r, "mc.policy_set")
                    pass
                pass
        except Exception as e:
            logger.error(f"Exception in delete_bucket: exception={e}",
                         exc_info=True)
            pass
        self.tables.routing_table.delete_bucket(bucket)
        pooldesc1 = self._gather_pool_desc(traceid, pool_id)
        return (200, None, {"pool_list": [pooldesc1]})

    # SECRETS.

    def make_secret(self, traceid, user_id, pool_id, policy):
        self._check_user_is_authorized(user_id)
        self._check_pool_owner(pool_id, user_id)
        secret = gen_secret_access_key()
        info = {"secret_key": secret, "key_policy": policy}
        key = self.tables.make_unique_id("access_key", pool_id, info)
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                (p_, r) = mc.admin_user_add(key, secret)
                assert p_ is None
                assert_mc_success(r, "mc.admin_user_add")
                (p_, r) = mc.admin_policy_set(key, policy)
                assert p_ is None
                assert_mc_success(r, "mc.admin_policy_set")
                (p_, r) = mc.admin_user_enable(key)
                assert p_ is None
                assert_mc_success(r, "mc.admin_user_enable")
            pass
        except Exception as e:
            self.tables.delete_id_unconditionally(key)
            raise
        pooldesc1 = self._gather_pool_desc(traceid, pool_id)
        return (200, None, {"pool_list": [pooldesc1]})

    def delete_secret(self, traceid, user_id, pool_id, access_key):
        """Deletes a secret.  Deleting will fail when errors occur in MC
        commands.
        """
        self._check_user_is_authorized(user_id)
        self._check_pool_owner(pool_id, user_id)
        self._check_secret_owner(access_key, pool_id)
        try:
            mc = self._make_mc_for_pool(traceid, pool_id)
            assert mc is not None
            with mc:
                (p_, keys0) = mc.admin_user_list()
                assert p_ is None
                assert_mc_success(keys0, "mc.admin_user_list")
                keys = [intern_mc_user_info(e) for e in keys0]
                entry = [d for d in keys
                         if d.get("access_key") == access_key]
                if entry == []:
                    logger.error(f"Inconsistency is found in MinIO and Lens3"
                                 f" in deleting an access-key:"
                                 f" pool={pool_id}, access-key={access_key}")
                else:
                    (p_, r) = mc.admin_user_remove(access_key)
                    assert p_ is None
                    assert_mc_success(r, "mc.admin_user_remove")
                    pass
                pass
            self.tables.delete_id_unconditionally(access_key)
        except Exception as e:
            raise
        pooldesc1 = self._gather_pool_desc(traceid, pool_id)
        return (200, None, {"pool_list": [pooldesc1]})

    def create_pool(self, traceid, user_id, pooldesc0):
        decrypt=True
        include_atime=False
        initialize=True
        assert user_id is not None
        assert initialize == True
        atime_from_arg = pooldesc0.pop("atime", None) if include_atime else None
        _check_zone_keys(pooldesc0)
        how = "create_zone"
        pooldesc1 = self._do_create_pool(how, traceid, user_id, pooldesc0,
                                         atime_from_arg)
        check_pool_is_well_formed(pooldesc1, None)
        return pooldesc1

    def update_pool(self, traceid, user_id, zone_id, zone, *,
                    include_atime=False,
                    decrypt=False, initialize=True):
        assert user_id is not None
        assert zone_id is not None
        atime_from_arg = zone.pop("atime", None) if include_atime else None
        _check_zone_keys(zone)
        how = "update_zone"
        return self._do_update_pool(how, traceid, user_id, zone_id, zone,
                                    atime_from_arg=atime_from_arg,
                                    initialize=initialize,
                                    decrypt=decrypt)

    def update_buckets(self, traceid, user_id, zone_id, zone, *,
                       include_atime=False,
                       decrypt=False, initialize=True):
        assert user_id is not None
        assert zone_id is not None
        _check_create_bucket_keys(zone)
        how = "update_buckets"
        return self._do_update_buckets(how, traceid, user_id, zone_id, zone,
                                       decrypt=decrypt)

    def restore_pool(self, traceid, user_id, zone_id, zone, *,
                     include_atime, initialize):
        ## This is called only from admin commands.
        assert user_id is not None
        assert zone_id is not None
        atime_from_arg = zone.pop("atime", None) if include_atime else None
        _check_zone_keys(zone)
        how = "restore_zone"
        return self._do_restore_pool(how, traceid, user_id, zone_id, zone,
                                     atime_from_arg=atime_from_arg,
                                     initialize=initialize,
                                     decrypt=False)

    ##def _upsert_zone_(self, how, traceid, user_id, zone_id, zone,
    ##                  include_atime=False,
    ##                  decrypt=False, initialize=True):
    ##    ## how=None is for admin commands.  Note that "delete_zone",
    ##    ## "disable_zone", "enable_zone" never appears.
    ##    assert how in {None, "create_zone", "update_zone",
    ##                   "update_buckets", "change_secret_key"}
    ##    assert user_id is not None
    ##    assert (how == "create_zone") == (zone_id is None)
    ##
    ##    if how == "update_buckets":
    ##        _check_create_bucket_keys(zone)
    ##        return self._do_update_zone(traceid, user_id, zone_id, zone, how, decrypt=decrypt)
    ##
    ##    elif how == "change_secret_key":
    ##        _check_change_secret_keys(zone)
    ##        return self._do_update_zone(traceid, user_id, zone_id, zone, how, decrypt=decrypt)
    ##
    ##    else:
    ##        ## how in {None, "create_zone", "update_zone"}
    ##        atime_from_arg = zone.pop("atime", None) if include_atime else None
    ##        _check_zone_keys(zone)
    ##        return self._do_update_zone(traceid, user_id, zone_id, zone, how,
    ##                                    atime_from_arg=atime_from_arg,
    ##                                    ## owerride behaviour
    ##                                    initialize=initialize,
    ##                                    decrypt=decrypt)

    def delete_zone(self, traceid, user_id, zoneID):
        logger.debug(f"+++ {user_id} {zoneID}")
        zone = {"permit_status": "denied"}
        how = "delete_zone"
        return self._do_delete_zone(how, traceid, user_id, zoneID, zone)

    def disable_zone(self, traceid, user_id, zoneID):
        logger.debug(f"+++ {user_id} {zoneID}")
        zone = {}
        how = "disable_zone"
        return self._do_disable_zone(how, traceid, user_id, zoneID, zone,
                                     permission="denied")

    def enable_zone(self, traceid, user_id, zoneID):
        logger.debug(f"+++ {user_id} {zoneID}")
        zone = {}
        how = "enable_zone"
        return self._do_enable_zone(how, traceid, user_id, zoneID, zone,
                                    permission="allowed")

    def flush_storage_table(self, everything=False):
        self.tables.storage_table.clear_all(everything=everything)
        return

    def reset_database(self, everything=False):
        self.tables.storage_table.clear_all(everything=everything)
        self.tables.process_table.clear_all(everything=everything)
        self.tables.routing_table.clear_routing(everything=everything)
        self.tables.pickone_table.clear_all(everything=everything)
        return

    def print_database(self):
        self.tables.storage_table.print_all()
        self.tables.process_table.print_all()
        self.tables.routing_table.print_all()
        self.tables.pickone_table.print_all()
        return

    def fetch_multiplexer_list(self):
        return self.tables.process_table.list_muxs()

    def fetch_process_list(self):
        return self.tables.process_table.list_minio_procs(None)

    def delete_process(self, processID):
        return self.tables.process_table.delete_minio_proc(processID)

    def flush_process_table(self, everything=False):
        self.tables.process_table.clear_all(everything=everything)
        return

    def access_mux_for_pool(self, traceid, zoneID, *, force, access_key=None):
        """Tries to access a Mux of the pool.  Always use with force=True, to
        let access regardless of the running state of MinIO.
        """

        logger.debug(f"zone={zoneID}, access_key={access_key}, force={force}")

        procdesc = self.tables.process_table.get_minio_proc(zoneID)
        if procdesc is not None:
            mux_host = procdesc.get("mux_host")
            mux_port = procdesc.get("mux_port")
            ep = host_port(mux_host, mux_port)
        elif force:
            muxs = self.tables.process_table.list_mux_eps()
            pair = pick_one(muxs)
            ep = host_port(pair[0], pair[1])
        else:
            # Do nothing, when not force and MinIO is not running.
            return ""
        assert ep is not None
        if access_key is None:
            pooldesc = self.tables.storage_table.get_pool(zoneID)
            if pooldesc is None:
                # Done if neither access-key nor pool exists.
                logger.debug(f"No check, as neither access-key nor zone.")
                return ""
            else:
                # Choose any key in the list.
                ##access_key = _choose_any_access_key(pooldesc)
                access_key = pooldesc["probe_access"]
                logger.debug(f"AHO probe_access={access_key}")
                pass
        else:
            pass

        ##AHO
        pooldesc = self.tables.storage_table.get_pool(zoneID)
        access_key = pooldesc["probe_access"]
        logger.debug(f"AHOAHO probe_access={access_key}")

        facade_hostname = self.facade_hostname
        status = access_mux(traceid, ep, access_key, facade_hostname,
                            self.probe_access_timeout)
        logger.debug(f"Access Mux for pool={zoneID}: status={status}")
        return status

    ##def fetch_route_list(self):
    ##    return self.tables.routing_table.list_routes()

    def flush_routing_table(self, everything=False):
        self.tables.routing_table.clear_routing(everything=everything)
        return

    def _lock_pool_entry(self, lock, pool_id):
        lockprefix = self.tables.storage_table.storage_table_lock_prefix
        key = f"{lockprefix}{pool_id}"
        lockstatus = lock.lock(key, self.timeout)
        return lockstatus

    def _unlock_pool_entry(self, lock, pool_id):
        lockstatus = lock.unlock()
        return lockstatus

    def _lock_pool_table(self, lock):
        lockprefix = self.tables.storage_table.storage_table_lock_prefix
        key = f"{lockprefix}"
        lockstatus = lock.lock(key, self.timeout)
        return lockstatus

    def _unlock_pool_table(self, lock):
        lockstatus = lock.unlock()
        return lockstatus

    ##def _do_update_zone_(self, how, traceid, user_id, zoneID, zone, *,
    ##                     permission=None,
    ##                     atime_from_arg=None,
    ##                     initialize=True,
    ##                     decrypt=False):
    ##    lock = LockDB(self.tables.storage_table, "Adm")
    ##    try:
    ##        self._lock_pool_entry(lock, zoneID)
    ##        return self._update_zone_with_lock_(
    ##            how, traceid, user_id, zoneID, zone,
    ##            permission, atime_from_arg, initialize, decrypt)
    ##    finally:
    ##        self._unlock_pool_entry(lock, zoneID)

    def _do_create_pool(self, how, traceid, user_id, pooldesc,
                        atime_from_arg):
        permission=None
        initialize=True
        decrypt=True
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, None)
            return self._create_pool_with_lock(
                how, traceid, user_id, pooldesc,
                atime_from_arg)
        finally:
            self._unlock_pool_entry(lock, None)
            pass
        return

    def _do_update_pool(self, how, traceid, user_id, zoneID, zone, *,
                        permission=None,
                        atime_from_arg=None,
                        initialize=True,
                        decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._update_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _do_update_buckets(self, how, traceid, user_id, zoneID, zone, *,
                           permission=None,
                           atime_from_arg=None,
                           initialize=True,
                           decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._update_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _do_change_secret(self, how, traceid, user_id, zoneID, zone, *,
                          permission=None,
                          atime_from_arg=None,
                          initialize=True,
                          decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._update_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _do_restore_pool(self, how, traceid, user_id, zoneID, zone, *,
                         permission=None,
                         atime_from_arg=None,
                         initialize=True,
                         decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            ##AHO
            return self._create_pool_with_lock(
                how, traceid, user_id, zone,
                atime_from_arg)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _do_delete_zone(self, how, traceid, user_id, zoneID, zone, *,
                        permission=None,
                        atime_from_arg=None,
                        initialize=True,
                        decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._delete_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _do_disable_zone(self, how, traceid, user_id, zoneID, zone, *,
                         permission=None,
                         atime_from_arg=None,
                         initialize=True,
                         decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._update_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _do_enable_zone(self, how, traceid, user_id, zoneID, zone, *,
                        permission=None,
                        atime_from_arg=None,
                        initialize=True,
                        decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._update_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)
            pass
        return

    def _delete_existing_zone(self, zone_id, existing):
        logger.debug(f"+++")
        logger.debug(f"@@@ del_mode {zone_id}")
        self.tables.storage_table.del_mode(zone_id)
        logger.debug(f"@@@ del_atime {zone_id}")
        self.tables.storage_table.del_atime(zone_id)
        logger.debug(f"@@@ DELETE PTR {zone_id} {[e.get('access_key') for e in existing.get('access_keys')]}")
        self.tables.storage_table.del_ptr(zone_id, existing)
        logger.debug("@@@ del_zone")
        self.tables.storage_table.del_zone(zone_id)
        logger.debug("@@@ DONE")
        return

    def _check_user_group(self, user_id, zone):
        ui = self.tables.get_user(user_id)
        groups = ui.get("groups") if ui else []
        group = zone.get("owner_gid") if zone else None
        if group not in groups:
            raise Exception(f"invalid group: {group}")
        return

    def _check_direct_hostname(self, host_fqdn):
        host_fqdn = host_fqdn.lower()
        fns = {"flat": _check_direct_hostname_flat}

        criteria = self.system_settings_param["direct_hostname_validator"]
        logger.debug(f"@@@ {self.system_settings_param}")
        logger.debug(f"@@@ criteria = {criteria}")

        if any(host_fqdn == d for d in self.reserved_hostnames):
            raise Exception(f"{host_fqdn}: the name is reserved")

        try:
            domain = next(d for d in self.direct_hostname_domains if _is_subdomain(host_fqdn, d))
        except StopIteration:
            raise Exception(f"{host_fqdn}: direct hostname should "
                            f"ends with one of '{self.direct_hostname_domains}'")

        fn = fns.get(criteria)
        if fn is None:
            raise Exception(f"system configulation error: direct_hostname_validator '{criteria}' is not defined")
        fn(_strip_domain(host_fqdn, domain))
        return

    def _halt_minio(self, traceid, pool_id, existing):
        """Stops a MinIO.  It throws an exception to break further processing.
        """
        mode = self.fetch_current_mode(pool_id)
        assert mode == "suspended"
        self._clear_route(pool_id, existing)
        status = self.access_mux_for_pool(traceid, pool_id, force=False)
        procdesc = self.tables.process_table.get_minio_proc(pool_id)
        if procdesc is not None:
            logger.error(f"COULD NOT STOP MINIO: {procdesc}")
        assert procdesc is None
        return

    ##def _update_zone_with_lock_(self, how, traceid, user_id, zone_id, zone,
    ##                            permission, atime_from_arg,
    ##                            initialize, decrypt):
    ##    existing = self.tables.storage_table.get_pool(zone_id) if zone_id else None
    ##
    ##    must_exist = how not in {"restore_zone", "create_zone"}
    ##    if must_exist and not existing:
    ##        raise Exception(f"Non-existing pool is specified: pool={zone_id}")
    ##
    ##    if existing:
    ##        check_pool_owner(user_id, zone_id, existing)
    ##
    ##    delete_zone = how == "delete_zone"
    ##
    ##    (need_initialize, need_uniquify) = self._prepare_zone(
    ##        user_id, zone_id, existing, zone, permission, how)
    ##
    ##    # if explicitly ordered not to initialize,
    ##    # set need_initialize to be False
    ##
    ##    need_initialize = need_initialize and initialize
    ##
    ##    omode = None
    ##    if not need_initialize:
    ##        omode = self.fetch_current_mode(zone_id)
    ##
    ##    if zone_id:
    ##        self.set_current_mode(zone_id, "suspended")
    ##
    ##    ### XXX can we merge following two tries into one?
    ##
    ##    # We will restart minio always, though there
    ##    # may be no changes have been made to existing zone.
    ##    # If explicitly ordered not to initialize, do not try
    ##    # to stop minio (regardless it is running or not).
    ##
    ##    try:
    ##        if existing and initialize:
    ##            self._clear_route(zone_id, existing)
    ##            logger.debug(f"@@@ SEND DECOY zone_id = {zone_id}")
    ##            ## Stop MinIO.
    ##            status = self.access_mux_for_pool(traceid, zone_id, force=False)
    ##            logger.debug(f"@@@ SEND DECOY STATUS {status}")
    ##            procdesc = self.tables.process_table.get_minio_proc(zone_id)
    ##            if procdesc is not None:
    ##                logger.debug(f"@@@ COULD NOT STOP MINIO")
    ##                raise Exception("could not stop minio")
    ##    except Exception as e:
    ##        logger.debug(f"@@@ ignore exception {e}")
    ##        pass
    ##
    ##    if delete_zone:
    ##        pass
    ##    else:
    ##        need_conflict_check = existing is not None
    ##        zone_id = self._lock_and_store_zone(user_id, zone_id, zone, need_conflict_check, need_uniquify)
    ##        # NOTE: delete ptr here, if user allowed to modify access keys
    ##        #    in the future lenticularis specification.
    ##
    ##    try:
    ##        if delete_zone:
    ##            self.set_current_mode(zone_id, "deprecated")
    ##        elif need_initialize:
    ##            self.set_current_mode(zone_id, "initial")
    ##            self._send_decoy_with_zoneid_ptr(traceid, zone_id)  # trigger initialize minio
    ##        else:
    ##            pass
    ##    except Exception as e:
    ##        logger.debug(f"@@@ ignore exception {e}")
    ##        pass
    ##
    ##    if delete_zone:
    ##        self._delete_existing_zone(existing)
    ##    else:
    ##        logger.debug(f"@@@ INSERT PTR {zone_id} {[e.get('access_key') for e in zone.get('access_keys')]}")
    ##        if atime_from_arg:
    ##            logger.debug(f"@@@ INSERT PTR {zone_id} {[e.get('access_key') for e in zone.get('access_keys')]}")
    ##            self.tables.storage_table.set_atime(zone_id, atime_from_arg)
    ##        self.tables.storage_table.ins_ptr(zone_id, zone)
    ##
    ##    if not delete_zone and omode:
    ##        self.set_current_mode(zone_id, omode)
    ##        mode = omode
    ##    elif not initialize:
    ##        # intentionally leave mode be unset
    ##        pass
    ##    else:
    ##        mode = self.fetch_current_mode(zone_id)
    ##
    ##    if delete_zone:
    ##        if mode is not None:
    ##            logger.error(f"delete zone: error: mode is not None: {mode}")
    ##            raise Exception(f"delete zone: error: mode is not None: {mode}")
    ##    elif not initialize:
    ##        pass
    ##    elif mode not in {"ready"}:
    ##        logger.error(f"initialize: error: mode is not ready: {mode}")
    ##        raise Exception(f"initialize: error: mode is not ready: {mode}")
    ##    else:
    ##        pass
    ##
    ##    zone["zoneID"] = zone_id
    ##    logger.debug(f"@@@ decrypt = {decrypt}")
    ##    if decrypt:
    ##        self.decrypt_access_keys(zone)
    ##    #logger.debug(f"@@@ zone = {zone}")
    ##    return zone
    ##
    ### END update_zone_with_lock

    def _create_pool_with_lock(self, how, traceid, user_id, zone,
                               atime_from_arg):
        permission=None
        initialize=True
        decrypt=True
        zone_id = None
        assert how in {"create_zone", "restore_zone"}
        if how == "create_zone":
            assert zone_id is None
        elif how == "restore_zone":
            assert zone_id is not None
            pass

        existing = self.tables.storage_table.get_pool(zone_id) if zone_id else None
        if existing:
            check_pool_owner(user_id, zone_id, existing)
            pass

        (need_initialize, need_uniquify) = self._prepare_zone(
            user_id, zone_id, existing, zone, permission, how)

        need_initialize = need_initialize and initialize

        omode = None
        if not need_initialize:
            omode = self.fetch_current_mode(zone_id)
            pass
        if zone_id:
            self.set_current_mode(zone_id, "suspended")
            pass

        if existing and initialize:
            ## how = "restore_zone"
            self._halt_minio(traceid, zone_id, existing)
            pass

        ## NO FURTHER PROCESSING IF _halt_minio FAILS.

        ##AHO
        probe_access = gen_access_key_id()
        zone["probe_access"] = probe_access

        need_conflict_check = existing is not None
        zone_id = self._lock_and_store_zone(user_id, zone_id, zone, need_conflict_check, need_uniquify)

        ##AHO
        self.tables.routing_table.set_probe_key__(probe_access, zone_id)

        try:
            if need_initialize:
                self.set_current_mode(zone_id, "initial")
                self._send_decoy_with_zoneid_ptr(traceid, zone_id)
            else:
                pass
        except Exception as e:
            logger.debug(f"@@@ ignore exception {e}")
            pass

        if atime_from_arg:
            self.tables.storage_table.set_atime(zone_id, atime_from_arg)
            pass
        self.tables.storage_table.ins_ptr(zone_id, zone)

        if omode:
            self.set_current_mode(zone_id, omode)
            mode = omode
        elif not initialize:
            mode = None
        else:
            mode = self.fetch_current_mode(zone_id)
            pass

        if initialize and mode not in {"ready"}:
            logger.error(f"initialize: error: mode is not ready: {mode}")
            raise Exception(f"initialize: error: mode is not ready: {mode}")
        else:
            pass

        zone["pool_name"] = zone_id
        if decrypt:
            self.decrypt_access_keys(zone)
            pass
        return zone

    def _update_pool_with_lock(self, how, traceid, user_id, zone_id, zone,
                               permission, atime_from_arg,
                               initialize, decrypt):
        assert how in {"update_zone", "update_buckets" "change_secret_key",
                       "disable_zone", "enable_zone"}
        assert how not in {"restore_zone", "create_zone", "delete_zone"}
        assert zone_id is not None
        existing = self.tables.storage_table.get_pool(zone_id)
        if not existing:
            raise Exception(f"Non-existing pool is specified: pool={zone_id}")
        check_pool_owner(user_id, zone_id, existing)

        (need_initialize, need_uniquify) = self._prepare_zone(
            user_id, zone_id, existing, zone, permission, how)

        need_initialize = need_initialize and initialize

        omode = None
        if not need_initialize:
            omode = self.fetch_current_mode(zone_id)
            pass

        if zone_id:
            self.set_current_mode(zone_id, "suspended")
            pass

        if initialize:
            self._halt_minio(traceid, zone_id, existing)
            pass

        ## NO FURTHER PROCESSING IF _halt_minio FAILS.

        need_conflict_check = True
        zone_id = self._lock_and_store_zone(user_id, zone_id, zone, need_conflict_check, need_uniquify)

        try:
            if need_initialize:
                # Trigger initialization of MinIO.
                self.set_current_mode(zone_id, "initial")
                self._send_decoy_with_zoneid_ptr(traceid, zone_id)
            else:
                pass
        except Exception as e:
            logger.debug(f"@@@ ignore exception {e}")
            pass

        if atime_from_arg:
            self.tables.storage_table.set_atime(zone_id, atime_from_arg)
            pass
        self.tables.storage_table.ins_ptr(zone_id, zone)

        if omode:
            self.set_current_mode(zone_id, omode)
            mode = omode
        elif not initialize:
            mode = None
        else:
            mode = self.fetch_current_mode(zone_id)
            pass

        if not initialize:
            pass
        elif mode not in {"ready"}:
            logger.error(f"initialize: error: mode is not ready: {mode}")
            raise Exception(f"initialize: error: mode is not ready: {mode}")
        else:
            pass

        zone["pool_name"] = zone_id
        if decrypt:
            self.decrypt_access_keys(zone)
            pass
        return zone

    def _delete_pool_with_lock(self, how, traceid, user_id, zone_id, zone,
                               permission, atime_from_arg,
                               initialize, decrypt):
        assert not initialize
        assert not decrypt
        existing = self.tables.storage_table.get_pool(zone_id) if zone_id else None
        if not existing:
            raise Exception(f"Deleting a non-existing pool: pool={zone_id}")
        check_pool_owner(user_id, zone_id, existing)

        (need_initialize, need_uniquify) = self._prepare_zone(
            user_id, zone_id, existing, zone, permission, how)

        omode = self.fetch_current_mode(zone_id)
        self.set_current_mode(zone_id, "suspended")
        self.set_current_mode(zone_id, "deprecated")
        self._delete_existing_zone(zone_id, existing)
        mode = self.fetch_current_mode(zone_id)
        assert mode is None
        zone["pool_name"] = zone_id
        return zone

    def _prepare_zone(self, user_id, zone_id, existing, zone, permission, how):
        if how == "delete_zone":
            return (False, False)
        elif how == "update_buckets":
            return self._prepare_for_update_buckets(how, user_id, zone_id, existing, zone, permission)
        elif how == "change_secret_key":
            return self._prepare_for_change_secret(how, user_id, zone_id, existing, zone, permission)
        else:
            return self._prepare_for_update_pool(how, user_id, zone_id, existing, zone, permission)
        return

    def _prepare_for_update_pool(self, how, user_id, zone_id,
                                 existing, zone, permission):
        assert how not in {"update_buckets", "change_secret_key",
                           "delete_zone"}
        assert how in {"create_zone", "update_zone", "restore_zone",
                       "disable_zone", "enable_zone"}

        merge_pool_descriptions(user_id, existing, zone)

        need_uniquify = self._regularize_pool_dict(user_id, existing, zone, permission)

        r = compare_access_keys(existing, zone)
        if r != []:
            raise Exception(f"Changing an access key is not allowed: {r}")

        r = compare_buckets_directory(existing, zone)
        if r != []:
            raise Exception(f"Changing a buckets-directory is not allowed: {r}")

        r = compare_buckets(existing, zone)
        bucket_settings_modified = r != []

        if zone_id:
            mode = self.fetch_current_mode(zone_id)
        else:
            mode = None
            pass
        create_bucket = False
        change_secret = False
        need_initialize = (zone_id is None or
                           existing is None or
                           bucket_settings_modified or
                           mode not in {"ready"} or
                           create_bucket or
                           change_secret)
        return (need_initialize, need_uniquify)

    def _prepare_for_update_buckets(self, how, user_id, zone_id,
                                    existing, zone, permission):
        assert how == "update_buckets"
        assert zone is not None
        assert zone_id is not None and existing is not None
        assert "buckets" in zone

        new_buckets = zone.pop("buckets")
        if len(new_buckets) != 1:
            raise Exception(f"Updating a bucket for too few/many buckets: {new_buckets}")
        bucket = new_buckets[0]
        name = bucket["name"]

        if any(b["name"] == name for b in existing.get("buckets", [])):
            raise Exception(f"Updating a bucket that exists: name={name}")
        merge_pool_descriptions(user_id, existing, zone)
        zone["buckets"].append(bucket)

        need_uniquify = self._regularize_pool_dict(user_id, existing, zone, permission)
        if zone_id is None:
            mode = None
        else:
            mode = self.fetch_current_mode(zone_id)
        change_secret = False
        create_bucket = True
        bucket_settings_modified = True
        need_initialize = (zone_id is None or
                           existing is None or
                           bucket_settings_modified or
                           mode not in {"ready"} or
                           create_bucket or
                           change_secret)
        return (need_initialize, need_uniquify)

    def _prepare_for_change_secret(self, how, user_id, zone_id,
                                   existing, zone, permission):
        assert how == "change_secret_key"
        assert existing is not None
        assert "access_keys" in zone

        new_keys = zone.pop("access_keys")
        if len(new_keys) != 1:
            raise Exception(f"Changing secret for too few/many access-keys: keys={new_keys}")
        newkey = new_keys[0]
        keyid = newkey["access_key"]

        merge_pool_descriptions(user_id, existing, zone)

        access_keys = zone.get("access_keys", [])
        if not any(k["access_key"] == keyid for k in access_keys):
            raise Exception(f"Changing secret for a non-existing key: key={keyid}")
        for k in access_keys:
            if k["access_key"] == keyid:
                ## Let `regularize_zone` generate a new secret access key.
                k["secret_key"] = ""
                break
            pass
        ## assert(permission is None)
        need_uniquify = self._regularize_pool_dict(user_id, existing, zone, permission)

        if zone_id:
            mode = self.fetch_current_mode(zone_id)
        else:
            mode = None
            pass
        create_bucket = False
        change_secret = True
        bucket_settings_modified = True
        need_initialize = (zone_id is None or
                           existing is None or
                           bucket_settings_modified or
                           mode not in {"ready"} or
                           create_bucket or
                           change_secret)
        return (need_initialize, need_uniquify)

    def _regularize_pool_dict(self, user_id, existing, zone, permission):
        _encrypt_or_generate(zone, "root_secret")

        if permission is None:
            ## how not in {"enable_zone", "disable_zone"}
            allow_deny_rules = self.tables.storage_table.get_allow_deny_rules()
            zone["permit_status"] = check_permission(user_id, allow_deny_rules)
        else:
            ## how in {"enable_zone", "disable_zone"}
            zone["permit_status"] = permission
            pass

        #logger.debug(f"@@@ zone = {zone}")

        bucket_names = [bucket.get("name") for bucket in zone.get("buckets", [])]
        logger.debug(f"@@@ bucket_names = {bucket_names}")
        bucket_names = uniq_d(bucket_names)
        if bucket_names:
            logger.debug(f"@@@ bucket names are not unique: {bucket_names}")
            raise Exception(f"update_zone: bucket names are not unique: {bucket_names}")

        for bucket in zone.get("buckets", []):
            if not bucket.get("bkt_policy"):
                bucket["bkt_policy"] = "none"
                # bucket name and policy will be checed in `check_zone_values`
                pass
            pass

        need_uniquify = False
        access_keys = zone.get("access_keys", [])
        for accessKey in access_keys:
            if not accessKey.get("access_key"):  # (unset) or ""
                accessKey["access_key"] = ""   # temporary value
                need_uniquify = True   # access_key is updated in uniquify_zone
                pass

            _encrypt_or_generate(accessKey, "secret_key")

            if not accessKey.get("key_policy"):  # (unset) or ""
                accessKey["key_policy"] = "readwrite"
            # key_policy will be checked in `check_pool_dict_is_sound`
            pass

        logger.debug(f"@@@ CHECK_SCHEMA")
        check_pool_is_well_formed(zone, user_id)
        logger.debug(f"@@@ CHECK_SCHEMA END")
        check_pool_dict_is_sound(zone, user_id, self.adm_conf)
        self._check_zone_values(user_id, zone)

        directHostnames = zone["direct_hostnames"]
        logger.debug(f"@@@ directHostnames = {directHostnames}")
        zone["direct_hostnames"] = [e.lower() for e in directHostnames]

        return need_uniquify

    def _check_zone_values(self, user_id, zone):
        logger.debug(f"+++")
        num_hostnames_of_zone = len(zone.get("direct_hostnames"))

        logger.debug(f"@@@ num_hostnames_of_zone = {num_hostnames_of_zone}")

        if num_hostnames_of_zone > self.max_direct_hostnames_per_user:
            raise Exception(f"update_zone: too many direct hostnames (limit per zone exceeded)")

        maxExpDate = int(self.system_settings_param["allowed_maximum_zone_exp_date"])
        if int(zone["expiration_date"]) > maxExpDate:
            raise Exception(f"update_zone: expiration date is beyond the system limit")

        for h in zone.get("direct_hostnames", []):
            self._check_direct_hostname(h)
            pass

        self._check_user_group(user_id, zone)

        _check_bucket_names(zone)
        return

    def _clear_route(self, zone_id, zone):
        # we need to flush the routing table entry of zone_id before,
        # to make the controller checks minio_address_table and zone.
        ##route = zone_to_route(zone)
        self.tables.routing_table.delete_route(zone_id)
        pass

    def _lock_and_store_zone(self, user_id, zone_id, zone, need_conflict_check, need_uniquify):
        lock = LockDB(self.tables.storage_table, "Adm")
        ##key = f"{self.storage_table_lock_prefix}"
        lock_status = False
        try:
            ##lock_status = lock.lock(key, self.timeout)
            lock_status = self._lock_pool_table(lock)
            if need_conflict_check or need_uniquify:
                zone_id = self._uniquify_zone(user_id, zone_id, zone)
            self.tables.storage_table.set_pool(zone_id, zone)
            self.tables.storage_table.set_atime(zone_id, "0")
        finally:
            ##lock.unlock()
            self._unlock_pool_table(lock)
            pass
        return zone_id

    def _get_all_keys(self, zone_id):
        ## (IT DOSE NOT EXCLUDE OF IDS OF GIVEN POOL).
        pools = set(self.tables.storage_table.list_pool_ids(None))
        keys = []
        for id in pools:
            desc = self.tables.storage_table.get_pool(id)
            if desc is None:
                continue
            ids = _list_access_keys(desc)
            keys.extend(ids)
            pass
        return pools.union(set(keys))

    def _uniquify_zone(self, user_id, zone_id, zone):
        reasons = []
        num_zones_of_user = 0

        allkeys = self._get_all_keys(zone_id)
        logger.debug(f"AHO all-keys={allkeys}")
        allkeys_orig = allkeys.copy()

        if not zone_id:
            zone_id = _gen_unique_key(gen_access_key_id, allkeys)
            logger.debug(f"@@@ zone_id = {zone_id}")

        access_keys = zone.get("access_keys", [])
        for access_key in access_keys:
            if not access_key.get("access_key"):
                access_key["access_key"] = _gen_unique_key(gen_access_key_id, allkeys)
                pass
            pass

        for z_id in self.tables.storage_table.list_pool_ids(None):
            if z_id == zone_id:
                continue
            z = self.tables.storage_table.get_pool(z_id)
            if z is None:
                continue
            reasons += check_conflict(zone_id, zone, z_id, z)
            if z.get("owner_uid") == user_id:
                num_zones_of_user += 1
                pass
            pass

        if reasons != []:
            raise Exception(f"update_zone: conflict with another zone: {reasons}")

        if num_zones_of_user > self.max_zone_per_user:
            raise Exception(f"update_zone: too many zones (limit per user exceeded)")

        return zone_id

    def _send_decoy_with_zoneid_ptr(self, traceid, zone_id):
        temp_access_keys = [{"access_key": zone_id}]
        zoneID_accessible_zone = {"access_keys": temp_access_keys,
                                  "direct_hostnames": []}
        try:
            self.tables.storage_table.ins_ptr(zone_id, zoneID_accessible_zone)
            ## Trigger initialize.
            status = self.access_mux_for_pool(traceid, zone_id, force=True, access_key=zone_id)
        except Exception as e:
            ## (IGNORE-FATAL-ERROR)
            logger.exception(e)
            pass
        finally:
            self.tables.storage_table.del_ptr(zone_id, zoneID_accessible_zone)
            pass
        return

    def fetch_current_mode(self, zoneID):
        return self.tables.storage_table.get_mode(zoneID)

    def set_current_mode(self, zoneID, state):
        o = self.fetch_current_mode(zoneID)
        logger.debug(f"pool-state change pool=({zoneID}): {o} to {state}")
        self.tables.storage_table.set_mode(zoneID, state)
        return

    def zone_to_user(self, zoneID):
        ## ADMIN, multiplexer   CODE CLONE @ multiplexer.py
        zone = self.tables.storage_table.get_pool(zoneID)
        return zone["owner_uid"] if zone else None

    def determine_expiration_date(self):
        now = int(time.time())
        maxExpDate = int(self.system_settings_param["allowed_maximum_zone_exp_date"])
        logger.debug(f"@@@ maxExpDate = {maxExpDate}")
        deflZoneLifetime = int(self.system_settings_param["default_zone_lifetime"])
        logger.debug(f"@@@ deflZoneLifetime = {deflZoneLifetime}")
        logger.debug(f"@@@ now = {now}")
        logger.debug(f"@@@ now + deflZoneLifetime = {now + deflZoneLifetime}")
        expDate = min(now + deflZoneLifetime, maxExpDate)
        logger.debug(f"@@@ timeleft = {expDate - now}")
        return str(expDate)

    def decrypt_access_keys(self, zone):
        """Decrypts secrets in the pool description for showing to a user.
        """
        access_keys = zone.get("access_keys", [])
        for accessKey in access_keys:
            accessKey["secret_key"] = decrypt_secret(accessKey["secret_key"])
            pass
        return

    def _pullup_mode(self, zoneID, zone):
        zone["minio_state"] = self.fetch_current_mode(zoneID)
        return

    def _pullup_atime(self, zoneID, zone):
        # we do not copy atime form routing table here.
        #  (1) manager periodically copy atime from routing table to zone table.
        #  (2) it's nouissance to access atime on routing table, because we must
        #      know minio's id that serves for this zone.
        atime = self.tables.storage_table.get_atime(zoneID)
        zone["atime"] = atime
        pass

    def _pullup_ptr(self, zoneID, zone, access_key_ptr, direct_host_ptr):
        ##AHO
        zone["accessKeysPtr"] = [{"name": e, "ptr": v} for (e, v) in access_key_ptr if v == zoneID]
        zone["directHostnamePtr"] = [{"name": e, "ptr": v} for (e, v) in direct_host_ptr if v == zoneID]
        return

    def _add_info_for_webui(self, zoneID, zone, groups):
        zone["groups"] = groups
        zone["directHostnameDomains"] = self.direct_hostname_domains
        zone["facadeHostname"] = self.facade_hostname
        zone["endpoint_url"] = self.endpoint_urls(zone)
        return

    def fetch_zone_list(self, user_id, extra_info=False, include_atime=False,
                        decrypt=False, include_userinfo=False, zone_id=None):

        logger.debug(f"@@@ zone_id = {zone_id}")
        groups = None
        if include_userinfo:
            ui = self.tables.get_user(user_id)
            groups = ui.get("groups") if ui is not None else None
        zone_list = []
        broken_zones = []
        if extra_info:
            (access_key_ptr, direct_host_ptr) = self.tables.storage_table.get_ptr_list()
        else:
            (access_key_ptr, direct_host_ptr) = (None, None)

        for zoneID in self.tables.storage_table.list_pool_ids(zone_id):
            logger.debug(f"@@@ zoneID = {zoneID}")
            zone = self.tables.storage_table.get_pool(zoneID)

            if zone is None:
                logger.error(f"INCOMPLETE ZONE: {zoneID}")
                broken_zones.append(zoneID)
                continue

            if user_id and zone["owner_uid"] != user_id:
                continue

            zone["pool_name"] = zoneID

            if decrypt:
                self.decrypt_access_keys(zone)
                pass

            self._pullup_mode(zoneID, zone)
            if include_atime:
                self._pullup_atime(zoneID, zone)
                pass

            if extra_info:
                self._pullup_ptr(zoneID, zone, access_key_ptr, direct_host_ptr)
                pass

            if include_userinfo:
                self._add_info_for_webui(zoneID, zone, groups)
                pass

            zone_list.append(zone)
            pass
        # logger.debug(f"@@@ {zone_list} {broken_zones}")
        return (zone_list, broken_zones)

    def endpoint_urls(self, zone):
        template = self.system_settings_param["endpoint_url"]
        return ([template.format(hostname=h)
                 for h in [self.facade_hostname]] +
                [template.format(hostname=h)
                 for h in zone.get("direct_hostnames", [])])

    pass
