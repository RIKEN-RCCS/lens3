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
from lenticularis.poolutil import Api_Error
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


def _read_user_list(path):
    """Reads a CSV file with rows: "add"/"delete", "uid", "group",
    "group", ..., to load a user-list.  It adds an entry to the
    user-list if add="add", or deletes otherwise.
    """
    with open(path, newline="") as f:
        rows = csv.reader(f, delimiter=",", quotechar='"')
        rows = list(rows)
        print(f"AHO rows={rows}")
        assert all(r[0].upper() == "ADD" or r[0].upper() == "DELETE"
                   for r in rows)
        assert all(check_user_naming(e) for r in rows for e in r[1:])
        return [{"add": r[0].upper() == "ADD", "uid": r[1], "groups": r[2:]}
                for r in rows]
    pass


def _read_permit_list(path):
    """Reads a CSV file with rows: "enable"/"disable", "uid", "uid",
    "uid", ..., to load a permit-list.  Returns a list by changing the
    first column in uppercase.
    """
    with open(path, newline="") as f:
        rows = csv.reader(f, delimiter=",", quotechar='"')
        rows = list(rows)
        print(f"AHO rows={rows}")
        assert all(len(r) >= 2 for r in rows)
        assert all(r[0].upper() == "ENABLE" or r[0].upper() == "DISABLE"
                   for r in rows)
        assert all(check_user_naming(e) for r in rows for e in r[1:])
        return [[r[0].upper(), r[1]] for r in rows]
    pass


def _load_user_list(pool_adm, user_list):
    now = int(time.time())
    for e in user_list:
        id = e["uid"]
        oldu = pool_adm.tables.get_user(id)
        if e["add"] and oldu is not None:
            newu = {"uid": id, "groups": e["groups"],
                    "permitted": oldu["permitted"],
                    "modification_date": now}
            pool_adm.tables.set_user(id, newu)
        elif not e["add"] and oldu is not None:
            pool_adm.tables.delete_user(id)
        elif  e["add"] and oldu is None:
            newu = {"uid": id, "groups": e["groups"],
                    "permitted": True,
                    "modification_date": now}
            pool_adm.tables.set_user(id, newu)
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


def _store_user_info_add__(pool_adm, b):
    # New Entry (no right hand side)
    logger.debug(f"@@@ >> New {b}")
    pool_adm.tables.set_user(b["uid"], b)


def _store_user_info_delete__(pool_adm, e):
    # Deleted Entry (no left hand side)
    logger.debug(f"@@@ >> Delete {e}")
    pool_adm.delete_user(e)
    pass


def _store_user_info_update__(pool_adm, x):
    # Updated Entry
    (b, e) = x
    logger.debug(f"@@@ >> Update {b} {e}")
    pool_adm.tables.set_user(b["uid"], b)
    pass


def _restore_zone_delete(pool_adm, traceid, e):
    # Deleted Entry (no left hand side)
    user_id = e.get("owner_uid")
    zone_id = e.get("pool_name")
    logger.debug(f"@@@ >> Delete {user_id} {zone_id}")
    pool_adm.delete_zone(traceid, user_id, zone_id)
    pass


def _restore_zone_add(pool_adm, traceid, b):
    # New Entry (no right hand side)
    user_id = b.get("owner_uid")
    zone_id = b.get("pool_name")
    logger.debug(f"@@@ >> Insert / Update {user_id} {zone_id}")
    b.pop("pool_name")
    b.pop("minio_state")
    ##pool_adm.restore_pool(traceid, user_id, zone_id, b,
    ##                      include_atime=True, initialize=False)
    pass


def _restore_zone_update(pool_adm, traceid, x):
    # Updated Entry
    (b, e) = x
    _restore_zone_add(pool_adm, traceid, b)
    pass


