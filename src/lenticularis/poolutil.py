"""Small utility."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
import enum
import jsonschema
from lenticularis.utility import logger


class Api_Error(Exception):
    def __init__(self, code, *args):
        self.code = code
        super().__init__(*args)
        pass

    pass


class Pool_State(enum.Enum):
    INITIAL = "initial"
    READY = "ready"
    DISABLED = "disabled"
    INOPERABLE = "inoperable"

    def __str__(self):
        return self.value

    pass


def _drop_non_ui_info_from_keys(access_key):
    """Drops unnecessary info to pass access-key info to Web-UI.  That is,
    they are {"use", "owner", "modification_time"}.
    """
    needed = {"access_key", "secret_key", "key_policy"}
    return {k: v for (k, v) in access_key.items() if k in needed}


def gather_buckets(tables, pool_id):
    """Gathers buckets in the pool."""
    bkts = tables.list_buckets(pool_id)
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
    # pooldesc.pop("probe_access")
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
    return re.fullmatch("[a-zA-Z0-9]{20}", pool_id) is not None


def check_bucket_naming(name):
    """Checks restrictions.  Names are all lowercase.  IT BANS DOTS.  It
    bans "aws", "amazon", "minio", "goog.*", and "g00g.*".
    """
    ## [Bucket naming rules]
    ## https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
    ## [Bucket naming guidelines]
    ## https://cloud.google.com/storage/docs/naming-buckets
    return (re.fullmatch("[a-z0-9-]{3,63}", name) is not None
            and
            re.fullmatch(
                ("^[0-9.]*$|^.*-$"
                 "|^xn--.*$|^.*-s3alias$|^aws$|^amazon$"
                 "|^minio$|^goog.*$|^g00g.*$"),
                name) is None)


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
            "probe_access": {"type": "string"},
            "access_keys": {"type": "array", "items": access_key},
            "minio_state": {"type": "string"},
            "minio_reason": {"type": "string"},
            "expiration_date": {"type": "integer"},
            "permit_status": {"type": "boolean"},
            "online_status": {"type": "boolean"},
            "modification_time": {"type": "integer"},
            # Below keys are internally held:
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
