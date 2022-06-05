"""Small utility."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
import enum
import jsonschema
from lenticularis.utility import dict_diff
from lenticularis.utility import logger


class Api_Error(Exception):
    def __init__(self, code, *args):
        self.code = code
        super().__init__(*args)
        return

    pass


class Pool_State(enum.Enum):
    INITIAL = "initial"
    READY = "ready"
    DISABLED = "disabled"
    INOPERABLE = "inoperable"

    def __str__(self):
        return self.value

    pass


def _update_for_key(dict0, key, dict1, overwrite):
    """Dict-updates for the key.  It skips updating an existing entry
    unless overwrite.
    """
    if dict0.get(key) is None or overwrite:
        val = dict1.get(key)
        if val is not None:
            dict0[key] = val
    else:
        pass
    return


def merge_pool_descriptions__(user_id, existing, zone):
    ## Note it disallows updating "root_secret" by preferring an
    ## existing one.
    if not existing:
        existing = {}
    zone["owner_uid"] = user_id
    _update_for_key(zone, "owner_gid", existing, False)
    _update_for_key(zone, "root_secret", existing, True)
    _update_for_key(zone, "buckets_directory", existing, False)
    _update_for_key(zone, "buckets", existing, False)
    _update_for_key(zone, "access_keys", existing, False)
    _update_for_key(zone, "direct_hostnames", existing, False)
    _update_for_key(zone, "expiration_date", existing, False)
    _update_for_key(zone, "online_status", existing, False)
    return


def compare_access_keys__(existing, zone):
    if existing is None:
        return []
    e = existing.get("access_keys")
    z = zone.get("access_keys")
    if (e, z) == (None, None):
        return []

    if z is None:
        return []
    e_dic = {i.get("access_key"): i for i in e}
    z_dic = {i.get("access_key"): i for i in z}
    #logger.debug(f"@@@ {e_dic} {z_dic}")
    return dict_diff(e_dic, z_dic)


def compare_buckets_directory__(existing, zone):
    if existing is None:
        return []
    e = existing.get("buckets_directory")
    z = zone.get("buckets_directory")
    if z is None:
        return []
    if e != z:
        return [{"reason": "modified", "existing": e, "new": z}]
    return []


def compare_buckets__(existing, zone):
    if existing is None:
        return []
    e = existing.get("buckets")
    z = zone.get("buckets")
    if z is None:
        return []
    e_dic = {i.get("name"): i for i in e}
    z_dic = {i.get("name"): i for i in z}
    #logger.debug(f"@@@ {e_dic} {z_dic}")
    return dict_diff(e_dic, z_dic)


def _zone_keys(zoneID, zone):
    return set([zoneID] + [e.get("access_key")
                           for e in zone.get("access_keys")])


def _direct_hostnames(zone):
    return set(zone.get("direct_hostnames"))


def check_conflict__(zoneID, zone, z_id, z):
    #logger.debug(f"@@@ zoneID = {zoneID}, zone = {zone}, z_id = {z_id}, z = {z}")

    reasons = []

    #logger.debug(f"@@@ z_id = {z_id}")
    #logger.debug(f"@@@ zone = {zone}")
    #logger.debug(f"@@@ z = {z}")

    # check Access Key ID
    new = _zone_keys(zoneID, zone)
    old = _zone_keys(z_id, z)
    #logger.debug(f"@@@ new = {new}")
    #logger.debug(f"@@@ old = {old}")
    i = new.intersection(old)
    if i:
        #logger.debug(f"@@@ KEY CONFLICT {i}")
        reasons.append({"Zone ID / Access Key ID": i})
        pass
    # check buckets directories
    new = {zone["buckets_directory"]}
    old = {z["buckets_directory"]}
    #logger.debug(f"@@@ new = {new}")
    #logger.debug(f"@@@ old = {old}")
    i = new.intersection(old)
    if new == old:
        #logger.debug(f"@@@ DIR CONFLICT {new}")
        reasons.append({"buckets_directory": i})
        pass
    # check Direct Hostnames
    new = _direct_hostnames(zone)
    old = _direct_hostnames(z)
    #logger.debug(f"@@@ new = {new}")
    #logger.debug(f"@@@ old = {old}")
    i = new.intersection(old)
    if i:
        #logger.debug(f"@@@ HOST CONFLICT {i}")
        reasons.append({"directHostname": i})
        pass
    return reasons


def _check_bkt_policy(policy):
    if policy not in {"none", "upload", "download", "public"}:
        raise Exception(f"invalid policy: {policy}")
    return


def _check_key_policy(key_policy):
    if key_policy not in {"readwrite", "readonly", "writeonly"}:
        raise Exception(f"invalid key_policy: {key_policy}")
    return


def _check_online_status(status):
    ##if status not in {"online", "offline"}:
    ##    raise Exception(f"invalid status: {status}")
    return


def _check_permit_status(permission):
    ##if permission not in {"allowed", "denied"}:
    ##    raise Exception(f"invalid permission: {permission}")
    return


def _check_number(number):
    if not number.isdigit():
        raise Exception(f"number expected: {number}")
    return


def check_pool_dict_is_sound(pooldesc, user, adm_conf):
    """Checks somewhat on values are defined in _check_zone_values.
    """
    for bucket in pooldesc.get("buckets", []):
        _check_bkt_policy(bucket["bkt_policy"])
        pass
    _check_online_status(pooldesc["online_status"])
    _check_permit_status(pooldesc["permit_status"])
    for accessKey in pooldesc.get("access_keys", []):
        _check_key_policy(accessKey["key_policy"])
        pass
    # _check_number(pooldesc["expiration_date"])
    # _check_number(pooldesc.get("atime", "0"))
    #
    # XXX fixme check_policy()
    # XXX FIXME
    # group: user's group
    # buckets directory: path
    # buckets: 3..63, [a-z0-9][-\.a-z0-9][a-z0-9]
    #          no .. , not ip-address form
    # check all direct hostnames ends with one of direct_hostname_domains
    # expiration date is not past
    # zoneID: 24 [a-zA-Z][\w]+
    # Access Key ID: 16..128 [a-zA-Z][\w]+
    # Secret Access Key: 1..128 string
    # status: online/offline
    return


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
            "modification_date": {"type": "integer"},
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


def check_pool_is_well_formed(desc, user_):
    """Checks a pool description is well-formed for passing to Web-UI."""
    schema = _pool_desc_schema({"type": "string"})
    jsonschema.validate(instance=desc, schema=schema)
    return
