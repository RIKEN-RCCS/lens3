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
from lenticularis.zoneadm import ZoneAdm
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import ERROR_READCONF, ERROR_EXCEPTION, ERROR_ARGUMENT
from lenticularis.utility import format_rfc3339_z
from lenticularis.utility import logger, openlog
from lenticularis.utility import objdump
from lenticularis.utility import outer_join_list
from lenticularis.utility import random_str
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

def fix_date_format(dic, keys):
    for key in keys:
        dic[key] = format_rfc3339_z(float(dic[key]))

def print_json_csv(table_name, c, format):
    if format in {"json"}:
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

def print_json_plain(table_name, outs, format, order=None):
    if format in {"json"}:
        dump = json.dumps(outs)
        print(f"{dump}")
    else:
        print(f"----- {table_name}")
        for d in outs:
            dump = objdump(d, order=order)
            print(f"{dump}")

def read_allow_deny_rules(path):
    with open(path, newline='') as f:
        r = csv.reader(f, delimiter=',', quotechar='"')
        return [[row[0].lower(), row[1]] for row in r]

def read_user_info(path):
    with open(path, newline='') as f:
        r = csv.reader(f, delimiter=',', quotechar='"')
        return [{"id": row[0], "groups": row[1:]} for row in r]

def user_info_to_csv_row(ui, id):
    if ui:
        return [ui["id"]] + ui["groups"]
    return [id]

def format_mux(m, format):
    (multiplexer, info) = m
    if format not in {"json"}:
        fix_date_format(info, ["last_interrupted_time", "start_time"])
    return {multiplexer: info}

def _store_unix_user_info_add(zone_adm, b):
    # New Entry (no right hand side)
    logger.debug(f"@@@ >> New {b}")
    zone_adm.store_unixUserInfo(b["id"], b)

def _store_unix_user_info_delete(zone_adm, e):
    # Deleted Entry (no left hand side)
    logger.debug(f"@@@ >> Delete {e}")
    zone_adm.delete_unixUserInfo(e)

def _store_unix_user_info_update(zone_adm, x):
    # Updated Entry
    (b, e) = x
    logger.debug(f"@@@ >> Update {b} {e}")
    zone_adm.store_unixUserInfo(b["id"], b)

def _store_user_info(zone_adm, user_info):
    existing = zone_adm.list_unixUsers()
    logger.debug(f"@@@ existing = {existing}")
    (ll, pp, rr) = outer_join_list(user_info, lambda b: b.get("id"),
                                   existing, lambda e: e)
    for x in ll:
        _store_unix_user_info_add(zone_adm, x)
    for x in rr:
        _store_unix_user_info_delete(zone_adm, x)
    for x in pp:
        _store_unix_user_info_update(zone_adm, x)


def _restore_zone_delete(zone_adm, traceid, e):
    # Deleted Entry (no left hand side)
    user_id = e.get("user")
    zone_id = e.get("zoneID")
    logger.debug(f"@@@ >> Delete {user_id} {zone_id}")
    zone_adm.delete_zone(traceid, user_id, zone_id)

def _restore_zone_add(zone_adm, traceid, b):
    # New Entry (no right hand side)
    user_id = b.get("user")
    zone_id = b.get("zoneID")
    logger.debug(f"@@@ >> Insert / Update {user_id} {zone_id}")
    b.pop("zoneID")
    b.pop("minio_state")
    zone_adm.restore_pool(traceid, user_id, zone_id, b,
                          include_atime=True, initialize=False)

def _restore_zone_update(zone_adm, traceid, x):
    # Updated Entry
    (b, e) = x
    _restore_zone_add(zone_adm, traceid, b)


def pool_key_order(e):
    order = [
        "user",
        "group",
        "rootSecret",
        "accessKeys",
        "bucketsDir",
        "buckets",
        "directHostnames",
        "expDate",
        "online_status",
        "operation_status",
        "minio_state",
        "atime",
        "accessKeysPtr",
        "directHostnamePtr",
        "accessKeyID",
        "secretAccessKey",
        "policyName",
        "key",
        "ptr",
        "policy"]
    return order.index(e) if e in order else len(order)

def mux_key_order(e):
    order = [
        "mux_conf",
        "start_time",
        "last_interrupted_time",
        "lenticularis",
        "multiplexer",
        "host",
        "port"]
    return order.index(e) if e in order else len(order)

def proc_key_order(e):
    order = [
        "minioAddr",
        "minioPid",
        "muxAddr",
        "supervisorPid"]
    return order.index(e) if e in order else len(order)

