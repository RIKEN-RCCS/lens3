"""Accessors of the Redis DB.  A table is accessed like a single
database, while it is implemented by a couple of databases inside.
"""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
import os
import json
import jsonschema
import redis
from redis import Redis
from lenticularis.yamlconf import redis_json_schema
from lenticularis.pooldata import Pool_State
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import generate_access_key
from lenticularis.utility import logger

# Redis DB number.

_SETTING_DB = 0
_STORAGE_DB = 1
_PROCESS_DB = 2
_ROUTING_DB = 3
_MONOKEY_DB = 4

_limit_of_id_generation_loop = 30


def read_redis_conf(conf_file):
    """Reads conf.json file and returns a record for a Redis connection.
    """
    assert conf_file is not None
    try:
        with open(conf_file, "r") as f:
            conf = json.load(f, parse_int=None)
    except json.JSONDecodeError as e:
        raise Exception(f"Reading a conf file failed: {conf_file}:"
                        f" exception=({e})")
    except Exception as e:
        m = rephrase_exception_message(e)
        raise Exception(f"Reading a conf file failed: {conf_file}:"
                        f" exception=({m})")
    schema = {
        "type": "object",
        "properties": {
            "redis": redis_json_schema
        },
        "required": [
            "redis",
        ],
        "additionalProperties": True,
    }
    jsonschema.validate(instance=conf, schema=schema)
    return conf["redis"]


def get_table(redis):
    """Makes a Redis connection for a Redis endpoint."""
    # redis_conf = mux_conf["redis"]
    setting = _Setting_Table(_SETTING_DB, redis)
    storage = _Storage_Table(_STORAGE_DB, redis)
    process = _Process_Table(_PROCESS_DB, redis)
    routing = _Routing_Table(_ROUTING_DB, redis)
    monokey = _Monokey_Table(_MONOKEY_DB, redis)
    return Table(setting, storage, process, routing, monokey)


def set_conf(conf, redis):
    """Stores a conf in Redis."""
    setting = _Setting_Table(_SETTING_DB, redis)
    setting.set_conf(conf)
    del setting
    pass


def get_conf(sub, suffix, redis):
    """Takes a conf in Redis with regard to a subject, sub="api" or
    sub="mux".  It may quaify a key "mux" with a suffix as
    "mux:"+suffix.  It raises an exception if a conf does not exist.
    (The contents should have been schema checked at an insertion).
    """
    if sub == "api":
        key = "api"
    elif sub == "mux":
        if suffix is None:
            key = "mux"
        else:
            key = ("mux:" + suffix) if len(suffix) > 0 else "mux"
            pass
    else:
        assert sub in {"api", "mux"}
        key = "BADKEY"
        pass
    setting = _Setting_Table(_SETTING_DB, redis)
    conf = setting.get_conf(key)
    del setting
    if conf is None:
        raise Exception(f"No {key} conf record in Redis")
    return conf


def _print_all(r, name):
    print(f"---")
    print(f"# {name}")
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
    """Redis databases."""

    def __init__(self, setting, storage, process, routing, monokey):
        self._setting_table = setting
        self._storage_table = storage
        self._process_table = process
        self._routing_table = routing
        self._monokey_table = monokey
        pass

    # Setting-Table:

    def set_conf(self, conf):
        """Stores a conf.  It is the same as the module function."""
        return self._setting_table.set_conf(conf)

    def list_confs(self):
        """Returns a list of confs"""
        return self._setting_table._list_confs()

    def set_user(self, userinfo):
        self._setting_table.set_user(userinfo)
        pass

    def get_user(self, uid):
        return self._setting_table.get_user(uid)

    def map_claim_to_uid(self, claim):
        return self._setting_table.map_claim_to_uid(claim)

    def delete_user(self, uid):
        self._setting_table.delete_user(uid)
        pass

    def list_users(self):
        return self._setting_table.list_users()

    # Storage-Table:

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

    def set_pool_state(self, pool_id, state, reason):
        self._storage_table.set_pool_state(pool_id, state, reason)
        pass

    def get_pool_state(self, pool_id):
        return self._storage_table.get_pool_state(pool_id)

    def delete_pool_state(self, pool_id):
        self._storage_table.delete_pool_state(pool_id)
        pass

    # Process-Table:

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

    def set_mux_expiry(self, mux_ep, timeout):
        return self._process_table.set_mux_expiry(mux_ep, timeout)

    def get_mux(self, mux_ep):
        return self._process_table.get_mux(mux_ep)

    def delete_mux(self, mux_ep):
        self._process_table.delete_mux(mux_ep)
        pass

    def list_muxs(self):
        return self._process_table.list_muxs()

    def list_mux_eps(self):
        return self._process_table.list_mux_eps()

    # Routing-Table:

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

    # Monokey-Table:

    def make_unique_id(self, usage, owner, info):
        return self._monokey_table.make_unique_id(usage, owner, info)

    def set_ex_id(self, xid, usage, desc):
        """Inserts an id, used at database restoring."""
        return self._monokey_table.set_ex_id(xid, usage, desc)

    def get_id(self, uid):
        return self._monokey_table.get_id(uid)

    def delete_id_unconditionally(self, uid):
        self._monokey_table.delete_id_unconditionally(uid)
        pass

    def list_access_keys_of_pool(self, pool_id):
        return self._monokey_table.list_access_keys_of_pool(pool_id)

    # Clear tables.

    def clear_all(self, everything=False):
        self._setting_table.clear_all(everything=everything)
        self._storage_table.clear_all(everything=everything)
        self._process_table.clear_all(everything=everything)
        self._routing_table.clear_all(everything=everything)
        self._monokey_table.clear_all(everything=everything)
        pass

    def print_all(self):
        self._setting_table.print_all()
        self._storage_table.print_all()
        self._process_table.print_all()
        self._routing_table.print_all()
        self._monokey_table.print_all()
        pass

    pass


