# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import collections
from lenticularis.utility import sha1
from lenticularis.utility import logger


class Scheduler():
    """A part of a Controller."""

    def __init__(self, tables):
        self.tables = tables

    def schedule(self, pool_id_):
        """Chooses a least used host for running MinIO."""
        multiplexers = self.tables.list_mux_eps()

        if len(multiplexers) == 0:
            # Choose the localhost.
            return (None, None)

        servers = self.tables.list_minio_procs(None)
        minios = [procdesc["mux_host"] for (_, procdesc) in servers]
        muxs = [host for (host, port) in multiplexers]
        occupancy = collections.Counter(minios + muxs)
        occupancy = sorted(occupancy.items(), key=lambda e: e[1])
        (preferred, _) = occupancy[0]
        selected = next((host, port) for (host, port) in multiplexers if host == preferred)
        assert selected is not None
        return selected