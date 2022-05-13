"""A gunicorn main started as a service."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import atexit
import os
import platform
import random
import threading
import time
import sys
from lenticularis.controller import Controller
from lenticularis.multiplexer import Multiplexer
from lenticularis.readconf import read_mux_conf, node_envname
from lenticularis.table import get_tables
from lenticularis.utility import logger, openlog


def app():
    try:
        (mux_conf, configfile) = read_mux_conf()
    except Exception as e:
        sys.stderr.write(f"Lens3 reading conf failed: {e}\n")
        return None

    openlog(mux_conf["lenticularis"]["log_file"],
            **mux_conf["lenticularis"]["log_syslog"])
    logger.info("**** START MUX ****")

    tables = get_tables(mux_conf)

    hostname = os.environ.get(node_envname)
    if not hostname:
        hostname = platform.node()

    logger.info(f"Mux is running on a host=({hostname})")

    controller = Controller(mux_conf, tables, configfile, hostname)
    multiplexer = Multiplexer(mux_conf, tables, controller, hostname)

    atexit.register((lambda: multiplexer.__del__()))

    threading.Thread(target=multiplexer.periodic_work, daemon=True).start()

    return multiplexer
