"""Adm Web-API.  An object for Adm."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import base64
import sys
from lenticularis.pooladmin import Pool_Admin
from lenticularis.pooladmin import rephrase_exception_message
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import check_pool_naming
from lenticularis.poolutil import check_bucket_naming
from lenticularis.table import get_tables
from lenticularis.utility import get_ip_address
from lenticularis.utility import logger
from lenticularis.utility import random_str
import time


class Api():

    def __init__(self, adm_conf):
        self.zone_adm = Pool_Admin(adm_conf)
        trusted_proxies = adm_conf["webui"]["trusted_proxies"]
        self.trusted_proxies = set([addr for h in trusted_proxies
                                       for addr in get_ip_address(h)])
        logger.debug(f"@@@ self.trusted_proxies = {self.trusted_proxies}")
        return

    def api_get_template(self, traceid, user_id):
        try:
            t = self.zone_adm.return_user_template(user_id)
            return (200, None, {"pool_list": [t]})
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"get_template failed: user={user_id};"
                          f" exception=({m})"),
                         exc_info=True)
            return (500, m, [])
        pass

    # POOLS.

    def api_make_pool(self, traceid, user_id, pooldesc0):
        try:
            pooldesc1 = self.zone_adm.make_pool(traceid, user_id, pooldesc0)
            return (200, None, {"pool_list": [pooldesc1]})
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_pool failed: user={user_id};"
                          f" exception=({m}); pool=({pooldesc0})"),
                         exc_info=True)
            return (500, m, None)
        pass

    def api_delete_pool(self, traceid, user_id, pool_id):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool={pool_id}", [])
            self.zone_adm.delete_pool(traceid, user_id, pool_id)
            return (200, None, [])
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"delete_pool failed: user={user_id},"
                          f" pool={pool_id}; exception=({m})"),
                         exc_info=True)
            return (500, m, [])
        pass

    def api_list_pools(self, traceid, user_id, pool_id):
        try:
            if pool_id is None:
                pass
            elif not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", [])
            ##(zone_list, _) = self.zone_adm.fetch_zone_list(
            ##user_id, decrypt=True, include_atime=True, include_userinfo=True,
            ##zone_id=pool_id)
            triple = self.zone_adm.list_pools(traceid, user_id, pool_id)
            return triple
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"list_pools failed: user={user_id}, pool={pool_id};"
                          f" exception=({m})"),
                         exc_info=True)
            return (500, m, [])
        pass

    # BUCKETS.

    def api_make_bucket(self, traceid, user_id, pool_id, body):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", [])
            d = body.get("bucket")
            bucket = d.get("name")
            policy = d.get("policy")
            if not check_bucket_naming(bucket):
                return (403, f"Bad bucket name={bucket}", [])
            if not policy in ["none", "public", "upload", "download"]:
                return (403, f"Bad bucket policy={policy}", [])
            # assert name == bucket
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Adding a bucket to pool={pool_id}"
                         f": name={bucket}, policy={policy}")
            triple = self.zone_adm.make_bucket(traceid, user_id, pool_id,
                                               bucket, policy)
            return triple
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_bucket failed: user={user_id},"
                          f" pool={pool_id}, name={bucket},"
                          f" policy={policy}; exception=({m})"),
                         exc_info=True)
            return (500, m, None)
        pass

    def api_delete_bucket(self, traceid, user_id, pool_id, bucket):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool={pool_id}", [])
            if not check_bucket_naming(bucket):
                return (403, f"Bad bucket name={bucket}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Deleting a bucket: {bucket}")
            triple = self.zone_adm.delete_bucket(traceid, user_id, pool_id, bucket)
            return triple
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"delete_bucket failed: user={user_id}"
                          f" pool={pool_id} bucket={bucket};"
                          f" exception=({m})"),
                         exc_info=True)
            return (500, m, None)
        pass

    # SECRETS.

    def api_make_secret(self, traceid, user_id, pool_id, body):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", [])
            rw = body.get("key_policy")
            if not rw in ["readwrite", "readonly", "writeonly"]:
                return (403, f"Bad access policy={rw}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Adding a new secret: {rw}")
            triple = self.zone_adm.make_secret(traceid, user_id, pool_id, rw)
            return triple
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_secret failed: user={user_id} pool={pool_id}"
                          f" policy={rw}; exception=({m})"),
                         exc_info=True)
            return (500, m, None)
        pass

    def api_delete_secret(self, traceid, user_id, pool_id, access_key):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", [])
            if not check_pool_naming(access_key):
                return (403, f"Bad access-key={access_key}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            return (400, m, None)
        try:
            logger.debug(f"Deleting a secret: {access_key}")
            triple = self.zone_adm.delete_secret(traceid, user_id, pool_id, access_key)
            return triple
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"delete_secret failed: user={user_id}"
                          f" pool={pool_id} access-key={access_key};"
                          f" exception=({m})"),
                         exc_info=True)
            return (500, m, None)
        pass

    pass