def _wait_for_redis(db):
    while True:
        try:
            db.ping()
            logger.debug("Connected to Redis.")
            return
        except redis.ConnectionError:
            logger.debug("Connection to Redis failed (sleeping).")
            time.sleep(30)
            pass
        pass
    pass


class Table_Common():
    def __init__(self, db, redis):
        host = redis["host"]
        port = redis["port"]
        password = redis["password"]
        self.db = Redis(host=host, port=port, db=db, password=password,
                        charset="utf-8", decode_responses=True)
        _wait_for_redis(self.db)
        pass

    pass


class _Setting_Table(Table_Common):
    _conf_prefix = "cf:"
    _user_info_prefix = "uu:"
    _user_claim_prefix = "um:"

    _user_info_keys = {
        "uid", "claim", "groups", "enabled", "modification_time"}

    def _delete_claim(self, uid):
        """Deletes a claim associated to a uid.  It scans the database to find
        an entry owned by a uid.
        """
        claims = _scan_table(self.db, self._user_claim_prefix, None)
        for claim in claims:
            u = self.map_claim_to_uid(claim)
            if (u is not None and u == uid):
                key = f"{self._user_claim_prefix}{claim}"
                self.db.delete(key)
                pass
            pass
        return

    def set_conf(self, conf):
        assert "subject" in conf
        sub = conf["subject"]
        assert (sub == "api" or sub == "mux"
                or (len(sub) >= 5 and sub[:4] == "mux:"))
        key = f"{self._conf_prefix}{sub}"
        v = json.dumps(conf)
        self.db.set(key, v)
        pass

    def get_conf(self, sub):
        assert (sub == "api" or sub == "mux"
                or (len(sub) >= 5 and sub[:4] == "mux:"))
        key = f"{self._conf_prefix}{sub}"
        v = self.db.get(key)
        return json.loads(v) if v is not None else None

    def _list_confs(self):
        keyi = _scan_table(self.db, self._conf_prefix, None)
        keys = list(keyi)
        conflist = [v for v in [self.get_conf(k) for k in keys]
                if v is not None]
        return conflist

    def set_user(self, userinfo):
        assert set(userinfo.keys()) == self._user_info_keys
        uid = userinfo["uid"]
        assert uid is not None and uid != ""
        key1 = f"{self._user_info_prefix}{uid}"
        v = json.dumps(userinfo)
        self.db.set(key1, v)
        claim = userinfo["claim"]
        if claim != "":
            key2 = f"{self._user_claim_prefix}{claim}"
            self.db.set(key2, uid)
            pass
        pass

    def get_user(self, uid):
        key1 = f"{self._user_info_prefix}{uid}"
        v = self.db.get(key1)
        return json.loads(v) if v is not None else None

    def map_claim_to_uid(self, claim):
        assert claim != ""
        key2 = f"{self._user_claim_prefix}{claim}"
        v = self.db.get(key2)
        return v

    def delete_user(self, uid):
        key1 = f"{self._user_info_prefix}{uid}"
        v = self.get_user(uid)
        self.db.delete(key1)
        claim = v["claim"] if v is not None else ""
        if claim != "":
            key2 = f"{self._user_claim_prefix}{claim}"
            self.db.delete(key2)
            pass
        self._delete_claim(uid)
        pass

    def list_users(self):
        keyi = _scan_table(self.db, self._user_info_prefix, None)
        return list(keyi)

    def clear_all(self, everything):
        if everything:
            _delete_all(self.db, self._user_info_prefix)
            _delete_all(self.db, self._user_claim_prefix)
            _delete_all(self.db, self._conf_prefix)
            pass
        pass

    def print_all(self):
        _print_all(self.db, "Setting")
        pass

    pass


