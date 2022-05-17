"""Pool mangement."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import string
import sys
import time
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables
from lenticularis.table import StorageTable
from lenticularis.utility import decrypt_secret, encrypt_secret
from lenticularis.utility import gen_access_key_id, gen_secret_access_key
from lenticularis.utility import logger
from lenticularis.utility import pick_one, check_permission
from lenticularis.utility import check_mux_access, host_port
from lenticularis.utility import uniq_d
from lenticularis.zoneutil import check_zone_schema, check_pool_dict_is_sound
from lenticularis.zoneutil import merge_pool_descriptions, check_conflict
from lenticularis.zoneutil import compare_access_keys, compare_buckets_directory
from lenticularis.zoneutil import compare_buckets, check_policy
from lenticularis.utility import tracing


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
    return bucket_keys == {"key", "policy"}

def _check_access_key_fmt(access_key):
    access_key_keys = set(access_key.keys())
    return ({"access_key"}.issubset(access_key_keys) and
            access_key_keys.issubset({"access_key", "secret_key", "policy_name"}))

def _check_create_bucket_keys(zone):
    """ zone ::= {"buckets": [{"key": bucket_name,
                               "policy": policy}]}
    """
    if zone.keys() != {"buckets"}:
        raise Exception(f"update_buckets: invalid key set: {set(zone.keys())}")
    if not all(_check_bucket_fmt(bucket) for bucket in zone["buckets"]):
        raise Exception(f"update_buckets: invalid bucket: {zone}")

def _check_change_secret_keys(zone):
    """ zone ::= {"access_keys": [accessKey]}
        accessKey ::= {"access_key": access_key_id,
                       "secret_key": secret (optional),
                       "policy_name": policy (optional) }
    """
    if zone.keys() != {"access_keys"}:
        raise Exception(f"update_secret_keys: invalid key set: {set(zone.keys())}")
    if not all(_check_access_key_fmt(access_key) for access_key in zone["access_keys"]):
        raise Exception(f"change_secret_key: invalid accessKey: {zone}")

def _check_zone_keys(zone):
    given_keys = set(zone.keys())
    mandatory_keys = StorageTable.pool_desc_required_keys
    optional_keys = StorageTable.pool_desc_optional_keys
    allowed_keys = mandatory_keys.union(optional_keys)
    ##mandatory_keys = {"owner_gid", "pool_directory", "buckets", "access_keys",
    ##                  "direct_hostnames", "expiration_date", "online_status"}
    ##allowed_keys = mandatory_keys.union({"user", "root_secret", "admission_status"})
    if not mandatory_keys.issubset(given_keys):
        raise Exception(f"upsert_zone: invalid key set: missing {mandatory_keys - given_keys}")
    if not given_keys.issubset(allowed_keys):
        raise Exception(f"upsert_zone: invalid key set {given_keys - allowed_keys}")

def check_pool_owner(user_id, pool_id, pool):
    ## It uses a user-id as an owner if it is undefined."""
    ##AHO
    owner = pool.get("owner_uid", user_id)
    if owner != user_id:
        raise Exception(f"Mismatch in pool owner and authenticated user:"
                        f" owner={owner} to user={user_id}")

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

def _check_bucket_names(zone):
    for bucket in zone.get("buckets", []):
        _check_bucket_name(zone, bucket)

def _check_bucket_name(zone, bucket):
    name = bucket["key"]
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

    check_policy(bucket["policy"])  # {"none", "upload", "download", "public"}

def _check_direct_hostname_flat(host_label):
    logger.error(f"@@@ check_direct_hostname_flat")
    # logger.error(f"@@@ check_direct_hostname_flat XXX FIXME")
    if '.' in host_label:
        raise Exception(f"invalid direct hostname: {host_label}: only one level label is allowed")
    _check_rfc1035_label(host_label)
    _check_rfc1122_hostname(host_label)

def _check_rfc1035_label(label):
    if len(label) > 63:
        raise Exception(f"{label}: too long")
    if len(label) < 1:
        raise Exception(f"{label}: too short")

def _check_rfc1122_hostname(label):
    alnum = string.ascii_lowercase + string.digits
    if not all(c in alnum + '-' for c in label):
        raise Exception(f"{label}: contains invalid char(s)")
    if not label[0] in alnum:
        raise Exception(f"{label}: must start with a letter or a digit")
    if not label[-1] in alnum:
        raise Exception(f"{label}: must end with a letter or a digit")

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


