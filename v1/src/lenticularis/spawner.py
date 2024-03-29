"""A starter of a Manager of MinIO."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
from subprocess import Popen, DEVNULL, PIPE, TimeoutExpired
import sys
from lenticularis.utility import copy_minimal_environ
from lenticularis.utility import wait_line_on_stdout
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger
from lenticularis.utility import tracing


class Spawner():
    """A starter of a Manager of MinIO."""

    _manager_command = "lenticularis.manager"

    def __init__(self, mux_conf, tables, conf, host, port):
        self.tables = tables
        self.conf = conf
        self._mux_host = host
        self._mux_port = port
        self.executable = sys.executable
        ctl_param = mux_conf["minio_manager"]
        self.port_min = ctl_param["port_min"]
        self.port_max = ctl_param["port_max"]
        self._extra_timeout = 15
        pass

    def start_spawner(self, pool_id):
        """Runs MinIO on a local host.  It returns an endpoint or None on
        failure.
        """
        ok = self._start_manager(pool_id)
        if not ok:
            return None
        ep = self.tables.get_minio_ep(pool_id)
        if ep is None:
            return None
        return ep

    def _start_manager(self, pool_id):
        """Starts MinIO under a manager process.  It waits for a manager to
        write a message host:port on stdout.
        """
        cmd = [self.executable, "-m", self._manager_command]
        args = [self._mux_host, str(self._mux_port),
                str(self.port_min), str(self.port_max),
                pool_id, "--conf", self.conf]
        env = copy_minimal_environ(os.environ)
        traceid = tracing.get()
        if traceid is not None:
            args.append(f"--traceid={traceid}")
            pass
        assert all(isinstance(i, str) for i in (cmd + args))
        ok = False
        (outs, errs) = ("", "")
        try:
            logger.info(f"Starting a Manager: cmd={cmd+args}")
            with Popen(cmd + args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                       env=env) as p:
                (o1, e1, closed, _) = wait_line_on_stdout(p, b"", b"", None)
                p_status = p.poll()
                if p_status is None:
                    try:
                        (o2, e2) = p.communicate(timeout=self._extra_timeout)
                        o1 += o2
                        e1 += e2
                    except TimeoutExpired:
                        pass
                    p_status = p.poll()
                    pass
                outs = str(o1, "latin-1").strip()
                errs = str(e1, "latin-1").strip()
                if p_status is None:
                    ok = False
                    logger.warning(f"A Manager may not go background.")
                elif p_status == 0:
                    ok = True
                    logger.debug(f"A Manager started.")
                else:
                    ok = False
                    logger.warning(f"A Manager exited: status={p_status}")
                    pass
                if outs != "" or errs != "":
                    logger.info(f"A Manager outputs:"
                                f" stdout=({outs}), stderr=({errs})")
                    pass
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Starting a Manager failed: exception=({m})",
                         exc_info=True)
            if outs != "" or errs != "":
                logger.error(f"A Manager outputs:"
                             f" stdout=({outs}), stderr=({errs})")
                pass
            pass
        return ok

    pass
