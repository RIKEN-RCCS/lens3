"""A Mux-main started as a Gunicorn service."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import atexit
import os
import platform
import threading
import sys
from lenticularis.controller import Controller
from lenticularis.multiplexer import Multiplexer
from lenticularis.readconf import read_mux_conf, node_envname
from lenticularis.table import get_tables
from lenticularis.utility import host_port
from lenticularis.utility import logger, openlog


def app():
    try:
        (mux_conf, configfile) = read_mux_conf()
    except Exception as e:
        sys.stderr.write(f"Lens3 reading config file failed: {e}\n")
        return None

    openlog(mux_conf["log_file"],
            **mux_conf["log_syslog"])
    logger.info("START MUX.")

    tables = get_tables(mux_conf)

    mux_host = os.environ.get(node_envname)
    if not mux_host:
        mux_host = platform.node()

    gunicorn_conf = mux_conf["gunicorn"]
    mux_port = gunicorn_conf["port"]
    ep = host_port(mux_host, mux_port)
    logger.info(f"Mux is running on a host=({ep})")

    controller = Controller(mux_conf, tables, configfile, mux_host, mux_port)
    multiplexer = Multiplexer(mux_conf, tables, controller, mux_host, mux_port)

    atexit.register((lambda: multiplexer.__del__()))

    threading.Thread(target=multiplexer.periodic_work, daemon=True).start()

    return multiplexer
