# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

from lenticularis.scheduler import Scheduler
from lenticularis.utility import logger
from lenticularis.utility import make_clean_env, host_port
import os
from subprocess import Popen, PIPE
import sys


class Controller():
    """A manager of a MinIO instance."""

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
        logger.debug("@@@ +++")

        logger.debug(f"@@@ access_key_id: {access_key_id}  host: {host}")
        if host:
            # Use Direct Hostname to resolve routing
            zone_id = self.tables.zones.get_zoneID_by_directHostname(host)
        elif access_key_id:
            # Use Access Key ID to resolve routing
            zone_id = self.tables.zones.get_zoneID_by_access_key_id(access_key_id)
        else:
            zone_id = None

        logger.debug(f"@@@ zone_id: {zone_id}")
        if zone_id is None:
            if host:
                logger.debug(f"@@@ FAIL 404: unknown host: {host}")
            elif access_key_id:
                logger.debug(f"@@@ FAIL 404: unknown key: {access_key_id}")
            else:
                logger.debug("@@@ FAIL 404: No Host nor Access Key ID given")
            return (404, None)

        # schedule host
        minio_server = self.choose_minio_server(zone_id)

        logger.debug(f"@@@ minio_server = {minio_server}")

        if minio_server:  # run MinIO on another host
            logger.debug(f"@@@ start_minio on {minio_server}")
            return (minio_server, zone_id)

        # run MinIO on localhost
        logger.debug("@@@ start_minio on localhost")
        r = self.start_minio(traceid, zone_id, access_key_id)
        logger.debug(f"@@@ start_minio => {r}")

        if host:
            r = self.tables.routes.get_route_by_direct_hostname(host)
        elif access_key_id:
            r = self.tables.routes.get_route_by_access_key(access_key_id)
        else:
            raise Exception("SHOULD NOT HAPPEN: Host or access_key_id should be given here")

        logger.debug(f"@@@ r = {r}")

        if r:
            logger.debug(f"@@@ SUCCESS: Route = {r}")
            return (r, zone_id)

        # logger.debug("@@@ 404 (HARMLESS): reached end of the procedure")
        return (404, zone_id)

    def choose_minio_server(self, zone_id):
        logger.debug("@@@ +++")
        minioAddress = self.tables.processes.get_minio_address(zone_id)
        if minioAddress:
            mux_addr = minioAddress["muxAddr"]
            if mux_addr == self.mux_addr:
                return None  # localhost
            return mux_addr

        (host, port) = self.scheduler.schedule(zone_id)
        if host == self.mux_addr:
            logger.debug(f"@@@ localhost -- return None")
            return None  # localhost
        logger.debug(f"@@@ other -- return ({host}, {port})")
        return host_port(host, port)

        #scheduled_host = self.scheduler.schedule(zone_id)
        #if scheduled_host[0] == self.mux_addr:
        #    return None  # localhost
        #return host_port(scheduled_host[0], scheduled_host[1])

    def start_minio(self, traceid, zone_id, access_key_id):
        """
        Call Controller (BOTTOM)
        """
        logger.debug("@@@ +++")
        logger.debug(f"@@@ start_minio")

        cmd = [self.executable, "-m", self.manager]
        node = self.mux_addr
        args = [node, self.port_min, self.port_max, self.mux_addr,
                "--configfile", self.configfile]
        env = make_clean_env(os.environ)
        env["LENTICULARIS_ZONE_ID"] = zone_id
        if access_key_id == zone_id:
            args.append("--accessByZoneID=True")
        if traceid:
            args.append(f"--traceid={traceid}")
        logger.debug(f"@@@ cmd = {cmd}")
        logger.debug(f"@@@ args = {args}")
        try:
            with Popen(cmd + args, stdout=PIPE, env=env) as p:
                r = p.stdout.readline()
                logger.debug(f"@@@ readline: r = {r}")
                status = p.wait()
                logger.debug(f"@@@ wait: status = {status}")
        except Exception as e:
            logger.error(f"Exception: e = {e}")
            logger.exception(e)
            r = ""
        return r
