"""Pool data small utility."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
import enum
import time
import jsonschema
from urllib.request import Request, urlopen
import urllib.error
from lenticularis.utility import host_port
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger
from lenticularis.utility import tracing


class Api_Error(Exception):

    def __init__(self, code, *args):
        self.code = code
        super().__init__(*args)
        pass

    pass


class Key_Policy(enum.Enum):
    """A policy to an access-key; names are taken from MinIO."""
    # (NOT USED YET).
    READWRITE = "readwrite"
    READONLY = "readonly"
    WRITEONLY = "writeonly"

    def __str__(self):
        return self.value

    pass


class Bkt_Policy(enum.Enum):
    """A public-access policy of a bucket; names are taken from MinIO."""
    # (NOT USED YET).
    NONE = "none"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    PUBLIC = "public"

    def __str__(self):
        return self.value

    pass


class Pool_State(enum.Enum):
    """A state of a pool."""

    INITIAL = "initial"
    READY = "ready"
    SUSPENDED = "suspended"
    DISABLED = "disabled"
    INOPERABLE = "inoperable"

    def __str__(self):
        return self.value

    pass


class Pool_Reason():
    """Constant strings of reasons of state transitions.  It is not an
    enum to include other messages from MinIO.  POOL_REMOVED is not
    stored in the state of a pool.  EXEC_FAILED and SETUP_FAILED will
    be appended with a further reason.
    """

    # Pool_State.INITIAL or Pool_State.READY:
    NORMAL = "-"

    # Pool_State.SUSPENDED:
    BACKEND_BUSY = "backend busy"

    # Pool_State.DISABLED:
    POOL_EXPIRED = "pool expired"
    USER_DISABLED = "user disabled"
    POOL_OFFLINE = "pool offline"

    # Pool_State.INOPERABLE:
    POOL_REMOVED = "pool removed"
    USER_REMOVED = "user removed"
    EXEC_FAILED = "start failed: "
    SETUP_FAILED = "initialization failed: "
    # Other reasons are exceptions and messages from MinIO.

    # POOL_DISABLED_INITIALLY = "pool disabled initially"

    pass


def _pool_desc_schema():
    """A pool record schema.  A pool record is used by Web-API
    and database dumps.  A record of a pool is reconstructed.  See
    gather_pool_desc().
    """
    bucket_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "pool": {"type": "string"},
            "bkt_policy": {
                "type": "string",
                "enum": ["none", "upload", "download", "public"],
            },
            "modification_time": {"type": "integer"},
        },
        "required": [
            "name",
            "pool",
            "bkt_policy",
            "modification_time",
        ],
        "additionalProperties": False,
    }

    access_key_schema = {
        "type": "object",
        "properties": {
            "access_key": {"type": "string"},
            "secret_key": {"type": "string"},
            "key_policy": {
                "type": "string",
                "enum": ["readwrite", "readonly", "writeonly"],
            },
            "owner": {"type": "string"},
            "expiration_time": {"type": "integer"},
            "modification_time": {"type": "integer"},
        },
        "required": [
            "access_key",
            "secret_key",
            "key_policy",
            "owner",
            "expiration_time",
            "modification_time",
        ],
        "additionalProperties": False,
    }

    schema = {
        "type": "object",
        "properties": {
            "pool_name": {"type": "string"},
            "buckets_directory": {"type": "string"},
            "owner_uid": {"type": "string"},
            "owner_gid": {"type": "string"},
            "buckets": {"type": "array", "items": bucket_schema},
            "access_keys": {"type": "array", "items": access_key_schema},
            "probe_key": {"type": "string"},
            "expiration_time": {"type": "integer"},
            "online_status": {"type": "boolean"},
            "user_enabled_status": {"type": "boolean"},
            "minio_state": {"type": "string"},
            "minio_reason": {"type": "string"},
            "modification_time": {"type": "integer"},
        },
        "required": [
            "pool_name",
            "owner_uid",
            "owner_gid",
            "buckets_directory",
            "buckets",
            "access_keys",
            "probe_key",
            "expiration_time",
            "online_status",
            "user_enabled_status",
            "minio_state",
            "minio_reason",
            "modification_time",
        ],
        "additionalProperties": False,
    }
    return schema


def set_pool_state(tables, pool_id, state, reason):
    (o, _, _) = tables.get_pool_state(pool_id)
    logger.debug(f"Manager (pool={pool_id}):"
                 f" pool-state change: {o} to {state}")
    tables.set_pool_state(pool_id, state, reason)
    pass


def update_pool_state(tables, pool_id):
    """Checks changes of the user and pool setting, and updates the state.
    This code should be placed at a location where it is called
    periodically.  It returns a pair of a status and a reason.
    """
    desc = tables.get_pool(pool_id)
    if desc is None:
        return (Pool_State.INOPERABLE, Pool_Reason.POOL_REMOVED)
    (state, reason, ts) = tables.get_pool_state(pool_id)
    if state is None:
        logger.error(f"Mux (pool={pool_id}): pool-state not found.")
        return (Pool_State.INOPERABLE, Pool_Reason.POOL_REMOVED)
    if state in {Pool_State.SUSPENDED, Pool_State.INOPERABLE}:
        return (state, reason)

    # Check a state transition.

    assert state in {Pool_State.INITIAL, Pool_State.READY, Pool_State.DISABLED}
    user_id = desc["owner_uid"]
    u = tables.get_user(user_id)
    if u is None:
        reason = Pool_Reason.USER_REMOVED
        set_pool_state(tables, pool_id, Pool_State.INOPERABLE, reason)
        return (False, reason)
    now = int(time.time())
    enabled = u["enabled"]
    unexpired = now < desc["expiration_time"]
    online = desc["online_status"]
    ok = (enabled and unexpired and online)
    if ok:
        if state in {Pool_State.DISABLED}:
            # It forces to setup MinIO by a transition to initial,
            # without regard to the minio_setup_at_start value.
            state = Pool_State.INITIAL
            reason = Pool_Reason.NORMAL
            set_pool_state(tables, pool_id, Pool_State.INITIAL, reason)
            pass
        return (state, reason)
    else:
        reason = Pool_Reason.NORMAL
        if not enabled:
            reason = Pool_Reason.USER_DISABLED
        elif not unexpired:
            reason = Pool_Reason.POOL_EXPIRED
        elif not online:
            reason = Pool_Reason.POOL_OFFLINE
        else:
            reason = Pool_Reason.NORMAL
            pass
        set_pool_state(tables, pool_id, Pool_State.DISABLED, reason)
        return (state, reason)
    pass


def ensure_bucket_policy(bucket, desc, access_key):
    """Performs a very weak check that a bucket accepts any public access
       or an access has an access-key.
    """
    pool_id = desc["pool"]
    policy = desc["bkt_policy"]
    if policy in {"public", "download", "upload"}:
        # ANY PUBLIC ACCESS ARE PASSED.
        return
    elif access_key is not None:
        # JUST CHECK AN ACEESS IS WITH A KEY.
        return
    raise Api_Error(401, f"Access-key missing")


def ensure_user_is_authorized(tables, user_id):
    u = tables.get_user(user_id)
    assert u is not None
    if not u.get("enabled"):
        raise Api_Error(403, (f"User disabled: {user_id}"))
    pass


def ensure_mux_is_running(tables):
    muxs = tables.list_mux_eps()
    if len(muxs) == 0:
        raise Api_Error(500, (f"No Mux services in Lens3"))
    pass


def ensure_pool_state(tables, pool_id, reject_initial_state):
    (state, reason) = update_pool_state(tables, pool_id)
    if state == Pool_State.INITIAL:
        if reject_initial_state:
            logger.error(f"Manager (pool={pool_id}) is in initial state.")
            raise Api_Error(403, f"Pool is in initial state")
        pass
    elif state == Pool_State.READY:
        pass
    elif state == Pool_State.SUSPENDED:
        raise Api_Error(503, f"Pool suspended")
    elif state == Pool_State.DISABLED:
        raise Api_Error(403, f"Pool disabled")
    elif state == Pool_State.INOPERABLE:
        raise Api_Error(403, f"Pool inoperable")
    else:
        assert False
        pass
    pass


def ensure_pool_owner(tables, pool_id, user_id):
    pooldesc = tables.get_pool(pool_id)
    if pooldesc is None:
        raise Api_Error(403, (f"Non-existing pool: {pool_id}"))
    if pooldesc.get("owner_uid") != user_id:
        raise Api_Error(403, (f"Not an owner of a pool: {pool_id}"))
    pass


def ensure_bucket_owner(tables, bucket, pool_id):
    desc = tables.get_bucket(bucket)
    if desc is None:
        raise Api_Error(403, f"Non-exisiting bucket: {bucket}")
    if desc.get("pool") != pool_id:
        raise Api_Error(403, (f"Bucket for a wrong pool: {bucket}"))
    pass


def ensure_secret_owner(tables, access_key, pool_id):
    """Checks an access-key belongs to a given pool, and also checks a key
    is not expired.  Note that it accepts access-key=None.
    """
    _ensure_secret_owner(tables, access_key, pool_id, True)
    pass


def ensure_secret_owner_only(tables, access_key, pool_id):
    """Checks an access-key belongs to a given pool regardless of its
    expiration.
    """
    _ensure_secret_owner(tables, access_key, pool_id, False)
    pass


def _ensure_secret_owner(tables, access_key, pool_id, check_expiration):
    if access_key is None:
        return
    keydesc = tables.get_xid("akey", access_key)
    if keydesc is None:
        raise Api_Error(403, f"Non-existing access-key: {access_key}")
    if not (keydesc.get("owner") == pool_id):
        raise Api_Error(403, f"Wrong access-key: {access_key}")
    if check_expiration:
        now = int(time.time())
        if keydesc.get("expiration_time") < now:
            raise Api_Error(403, f"Expired access-key: {access_key}")
        pass
    pass


# def _drop_non_ui_info_from_keys(access_key):
#     """Drops unnecessary info to pass access-key info to Web-API.  That is,
#     they are {"use", "owner", "modification_time"}.
#     """
#     needed = {"access_key", "secret_key", "key_policy"}
#     return {k: v for (k, v) in access_key.items() if k in needed}


