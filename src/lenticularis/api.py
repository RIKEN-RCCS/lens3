# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import base64
from lenticularis.pooladm import ZoneAdm
from lenticularis.pooladm import check_pool_owner
from lenticularis.table import get_tables
from lenticularis.utility import get_ip_address
from lenticularis.utility import logger
from lenticularis.utility import random_str
import time


class Api():
    def __init__(self, adm_conf):

        self.zone_adm = ZoneAdm(adm_conf)
        trusted_proxies = adm_conf["webui"]["trusted_proxies"]
        self.trusted_proxies = set([addr for h in trusted_proxies
                                       for addr in get_ip_address(h)])
        logger.debug(f"@@@ self.trusted_proxies = {self.trusted_proxies}")

    def api_get_template(self, traceid, user_id):
        try:
            return ([self.zone_adm.generate_template(user_id)], None)
        except Exception as e:
            logger.exception(e)
            return ([], f"{e}")

    def api_list_pools(self, traceid, user_id, pool_id):
        logger.debug(f"@@@ {user_id} {pool_id}")
        try:
            (zone_list, _) = self.zone_adm.fetch_zone_list(user_id,
                             decrypt=True, include_atime=True, include_userinfo=True,
                             zone_id=pool_id)
            logger.debug(f"@@@ zone_list: {zone_list}")
            return (zone_list, None)
        except Exception as e:
            logger.exception(e)
            return ([], f"{e}")

    def api_create_pool(self, traceid, user_id, pool_id, zone):
        try:
            assert user_id is not None
            check_pool_owner(user_id, pool_id, zone)
            zone = self.zone_adm.create_pool(traceid, user_id, pool_id, zone, decrypt=True)
        except Exception as e:
            logger.exception(e)
            return (None, f"{e}")
        return ([zone], None)

    def api_update_pool(self, traceid, user_id, pool_id, zone):
        try:
            assert user_id is not None
            check_pool_owner(user_id, pool_id, zone)
            zone = self.zone_adm.update_pool(traceid, user_id, pool_id, zone, decrypt=True)
        except Exception as e:
            logger.exception(e)
            return (None, f"{e}")
        return ([zone], None)

    def api_update_buckets(self, traceid, user_id, pool_id, zone):
        try:
            assert user_id is not None
            check_pool_owner(user_id, pool_id, zone)
            zone = self.zone_adm.update_buckets(traceid, user_id, pool_id, zone, decrypt=True)
        except Exception as e:
            logger.exception(e)
            return (None, f"{e}")
        return ([zone], None)

    def api_change_secret(self, traceid, user_id, pool_id, zone):
        try:
            assert user_id is not None
            check_pool_owner(user_id, pool_id, zone)
            zone = self.zone_adm.change_secret(traceid, user_id, pool_id, zone, decrypt=True)
        except Exception as e:
            logger.exception(e)
            return (None, f"{e}")
        return ([zone], None)

    ##def _api_upsert_(self, how, traceid, user_id, pool_id, zone):
    ##    if not user_id:
    ##        logger.debug("@@@ user is required")
    ##        raise Exception(f"user is required")
    ##    if zone.get("owner_uid", user_id) != user_id:
    ##        logger.debug(f"@@@ user mismatch: {zone.get('owner_uid')} {user_id}")
    ##        raise Exception(f"user mismatch")
    ##    logger.debug(f"@@@ user = {user_id}")
    ##    try:
    ##        zone = self.zone_adm.upsert_zone(how, traceid, user_id, pool_id, zone, decrypt=True)
    ##    except Exception as e:
    ##        logger.debug(f"@@@ FAILED: {e}")
    ##        logger.exception(e)
    ##        return (None, f"{e}")
    ##    logger.debug("@@@ DONE")
    ##    return ([zone], None)

    def api_delete(self, traceid, user_id, pool_id):
        try:
            self.zone_adm.delete_zone(traceid, user_id, pool_id)
        except Exception as e:
            logger.debug(f"@@@ FAILED: {e}")
            logger.exception(e)
            return f"{e}"
        logger.debug("@@@ DONE")
        return None

    def api_check_user(self, user_id):
        return self.zone_adm.check_user(user_id)
