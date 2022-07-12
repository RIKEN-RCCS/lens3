"""A starter of a Manager of a MinIO."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
from subprocess import Popen, DEVNULL, PIPE, TimeoutExpired
import sys
from lenticularis.utility import copy_minimal_env
from lenticularis.utility import wait_one_line_on_stdout
from lenticularis.utility import rephrase_exception_message
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
        self._extra_timeout = 15
        pass

    def start(self, traceid, pool_id, probe_key):
        """Runs a MinIO on a local host.  It returns 200 and an endpoint, or
        500 on failure.
        """
        ok = self._start_manager(traceid, pool_id)
        if not ok:
            return (500, None)
        ep = self.tables.get_minio_ep(pool_id)
        if ep is None:
            return (500, None)
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
                        (o_, e_) = p.communicate(timeout=self._extra_timeout)
                        outs += o_
                        errs += e_
                    except TimeoutExpired:
                        pass
                    p_status = p.poll()
                    pass
                if p_status is None:
                    ok = False
                    logger.warning(f"A Manager may not go background.")
                elif p_status == 0:
                    ok = True
                    logger.debug(f"A Manager started.")
                else:
                    ok = False
                    logger.warning(f"A Manager exited with status={p_status}")
                    pass
                if outs != b"" or errs != b"":
                    logger.info(f"Output from a Manager:"
                                f" stdout=({outs}), stderr=({errs})")
                    pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Starting a Manager failed: exception=({m})",
                         exc_info=True)
            if outs != b"" or errs != b"":
                logger.error(f"Output from a Manager:"
                             f" stdout=({outs}), stderr=({errs})")
                pass
            pass
        return ok

    pass
