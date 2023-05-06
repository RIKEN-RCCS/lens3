"""lens3-admin command.  It provides a way to directly modify
databases.
"""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import csv
import inspect
import io
import os
import time
import json
import yaml
import sys
import traceback
from lenticularis.control import Control_Api
from lenticularis.control import erase_minio_ep, erase_pool_data, make_new_pool
from lenticularis.table import read_redis_conf
from lenticularis.table import get_table
from lenticularis.table import set_conf, get_conf
from lenticularis.yamlconf import read_yaml_conf
from lenticularis.pooldata import Api_Error
from lenticularis.pooldata import gather_pool_desc
from lenticularis.pooldata import check_user_naming
from lenticularis.pooldata import check_claim_string
from lenticularis.pooldata import get_pool_owner_for_messages
from lenticularis.pooldata import dump_db, restore_db
from lenticularis.utility import ERROR_EXIT_BADCONF, ERROR_EXIT_EXCEPTION, ERROR_EXIT_ARGUMENT
from lenticularis.utility import format_time_z
from lenticularis.utility import random_str
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger, openlog
from lenticularis.utility import tracing


def _get_nparams_of_fn(fn):
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


def _make_time_readable(d, keys):
    """Replaces date+time values by strings."""
    for key in keys:
        d[key] = format_time_z(float(d[key]))
        pass
    pass


def _print_in_csv(rows):
    with io.StringIO() as os:
        writer = csv.writer(os)
        for r in rows:
            writer.writerow(r)
            pass
        v = os.getvalue()
        pass
    print(f"{v}")
    pass


def _print_in_yaml(o):
    s = yaml.dump(o, default_flow_style=False, sort_keys=False, indent=4)
    print(f"{s}", end='', flush=True)
    pass


def _make_csv_user_list_entry(r):
    assert len(r) >= 2
    op = r[0].upper()
    if op == "ADD":
        # Row-entry: ADD,uid,claim,group,...
        assert len(r) >= 4
        assert check_user_naming(r[1])
        assert check_claim_string(r[2])
        assert all(check_user_naming(e) for e in r[3:])
        return {"op": op, "uid": r[1], "claim": r[2], "groups": list(r[3:])}
    elif op == "DELETE":
        # Row-entry: DELETE,uid,...
        assert all(check_user_naming(e) for e in r[1:])
        return {"op": op, "uids": list(r[1:])}
    elif op == "ENABLE":
        # Row-entry: ENABLE,uid,...
        assert all(check_user_naming(e) for e in r[1:])
        return {"op": op, "uids": list(r[1:])}
    elif op == "DISABLE":
        # Row-entry: DISABLE,uid,...
        assert all(check_user_naming(e) for e in r[1:])
        return {"op": op, "uids": list(r[1:])}
    else:
        assert (r[0].upper() == "ADD"
                or r[0].upper() == "DELETE"
                or r[0].upper() == "ENABLE"
                or r[0].upper() == "DISABLE")
        return {}
    pass


def _read_csv_user_list(path):
    with open(path, newline="") as f:
        rows = csv.reader(f, delimiter=",", quotechar='"')
        rows = list(rows)
        return [_make_csv_user_list_entry(r) for r in rows]
    pass


def _load_user(tables, u):
    # It copies the "enabled" slot and updates the "modification_time" slot.
    now = int(time.time())
    uid = u["uid"]
    oldu = tables.get_user(uid)
    if oldu is not None:
        newu = {"uid": uid,
                "claim": u["claim"],
                "groups": u["groups"],
                "enabled": oldu["enabled"],
                "modification_time": now}
        tables.set_user(newu)
    else:
        newu = {"uid": uid,
                "claim": u["claim"],
                "groups": u["groups"],
                "enabled": True,
                "modification_time": now}
        tables.set_user(newu)
        pass
    pass


def _enable_disable_user(tables, uid, enabled):
    u = tables.get_user(uid)
    if u is None:
        raise Api_Error(500, f"Bad user (unknown): {uid}")
    u["enabled"] = enabled
    tables.set_user(u)
    pass


def _make_disable_csv_rows(tables):
    """Returns rows (though it is a single row) of disabled entries or an
    empty list.  It does not return enabled entries.
    """
    users = tables.list_users()
    uu = [(uid, tables.get_user(uid)["enabled"])
          for uid in users]
    bid = [id for (id, enabled) in uu if enabled]
    ban = [id for (id, enabled) in uu if not enabled]
    return [["DISABLE", *ban]] if len(ban) != 0 else []


