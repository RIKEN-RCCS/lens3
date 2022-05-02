"""Pool mangement."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import string
import sys
import time
from lenticularis.lockdb import LockDB
from lenticularis.table import get_tables, zone_to_route
from lenticularis.utility import decrypt_secret, encrypt_secret
from lenticularis.utility import gen_access_key_id, gen_secret_access_key
from lenticularis.utility import logger
from lenticularis.utility import pick_one, check_permission, get_mux_addr
from lenticularis.utility import check_mux_access, host_port
from lenticularis.utility import uniq_d
from lenticularis.zoneutil import check_zone_schema, check_pool_dict_is_sound
from lenticularis.zoneutil import merge_zone, check_conflict
from lenticularis.zoneutil import compare_access_keys, compare_buckets_directory
from lenticularis.zoneutil import compare_buckets, check_policy
from lenticularis.utility import tracing


def _check_bucket_fmt(bucket):
                bucket_keys = set(bucket.keys())
                return bucket_keys == {"key", "policy"}

def _check_access_key_fmt(access_key):
                access_key_keys = set(access_key.keys())
                return ({"accessKeyID"}.issubset(access_key_keys) and
                        access_key_keys.issubset({"accessKeyID", "secretAccessKey", "policyName"}))

def _check_create_bucket_keys(zone):
            """ zone ::= {"buckets": [{"key": bucket_name,
                                       "policy": policy}]}
            """
            if zone.keys() != {"buckets"}:
                raise Exception(f"update_buckets: invalid key set: {set(zone.keys())}")
            if not all(_check_bucket_fmt(bucket) for bucket in zone["buckets"]):
                raise Exception(f"update_buckets: invalid bucket: {zone}")

def _check_change_secret_keys(zone):
            """ zone ::= {"accessKeys": [accessKey]}
                accessKey ::= {"accessKeyID": access_key_id,
                               "secretAccessKey": secret (optional),
                               "policyName": policy (optional) }
            """
            if zone.keys() != {"accessKeys"}:
                raise Exception(f"update_secret_keys: invalid key set: {set(zone.keys())}")
            if not all(_check_access_key_fmt(access_key) for access_key in zone["accessKeys"]):
                raise Exception(f"change_secret_key: invalid accessKey: {zone}")

def _check_zone_keys(zone):
            given_keys = set(zone.keys())
            mandatory_keys = {"group", "bucketsDir", "buckets", "accessKeys",
                              "directHostnames", "expDate", "status"}
            allowed_keys = mandatory_keys.union({"user", "rootSecret", "permission"})
            if not mandatory_keys.issubset(given_keys):
                raise Exception(f"upsert_zone: invalid key set: missing {mandatory_keys - given_keys}")
            if not given_keys.issubset(allowed_keys):
                raise Exception(f"upsert_zone: invalid key set {given_keys - allowed_keys}")

def _check_zone_owner(user_id, zone_id, zone):
            logger.debug(f"+++")
            if zone["user"] != user_id:
                existing_user = zone["user"]
                logger.error(f"user_id mismatch: {user_id} != {existing_user} in {zone_id}")
                raise Exception(f"user_id mismatch: {user_id} != {existing_user} in {zone_id}")

def _gen_unique_key(key_generator, allkeys):
            while True:
                key = key_generator()
                if key not in allkeys:
                    break
            allkeys.add(key)
            return key

def _encrypt_or_generate(dic, key):
            val = dic.get(key)
            dic[key] = encrypt_secret(val if val else gen_secret_access_key())

def _check_bucket_names(zone):
            for bucket in zone.get("buckets", []):
                _check_bucket_name(zone, bucket)

def _check_bucket_name(zone, bucket):
            name = bucket["key"]
            if len(name) < 3:
                raise Exception(f"too short bucket name: {name}")
            if len(name) > 63:
                raise Exception(f"too long bucket name: {name}")

            logger.debug("@@@ CHECK_BUCKET_NAME: FIXME XXX ")

            #    if not name ~ "[a-z0-9][-\.a-z0-9][a-z0-9]":
            #        raise Exception(f"")
            #    if strstr(name, ".."):
            #        raise Exception(f"")
            #    # buckets: 3..63, [a-z0-9][-\.a-z0-9][a-z0-9]
            #    #          no .. , not ip-address form

            check_policy(bucket["policy"])  # {"none", "upload", "download", "public"}

def _check_direct_hostname_flat(host_label):
            logger.error(f"@@@ check_direct_hostname_flat")
            # logger.error(f"@@@ check_direct_hostname_flat XXX FIXME")
            if '.' in host_label:
                raise Exception(f"invalid direct hostname: {host_label}: only one level label is allowed")
            _check_rfc1035_label(host_label)
            _check_rfc1122_hostname(host_label)

def _check_rfc1035_label(label):
            if len(label) > 63:
                raise Exception(f"{label}: too long")
            if len(label) < 1:
                raise Exception(f"{label}: too short")

def _check_rfc1122_hostname(label):
            alnum = string.ascii_lowercase + string.digits
            if not all(c in alnum + '-' for c in label):
                raise Exception(f"{label}: contains invalid char(s)")
            if not label[0] in alnum:
                raise Exception(f"{label}: must start with a letter or a digit")
            if not label[-1] in alnum:
                raise Exception(f"{label}: must end with a letter or a digit")

def _is_subdomain(host_fqdn, domain):
                return host_fqdn.endswith("." + domain)

def _strip_domain(host_fqdn, domain):
                domain_len = 1 + len(domain)
                return host_fqdn[:-domain_len]


class ZoneAdm():

    zone_table_lock_pfx = "zk:"

    def __init__(self, adm_conf):
        self.adm_conf = adm_conf

        controller_param = adm_conf["lenticularis"]["controller"]
        self.timeout = int(controller_param["max_lock_duration"])

        multiplexer_param = adm_conf["lenticularis"]["multiplexer"]
        self.facade_hostname = multiplexer_param["facade_hostname"]

        system_settings_param = adm_conf["lenticularis"]["system_settings"]
        self.system_settings_param = system_settings_param
        self.direct_hostname_domains = [h.lower() for h in system_settings_param["direct_hostname_domains"]]
        self.reserved_hostnames = [h.lower() for h in self.system_settings_param["reserved_hostnames"]]
        self.max_zone_per_user = int(system_settings_param["max_zone_per_user"])
        self.max_direct_hostnames_per_user = int(system_settings_param["max_direct_hostnames_per_user"])
        self.decoy_connection_timeout = int(system_settings_param["decoy_connection_timeout"])

        self.tables = get_tables(adm_conf)

    ### COMMON ENTRY POINTS ###

    def refresh_multiplexer_list(self):  # private use
        mux_list = self.tables.processes.get_mux_list(None)
        # logger.debug(f"@@@ mux_list => {mux_list}")
        multiplexers = [get_mux_addr(v["mux_conf"]) for (e, v) in mux_list]
        multiplexers = sorted(list(set(multiplexers)))
        logger.debug(f"@@@ self.tables.processes.get_mux_list() => {multiplexers}")
        logger.debug(f"@@@ SELF.MULTIPLEXERS = {multiplexers}")
        return multiplexers

    def fix_affected_zone(self, traceid):  # ADMIN
        allow_deny_rules = self.tables.zones.get_allow_deny_rules()
        fixed = []
        for z_id in self.tables.zones.get_zoneID_list(None):
            logger.debug(f"@@@ z_id = {z_id}")
            zone = self.tables.zones.get_zone(z_id)
            user_id = zone["user"]

            ui = self.fetch_unixUserInfo(user_id)
            if ui:
                groups = ui.get("groups", [])
                group = zone.get("group")
            else:
                groups = []
                group = None

            permission = "allowed" if (ui
                and any(grp for grp in groups if grp == group)
                and check_permission(user_id, allow_deny_rules) == "allowed"
                ) else "denied"

            if zone["permission"] != "denied" and not permission:
                disable_zone(traceid, user_id, z_id)
                fixed.append(z_id)
                logger.debug(f"permission dropped: {z_id} {user_id} {zone['permission']} => {permission}")
        return fixed

    def store_allow_deny_rules(self, allow_deny_rules):  # ADMIN
        self.tables.zones.ins_allow_deny_rules(allow_deny_rules)

    def fetch_allow_deny_rules(self):  # ADMIN
        return self.tables.zones.get_allow_deny_rules()

    def list_unixUsers(self):  # ADMIN
        return list(self.tables.zones.get_unixUsers_list())

    def store_unixUserInfo(self, user_id, uinfo):  # ADMIN
        self.tables.zones.ins_unixUserInfo(user_id, uinfo)

    def fetch_unixUserInfo(self, user_id):  # ADMIN
        return self.tables.zones.get_unixUserInfo(user_id)

    def check_user(self, user_id):  # API
        return self.fetch_unixUserInfo(user_id) is not None

    def delete_unixUserInfo(self, user_id):  # ADMIN
        self.tables.zones.del_unixUserInfo(user_id)


    def upsert_zone(self, how, traceid, user_id, zone_id, zone, include_atime=False,
                    decrypt=False, initialize=True):  # ADMIN, API
        """
         how ::= create_zone | update_zone | update_buckets | change_secret_key  -- (api.py)
                 | None  -- (admin.py)
        """

        logger.debug("+++"
                            f" traceid: {traceid}"
                            f" user_id: {user_id}"
                            f" zone_id: {zone_id}"
                            f" zone: <omitted>"
                            f" include_atime: {include_atime}"
                            f" how: {how}"
                            f" decrypt: {decrypt}"
                            )
        return self._upsert_zone_main_(how, traceid, user_id, zone_id, zone, include_atime, decrypt, initialize)


    def _upsert_zone_main_(self, how, traceid, user_id, zone_id, zone, include_atime, decrypt, initialize):

            if not user_id:
                logger.errror("INTERNAL ERROR: user id is None")
                raise Exception("INTERNAL ERROR: user id is None")

            if how == "update_buckets":
                _check_create_bucket_keys(zone)
                return self._do_update_zone(traceid, user_id, zone_id, zone, how, decrypt=decrypt) # let update_zone initialize (default)

            if how == "change_secret_key":
                _check_change_secret_keys(zone)
                return self._do_update_zone(traceid, user_id, zone_id, zone, how, decrypt=decrypt) # let update_zone initialize (default)

            # else: how in {"create_zone", "update_zone", None}

            if how == "create_zone" and zone_id is not None:
                logger.error("INTERNAL ERROR: zone_id should be None when creating a zone.")
                raise Exception("INTERNAL ERROR: zone_id should be None when creating a zone.")

            atime_from_arg = zone.pop("atime", None) if include_atime else None
            _check_zone_keys(zone)

            logger.debug("@@@"
                                f" user_id: {user_id}"
                                f" zone_id: {zone_id}"
                                f" zone: <omitted>"
                                f" atime_from_arg: {atime_from_arg}"
                                f" decrypt: {decrypt}"
                                )

            return self._do_update_zone(traceid, user_id, zone_id, zone, how,
                                    atime_from_arg=atime_from_arg,
                                    initialize=initialize, # owerride behaviour
                                    decrypt=decrypt)


    def delete_zone(self, traceid, user_id, zoneID):  # ADMIN, API
        logger.debug(f"+++ {user_id} {zoneID}")
        zone = {"permission": "denied"}
        how = "delete_zone"
        return self._do_update_zone(traceid, user_id, zoneID, zone, how)

    def disable_zone(self, traceid, user_id, zoneID):  # ADMIN, private
        logger.debug(f"+++ {user_id} {zoneID}")
        zone = {}
        how = "disable_zone"
        return self._do_update_zone(traceid, user_id, zoneID, zone, how, permission="denied")

    def enable_zone(self, traceid, user_id, zoneID):  # ADMIN
        logger.debug(f"+++ {user_id} {zoneID}")
        zone = {}
        how = "enable_zone"
        return self._do_update_zone(traceid, user_id, zoneID, zone, how, permission="allowed")

    def flush_zone_table(self, everything=False):  # ADMIN
        self.tables.zones.clear_all(everything=everything)

    def reset_database(self, everything=False):  # ADMIN
        self.tables.zones.clear_all(everything=everything)
        self.tables.processes.clear_all(everything=everything)
        self.tables.routes.clear_all(everything=everything)

    def print_database(self):  # ADMIN
        self.tables.zones.printall()
        self.tables.processes.printall()
        self.tables.routes.printall()

    def fetch_multiplexer_list(self):  # ADMIN
        return self.tables.processes.get_mux_list(None)

    def fetch_process_list(self):  # ADMIN
        return self.tables.processes.get_minio_address_list(None)

    def delete_process(self, processID):  # ADMIN
        return self.tables.processes.del_minio_address(processID)

    def flush_process_table(self, everything=False):  # ADMIN
        self.tables.processes.clear_all(everything=everything)

    def check_mux_access_for_zone(self, traceid, zoneID, force, access_key_id=None):  # ADMIN
        """Tries to access a multiplexer of the zone, if minio of the zone is
        running. force=True to send a decoy regardless minio is
        running or not. if there are no zone, do nothing.
        """

        logger.debug(f"zone={zoneID}, access_key={access_key_id}, force={force}")

        minioAddr = self.tables.processes.get_minio_address(zoneID)
        multiplexers = self.refresh_multiplexer_list()
        logger.debug(f"@@@ MULTIPLEXERS = {multiplexers}")
        if minioAddr:
            ## SEND PACKET TO MULTPLEXER OF THE MINIO, NOT MINIO ITSELF.
            mux_name = minioAddr.get("muxAddr")
            logger.debug(f"@@@ MUX_NAME = {mux_name}")
            # host = minioAddr.get("minioAddr")  ### DO NOT SEND
            multiplexer = next(((host, port) for (host, port) in multiplexers if host == mux_name), None)
            if multiplexer is None:
                multiplexer = pick_one(multiplexers)
            logger.debug(f"@@@ MUX OF MINIO = {multiplexer}")
        elif force:
            multiplexer = pick_one(multiplexers)
            logger.debug(f"@@@ PICK ONE = {multiplexer}")
        else:
            ## Done if MinIO is not running.
            logger.debug(f"No check, as no MinIO instance is running.")
            return ""
        logger.debug(f"@@@ MULTIPLEXER = {multiplexer}")
        assert multiplexer is not None
        ## multiplexer is a pair of (host, port).
        host = host_port(multiplexer[0], multiplexer[1])
        if access_key_id is None:
            zone = self.tables.zones.get_zone(zoneID)
            if zone is None:
                ## Done if neither access-key nor zone.
                logger.debug(f"No check, as neither access-key nor zone.")
                return ""
            access_key_id = zone["accessKeys"][0]["accessKeyID"]  # any key is suffice.
        facade_hostname = self.facade_hostname
        status = check_mux_access(traceid,
                                   host,
                                   access_key_id,
                                   facade_hostname, self.decoy_connection_timeout)
        logger.debug(f"@@@ SEND DECOY STATUS {status}")
        return status

    def fetch_route_list(self):  # ADMIN
        return self.tables.routes.get_route_list()

    def flush_routing_table(self, everything=False):  # ADMIN
        self.tables.routes.clear_all(everything=everything)


    def _do_update_zone(self, traceid, user_id, zoneID, zone, how,
                    permission=None,
                    atime_from_arg=None,
                    initialize=True,
                    decrypt=False):  # private use
        """
        permission           -- independent from "how"
        atime_from_arg       -- ditto.   <= include_atime
        initialize           -- ditto.
        decrypt              -- ditto.

        must_exist == how not in {None, "create_zone"}
        delete_zone = how == "delete_zone"
        create_bucket = how == "update_buckets"
        change_secret = how == "change_secret_key"

        how :   create_zone {
                    assert(zone_id is None)
                    permission=None (default)
                }
            |   None {
                    permission=None (default)
                }
            |   update_zone {
                    permission=None (default)
                }
            |   update_buckets {
                    permission=None (default)
                }
            |   change_secret_key {
                    permission=None (default)
                }
            |   delete_zone {
                    permission=None (default)
                }
            |   disable_zone {
                    permission="denied"
                }
            |   enable_zone {
                    permission="allowed"
                }
            ;

        """

        logger.debug("+++"
                            f" user_id: {user_id} zoneID: {zoneID} zone: <omitted>"
                            f" permission: {permission}"
                            f" atime_from_arg: {atime_from_arg}"
                            f" decrypt: {decrypt}")

        """
            Update or insert zone.

            traceid: debug use

            user_id: user ID of zone to be upserted.
                     if user_id is None, the value from zone["user"] is used.
                     otherwize zone["user"] should match user_id if it exists.

            zone_ID: zoneID to be updated.
                     if zoneID is None, new zone is created.
                     On the latter case, new zoneID is generated and
                     set to zone["zoneID"]
                     (if zoneID is not None and the zone does not exist, its error)

            zone: zone values to be created or updated.
                  see below.

            permission=None,       if supplied, set zone["permission"] to the given value,
                                   otherwize calculate permission using allow-deny-rules.
            atime_from_arg=None,   if supplied, set atime on database to the given value.

            Dictionary zone consists of following items:
              zoneID:           not on db
              rootSecret:
              user:
            * group:
            * bucketsDir:
            * buckets:
            * accessKeys:
            * directHostnames:
            * expDate:
            * status:
              permission:
              atime:            not on db

            (* denotes the item is mandatory)

            When creating buckets, supply only "buckets" item:
            * buckets:

            When changing access keys, supply only "accessKeys" item:
            * accessKeys:


            "buckets" is a list of buckets.
            buckets consists of following items:
            * key:
            * policy:


            "accessKeys" is a list of accessKeys.
            accessKey consists of following items:
            * accessKeyID:
            * secretAccessKey:
            * policyName:

           When changing Secret Access Keys, "secretAccesKey" and/or "policy" may be missing.
           NOT IMPLEMENTED: When changing policy, "secretAccesKey" may be missing.
           When creating new access key, "accessKeyID" and/or "secretAccesKey" may be missing.

        we must validate zone before inserting into dictionary.
        values may be missing in user supplied zone are,
            "rootSecret", "user", "permission", "accessKeyID", and "secretAccessKey".
        "user" is set in early step.
        "rootSecret" and "secretAccessKey" may generated and set at any time.
        "permission" may be set any time.


        "accessKeyID" must generated and set while entire database is locked.


        ※ when creating new zone, "zoneID" must generated while entire database is locked.
          this means we cannot include "zoneID" in the error report (on error).

        SPECIAL CASE 1:
            when deleing zone, following dict is used:
            {"permission": "denied"}

        SPECIAL CASE 2:
            when changing permission, following dict is used:
            {}

        """

        if zoneID is None:  # do update without locking zone
            return self.update_zone_with_lockdb(traceid, user_id, zoneID, zone, how, permission, atime_from_arg, initialize, decrypt)

        lock = LockDB(self.tables.zones)
        key = f"{self.zone_table_lock_pfx}{zoneID}"
        lock_status = False
        try:
            lock.lock(key, self.timeout)
            # logger.debug(f"@@@ case 2: LOCK SUCCEEDED: {zoneID}")
            return self.update_zone_with_lockdb(traceid, user_id, zoneID, zone, how, permission, atime_from_arg, initialize, decrypt)
        finally:
            # logger.debug(f"@@@ UNLOCK {zoneID}")
            lock.unlock()


    def _delete_existing_zone(self, existing):
            logger.debug(f"+++")
            logger.debug(f"@@@ del_mode {zone_id}")
            self.tables.zones.del_mode(zone_id)
            logger.debug(f"@@@ del_atime {zone_id}")
            self.tables.zones.del_atime(zone_id)
            logger.debug(f"@@@ DELETE PTR {zone_id} {[e.get('accessKeyID') for e in existing.get('accessKeys')]}")
            self.tables.zones.del_ptr(zone_id, existing)
            logger.debug("@@@ del_zone")
            self.tables.zones.del_zone(zone_id)
            logger.debug("@@@ DONE")

    def _check_user_group(self, user_id, zone):
            ui = self.fetch_unixUserInfo(user_id)
            groups = ui.get("groups") if ui else []
            group = zone.get("group") if zone else None
            if group not in groups:
                raise Exception(f"invalid group: {group}")

    def _check_direct_hostname(self, host_fqdn):
            host_fqdn = host_fqdn.lower()
            fns = {"flat": _check_direct_hostname_flat}

            criteria = self.system_settings_param["direct_hostname_validator"]
            logger.debug(f"@@@ {self.system_settings_param}")
            logger.debug(f"@@@ criteria = {criteria}")

            if any(host_fqdn == d for d in self.reserved_hostnames):
                raise Exception(f"{host_fqdn}: the name is reserved'")

            try:
                domain = next(d for d in self.direct_hostname_domains if _is_subdomain(host_fqdn, d))
            except StopIteration:
                raise Exception(f"{host_fqdn}: direct hostname should "
                                f"ends with one of '{self.direct_hostname_domains}'")

            fn = fns.get(criteria)
            if fn is None:
                raise Exception(f"system configulation error: direct_hostname_validator '{criteria}' is not defined")
            fn(_strip_domain(host_fqdn, domain))


    def update_zone_with_lockdb(self, traceid, user_id, zone_id, zone, how,
                                permission=None,
                                atime_from_arg=None,
                                initialize=True,
                                decrypt=False):
            logger.debug(f"@@@ user_id = {user_id}")
            logger.debug(f"@@@ zone_id = {zone_id}")

            existing = self.tables.zones.get_zone(zone_id) if zone_id else None

            must_exist = how not in {None, "create_zone"}
            if must_exist and not existing:
                logger.error(f"no such zone: {zone_id}")
                raise Exception(f"no such zone: {zone_id}")

            if existing:
                _check_zone_owner(user_id, zone_id, existing)

            delete_zone = how == "delete_zone"

            if delete_zone:
                (need_initialize, need_uniquify) = (False, False)
            else:
                (need_initialize, need_uniquify) = self._prepare_zone(
                 user_id, zone_id, existing, zone, permission, how)

            # if explicitly ordered not to initialize,
            # set need_initialize to be False
            need_initialize = need_initialize and initialize

            omode = None
            if not need_initialize:
                omode = self.fetch_current_mode(zone_id)

            if zone_id:
                self.set_current_mode(zone_id, "suspended")

            ### XXX can we merge following two tries into one?

            try:
                # We will restart minio always, though there
                # may be no changes have been made to existing zone.
                # If explicitly ordered not to initialize, do not try
                # to stop minio (regardless it is running or not).
                if existing and initialize:
                    self._clear_route(zone_id, existing)
                    logger.debug(f"@@@ SEND DECOY zone_id = {zone_id}")
                    ## Stop MinIO.
                    status = self.check_mux_access_for_zone(traceid, zone_id, force=False)
                    logger.debug(f"@@@ SEND DECOY STATUS {status}")
                    minioAddr = self.tables.processes.get_minio_address(zone_id)
                    if minioAddr is not None:
                        logger.debug(f"@@@ COULD NOT STOP MINIO")
                        raise Exception("could not stop minio")
            except Exception as e:
                logger.debug(f"@@@ ignore exception {e}")
                pass

            if delete_zone:
                pass
            else:
                need_conflict_check = existing is not None
                zone_id = self._lockdb_and_store_zone(user_id, zone_id, zone, need_conflict_check, need_uniquify)
                # NOTE: delete ptr here, if user allowed to modify access keys
                #    in the future lenticularis specification.

            try:
                if delete_zone:
                    self.set_current_mode(zone_id, "deprecated")
                elif need_initialize:
                    self.set_current_mode(zone_id, "initial")
                    self._send_decoy_with_zoneid_ptr(traceid, zone_id)  # trigger initialize minio
                else:
                    pass
            except Exception as e:
                logger.debug(f"@@@ ignore exception {e}")
                pass

            if delete_zone:
                self._delete_existing_zone(existing)
            else:
                logger.debug(f"@@@ INSERT PTR {zone_id} {[e.get('accessKeyID') for e in zone.get('accessKeys')]}")
                if atime_from_arg:
                    logger.debug(f"@@@ INSERT PTR {zone_id} {[e.get('accessKeyID') for e in zone.get('accessKeys')]}")
                    self.tables.zones.set_atime(zone_id, atime_from_arg)
                self.tables.zones.ins_ptr(zone_id, zone)

            if not delete_zone and omode:
                self.set_current_mode(zone_id, omode)
                mode = omode
            elif not initialize:
                # intentionally leave mode be unset
                pass
            else:
                mode = self.fetch_current_mode(zone_id)

            if delete_zone:
                if mode is not None:
                    logger.error(f"delete zone: error: mode is not None: {mode}")
                    raise Exception(f"delete zone: error: mode is not None: {mode}")
            elif not initialize:
                pass
            elif mode not in {"ready"}:
                logger.error(f"initialize: error: mode is not ready: {mode}")
                raise Exception(f"initialize: error: mode is not ready: {mode}")
            else:
                pass

            zone["zoneID"] = zone_id
            logger.debug(f"@@@ decrypt = {decrypt}")
            if decrypt:
                self.decrypt_access_keys(zone)
            #logger.debug(f"@@@ zone = {zone}")
            return zone

    ### END update_zone_with_lockdb

    def _prepare_zone(self, user_id, zone_id, existing, zone, permission, how):
            logger.debug(f"+++")

            #logger.debug(f"@@@ zone = {zone}")
            #logger.debug(f"@@@ existing = {existing}")

            bucket_settings_modified = None

            create_bucket = how == "update_buckets"
            change_secret = how == "change_secret_key"
            if create_bucket:
                logger.debug(f"create bucket")
                if not existing:
                    raise Exception("INTERNAL ERROR: existing is None")

                new_buckets = zone.pop("buckets")
                if len(new_buckets) != 1:
                    raise Exception(f"too many/few buckets: {new_buckets}")
                new_bucket = new_buckets[0]

                logger.debug(f"@@@ new_bucket = {new_bucket}")
                bucket_name = new_bucket["key"]
                merge_zone(user_id, existing, zone)
                if zone["buckets"] is not None:
                    if any(bucket["key"] == bucket_name for bucket in zone.get("buckets", [])):
                        raise Exception(f"bucket {bucket_name} exists")
                    zone["buckets"].append(new_bucket)
                else:
                    zone["buckets"] = [new_bucket]
                bucket_settings_modified = True
                need_uniquify = self._regularize_pool_dict(user_id, existing, zone, permission)  # assert(permission is None)

            elif change_secret:
                logger.debug(f"change secret")
                if not existing:
                    raise Exception("INTERNAL ERROR: existing is None")
                new_keys = zone.pop("accessKeys")

                if len(new_keys) != 1:
                    raise Exception(f"too many/few accessKeys: {new_keys}")
                new_key = new_keys[0]

                logger.debug(f"@@@ new_key = {new_key}")
                merge_zone(user_id, existing, zone)
                access_key_id = new_key["accessKeyID"]
                access_keys = zone.get("accessKeys", [])
                logger.debug(f"@@@ access_keys = {access_keys}")
                if not any(access_key["accessKeyID"] == access_key_id for access_key in access_keys):
                    raise Exception(f"access key {access_key_id} does not exist")
                for access_key in access_keys:
                    if access_key["accessKeyID"] == new_key["accessKeyID"]:
                        access_key["secretAccessKey"] = ""  # let `regulate_zone` generate new Secret Access Key
                        break

#                        if new_key.get("secretAccessKey") is not None:
#                            a["secretAccessKey"] = new_key["secretAccessKey"]
#                        else:
#                            a["secretAccessKey"] = gen_secret_access_key()  # will be encrypted later XXX <<< regulate_zone will fill secretAccessKey.

                need_uniquify = regulate_zone(user_id, existing, zone, permission)  # assert(permission is None)

            else:
                logger.debug(f"upsert zone")
                merge_zone(user_id, existing, zone)

                need_uniquify = self._regularize_pool_dict(user_id, existing, zone, permission)

                r = compare_access_keys(existing, zone)
                if r != []:
                    raise Exception(f"Access Key may not be modified {r}")

                r = compare_buckets_directory(existing, zone)
                if r != []:
                    raise Exception(f"Buckets Directory may not be modified: {r}")

                r = compare_buckets(existing, zone)
                bucket_settings_modified = r != []
                logger.debug(f"@@@ bucket_settings_modified = {bucket_settings_modified}")

            #logger.debug(f"@@@ zone = {zone}")

            mode = None
            if zone_id:
                mode = self.fetch_current_mode(zone_id)
            need_initialize = (zone_id is None or  # subset of 'mode not in {ready}' below, but is here to clarify the logic.
                               existing is None or
                               bucket_settings_modified or
                               mode not in {"ready"} or
                               create_bucket or   # sync. with bucket_settings_modified
                               change_secret)

            return (need_initialize, need_uniquify)

    def _regularize_pool_dict(self, user_id, existing, zone, permission):
            logger.debug(f"+++")

            _encrypt_or_generate(zone, "rootSecret")

            if permission is None:  # how not in {"enable_zone", "disable_zone"}
                allow_deny_rules = self.tables.zones.get_allow_deny_rules()
                zone["permission"] = check_permission(user_id, allow_deny_rules)
            else:
                zone["permission"] = permission  # how in {"enable_zone" in "disable_zone"}

            #logger.debug(f"@@@ zone = {zone}")

            bucket_names = [bucket.get("key") for bucket in zone.get("buckets", [])]
            logger.debug(f"@@@ bucket_names = {bucket_names}")
            bucket_names = uniq_d(bucket_names)
            if bucket_names:
                logger.debug(f"@@@ bucket names are not unique: {bucket_names}")
                raise Exception(f"update_zone: bucket names are not unique: {bucket_names}")

            for bucket in zone.get("buckets", []):
                if not bucket.get("policy"):
                    bucket["policy"] = "none"
                # bucket name and policy will be checed in `check_zone_values`

            need_uniquify = False
            access_keys = zone.get("accessKeys", [])
            for accessKey in access_keys:
                if not accessKey.get("accessKeyID"):  # (unset) or ""
                    accessKey["accessKeyID"] = ""   # temporary value
                    need_uniquify = True   # accessKeyID is updated in uniquify_zone

                _encrypt_or_generate(accessKey, "secretAccessKey")

                if not accessKey.get("policyName"):  # (unset) or ""
                    accessKey["policyName"] = "readwrite"
                # policyName will be checked in `check_pool_dict_is_sound`

            logger.debug(f"@@@ CHECK_SCHEMA")
            check_zone_schema(zone, user_id)
            logger.debug(f"@@@ CHECK_SCHEMA END")
            check_pool_dict_is_sound(zone, user_id, self.adm_conf)
            self._check_zone_values(user_id, zone)

            directHostnames = zone["directHostnames"]
            logger.debug(f"@@@ directHostnames = {directHostnames}")
            zone["directHostnames"] = [e.lower() for e in directHostnames]

            return need_uniquify

    def _check_zone_values(self, user_id, zone):
            logger.debug(f"+++")
            num_hostnames_of_zone = len(zone.get("directHostnames"))

            logger.debug(f"@@@ num_hostnames_of_zone = {num_hostnames_of_zone}")

            if num_hostnames_of_zone > self.max_direct_hostnames_per_user:
                raise Exception(f"update_zone: too many direct hostnames (limit per zone exceeded)")

            maxExpDate = int(self.system_settings_param["allowed_maximum_zone_exp_date"])
            if int(zone["expDate"]) > maxExpDate:
                raise Exception(f"update_zone: expiration date is beyond the system limit")

            for h in zone.get("directHostnames", []):
                self._check_direct_hostname(h)

            self._check_user_group(user_id, zone)

            _check_bucket_names(zone)


    def _clear_route(self, zone_id, zone):
            logger.debug(f"+++")
            # we need to flush the routing table entry of zone_id before,
            # to make the controller checks minio_address_table and zone.

            route = zone_to_route(zone)
            logger.debug(f"@@@ {zone_id} {route}")

            self.tables.routes.del_route(route)

    def _lockdb_and_store_zone(self, user_id, zone_id, zone, need_conflict_check, need_uniquify):
            logger.debug(f"+++ {zone_id}")

            lock = LockDB(self.tables.zones)
            key = f"{self.zone_table_lock_pfx}"  # lock entire table
            lock_status = False
            try:
                logger.debug(f"lock")
                lock_status = lock.lock(key, self.timeout)
                if need_conflict_check or need_uniquify:
                    zone_id = self._uniquify_zone(user_id, zone_id, zone)
                #logger.debug(f"@@@ zone = {zone}")
                logger.debug(f"@@@ call ins_zone")
                self.tables.zones.ins_zone(zone_id, zone)  # encrypted!
                logger.debug(f"@@@ call set_atime")
                self.tables.zones.set_atime(zone_id, "0")
                logger.debug(f"@@@ done")
            finally:
                logger.debug(f"unlock")
                lock.unlock()
            logger.debug(f"--- {zone_id}")
            return zone_id

    def _get_all_keys(self, zone_id):
            allkeys = set()
            for z_id in self.tables.zones.get_zoneID_list(None):
                #logger.debug(f"@@@ z_id = {z_id}")
                if z_id == zone_id:
                    continue
                allkeys.add(z_id)
                z = self.tables.zones.get_zone(z_id)
                #logger.debug(f"@@@ z = {z}")
                if z is None:
                    continue
                #logger.debug(f"@@@ A allkeys = {allkeys}")
                zz = z.get("accessKeys", [])
                #logger.debug(f"@@@ B accessKeys = {type(zz)} {zz}")
                #for access_key in zz:
                    #logger.debug(f"@@@ C access_key = {type(access_key)}")
                    #logger.debug(f"@@@ C access_key = {access_key}")
                    #logger.debug(f"@@@ D access_key_id = {access_key['accessKeyID']}")
                kk = [access_key["accessKeyID"] for access_key in z.get("accessKeys", [])]
                #logger.debug(f"@@@ E kk = {kk}")

                allkeys = allkeys.union(set([access_key["accessKeyID"] for access_key in z.get("accessKeys", [])]))

                #logger.debug(f"@@@ F")
            #logger.debug(f"@@@ allkeys = {allkeys}")
            return allkeys

    def _uniquify_zone(self, user_id, zone_id, zone):
            logger.debug(f"+++")
            logger.debug(f"@@@ UNIQUIFY")
            reasons = []
            num_zones_of_user = 0

            logger.debug(f"@@@ get_allkeys")
            allkeys = self._get_all_keys(zone_id)
            allkeys_orig = allkeys.copy()
            #logger.debug(f"@@@ allkeys = {allkeys}")

            if not zone_id:
                zone_id = _gen_unique_key(gen_access_key_id, allkeys)
                logger.debug(f"@@@ zone_id = {zone_id}")

            access_keys = zone.get("accessKeys", [])
            for access_key in access_keys:
                if not access_key.get("accessKeyID"):
                    access_key["accessKeyID"] = _gen_unique_key(gen_access_key_id, allkeys)

            #logger.debug(f"@@@ allkeys = {allkeys}")
            logger.debug(f"@@@ newkeys = {allkeys - allkeys_orig}")

            logger.debug(f"@@@ zone_id = {zone_id}")
            for z_id in self.tables.zones.get_zoneID_list(None):
                logger.debug(f"@@@ z_id = {z_id}")
                if z_id == zone_id:
                    continue
                z = self.tables.zones.get_zone(z_id)
                if z is None:
                    continue
                # logger.debug(f"@@@ z_id = {z_id}, z = {z}")
                reasons += check_conflict(zone_id, zone, z_id, z)
                if z.get("user") == user_id:
                    num_zones_of_user += 1
            logger.debug(f"@@@ reasons = {reasons}")

            if reasons != []:
                raise Exception(f"update_zone: conflict with another zone: {reasons}")

            logger.debug(f"@@@ num_zones_of_user = {num_zones_of_user}")

            if num_zones_of_user > self.max_zone_per_user:
                raise Exception(f"update_zone: too many zones (limit per user exceeded)")

            return zone_id

    def _send_decoy_with_zoneid_ptr(self, traceid, zone_id):
            temp_access_keys = [{"accessKeyID": zone_id}]
            zoneID_accessible_zone = {"accessKeys": temp_access_keys,
                             "directHostnames": []}
            try:
                logger.debug(f"@@@ INSERT PTR {zone_id} {zoneID_accessible_zone}")
                self.tables.zones.ins_ptr(zone_id, zoneID_accessible_zone)
                logger.debug("@@@ SEND DECOY START (try)")
                logger.debug(f"@@@ SEND DECOY zone_id = {zone_id}")
                ## Trigger initialize.
                status = self.check_mux_access_for_zone(traceid, zone_id, force=True, access_key_id=zone_id)
                logger.debug(f"@@@ SEND DECOY STATUS {status}")
            except Exception as e:
                ## (IGNORE-FATAL-ERROR)
                logger.exception(e)
                pass
            finally:
                logger.debug(f"@@@ DELETE PTR {zone_id} {[e.get('accessKeyID') for e in temp_access_keys]}")
                self.tables.zones.del_ptr(zone_id, zoneID_accessible_zone)
            logger.debug("@@@ SEND DECOY END")

    def fetch_current_mode(self, zoneID):  # private use
        return self.tables.zones.get_mode(zoneID)

    def set_current_mode(self, zoneID, state):  # private use
        o = self.fetch_current_mode(zoneID)
        logger.debug(f"pool-state change pool=({zoneID}): {o} to {state}")
        self.tables.zones.set_mode(zoneID, state)

    def zone_to_user(self, zoneID):  # ADMIN, multiplexer   CODE CLONE @ multiplexer.py
        zone = self.tables.zones.get_zone(zoneID)
        return zone["user"] if zone else None

    def exp_date(self):  # private use
        now = int(time.time())
        maxExpDate = int(self.system_settings_param["allowed_maximum_zone_exp_date"])
        logger.debug(f"@@@ maxExpDate = {maxExpDate}")
        deflZoneLifetime = int(self.system_settings_param["default_zone_lifetime"])
        logger.debug(f"@@@ deflZoneLifetime = {deflZoneLifetime}")
        logger.debug(f"@@@ now = {now}")
        logger.debug(f"@@@ now + deflZoneLifetime = {now + deflZoneLifetime}")
        expDate = min(now + deflZoneLifetime, maxExpDate)
        logger.debug(f"@@@ timeleft = {expDate - now}")
        return str(expDate)

    def generate_template(self, user_id):  # API
        ui = self.fetch_unixUserInfo(user_id)
        groups = ui.get("groups")

        return {
            "user": user_id,
            "group": groups[0],
            "bucketsDir": "",
            "buckets": [],
            "accessKeys": [
                   {"policyName": "readwrite"},
                   {"policyName": "readonly"},
                   {"policyName": "writeonly"}],
            "directHostnames": [],
            "expDate": self.exp_date(),
            "status": "online",
            "groups": groups,
            "atime": "0",
            "directHostnameDomains": self.direct_hostname_domains,
            "facadeHostname": self.facade_hostname,
            "endpoint_url": self.endpoint_urls({"directHostnames": []})
        }

    def decrypt_access_keys(self, zone):
        access_keys = zone.get("accessKeys", [])
        for accessKey in access_keys:
            accessKey["secretAccessKey"] = decrypt_secret(accessKey["secretAccessKey"])

    def _pullup_mode(self, zoneID, zone):
            zone["mode"] = self.fetch_current_mode(zoneID)

    def _pullup_atime(self, zoneID, zone):
            # we do not copy atime form routing table here.
            #  (1) manager periodically copy atime from routing table to zone table.
            #  (2) it's nouissance to access atime on routing table, because we must
            #      know minio's id that serves for this zone.
            atime = self.tables.zones.get_atime(zoneID)
            zone["atime"] = atime

    def _pullup_ptr(self, zoneID, zone, access_key_ptr, direct_host_ptr):
            zone["accessKeysPtr"] = [{"key": e, "ptr": v} for (e, v) in access_key_ptr if v == zoneID]
            zone["directHostnamePtr"] = [{"key": e, "ptr": v} for (e, v) in direct_host_ptr if v == zoneID]

    def _add_info_for_webui(self, zoneID, zone, groups):
            zone["groups"] = groups
            zone["directHostnameDomains"] = self.direct_hostname_domains
            zone["facadeHostname"] = self.facade_hostname
            zone["endpoint_url"] = self.endpoint_urls(zone)

    def fetch_zone_list(self, user_id, extra_info=False, include_atime=False,
            decrypt=False, include_userinfo=False, zone_id=None):  # ADMIN, API


        # logger.debug(f"@@@ zone_id = {zone_id}")
        groups = None
        if include_userinfo:
            ui = self.fetch_unixUserInfo(user_id)
            groups = ui.get("groups")
        zone_list = []
        broken_zones = []
        if extra_info:
            (access_key_ptr, direct_host_ptr) = self.tables.zones.get_ptr_list()
        for zoneID in self.tables.zones.get_zoneID_list(zone_id):
            #logger.debug(f"@@@ zoneID = {zoneID}")
            zone = self.tables.zones.get_zone(zoneID)

            if zone is None:
                logger.error(f"INCOMPLETE ZONE: {zoneID}")
                broken_zones.append(zoneID)
                continue

            if user_id and zone["user"] != user_id:
                continue

            zone["zoneID"] = zoneID

            if decrypt:
                self.decrypt_access_keys(zone)

            self._pullup_mode(zoneID, zone)

            if include_atime:
                self._pullup_atime(zoneID, zone)

            if extra_info:
                self._pullup_ptr(zoneID, zone, access_key_ptr, direct_host_ptr)

            if include_userinfo:
                self._add_info_for_webui(zoneID, zone, groups)

            zone_list.append(zone)
        # logger.debug(f"@@@ {zone_list} {broken_zones}")
        return (zone_list, broken_zones)

    def endpoint_urls(self, zone):  # private use
        template = self.system_settings_param["endpoint_url"]
        return ([template.format(hostname=h)
                 for h in [self.facade_hostname]] +
                [template.format(hostname=h)
                 for h in zone.get("directHostnames", [])])
