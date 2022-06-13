"""Small utility."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
import enum
import jsonschema
from urllib.request import Request, urlopen
import urllib.error
from lenticularis.utility import logger


class Api_Error(Exception):
    def __init__(self, code, *args):
        self.code = code
        super().__init__(*args)
        pass

    pass


class Pool_State(enum.Enum):
    """A pool state."""
    INITIAL = "initial"
    READY = "ready"
    DISABLED = "disabled"
    INOPERABLE = "inoperable"

    def __str__(self):
        return self.value

    pass


class ID_Use(enum.Enum):
    """A usage of an ID entry in the table.  The "id:" entries are either
    pool-ids or access-keys.
    """
    POOL = "pool"
    KEY = "access_key"

    def __str__(self):
        return self.value

    pass


class Key_Policy(enum.Enum):
    READWRITE = "readwrite"
    READONLY = "readonly"
    WRITEONLY = "writeonly"

    def __str__(self):
        return self.value

    pass


class Bkt_Policy(enum.Enum):
    NONE = "none"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    PUBLIC = "public"

    def __str__(self):
        return self.value

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
    if not u.get("permitted"):
        raise Api_Error(403, (f"User disabled: {user_id}"))
    pass


def ensure_mux_is_running(tables):
    muxs = tables.list_mux_eps()
    if len(muxs) == 0:
        raise Api_Error(500, (f"No Mux services in Lens3"))
    pass


def ensure_pool_state(tables, pool_id):
    (poolstate, _) = tables.get_pool_state(pool_id)
    if poolstate != Pool_State.READY:
        if poolstate == Pool_State.DISABLED:
            raise Api_Error(403, f"Pool disabled")
        elif poolstate == Pool_State.INOPERABLE:
            raise Api_Error(500, f"Pool inoperable")
        else:
            raise Api_Error(500, f"Pool is in {poolstate}")
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
    """Checks a key owner is a pool.  It accepts no access-key."""
    if access_key is None:
        return
    desc = tables.get_id(access_key)
    if desc is None:
        raise Api_Error(403, f"Non-existing access-key: {access_key}")
    if not (desc.get("use") == "access_key"
            and desc.get("owner") == pool_id):
        raise Api_Error(403, f"Wrong access-key: {access_key}")
    pass


def _drop_non_ui_info_from_keys(access_key):
    """Drops unnecessary info to pass access-key info to Web-UI.  That is,
    they are {"use", "owner", "modification_time"}.
    """
    needed = {"access_key", "secret_key", "key_policy"}
    return {k: v for (k, v) in access_key.items() if k in needed}


def gather_buckets(tables, pool_id):
    """Gathers buckets in the pool.  It drops unnecessary slots."""
    bkts = tables.list_buckets(pool_id)
    bkts = [{k: v for (k, v) in d.items()
             if k not in {"pool", "modification_time"}}
            for d in bkts]
    bkts = sorted(bkts, key=lambda k: k["name"])
    return bkts


def gather_keys(tables, pool_id):
    """Gathers keys in the pool, but drops a probe-key and slots
    uninteresting to Web-UI.
    """
    keys = tables.list_access_keys_of_pool(pool_id)
    keys = sorted(keys, key=lambda k: k["modification_time"])
    keys = [k for k in keys
            if (k is not None and k.get("secret_key") != "")]
    keys = [_drop_non_ui_info_from_keys(k) for k in keys]
    return keys


def gather_pool_desc(tables, pool_id):
    """Returns a pool description for displaying by Web-UI."""
    pooldesc = tables.get_pool(pool_id)
    if pooldesc is None:
        return None
    bd = tables.get_buckets_directory_of_pool(pool_id)
    pooldesc["buckets_directory"] = bd
    assert pooldesc["buckets_directory"] is not None
    # Gather buckets.
    bkts = gather_buckets(tables, pool_id)
    pooldesc["buckets"] = bkts
    # Gather keys.
    keys = gather_keys(tables, pool_id)
    pooldesc["access_keys"] = keys
    # pooldesc.pop("probe_key")
    pooldesc["pool_name"] = pool_id
    (poolstate, reason) = tables.get_pool_state(pool_id)
    pooldesc["minio_state"] = str(poolstate)
    pooldesc["minio_reason"] = str(reason)
    # pooldesc["expiration_date"]
    # pooldesc["online_status"]
    user_id = pooldesc["owner_uid"]
    u = tables.get_user(user_id)
    pooldesc["permit_status"] = u["permitted"]
    check_pool_is_well_formed(pooldesc, None)
    return pooldesc


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


def _check_bkt_policy(bkt_policy):
    assert bkt_policy in {"none", "upload", "download", "public"}
    pass


def _check_key_policy(key_policy):
    assert key_policy in {"readwrite", "readonly", "writeonly"}
    pass


def check_user_naming(user_id):
    return re.fullmatch("^[a-z_][-a-z0-9_]{0,31}$", user_id) is not None


def check_pool_naming(pool_id):
    assert pool_id is not None
    return re.fullmatch("[a-zA-Z][a-zA-Z0-9]{19}", pool_id) is not None


def check_access_key_naming(access_key):
    assert access_key is not None
    return re.fullmatch("[a-zA-Z][a-zA-Z0-9]{19}", access_key) is not None


def check_bucket_naming(name):
    """Checks restrictions.  Names are all lowercase.  IT BANS DOTS.  It
    bans "aws", "amazon", "minio", "goog.*", and "g00g.*".
    """
    # [Bucket naming rules]
    # https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
    # [Bucket naming guidelines]
    # https://cloud.google.com/storage/docs/naming-buckets
    return (re.fullmatch("[a-z0-9-]{3,63}", name) is not None
            and
            re.fullmatch(
                ("^[0-9.]*$|^.*-$"
                 "|^xn--.*$|^.*-s3alias$|^aws$|^amazon$"
                 "|^minio$|^goog.*$|^g00g.*$"),
                name) is None)


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


def _pool_desc_schema(type_number):
    bucket = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "bkt_policy": {"type": "string"},
        },
        "required": [
            "name",
            "bkt_policy",
        ],
        "additionalProperties": False,
    }

    access_key = {
        "type": "object",
        "properties": {
            "access_key": {"type": "string"},
            "secret_key": {"type": "string"},
            "key_policy": {"type": "string"},
        },
        "required": [
            "access_key",
            "secret_key",
            "key_policy",
        ],
        "additionalProperties": False,
    }

    schema = {
        "type": "object",
        "properties": {
            "pool_name": {"type": "string"},
            "owner_uid": {"type": "string"},
            "owner_gid": {"type": "string"},
            "buckets_directory": {"type": "string"},
            "buckets": {"type": "array", "items": bucket},
            "access_keys": {"type": "array", "items": access_key},
            "probe_key": {"type": "string"},
            "minio_state": {"type": "string"},
            "minio_reason": {"type": "string"},
            "expiration_date": {"type": "integer"},
            "permit_status": {"type": "boolean"},
            "online_status": {"type": "boolean"},
            "modification_time": {"type": "integer"},
        },
        "required": [
            # "pool_name",
            "owner_uid",
            "owner_gid",
            "buckets_directory",
            "buckets",
            "access_keys",
            "expiration_date",
            "permit_status",
            "online_status",
        ],
        "additionalProperties": False,
    }
    return schema


def check_pool_is_well_formed(pooldesc, user_):
    """Checks a pool description is well-formed for passing to Web-UI."""
    schema = _pool_desc_schema({"type": "string"})
    jsonschema.validate(instance=pooldesc, schema=schema)
    for bucket in pooldesc.get("buckets", []):
        _check_bkt_policy(bucket["bkt_policy"])
        pass
    for accessKey in pooldesc.get("access_keys", []):
        _check_key_policy(accessKey["key_policy"])
        pass
    pass


def access_mux(traceid, ep, access_key, facade_hostname, facade_host_ip,
               timeout):
    # Mux requires several http-headers, especially including
    # "X-REAL-IP".  See the code of Mux.
    proto = "http"
    url = f"{proto}://{ep}/"
    headers = {}
    headers["HOST"] = facade_hostname
    headers["X-REAL-IP"] = facade_host_ip
    authorization = forge_s3_auth(access_key)
    headers["AUTHORIZATION"] = authorization
    headers["X-FORWARDED-PROTO"] = proto
    if traceid is not None:
        headers["X-TRACEID"] = traceid
        pass
    req = Request(url, headers=headers)
    logger.debug(f"urlopen with url={url}, timeout={timeout},"
                 f" headers={headers}")
    try:
        with urlopen(req, timeout=timeout) as response:
            pass
        status = response.status
        assert isinstance(status, int)
    except urllib.error.HTTPError as e:
        b = e.read()
        logger.warning(f"urlopen to Mux failed for url=({url}):"
                       f" exception=({e}); body=({b})")
        status = e.code
        assert isinstance(status, int)
    except urllib.error.URLError as e:
        logger.error(f"urlopen to Mux failed for url=({url}):"
                     f" exception=({e})")
        status = 400
    except Exception as e:
        logger.error(f"urlopen to Mux failed for url=({url}):"
                     f" exception=({e})",
                     exc_info=True)
        status = 400
        pass
    logger.debug(f"urlopen to Mux: status={status}")
    return status
