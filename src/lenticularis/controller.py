"""A starter of a Manager of a MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
from subprocess import Popen, PIPE, DEVNULL
import sys
import select
from lenticularis.scheduler import Scheduler
from lenticularis.utility import copy_minimal_env, host_port
from lenticularis.utility import wait_one_line_on_stdout
from lenticularis.utility import logger


class Controller():
    """A starter of a Manager of a MinIO."""

    manager = "lenticularis.manager"

    def __init__(self, mux_conf, tables, configfile, host, port):
        gunicorn_conf = mux_conf["gunicorn"]
        self.tables = tables
        self.configfile = configfile
        self._mux_host = host
        self._mux_port = port
        self.executable = sys.executable
        ##self.scheduler = Scheduler(tables)
        ##lenticularis_conf = mux_conf["lenticularis"]
        ctl_param = mux_conf["minio_manager"]
        self.port_min = ctl_param["port_min"]
        self.port_max = ctl_param["port_max"]
        pass

    def start_service(self, traceid, pool_id, probe_key):
        ##if host:
        ##    pool_id = self.tables.storage_table.get_pool_id_by_direct_hostname(host)
        ##elif access_key:
        ##    pool_id = self.tables.storage_table.get_pool_by_access_key(access_key)
        ##else:
        ##    pool_id = None
        ##    pass

        ##if pool_id is None:
        ##    if host:
        ##        logger.debug(f"@@@ FAIL 404: unknown host: {host}")
        ##    elif access_key:
        ##        logger.debug(f"@@@ FAIL 404: unknown key: {access_key}")
        ##    else:
        ##        logger.debug("@@@ FAIL 404: No Host nor Access Key ID given")
        ##        pass
        ##    return (None, 404, None)

        ##minio_host = self._choose_server_host(pool_id)
        ##if minio_host:
        ##    # Run MinIO on another host.
        ##    logger.debug(f"@@@ start_minio on {minio_host}")
        ##    return (minio_host, 200)

        # Run a MinIO on the localhost.

        ok = self._start_manager(traceid, pool_id)
        if not ok:
            return (None, 503)
        ep = self.tables.routing_table.get_route(pool_id)
        if ep:
            return (ep, 200)
        else:
            return (None, 503)
        pass

    def _start_manager(self, traceid, zone_id):
        """Starts a MinIO under a manager process.  It waits for a manager to
        write a message host:port on stdout.
        """
        cmd = [self.executable, "-m", self.manager]
        args = [self._mux_host, self._mux_port, self.port_min, self.port_max,
                "--configfile", self.configfile]
        env = copy_minimal_env(os.environ)
        env["LENTICULARIS_POOL_ID"] = zone_id
        ##if access_key_id == zone_id:
        ##    args.append("--accessByZoneID=True")
        ##    pass
        if traceid is not None:
            args.append(f"--traceid={traceid}")
            pass
        ok = False
        (outs, errs) = (b"", b"")
        try:
            ## It waits for a Manager to write a line on stdout.
            logger.info(f"Starting a Manager: cmd={cmd+args}")
            with Popen(cmd + args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                       env=env) as p:
                ##(outs, errs) = p.communicate()
                (outs, errs, closed) = wait_one_line_on_stdout(p, None)
                p_status = p.wait()
                assert p_status == 0
                ok = True
                logger.debug(f"A Manager started.")
                if outs != b"" or errs != b"":
                    logger.info(f"Output from a Manager:"
                                f" stdout=({outs}), stderr=({errs})")
                    pass
        except Exception as e:
            logger.error(f"Starting a Manager failed: exception={e}")
            logger.exception(e)
            if outs != b"" or errs != b"":
                logger.error(f"Output from a Manager:"
                             f" stdout=({outs}), stderr=({errs})")
                pass
            pass
        return ok

    pass
