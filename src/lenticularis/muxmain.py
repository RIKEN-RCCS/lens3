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
from lenticularis.utility import uniform_distribution_jitter


def app():
    try:
        (mux_conf, configfile) = read_mux_conf()
    except Exception as e:
        sys.stderr.write(f"{e}\n")
        return None

    openlog(mux_conf["lenticularis"]["log_file"],
            **mux_conf["lenticularis"]["log_syslog"])
    logger.info("***** START MUXMAIN *****")

    tables = get_tables(mux_conf)

    node = os.environ.get(node_envname)
    if not node:
        node = platform.node()

    logger.info(f"mux is running on a host=({node})")

    controller = Controller(mux_conf, tables, configfile, node)
    multiplexer = Multiplexer(mux_conf, tables, controller, node)

    atexit.register((lambda: multiplexer.__del__()))

    timer_interval = int(mux_conf["lenticularis"]["multiplexer"]["timer_interval"])

    def interval_timer():
        while True:
            jitter = uniform_distribution_jitter()
            sleep_time = timer_interval + jitter
            multiplexer.timer_interrupt(sleep_time)
            time.sleep(sleep_time)

    threading.Thread(target=interval_timer, daemon=True).start()

    return multiplexer
