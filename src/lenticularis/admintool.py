"""lenticularis-admin command."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import csv
import inspect
import io
import os
import time
import json
#import threading
import sys
import traceback
from lenticularis.pooladmin import Pool_Admin
from lenticularis.readconf import read_adm_conf
from lenticularis.poolutil import check_user_naming
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
        pass
    pass


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
        pass
    pass


def print_json_plain(table_name, outs, formatting, order=None):
    if formatting in {"json"}:
        dump = json.dumps(outs)
        print(f"{dump}")
    else:
        print(f"----- {table_name}")
        for d in outs:
            dump = objdump(d, order=order)
            print(f"{dump}")
            pass
        pass
    pass


def read_allow_deny_rules(path):
    with open(path, newline="") as f:
        r = csv.reader(f, delimiter=",", quotechar='"')
        return [[row[0].lower(), row[1]] for row in r]
    pass


def _read_user_list(path):
    """Reads a CSV file with rows: "add"/"delete", "uid", "group",
    "group", ..., to load a user-list.  It adds an entry to the
    user-list if add="add", or deletes otherwise.

    """
    with open(path, newline="") as f:
        rows = csv.reader(f, delimiter=",", quotechar='"')
        rows = list(rows)
        print(f"rows={rows}")
        assert all(r[0].upper() == "ADD" or r[0].upper() == "DELETE"
                   for r in rows)
        assert all(check_user_naming(e) for r in rows for e in r[1:])
        return [{"add": r[0].upper() == "ADD", "uid": r[1], "groups": r[2:]}
                for r in rows]
    pass


def _load_user_list(zone_adm, user_list):
    now = int(time.time())
    for e in user_list:
        id = e["uid"]
        oldu = zone_adm.tables.get_user(id)
        if e["add"] and oldu is not None:
            newu = {"uid": id, "groups": e["groups"],
                    "permitted": oldu["permitted"],
                    "modification_date": now}
            zone_adm.tables.set_user(id, newu)
        elif not e["add"] and oldu is not None:
            zone_adm.tables.delete_user(id)
        elif  e["add"] and oldu is None:
            newu = {"uid": id, "groups": e["groups"],
                    "permitted": True,
                    "modification_date": now}
            zone_adm.tables.set_user(id, newu)
        else:
            pass
        pass
    pass


def user_info_to_csv_row(id, ui):
    # "permitted" entry is ignored.
    assert ui is not None
    return ["add", id] + ui["groups"]


def format_mux(m, formatting):
    (ep, desc) = m
    if formatting not in {"json"}:
        fix_date_format(desc, ["last_interrupted_time", "start_time"])
    return {ep: desc}


def _store_user_info_add__(zone_adm, b):
    # New Entry (no right hand side)
    logger.debug(f"@@@ >> New {b}")
    zone_adm.tables.set_user(b["uid"], b)


def _store_user_info_delete__(zone_adm, e):
    # Deleted Entry (no left hand side)
    logger.debug(f"@@@ >> Delete {e}")
    zone_adm.delete_user(e)
    pass


def _store_user_info_update__(zone_adm, x):
    # Updated Entry
    (b, e) = x
    logger.debug(f"@@@ >> Update {b} {e}")
    zone_adm.tables.set_user(b["uid"], b)
    pass


def _restore_zone_delete(zone_adm, traceid, e):
    # Deleted Entry (no left hand side)
    user_id = e.get("owner_uid")
    zone_id = e.get("pool_name")
    logger.debug(f"@@@ >> Delete {user_id} {zone_id}")
    zone_adm.delete_zone(traceid, user_id, zone_id)
    pass


def _restore_zone_add(zone_adm, traceid, b):
    # New Entry (no right hand side)
    user_id = b.get("owner_uid")
    zone_id = b.get("pool_name")
    logger.debug(f"@@@ >> Insert / Update {user_id} {zone_id}")
    b.pop("pool_name")
    b.pop("minio_state")
    zone_adm.restore_pool(traceid, user_id, zone_id, b,
                          include_atime=True, initialize=False)
    pass


def _restore_zone_update(zone_adm, traceid, x):
    # Updated Entry
    (b, e) = x
    _restore_zone_add(zone_adm, traceid, b)
    pass


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
        "bkt_policy"]
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
        self.zone_adm = Pool_Admin(adm_conf)
        self.traceid = traceid
        self.args = args
        self.rest = rest
        pass

    def fn_help(self):
        prog = os.path.basename(sys.argv[0])
        print(f"USAGE")
        for (k, v) in self.opdict.items():
            (fn, args, help) = v
            print(f"{prog} {args}\n\t{help}")
            pass
        sys.exit(ERROR_EXIT_ARGUMENT)
        pass

    def fn_load_permit_list(self, csvfile):
        logger.debug(f"@@@ INSERT ALLOW DENY RULES")
        rules = read_allow_deny_rules(csvfile)
        logger.debug(f"@@@ rules = {rules}")
        self.zone_adm.store_allow_deny_rules(rules)
        fixed = self.zone_adm.fix_affected_zone(self.traceid)
        logger.debug(f"@@@ fixed = {fixed}")
        pass

    def fn_show_permit_list(self):
        rules = self.zone_adm.fetch_allow_deny_rules()
        print_json_csv("allow deny rules", rules, self.args.format)
        pass

    def fn_load_user_list(self, csvfile):
        user_info = _read_user_list(csvfile)
        _load_user_list(self.zone_adm, user_info)
        fixed = self.zone_adm.fix_affected_zone(self.traceid)
        pass

    def fn_show_user_list(self):
        users = self.zone_adm.tables.list_users()
        uu = [user_info_to_csv_row(id, self.zone_adm.tables.get_user(id))
              for id in users]
        print_json_csv("user info", uu, self.args.format)
        pass

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
        pass

    def fn_delete_zone(self, *zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.delete_zone(self.traceid, user_id, zone_id)
            pass
        pass

    def fn_disable_zone(self, *zoneIDs):
        logger.debug(f"@@@ DISABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.disable_zone(self.traceid, user_id, zone_id)
            pass
        pass

    def fn_enable_zone(self, *zoneIDs):
        logger.debug(f"@@@ ENABLE ZONE")
        for zone_id in zoneIDs:
            user_id = self.zone_adm.zone_to_user(zone_id)
            self.zone_adm.enable_zone(self.traceid, user_id, zone_id)
            pass
        pass

    def fn_show_zone(self, *zoneIDs):
        decrypt = False
        if len(zoneIDs) > 0 and zoneIDs[0] == "--decrypt":
            zoneIDs = list(zoneIDs)
            zoneIDs.pop(0)
            decrypt = True
            pass
        zoneIDs = set(zoneIDs)
        (zone_list, broken_zone) = self.zone_adm.fetch_zone_list(None, extra_info=True, include_atime=True, decrypt=decrypt)
        outs = []
        for zone in zone_list:
            zone_id = zone["pool_name"]
            if zoneIDs != set() and zone_id not in zoneIDs:
                continue
            if self.args.format not in {"json"}:
                fix_date_format(zone, ["atime", "expiration_date"])
                pass
            zone.pop("pool_name")
            outs.append({zone_id: zone})
            pass
        print_json_plain("zones", outs, self.args.format, order=pool_key_order)
        logger.debug(f"broken zones: {broken_zone}")
        pass

    def fn_dump_zone(self):
        rules = self.zone_adm.fetch_allow_deny_rules()
        unix_users = self.zone_adm.tables.list_users()
        users = [self.zone_adm.tables.get_user(id) for id in unix_users]
        (zone_list, _) = self.zone_adm.fetch_zone_list(None, include_atime=True)
        dump_data = json.dumps({"rules": rules, "users": users, "zones": zone_list})
        print(dump_data)
        pass

    def fn_restore_zone(self, dump_file):
        logger.debug(f"@@@ INSERT ZONE")
        with open(dump_file) as f:
            dump_data = f.read()
            pass
        j = json.loads(dump_data, parse_int=None)
        rules = j["rules"]
        user_info = j["users"]
        zone_list = j["zones"]
        self.zone_adm.store_allow_deny_rules(rules)
        _load_user_list(self.zone_adm, user_info)
        (existing, _) = self.zone_adm.fetch_zone_list(None)
        (ll, pp, rr) = list_diff3(zone_list, lambda b: b.get("pool_name"),
                                  existing, lambda e: e.get("pool_name"))
        for x in rr:
            _restore_zone_delete(self.zone_adm, self.traceid, x)
            pass
        for x in ll:
            _restore_zone_add(self.zone_adm, self.traceid, x)
            pass
        for x in pp:
            _restore_zone_update(self.zone_adm, self.traceid, x)
            pass
        pass

    def fn_drop_zone(self):
        everything = self.args.everything
        self.zone_adm.flush_storage_table(everything=everything)
        pass

    def fn_reset_db(self):
        everything = self.args.everything
        self.zone_adm.reset_database(everything=everything)
        pass

    def fn_list_db(self):
        self.zone_adm.print_database()
        pass

    def fn_show_muxs(self):
        muxs = sorted(list(self.zone_adm.fetch_multiplexer_list()))
        outs = [format_mux(m, self.args.format) for m in muxs]
        print_json_plain("muxs", outs, self.args.format, order=_mux_key_order)
        pass

    def fn_show_server_processes(self):
        process_list = sorted(list(self.zone_adm.fetch_process_list()))
        logger.debug(f"@@@ process_list = {process_list}")
        outs = [{zone: process} for (zone, process) in process_list]
        print_json_plain("servers", outs, self.args.format, order=proc_key_order)
        pass

    def fn_flush_server_processes(self):
        everything = self.args.everything
        logger.debug(f"@@@ EVERYTHING = {everything}")
        self.zone_adm.flush_process_table(everything=everything)
        pass

    def fn_delete_server_processes(self, *processIDs):
        logger.debug(f"@@@ DELETE = {processIDs}")
        for processID in processIDs:
            logger.debug(f"@@@ DELETE = {processID}")
            self.zone_adm.delete_process(processID)
            pass
        pass

    def fn_throw_decoy(self, zone_id):
        logger.debug(f"@@@ THROW DECOY zone_id = {zone_id}")
        self.zone_adm.access_mux_for_pool(self.traceid, zone_id, force=True)
        pass

    def fn_show_routing_table(self):
        pairs = self.zone_adm.tables.routing_table.list_routes()
        print_json_plain("routing table", pairs, self.args.format, order=route_key_order)
        pass

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
        pass

    op_help_list = [
        (fn_help, "Print help."),

        (fn_load_user_list, "Loads user list."),
        (fn_show_user_list, "Prints user list."),

        (fn_load_permit_list, "Loads permit list."),
        (fn_show_permit_list, "Shows permit list."),

        (fn_insert_zone, "insert-zone"),
        (fn_delete_zone, "delete-zone"),
        (fn_disable_zone, "disable-zone"),
        (fn_enable_zone, "enable-zone"),
        (fn_show_zone, "show-zone"),

        (fn_dump_zone, "dump-zone"),
        (fn_restore_zone, "restore-zone"),
        (fn_drop_zone, "drop-zone"),

        (fn_reset_db, "reset-db"),
        (fn_list_db, "list-db"),

        (fn_show_muxs, "show-muxs"),

        (fn_show_server_processes, "show-minios"),
        (fn_flush_server_processes, "flush-server-processes"),
        (fn_delete_server_processes, "delete-server-processes"),

        (fn_throw_decoy, "throw-decoy"),

        (fn_show_routing_table, "show-routing"),
        (fn_flush_routing_table, "clear-routing"),
    ]

    def make_op_help_entry(self, fn, help):
        # sig.parameters=['self', 'csvfile']
        (nparams, varargs) = get_nparams_of_fn(fn)
        name = fn.__name__.removeprefix("fn_").replace("_", "-")
        sig = inspect.signature(fn)
        pars = list(sig.parameters)
        self_ = pars.pop(0)
        assert self_ == "self"
        prog = [name, *pars]
        usage = " ".join(prog)
        return (name, fn, usage, help)

    def make_op_dict(self):
        d = {name: (fn, args, help)
             for (name, fn, args, help)
             in (self.make_op_help_entry(fn, help)
                 for (fn, help) in self.op_help_list)}
        self.opdict = d
        pass

    def execute_command(self):
        # fn = Command.optbl.get(self.args.operation)
        ent = self.opdict.get(self.args.operation)
        # if fn is None:
        if ent is None:
            raise Exception(f"undefined operation: {self.args.operation}")
        (fn, _, _) = ent
        (nparams, varargsp) = get_nparams_of_fn(fn)
        if not varargsp and len(self.rest) != nparams:
            sys.stderr.write("Missing/excessive arguments for command.\n")
            self.fn_help()
            pass
        return fn(self, *self.rest)

    pass


def main():
    # _commands = Command.optbl.keys()

    parser = argparse.ArgumentParser()
    #parser.add_argument("operation",
    #choices=_commands)
    parser.add_argument("operation")
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
        pass

    traceid = random_str(12)
    #threading.current_thread().name = traceid
    tracing.set(traceid)
    openlog(adm_conf["log_file"],
            **adm_conf["log_syslog"])
    ##logger.info("**** START ADMIN ****")
    logger.debug(f"traceid = {traceid}")

    try:
        logger.debug(f"@@@ MAIN")
        ##zone_adm = Pool_Admin(adm_conf)
        adm = Command(adm_conf, traceid, args, rest)

        adm.make_op_dict()

        adm.execute_command()
    except Exception as e:
        sys.stderr.write(f"Executing admin command failed: {e}\n")
        print(traceback.format_exc())
        ##adm.fn_help()
        sys.exit(ERROR_EXIT_EXCEPTION)
        pass
    pass


if __name__ == "__main__":
    main()
