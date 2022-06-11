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
import sys
import traceback
from lenticularis.control import Control_Api
from lenticularis.readconf import read_wui_conf
from lenticularis.poolutil import Api_Error
from lenticularis.poolutil import gather_pool_desc
from lenticularis.poolutil import check_user_naming
from lenticularis.utility import ERROR_EXIT_READCONF, ERROR_EXIT_EXCEPTION, ERROR_EXIT_ARGUMENT
from lenticularis.utility import format_rfc3339_z
from lenticularis.utility import objdump
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
        varargs = (v.kind == v.VAR_POSITIONAL)
    else:
        varargs = False
    return (nparams - 1, varargs)


def make_date_readable(d, keys):
    for key in keys:
        d[key] = format_rfc3339_z(float(d[key]))
        pass
    pass


def print_json_csv(table_name, c, formatting):
    if formatting in {"json"}:
        dump = json.dumps(c)
        print(f"{dump}")
    else:
        print(f"---- {table_name}")
        with io.StringIO() as out:
            writer = csv.writer(out)
            for r in c:
                writer.writerow(r)
            v = out.getvalue()
        print(f"{v}")
        pass
    pass


def print_json_plain(title, outs, formatting, order=None):
    if formatting in {"json"}:
        dump = json.dumps(outs)
        print(f"{dump}")
    else:
        print(f"---- {title}")
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
        assert all(r[0].upper() == "ADD" or r[0].upper() == "DELETE"
                   for r in rows)
        assert all(check_user_naming(e) for r in rows for e in r[1:])
        return [{"ADD": r[0].upper() == "ADD", "uid": r[1], "groups": r[2:]}
                for r in rows]
    pass


def _read_permit_list(path):
    """Reads a CSV file with rows: "ENABLE"/"DISABLE", "uid", "uid",
    "uid", ..., to load a permit-list.  Returns a list by changing the
    first column in uppercase.
    """
    with open(path, newline="") as f:
        rows = csv.reader(f, delimiter=",", quotechar='"')
        rows = list(rows)
        assert all(len(r) >= 2 for r in rows)
        assert all(r[0].upper() == "ENABLE" or r[0].upper() == "DISABLE"
                   for r in rows)
        assert all(check_user_naming(e) for r in rows for e in r[1:])
        return [[r[0].upper(), r[1]] for r in rows]
    pass


def _load_user(pool_adm, u):
    # It discards "permitted" and "modification_time" slots.
    now = int(time.time())
    uid = u["uid"]
    oldu = pool_adm.tables.get_user(uid)
    if oldu is not None:
        newu = {"uid": uid, "groups": u["groups"],
                "permitted": oldu["permitted"],
                "modification_time": now}
        pool_adm.tables.set_user(uid, newu)
    else:
        newu = {"uid": uid, "groups": u["groups"],
                "permitted": True,
                "modification_time": now}
        pool_adm.tables.set_user(uid, newu)
        pass
    pass


def _enable_disable_user(pool_adm, uid, permitted):
    u = pool_adm.tables.get_user(uid)
    if u is None:
        raise Api_Error(500, f"Bad user (unknown): {uid}")
    u["permitted"] = permitted
    pool_adm.tables.set_user(uid, u)
    pass


def _list_permit_list(pool_adm):
    users = pool_adm.tables.list_users()
    uu = [(uid, pool_adm.tables.get_user(uid)["permitted"])
          for uid in users]
    bid = [id for (id, permitted) in uu if permitted]
    ban = [id for (id, permitted) in uu if not permitted]
    rows = [["ENABLE", *bid], ["DISABLE", *ban]]
    return rows


def user_info_to_csv_row(uid, ui):
    # "permitted" entry is ignored.
    assert ui is not None
    return ["ADD", uid] + ui["groups"]


def _format_mux(m, formatting):
    (ep, desc) = m
    if formatting not in {"json"}:
        make_date_readable(desc, ["modification_time", "start_time"])
    return {ep: desc}


def pool_key_order(e):
    order = [
        "owner_uid",
        "owner_gid",
        "buckets_directory",
        "buckets",
        "access_keys",
        "minio_state",
        "minio_reason",
        "expiration_date",
        "permit_status",
        "online_status",
        "probe_key",
        "modification_time",
        "name",
        "bkt_policy",
        "access_key",
        "secret_key",
        "key_policy",
    ]
    return order.index(e) if e in order else len(order)