def get_pool_owner_for_messages(tables, pool_id):
    """Finds an owner of a pool for printing error messages.  It returns
    unknown-user, when an owner is not found.
    """
    if pool_id is None:
        return "unknown-user"
    pooldesc = tables.get_pool(pool_id)
    if pooldesc is None:
        return "unknown-user"
    return pooldesc.get("owner_uid")


# def get_manager_name_for_messages__(manager):
#     if manager is None:
#         return "unknown-mux-ep"
#     muxep = host_port(manager["mux_host"], manager["mux_port"])
#     return muxep


def tally_manager_expiry(tolerance, interval, timeout):
    return ((tolerance + 1 + 2) * (interval + timeout))


# def _check_bkt_policy(bkt_policy):
#     assert bkt_policy in {"none", "upload", "download", "public"}
#     pass


# def _check_key_policy(key_policy):
#     assert key_policy in {"readwrite", "readonly", "writeonly"}
#     pass


def check_user_naming(user_id):
    return re.fullmatch("^[a-z_][-a-z0-9_.]{0,31}$", user_id) is not None


def check_pool_naming(pool_id):
    assert pool_id is not None
    return re.fullmatch("[a-zA-Z][a-zA-Z0-9]{19}", pool_id) is not None


def check_access_key_naming(access_key):
    assert access_key is not None
    return re.fullmatch("[a-zA-Z][a-zA-Z0-9]{19}", access_key) is not None


