# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from jsonschema import validate
from lenticularis.utility import dict_diff
from lenticularis.utility import logger


def merge_zone(user_id, existing, zone):
    def find_and_set(key, *dicts):
        for d in dicts:
            val = d.get(key)
            if val is not None:
                zone[key] = val
                break

    #logger.debug(f"@@@ user_id: {user_id}")
    #logger.debug(f"@@@ existing: {existing}")
    #logger.debug(f"@@@ zone: {zone}")

    if not existing:
        existing = {}
    zone["user"] = user_id
    find_and_set("group", zone, existing)
    find_and_set("rootSecret", existing)  # do not use the value from `zone`
    find_and_set("bucketsDir", zone, existing)
    find_and_set("buckets", zone, existing)
    find_and_set("accessKeys", zone, existing)
    find_and_set("directHostnames", zone, existing)
    find_and_set("expDate", zone, existing)
    find_and_set("status", zone, existing)
    #logger.debug(f"@@@ result: {zone}")


def compare_access_keys(existing, zone):
    if existing is None:
        return []
    e = existing.get("accessKeys")
    z = zone.get("accessKeys")
    if (e, z) == (None, None):
        return []

    if z is None:
        return []
    e_dic = {i.get("accessKeyID"): i for i in e}
    z_dic = {i.get("accessKeyID"): i for i in z}
    #logger.debug(f"@@@ {e_dic} {z_dic}")
    return dict_diff(e_dic, z_dic)


def compare_buckets_directory(existing, zone):
    if existing is None:
        return []
    e = existing.get("bucketsDir")
    z = zone.get("bucketsDir")
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


def check_conflict(zoneID, zone, z_id, z):
    #logger.debug(f"@@@ zoneID = {zoneID}, zone = {zone}, z_id = {z_id}, z = {z}")

    reasons = []

    def zone_keys(zoneID, zone):
        return set([zoneID] + [e.get("accessKeyID")
                   for e in zone.get("accessKeys")])

    def direct_hostnames(zone):
        return set(zone.get("directHostnames"))

    #logger.debug(f"@@@ z_id = {z_id}")
    #logger.debug(f"@@@ zone = {zone}")
    #logger.debug(f"@@@ z = {z}")

    # check Access Key ID
    new = zone_keys(zoneID, zone)
    old = zone_keys(z_id, z)
    #logger.debug(f"@@@ new = {new}")
    #logger.debug(f"@@@ old = {old}")
    i = new.intersection(old)
    if i:
        #logger.debug(f"@@@ KEY CONFLICT {i}")
        reasons.append({"Zone ID / Access Key ID": i})

    # check buckets directories
    new = {zone["bucketsDir"]}
    old = {z["bucketsDir"]}
    #logger.debug(f"@@@ new = {new}")
    #logger.debug(f"@@@ old = {old}")
    i = new.intersection(old)
    if new == old:
        #logger.debug(f"@@@ DIR CONFLICT {new}")
        reasons.append({"bucketsDir": i})

    # check Direct Hostnames
    new = direct_hostnames(zone)
    old = direct_hostnames(z)
    #logger.debug(f"@@@ new = {new}")
    #logger.debug(f"@@@ old = {old}")
    i = new.intersection(old)
    if i:
        #logger.debug(f"@@@ HOST CONFLICT {i}")
        reasons.append({"directHostname": i})

    return reasons


def zone_schema(type_number):

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
            "accessKeyID": {"type": "string"},
            "secretAccessKey": {"type": "string"},
            "policyName": {"type": "string"},
        },
        "required": [
            "accessKeyID",
            "secretAccessKey",
            "policyName",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "user": {"type": "string"},
            "group": {"type": "string"},
            "rootSecret": {"type": "string"},
            "bucketsDir": {"type": "string"},
            "buckets": {"type": "array", "items": bucket},
            "accessKeys": {"type": "array", "items": access_key},
            "directHostnames": {"type": "array", "items": {"type": "string"}},
            "expDate": type_number,
            "status": {"type": "string"},
            "permission": {"type": "string"},
        },
        "required": [
            "user",
            "group",
            "rootSecret",
            "bucketsDir",
            "buckets",
            "accessKeys",
            "directHostnames",
            "expDate",
            "status",
            "permission",
        ],
        "additionalProperties": False,
    }


def check_zone_schema(dict, user):
    validate(instance=dict, schema=zone_schema({"type": "string"}))


def check_policy(policy):
    if policy not in {"none", "upload", "download", "public"}:
        raise Exception(f"invalid policy: {policy}")


def check_policy_name(policy_name):
    if policy_name not in {"readwrite", "readonly", "writeonly"}:
        raise Exception(f"invalid policy_name: {policy_name}")


def check_status(status):
    if status not in {"online", "offline"}:
        raise Exception(f"invalid status: {status}")


def check_permission(permission):
    if permission not in {"allowed", "denied"}:
        raise Exception(f"invalid permission: {permission}")


def check_number(number):
    if not number.isdigit():
        raise Exception(f"number expected: {number}")


def check_pool_dict_is_sound(dict, user, adm_conf):
    """
    in situ checks are defined in `check_zone_values'
    """

    for bucket in dict.get("buckets", []):  # may be absent
        check_policy(bucket["policy"])

    check_status(dict["status"]) # mandatory
    check_permission(dict["permission"]) # mandatory
    for accessKey in dict.get("accessKeys", []):
        check_policy_name(accessKey["policyName"])

    check_number(dict["expDate"])
    check_number(dict.get("atime", "0"))  # may be absent

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
