# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import collections
from lenticularis.utility import logger
from lenticularis.utility import sha1, get_mux_addr


class Scheduler():
    """A part of a Controller."""

    def __init__(self, tables):
        #self.mux_conf = mux_conf
        #self.process_table = process_table
        self.tables = tables

    def schedule(self, zoneID):
        logger.debug("@@@ +++")
        #logger.debug(f"@@@ zoneID = {zoneID}")

        mux_list = self.tables.processes.get_mux_list(None)
        multiplexers = [get_mux_addr(v["mux_conf"]) for (e, v) in mux_list]

        if len(multiplexers) == 0:
            logger.debug(f"@@@ return None (locahost)")
            return None  # localhost

        # assert(len(multiplexers) > 0)

        server_list = self.tables.processes.get_minio_address_list(None)
        mux_occupation_list = [process["muxAddr"] for (zone, process) in server_list]
        logger.debug(f"@@@ mux_occupation_list = {mux_occupation_list}")

        multiplexers = sorted(list(set(multiplexers)))
        logger.debug(f"@@@ multiplexers = {multiplexers}")
        mux_names = [host for (host, port) in multiplexers]
        logger.debug(f"@@@ mux_names = {mux_names}")
        mux_occupation_count_dic = collections.Counter(mux_occupation_list + mux_names)
        mux_occupation_count = [(k, v) for k, v in mux_occupation_count_dic.items()]
        logger.debug(f"@@@ mux_occupation_count = {mux_occupation_count}")
        mux_occupation_count = sorted(mux_occupation_count, key=lambda e: e[1])
        logger.debug(f"@@@ mux_occupation_count(sorted) = {mux_occupation_count}")
        (preferred, _) = mux_occupation_count[0]
        logger.debug(f"@@@ preferred = {preferred}")
        selected = next((host, port) for (host, port) in multiplexers if host == preferred)
        logger.debug(f"@@@ selected = {selected}")
        return selected
