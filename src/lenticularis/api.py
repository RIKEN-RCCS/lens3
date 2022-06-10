"""An object used in Adm Web-API"""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

from lenticularis.settingapi import Admin_Api
from lenticularis.settingapi import rephrase_exception_message
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import check_pool_naming
from lenticularis.poolutil import check_bucket_naming
from lenticularis.utility import get_ip_addresses
from lenticularis.utility import logger


class Api():

    def __init__(self, adm_conf):
        self.pool_adm = Admin_Api(adm_conf)
        trusted_proxies = adm_conf["webui"]["trusted_proxies"]
        self.trusted_proxies = set([addr for h in trusted_proxies
                                    for addr in get_ip_addresses(h)])
        return

    def return_user_template_ui(self, traceid, user_id):
        try:
            t = self.pool_adm.return_user_template(user_id)
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

    def make_pool_ui(self, traceid, user_id, pooldesc0):
        try:
            triple = self.pool_adm.make_pool_ui(traceid, user_id, pooldesc0)
            return triple
        except Api_Error as e:
            return (e.code, f"{e}", [])
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error((f"make_pool failed: user={user_id};"
                          f" exception=({m}); pool=({pooldesc0})"),
                         exc_info=True)
            return (500, m, None)
        pass

    def delete_pool_ui(self, traceid, user_id, pool_id):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool={pool_id}", [])
            self.pool_adm.delete_pool_ui(traceid, user_id, pool_id)
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

    def list_pools_ui(self, traceid, user_id, pool_id):
        try:
            if pool_id is None:
                pass
            elif not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", [])
            triple = self.pool_adm.list_pools_ui(traceid, user_id, pool_id)
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

    def make_bucket_ui(self, traceid, user_id, pool_id, body):
        try:
            if not check_pool_naming(pool_id):
                return (403, f"Bad pool-id={pool_id}", [])
            d = body.get("bucket")
            bucket = d.get("name")
            policy = d.get("bkt_policy")
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
            triple = self.pool_adm.make_bucket_ui(traceid, user_id, pool_id,
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

    def delete_bucket_ui(self, traceid, user_id, pool_id, bucket):
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
            triple = self.pool_adm.delete_bucket_ui(traceid, user_id, pool_id, bucket)
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

    def make_secret_ui(self, traceid, user_id, pool_id, body):
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
            triple = self.pool_adm.make_secret_ui(traceid, user_id, pool_id, rw)
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

    def delete_secret_ui(self, traceid, user_id, pool_id, access_key):
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
            triple = self.pool_adm.delete_secret_ui(traceid, user_id, pool_id,
                                                    access_key)
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
