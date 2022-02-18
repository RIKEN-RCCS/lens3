# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import json
from lenticularis.utility import logger
from lenticularis.utility import random_str
import threading
import time


def try_mangle_a_zone(lc, zone_id):
    (zone, csrf_token) = get_zone(lc, zone_id)
    #print(f"@zone: {zone_id} = {zone}")
    #print(f"@zone: csrf_token = {csrf_token}")
    mangled_zone = mangle_zone(zone)
    #print(f"@zone: {zone_id} = {zone}")
    try:
        create_zone(lc, zone_id, mangled_zone, csrf_token)
    except Exception as e:
        if "Access Key may not be modified" in str(e):
             logger.debug("Expected failure")
        else:
            raise
    return zone_id


def mangle_zone(zone):
    zone = zone.copy()
    zone["accessKeys"][0]["secretAccessKey"] = "xyzzy"
    zone.pop("atime")
    zone.pop("directHostnameDomains")
    zone.pop("groups")
    zone.pop("mode")
    zone.pop("zoneID")
    zone.pop("endpoint_url")
    zone.pop("delegateHostnames")
    return zone


def create_new_zone(system_test, lc, user, injection=None):
    logger.debug(f"@@@ get_template")
    (template, csrf_token) = get_template(lc)
    system_test.rsleep()
    logger.debug(f"@@@ template = {template}")
    #zoneID = template["zoneID"]
    zone = fillout(template, user)
    logger.debug(f"@@@ zone = {zone}")
    res = create_zone(lc, zone, csrf_token, injection=injection)
    system_test.rsleep()
    return res["zonelist"][0]["zoneID"]


def create_a_bucket(system_test, lc, zone_id, key, policy="none"):
    #sys.stderr.write(f"@@@ get_template\n")
    (_, csrf_token) = get_zone(lc, zone_id)
    system_test.rsleep()
    #print(f"@@@ template = {template}")
    #zoneID = template["zoneID"]
    zone = {"buckets": [{"key": key, "policy": policy}]}
    res = put_update_zone_bk(lc, zone_id, zone, csrf_token, "buckets")
    system_test.rsleep()
    #res = create_zone(lc, zone, csrf_token)
    #return res["zonelist"][0]["zoneID"]


def change_secret(system_test, lc, zone_id):
    #sys.stderr.write(f"@@@ get_template\n")
    (zone, csrf_token) = get_zone(lc, zone_id)
    system_test.rsleep()

    access_key_id = next(e["accessKeyID"] for e in zone["accessKeys"] if e["policyName"] == "readwrite")
    old_secret = next(e["secretAccessKey"] for e in zone["accessKeys"] if e["policyName"] == "readwrite")

    logger.debug(f"@@@ access_key_id = {access_key_id}")
    #zoneID = template["zoneID"]
    #zoneID = template["zoneID"]
    zone = {"accessKeys": [{"accessKeyID": access_key_id}]}
    res = put_update_zone_bk(lc, zone_id, zone, csrf_token, "accessKeys")
    system_test.rsleep()
    zone = next(zone for zone in res["zonelist"] if zone["zoneID"] == zone_id)
    new_secret = next(e["secretAccessKey"] for e in zone["accessKeys"] if e["policyName"] == "readwrite")
    logger.debug(f"@@@ old_secret = {old_secret}")
    logger.debug(f"@@@ new_secret = {new_secret}")
    #res = create_zone(lc, zone, csrf_token)
    #return res["zonelist"][0]["zoneID"]


#def create_forged_zone(system_test, lc, user):
#    (_, csrf_token) = get_template(lc)
#    system_test.rsleep()
#    (zoneID, zone) = forge_zone(user)
#    zone = create_zone(lc, zone, csrf_token)
#    system_test.rsleep()
#    return res["zonelist"][0]["zoneID"]
#    #return zone["zoneID"]


def delete_all_zones(lc):
    (zones, csrf_token) = zone_list(lc)
    deleted = []
    for z in zones if zones else []:
        zoneID = z["zoneID"]
        delete_zone(lc, zoneID, csrf_token)
        deleted.append(zoneID)
    return deleted


def zone_list(lc):
    path = "/zone"
    traceid = random_str(12)
    threading.currentThread().name = traceid
    logger.debug(f"[{traceid}] GET {path}")
    r = lc.request(traceid, path, method="GET")
    return (r.get("zonelist"), r.get("CSRF-Token"))


def get_zone(lc, zone_id):
    path = f"/zone/{zone_id}"
    traceid = random_str(12)
    threading.currentThread().name = traceid
    logger.debug(f"[{traceid}] GET {path}")
    r = lc.request(traceid, path, method="GET")
    #sys.stderr.write(f"r = {r}")
    zone = next(zone for zone in r.get("zonelist") if zone["zoneID"] == zone_id)
    return (zone, r.get("CSRF-Token"))


