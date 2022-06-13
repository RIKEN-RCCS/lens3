"""Accessors for the set of Redis DBs."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
import json
from lenticularis.poolutil import Pool_State
from lenticularis.dbase import DBase
from lenticularis.utility import generate_access_key
from lenticularis.utility import logger

# Redis DB number.

_STORAGE_TABLE = 1
_PROCESS_TABLE = 2
_ROUTING_TABLE = 3
_PICKONE_TABLE = 4


_limit_of_id_generation_loop = 30


def get_table(mux_conf):
    redis_conf = mux_conf["redis"]
    redis_host = redis_conf["host"]
    redis_port = redis_conf["port"]
    redis_password = redis_conf["password"]
    storage_table = Storage_Table(redis_host, redis_port, _STORAGE_TABLE,
                                  redis_password)
    process_table = Process_Table(redis_host, redis_port, _PROCESS_TABLE,
                                  redis_password)
    routing_table = Routing_Table(redis_host, redis_port, _ROUTING_TABLE,
                                  redis_password)
    pickone_table = Pickone_Table(redis_host, redis_port, _PICKONE_TABLE,
                                  redis_password)
    return Table(storage_table, process_table, routing_table, pickone_table)


def _print_all(r, name):
    print(f"---- {name}")
    for key in r.scan_iter("*"):
        print(f"{key}")
        pass
    pass


def _delete_all(r, match):
    for key in r.scan_iter(f"{match}*"):
        r.delete(key)
        pass
    pass


def _scan_table(r, prefix, target):
    """Returns an iterator to scan keys in the table for a prefix+target
    pattern, where target is * if it is None.  It drops the prefix
    from the returned key.  Note it is always necessary a null-ness
    check when getting a value, because a deletion can intervene
    scanning a key and getting a value.
    """
    target = target if target else "*"
    pattern = f"{prefix}{target}"
    striplen = len(prefix)
    cursor = "0"
    while cursor != 0:
        (cursor, data) = r.scan(cursor=cursor, match=pattern)
        for rawkey in data:
            key = rawkey[striplen:]
            yield key
            pass
        pass
    pass


class Table():
    def __init__(self, storage_table, process_table, routing_table, pickone_table):
        self._storage_table = storage_table
        self._process_table = process_table
        self._routing_table = routing_table
        self._pickone_table = pickone_table
        pass

    # Storage-table:

    def set_pool(self, pool_id, pooldesc):
        self._storage_table.set_pool(pool_id, pooldesc)
        pass

    def get_pool(self, pool_id):
        return self._storage_table.get_pool(pool_id)

    def delete_pool(self, pool_id):
        self._storage_table.delete_pool(pool_id)
        pass

    def list_pools(self, pool_id):
        """Returns a ID list of pools if argument is None.  Or, it just checks
        existence of a pool.
        """
        return self._storage_table.list_pools(pool_id)

    def set_ex_buckets_directory(self, path, pool_id):
        return self._storage_table.set_ex_buckets_directory(path, pool_id)

    def get_buckets_directory_of_pool(self, pool_id):
        return self._storage_table.get_buckets_directory_of_pool(pool_id)

    def delete_buckets_directory(self, path):
        self._storage_table.delete_buckets_directory(path)
        pass

    def list_buckets_directories(self):
        return self._storage_table.list_buckets_directories()

    def set_user(self, uid, info):
        self._storage_table.set_user(uid, info)
        pass

    def get_user(self, uid):
        return self._storage_table.get_user(uid)

    def delete_user(self, uid):
        self._storage_table.delete_user(uid)
        pass

    def list_users(self):
        return self._storage_table.list_users()

    def set_pool_state(self, pool_id, state, reason):
        self._storage_table.set_pool_state(pool_id, state, reason)
        pass

    def get_pool_state(self, pool_id):
        return self._storage_table.get_pool_state(pool_id)

    def delete_pool_state(self, pool_id):
        self._storage_table.delete_pool_state(pool_id)
        pass

    # Process-table:

    def set_ex_minio_manager(self, pool_id, desc):
        return self._process_table.set_ex_minio_manager(pool_id, desc)

    def set_minio_manager_expiry(self, pool_id, timeout):
        return self._process_table.set_minio_manager_expiry(pool_id, timeout)

    def get_minio_manager(self, pool_id):
        return self._process_table.get_minio_manager(pool_id)

    def delete_minio_manager(self, pool_id):
        self._process_table.delete_minio_manager(pool_id)
        pass

    def set_minio_proc(self, pool_id, procdesc):
        self._process_table.set_minio_proc(pool_id, procdesc)
        pass

    def get_minio_proc(self, pool_id):
        return self._process_table.get_minio_proc(pool_id)

    def delete_minio_proc(self, pool_id):
        self._process_table.delete_minio_proc(pool_id)
        pass

    def list_minio_procs(self, pool_id):
        return self._process_table.list_minio_procs(pool_id)

    def set_mux(self, mux_ep, mux_desc):
        self._process_table.set_mux(mux_ep, mux_desc)
        pass

    def get_mux(self, mux_ep):
        return self._process_table.get_mux(mux_ep)

    def delete_mux(self, mux_ep):
        self._process_table.delete_mux(mux_ep)
        pass

    def list_muxs(self):
        return self._process_table.list_muxs()

    def list_mux_eps(self):
        return self._process_table.list_mux_eps()

    # Routing-table:

    def set_ex_bucket(self, bucket, desc):
        return self._routing_table.set_ex_bucket(bucket, desc)

    def get_bucket(self, bucket):
        return self._routing_table.get_bucket(bucket)

    def delete_bucket(self, bucket):
        self._routing_table.delete_bucket(bucket)
        pass

    def list_buckets(self, pool_id):
        return self._routing_table.list_buckets(pool_id)

    def set_minio_ep(self, pool_id, ep):
        self._routing_table.set_minio_ep(pool_id, ep)
        pass

    def get_minio_ep(self, pool_id):
        return self._routing_table.get_minio_ep(pool_id)

    def delete_minio_ep(self, pool_id):
        self._routing_table.delete_minio_ep(pool_id)
        pass

    def list_minio_ep(self):
        return self._routing_table.list_minio_ep()

    def set_access_timestamp(self, pool_id):
        self._routing_table.set_access_timestamp(pool_id)
        pass

    def get_access_timestamp(self, pool_id):
        return self._routing_table.get_access_timestamp(pool_id)

    def delete_access_timestamp(self, pool_id):
        self._routing_table.delete_access_timestamp(pool_id)
        pass

    def list_access_timestamps(self):
        return self._routing_table.list_access_timestamps()

    # Pickone-table:

    def make_unique_id(self, usage, owner, info={}):
        return self._pickone_table.make_unique_id(usage, owner, info)

    def set_ex_id(self, uid, desc):
        return self._pickone_table.set_ex_id(uid, desc)

    def get_id(self, uid):
        return self._pickone_table.get_id(uid)

    def delete_id_unconditionally(self, uid):
        self._pickone_table.delete_id_unconditionally(uid)
        pass

    def list_access_keys_of_pool(self, pool_id):
        return self._pickone_table.list_access_keys_of_pool(pool_id)

    # Clear tables.

    def clear_all(self, everything=False):
        self._storage_table.clear_all(everything=everything)
        self._process_table.clear_all(everything=everything)
        self._routing_table.clear_all(everything=everything)
        self._pickone_table.clear_all(everything=everything)
        pass

    def print_all(self):
        self._storage_table.print_all()
        self._process_table.print_all()
        self._routing_table.print_all()
        self._pickone_table.print_all()
        pass

    pass


class Table_Common():
    def __init__(self, host, port, db, password):
        self.dbase = DBase(host, port, db, password)
        pass

    pass


class Storage_Table(Table_Common):
    _pool_desc_prefix = "po:"
    _buckets_directory_prefix = "bd:"
    _pool_state_prefix = "ps:"
    _user_info_prefix = "uu:"
    storage_table_lock_prefix = "zk:"
    hashes_ = {_pool_desc_prefix}

    # Pool data is partial entries of the json schema.

    pool_desc_stored_keys = {
        "pool_name", "owner_uid", "owner_gid",
        "buckets_directory", "probe_key",
        "expiration_date", "online_status", "modification_time"}
    _pool_desc_keys = pool_desc_stored_keys

    _user_info_keys = {
        "uid", "groups", "permitted", "modification_time"}

    def set_pool(self, pool_id, pooldesc):
        assert set(pooldesc.keys()) == self._pool_desc_keys
        key = f"{self._pool_desc_prefix}{pool_id}"
        v = json.dumps(pooldesc)
        self.dbase.set(key, v)
        pass

    def get_pool(self, pool_id):
        key = f"{self._pool_desc_prefix}{pool_id}"
        v = self.dbase.get(key)
        pooldesc = (json.loads(v, parse_int=None)
                    if v is not None else None)
        return pooldesc

    def delete_pool(self, pool_id):
        self.dbase.delete(f"{self._pool_desc_prefix}{pool_id}")
        pass

    def set_pool_state(self, pool_id, state : Pool_State, reason):
        key = f"{self._pool_state_prefix}{pool_id}"
        assert reason is not None
        s = str(state)
        v = json.dumps((s, reason))
        self.dbase.set(key, v)
        pass

    def get_pool_state(self, pool_id):
        key = f"{self._pool_state_prefix}{pool_id}"
        v = self.dbase.get(key)
        (s, reason) = (json.loads(v, parse_int=None)
                       if v is not None else (None, None))
        state = Pool_State(s) if s is not None else None
        return (state, reason)

    def delete_pool_state(self, pool_id):
        key = f"{self._pool_state_prefix}{pool_id}"
        self.dbase.delete(key)
        pass

    def set_user(self, uid, userinfo):
        assert set(userinfo.keys()) == self._user_info_keys
        key = f"{self._user_info_prefix}{uid}"
        v = json.dumps(userinfo)
        self.dbase.set(key, v)
        pass

    def get_user(self, uid):
        key = f"{self._user_info_prefix}{uid}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_user(self, uid):
        key = f"{self._user_info_prefix}{uid}"
        self.dbase.delete(key)
        pass

    def list_users(self):
        keyi = _scan_table(self.dbase.r, self._user_info_prefix, None)
        return list(keyi)

    def list_pools(self, pool_id):
        keyi = _scan_table(self.dbase.r, self._pool_desc_prefix, pool_id)
        return list(keyi)

    def set_ex_buckets_directory(self, path, pool_id):
        assert isinstance(pool_id, str)
        key = f"{self._buckets_directory_prefix}{path}"
        ok = self.dbase.r.setnx(key, pool_id)
        if ok:
            return (ok, None)
        o = self.get_buckets_directory(path)
        if o is None:
            # (Possible race, ignored, returns failure).
            return (ok, None)
        else:
            return (ok, o)
        pass

    def get_buckets_directory(self, path):
        key = f"{self._buckets_directory_prefix}{path}"
        v = self.dbase.get(key)
        return v

    def get_buckets_directory_of_pool(self, pool_id):
        keyi = _scan_table(self.dbase.r, self._buckets_directory_prefix, None)
        path = next((i for (i, v)
                     in ((i, self.get_buckets_directory(i)) for i in keyi)
                     if v == pool_id), None)
        return path

    def delete_buckets_directory(self, path):
        key = f"{self._buckets_directory_prefix}{path}"
        self.dbase.delete(key)
        pass

    def list_buckets_directories(self):
        keyi = _scan_table(self.dbase.r, self._buckets_directory_prefix, None)
        bkts = [{"directory": i, "pool": v}
                for (i, v) in ((i, self.get_buckets_directory(i))
                               for i in keyi)
                if v is not None]
        return bkts

    def clear_all(self, everything):
        _delete_all(self.dbase.r, self._pool_desc_prefix)
        _delete_all(self.dbase.r, self._buckets_directory_prefix)
        _delete_all(self.dbase.r, self._pool_state_prefix)
        if everything:
            _delete_all(self.dbase.r, self._user_info_prefix)
            pass
        _delete_all(self.dbase.r, self.storage_table_lock_prefix)
        pass

    def print_all(self):
        _print_all(self.dbase.r, "storage")
        pass

    pass


class Process_Table(Table_Common):
    _minio_manager_prefix = "ma:"
    _minio_process_prefix = "mn:"
    _mux_desc_prefix = "mx:"
    process_table_lock_prefix = "lk:"
    hashes_ = {}

    _minio_manager_desc_keys = {
        "mux_host", "mux_port", "manager_pid",
        "modification_time"}

    _minio_process_desc_keys = {
        "minio_ep", "minio_pid", "admin", "password",
        "mux_host", "mux_port", "manager_pid", "modification_time"}

    _mux_desc_keys = {
        "host", "port", "start_time", "modification_time"}

    def set_ex_minio_manager(self, pool_id, desc):
        assert set(desc.keys()) == self._minio_manager_desc_keys
        key = f"{self._minio_manager_prefix}{pool_id}"
        v = json.dumps(desc)
        ok = self.dbase.r.setnx(key, v)
        if ok:
            return (True, None)
        # Race, returns failure.
        o = self.get_minio_manager(pool_id)
        return (False, o.get("pool") if o is not None else None)

    def set_minio_manager_expiry(self, pool_id, timeout):
        key = f"{self._minio_manager_prefix}{pool_id}"
        return self.dbase.r.expire(key, timeout)

    def get_minio_manager(self, pool_id):
        key = f"{self._minio_manager_prefix}{pool_id}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_minio_manager(self, pool_id):
        key = f"{self._minio_manager_prefix}{pool_id}"
        self.dbase.delete(key)
        pass

    def set_minio_proc(self, pool_id, procdesc):
        assert set(procdesc.keys()) == self._minio_process_desc_keys
        key = f"{self._minio_process_prefix}{pool_id}"
        v = json.dumps(procdesc)
        self.dbase.set(key, v)
        pass

    def get_minio_proc(self, pool_id):
        key = f"{self._minio_process_prefix}{pool_id}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_minio_proc(self, pool_id):
        key = f"{self._minio_process_prefix}{pool_id}"
        self.dbase.delete(key)
        pass

    def list_minio_procs(self, pool_id):
        keyi = _scan_table(self.dbase.r, self._minio_process_prefix, pool_id)
        vv = [(i, v) for (i, v) in ((i, self.get_minio_proc(i)) for i in keyi)
              if v is not None]
        return vv

    def set_mux(self, mux_ep, mux_desc):
        assert set(mux_desc.keys()) == self._mux_desc_keys
        key = f"{self._mux_desc_prefix}{mux_ep}"
        v = json.dumps(mux_desc)
        self.dbase.set(key, v)
        pass

    def get_mux(self, mux_ep):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_mux(self, mux_ep):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        self.dbase.delete(key)
        pass

    def list_muxs(self):
        keyi = _scan_table(self.dbase.r, self._mux_desc_prefix, None)
        vv = [(i, v) for (i, v) in ((i, self.get_mux(i)) for i in keyi)
              if v is not None]
        return vv

    def list_mux_eps(self):
        """Retruns a list of (host, port)."""
        keyi = _scan_table(self.dbase.r, self._mux_desc_prefix, None)
        eps = [(desc["host"], desc["port"])
               for (_, desc) in ((ep, self.get_mux(ep)) for ep in keyi)
               if desc is not None]
        return sorted(eps)

    def clear_all(self, everything):
        """Clears Redis DB.  It leaves entires for multiplexers unless
        everything.
        """
        _delete_all(self.dbase.r, self._minio_manager_prefix)
        _delete_all(self.dbase.r, self._minio_process_prefix)
        _delete_all(self.dbase.r, self._mux_desc_prefix)
        _delete_all(self.dbase.r, self.process_table_lock_prefix)
        pass

    def print_all(self):
        _print_all(self.dbase.r, "process")
        pass

    pass


class Routing_Table(Table_Common):
    _minio_ep_prefix = "ep:"
    _bucket_prefix = "bk:"
    _access_timestamp_prefix = "ts:"
    hashes_ = {}

    _bucket_desc_keys = {"pool", "bkt_policy", "modification_time"}

    def set_minio_ep(self, pool_id, ep):
        assert isinstance(ep, str)
        key = f"{self._minio_ep_prefix}{pool_id}"
        self.dbase.set(key, ep)
        pass

    def get_minio_ep(self, pool_id):
        key = f"{self._minio_ep_prefix}{pool_id}"
        return self.dbase.get(key)

    def delete_minio_ep(self, pool_id):
        key = f"{self._minio_ep_prefix}{pool_id}"
        self.dbase.delete(key)
        pass

    def list_minio_ep(self):
        keyi = _scan_table(self.dbase.r, self._minio_ep_prefix, None)
        vv = [(i, v) for (i, v) in ((i, self.get_minio_ep(i)) for i in keyi)
              if v is not None]
        return vv

    def set_ex_bucket(self, bucket, desc):
        assert set(desc.keys()) == self._bucket_desc_keys
        key = f"{self._bucket_prefix}{bucket}"
        v = json.dumps(desc)
        ok = self.dbase.r.setnx(key, v)
        if ok:
            return (True, None)
        # Race, returns failure.
        o = self.get_bucket(bucket)
        return (False, o.get("pool") if o is not None else None)

    def get_bucket(self, bucket):
        key = f"{self._bucket_prefix}{bucket}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_bucket(self, bucket):
        key = f"{self._bucket_prefix}{bucket}"
        self.dbase.delete(key)
        pass

    def list_buckets(self, pool_id):
        keyi = _scan_table(self.dbase.r, self._bucket_prefix, None)
        bkts = [{"name": name, **d}
                for (name, d)
                in [(name, self.get_bucket(name)) for name in keyi]
                if (d is not None
                    and (pool_id is None or d.get("pool") == pool_id))]
        return bkts
        pass

    def set_access_timestamp(self, pool_id):
        key = f"{self._access_timestamp_prefix}{pool_id}"
        ts = int(time.time())
        self.dbase.set(key, f"{ts}")
        pass

    def get_access_timestamp(self, pool_id):
        key = f"{self._access_timestamp_prefix}{pool_id}"
        v = self.dbase.get(key)
        return int(v) if v is not None else None

    def delete_access_timestamp(self, pool_id):
        key = f"{self._access_timestamp_prefix}{pool_id}"
        self.dbase.delete(key)
        pass

    def list_access_timestamps(self):
        keyi = _scan_table(self.dbase.r, self._access_timestamp_prefix, None)
        stamps = [{"pool": pid, "timestamp": ts}
                  for (pid, ts)
                  in [(pid, self.get_access_timestamp(pid)) for pid in keyi]
                  if ts is not None]
        return stamps

    def clear_all(self, everything):
        _delete_all(self.dbase.r, self._minio_ep_prefix)
        _delete_all(self.dbase.r, self._bucket_prefix)
        _delete_all(self.dbase.r, self._access_timestamp_prefix)
        pass

    def print_all(self):
        _print_all(self.dbase.r, "routing")
        pass

    pass


class Pickone_Table(Table_Common):
    _id_prefix = "id:"
    hashes_ = {}

    _id_desc_keys = {"use", "owner", "secret_key", "key_policy",
                     "modification_time"}

    def make_unique_id(self, usage, owner, info={}):
        assert usage in {"pool", "access_key"}
        assert usage != "access_key" or info != {}
        now = int(time.time())
        desc = {"use": usage, "owner": owner, **info, "modification_time": now}
        v = json.dumps(desc)
        id_generation_loops = 0
        while True:
            xid = generate_access_key()
            key = f"{self._id_prefix}{xid}"
            ok = self.dbase.r.setnx(key, v)
            if ok:
                return xid
            id_generation_loops += 1
            assert id_generation_loops < _limit_of_id_generation_loop
            pass
        assert False
        pass

    def set_ex_id(self, xid, desc):
        assert set(desc.keys()) == self._id_desc_keys
        key = f"{self._id_prefix}{xid}"
        v = json.dumps(desc)
        ok = self.dbase.r.setnx(key, v)
        return ok

    def get_id(self, xid):
        key = f"{self._id_prefix}{xid}"
        v = self.dbase.get(key)
        return json.loads(v, parse_int=None) if v is not None else None

    def delete_id_unconditionally(self, xid):
        key = f"{self._id_prefix}{xid}"
        self.dbase.delete(key)
        pass

    def list_access_keys_of_pool(self, pool_id):
        """Lists access-keys of a pool.  It includes an probe-key.  A
        probe-key is an access-key but has no corresponding secret-key.
        """
        keyi = _scan_table(self.dbase.r, self._id_prefix, None)
        keys = [{"access_key": i, **d}
                for (i, d) in [(i, self.get_id(i)) for i in keyi]
                if (d is not None
                    and d["use"] == "access_key"
                    and d["owner"] == pool_id)]
        return keys

    def clear_all(self, everything):
        _delete_all(self.dbase.r, self._id_prefix)
        pass

    def print_all(self):
        _print_all(self.dbase.r, "pickone")
        pass

    pass