def check_bucket_naming(name):
    """Checks restrictions.  Names are all lowercase.  Lens3 BANS DOTS.
    Lens3 bans "aws", "amazon", "minio", "goog*", and "g00g*".
    """
    # [Bucket naming rules]
    # https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
    # [Bucket naming guidelines]
    # https://cloud.google.com/storage/docs/naming-buckets
    return (re.fullmatch("[a-z0-9-]{3,63}", name) is not None
            and
            re.fullmatch(
                ("^[0-9.]*$|^.*-$"
                 "|^xn--.*$"
                 "|^.*-s3alias$|^.*--ol-s3$|^aws$|^amazon$"
                 "|^minio$|^goog.*$|^g00g.*$"),
                name) is None)


def check_claim_string(claim):
    return re.fullmatch("^[-_a-zA-Z0-9.:@%]{0,256}$", claim) is not None


def forge_s3_auth(access_key):
    """Makes an S3 authorization for an access-key."""
    return f"AWS4-HMAC-SHA256 Credential={access_key}////"


def parse_s3_auth(authorization):
    """Extracts an access-key in an S3 authorization, or returns None if
    not found.
    """
    if authorization is None:
        return None
    components = authorization.split(" ")
    if "AWS4-HMAC-SHA256" not in components:
        return None
    for c in components:
        if c.startswith("Credential="):
            e = c.find("/")
            if e == -1:
                return None
            else:
                k = c[len("Credential="):e]
                if check_access_key_naming(k):
                    return k
                else:
                    return None
        else:
            pass
        pass
    return None


