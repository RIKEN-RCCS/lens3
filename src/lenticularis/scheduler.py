# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import collections
from lenticularis.utility import sha1
from lenticularis.utility import logger


class Scheduler():
    """A part of a Controller."""

    def __init__(self, tables):
        #self.mux_conf = mux_conf
        #self.process_table = process_table
        self.tables = tables

    def schedule(self, zoneID_):
        """Chooses a least used host for running MinIO."""
        multiplexers = self.tables.process_table.get_mux_list()

        if len(multiplexers) == 0:
            ## Choose the localhost.
            return (None, None)

        servers = self.tables.process_table.get_minio_address_list(None)
        minios = [process["muxAddr"] for (zone, process) in servers]
        muxs = [host for (host, port) in multiplexers]
        occupancy = collections.Counter(minios + muxs)
        occupancy = sorted(occupancy.items(), key=lambda e: e[1])
        (preferred, _) = occupancy[0]
        selected = next((host, port) for (host, port) in multiplexers if host == preferred)
        assert selected is not None
        return selected
