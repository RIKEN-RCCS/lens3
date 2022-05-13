"""A set of three Redis DBs."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
import json
from lenticularis.utility import logger
from lenticularis.dbase import DBase


# Redis DB number.

STORAGE_TABLE_ID = 0
PROCESS_TABLE_ID = 2
ROUTING_TABLE_ID = 4


class TableCommon():
    def __init__(self, host, port, db, password):
        self.dbase = DBase(host, port, db, password)


class StorageTable(TableCommon):

    zoneIDPrefix = "ru:"
    access_key_id_prefix = "ar:"
    directHostnamePrefix = "dr:"
    atimePrefix = "ac:"
    modePrefix = "mo:"
    allowDenyRuleKey = "pr::"
    unixUserPrefix = "uu:"
    storage_table_lock_prefix = "zk:"
    hashes_ = {zoneIDPrefix}
    structured = {"buckets", "accessKeys", "directHostnames"}

    def ins_zone(self, zoneID, dict):
        ##logger.debug(f"ins_zone {zoneID} {dict}")
        key = f"{self.zoneIDPrefix}{zoneID}"
        return self.dbase.hset_map(key, dict, self.structured)

    def ins_ptr(self, zoneID, dict):
        # logger.debug(f"+++ {zoneID} {dict}")
        ## accessKeys must exist.
        for a in dict.get("accessKeys"):
            access_key_id = a.get("accessKeyID")
            if access_key_id:
                key = f"{self.access_key_id_prefix}{access_key_id}"
                self.dbase.set(key, zoneID)
        ## directHostnames must exist.
        for directHostname in dict.get("directHostnames"):
            key = f"{self.directHostnamePrefix}{directHostname}"
            self.dbase.set(key, zoneID)
        return None

    def del_zone(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        return self.dbase.delete(f"{self.zoneIDPrefix}{zoneID}")

    def del_ptr(self, zoneID, dict):
        # logger.debug(f"+++ {zoneID} {dict}")
        # logger.debug(f"@@@ del_ptr zoneID {zoneID} dict {dict}")
        for a in dict.get("accessKeys", []):  # accessKeys may be absent
            access_key_id = a.get("accessKeyID")
            if access_key_id:
                # logger.debug(f"@@@ del_ptr access_key_id {access_key_id}")
                key = f"{self.access_key_id_prefix}{access_key_id}"
                self.dbase.delete(key)
        for directHostname in dict.get("directHostnames", []):  # directHostname may be absent
            # logger.debug(f"@@@ del_ptr directHostname {directHostname}")
            key = f"{self.directHostnamePrefix}{directHostname}"
            self.dbase.delete(key)
        return None

    def get_zone(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self.zoneIDPrefix}{zoneID}"
        if not self.dbase.hexists(key, "user"):
            return None
        return self.dbase.hget_map(key, self.structured)

    def get_ptr_list(self):
        # logger.debug(f"+++ ")
        access_key_ptr = _scan_strip(self.dbase.r, self.access_key_id_prefix, None, get_value="get")
        direct_host_ptr = _scan_strip(self.dbase.r, self.directHostnamePrefix, None, get_value="get")
        return (list(access_key_ptr), list(direct_host_ptr))

    def get_pool_by_access_key(self, access_key_id):
        # logger.debug(f"+++ {access_key_id}")
        key = f"{self.access_key_id_prefix}{access_key_id}"
        return self.dbase.get(key)

    def get_zoneID_by_directHostname(self, directHostname):
        # logger.debug(f"+++ {directHostname}")
        key = f"{self.directHostnamePrefix}{directHostname}"
        return self.dbase.get(key)

    def set_permission(self, zoneID, permission):
        # logger.debug(f"+++ {zoneID} {permission}")
        key = f"{self.zoneIDPrefix}{zoneID}"
        return self.dbase.hset(key, "operation_status", permission, self.structured)

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

    def set_mode(self, zoneID, mode):
        # logger.debug(f"+++ {zoneID} {mode}")
        key = f"{self.modePrefix}{zoneID}"
        return self.dbase.set(key, mode)

    def get_mode(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self.modePrefix}{zoneID}"
        return self.dbase.get(key)

    def del_mode(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self.modePrefix}{zoneID}"
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

    def ins_unixUserInfo(self, id, uinfo):
        # logger.debug(f"+++ {id} {uinfo}")
        key = f"{self.unixUserPrefix}{id}"
        return self.dbase.set(key, json.dumps(uinfo))

    def get_unixUserInfo(self, id):
        # logger.debug(f"+++ {id}")
        key = f"{self.unixUserPrefix}{id}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def del_unixUserInfo(self, id):
        # logger.debug(f"+++ {id}")
        key = f"{self.unixUserPrefix}{id}"
        return self.dbase.delete(key)

    def get_unixUsers_list(self):
        # logger.debug(f"+++ ")
        return _scan_strip(self.dbase.r, self.unixUserPrefix, None)

    def get_zoneID_list(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        return _scan_strip(self.dbase.r, self.zoneIDPrefix, zoneID)

    def clear_all(self, everything):
        delete_all(self.dbase.r, self.access_key_id_prefix)
        delete_all(self.dbase.r, self.directHostnamePrefix)
        delete_all(self.dbase.r, self.zoneIDPrefix)
        delete_all(self.dbase.r, self.atimePrefix)
        delete_all(self.dbase.r, self.modePrefix)
        delete_all(self.dbase.r, self.storage_table_lock_prefix)
        if everything:
            delete_all(self.dbase.r, self.allowDenyRuleKey)
            delete_all(self.dbase.r, self.unixUserPrefix)

    def printall(self):
        _prntall(self.dbase.r, "storage")

class ProcessTable(TableCommon):
    minioAddrPrefix = "ma:"
    muxPrefix = "mx:"
    process_table_lock_prefix = "lk:"
    hashes_ = {minioAddrPrefix, muxPrefix}
    structured = {"mux_conf"}

    def ins_minio_address(self, zoneID, minioAddr, timeout):
        # logger.debug(f"+++ {zoneID} {minioAddr} {timeout}")
        # logger.debug(f"@@@ MINIO_ADDRESS INSERT {zoneID} {minioAddr}")
        key = f"{self.minioAddrPrefix}{zoneID}"
        self.set_minio_address_expire(zoneID, timeout)
        return self.dbase.hset_map(key, minioAddr, self.structured)

    def del_minio_address(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        # logger.debug(f"@@@ MINIO_ADDRESS DELETE {zoneID}")
        key = f"{self.minioAddrPrefix}{zoneID}"
        return self.dbase.delete(key)

    def get_minio_address(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        key = f"{self.minioAddrPrefix}{zoneID}"
        if not self.dbase.hexists(key, "minioAddr"):
            # logger.debug(f"@@@ MINIO_ADDRESS GET {zoneID} None")
            return None
        minioAddr = self.dbase.hget_map(key, self.structured)
        # logger.debug(f"@@@ MINIO_ADDRESS GET {zoneID} {minioAddr}")
        return minioAddr

    def set_minio_address_expire(self, zoneID, timeout):
        # logger.debug(f"+++ {zoneID} {timeout}")
        key = f"{self.minioAddrPrefix}{zoneID}"
        self.dbase.r.expire(key, timeout)
        return None

    def get_minio_address_list(self, zoneID):
        # logger.debug(f"+++ {zoneID}")
        return _scan_strip(self.dbase.r, self.minioAddrPrefix, zoneID, get_value=self.get_minio_address)

    def set_mux(self, muxID, mux_val, timeout):
        # logger.debug(f"+++ {muxID} {mux_val} {timeout}")
        key = f"{self.muxPrefix}{muxID}"
        r = self.dbase.hset_map(key, mux_val, self.structured)
        if timeout:
            self.set_mux_expire(muxID, timeout)
        return r

    def set_mux_expire(self, muxID, timeout):
        # logger.debug(f"+++ {muxID} {timeout}")
        key = f"{self.muxPrefix}{muxID}"
        self.dbase.r.expire(key, timeout)
        return None

    def get_mux(self, muxID):
        # logger.debug(f"+++ {muxID}")
        key = f"{self.muxPrefix}{muxID}"
        if not self.dbase.hexists(key, "mux_conf"):
            return None
        return self.dbase.hget_map(key, self.structured)

    def del_mux(self, muxID):
        # logger.debug(f"+++ {muxID}")
        key = f"{self.muxPrefix}{muxID}"
        return self.dbase.delete(key)

    def get_mux_list(self, muxID):
        return _scan_strip(self.dbase.r, self.muxPrefix, muxID, get_value=self.get_mux)

    def clear_all(self, everything):
        """Clears Redis DB.  It leaves entires for multiplexers unless
        everything.
        """
        # logger.debug(f"@@@ FLUSHALL: EVERYTHING = {everything}")
        delete_all(self.dbase.r, self.process_table_lock_prefix)
        delete_all(self.dbase.r, self.minioAddrPrefix)
        if everything:
            delete_all(self.dbase.r, self.muxPrefix)

    def printall(self):
        _prntall(self.dbase.r, "process")


def zone_to_route(zone):
    ##logger.debug(f"zone = {zone}")
    access_keys = [i["accessKeyID"] for i in zone.get("accessKeys", [])]
    directHostnames = zone["directHostnames"]
    return {
        "accessKeys": access_keys,
        "directHostnames": directHostnames,
    }


class RoutingTable(TableCommon):
    access_key_id_prefix = "aa:"
    directHostnamePrefix = "da:"
    atimePrefix = "at:"
    _endpoint_prefix = "ep:"
    _timestamp_prefix = "ts:"
    _bucket_prefix = "bk:"
    hashes_ = {}
    structured = {}

    def set_route(self, pool_id, ep, timeout):
        key = f"{self._endpoint_prefix}{pool_id}"
        self.dbase.set(key, ep)
        ##self.dbase.r.expire(key, timeout)
        return None

    def get_route(self, pool_id):
        key = f"{self._endpoint_prefix}{pool_id}"
        return self.dbase.get(key)

    def delete_route(self, pool_id):
        key = f"{self._endpoint_prefix}{pool_id}"
        self.dbase.delete(key)
        return None

    def set_route_expiry(self, pool_id, timeout):
        key = f"{self._timestamp_prefix}{pool_id}"
        ts = int(time.time())
        self.dbase.set(key, f"{ts}")
        self.dbase.r.expire(key, timeout)
        return None

    def get_route_expiry(self, pool_id):
        key = f"{self._timestamp_prefix}{pool_id}"
        return self.dbase.get(key)

    def delete_route_expiry(self, pool_id):
        key = f"{self._timestamp_prefix}{pool_id}"
        return self.dbase.delete(key)


    def ins_route_(self, minioAddr, route, timeout):
        # logger.debug(f"+++ {minioAddr} {route} {timeout}")
        for a in route.get("accessKeys"):
            key = f"{self.access_key_id_prefix}{a}"
            self.dbase.set(key, minioAddr)
        for h in route.get("directHostnames"):
            key = f"{self.directHostnamePrefix}{h}"
            self.dbase.set(key, minioAddr)
        if route:
            self.set_route_expire_(route, timeout)
        return None

    def del_route_(self, route):
        # logger.debug(f"+++")
        for a in route.get("accessKeys"):
            key = f"{self.access_key_id_prefix}{a}"
            self.dbase.delete(key)
        for h in route.get("directHostnames"):
            key = f"{self.directHostnamePrefix}{h}"
            self.dbase.delete(key)
        return None

    def set_route_expire_(self, route, timeout):
        # logger.debug(f"+++ {route} {timeout}")
        for a in route.get("accessKeys"):
            key = f"{self.access_key_id_prefix}{a}"
            self.dbase.r.expire(key, timeout)
        for h in route.get("directHostnames"):
            key = f"{self.directHostnamePrefix}{h}"
            self.dbase.r.expire(key, timeout)
        return None

    def get_route_by_access_key_(self, access_key_id):
        # logger.debug(f"+++ {access_key_id}")
        key = f"{self.access_key_id_prefix}{access_key_id}"
        return self.dbase.get(key)

    def get_route_by_direct_hostname_(self, directHostname):
        # logger.debug(f"+++ {directHostname}")
        key = f"{self.directHostnamePrefix}{directHostname}"
        return self.dbase.get(key)


    def set_atime_expire_(self, addr, timeout):
        # logger.debug(f"+++ {addr} {timeout}")
        key = f"{self.atimePrefix}{addr}"
        return self.dbase.r.expire(key, timeout)

    def set_atime_by_addr_(self, addr, atime, default_ttl):
        ## addr is an endpoint of a minio.
        ## NOTE: keepttl is not used, because it is available in
        ## Redis-6.0 and later.
        key = f"{self.atimePrefix}{addr}"
        ttl = self.dbase.r.ttl(key)
        retval = self.dbase.set(key, atime)
        if ttl > 0:
            self.dbase.r.expire(key, ttl)
        else:
            self.dbase.r.expire(key, default_ttl)
        return retval

    def get_atime_by_addr_(self, addr):
        # logger.debug(f"+++ {addr}")
        key = f"{self.atimePrefix}{addr}"
        return self.dbase.get(key)

    def del_atime_by_addr_(self, addr):
        # logger.debug(f"+++ {addr}")
        key = f"{self.atimePrefix}{addr}"
        return self.dbase.delete(key)


    def get_route_list(self):
        return _scan_strip(self.dbase.r, self._endpoint_prefix, None, get_value="get")
        ##access_key_route = _scan_strip(self.dbase.r, self.access_key_id_prefix, None, get_value="get")
        ##direct_host_route = _scan_strip(self.dbase.r, self.directHostnamePrefix, None, get_value="get")
        ##atime = _scan_strip(self.dbase.r, self.atimePrefix, None, get_value="get")
        ##return (access_key_route, direct_host_route, atime)

    def clear_routing(self, everything):
        delete_all(self.dbase.r, self._endpoint_prefix)
        delete_all(self.dbase.r, self._timestamp_prefix)
        delete_all(self.dbase.r, self._bucket_prefix)
        delete_all(self.dbase.r, self.atimePrefix)

    def clear_all_(self, everything):
        delete_all(self.dbase.r, self.access_key_id_prefix)
        delete_all(self.dbase.r, self.directHostnamePrefix)
        delete_all(self.dbase.r, self.atimePrefix)

    def printall(self):
        _prntall(self.dbase.r, "routing")


class Tables():
    def __init__(self, storage_table, process_table, routing_table):
        self.storage_table = storage_table
        self.process_table = process_table
        self.routing_table = routing_table


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


def _prntall(r, name):
    print(f"---- {name}")
    for key in r.scan_iter("*"):
        print(f"{key}")


def delete_all(r, match):
    for key in r.scan_iter(f"{match}*"):
        r.delete(key)


def _scan_strip(r, prefix, target, *, get_value=None):
    """Returns an iterator to scan a table for a prefix+target pattern,
    where target is * if it is None.  It drops a prefix from the
    returned key.
    """
    cursor = "0"
    mkey = target if target else "*"
    match = f"{prefix}{mkey}"
    striplen = len(prefix)
    while cursor != 0:
        (cursor, data) = r.scan(cursor=cursor, match=match)
        for item in data:
            key = item[striplen:]
            if get_value == "get":
                val = r.get(item)
                yield (key, val)
            elif get_value is not None:
                val = get_value(key)
                yield (key, val)
            else:
                yield key
