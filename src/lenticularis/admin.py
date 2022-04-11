"""lenticularis-admin command."""

# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import csv
from inspect import signature
import io
import json
from lenticularis.zoneadm import ZoneAdm
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import ERROR_READCONF, ERROR_EXCEPTION, ERROR_ARGUMENT
from lenticularis.utility import format_rfc3339_z
from lenticularis.utility import logger, openlog
from lenticularis.utility import objdump
from lenticularis.utility import outer_join
from lenticularis.utility import random_str
from lenticularis.utility import safe_json_loads
import os
import threading
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation",
                        choices=["delete",
                                 "disable",
                                 "drop",
                                 "resetall",
                                 "printall",
                                 "dump",
                                 "flush",
                                 "enable",
                                 "insert",
                                 "restore",
                                 "show",
                                 "throw"])

    parser.add_argument("--configfile", "-c")
    parser.add_argument("--format", "-f", choices=["text", "json"])
    parser.add_argument("--everything", type=bool, default=False)
    #action=argparse.BooleanOptionalAction was introduced in Python3.9

    args, rest = parser.parse_known_args()

    try:
        (adm_conf, configfile) = read_adm_conf(args.configfile)
    except Exception as e:
        sys.stderr.write(f"Reading conf failed: {e}\n")
        sys.exit(ERROR_READCONF)

    traceid = random_str(12)
    threading.current_thread().name = traceid
    openlog(adm_conf["lenticularis"]["log_file"],
            **adm_conf["lenticularis"]["log_syslog"])
    logger.info("***** START ADMIN *****")
    logger.debug(f"traceid = {traceid}")

    try:
        logger.debug(f"@@@ MAIN")
        admin_main(traceid, adm_conf, args, rest)
    except Exception as e:
        logger.debug(f"@@@ {e}")
        logger.exception(e)
        sys.stderr.write(f"admin_main: {e}\n")
        usage()
        sys.exit(ERROR_EXCEPTION)