def pool_key_order(e):
    order = [
        "owner_uid",
        "owner_gid",
        "root_secret",
        "access_keys",
        "buckets_directory",
        "buckets",
        #"direct_hostnames",
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


class Command():
    """Administration command support.  Status code to Api_Error is 500
    always."""

    def __init__(self, adm_conf, traceid, args, rest):
        self.adm_conf = adm_conf
        self.pool_adm = Pool_Admin(adm_conf)
        self._traceid = traceid
        self.args = args
        self.rest = rest
        pass

    def op_help(self):
        """Print help."""
        prog = os.path.basename(sys.argv[0])
        print(f"USAGE")
        for (k, v) in self.opdict.items():
            (fn, args, _) = v
            help = inspect.getdoc(fn)
            print(f"{prog} {args}\n\t{help}")
            pass
        sys.exit(ERROR_EXIT_ARGUMENT)
        pass

    def op_load_user_list(self, csvfile):
        """Loads a user list."""
        user_info = _read_user_list(csvfile)
        _load_user_list(self.pool_adm, user_info)
        ##fixed = self.pool_adm.fix_affected_zone(self._traceid)
        pass

    def op_show_user_list(self):
        """Prints a user list."""
        users = self.pool_adm.tables.list_users()
        uu = [user_info_to_csv_row(id, self.pool_adm.tables.get_user(id))
              for id in users]
        print_json_csv("user info", uu, self.args.format)
        pass

    def op_load_permit_list(self, csvfile):
        """Loads a permit list."""
        rules = _read_permit_list(csvfile)
        for row in rules:
            assert (len(row) >= 1
                    and (row[0] == "ENABLE" or row[0] == "DISABLE"))
            permitted = (row[0] == "ENABLE")
            for id in row[1:]:
                self._enable_disable_user(id, permitted)
                pass
            pass
        pass

    def _enable_disable_user(self, id, permitted):
        u = self.pool_adm.tables.get_user(id)
        if u is None:
            raise Api_Error(500, f"Bad user (unknown): {id}")
        u["permitted"] = permitted
        self.pool_adm.tables.set_user(id, u)
        pass

    def op_show_permit_list(self):
        """Shows a permit list."""
        rows = self._list_permit_list()
        print_json_csv("allow deny rules", rows, self.args.format)
        pass

    def _list_permit_list(self):
        users = self.pool_adm.tables.list_users()
        uu = [(id, self.pool_adm.tables.get_user(id)["permitted"])
              for id in users]
        bid = [id for (id, permitted) in uu if permitted]
        ban = [id for (id, permitted) in uu if not permitted]
        rows = [["ENABLE", *bid], ["DISABLE", *ban]]
        return rows

    def op_show_pool(self, *pool_id_dotdotdot):
        """Show pools."""
        pool_list = set(pool_id_dotdotdot)
        if pool_list == set():
            pool_list = self.pool_adm.tables.list_pools(None)
            pass
        pools = []
        for pool_id in pool_list:
            pooldesc = self.pool_adm.gather_pool_desc(pool_id)
            if pooldesc is None:
                continue
            if self.args.format not in {"json"}:
                fix_date_format(pooldesc, ["expiration_date"])
                pass
            pooldesc.pop("pool_name")
            pools.append({pool_id: pooldesc})
            pass
        print_json_plain("pools", pools, self.args.format, order=pool_key_order)
        pass

    def op_delete_pool(self, *pool_id_dotdotdot):
        """Delete pools by pool-id."""
        for pool_id in pool_id_dotdotdot:
            self.pool_adm.do_delete_pool(self._traceid, pool_id)
            pass
        pass

    def op_insert_zone(self, zone_id, jsonfile):
        """insert-zone."""
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
        ##self.pool_adm.restore_pool(self._traceid, user_id, zone_id, zone,
        ##                           include_atime=False, initialize=True)
        pass

    def op_dump_pools(self):
        """Dumps users and pools."""
        user_list = self.pool_adm.tables.list_users()
        users = [self.pool_adm.tables.get_user(id) for id in user_list]
        pool_list = self.pool_adm.tables.list_pools(None)
        pools = [self.pool_adm.gather_pool_desc(id) for id in pool_list]
        dump_data = json.dumps({"users": users, "pools": pools})
        print(dump_data)
        pass

    def op_restore_pools(self, jsonfile):
        """Restore users and pools from a file."""
        with open(jsonfile) as f:
            data = f.read()
            pass
        jj = json.loads(data, parse_int=None)
        users = jj["users"]
        pools = jj["pools"]
        _load_user_list(self.pool_adm, users)
        pool_list = [d["pool_name"] for d in pools]
        # Delete the pools if exist, first.
        for pool_id in pool_list:
            if self.pool_adm.tables.get_pool(pool_id) is not None:
                self.pool_adm.do_delete_pool(self._traceid, pool_id)
                pass
            pass
        # Insert new pools.
        for pooldesc in pools:
            self._restore_pool(self._traceid, pooldesc)
            pass
        pass

    def _restore_pool(self, traceid, pooldesc):
        user_id = pooldesc["owner_uid"]
        owner_gid = pooldesc["owner_gid"]
        path = pooldesc["buckets_directory"]
        u = self.pool_adm.tables.get_user(user_id)
        if u is None:
            raise Api_Error(500, f"Bad user (unknown): {user_id}")
        if owner_gid not in u["groups"]:
            raise Api_Error(500, f"Bad group for a user: {owner_gid}")
        # Add a new pool.
        try:
            pool_id = self.pool_adm.do_make_pool(traceid, user_id,
                                                 owner_gid, path)
            assert pool_id is not None
            pooldesc["pool_name"] = pool_id
        except Exception as e:
            raise
        now = int(time.time())
        # Add buckets.
        try:
            bkts = pooldesc["buckets"]
            for desc in bkts:
                bucket= desc["name"]
                bkt_policy = desc["bkt_policy"]
                self.pool_adm.do_make_bucket(traceid, pool_id,
                                             bucket, bkt_policy)
        except Exception as e:
            self.pool_adm.do_delete_pool(traceid, pool_id)
            raise
        # Add access-keys.
        try:
            keys = pooldesc["access_keys"]
            for k in keys:
                id = k["access_key"]
                secret = k["secret_key"]
                key_policy = k["key_policy"]
                desc = k.copy()
                desc.pop("access_key")
                desc["owner"]= pool_id
                ok = self.pool_adm.tables.set_ex_id(id, desc)
                if not ok:
                    raise Api_Error(500, f"Duplicate access-key: {id}")
                self.pool_adm.do_record_secret(traceid, pool_id,
                                               id, secret, key_policy)
        except Exception as e:
            self.pool_adm.do_delete_pool(traceid, pool_id)
            raise
        pass

    def op_drop_zone(self):
        """drop-zone"""
        everything = self.args.everything
        ##self.pool_adm.flush_storage_table(everything=everything)
        pass

    def op_reset_db(self):
        """reset-db"""
        everything = self.args.everything
        self._reset_database(everything=everything)
        pass

    def _reset_database(self, everything=False):
        self.pool_adm.tables.storage_table.clear_all(everything=everything)
        self.pool_adm.tables.process_table.clear_all(everything=everything)
        self.pool_adm.tables.routing_table.clear_routing(everything=everything)
        self.pool_adm.tables.pickone_table.clear_all(everything=everything)
        return

    def op_list_db(self):
        """list-db"""
        self._print_database()
        pass

    def _print_database(self):
        self.pool_adm.tables.storage_table.print_all()
        self.pool_adm.tables.process_table.print_all()
        self.pool_adm.tables.routing_table.print_all()
        self.pool_adm.tables.pickone_table.print_all()
        return

    def op_show_muxs(self):
        """show-muxs"""
        muxs = self.pool_adm.tables.process_table.list_muxs()
        muxs = sorted(list(muxs))
        outs = [format_mux(m, self.args.format) for m in muxs]
        print_json_plain("muxs", outs, self.args.format, order=_mux_key_order)
        pass

    def op_show_server_processes(self):
        """show-minios"""
        proc_list = self.pool_adm.tables.process_table.list_minio_procs(None)
        process_list = sorted(list(proc_list))
        outs = [{pool: process} for (pool, process) in process_list]
        print_json_plain("servers", outs, self.args.format, order=proc_key_order)
        pass

    def op_flush_server_processes(self):
        """flush-server-processes"""
        everything = self.args.everything
        self.pool_adm.tables.process_table.clear_all(everything=everything)
        pass

    def op_delete_server_processes(self, *pool_id_dotdotdot):
        """delete-server-processes"""
        for pool_id in pool_id_dotdotdot:
            self.pool_adm.tables.process_table.delete_minio_proc(pool_id)
            pass
        pass

    def op_throw_decoy(self, zone_id):
        """throw-decoy"""
        self.pool_adm.access_mux_for_pool(self._traceid, zone_id, force=True)
        pass

    def op_show_routing_table(self):
        """show-routing"""
        pairs = self.pool_adm.tables.routing_table.list_routes()
        print_json_plain("routing table", pairs, self.args.format, order=route_key_order)
        pass

    ##def op_show_routing_table(self):
    ##    (akey_list, host_list, atime_list) = self.pool_adm.fetch_route_list()
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

    def op_flush_routing_table(self):
        """clear-routing"""
        everything = self.args.everything
        self.pool_adm.tables.routing_table.clear_routing(everything=everything)
        pass

    op_list = [
        op_help,

        op_load_user_list,
        op_show_user_list,

        op_load_permit_list,
        op_show_permit_list,

        op_show_pool,
        op_delete_pool,
        op_insert_zone,

        op_dump_pools,
        op_restore_pools,
        op_drop_zone,

        op_reset_db,
        op_list_db,

        op_show_muxs,

        op_show_server_processes,
        op_flush_server_processes,
        op_delete_server_processes,

        op_throw_decoy,

        op_show_routing_table,
        op_flush_routing_table,
    ]

    def make_op_entry(self, fn, _):
        # sig.parameters=['self', 'csvfile']
        (nparams, varargs) = get_nparams_of_fn(fn)
        name = fn.__name__.removeprefix("op_").replace("_", "-")
        sig = inspect.signature(fn)
        pars = list(sig.parameters)
        self_ = pars.pop(0)
        assert self_ == "self"
        prog = [name, *pars]
        usage = " ".join(prog)
        return (name, fn, usage, None)

    def make_op_dict(self):
        d = {name: (fn, args, None)
             for (name, fn, args, _)
             in (self.make_op_entry(fn, None)
                 for fn in self.op_list)}
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
            self.op_help()
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
        ##pool_adm = Pool_Admin(adm_conf)
        adm = Command(adm_conf, traceid, args, rest)

        adm.make_op_dict()

        adm.execute_command()
    except Exception as e:
        sys.stderr.write(f"Executing admin command failed: {e}\n")
        print(traceback.format_exc())
        ##adm.op_help()
        sys.exit(ERROR_EXIT_EXCEPTION)
        pass
    pass


if __name__ == "__main__":
    main()
