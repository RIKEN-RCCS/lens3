"""A starter of a Manager of a MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
from subprocess import Popen, DEVNULL, PIPE, TimeoutExpired
import sys
from lenticularis.utility import copy_minimal_env
from lenticularis.utility import wait_one_line_on_stdout
from lenticularis.utility import logger


class Spawner():
    """A starter of a Manager of a MinIO."""

    _manager_command = "lenticularis.manager"

    def __init__(self, mux_conf, tables, configfile, host, port):
        self.tables = tables
        self.configfile = configfile
        self._mux_host = host
        self._mux_port = port
        self.executable = sys.executable
        ctl_param = mux_conf["minio_manager"]
        self.port_min = ctl_param["port_min"]
        self.port_max = ctl_param["port_max"]
        pass

    def start(self, traceid, pool_id, probe_key):
        # Runs a MinIO on the localhost.
        ok = self._start_manager(traceid, pool_id)
        if not ok:
            return (503, None)
        ep = self.tables.get_minio_ep(pool_id)
        if ep is None:
            return (503, None)
        return (200, ep)

    def _start_manager(self, traceid, pool_id):
        """Starts a MinIO under a manager process.  It waits for a manager to
        write a message host:port on stdout.
        """
        cmd = [self.executable, "-m", self._manager_command]
        args = [self._mux_host, str(self._mux_port),
                str(self.port_min), str(self.port_max),
                pool_id, "--configfile", self.configfile]
        env = copy_minimal_env(os.environ)
        if traceid is not None:
            args.append(f"--traceid={traceid}")
            pass
        assert all(isinstance(i, str) for i in (cmd + args))
        ok = False
        (outs, errs) = (b"", b"")
        try:
            # It waits for a Manager to write a line on stdout.
            logger.info(f"Starting a Manager: cmd={cmd+args}")
            with Popen(cmd + args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                       env=env) as p:
                (outs, errs, closed) = wait_one_line_on_stdout(p, None)
                p_status = p.poll()
                if p_status is None:
                    try:
                        (o_, e_) = p.communicate(timeout=15)
                        outs += o_
                        errs += e_
                    except TimeoutExpired:
                        pass
                    p_status = p.poll()
                    pass
                if p_status is None or p_status != 0:
                    logger.warning(f"Starting a Manager exited with"
                                   f" a bad status: {p_status}")
                    pass
                ok = True
                logger.debug(f"A Manager started.")
                if outs != b"" or errs != b"":
                    logger.info(f"Output from a Manager:"
                                f" stdout=({outs}), stderr=({errs})")
                    pass
        except Exception as e:
            logger.error(f"Starting a Manager failed: exception={e}",
                         exc_info=True)
            if outs != b"" or errs != b"":
                logger.error(f"Output from a Manager:"
                             f" stdout=({outs}), stderr=({errs})")
                pass
            pass
        return ok

    pass
