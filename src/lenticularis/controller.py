"""A manager of a MinIO instance."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
from subprocess import Popen, PIPE, DEVNULL
import sys
from lenticularis.scheduler import Scheduler
from lenticularis.utility import logger
from lenticularis.utility import make_clean_env, host_port


class Controller():
    """A starter of a MinIO instance."""

    manager = "lenticularis.manager"

    def __init__(self, mux_conf, tables, configfile, node):
        self.tables = tables
        self.configfile = configfile
        self.mux_addr = node
        self.executable = sys.executable
        self.scheduler = Scheduler(tables)
        lenticularis_conf = mux_conf["lenticularis"]
        controller_param = lenticularis_conf["controller"]
        self.port_min = controller_param["port_min"]
        self.port_max = controller_param["port_max"]

    def route_request(self, traceid, host, access_key_id):
        """
        Controller (TOP)
        host is not None  => design.md:2.1
        host is None      => design.md:2.2
        """
        if host:
            zone_id = self.tables.storage_table.get_zoneID_by_directHostname(host)
        elif access_key_id:
            zone_id = self.tables.storage_table.get_pool_by_access_key(access_key_id)
        else:
            zone_id = None

        if zone_id is None:
            if host:
                logger.debug(f"@@@ FAIL 404: unknown host: {host}")
            elif access_key_id:
                logger.debug(f"@@@ FAIL 404: unknown key: {access_key_id}")
            else:
                logger.debug("@@@ FAIL 404: No Host nor Access Key ID given")
            return (404, None)

        minio_server = self._choose_minio_server(zone_id)

        if minio_server:
            ## Run MinIO on another host.
            logger.debug(f"@@@ start_minio on {minio_server}")
            return (minio_server, zone_id)

        ## Run MinIO on the localhost.

        r = self.start_minio(traceid, zone_id, access_key_id)

        ##if host:
        ##    r = self.tables.routing_table.get_route_by_direct_hostname_(host)
        ##elif access_key_id:
        ##    r = self.tables.routing_table.get_route_by_access_key_(access_key_id)
        ##else:
        ##    raise Exception("SHOULD NOT HAPPEN: Host or access_key_id should be given here")

        r = self.tables.routing_table.get_route(zone_id)

        if r:
            return (r, zone_id)
        else:
            return (404, zone_id)


    def _choose_minio_server(self, zone_id):
        """Chooses a host to run a MinIO.  It returns None to mean the
        localhost.
        """
        minioAddress = self.tables.process_table.get_minio_address(zone_id)
        if minioAddress:
            mux_addr = minioAddress["muxAddr"]
            if mux_addr == self.mux_addr:
                return None
            return mux_addr

        (host, port) = self.scheduler.schedule(zone_id)
        if host is None:
            return None
        elif host == self.mux_addr:
            return None
        else:
            return host_port(host, port)

    def start_minio(self, traceid, zone_id, access_key_id):
        """Starts a MinIO under a manager process.  It waits for a manager to
        write addr:port on stdout and to close stdout/stderr.
        """
        node = self.mux_addr
        cmd = [self.executable, "-m", self.manager]
        args = [node, self.port_min, self.port_max, self.mux_addr,
                "--configfile", self.configfile]
        env = make_clean_env(os.environ)
        env["LENTICULARIS_ZONE_ID"] = zone_id
        if access_key_id == zone_id:
            args.append("--accessByZoneID=True")
        if traceid is not None:
            args.append(f"--traceid={traceid}")

        (outs, errs) = (b"", b"")
        try:
            ## It waits for a manager to close stdout/stderr.
            logger.debug(f"Starting a Manager: cmd={cmd+args}")
            with Popen(cmd + args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
                       env=env) as p:
                (outs, errs) = p.communicate()
                status = p.wait()
                assert status == 0
        except Exception as e:
            logger.error(f"Starting a Manager failed: exception={e}")
            logger.exception(e)
        if errs != b"":
            logger.debug(f"Output on stderr from a Manager: {errs}")
        return outs