def delete_zone(lc, zone_id, csrf_token):
    payload = {"CSRF-Token": csrf_token}
    path = f"/zone/{zone_id}"
    delete_body = json.dumps(payload).encode()
    traceid = random_str(12)
    threading.currentThread().name = traceid
    logger.debug(f"[{traceid}] DELETE {path}")
    return lc.request(traceid, path, data=delete_body, method="DELETE")


def get_template(lc):
    path = "/template"
    traceid = random_str(12)
    threading.currentThread().name = traceid
    logger.debug(f"[{traceid}] GET {path}")
    r = lc.request(traceid, path, method="GET")
    logger.debug(f"get_template {r}")
    return (r.get("zonelist")[0], r.get("CSRF-Token"))


def create_zone(lc, zone, csrf_token, injection=None):
    logger.debug(f"crate_zone {zone} (csrf_token)")
    if injection == "fail_to_send_csrf_token":
        csrf_token = "x" + csrf_token
    payload = {"CSRF-Token": csrf_token, "zone": zone}
    path = f"/zone"
    post_body = json.dumps(payload).encode()
    traceid = random_str(12)
    threading.currentThread().name = traceid
    logger.debug(f"[{traceid}] POST {path} {post_body}")
    return lc.request(traceid, path, data=post_body, method="POST")


def put_update_zone_bk(lc, zone_id, zone, csrf_token, bk):
    logger.debug(f"put_update_zone_bk {zone_id} {zone} (csrf_token) {bk}")
    payload = {"CSRF-Token": csrf_token, "zone": zone}
    if bk == "buckets":
        path = f"/zone/{zone_id}/buckets"
    elif bk == "accessKeys":
        path = f"/zone/{zone_id}/accessKeys"
    else:
        path = f"/zone/{zone_id}"
    put_body = json.dumps(payload).encode()
    traceid = random_str(12)
    threading.currentThread().name = traceid
    logger.debug(f"[{traceid}] PUT {path} {put_body}")
    return lc.request(traceid, path, data=put_body, method="PUT")



def fillout(template, user):

    #zoneID = template["zoneID"]
    #bucketsDir =
    direct_hostname_domains = template["directHostnameDomains"]
    direct_hostname_domain = direct_hostname_domains[0]
    hostname = random_str(12).lower()
    direct_hostname = f"{hostname}.{direct_hostname_domain}"
    direct_hostnames = template["directHostnames"]
    direct_hostnames.append(direct_hostname)
    buckets_dirname = f"zone.{random_str(12)}"
    return {
        "group": template["group"],
        "bucketsDir": f"/home/{user}/{buckets_dirname}",
        "buckets": template["buckets"],
        "accessKeys": template["accessKeys"],
        "directHostnames": direct_hostnames,
        "expDate": template["expDate"],
        "status": template["status"]
    }


def forge_zone(user):
    zone_id = "RFyNGpTq3HVkklCKeoMl"
    bucketsDir = f"/home/{user}/zone.{zone_id}"

    zone = {"group": user,
        "bucketsDir": bucketsDir,
        "buckets": [
            {"key": "work", "policy": "none"},
            {"key": "project", "policy": "none"},
            {"key": "pub", "policy": "public"},
            {"key": "release", "policy": "download"},
            {"key": "inquiry", "policy": "upload"}],
        "accessKeys": [
            {"accessKeyID": "PDVxvhmRRTfz0UAlJ9O5",
             "secretAccessKey": "rROsTvoCcaJTf3BdJrVlJnjowP9CQp2uMGLCEwHkbA2obhd4",
             "policyName": "readwrite"},
            {"accessKeyID": "VD0qydrWJhJloKM2Sblo",
             "secretAccessKey": "mygcyvkeoXDQs6lWUSYsGuW4v3jsi7lqED8pKzDdn1RS68Is",
             "policyName": "readonly"},
            {"accessKeyID": "zHf4wOChYyZXAmI9TG9s",
             "secretAccessKey": "ZuCzd6nnZCNM951jamODl7T9LMpgE8NOvekr3FlkvSYuMvX7",
             "policyName": "writeonly"}],
        "directHostnames": [],
        "expDate": "1640995200",
        "status": "online"}

    return (zone_id, zone)


def accesskey_of_a_zone(lc, policy_name="readwrite"):
    (zones, _) = zone_list(lc)
    #sys.stderr.write(f"response: {zones}\n")
    #zones = response["zonelist"]
    if zones == []:
        return (None, None, None)
    for zone in zones:
        user = zone["user"]
        #policyName = "readwrite"  #, "readonly", "writeonly"
        for access_key in zone.get("accessKeys"):
            if access_key.get("policyName") == policy_name:
                return (user, access_key["accessKeyID"], access_key["secretAccessKey"])
    return (None, None, None)


def direct_hostname_of_a_zone(lc):
    (zones, _) = zone_list(lc)
    #sys.stderr.write(f"response: {zones}\n")
    #zones = response["zonelist"]
    if zones == []:
        return (None, None)
    for zone in zones:
        user = zone["user"]
        direct_hostnames = zone.get("directHostnames")
        if direct_hostnames and direct_hostnames != []:
            return (user, direct_hostnames[0])
    return (None, None)