class _Storage_Table(Table_Common):
    _pool_desc_prefix = "po:"
    _pool_state_prefix = "ps:"
    _buckets_directory_prefix = "bd:"

    # A pool description is semi-static partial state, which will be
    # amended by such as an enabled state.

    _pool_desc_keys = {
        "pool_name", "owner_uid", "owner_gid", "buckets_directory",
        "probe_key", "online_status", "expiration_time", "modification_time"}

    def set_pool(self, pool_id, pooldesc):
        assert set(pooldesc.keys()) == self._pool_desc_keys
        key = f"{self._pool_desc_prefix}{pool_id}"
        v = json.dumps(pooldesc)
        self.db.set(key, v)
        pass

    def get_pool(self, pool_id):
        key = f"{self._pool_desc_prefix}{pool_id}"
        v = self.db.get(key)
        pooldesc = (json.loads(v)
                    if v is not None else None)
        return pooldesc

    def delete_pool(self, pool_id):
        self.db.delete(f"{self._pool_desc_prefix}{pool_id}")
        pass

    def set_pool_state(self, pool_id, state : Pool_State, reason):
        key = f"{self._pool_state_prefix}{pool_id}"
        assert reason is not None
        s = str(state)
        v = json.dumps((s, reason))
        self.db.set(key, v)
        pass

    def get_pool_state(self, pool_id):
        key = f"{self._pool_state_prefix}{pool_id}"
        v = self.db.get(key)
        (s, reason) = (json.loads(v)
                       if v is not None else (None, None))
        state = Pool_State(s) if s is not None else None
        return (state, reason)

    def delete_pool_state(self, pool_id):
        key = f"{self._pool_state_prefix}{pool_id}"
        self.db.delete(key)
        pass

    def list_pools(self, pool_id):
        keyi = _scan_table(self.db, self._pool_desc_prefix, pool_id)
        return list(keyi)

    def set_ex_buckets_directory(self, path, pool_id):
        """Registers atomically a directory.  At a failure, a returned current
        owner information can be None due to a race (but practically
        never).
        """
        assert isinstance(pool_id, str)
        key = f"{self._buckets_directory_prefix}{path}"
        ok = self.db.setnx(key, pool_id)
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
        v = self.db.get(key)
        return v

    def get_buckets_directory_of_pool(self, pool_id):
        keyi = _scan_table(self.db, self._buckets_directory_prefix, None)
        path = next((i for (i, v)
                     in ((i, self.get_buckets_directory(i)) for i in keyi)
                     if v == pool_id), None)
        return path

    def delete_buckets_directory(self, path):
        key = f"{self._buckets_directory_prefix}{path}"
        self.db.delete(key)
        pass

    def list_buckets_directories(self):
        keyi = _scan_table(self.db, self._buckets_directory_prefix, None)
        bkts = [{"directory": i, "pool": v}
                for (i, v) in ((i, self.get_buckets_directory(i))
                               for i in keyi)
                if v is not None]
        return bkts

    def clear_all(self, everything):
        _delete_all(self.db, self._pool_desc_prefix)
        _delete_all(self.db, self._buckets_directory_prefix)
        _delete_all(self.db, self._pool_state_prefix)
        pass

    def print_all(self):
        _print_all(self.db, "Storage")
        pass

    pass