def route_key_order(e):
    order = [
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
            f"{progname} insert-allow-deny-rules file\n"
            # fn_show_allow_deny_rules
            f"{progname} show-allow-deny-rules\n"

            # fn_insert_user_info
            f"{progname} insert-user-info file\n"
            # fn_show_user_info
            f"{progname} show-user-info\n"

            # fn_insert_zone
            f"{progname} insert-zone Zone-ID jsonfile\n"
            # fn_delete_zone ...
            f"{progname} delete-zone Zone-ID...\n"
            # fn_disable_zone ...
            f"{progname} disable-zone Zone-ID...\n"
            # fn_enable_zone ...
            f"{progname} enable-zone Zone-ID...\n"
            # fn_show_zone ...
            f"{progname} show-zone [--decrypt] [Zone-ID...]\n"
            # fn_dump_zone
            f"{progname} dump-zone\n"
            # fn_restore_zone
            f"{progname} restore-zone dump-file\n"
            # fn_drop_zone
            f"{progname} drop-zone\n"
            # fn_reset_database
            f"{progname} reset-db\n"
            # fn_print_database
            f"{progname} print-db\n"

            # fn_show_multiplexer
            f"{progname} show-multiplexer\n"
            # f"{progname} flush-multiplexer\n" NOT IMPLEMENTED

            # fn_show_server_processes
            f"{progname} show-server-processes\n"
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
        sys.exit(ERROR_ARGUMENT)

    def fn_insert_allow_deny_rules(self, csvfile):
        logger.debug(f"@@@ INSERT ALLOW DENY RULES")
        rules = read_allow_deny_rules(csvfile)
        logger.debug(f"@@@ rules = {rules}")
        self.zone_adm.store_allow_deny_rules(rules)
        fixed = self.zone_adm.fix_affected_zone(traceid)
        logger.debug(f"@@@ fixed = {fixed}")

    def fn_show_allow_deny_rules(self):
        rules = self.zone_adm.fetch_allow_deny_rules()
        print_json_csv("allow deny rules", rules, self.args.format)

    def fn_insert_user_info(self, csvfile):
        logger.debug(f"@@@ INSERT USER INFO")
        user_info = read_user_info(csvfile)
        logger.debug(f"@@@ user_info = {user_info}")
        _store_user_info(self.zone_adm, user_info)
        fixed = self.zone_adm.fix_affected_zone(traceid)
        logger.debug(f"@@@ fixed = {fixed}")

    def fn_show_user_info(self):
        unix_users = self.zone_adm.list_unixUsers()
        logger.debug(f"@@@ {unix_users}")
        uis = [user_info_to_csv_row(self.zone_adm.fetch_unixUserInfo(id), id)
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
        user_id = zone["user"]
        self.zone_adm.restore_pool(traceid, user_id, zone_id, zone,
                                   include_atime=False, initialize=True)

    def fn_delete_zone(self, *zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.delete_zone(traceid, user_id, zone_id)

    def fn_disable_zone(self, *zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.disable_zone(traceid, user_id, zone_id)

    def fn_enable_zone(self, *zoneIDs):
        logger.debug(f"@@@ ENABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.enable_zone(traceid, user_id, zone_id)

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
            zone_id = zone["zoneID"]
            if zoneIDs != set() and zone_id not in zoneIDs:
                continue
            if self.args.format not in {"json"}:
                fix_date_format(zone, ["atime", "expDate"])
            zone.pop("zoneID")
            outs.append({zone_id: zone})
        print_json_plain("zones", outs, self.args.format, order=pool_key_order)
        logger.debug(f"broken zones: {broken_zone}")

    def fn_dump_zone(self):
        rules = self.zone_adm.fetch_allow_deny_rules()
        unix_users = self.zone_adm.list_unixUsers()
        users = [self.zone_adm.fetch_unixUserInfo(id) for id in unix_users]
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
        (ll, pp, rr) = outer_join_list(zone_list, lambda b: b.get("zoneID"),
                                       existing, lambda e: e.get("zoneID"))
        for x in rr:
            _restore_zone_delete(self.zone_adm, traceid, x)
        for x in ll:
            _restore_zone_add(self.zone_adm, traceid, x)
        for x in pp:
            _restore_zone_update(self.zone_adm, traceid, x)

    def fn_drop_zone(self):
        everything = self.args.everything
        self.zone_adm.flush_storage_table(everything=everything)

    def fn_reset_database(self):
        everything = self.args.everything
        self.zone_adm.reset_database(everything=everything)

    def fn_print_database(self):
        self.zone_adm.print_database()

    def fn_show_multiplexer(self):
        multiplexer_list = sorted(list(self.zone_adm.fetch_multiplexer_list()))
        outs = [format_mux(m, self.args.format) for m in multiplexer_list]
        print_json_plain("multiplexers", outs, self.args.format, order=mux_key_order)

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
        self.zone_adm.check_mux_access_for_zone(traceid, zone_id, force=True)

    def fn_show_routing_table(self):
        pairs = self.zone_adm.tables.routing_table.get_route_list()
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

        "insert-user-info": fn_insert_user_info,
        "show-user-info": fn_show_user_info,
        "insert-user-validity": fn_insert_allow_deny_rules,
        "show-user-validity": fn_show_allow_deny_rules,

        "insert-zone": fn_insert_zone,
        "delete-zone": fn_delete_zone,
        "disable-zone": fn_disable_zone,
        "enable-zone": fn_enable_zone,
        "show-zone": fn_show_zone,

        "dump-zone": fn_dump_zone,
        "restore-zone": fn_restore_zone,
        "drop-zone": fn_drop_zone,
        "reset-db": fn_reset_database,
        "print-db": fn_print_database,

        "show-multiplexer": fn_show_multiplexer,

        "show-server-processes": fn_show_server_processes,
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
        sys.exit(ERROR_READCONF)

    traceid = random_str(12)
    #threading.current_thread().name = traceid
    tracing.set(traceid)
    openlog(adm_conf["lenticularis"]["log_file"],
            **adm_conf["lenticularis"]["log_syslog"])
    ##logger.info("**** START ADMIN ****")
    logger.debug(f"traceid = {traceid}")

    try:
        logger.debug(f"@@@ MAIN")
        ##zone_adm = ZoneAdm(adm_conf)
        adm = Command(adm_conf, traceid, args, rest)
        adm.execute_command()
    except Exception as e:
        sys.stderr.write(f"Executing admin command failed: {e}\n")
        ##adm.fn_usage()
        sys.exit(ERROR_EXCEPTION)


if __name__ == "__main__":
    main()
