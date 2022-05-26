"""Accessors for the set of Redis DBs."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
import json
from lenticularis.utility import logger
from lenticularis.dbase import DBase


# Redis DB number.

STORAGE_TABLE_ID = 1
PROCESS_TABLE_ID = 2
ROUTING_TABLE_ID = 3


def _get_mux_host_port(desc):
    ## (for pyright).
    return (desc["host"], desc["port"])


def get_tables(mux_conf):
    redis_conf = mux_conf["redis"]
    redis_host = redis_conf["host"]
    redis_port = redis_conf["port"]
    redis_password = redis_conf["password"]
    _storage_table = StorageTable(redis_host, redis_port, STORAGE_TABLE_ID,
                                  redis_password)
    _process_table = ProcessTable(redis_host, redis_port, PROCESS_TABLE_ID,
                                  redis_password)
    _routing_table = RoutingTable(redis_host, redis_port, ROUTING_TABLE_ID,
                                  redis_password)
    return Tables(_storage_table, _process_table, _routing_table)


def _print_table(r, name):
    print(f"---- {name}")
    for key in r.scan_iter("*"):
        print(f"{key}")
        pass
    return


def delete_all(r, match):
    for key in r.scan_iter(f"{match}*"):
        r.delete(key)
        pass
    return


def _scan_table(r, prefix, target, *, value=None):
    """Returns an iterator to scan a table for a prefix+target pattern,
    where target is * if it is None.  It drops the prefix from the
    returned key.  It returns key+value pairs, where value is None if
    value= is not specified.
    """
    target = target if target else "*"
    pattern = f"{prefix}{target}"
    striplen = len(prefix)
    cursor = "0"
    while cursor != 0:
        (cursor, data) = r.scan(cursor=cursor, match=pattern)
        for rawkey in data:
            key = rawkey[striplen:]
            if value == "get":
                val = r.get(rawkey)
                yield (key, val)
            elif value is not None:
                val = value(key)
                yield (key, val)
            else:
                yield (key, None)
                pass
            pass
        pass
    return


class Tables():
    def __init__(self, storage_table, process_table, routing_table):
        self.storage_table = storage_table
        self.process_table = process_table
        self.routing_table = routing_table
        return

    pass


class TableCommon():
    def __init__(self, host, port, db, password):
        self.dbase = DBase(host, port, db, password)
        return


class StorageTable(TableCommon):
    _pool_desc_prefix = "po:"
    _pool_state_prefix = "ps:"
    allowDenyRuleKey = "pr::"
    _unix_user_prefix = "uu:"
    storage_table_lock_prefix = "zk:"
    _access_key_id_prefix = "ar:"
    directHostnamePrefix = "dr:"
    atimePrefix = "ac:"
    hashes_ = {_pool_desc_prefix}
    structured = {"buckets", "access_keys", "direct_hostnames"}

    ## See zone_schema for json schema.

    pool_desc_required_keys = {
        "owner_gid", "buckets_directory", "buckets", "access_keys",
        "direct_hostnames", "expiration_date", "online_status"}
    pool_desc_optional_keys = {
        "owner_uid", "root_secret",
        "probe_access",
        "admission_status"}

    _pool_desc_keys = pool_desc_required_keys.union(pool_desc_optional_keys)

    _access_keys_keys = {
        "policy_name", "access_key", "secret_key"}

    def set_pool(self, zoneID, pooldesc):
        assert set(pooldesc.keys()).issubset(self._pool_desc_keys)
        key = f"{self._pool_desc_prefix}{zoneID}"
        return self.dbase.hset_map(key, pooldesc, self.structured)

    def ins_ptr(self, zoneID, dict):
        # logger.debug(f"+++ {zoneID} {dict}")
        ## accessKeys must exist.
        for a in dict.get("access_keys"):
            access_key_id = a.get("access_key")
            if access_key_id:
                key = f"{self._access_key_id_prefix}{access_key_id}"
                self.dbase.set(key, zoneID)
                pass
            pass
        ## directHostnames must exist.
        for directHostname in dict.get("direct_hostnames"):
            key = f"{self.directHostnamePrefix}{directHostname}"
            self.dbase.set(key, zoneID)
            pass
        return None

    def del_zone(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        return self.dbase.delete(f"{self._pool_desc_prefix}{zoneID}")

    def del_ptr(self, zoneID, dict):
        # logger.debug(f"+++ {zoneID} {dict}")
        # logger.debug(f"@@@ del_ptr zoneID {zoneID} dict {dict}")
        for a in dict.get("access_keys", []):  # access_keys may be absent
            access_key_id = a.get("access_key")
            if access_key_id:
                # logger.debug(f"@@@ del_ptr access_key_id {access_key_id}")
                key = f"{self._access_key_id_prefix}{access_key_id}"
                self.dbase.delete(key)
                pass
            pass
        for directHostname in dict.get("direct_hostnames", []):  # directHostname may be absent
            # logger.debug(f"@@@ del_ptr directHostname {directHostname}")
            key = f"{self.directHostnamePrefix}{directHostname}"
            self.dbase.delete(key)
            pass
        return None

    def get_pool(self, pool_id):
        key = f"{self._pool_desc_prefix}{pool_id}"
        if not self.dbase.hexists(key, "owner_uid"):
            return None
        return self.dbase.hget_map(key, self.structured)

    def get_ptr_list(self):
        # logger.debug(f"+++ ")
        access_key_ptr = _scan_table(self.dbase.r, self._access_key_id_prefix, None, value="get")
        direct_host_ptr = _scan_table(self.dbase.r, self.directHostnamePrefix, None, value="get")
        return (list(access_key_ptr), list(direct_host_ptr))

    def get_pool_by_access_key(self, access_key_id):
        # logger.debug(f"+++ {access_key_id}")
        key = f"{self._access_key_id_prefix}{access_key_id}"
        return self.dbase.get(key)

    def get_pool_id_by_direct_hostname(self, directHostname):
        # logger.debug(f"+++ {directHostname}")
        key = f"{self.directHostnamePrefix}{directHostname}"
        return self.dbase.get(key)

    def set_permission(self, zoneID, permission):
        # logger.debug(f"+++ {zoneID} {permission}")
        key = f"{self._pool_desc_prefix}{zoneID}"
        return self.dbase.hset(key, "admission_status", permission, self.structured)

    def set_atime(self, zoneID, atime):
        # logger.debug(f"+++ {zoneID} {atime}")
        key = f"{self.atimePrefix}{zoneID}"
        return self.dbase.set(key, atime)

    def get_atime(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self.atimePrefix}{zoneID}"
        return self.dbase.get(key)

    def del_atime(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self.atimePrefix}{zoneID}"
        return self.dbase.delete(key)

    def set_pool_state(self, pool_id, state, reason):
        key = f"{self._pool_state_prefix}{pool_id}"
        ee = json.dumps((state, reason))
        return self.dbase.set(key, ee)

    def set_mode(self, zoneID, mode):
        # logger.debug(f"+++ {zoneID} {mode}")
        key = f"{self._pool_state_prefix}{zoneID}"
        ee = json.dumps((mode, None))
        return self.dbase.set(key, ee)

    def get_mode(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self._pool_state_prefix}{zoneID}"
        ee = self.dbase.get(key)
        (state, _) = (json.loads(ee, parse_int=None)
                      if ee is not None else (None, None))
        return state

    def del_mode(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self._pool_state_prefix}{zoneID}"
        return self.dbase.delete(key)

    def ins_allow_deny_rules(self, rule):
        # logger.debug(f"+++ {rule}")
        return self.dbase.set(self.allowDenyRuleKey, json.dumps(rule))

    def get_allow_deny_rules(self):
        # logger.debug(f"+++ ")
        v = self.dbase.get(self.allowDenyRuleKey)
        # logger.debug(f"@@@ v = {v}")
        if not v:
            return []
        return json.loads(v, parse_int=None)

    def ins_unix_user_info(self, id, uinfo):
        # logger.debug(f"+++ {id} {uinfo}")
        key = f"{self._unix_user_prefix}{id}"
        return self.dbase.set(key, json.dumps(uinfo))

    def get_unix_user_info(self, id):
        # logger.debug(f"+++ {id}")
        key = f"{self._unix_user_prefix}{id}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def del_unix_user_info(self, id):
        # logger.debug(f"+++ {id}")
        key = f"{self._unix_user_prefix}{id}"
        return self.dbase.delete(key)

    def get_unixUsers_list(self):
        kk = _scan_table(self.dbase.r, self._unix_user_prefix, None)
        return [k for (k, _) in kk]

    def list_pool_ids(self, zoneID):
        kk = _scan_table(self.dbase.r, self._pool_desc_prefix, zoneID)
        return [k for (k, _) in kk]

    def clear_all(self, everything):
        delete_all(self.dbase.r, self._access_key_id_prefix)
        delete_all(self.dbase.r, self.directHostnamePrefix)
        delete_all(self.dbase.r, self._pool_desc_prefix)
        delete_all(self.dbase.r, self.atimePrefix)
        delete_all(self.dbase.r, self._pool_state_prefix)
        delete_all(self.dbase.r, self.storage_table_lock_prefix)
        if everything:
            delete_all(self.dbase.r, self.allowDenyRuleKey)
            delete_all(self.dbase.r, self._unix_user_prefix)

    def print_all(self):
        _print_table(self.dbase.r, "storage")
        return

    pass


class ProcessTable(TableCommon):
    _minio_process_prefix = "mn:"
    _mux_desc_prefix = "mx:"
    process_table_lock_prefix = "lk:"
    hashes_ = {_minio_process_prefix, _mux_desc_prefix}
    structured = {}

    ## See _record_minio_process for the content of a MinIO process.
    ## See _register_mux_info for the content of a Mux description.

    _minio_desc_keys = {
        "minio_ep", "minio_pid", "mux_host", "mux_port", "manager_pid",
        "admin", "password"}

    _mux_desc_keys = {
        "host", "port", "start_time", "last_interrupted_time"}

    def set_minio_proc(self, pool_id, procdesc, timeout):
        assert set(procdesc.keys()) == self._minio_desc_keys
        key = f"{self._minio_process_prefix}{pool_id}"
        self.set_minio_proc_expiry(pool_id, timeout)
        return self.dbase.hset_map(key, procdesc, self.structured)

    def get_minio_proc(self, pool_id):
        key = f"{self._minio_process_prefix}{pool_id}"
        if not self.dbase.hexists(key, "minio_ep"):
            return None
        procdesc = self.dbase.hget_map(key, self.structured)
        return procdesc

    def delete_minio_proc(self, pool_id):
        key = f"{self._minio_process_prefix}{pool_id}"
        return self.dbase.delete(key)

    def set_minio_proc_expiry(self, pool_id, timeout):
        key = f"{self._minio_process_prefix}{pool_id}"
        self.dbase.r.expire(key, timeout)
        return None

    def list_minio_procs(self, pool_id):
        return _scan_table(self.dbase.r, self._minio_process_prefix, pool_id, value=self.get_minio_proc)

    def set_mux(self, mux_ep, mux_desc, timeout):
        assert set(mux_desc.keys()) == self._mux_desc_keys
        key = f"{self._mux_desc_prefix}{mux_ep}"
        r = self.dbase.hset_map(key, mux_desc, self.structured)
        if timeout:
            self._set_mux_expiry(mux_ep, timeout)
        return r

    def get_mux(self, mux_ep):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        return self.dbase.hget_map(key, self.structured)

    def delete_mux(self, mux_ep):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        return self.dbase.delete(key)

    def _set_mux_expiry(self, mux_ep, timeout):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        self.dbase.r.expire(key, timeout)
        return None

    def list_muxs(self):
        vv = _scan_table(self.dbase.r, self._mux_desc_prefix, None,
                         value=self.get_mux)
        return vv

    def list_mux_eps(self):
        """Retruns a list of (host, port)."""
        vv = _scan_table(self.dbase.r, self._mux_desc_prefix, None,
                         value=self.get_mux)
        ep0 = [_get_mux_host_port(desc) for (k, desc) in vv]
        ep1 = sorted(list(set(ep0)))
        return ep1

    def clear_all(self, everything):
        """Clears Redis DB.  It leaves entires for multiplexers unless
        everything.
        """
        # logger.debug(f"@@@ FLUSHALL: EVERYTHING = {everything}")
        delete_all(self.dbase.r, self.process_table_lock_prefix)
        delete_all(self.dbase.r, self._minio_process_prefix)
        if everything:
            delete_all(self.dbase.r, self._mux_desc_prefix)
            pass
        return

    def print_all(self):
        _print_table(self.dbase.r, "process")
        return

    pass


def zone_to_route_(zone):
    ##logger.debug(f"zone = {zone}")
    access_keys = [i["access_key"] for i in zone.get("access_keys", [])]
    directHostnames = zone["direct_hostnames"]
    return {
        "access_keys": access_keys,
        "direct_hostnames": directHostnames,
    }


class RoutingTable(TableCommon):
    _minio_ep_prefix = "ep:"
    _bucket_prefix = "bu:"
    _probe_access_prefix = "wu:"
    _timestamp_prefix = "ts:"
    _host_style_prefix = "da:"
    _atime_prefix = "at:"
    hashes_ = {}
    structured = {}

    _bucket_desc_keys = {"pool", "policy"}

    def set_route(self, pool_id, ep, timeout):
        assert isinstance(ep, str)
        key = f"{self._minio_ep_prefix}{pool_id}"
        self.dbase.set(key, ep)
        ##self.dbase.r.expire(key, timeout)
        return

    def get_route(self, pool_id):
        key = f"{self._minio_ep_prefix}{pool_id}"
        return self.dbase.get(key)

    def delete_route(self, pool_id):
        key = f"{self._minio_ep_prefix}{pool_id}"
        self.dbase.delete(key)
        return

    def set_route_expiry(self, pool_id, timeout):
        key = f"{self._timestamp_prefix}{pool_id}"
        ts = int(time.time())
        self.dbase.set(key, f"{ts}")
        self.dbase.r.expire(key, timeout)
        return

    def get_route_expiry(self, pool_id):
        key = f"{self._timestamp_prefix}{pool_id}"
        return self.dbase.get(key)

    def delete_route_expiry(self, pool_id):
        key = f"{self._timestamp_prefix}{pool_id}"
        return self.dbase.delete(key)

    def get_route_by_direct_hostname_(self, directHostname):
        # logger.debug(f"+++ {directHostname}")
        key = f"{self._host_style_prefix}{directHostname}"
        return self.dbase.get(key)

    def list_routes(self):
        return _scan_table(self.dbase.r, self._minio_ep_prefix, None, value="get")

    def set_atime_expire_(self, addr, timeout):
        # logger.debug(f"+++ {addr} {timeout}")
        key = f"{self._atime_prefix}{addr}"
        return self.dbase.r.expire(key, timeout)

    def set_atime_by_addr_(self, addr, atime, default_ttl):
        ## addr is an endpoint of a minio.
        ## NOTE: keepttl is not used, because it is available in
        ## Redis-6.0 and later.
        key = f"{self._atime_prefix}{addr}"
        ttl = self.dbase.r.ttl(key)
        retval = self.dbase.set(key, atime)
        if ttl > 0:
            self.dbase.r.expire(key, ttl)
        else:
            self.dbase.r.expire(key, default_ttl)
        return retval

    def set_bucket(self, bucket, desc):
        assert set(desc.keys()) == self._bucket_desc_keys
        key = f"{self._bucket_prefix}{bucket}"
        v = json.dumps(desc)
        ok = self.dbase.r.setnx(key, v) != 0
        if ok:
            return (ok, None)
        o = self.get_bucket(bucket)
        if o is None:
            ## (Possible race, ignored).
            return (ok, None)
        else:
            return (ok, o.get("pool"))
        pass

    def get_bucket(self, bucket):
        key = f"{self._bucket_prefix}{bucket}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_bucket(self, bucket):
        key = f"{self._bucket_prefix}{bucket}"
        self.dbase.delete(key)
        return

    def set_probe_access(self, access_key, pool_id):
        key = f"{self._probe_access_prefix}{access_key}"
        self.dbase.set(key, pool_id)
        return

    def get_probe_access(self, access_key):
        key = f"{self._probe_access_prefix}{access_key}"
        return self.dbase.get(key)

    def delete_probe_access(self, access_key):
        key = f"{self._probe_access_prefix}{access_key}"
        self.dbase.delete(key)
        return

    def clear_routing(self, everything):
        delete_all(self.dbase.r, self._minio_ep_prefix)
        delete_all(self.dbase.r, self._bucket_prefix)
        delete_all(self.dbase.r, self._probe_access_prefix)
        delete_all(self.dbase.r, self._timestamp_prefix)
        delete_all(self.dbase.r, self._atime_prefix)
        return

    def clear_all_(self, everything):
        delete_all(self.dbase.r, self._host_style_prefix)
        delete_all(self.dbase.r, self._atime_prefix)
        return

    def print_all(self):
        _print_table(self.dbase.r, "routing")
        return

    pass