def check_pool_is_well_formed(pooldesc, user_):
    """Checks a pool record is well-formed."""
    schema = _pool_desc_schema()
    jsonschema.validate(instance=pooldesc, schema=schema)
    # for bucket in pooldesc.get("buckets", []):
    #     _check_bkt_policy(bucket["bkt_policy"])
    #     pass
    # for accessKey in pooldesc.get("access_keys", []):
    #     _check_key_policy(accessKey["key_policy"])
    #     pass
    pass


def access_mux(ep, access_key, front_host, front_host_ip, timeout):
    """Tries to access a Mux.  This is used in access_mux_by_pool().  A
    Mux requires several http headers, especially including
    "X-REAL-IP".  Check the code of a Mux.
    """
    proto = "http"
    url = f"{proto}://{ep}/"
    headers = {}
    headers["HOST"] = front_host
    headers["X-REAL-IP"] = front_host_ip
    authorization = forge_s3_auth(access_key)
    headers["AUTHORIZATION"] = authorization
    headers["X-FORWARDED-PROTO"] = proto
    traceid = tracing.get()
    if traceid is not None:
        headers["X-TRACEID"] = traceid
        pass
    req = Request(url, headers=headers)
    logger.debug(f"urlopen to Mux: url={url}, timeout={timeout},"
                 f" headers={headers}")
    try:
        with urlopen(req, timeout=timeout) as response:
            pass
        status = response.status
        assert isinstance(status, int)
    except urllib.error.HTTPError as e:
        body = e.read()
        logger.warning(f"urlopen to Mux failed: url=({url}):"
                       f" exception=({e}); body=({body})")
        status = e.code
        assert isinstance(status, int)
    except urllib.error.URLError as e:
        logger.error(f"urlopen to Mux failed: url=({url}):"
                     f" exception=({e})")
        status = 400
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.error(f"urlopen to Mux failed: url=({url}):"
                     f" exception=({m})",
                     exc_info=True)
        status = 400
        pass
    logger.debug(f"urlopen to Mux: status={status}")
    return status


def gather_pool_desc(tables, pool_id):
    """Returns a pool record.  It reconstructs a record by gathering
    data scattered in the database.
    """
    pooldesc = tables.get_pool(pool_id)
    if pooldesc is None:
        return None
    bd = tables.get_buckets_directory_of_pool(pool_id)
    assert pooldesc["pool_name"] == pool_id
    assert pooldesc["buckets_directory"] == bd
    assert pooldesc["buckets_directory"] is not None
    #
    # Gather buckets.
    #
    bkts = gather_buckets(tables, pool_id)
    pooldesc["buckets"] = bkts
    #
    # Gather access-keys.
    #
    keys = gather_keys(tables, pool_id)
    pooldesc["access_keys"] = keys
    #
    # Gather dynamic states.
    #
    (state, reason, _) = tables.get_pool_state(pool_id)
    pooldesc["minio_state"] = str(state)
    pooldesc["minio_reason"] = str(reason)
    user_id = pooldesc["owner_uid"]
    u = tables.get_user(user_id)
    pooldesc["user_enabled_status"] = u["enabled"]
    check_pool_is_well_formed(pooldesc, None)
    return pooldesc


def gather_buckets(tables, pool_id):
    """Gathers buckets in a pool.  A returned list is sorted for
    displaying."""
    bkts1 = tables.list_buckets(pool_id)
    # bkts2 = [{k: v for (k, v) in d.items()
    #         if k not in {"pool", "modification_time"}}
    #         for d in bkts1]
    bkts3 = sorted(bkts1, key=lambda k: k["name"])
    return bkts3