class _Process_Table(Table_Common):
    _minio_manager_prefix = "ma:"
    _minio_process_prefix = "mn:"
    _mux_desc_prefix = "mx:"

    _minio_manager_desc_keys = {
        "mux_host", "mux_port", "start_time"}

    _minio_process_desc_keys = {
        "minio_ep", "minio_pid", "admin", "password",
        "mux_host", "mux_port", "manager_pid", "modification_time"}

    _mux_desc_keys = {
        "host", "port", "start_time", "modification_time"}

    def set_ex_minio_manager(self, pool_id, desc):
        """Registers atomically a manager process.  It returns OK/NG, paired
        with a manager that took the role earlier when it fails.  At
        a failure, a returned current owner information can be None due
        to a race (but practically never).
        """
        assert set(desc.keys()) == self._minio_manager_desc_keys
        key = f"{self._minio_manager_prefix}{pool_id}"
        v = json.dumps(desc)
        ok = self.db.setnx(key, v)
        if ok:
            return (True, None)
        # Race, returns failure.
        o = self.get_minio_manager(pool_id)
        return (False, o if o is not None else None)

    def set_minio_manager_expiry(self, pool_id, timeout):
        key = f"{self._minio_manager_prefix}{pool_id}"
        return self.db.expire(key, timeout)

    def get_minio_manager(self, pool_id):
        key = f"{self._minio_manager_prefix}{pool_id}"
        v = self.db.get(key)
        return json.loads(v) if v is not None else None

    def delete_minio_manager(self, pool_id):
        key = f"{self._minio_manager_prefix}{pool_id}"
        self.db.delete(key)
        pass

    def set_minio_proc(self, pool_id, procdesc):
        assert set(procdesc.keys()) == self._minio_process_desc_keys
        key = f"{self._minio_process_prefix}{pool_id}"
        v = json.dumps(procdesc)
        self.db.set(key, v)
        pass

    def get_minio_proc(self, pool_id):
        key = f"{self._minio_process_prefix}{pool_id}"
        v = self.db.get(key)
        return json.loads(v) if v is not None else None

    def delete_minio_proc(self, pool_id):
        key = f"{self._minio_process_prefix}{pool_id}"
        self.db.delete(key)
        pass

    def list_minio_procs(self, pool_id):
        keyi = _scan_table(self.db, self._minio_process_prefix, pool_id)
        vv = [(i, v) for (i, v) in ((i, self.get_minio_proc(i)) for i in keyi)
              if v is not None]
        return vv

    def set_mux(self, mux_ep, mux_desc):
        assert set(mux_desc.keys()) == self._mux_desc_keys
        key = f"{self._mux_desc_prefix}{mux_ep}"
        v = json.dumps(mux_desc)
        self.db.set(key, v)
        pass

    def set_mux_expiry(self, mux_ep, timeout):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        return self.db.expire(key, timeout)

    def get_mux(self, mux_ep):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        v = self.db.get(key)
        return json.loads(v) if v is not None else None

    def delete_mux(self, mux_ep):
        key = f"{self._mux_desc_prefix}{mux_ep}"
        self.db.delete(key)
        pass

    def list_muxs(self):
        keyi = _scan_table(self.db, self._mux_desc_prefix, None)
        vv = [(i, v) for (i, v) in ((i, self.get_mux(i)) for i in keyi)
              if v is not None]
        return vv

    def list_mux_eps(self):
        """Retruns a list of (host, port)."""
        keyi = _scan_table(self.db, self._mux_desc_prefix, None)
        eps = [(desc["host"], desc["port"])
               for (_, desc) in ((ep, self.get_mux(ep)) for ep in keyi)
               if desc is not None]
        return sorted(eps)

    def clear_all(self, everything):
        """Clears Redis DB.  It leaves entires for multiplexers unless
        everything.
        """
        _delete_all(self.db, self._minio_manager_prefix)
        _delete_all(self.db, self._minio_process_prefix)
        _delete_all(self.db, self._mux_desc_prefix)
        pass

    def print_all(self):
        _print_all(self.db, "Process")
        pass

    pass