class ZoneAdm():

    def __init__(self, adm_conf):
        self.adm_conf = adm_conf

        controller_param = adm_conf["lenticularis"]["controller"]
        self.timeout = int(controller_param["max_lock_duration"])

        multiplexer_param = adm_conf["lenticularis"]["multiplexer"]
        self.facade_hostname = multiplexer_param["facade_hostname"]

        system_settings_param = adm_conf["lenticularis"]["system_settings"]
        self.system_settings_param = system_settings_param
        self.direct_hostname_domains = [h.lower() for h in system_settings_param["direct_hostname_domains"]]
        self.reserved_hostnames = [h.lower() for h in self.system_settings_param["reserved_hostnames"]]
        self.max_zone_per_user = int(system_settings_param["max_zone_per_user"])
        self.max_direct_hostnames_per_user = int(system_settings_param["max_direct_hostnames_per_user"])
        self.decoy_connection_timeout = int(system_settings_param["decoy_connection_timeout"])

        self.tables = get_tables(adm_conf)


    def fix_affected_zone(self, traceid):
        allow_deny_rules = self.tables.storage_table.get_allow_deny_rules()
        fixed = []
        for z_id in self.tables.storage_table.list_pool_ids(None):
            logger.debug(f"@@@ z_id = {z_id}")
            zone = self.tables.storage_table.get_zone(z_id)
            assert zone is not None
            user_id = zone["owner_uid"]

            ui = self.fetch_unix_user_info(user_id)
            if ui:
                groups = ui.get("groups", [])
                group = zone.get("owner_gid")
            else:
                groups = []
                group = None

            permission = "allowed" if (ui
                and any(grp for grp in groups if grp == group)
                and check_permission(user_id, allow_deny_rules) == "allowed"
                ) else "denied"

            if zone["admission_status"] != "denied" and not permission:
                self.disable_zone(traceid, user_id, z_id)
                fixed.append(z_id)
                logger.debug(f"permission dropped: {z_id} {user_id} {zone['admission_status']} => {permission}")
        return fixed

    def store_allow_deny_rules(self, allow_deny_rules):
        self.tables.storage_table.ins_allow_deny_rules(allow_deny_rules)

    def fetch_allow_deny_rules(self):
        return self.tables.storage_table.get_allow_deny_rules()

    def list_unixUsers(self):
        return list(self.tables.storage_table.get_unixUsers_list())

    def store_unix_user_info(self, user_id, uinfo):
        self.tables.storage_table.ins_unix_user_info(user_id, uinfo)

    def fetch_unix_user_info(self, user_id):
        return self.tables.storage_table.get_unix_user_info(user_id)

    def check_user(self, user_id):  # API
        return self.fetch_unix_user_info(user_id) is not None

    def delete_unix_user_info(self, user_id):
        self.tables.storage_table.del_unix_user_info(user_id)


    def create_pool(self, traceid, user_id, zone_id, zone, *,
                    include_atime=False,
                    decrypt=False, initialize=True):
        assert user_id is not None
        assert zone_id is None
        assert initialize == True
        atime_from_arg = zone.pop("atime", None) if include_atime else None
        _check_zone_keys(zone)
        how = "create_zone"
        return self._do_create_pool(how, traceid, user_id, zone_id, zone,
                                    atime_from_arg=atime_from_arg,
                                    initialize=initialize,
                                    decrypt=decrypt)

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

    def change_secret(self, traceid, user_id, zone_id, zone, *,
                      include_atime=False,
                      decrypt=False, initialize=True):
        assert user_id is not None
        assert zone_id is not None
        _check_change_secret_keys(zone)
        how = "change_secret_key"
        return self._do_change_secret(how, traceid, user_id, zone_id, zone,
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
        zone = {"admission_status": "denied"}
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

    def reset_database(self, everything=False):
        self.tables.storage_table.clear_all(everything=everything)
        self.tables.process_table.clear_all(everything=everything)
        self.tables.routing_table.clear_routing(everything=everything)

    def print_database(self):
        self.tables.storage_table.printall()
        self.tables.process_table.printall()
        self.tables.routing_table.printall()
        print("---- memo\n"
              "  (storage table)\n"
              "  ac:pool -> access-time : string\n"
              "  ar:key -> secret : string\n"
              "  mo:pool -> mode : string\n"
              "  pr:: -> list of permissions of users (json)\n"
              "  ru:pool -> pool data (htable)\n"
              "  uu:user -> user info (json)\n"
              "  (process table)\n"
              "  mx:host -> route (htable)\n"
              "  ma:pool -> ? (htable)\n"
              "  lk:?? -> (lock)\n"
              "  (routing table)\n"
              "  aa:key -> route-description\n"
              "  at:address -> atime")

    def fetch_multiplexer_list(self):
        return self.tables.process_table.list_muxs()

    def fetch_process_list(self):
        return self.tables.process_table.list_minio_procs(None)

    def delete_process(self, processID):
        return self.tables.process_table.delete_minio_proc(processID)

    def flush_process_table(self, everything=False):
        self.tables.process_table.clear_all(everything=everything)

    def check_mux_access_for_zone(self, traceid, zoneID, force, access_key_id=None):
        """Tries to access a multiplexer of the zone, if minio of the zone is
        running. force=True to send a decoy regardless minio is
        running or not. if there are no zone, do nothing.
        """

        logger.debug(f"zone={zoneID}, access_key={access_key_id}, force={force}")

        procdesc = self.tables.process_table.get_minio_proc(zoneID)
        multiplexers = self.tables.process_table.list_muxs()
        logger.debug(f"@@@ MULTIPLEXERS = {multiplexers}")
        if procdesc:
            ## SEND PACKET TO MULTPLEXER OF THE MINIO, NOT MINIO ITSELF.
            mux_name = procdesc.get("mux_host")
            logger.debug(f"@@@ MUX_NAME = {mux_name}")
            # host = procdesc.get("minio_ep")  ### DO NOT SEND
            multiplexer = next(((host, port) for (host, port) in multiplexers if host == mux_name), None)
            if multiplexer is None:
                multiplexer = pick_one(multiplexers)
            logger.debug(f"@@@ MUX OF MINIO = {multiplexer}")
        elif force:
            multiplexer = pick_one(multiplexers)
            logger.debug(f"@@@ PICK ONE = {multiplexer}")
        else:
            ## Done if MinIO is not running.
            logger.debug(f"No check, as no MinIO instance is running.")
            return ""
        logger.debug(f"@@@ MULTIPLEXER = {multiplexer}")
        assert multiplexer is not None
        ## multiplexer is a pair of (host, port).
        host = host_port(multiplexer[0], multiplexer[1])
        if access_key_id is None:
            zone = self.tables.storage_table.get_zone(zoneID)
            if zone is None:
                ## Done if neither access-key nor zone.
                logger.debug(f"No check, as neither access-key nor zone.")
                return ""
            ## Choose any key in the list.
            access_key_id = _choose_any_access_key(zone)
        facade_hostname = self.facade_hostname
        status = check_mux_access(traceid,
                                   host,
                                   access_key_id,
                                   facade_hostname, self.decoy_connection_timeout)
        logger.debug(f"@@@ SEND DECOY STATUS {status}")
        return status

    ##def fetch_route_list(self):
    ##    return self.tables.routing_table.list_routes()

    def flush_routing_table(self, everything=False):
        self.tables.routing_table.clear_routing(everything=everything)


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

    def _do_create_pool(self, how, traceid, user_id, zoneID, zone, *,
                        permission=None,
                        atime_from_arg=None,
                        initialize=True,
                        decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._create_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)

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

    def _do_restore_pool(self, how, traceid, user_id, zoneID, zone, *,
                         permission=None,
                         atime_from_arg=None,
                         initialize=True,
                         decrypt=False):
        lock = LockDB(self.tables.storage_table, "Adm")
        try:
            self._lock_pool_entry(lock, zoneID)
            return self._create_pool_with_lock(
                how, traceid, user_id, zoneID, zone,
                permission, atime_from_arg, initialize, decrypt)
        finally:
            self._unlock_pool_entry(lock, zoneID)

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

    ####

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

    def _check_user_group(self, user_id, zone):
        ui = self.fetch_unix_user_info(user_id)
        groups = ui.get("groups") if ui else []
        group = zone.get("owner_gid") if zone else None
        if group not in groups:
            raise Exception(f"invalid group: {group}")

    def _check_direct_hostname(self, host_fqdn):
        host_fqdn = host_fqdn.lower()
        fns = {"flat": _check_direct_hostname_flat}

        criteria = self.system_settings_param["direct_hostname_validator"]
        logger.debug(f"@@@ {self.system_settings_param}")
        logger.debug(f"@@@ criteria = {criteria}")

        if any(host_fqdn == d for d in self.reserved_hostnames):
            raise Exception(f"{host_fqdn}: the name is reserved'")

        try:
            domain = next(d for d in self.direct_hostname_domains if _is_subdomain(host_fqdn, d))
        except StopIteration:
            raise Exception(f"{host_fqdn}: direct hostname should "
                            f"ends with one of '{self.direct_hostname_domains}'")

        fn = fns.get(criteria)
        if fn is None:
            raise Exception(f"system configulation error: direct_hostname_validator '{criteria}' is not defined")
        fn(_strip_domain(host_fqdn, domain))


    def _halt_minio(self, traceid, pool_id, existing):
        """Stops a MinIO.  It throws an exception to break further processing.
        """
        mode = self.fetch_current_mode(pool_id)
        assert mode == "suspended"
        self._clear_route(pool_id, existing)
        status = self.check_mux_access_for_zone(traceid, pool_id, force=False)
        procdesc = self.tables.process_table.get_minio_proc(pool_id)
        if procdesc is not None:
            logger.error(f"COULD NOT STOP MINIO: {procdesc}")
        assert procdesc is None

    ##def _update_zone_with_lock_(self, how, traceid, user_id, zone_id, zone,
    ##                            permission, atime_from_arg,
    ##                            initialize, decrypt):
    ##    existing = self.tables.storage_table.get_zone(zone_id) if zone_id else None
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
    ##            status = self.check_mux_access_for_zone(traceid, zone_id, force=False)
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


    def _create_pool_with_lock(self, how, traceid, user_id, zone_id, zone,
                               permission, atime_from_arg,
                               initialize, decrypt):
        assert how in {"create_zone", "restore_zone"}
        if how == "create_zone":
            assert zone_id is None
        elif how == "restore_zone":
            assert zone_id is not None

        existing = self.tables.storage_table.get_zone(zone_id) if zone_id else None
        if existing:
            check_pool_owner(user_id, zone_id, existing)

        (need_initialize, need_uniquify) = self._prepare_zone(
            user_id, zone_id, existing, zone, permission, how)

        need_initialize = need_initialize and initialize

        omode = None
        if not need_initialize:
            omode = self.fetch_current_mode(zone_id)
        if zone_id:
            self.set_current_mode(zone_id, "suspended")

        if existing and initialize:
            ## how = "restore_zone"
            self._halt_minio(traceid, zone_id, existing)

        ## NO FURTHER PROCESSING IF _halt_minio FAILS.

        need_conflict_check = existing is not None
        zone_id = self._lock_and_store_zone(user_id, zone_id, zone, need_conflict_check, need_uniquify)

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
        self.tables.storage_table.ins_ptr(zone_id, zone)

        if omode:
            self.set_current_mode(zone_id, omode)
            mode = omode
        elif not initialize:
            mode = None
        else:
            mode = self.fetch_current_mode(zone_id)

        if initialize and mode not in {"ready"}:
            logger.error(f"initialize: error: mode is not ready: {mode}")
            raise Exception(f"initialize: error: mode is not ready: {mode}")
        else:
            pass

        zone["zoneID"] = zone_id
        if decrypt:
            self.decrypt_access_keys(zone)
        return zone

    def _update_pool_with_lock(self, how, traceid, user_id, zone_id, zone,
                               permission, atime_from_arg,
                               initialize, decrypt):
        assert how in {"update_zone", "update_buckets" "change_secret_key",
                       "disable_zone", "enable_zone"}
        assert how not in {"restore_zone", "create_zone", "delete_zone"}
        assert zone_id is not None
        existing = self.tables.storage_table.get_zone(zone_id)
        if not existing:
            raise Exception(f"Non-existing pool is specified: pool={zone_id}")
        check_pool_owner(user_id, zone_id, existing)

        (need_initialize, need_uniquify) = self._prepare_zone(
            user_id, zone_id, existing, zone, permission, how)

        need_initialize = need_initialize and initialize

        omode = None
        if not need_initialize:
            omode = self.fetch_current_mode(zone_id)

        if zone_id:
            self.set_current_mode(zone_id, "suspended")

        if initialize:
            self._halt_minio(traceid, zone_id, existing)

        ## NO FURTHER PROCESSING IF _halt_minio FAILS.

        need_conflict_check = True
        zone_id = self._lock_and_store_zone(user_id, zone_id, zone, need_conflict_check, need_uniquify)

        try:
            if need_initialize:
                self.set_current_mode(zone_id, "initial")
                self._send_decoy_with_zoneid_ptr(traceid, zone_id)  # trigger initialize minio
            else:
                pass
        except Exception as e:
            logger.debug(f"@@@ ignore exception {e}")
            pass

        if atime_from_arg:
            self.tables.storage_table.set_atime(zone_id, atime_from_arg)
        self.tables.storage_table.ins_ptr(zone_id, zone)

        if omode:
            self.set_current_mode(zone_id, omode)
            mode = omode
        elif not initialize:
            mode = None
        else:
            mode = self.fetch_current_mode(zone_id)

        if not initialize:
            pass
        elif mode not in {"ready"}:
            logger.error(f"initialize: error: mode is not ready: {mode}")
            raise Exception(f"initialize: error: mode is not ready: {mode}")
        else:
            pass

        zone["zoneID"] = zone_id
        if decrypt:
            self.decrypt_access_keys(zone)
        return zone

    def _delete_pool_with_lock(self, how, traceid, user_id, zone_id, zone,
                               permission, atime_from_arg,
                               initialize, decrypt):
        assert not initialize
        assert not decrypt
        existing = self.tables.storage_table.get_zone(zone_id) if zone_id else None
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
        zone["zoneID"] = zone_id
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
        name = bucket["key"]

        if any(b["key"] == name for b in existing.get("buckets", [])):
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
        ## assert(permission is None)
        need_uniquify = self._regularize_pool_dict(user_id, existing, zone, permission)

        if zone_id:
            mode = self.fetch_current_mode(zone_id)
        else:
            mode = None
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
            zone["admission_status"] = check_permission(user_id, allow_deny_rules)
        else:
            ## how in {"enable_zone", "disable_zone"}
            zone["admission_status"] = permission

        #logger.debug(f"@@@ zone = {zone}")

        bucket_names = [bucket.get("key") for bucket in zone.get("buckets", [])]
        logger.debug(f"@@@ bucket_names = {bucket_names}")
        bucket_names = uniq_d(bucket_names)
        if bucket_names:
            logger.debug(f"@@@ bucket names are not unique: {bucket_names}")
            raise Exception(f"update_zone: bucket names are not unique: {bucket_names}")

        for bucket in zone.get("buckets", []):
            if not bucket.get("policy"):
                bucket["policy"] = "none"
            # bucket name and policy will be checed in `check_zone_values`

        need_uniquify = False
        access_keys = zone.get("access_keys", [])
        for accessKey in access_keys:
            if not accessKey.get("access_key"):  # (unset) or ""
                accessKey["access_key"] = ""   # temporary value
                need_uniquify = True   # access_key is updated in uniquify_zone

            _encrypt_or_generate(accessKey, "secret_key")

            if not accessKey.get("policy_name"):  # (unset) or ""
                accessKey["policy_name"] = "readwrite"
            # policy_name will be checked in `check_pool_dict_is_sound`

        logger.debug(f"@@@ CHECK_SCHEMA")
        check_zone_schema(zone, user_id)
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

        self._check_user_group(user_id, zone)

        _check_bucket_names(zone)


    def _clear_route(self, zone_id, zone):
        # we need to flush the routing table entry of zone_id before,
        # to make the controller checks minio_address_table and zone.
        ##route = zone_to_route(zone)
        self.tables.routing_table.delete_route(zone_id)

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
        return zone_id

    def _get_all_keys(self, zone_id):
        ## (IT DOSE NOT EXCLUDE OF IDS OF GIVEN POOL).
        pools = set(self.tables.storage_table.list_pool_ids(None))
        keys = []
        for id in pools:
            desc = self.tables.storage_table.get_zone(id)
            if desc is None:
                continue
            ids = _list_access_keys(desc)
            keys.extend(ids)
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

        for z_id in self.tables.storage_table.list_pool_ids(None):
            if z_id == zone_id:
                continue
            z = self.tables.storage_table.get_zone(z_id)
            if z is None:
                continue
            reasons += check_conflict(zone_id, zone, z_id, z)
            if z.get("owner_uid") == user_id:
                num_zones_of_user += 1

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
            status = self.check_mux_access_for_zone(traceid, zone_id, force=True, access_key_id=zone_id)
        except Exception as e:
            ## (IGNORE-FATAL-ERROR)
            logger.exception(e)
            pass
        finally:
            self.tables.storage_table.del_ptr(zone_id, zoneID_accessible_zone)

    def fetch_current_mode(self, zoneID):
        return self.tables.storage_table.get_mode(zoneID)

    def set_current_mode(self, zoneID, state):
        o = self.fetch_current_mode(zoneID)
        logger.debug(f"pool-state change pool=({zoneID}): {o} to {state}")
        self.tables.storage_table.set_mode(zoneID, state)

    def zone_to_user(self, zoneID):
        ## ADMIN, multiplexer   CODE CLONE @ multiplexer.py
        zone = self.tables.storage_table.get_zone(zoneID)
        return zone["owner_uid"] if zone else None

    def exp_date(self):
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

    def generate_template(self, user_id):
        ui = self.fetch_unix_user_info(user_id)
        assert ui is not None
        groups = ui.get("groups")

        ## Excluding: "root_secret".

        return {
            "owner_uid": user_id,
            "owner_gid": groups[0],
            "pool_directory": "",
            "buckets": [],
            "access_keys": [
                   {"policy_name": "readwrite"},
                   {"policy_name": "readonly"},
                   {"policy_name": "writeonly"}],
            "direct_hostnames": [],
            "expiration_date": self.exp_date(),
            "online_status": "online",
            "groups": groups,
            "atime": "0",
            "directHostnameDomains": self.direct_hostname_domains,
            "facadeHostname": self.facade_hostname,
            "endpoint_url": self.endpoint_urls({"direct_hostnames": []})
        }

    def decrypt_access_keys(self, zone):
        """Decrypts secrets in the pool description for showing to a user.
        """
        access_keys = zone.get("access_keys", [])
        for accessKey in access_keys:
            accessKey["secret_key"] = decrypt_secret(accessKey["secret_key"])

    def _pullup_mode(self, zoneID, zone):
        zone["minio_state"] = self.fetch_current_mode(zoneID)

    def _pullup_atime(self, zoneID, zone):
        # we do not copy atime form routing table here.
        #  (1) manager periodically copy atime from routing table to zone table.
        #  (2) it's nouissance to access atime on routing table, because we must
        #      know minio's id that serves for this zone.
        atime = self.tables.storage_table.get_atime(zoneID)
        zone["atime"] = atime

    def _pullup_ptr(self, zoneID, zone, access_key_ptr, direct_host_ptr):
        ##AHO
        zone["accessKeysPtr"] = [{"key": e, "ptr": v} for (e, v) in access_key_ptr if v == zoneID]
        zone["directHostnamePtr"] = [{"key": e, "ptr": v} for (e, v) in direct_host_ptr if v == zoneID]

    def _add_info_for_webui(self, zoneID, zone, groups):
        zone["groups"] = groups
        zone["directHostnameDomains"] = self.direct_hostname_domains
        zone["facadeHostname"] = self.facade_hostname
        zone["endpoint_url"] = self.endpoint_urls(zone)

    def fetch_zone_list(self, user_id, extra_info=False, include_atime=False,
                        decrypt=False, include_userinfo=False, zone_id=None):

        # logger.debug(f"@@@ zone_id = {zone_id}")
        groups = None
        if include_userinfo:
            ui = self.fetch_unix_user_info(user_id)
            groups = ui.get("groups") if ui is not None else None
        zone_list = []
        broken_zones = []
        if extra_info:
            (access_key_ptr, direct_host_ptr) = self.tables.storage_table.get_ptr_list()
        else:
            (access_key_ptr, direct_host_ptr) = (None, None)

        for zoneID in self.tables.storage_table.list_pool_ids(zone_id):
            #logger.debug(f"@@@ zoneID = {zoneID}")
            zone = self.tables.storage_table.get_zone(zoneID)

            if zone is None:
                logger.error(f"INCOMPLETE ZONE: {zoneID}")
                broken_zones.append(zoneID)
                continue

            if user_id and zone["owner_uid"] != user_id:
                continue

            zone["zoneID"] = zoneID

            if decrypt:
                self.decrypt_access_keys(zone)

            self._pullup_mode(zoneID, zone)

            if include_atime:
                self._pullup_atime(zoneID, zone)

            if extra_info:
                self._pullup_ptr(zoneID, zone, access_key_ptr, direct_host_ptr)

            if include_userinfo:
                self._add_info_for_webui(zoneID, zone, groups)

            zone_list.append(zone)
        # logger.debug(f"@@@ {zone_list} {broken_zones}")
        return (zone_list, broken_zones)

    def endpoint_urls(self, zone):
        template = self.system_settings_param["endpoint_url"]
        return ([template.format(hostname=h)
                 for h in [self.facade_hostname]] +
                [template.format(hostname=h)
                 for h in zone.get("direct_hostnames", [])])