def gather_keys(tables, pool_id):
    """Gathers access-keys in a pool.  A returned list is sorted for
    displaying.  It excludes a probe-key (which is internally used).
    """
    keys1 = tables.list_access_keys_of_pool(pool_id)
    keys2 = sorted(keys1, key=lambda k: k["modification_time"])
    keys3 = [k for k in keys2
             if (k is not None and k.get("secret_key") != "")]
    # keys4 = [_drop_non_ui_info_from_keys(k) for k in keys3]
    return keys3


def dump_db(tables):
    """Returns a record of confs, users, and pools for restoring."""
    # Collect confs:
    confs = tables.list_confs()
    # Collect users:
    user_list = tables.list_users()
    users = [tables.get_user(id) for id in user_list]
    # Collect pools:
    pool_list = tables.list_pools(None)
    pools = [gather_pool_desc(tables, id) for id in pool_list]
    return {"confs": confs, "users": users, "pools": pools}


def restore_db(tables, record):
    """Restores confs, users and pools from a dump file.  Note that the
    dumper uses gather_pool_desc() and the restorer performs the
    reverse in _restore_pool().  It does not restore MinIO state of a
    pool ("minio_state" and "minio_reason").  Call after resetting a
    database.  It is an error if some entries are already occupied: a
    buckets-directory, bucket names, and access-keys, (or etc.).
    Pools are given new pool-ids.
    """
    confs = record.get("confs", [])
    users = record.get("users", [])
    pools = record.get("pools", [])
    # Restore Confs.
    for e in confs:
        tables.set_conf(e)
        pass
    # Restore Users.
    for e in users:
        tables.set_user(e)
        pass
    # Restore Pools.
    for pooldesc in pools:
        _restore_pool(tables, pooldesc)
        pass
    pass


def _restore_pool(tables, pooldesc):
    """Restores a pool.  Call this after restoring users."""
    now = int(time.time())
    user_id = pooldesc["owner_uid"]
    owner_gid = pooldesc["owner_gid"]
    u = tables.get_user(user_id)
    if u is None:
        raise Api_Error(401, f"Bad user (unknown): {user_id}")
    if owner_gid not in u["groups"]:
        raise Api_Error(401, f"Bad group for a user: {owner_gid}")
    #
    # Restore a pool.
    #
    pool_id = pooldesc["pool_name"]
    entry1 = {
        "pool_name": pooldesc["pool_name"],
        "owner_uid": pooldesc["owner_uid"],
        "owner_gid": pooldesc["owner_gid"],
        "buckets_directory": pooldesc["buckets_directory"],
        "probe_key": pooldesc["probe_key"],
        "expiration_time": pooldesc["expiration_time"],
        "online_status": pooldesc["online_status"],
        "modification_time": pooldesc["modification_time"],
    }
    tables.set_pool(pool_id, entry1)
    # tables.set_pool_state(pool_id, state, reason)
    #
    # Restore a buckets-directory.
    #
    path = pooldesc["buckets_directory"]
    tables.set_ex_buckets_directory(path, pool_id)
    #
    # Restore buckets.
    #
    bkts = pooldesc["buckets"]
    for b in bkts:
        bucket = b["name"];
        entry2 = {
            "pool": b["pool"],
            "bkt_policy": b["bkt_policy"],
            "modification_time": b["modification_time"],
        }
        (ok, holder) = tables.set_ex_bucket(bucket, entry2)
        if not ok:
            owner = get_pool_owner_for_messages(tables, holder)
            raise Api_Error(403, f"Bucket name taken: owner={owner}")
        pass
    #
    # Restore access-keys.
    #
    keys = pooldesc["access_keys"]
    for k in keys:
        xid = k["access_key"]
        entry3 = {
            "owner": k["owner"],
            "secret_key": k["secret_key"],
            "key_policy": k["key_policy"],
            "expiration_time": k["expiration_time"],
            "modification_time": k["modification_time"],
        }
        ok = tables.set_ex_xid(xid, "akey", entry3)
        if not ok:
            raise Api_Error(400, "Duplicate access-key: {key}")
        pass
    pass