def _make_user_csv_row(uid, u):
    # It discards "enabled" and "modification_time" slots.
    assert u is not None
    return ["ADD", uid, u["claim"]] + u["groups"]


def _format_mux(m, formatting):
    (ep, desc) = m
    if formatting not in {"json"}:
        _make_time_readable(desc, ["modification_time", "start_time"])
    return {ep: desc}


def _pool_key_order(e):
    order = [
        "owner_uid",
        "owner_gid",
        "buckets_directory",
        "buckets",
        "access_keys",
        "minio_state",
        "minio_reason",
        "expiration_time",
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


def _proc_key_order(e):
    order = [
        "minio_ep",
        "minio_pid",
        "mux_host",
        "mux_port",
        "manager_pid"]
    return order.index(e) if e in order else len(order)


def _directory_key_order(e):
    order = [
        "directory",
        "pool"]
    return order.index(e) if e in order else len(order)


def _bucket_key_order(e):
    order = [
        "pool",
        "bkt_policy",
        "modification_time"]
    return order.index(e) if e in order else len(order)


def _timestamp_key_order(e):
    order = [
        "pool",
        "timestamp"]
    return order.index(e) if e in order else len(order)


def _determine_expiration_time(maxexpiry):
    now = int(time.time())
    duration = maxexpiry
    return (now + duration)


class Command():
    """Administration commands.  Api_Error is used as a placeholder and
    its status code is 500 always.
    """

    def __init__(self, traceid, redis, args, rest):
        self._traceid = traceid
        self._redis = redis
        self.args = args
        self.rest = rest
        self._tables = get_table(redis)
        # self._api_conf = get_conf("api", None, redis)
        pass

    def op_help(self):
        """Prints help.  Use option -d for debugging lens3-admin.  Some
        commands needs an Api configuration in Redis.  Use "load-conf"
        first at a system (re-)initialization.
        """
        prog = os.path.basename(sys.argv[0])
        print(f"USAGE")
        for (_, v) in self._command_dict.items():
            (fn, args, _) = v
            msg = inspect.getdoc(fn)
            msg = msg.replace("\n", "\n\t") if msg is not None else None
            print(f"{prog} {args}\n\t{msg}")
            pass
        sys.exit(ERROR_EXIT_ARGUMENT)
        pass

    def op_load_conf(self, yamlfile):
        """Loads a yaml conf file in Redis.  (There is no command to delete a
        conf, currenly).
        """
        conf = read_yaml_conf(yamlfile)
        set_conf(conf, self._redis)
        pass

    def op_list_conf(self):
        """Prints a list of conf data in yaml."""
        conflist = self._tables.list_confs()
        for e in conflist:
            print(f"---")
            print(f"# Conf {e['subject']}")
            _print_in_yaml(e)
            pass
        pass

    def op_load_user(self, csvfile):
        """Adds or deletes users from a CSV file.  It reads a CSV file with
        rows starting with one of: "ADD", "DELETE", "ENABLE", or
        "DISABLE".  An add-row is: ADD,uid,claim,group,... (the rest
        is a group list).  The claim is an X-REMOTE-USER key or empty.
        A group list needs at least one entry.  Adding a row
        overwrites the old one but keeps an enabled state.  A delete
        rows takes a uid list: DELETE,uid,...; and similar for ENABLE
        or DISABLE.  It processes all add rows first, then the delete
        rows, enable rows, and disable rows in this order.  DO NOT PUT
        SPACES AROUND A COMMA OR TRAILING COMMAS IN CSV.
        """
        desclist = _read_csv_user_list(csvfile)
        adds = [{"uid": d["uid"], "claim": d["claim"], "groups": d["groups"]}
                for d in desclist if d["op"] == "ADD"]
        dels = [u for d in desclist if d["op"] == "DELETE"
                for u in d["uids"]]
        enbs = [u for d in desclist if d["op"] == "ENABLE"
                for u in d["uids"]]
        diss = [u for d in desclist if d["op"] == "DISABLE"
                for u in d["uids"]]
        for u in adds:
            print(f"adding a user: {u}")
            _load_user(self._tables, u)
            pass
        for u in dels:
            print(f"deleting a user: {u}")
            self._tables.delete_user(u)
            pass
        for u in enbs:
            print(f"enabling a user: {u}")
            _enable_disable_user(self._tables, u, True)
            pass
        for u in diss:
            print(f"disabling a user: {u}")
            _enable_disable_user(self._tables, u, False)
            pass
        pass

    def op_list_user(self):
        """Prints a user list in CSV.  It lists ADD rows first, and then
        a DISABLE row.
        """
        users = self._tables.list_users()
        urows = [_make_user_csv_row(id, self._tables.get_user(id))
                 for id in users]
        drows = _make_disable_csv_rows(self._tables)
        _print_in_csv(urows + drows)
        pass

    def op_list_pool(self, *pool_id):
        """Prints pools.  It shows all pools without arguments."""
        pool_list = list(pool_id)
        if pool_list == []:
            pool_list = self._tables.list_pools(None)
            pass
        pools = []
        for pid in pool_list:
            pooldesc = gather_pool_desc(self._tables, pid)
            if pooldesc is None:
                print(f"No pool found for {pid}")
                continue
            if self.args.format not in {"json"}:
                _make_time_readable(pooldesc, ["expiration_time", "modification_time"])
                pass
            pooldesc.pop("pool_name")
            pools.append({pid: pooldesc})
            pass
        for o in pools:
            _print_in_yaml(o)
            pass
        pass

    def op_delete_pool(self, *pool_id):
        """Deletes pools by pool-id."""
        if not self.args.yes:
            print("Need yes (-y) for action.")
        else:
            pool_list = list(pool_id)
            traceid = self._traceid
            for pid in pool_list:
                erase_minio_ep(self._tables, pid)
                erase_pool_data(self._tables, pid)
                pass
            pass
        pass

    def op_list_bucket(self):
        """Prints all buckets and all buckets-directories of pools."""
        # pool_list = list(pool_id)
        # if pool_list == []:
        #     bkts = self._tables.list_buckets(None)
        # else:
        #     bkts = [b for pid in pool_list
        #             for b in self._tables.list_buckets(pid)]
        #     pass
        # List Buckets.
        allbkts = self._tables.list_buckets(None)
        bkts = [{d["name"]: {"pool": d["pool"], "bkt_policy": d["bkt_policy"]}}
                for d in allbkts]
        print("---")
        print("# Buckets")
        for o in bkts:
            _print_in_yaml(o)
            pass
        # List Buckets-Directories.
        alldirs = self._tables.list_buckets_directories()
        dirs = [{d["pool"]: d} for d in alldirs]
        print("---")
        print("# Buckets-Directories")
        for o in dirs:
            _print_in_yaml(o)
            pass
        pass

    def op_list_ep(self):
        """Lists endpoints of Mux and MinIO."""
        # Mux.
        muxs = self._tables.list_muxs()
        muxs = sorted(list(muxs))
        outs = [_format_mux(m, self.args.format) for m in muxs]
        print("---")
        print("# Lens3-Mux")
        for o in outs:
            _print_in_yaml(o)
            pass
        # MinIO.
        eps = self._tables.list_minio_ep()
        eps = [{ep: {"pool": pid}} for (pid, ep) in eps]
        print("---")
        print("# MinIO")
        for o in eps:
            _print_in_yaml(o)
            pass
        pass

    def op_list_ts(self):
        """Shows last access timestamps of pools."""
        stamps = self._tables.list_access_timestamps()
        stamps = [{d["pool"]:
                   {"timestamp": format_time_z(float(d["timestamp"]))}}
                  for d in stamps]
        print("# Timestamps")
        for o in stamps:
            _print_in_yaml(o)
            pass
        pass

    def op_list_minio(self, pool_id):
        """Prints a MinIO process and a Manager of a pool."""
        proc_list = self._tables.list_minio_procs(pool_id)
        proc_list = sorted(list(proc_list))
        outs = [{pool: process} for (pool, process) in proc_list]
        print("# MinIO")
        for o in outs:
            _print_in_yaml(o)
            pass
        ma = self._tables.get_minio_manager(pool_id)
        outs = [{pool_id: ma}] if ma is not None else []
        print("# Manager")
        for o in outs:
            _print_in_yaml(o)
            pass
        pass

    def op_delete_ep(self, *pool_id):
        """Deletes endpoint entires from a database.  Entries of
        MinIO-managers (ma:pool-id), MinIO-processes (mn:pool-id), and
        MinIO-eps (ep:pool-id) are deleted.
        """
        pool_list = list(pool_id)
        for pid in pool_list:
            self._tables.delete_minio_manager(pid)
            self._tables.delete_minio_proc(pid)
            self._tables.delete_minio_ep(pid)
            pass
        pass

    def op_dump_db(self, jsonfile):
        """Dumps confs, users and pools for restoring."""
        record = dump_db(self._tables)
        try:
            with open(jsonfile, 'w') as f:
                record = json.dump(record, f)
                pass
        except OSError as e:
            sys.stderr.write(f"Writing a file failed: ({jsonfile});"
                             f" {os.strerror(e.errno)}\n")
            return
        except Exception as e:
            m = rephrase_exception_message(e)
            sys.stderr.write(f"Writing a file failed: ({jsonfile});"
                             f" exception={m}\n")
            traceback.print_exc()
            return
        pass

    def op_restore_db(self, jsonfile):
        """Restores confs, users and pools from a dump.  It should be worked
        on an empty database.  It is an error if some entries are
        already occupied.  Errors are fatal, that is, Redis gets
        partially modified.
        """
        try:
            with open(jsonfile) as f:
                record = json.load(f)
                pass
        except OSError as e:
            sys.stderr.write(f"Reading a file failed: ({jsonfile});"
                             f" {os.strerror(e.errno)}\n")
            return
        except Exception as e:
            m = rephrase_exception_message(e)
            sys.stderr.write(f"Reading a file failed: ({jsonfile});"
                             f" exception={m}\n")
            traceback.print_exc()
            return
        restore_db(self._tables, record)
        pass

    def op_list_db(self):
        """Lists all database keys."""
        self._tables.print_all()
        pass

    def op_reset_db(self):
        """Clears all records in the database."""
        if not self.args.yes:
            print("Need -y (yes) for action.")
        else:
            self._tables.clear_all(everything=self.args.everything)
            pass
        pass

    # THE COMMANDS FROM HERE BELOW USE ROUTINES IN THE CONTROL.  The
    # commands above only access Redis.

    def op_access_mux(self, pool_id):
        """Accesses Mux for a pool.  It may wake up or stop MinIO."""
        api_conf = get_conf("api", None, self._redis)
        assert api_conf is not None
        traceid = self._traceid
        control = Control_Api(api_conf, self._redis)
        control.access_mux_for_pool(traceid, pool_id)
        pass

    command_list = [
        op_help,

        op_load_conf,
        op_list_conf,
        op_load_user,
        op_list_user,

        op_list_pool,
        op_list_bucket,
        op_list_minio,
        op_list_ep,
        op_list_ts,

        op_delete_pool,
        # op_delete_ep,
        op_access_mux,

        op_dump_db,
        op_restore_db,
        op_list_db,
        op_reset_db,
    ]

    def make_command_entry(self, fn, _):
        """Makes a command entry from a function by registering in the
        command_dict.  It makes a command by converting a function
        name "op_list_user" to a command "list-user" and so on.
        """
        # sig.parameters=['self', 'csvfile']
        (_, varargs) = _get_nparams_of_fn(fn)
        name = fn.__name__.removeprefix("op_").replace("_", "-")
        sig = inspect.signature(fn)
        pars = list(sig.parameters)
        self_ = pars.pop(0)
        assert self_ == "self"
        prog = [name, *pars] + (["..."] if varargs else [])
        prog = [s.replace("_", "-") for s in prog]
        usage = " ".join(prog)
        return (name, fn, usage, None)

    def make_command_dict(self):
        d = {name: (fn, args, None)
             for (name, fn, args, _)
             in (self.make_command_entry(fn, None)
                 for fn in self.command_list)}
        self._command_dict = d
        pass

    def execute_command(self):
        # fn = Command.optbl.get(self.args.command)
        ent = self._command_dict.get(self.args.command)
        # if fn is None:
        if ent is None:
            raise Exception(f"undefined command: {self.args.command}")
        (fn, _, _) = ent
        (nparams, varargs) = _get_nparams_of_fn(fn)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--conf", "-c")
    parser.add_argument("--yes", "-y", default=False,
                        action=argparse.BooleanOptionalAction)
    parser.add_argument("--everything", type=bool, default=False)
    parser.add_argument("--debug", "-d", default=False,
                        action=argparse.BooleanOptionalAction)
    parser.add_argument("--format", "-f", choices=["text", "json"])
    (args, rest) = parser.parse_known_args()

    try:
        redis = read_redis_conf(args.conf)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Getting a conf failed: exception=({m})\n")
        sys.exit(ERROR_EXIT_BADCONF)
        pass

    traceid = random_str(12)
    tracing.set(traceid)
    # openlog(api_conf["log_file"], **api_conf["log_syslog"])

    try:
        cmd = Command(traceid, redis, args, rest)
        cmd.make_command_dict()
        cmd.execute_command()
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Executing admin command failed: exception=({m})\n")
        if args.debug:
            print(traceback.format_exc())
            pass
        sys.exit(ERROR_EXIT_EXCEPTION)
        pass
    pass


if __name__ == "__main__":
    main()