def admin_main(traceid, adm_conf, args, rest):

    def quote(s):
        return f'"{s}"'

    zone_adm = ZoneAdm(adm_conf)

    def fn_insert_allow_deny_rules(csvfile):
        logger.debug(f"@@@ INSERT ALLOW DENY RULES")

        def read_allow_deny_rules(path):
            with open(path, newline='') as f:
                r = csv.reader(f, delimiter=',', quotechar='"')
                return [[row[0].lower(), row[1]] for row in r]
        rules = read_allow_deny_rules(csvfile)
        logger.debug(f"@@@ rules = {rules}")
        zone_adm.store_allow_deny_rules(rules)
        fixed = zone_adm.fix_affected_zone(traceid)
        logger.debug(f"@@@ fixed = {fixed}")

    def fn_show_allow_deny_rules():
        rules = zone_adm.fetch_allow_deny_rules()
        print_json_csv("allow deny rules", rules, args.format)

    def fn_insert_user_info(csvfile):
        logger.debug(f"@@@ INSERT USER INFO")

        def read_user_info(path):
            with open(path, newline='') as f:
                r = csv.reader(f, delimiter=',', quotechar='"')
                return [{"id": row[0], "groups": row[1:]} for row in r]
        user_info = read_user_info(csvfile)
        logger.debug(f"@@@ user_info = {user_info}")
        store_user_info(user_info)
        fixed = zone_adm.fix_affected_zone(traceid)
        logger.debug(f"@@@ fixed = {fixed}")

    def store_user_info(user_info):

        existing = zone_adm.list_unixUsers()
        logger.debug(f"@@@ existing = {existing}")

        def store_unix_user_info_body(b, e):
            if e is None:  # New Entry
                logger.debug(f"@@@ >> New {b}")
                zone_adm.store_unixUserInfo(b["id"], b)
            elif b is None:  # Deleted Entry
                logger.debug(f"@@@ >> Delete {e}")
                zone_adm.delete_unixUserInfo(e)
            else:  # Updated Entry
                logger.debug(f"@@@ >> Update {b} {e}")
                zone_adm.store_unixUserInfo(b["id"], b)

        outer_join(user_info, lambda b: b.get("id"),
                   existing, lambda e: e,
                   store_unix_user_info_body)

    def fn_show_user_info():
        def ui_to_csvrow(ui, id):
            if ui:
                return [ui["id"]] + ui["groups"]
            return [id]
        unix_users = zone_adm.list_unixUsers()
        logger.debug(f"@@@ {unix_users}")
        uis = [ui_to_csvrow(zone_adm.fetch_unixUserInfo(id), id) for id in unix_users]
        print_json_csv("user info", uis, args.format)

    def fn_insert_zone(zone_id, jsonfile):
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
        zone = safe_json_loads(r, parse_int=str)
        user_id = zone["user"]
        zone_adm.upsert_zone(traceid, user_id, zone_id, zone)

    def fn_delete_zone(*zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = zone_adm.zone_to_user(zone_id)
            zone_adm.delete_zone(traceid, user_id, zone_id)

    def fn_disable_zone(*zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = zone_adm.zone_to_user(zone_id)
            zone_adm.disable_zone(traceid, user_id, zone_id)

    def fn_enable_zone(*zoneIDs):
        logger.debug(f"@@@ ENABLE ZONE")
        for zone_id in zoneIDs:
            user_id = zone_adm.zone_to_user(zone_id)
            zone_adm.enable_zone(traceid, user_id, zone_id)

    def fn_show_zone(*zoneIDs):
        decrypt = False
        if len(zoneIDs) > 0 and zoneIDs[0] == "--decrypt":
            zoneIDs = list(zoneIDs)
            zoneIDs.pop(0)
            decrypt = True
        zoneIDs = set(zoneIDs)
        (zone_list, broken_zone) = zone_adm.fetch_zone_list(None, extra_info=True, include_atime=True, decrypt=decrypt)
        outs = []
        for zone in zone_list:
            zone_id = zone["zoneID"]
            if zoneIDs != set() and zone_id not in zoneIDs:
                continue
            if args.format not in {"json"}:
                fix_date_format(zone, ["atime", "expDate"])
            zone.pop("zoneID")
            outs.append({zone_id: zone})

        order = [
            "user",
            "group",
            "rootSecret",
            "accessKeys",
            "bucketsDir",
            "buckets",
            "directHostnames",
            "expDate",
            "status",
            "permission",
            "mode",
            "atime",
            "accessKeysPtr",
            "directHostnamePtr",
            "accessKeyID",
            "secretAccessKey",
            "policyName",
            "key",
            "ptr",
            "policy"]

        def keyfactory(e):
            return order.index(e) if e in order else len(order)

        print_json_plain("zones", outs, args.format, order=keyfactory)
        logger.debug(f"broken zones: {broken_zone}")

    def fn_dump_zone():
        rules = zone_adm.fetch_allow_deny_rules()
        unix_users = zone_adm.list_unixUsers()
        users = [zone_adm.fetch_unixUserInfo(id) for id in unix_users]
        (zone_list, _) = zone_adm.fetch_zone_list(None, include_atime=True)
        dump_data = json.dumps({"rules": rules, "users": users, "zones": zone_list})
        print(dump_data)

    def fn_restore_zone(dump_file):
        logger.debug(f"@@@ INSERT ZONE")
        with open(dump_file) as f:
            dump_data = f.read()
        j = safe_json_loads(dump_data, parse_int=str)
        rules = j["rules"]
        user_info = j["users"]
        zone_list = j["zones"]
        zone_adm.store_allow_deny_rules(rules)
        store_user_info(user_info)

        (existing, _) = zone_adm.fetch_zone_list(None)

        def restore_zone_body_pass1(b, e):
            if b is None:  # Deleted Entry
                user_id = e.get("user")
                zone_id = e.get("zoneID")
                logger.debug(f"@@@ >> Delete {user_id} {zone_id}")
                zone_adm.delete_zone(traceid, user_id, zone_id)

        def restore_zone_body_pass2(b, e):
            if b is not None:  # New / Updated Entry
                user_id = b.get("user")
                zone_id = b.get("zoneID")
                logger.debug(f"@@@ >> Insert / Update {user_id} {zone_id}")
                b.pop("zoneID")
                b.pop("mode")
                zone_adm.upsert_zone(traceid, user_id, zone_id, b, include_atime=True,
                                     initialize=False)

        outer_join(zone_list, lambda b: b.get("zoneID"),
                   existing, lambda e: e.get("zoneID"),
                   restore_zone_body_pass1)
        outer_join(zone_list, lambda b: b.get("zoneID"),
                   existing, lambda e: e.get("zoneID"),
                   restore_zone_body_pass2)

    def fn_drop_zone():
        everything = args.everything
        zone_adm.flush_zone_table(everything=everything)

    def fn_reset_database():
        everything = args.everything
        zone_adm.reset_database(everything=everything)

    def fn_print_database():
        zone_adm.print_database()

    def fn_show_multiplexer():
        multiplexer_list = sorted(list(zone_adm.fetch_multiplexer_list()))

        def fmt_multiplexer(m):
            (multiplexer, info) = m
            if args.format not in {"json"}:
                fix_date_format(info, ["last_interrupted_time", "start_time"])
            return {multiplexer: info}
        outs = [fmt_multiplexer(m) for m in multiplexer_list]
        order = [
            "mux_conf",
            "start_time",
            "last_interrupted_time",
            "lenticularis",
            "multiplexer",
            "host",
            "port"]

        def keyfactory(e):
            return order.index(e) if e in order else len(order)

        print_json_plain("multiplexers", outs, args.format, order=keyfactory)

    def fn_show_server_processes():

        process_list = sorted(list(zone_adm.fetch_process_list()))
        logger.debug(f"@@@ process_list = {process_list}")
        outs = [{zone: process} for (zone, process) in process_list]
        order = [
            "minioAddr",
            "minioPid",
            "muxAddr",
            "supervisorPid"]

        def keyfactory(e):
            return order.index(e) if e in order else len(order)

        print_json_plain("servers", outs, args.format, order=keyfactory)

    def fn_flush_server_processes():
        everything = args.everything
        logger.debug(f"@@@ EVERYTHING = {everything}")
        zone_adm.flush_process_table(everything=everything)

    def fn_delete_server_processes(*processIDs):
        logger.debug(f"@@@ DELETE = {processIDs}")
        for processID in processIDs:
            logger.debug(f"@@@ DELETE = {processID}")
            zone_adm.delete_process(processID)

    def fn_throw_decoy(zone_id):
        logger.debug(f"@@@ THROW DECOY zone_id = {zone_id}")
        zone_adm.throw_decoy(traceid, zone_id, force=True)

    def fn_show_routing_table():
        (akey_list, host_list, atime_list) = zone_adm.fetch_route_list()
        akey_list = [(v, e) for (e, v) in akey_list]
        host_list = [(v, e) for (e, v) in host_list]
        logger.debug(f"HOST_LIST = {host_list}")
        atime_list = list(atime_list)
        servers = [e for (e, v) in akey_list] + [e for (e, v) in host_list] + [e for (e, v) in atime_list]
        servers = sorted(list(set(servers)))
        logger.debug(f"SERVERS = {servers}")

        def collect_routes_of_server(server):
            accessKeys = [akey for (srv, akey) in akey_list if srv == server]
            hosts = [host for (srv, host) in host_list if srv == server]
            atime = next((atm for (srv, atm) in atime_list if srv == server), None)
            routes = {"accessKey": accessKeys, "host": hosts, "atime": atime}
            if args.format not in {"json"}:
                fix_date_format(routes, ["atime"])
            return {server: routes}

        outs = [collect_routes_of_server(server) for server in servers]
        order = [
            "accessKey",
            "host",
            "atime"]

        def keyfactory(e):
            return order.index(e) if e in order else len(order)

        print_json_plain("routing table", outs, args.format, order=keyfactory)

    def fn_flush_routing_table():
        everything = args.everything
        zone_adm.flush_routing_table(everything=everything)

    logger.debug(f"@@@ BODY")

    optbl = {
        "insert.allow-deny-rules": fn_insert_allow_deny_rules,
        "show.allow-deny-rules": fn_show_allow_deny_rules,

        "insert.user-info": fn_insert_user_info,
        "show.user-info": fn_show_user_info,

        "insert.zone": fn_insert_zone,
        "delete.zone": fn_delete_zone,
        "disable.zone": fn_disable_zone,
        "enable.zone": fn_enable_zone,
        "show.zone": fn_show_zone,

        "dump.": fn_dump_zone,
        "restore.": fn_restore_zone,
        "drop.": fn_drop_zone,
        "resetall.": fn_reset_database,
        "printall.": fn_print_database,

        "show.multiplexer": fn_show_multiplexer,

        "show.server-processes": fn_show_server_processes,
        "flush.server-processes": fn_flush_server_processes,
        "delete.server-processes": fn_delete_server_processes,

        "throw.decoy": fn_throw_decoy,

        "show.routing-table": fn_show_routing_table,
        "flush.routing-table": fn_flush_routing_table,
    }

    no_table_ops = {"dump", "restore", "drop", "resetall", "printall"}

    table = rest.pop(0) if args.operation not in no_table_ops else ""
    key = f"{args.operation}.{table}"
    fn = optbl.get(key)

    if fn is None:
        raise Exception(f"undefined operation: {args.operation} {table}")

    (nparams, varargsp) = get_nparams_of_fn(fn)
    logger.debug(f"@@@ NPARAMS = {nparams}  VARARGSP = {varargsp}")

    if not varargsp and len(rest) != nparams:
        sys.stderr.write("argument number\n")
        usage()
    return fn(*rest)


def get_nparams_of_fn(fn):
    sig = signature(fn)
    params = list(sig.parameters)
    nparams = len(params)
    varargsp = False
    if nparams > 0:
        v = sig.parameters.get(params[-1])
        if v.kind == v.VAR_POSITIONAL:
            varargsp = True
    return (nparams, varargsp)


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


def usage():
    progname = os.path.basename(sys.argv[0])
    sys.stderr.write(
        "usage:\n"
        f"     {progname} insert allow-deny-rules file\n"        # fn_insert_allow_deny_rules
        f"     {progname} show allow-deny-rules\n"               # fn_show_allow_deny_rules

        f"     {progname} insert user-info file\n"               # fn_insert_user_info
        f"     {progname} show user-info\n"                      # fn_show_user_info

        f"     {progname} insert zone Zone-ID jsonfile\n"        # fn_insert_zone
        f"     {progname} delete zone Zone-ID...\n"              # fn_delete_zone ...
        f"     {progname} disable zone Zone-ID...\n"             # fn_disable_zone ...
        f"     {progname} enable zone Zone-ID...\n"              # fn_enable_zone ...
        f"     {progname} show zone [--decrypt] [Zone-ID...]\n"  # fn_show_zone ...
        f"     {progname} dump\n"                                # fn_dump_zone
        f"     {progname} restore dump-file\n"                   # fn_restore_zone
        f"     {progname} drop\n"                                # fn_drop_zone
        f"     {progname} resetall\n"                            # fn_reset_database
        f"     {progname} printall\n"                            # fn_print_database

        f"     {progname} show multiplexer\n"                    # fn_show_multiplexer
        # f"     {progname} flush multiplexer\n" NOT IMPLEMENTED

        f"     {progname} show server-processes\n"               # fn_show_server_processes
        f"     {progname} flush server-processes\n"              # fn_flush_server_processes
        f"     {progname} delete server-processes [Server-ID...]\n"  # fn_delete_server_processes ...

        f"     {progname} throw decoy Zone-ID\n"                 # fn_throw_decoy

        f"     {progname} show routing-table\n"                  # fn_show_routing_table
        f"     {progname} flush routing-table\n"                 # fn_flush_routing_table
    )
    sys.exit(ERROR_ARGUMENT)


if __name__ == "__main__":
    main()