def _mux_key_order(e):
    order = [
        "host",
        "port",
        "mux_conf",
        "start_time",
        "modification_time",
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


def bucket_key_order(e):
    order = [
        "pool",
        "bkt_policy",
        "modification_time"]
    return order.index(e) if e in order else len(order)


def timestamp_key_order(e):
    order = [
        "pool",
        "timestamp"]
    return order.index(e) if e in order else len(order)


class Command():
    """Administration commands.  Api_Error is used as a placeholder and
    its status code is 500 always.
    """

    def __init__(self, traceid, pool_adm, args, rest):
        self._traceid = traceid
        self.pool_adm = pool_adm
        self.args = args
        self.rest = rest
        pass

    def op_help(self):
        """Print help."""
        prog = os.path.basename(sys.argv[0])
        print(f"USAGE")
        for (_, v) in self._op_dict.items():
            (fn, args, _) = v
            msg = inspect.getdoc(fn)
            msg = msg.replace("\n", "\n\t") if msg is not None else None
            print(f"{prog} {args}\n\t{msg}")
            pass
        sys.exit(ERROR_EXIT_ARGUMENT)
        pass

    def op_load_users(self, csvfile):
        """Load a user list from a file."""
        desc_list = _read_user_list(csvfile)
        adds = [{"uid": d["uid"], "groups": d["groups"]}
                for d in desc_list if d["ADD"]]
        dels = [{"uid": d["uid"], "groups": d["groups"]}
                for d in desc_list if not d["ADD"]]
        for u in dels:
            print(f"deleting a user: {u}")
            self.pool_adm.tables.delete_user(u["uid"])
            pass
        for u in adds:
            print(f"adding a user: {u}")
            _load_user(self.pool_adm, u)
            pass
        pass

    def op_show_users(self):
        """Print a user list."""
        users = self.pool_adm.tables.list_users()
        uu = [user_info_to_csv_row(id, self.pool_adm.tables.get_user(id))
              for id in users]
        print_json_csv("user info", uu, self.args.format)
        pass

    def op_load_permits(self, csvfile):
        """Load a user permit list from a file."""
        rules = _read_permit_list(csvfile)
        for row in rules:
            assert (len(row) >= 1
                    and (row[0] == "ENABLE" or row[0] == "DISABLE"))
            permitted = (row[0] == "ENABLE")
            for uid in row[1:]:
                _enable_disable_user(self.pool_adm, uid, permitted)
                pass
            pass
        pass

    def op_show_permits(self):
        """Print a user permit list."""
        rows = _list_permit_list(self.pool_adm)
        print_json_csv("user permit list", rows, self.args.format)
        pass

    def op_show_pool(self, *pool_id):
        """Show pools."""
        pool_list = set(pool_id)
        if pool_list == set():
            pool_list = self.pool_adm.tables.list_pools(None)
            pass
        pools = []
        for pid in pool_list:
            pooldesc = gather_pool_desc(self.pool_adm.tables, pid)
            if pooldesc is None:
                print(f"No pool found for {pid}")
                continue
            if self.args.format not in {"json"}:
                make_date_readable(pooldesc, ["expiration_date", "modification_time"])
                pass
            pooldesc.pop("pool_name")
            pools.append({pid: pooldesc})
            pass
        print_json_plain("pools", pools, self.args.format,
                         order=pool_key_order)
        pass

    def op_destruct_pool(self, *pool_id):
        """Delete pools by pool-id."""
        pool_list = pool_id
        for pid in pool_list:
            self.pool_adm.do_delete_pool(self._traceid, pid)
            pass
        pass

    def op_dump(self, users_or_pools):
        """Dumps users or pools.  Specify users or pools."""
        if users_or_pools.upper() == "USERS":
            user_list = self.pool_adm.tables.list_users()
            users = [self.pool_adm.tables.get_user(id) for id in user_list]
            data = json.dumps({"users": users})
            print(data)
        elif users_or_pools.upper() == "POOLS":
            pool_list = self.pool_adm.tables.list_pools(None)
            pools = [gather_pool_desc(self.pool_adm.tables, id)
                     for id in pool_list]
            data = json.dumps({"pools": pools})
            print(data)
        else:
            print(f"users-or_pools is either users or pools")
            pass
        pass

    def op_restore(self, jsonfile):
        """Restore users and pools from a file.  Pools are given new pool-ids.
        It is an error if some entries are already occupied: a
        buckets-directory, bucket names, and access-keys, (or etc.).
        Records of a file is {users: [...], pools: [...]}.
        """
        try:
            with open(jsonfile) as f:
                s = f.read()
                pass
        except OSError as e:
            sys.stderr.write(f"{jsonfile}: {os.strerror(e.errno)}\n")
            return
        except Exception as e:
            sys.stderr.write(f"{jsonfile}: {e}\n")
            traceback.print_exc()
            return
        desc = json.loads(s, parse_int=None)
        users = desc.get("users", [])
        pools = desc.get("pools", [])
        for u in users:
            _load_user(self.pool_adm, u)
            pass
        # Insert new pools.
        for pooldesc in pools:
            self._restore_pool(self._traceid, pooldesc)
            pass
        pass

    def _restore_pool(self, traceid, pooldesc):
        now = int(time.time())
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
        except Exception:
            raise
        # Add buckets.
        try:
            bkts = pooldesc["buckets"]
            for desc in bkts:
                bucket = desc["name"]
                bkt_policy = desc["bkt_policy"]
                self.pool_adm.do_make_bucket(traceid, pool_id,
                                             bucket, bkt_policy)
        except Exception:
            self.pool_adm.do_delete_pool(traceid, pool_id)
            raise
        # Add access-keys.
        try:
            keys = pooldesc["access_keys"]
            for k in keys:
                kid = k["access_key"]
                secret = k["secret_key"]
                key_policy = k["key_policy"]
                desc = k.copy()
                desc.pop("access_key")
                desc["use"] = "access_key"
                desc["owner"] = pool_id
                desc["modification_time"] = now
                ok = self.pool_adm.tables.set_ex_id(kid, desc)
                if not ok:
                    raise Api_Error(500, f"Duplicate access-key: {kid}")
                self.pool_adm.do_record_secret(traceid, pool_id,
                                               kid, secret, key_policy)
        except Exception:
            self.pool_adm.do_delete_pool(traceid, pool_id)
            raise
        pass

    def op_reset_db(self):
        """Clear all records in the DB."""
        if not self.args.yes:
            print("Need yes (-y) for action.")
        else:
            everything = self.args.everything
            self.pool_adm.tables.clear_all(everything=everything)
            pass
        pass

    def op_list_db(self):
        """List all DB keys."""
        self.pool_adm.tables.print_all()
        pass

    def op_show_manager(self, pool_id):
        """Show a manager of a pool."""
        ma = self.pool_adm.tables.get_minio_manager(pool_id)
        outs = [{pool_id: ma}]
        print_json_plain("manager", outs, self.args.format, order=proc_key_order)
        pass

    def op_show_minio(self, pool_id):
        """Show a MinIO process of a pool."""
        proc_list = self.pool_adm.tables.list_minio_procs(pool_id)
        process_list = sorted(list(proc_list))
        outs = [{pool: process} for (pool, process) in process_list]
        print_json_plain("minio", outs, self.args.format, order=proc_key_order)
        pass

    def op_list_ep(self):
        """List endpoints of Mux and MinIO."""
        # Mux.
        muxs = self.pool_adm.tables.list_muxs()
        muxs = sorted(list(muxs))
        outs = [_format_mux(m, self.args.format) for m in muxs]
        print_json_plain("mux", outs, self.args.format, order=_mux_key_order)
        # MinIO.
        eps = self.pool_adm.tables.list_minio_ep()
        eps = [{ep: {"pool": pid}} for (pid, ep) in eps]
        print_json_plain("minio", eps, self.args.format, order=bucket_key_order)
        pass

    def op_list_bucket(self):
        """List buckets."""
        bkts = self.pool_adm.tables.list_buckets(None)
        bkts = [{d["name"]: {"pool": d["pool"], "bkt_policy": d["bkt_policy"]}}
                for d in bkts]
        print_json_plain("buckets", bkts, self.args.format, order=bucket_key_order)
        pass

    def op_show_bucket(self, pool_id):
        """Show buckets of a pool."""
        bkts = self.pool_adm.tables.list_buckets(pool_id)
        print_json_plain("buckets", bkts, self.args.format, order=bucket_key_order)
        pass

    def op_list_timestamp(self):
        """Show timestamps."""
        stamps = self.pool_adm.tables.list_access_timestamps()
        stamps = [{d["pool"]:
                   {"timestamp": format_rfc3339_z(float(d["timestamp"]))}}
                  for d in stamps]
        print_json_plain("timestamps", stamps, self.args.format, order=timestamp_key_order)
        pass

    def op_delete_ep(self, *pool_id):
        """Deletes endpoint entires from a database.  Entries of
        MinIO-managers (ma:pool-id), MinIO-processes (mn:pool-id), and
        MinIO-eps (ep:pool-id) are deleted.
        """
        pool_list = pool_id
        for pid in pool_list:
            self.pool_adm.tables.delete_minio_manager(pid)
            self.pool_adm.tables.delete_minio_proc(pid)
            self.pool_adm.tables.delete_minio_ep(pid)
            pass
        pass

    op_list = [
        op_help,

        op_load_users,
        op_show_users,
        op_load_permits,
        op_show_permits,

        op_show_pool,
        op_show_manager,
        op_show_minio,
        op_show_bucket,
        op_list_ep,
        op_list_bucket,
        op_list_timestamp,

        op_destruct_pool,
        op_dump,
        op_restore,

        op_list_db,
        op_reset_db,
        op_delete_ep,
    ]

    def make_op_entry(self, fn, _):
        # sig.parameters=['self', 'csvfile']
        (_, varargs) = get_nparams_of_fn(fn)
        name = fn.__name__.removeprefix("op_").replace("_", "-")
        sig = inspect.signature(fn)
        pars = list(sig.parameters)
        self_ = pars.pop(0)
        assert self_ == "self"
        prog = [name, *pars] + (["..."] if varargs else [])
        prog = [s.replace("_", "-") for s in prog]
        usage = " ".join(prog)
        return (name, fn, usage, None)

    def make_op_dict(self):
        d = {name: (fn, args, None)
             for (name, fn, args, _)
             in (self.make_op_entry(fn, None)
                 for fn in self.op_list)}
        self._op_dict = d
        pass

    def execute_command(self):
        # fn = Command.optbl.get(self.args.operation)
        ent = self._op_dict.get(self.args.operation)
        # if fn is None:
        if ent is None:
            raise Exception(f"undefined operation: {self.args.operation}")
        (fn, _, _) = ent
        (nparams, varargs) = get_nparams_of_fn(fn)
        if not varargs and len(self.rest) != nparams:
            sys.stderr.write("Missing/excessive arguments for command.\n")
            self.op_help()
            pass
        try:
            fn(self, *self.rest)
        except Api_Error as e:
            sys.stderr.write(f"{e}.\n")
            pass
        pass

    pass


def main():
    # _commands = Command.optbl.keys()

    parser = argparse.ArgumentParser()
    # parser.add_argument("operation", choices=_commands)
    parser.add_argument("operation")
    parser.add_argument("--configfile", "-c")
    parser.add_argument("--format", "-f", choices=["text", "json"])
    parser.add_argument("--everything", type=bool, default=False)
    parser.add_argument("--yes", "-y", default=False,
                        action=argparse.BooleanOptionalAction)
    (args, rest) = parser.parse_known_args()

    try:
        (wui_conf, _) = read_wui_conf(args.configfile)
    except Exception as e:
        sys.stderr.write(f"Reading conf failed: {e}\n")
        sys.exit(ERROR_EXIT_READCONF)
        pass

    traceid = random_str(12)
    tracing.set(traceid)
    openlog(wui_conf["log_file"],
            **wui_conf["log_syslog"])

    try:
        pool_adm = Control_Api(wui_conf)
        cmd = Command(traceid, pool_adm, args, rest)
        cmd.make_op_dict()
        cmd.execute_command()
    except Exception as e:
        sys.stderr.write(f"Executing admin command failed: {e}\n")
        # print(traceback.format_exc())
        sys.exit(ERROR_EXIT_EXCEPTION)
        pass
    pass


if __name__ == "__main__":
    main()