class _Routing_Table(Table_Common):
    _minio_ep_prefix = "ep:"
    _bucket_prefix = "bk:"
    _access_timestamp_prefix = "ts:"

    _bucket_desc_keys = {"pool", "bkt_policy", "modification_time"}

    def set_minio_ep(self, pool_id, ep):
        assert isinstance(ep, str)
        key = f"{self._minio_ep_prefix}{pool_id}"
        self.db.set(key, ep)
        pass

    def get_minio_ep(self, pool_id):
        key = f"{self._minio_ep_prefix}{pool_id}"
        return self.db.get(key)

    def delete_minio_ep(self, pool_id):
        key = f"{self._minio_ep_prefix}{pool_id}"
        self.db.delete(key)
        pass

    def list_minio_ep(self):
        keyi = _scan_table(self.db, self._minio_ep_prefix, None)
        vv = [(i, v) for (i, v) in ((i, self.get_minio_ep(i)) for i in keyi)
              if v is not None]
        return vv

    def set_ex_bucket(self, bucket, desc):
        """Registers atomically a bucket.  It returns OK/NG, paired with a
        pool-id that took the bucket name earlier when it fails.  At
        a failure, a returned current owner information can be None due
        to a race (but practically never).
        """
        assert set(desc.keys()) == self._bucket_desc_keys
        key = f"{self._bucket_prefix}{bucket}"
        v = json.dumps(desc)
        ok = self.db.setnx(key, v)
        if ok:
            return (True, None)
        # Race, returns failure.
        o = self.get_bucket(bucket)
        return (False, o.get("pool") if o is not None else None)

    def get_bucket(self, bucket):
        key = f"{self._bucket_prefix}{bucket}"
        v = self.db.get(key)
        return json.loads(v) if v is not None else None

    def delete_bucket(self, bucket):
        key = f"{self._bucket_prefix}{bucket}"
        self.db.delete(key)
        pass

    def list_buckets(self, pool_id):
        keyi = _scan_table(self.db, self._bucket_prefix, None)
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
        self.db.set(key, f"{ts}")
        pass

    def get_access_timestamp(self, pool_id):
        key = f"{self._access_timestamp_prefix}{pool_id}"
        v = self.db.get(key)
        return int(v) if v is not None else None

    def delete_access_timestamp(self, pool_id):
        key = f"{self._access_timestamp_prefix}{pool_id}"
        self.db.delete(key)
        pass

    def list_access_timestamps(self):
        keyi = _scan_table(self.db, self._access_timestamp_prefix, None)
        stamps = [{"pool": pid, "timestamp": ts}
                  for (pid, ts)
                  in [(pid, self.get_access_timestamp(pid)) for pid in keyi]
                  if ts is not None]
        return stamps

    def clear_all(self, everything):
        _delete_all(self.db, self._minio_ep_prefix)
        _delete_all(self.db, self._bucket_prefix)
        _delete_all(self.db, self._access_timestamp_prefix)
        pass

    def print_all(self):
        _print_all(self.db, "Routing")
        pass

    pass


class _Monokey_Table(Table_Common):
    _id_prefix = "id:"

    _id_desc_keys = {"pool": {"use", "owner", "modification_time"},
                     "key": {"use", "owner", "secret_key", "key_policy",
                             "expiration_time", "modification_time"}}

    def make_unique_id(self, usage, owner, info):
        """Makes a unique key for a pool-id or an access-key."""
        assert usage in {"pool", "key"}
        now = int(time.time())
        desc = {"use": usage, "owner": owner, **info, "modification_time": now}
        assert set(desc.keys()) == self._id_desc_keys[usage]
        v = json.dumps(desc)
        id_generation_loops = 0
        while True:
            xid = generate_access_key()
            key = f"{self._id_prefix}{xid}"
            ok = self.db.setnx(key, v)
            if ok:
                return xid
            id_generation_loops += 1
            assert id_generation_loops < _limit_of_id_generation_loop
            pass
        assert False
        pass

    def set_ex_id(self, xid, usage, desc):
        assert usage in {"pool", "key"}
        assert set(desc.keys()) == self._id_desc_keys[usage]
        key = f"{self._id_prefix}{xid}"
        v = json.dumps(desc)
        ok = self.db.setnx(key, v)
        return ok

    def get_id(self, xid):
        key = f"{self._id_prefix}{xid}"
        v = self.db.get(key)
        desc = json.loads(v) if v is not None else None
        assert (set(desc.keys()) == self._id_desc_keys[desc["use"]]
                if desc is not None else True)
        return desc

    def delete_id_unconditionally(self, xid):
        key = f"{self._id_prefix}{xid}"
        self.db.delete(key)
        pass

    def list_access_keys_of_pool(self, pool_id):
        """Lists access-keys of a pool.  It includes an probe-key.  A
        probe-key is an access-key but has no corresponding secret-key.
        """
        keyi = _scan_table(self.db, self._id_prefix, None)
        keys = [{"access_key": i, **d}
                for (i, d) in [(i, self.get_id(i)) for i in keyi]
                if (d is not None
                    and d["use"] == "key"
                    and d["owner"] == pool_id)]
        return keys

    def clear_all(self, everything):
        _delete_all(self.db, self._id_prefix)
        pass

    def print_all(self):
        _print_all(self.db, "Monokey")
        pass

    pass
