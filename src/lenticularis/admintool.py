"""lenticularis-admin command."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import csv
import inspect
import io
import os
import json
#import threading
import sys
import traceback
from lenticularis.pooladm import ZoneAdm
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import ERROR_EXIT_READCONF, ERROR_EXIT_EXCEPTION, ERROR_EXIT_ARGUMENT
from lenticularis.utility import format_rfc3339_z
from lenticularis.utility import objdump
from lenticularis.utility import list_diff3
from lenticularis.utility import random_str
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


def get_nparams_of_fn(fn):
    sig = inspect.signature(fn)
    params = list(sig.parameters)
    nparams = len(params)
    if nparams > 0:
        v = sig.parameters.get(params[-1])
        assert v is not None
        varargsp = (v.kind == v.VAR_POSITIONAL)
    else:
        varargsp = False
    return (nparams - 1, varargsp)

def fix_date_format(d, keys):
    for key in keys:
        d[key] = format_rfc3339_z(float(d[key]))

def print_json_csv(table_name, c, formatting):
    if formatting in {"json"}:
        dump = json.dumps(c)
        print(f"{dump}")
    else:
        print(f"----- {table_name}")
        with io.StringIO() as out:
            writer = csv.writer(out)
            for r in c:
                writer.writerow(r)
            v = out.getvalue()
        print(f"{v}")

def print_json_plain(table_name, outs, formatting, order=None):
    if formatting in {"json"}:
        dump = json.dumps(outs)
        print(f"{dump}")
    else:
        print(f"----- {table_name}")
        for d in outs:
            dump = objdump(d, order=order)
            print(f"{dump}")

def read_allow_deny_rules(path):
    with open(path, newline="") as f:
        r = csv.reader(f, delimiter=",", quotechar='"')
        return [[row[0].lower(), row[1]] for row in r]

def read_user_info(path):
    with open(path, newline="") as f:
        r = csv.reader(f, delimiter=",", quotechar='"')
        return [{"id": row[0], "groups": row[1:]} for row in r]

def user_info_to_csv_row(ui, id):
    if ui:
        return [ui["id"]] + ui["groups"]
    return [id]

def format_mux(m, formatting):
    (ep, desc) = m
    if formatting not in {"json"}:
        fix_date_format(desc, ["last_interrupted_time", "start_time"])
    return {ep: desc}

def _store_unix_user_info_add(zone_adm, b):
    # New Entry (no right hand side)
    logger.debug(f"@@@ >> New {b}")
    zone_adm.store_unix_user_info(b["id"], b)

def _store_unix_user_info_delete(zone_adm, e):
    # Deleted Entry (no left hand side)
    logger.debug(f"@@@ >> Delete {e}")
    zone_adm.delete_unix_user_info(e)

def _store_unix_user_info_update(zone_adm, x):
    # Updated Entry
    (b, e) = x
    logger.debug(f"@@@ >> Update {b} {e}")
    zone_adm.store_unix_user_info(b["id"], b)

def _store_user_info(zone_adm, user_info):
    existing = zone_adm.list_unixUsers()
    logger.debug(f"@@@ existing = {existing}")
    (ll, pp, rr) = list_diff3(user_info, lambda b: b.get("id"),
                              existing, lambda e: e)
    for x in ll:
        _store_unix_user_info_add(zone_adm, x)
    for x in rr:
        _store_unix_user_info_delete(zone_adm, x)
    for x in pp:
        _store_unix_user_info_update(zone_adm, x)


def _restore_zone_delete(zone_adm, traceid, e):
    # Deleted Entry (no left hand side)
    user_id = e.get("owner_uid")
    zone_id = e.get("pool_name")
    logger.debug(f"@@@ >> Delete {user_id} {zone_id}")
    zone_adm.delete_zone(traceid, user_id, zone_id)

def _restore_zone_add(zone_adm, traceid, b):
    # New Entry (no right hand side)
    user_id = b.get("owner_uid")
    zone_id = b.get("pool_name")
    logger.debug(f"@@@ >> Insert / Update {user_id} {zone_id}")
    b.pop("pool_name")
    b.pop("minio_state")
    zone_adm.restore_pool(traceid, user_id, zone_id, b,
                          include_atime=True, initialize=False)

def _restore_zone_update(zone_adm, traceid, x):
    # Updated Entry
    (b, e) = x
    _restore_zone_add(zone_adm, traceid, b)


def pool_key_order(e):
    order = [
        "owner_uid",
        "owner_gid",
        "root_secret",
        "access_keys",
        "buckets_directory",
        "buckets",
        "direct_hostnames",
        "expiration_date",
        "permit_status",
        "online_status",
        "minio_state",
        "atime",
        ##AHO
        "accessKeysPtr",
        "directHostnamePtr",
        "access_key",
        "secret_key",
        "key_policy",
        "ptr",
        "name",
        "policy"]
    return order.index(e) if e in order else len(order)

def _mux_key_order(e):
    order = [
        "host",
        "port",
        "mux_conf",
        "start_time",
        "last_interrupted_time",
        "lenticularis",
        "multiplexer"]
    return order.index(e) if e in order else len(order)

def proc_key_order(e):
    order = [
        "minio_ep",
        "minio_pid",
        "mux_host",
        "mux_port",
        "manager_pid"]
    return order.index(e) if e in order else len(order)

def route_key_order(e):
    order = [
        ##AHO
        "accessKey",
        "host",
        "atime"]
    return order.index(e) if e in order else len(order)


##def quote(s):
##    return f'"{s}"'

class Command():
    def __init__(self, adm_conf, traceid, args, rest):
        self.adm_conf = adm_conf
        self.zone_adm = ZoneAdm(adm_conf)
        self.traceid = traceid
        self.args = args
        self.rest = rest

    def fn_usage(self):
        progname = os.path.basename(sys.argv[0])
        sys.stderr.write(
            f"USAGE:\n"
            f"{progname} help\n"

            # fn_insert_allow_deny_rules
            f"{progname} load-permit-list file\n"
            # fn_show_allow_deny_rules
            f"{progname} show-permit-list\n"

            # fn_insert_user_info
            f"{progname} load-user-list file\n"
            # fn_show_user_info
            f"{progname} show-user-list\n"

            # fn_insert_zone
            f"{progname} insert-zone Zone-ID jsonfile\n"
            # fn_delete_zone ...
            f"{progname} delete-zone Zone-ID...\n"
            # fn_disable_zone ...
            f"{progname} disable-zone Zone-ID...\n"
            # fn_enable_zone ...
            f"{progname} enable-zone Zone-ID...\n"
            # fn_show_zone ...
            f"{progname} show-zone [--decrypt] [pool-id ...]\n"
            # fn_dump_zone
            f"{progname} dump-zone\n"
            # fn_restore_zone
            f"{progname} restore-zone dump-file\n"
            # fn_drop_zone
            f"{progname} drop-zone\n"
            # fn_reset_database
            f"{progname} reset-db\n"
            # fn_print_database
            f"{progname} list-db\n"

            # fn_show_multiplexer
            f"{progname} show-muxs\n"
            # f"{progname} flush-multiplexer\n" NOT IMPLEMENTED

            # fn_show_server_processes
            f"{progname} show-minios\n"
            # fn_flush_server_processes
            f"{progname} flush-server-processes\n"
            # fn_delete_server_processes ...
            f"{progname} delete-server-processes [Server-ID...]\n"

            # fn_throw_decoy
            f"{progname} throw-decoy Zone-ID\n"

            # fn_show_routing_table
            f"{progname} show-routing\n"
            # fn_flush_routing_table
            f"{progname} clear-routing\n"
        )
        sys.exit(ERROR_EXIT_ARGUMENT)

    def fn_insert_allow_deny_rules(self, csvfile):
        logger.debug(f"@@@ INSERT ALLOW DENY RULES")
        rules = read_allow_deny_rules(csvfile)
        logger.debug(f"@@@ rules = {rules}")
        self.zone_adm.store_allow_deny_rules(rules)
        fixed = self.zone_adm.fix_affected_zone(self.traceid)
        logger.debug(f"@@@ fixed = {fixed}")

    def fn_show_allow_deny_rules(self):
        rules = self.zone_adm.fetch_allow_deny_rules()
        print_json_csv("allow deny rules", rules, self.args.format)

    def fn_insert_user_info(self, csvfile):
        logger.debug(f"@@@ INSERT USER INFO")
        user_info = read_user_info(csvfile)
        logger.debug(f"@@@ user_info = {user_info}")
        _store_user_info(self.zone_adm, user_info)
        fixed = self.zone_adm.fix_affected_zone(self.traceid)
        logger.debug(f"@@@ fixed = {fixed}")

    def fn_show_user_info(self):
        unix_users = self.zone_adm.list_unixUsers()
        logger.debug(f"@@@ {unix_users}")
        uis = [user_info_to_csv_row(self.zone_adm.fetch_unix_user_info(id), id)
               for id in unix_users]
        print_json_csv("user info", uis, self.args.format)

    def fn_insert_zone(self, zone_id, jsonfile):
        logger.debug(f"@@@ INSERT ZONE")
        try:
            with open(jsonfile, "r") as f:
                r = f.read()
        except OSError as e:
            sys.stderr.write(f"{jsonfile}: {os.strerror(e.errno)}\n")
            logger.exception(e)
            return
        except Exception as e:
            sys.stderr.write(f"{jsonfile}: {e}\n")
            logger.exception(e)
            return
        zone = json.loads(r, parse_int=None)
        user_id = zone["owner_uid"]
        self.zone_adm.restore_pool(self.traceid, user_id, zone_id, zone,
                                   include_atime=False, initialize=True)

    def fn_delete_zone(self, *zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.delete_zone(self.traceid, user_id, zone_id)

    def fn_disable_zone(self, *zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.disable_zone(self.traceid, user_id, zone_id)

    def fn_enable_zone(self, *zoneIDs):
        logger.debug(f"@@@ ENABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.enable_zone(self.traceid, user_id, zone_id)

    def fn_show_zone(self, *zoneIDs):
        decrypt = False
        if len(zoneIDs) > 0 and zoneIDs[0] == "--decrypt":
            zoneIDs = list(zoneIDs)
            zoneIDs.pop(0)
            decrypt = True
        zoneIDs = set(zoneIDs)
        (zone_list, broken_zone) = self.zone_adm.fetch_zone_list(None, extra_info=True, include_atime=True, decrypt=decrypt)
        outs = []
        for zone in zone_list:
            zone_id = zone["pool_name"]
            if zoneIDs != set() and zone_id not in zoneIDs:
                continue
            if self.args.format not in {"json"}:
                fix_date_format(zone, ["atime", "expiration_date"])
            zone.pop("pool_name")
            outs.append({zone_id: zone})
        print_json_plain("zones", outs, self.args.format, order=pool_key_order)
        logger.debug(f"broken zones: {broken_zone}")

    def fn_dump_zone(self):
        rules = self.zone_adm.fetch_allow_deny_rules()
        unix_users = self.zone_adm.list_unixUsers()
        users = [self.zone_adm.fetch_unix_user_info(id) for id in unix_users]
        (zone_list, _) = self.zone_adm.fetch_zone_list(None, include_atime=True)
        dump_data = json.dumps({"rules": rules, "users": users, "zones": zone_list})
        print(dump_data)

    def fn_restore_zone(self, dump_file):
        logger.debug(f"@@@ INSERT ZONE")
        with open(dump_file) as f:
            dump_data = f.read()
        j = json.loads(dump_data, parse_int=None)
        rules = j["rules"]
        user_info = j["users"]
        zone_list = j["zones"]
        self.zone_adm.store_allow_deny_rules(rules)
        _store_user_info(self.zone_adm, user_info)
        (existing, _) = self.zone_adm.fetch_zone_list(None)
        (ll, pp, rr) = list_diff3(zone_list, lambda b: b.get("pool_name"),
                                  existing, lambda e: e.get("pool_name"))
        for x in rr:
            _restore_zone_delete(self.zone_adm, self.traceid, x)
        for x in ll:
            _restore_zone_add(self.zone_adm, self.traceid, x)
        for x in pp:
            _restore_zone_update(self.zone_adm, self.traceid, x)

    def fn_drop_zone(self):
        everything = self.args.everything
        self.zone_adm.flush_storage_table(everything=everything)

    def fn_reset_database(self):
        everything = self.args.everything
        self.zone_adm.reset_database(everything=everything)

    def fn_print_database(self):
        self.zone_adm.print_database()

    def fn_show_multiplexer(self):
        muxs = sorted(list(self.zone_adm.fetch_multiplexer_list()))
        outs = [format_mux(m, self.args.format) for m in muxs]
        print_json_plain("muxs", outs, self.args.format, order=_mux_key_order)

    def fn_show_server_processes(self):
        process_list = sorted(list(self.zone_adm.fetch_process_list()))
        logger.debug(f"@@@ process_list = {process_list}")
        outs = [{zone: process} for (zone, process) in process_list]
        print_json_plain("servers", outs, self.args.format, order=proc_key_order)

    def fn_flush_server_processes(self):
        everything = self.args.everything
        logger.debug(f"@@@ EVERYTHING = {everything}")
        self.zone_adm.flush_process_table(everything=everything)

    def fn_delete_server_processes(self, *processIDs):
        logger.debug(f"@@@ DELETE = {processIDs}")
        for processID in processIDs:
            logger.debug(f"@@@ DELETE = {processID}")
            self.zone_adm.delete_process(processID)

    def fn_throw_decoy(self, zone_id):
        logger.debug(f"@@@ THROW DECOY zone_id = {zone_id}")
        self.zone_adm.access_mux_for_pool(self.traceid, zone_id, force=True)

    def fn_show_routing_table(self):
        pairs = self.zone_adm.tables.routing_table.list_routes()
        print_json_plain("routing table", pairs, self.args.format, order=route_key_order)

    ##def fn_show_routing_table(self):
    ##    (akey_list, host_list, atime_list) = self.zone_adm.fetch_route_list()
    ##    akey_list = [(v, e) for (e, v) in akey_list]
    ##    host_list = [(v, e) for (e, v) in host_list]
    ##    atime_list = list(atime_list)
    ##    servers = [e for (e, v) in akey_list] + [e for (e, v) in host_list] + [e for (e, v) in atime_list]
    ##    servers = sorted(list(set(servers)))
    ##    logger.debug(f"HOST_LIST = {host_list}")
    ##    logger.debug(f"SERVERS = {servers}")
    ##
    ##    def collect_routes_of_server(server):
    ##        accessKeys = [akey for (srv, akey) in akey_list if srv == server]
    ##        hosts = [host for (srv, host) in host_list if srv == server]
    ##        atime = next((atm for (srv, atm) in atime_list if srv == server), None)
    ##        routes = {"accessKey": accessKeys, "host": hosts, "atime": atime}
    ##        if self.args.format not in {"json"}:
    ##            fix_date_format(routes, ["atime"])
    ##        return {server: routes}
    ##
    ##    outs = [collect_routes_of_server(server) for server in servers]
    ##    print_json_plain("routing table", outs, self.args.format, order=route_key_order)

    def fn_flush_routing_table(self):
        everything = self.args.everything
        self.zone_adm.flush_routing_table(everything=everything)

    optbl = {
        "help": fn_usage,

        "load-user-list": fn_insert_user_info,
        "show-user-list": fn_show_user_info,
        "load-permit-list": fn_insert_allow_deny_rules,
        "show-permit-list": fn_show_allow_deny_rules,

        "insert-zone": fn_insert_zone,
        "delete-zone": fn_delete_zone,
        "disable-zone": fn_disable_zone,
        "enable-zone": fn_enable_zone,
        "show-zone": fn_show_zone,

        "dump-zone": fn_dump_zone,
        "restore-zone": fn_restore_zone,
        "drop-zone": fn_drop_zone,
        "reset-db": fn_reset_database,
        "list-db": fn_print_database,

        "show-muxs": fn_show_multiplexer,

        "show-minios": fn_show_server_processes,
        "flush-server-processes": fn_flush_server_processes,
        "delete-server-processes": fn_delete_server_processes,

        "throw-decoy": fn_throw_decoy,

        "show-routing": fn_show_routing_table,
        "clear-routing": fn_flush_routing_table,
    }

    def execute_command(self):
        fn = Command.optbl.get(self.args.operation)

        if fn is None:
            raise Exception(f"undefined operation: {self.args.operation}")

        (nparams, varargsp) = get_nparams_of_fn(fn)

        if not varargsp and len(self.rest) != nparams:
            sys.stderr.write("Missing/excessive arguments for command.\n")
            self.fn_usage()
        return fn(self, *self.rest)


def main():
    _commands = Command.optbl.keys()

    parser = argparse.ArgumentParser()
    parser.add_argument("operation",
                        choices=_commands)
    parser.add_argument("--configfile", "-c")
    parser.add_argument("--format", "-f", choices=["text", "json"])
    parser.add_argument("--everything", type=bool, default=False)
    parser.add_argument("--yes", "-y", type=bool, default=False)
    #action=argparse.BooleanOptionalAction was introduced in Python3.9

    args, rest = parser.parse_known_args()

    try:
        (adm_conf, configfile) = read_adm_conf(args.configfile)
    except Exception as e:
        sys.stderr.write(f"Reading conf failed: {e}\n")
        sys.exit(ERROR_EXIT_READCONF)

    traceid = random_str(12)
    #threading.current_thread().name = traceid
    tracing.set(traceid)
    openlog(adm_conf["log_file"],
            **adm_conf["log_syslog"])
    ##logger.info("**** START ADMIN ****")
    logger.debug(f"traceid = {traceid}")

    try:
        logger.debug(f"@@@ MAIN")
        ##zone_adm = ZoneAdm(adm_conf)
        adm = Command(adm_conf, traceid, args, rest)
        adm.execute_command()
    except Exception as e:
        sys.stderr.write(f"Executing admin command failed: {e}\n")
        print(traceback.format_exc())
        ##adm.fn_usage()
        sys.exit(ERROR_EXIT_EXCEPTION)


if __name__ == "__main__":
    main()
