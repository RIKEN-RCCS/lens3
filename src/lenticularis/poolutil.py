# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
import jsonschema
from lenticularis.utility import dict_diff
from lenticularis.utility import logger


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


def merge_pool_descriptions(user_id, existing, zone):
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


def compare_access_keys(existing, zone):
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


def compare_buckets_directory(existing, zone):
    if existing is None:
        return []
    e = existing.get("buckets_directory")
    z = zone.get("buckets_directory")
    if z is None:
        return []
    if e != z:
        return [{"reason": "modified", "existing": e, "new": z}]
    return []


def compare_buckets(existing, zone):
    if existing is None:
        return []
    e = existing.get("buckets")
    z = zone.get("buckets")
    if z is None:
        return []
    e_dic = {i.get("key"): i for i in e}
    z_dic = {i.get("key"): i for i in z}
    #logger.debug(f"@@@ {e_dic} {z_dic}")
    return dict_diff(e_dic, z_dic)


def _zone_keys(zoneID, zone):
    return set([zoneID] + [e.get("access_key")
                           for e in zone.get("access_keys")])


def _direct_hostnames(zone):
    return set(zone.get("direct_hostnames"))


def check_conflict(zoneID, zone, z_id, z):
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


def check_policy(policy):
    if policy not in {"none", "upload", "download", "public"}:
        raise Exception(f"invalid policy: {policy}")
    return


def check_policy_name(policy_name):
    if policy_name not in {"readwrite", "readonly", "writeonly"}:
        raise Exception(f"invalid policy_name: {policy_name}")
    return


def check_status(status):
    if status not in {"online", "offline"}:
        raise Exception(f"invalid status: {status}")
    return


def check_permission(permission):
    if permission not in {"allowed", "denied"}:
        raise Exception(f"invalid permission: {permission}")
    return


def check_number(number):
    if not number.isdigit():
        raise Exception(f"number expected: {number}")
    return


def check_pool_dict_is_sound(pooldesc, user, adm_conf):
    """Checks somewhat on values are defined in _check_zone_values.
    """

    for bucket in pooldesc.get("buckets", []):
        check_policy(bucket["policy"])
    check_status(pooldesc["online_status"])
    check_permission(pooldesc["permit_status"])
    for accessKey in pooldesc.get("access_keys", []):
        check_policy_name(accessKey["policy_name"])
        pass

    check_number(pooldesc["expiration_date"])
    check_number(pooldesc.get("atime", "0"))  # may be absent

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
            "key": {"type": "string"},
            "policy": {"type": "string"},
        },
        "required": [
            "key",
            "policy",
        ],
        "additionalProperties": False,
    }

    access_key = {
        "type": "object",
        "properties": {
            "access_key": {"type": "string"},
            "secret_key": {"type": "string"},
            "policy_name": {"type": "string"},
        },
        "required": [
            "access_key",
            "secret_key",
            "policy_name",
        ],
        "additionalProperties": False,
    }

    schema = {
        "type": "object",
        "properties": {
            "pool_name": {"type": "string"},
            "owner_uid": {"type": "string"},
            "owner_gid": {"type": "string"},
            "root_secret": {"type": "string"},
            "buckets_directory": {"type": "string"},
            "buckets": {"type": "array", "items": bucket},
            "probe_access": {"type": "string"},
            "access_keys": {"type": "array", "items": access_key},
            "direct_hostnames": {"type": "array", "items": {"type": "string"}},
            "expiration_date": type_number,
            "permit_status": {"type": "string"},
            "online_status": {"type": "string"},
            "minio_state": {"type": "string"},
            # Below keys are internally held:
            # "atime"
       },
        "required": [
            # "pool_name",
            "owner_uid",
            "owner_gid",
            "root_secret",
            "buckets_directory",
            "buckets",
            "access_keys",
            "direct_hostnames",
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
