# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

#import argparse
from lenticularis.utility import logger
from lenticularis.utility import random_str, format_rfc3339_z
from api_manipulation import try_mangle_a_zone
from api_manipulation import create_new_zone
from api_manipulation import create_a_bucket
from api_manipulation import change_secret
#from api_manipulation import create_forged_zone
from api_manipulation import delete_all_zones
from api_manipulation import zone_list
from api_manipulation import get_zone
import time

def cleanup_zone(system_test):
    lc = system_test.lent_client()

    logger.debug(f"@delete_all_zones")
    zone_ids = delete_all_zones(lc)

    #print(f"{format_rfc3339_z(time.time())} deleted: {zone_ids}")
    logger.debug(f"deleted: {zone_ids}")


def test_api_manipulation(system_test):
    user = system_test.user

    lc = system_test.lent_client()

    system_test.rsleep()

    try:
        logger.debug(f"@zone list: start")
        (zones, csrf_token) = zone_list(lc)
        logger.debug(f"@zone list: {zones}")
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: zone_list {e}", flush=True)
        logger.debug(f"FAIL: zone_list {e}")
        logger.exception(e)
        raise

    system_test.rsleep()

    for z in zones if zones else []:
        zone_id = z["zoneID"]
        logger.debug(f"@zone_id: {zone_id}")
        try:
            logger.debug(f"@get_zone: start")
            (zone, csrf_token) = get_zone(lc, zone_id)
            logger.debug(f"@zone: {zone}")
        except Exception as e:
            print(f"{format_rfc3339_z(time.time())} FAIL: get_zone({zone_id}) {e}", flush=True)
            logger.debug(f"FAIL: get_zone({zone_id}) {e}")
            logger.exception(e)
            raise

    system_test.rsleep()

    try:
        logger.debug(f"@create_new_zone: start")
        zone_id = create_new_zone(system_test, lc, user, injection="fail_to_send_csrf_token")
        logger.debug(f"@created: {zone_id}")
    except Exception as e:
        #print(f"{format_rfc3339_z(time.time())} EXPECTED FAILURE: create_new_zone({user}) {e}")
        logger.debug(f"EXPECTED FAILURE: create_new_zone({user}) {e}")
        #logger.exception(e)
        pass

    try:
        logger.debug(f"@create_new_zone: start")
        zone_id = create_new_zone(system_test, lc, user)
        logger.debug(f"@created: {zone_id}")
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: create_new_zone({user}) {e}", flush=True)
        logger.debug(f"FAIL: create_new_zone({user}) {e}")
        logger.exception(e)
        raise

    system_test.rsleep()

    try:
        logger.debug(f"@get_zone: {zone_id}")
        (zone, csrf_token) = get_zone(lc, zone_id)
        logger.debug(f"@zone: {zone}")
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: get_zone({zone_id}) {e}", flush=True)
        logger.debug(f"FAIL: get_zone({zone_id}) {e}")
        logger.exception(e)
        raise

    try:
        key = random_str(12).lower()
        logger.debug(f"@create_a_bucket: {zone_id} {key}")
        zone = create_a_bucket(system_test, lc, zone_id, key)
        logger.debug(f"@updated: {zone}")
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: create_a_bucket({zone_id}, {key}) {e}", flush=True)
        logger.debug(f"FAIL: create_a_bucket({zone_id}, {key}) {e}")
        logger.exception(e)
        raise

    system_test.rsleep()

    try:
        key = random_str(12).lower()
        logger.debug(f"@create_a_bucket: {zone_id} {key} public")
        zone = create_a_bucket(system_test, lc, zone_id, key, policy="public")
        logger.debug(f"@updated: {zone}")
        system_test.u["public_bucket"] = key
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: create_a_bucket({zone_id}, {key}, public) {e}", flush=True)
        logger.debug(f"FAIL: create_a_bucket({zone_id}, {key}, public) {e}")
        logger.exception(e)
        raise

    system_test.rsleep()

    try:
        key = random_str(12).lower()
        logger.debug(f"@create_a_bucket: {zone_id} {key} upload")
        zone = create_a_bucket(system_test, lc, zone_id, key, policy="upload")
        logger.debug(f"@updated: {zone}")
        system_test.u["upload_bucket"] = key
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: create_a_bucket({zone_id}, {key}, upload) {e}", flush=True)
        logger.debug(f"FAIL: create_a_bucket({zone_id}, {key}, upload) {e}")
        logger.exception(e)
        raise

    system_test.rsleep()

    try:
        key = random_str(12).lower()
        logger.debug(f"@create_a_bucket: {zone_id} {key} download")
        zone = create_a_bucket(system_test, lc, zone_id, key, policy="download")
        logger.debug(f"@updated: {zone}")
        system_test.u["download_bucket"] = key
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: create_a_bucket({zone_id}, {key}, download) {e}", flush=True)
        logger.debug(f"FAIL: create_a_bucket({zone_id}, {key}, download) {e}")
        logger.exception(e)
        raise

    system_test.rsleep()

    try:
        logger.debug(f"@change_secret: {zone_id}")
        zone = change_secret(system_test, lc, zone_id)
        logger.debug(f"@updated: {zone}")
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: change_secret({zone_id}) {e}", flush=True)
        logger.debug(f"FAIL: change_secret({zone_id}) {e}")
        logger.exception(e)
        raise

    #(zone, csrf_token) = get_zone(lc, zone_id)
    #logger.debug(f"@zone: {zone}")

#    zone_id = try_mangle_a_zone(lc, zone_id)
#    logger.debug(f"@mangled: {zone_id}")

#    zone_id = create_forged_zone(system_test, lc, user)
#    logger.debug(f"@created: {zone_id}")

#    try_change_secret():
#    try_create_a_bucket():


def test_create_a_zone(system_test):
    user = system_test.user

    lc = system_test.lent_client()

    try:
        logger.debug(f"@create_new_zone: start")
        zone_id = create_new_zone(system_test, lc, user)
        logger.debug(f"@created: {zone_id}")
    except Exception as e:
        print(f"{format_rfc3339_z(time.time())} FAIL: create_new_zone({user}) {e}", flush=True)
        logger.debug(f"FAIL: create_new_zone({user}) {e}")
        logger.exception(e)
        raise
