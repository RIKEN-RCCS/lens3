"""A Mux-main started as a Gunicorn service."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import atexit
import os
import platform
import threading
import sys
from lenticularis.spawner import Spawner
from lenticularis.multiplexer import Multiplexer
from lenticularis.readconf import read_mux_conf
from lenticularis.table import get_table
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import host_port
from lenticularis.utility import logger, openlog


def app():
    try:
        (mux_conf, configfile) = read_mux_conf()
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Lens3 reading a config file failed: ({m})\n")
        return None

    openlog(mux_conf["log_file"],
            **mux_conf["log_syslog"])
    logger.info("START Mux.")

    tables = get_table(mux_conf)

    mux_host = os.environ.get("LENTICULARIS_MUX_NODE")
    if not mux_host:
        mux_host = platform.node()
        pass

    gunicorn_conf = mux_conf["gunicorn"]
    mux_port = gunicorn_conf["port"]
    ep = host_port(mux_host, mux_port)
    logger.info(f"Mux is running on a host=({ep})")

    spawner = Spawner(mux_conf, tables, configfile, mux_host, mux_port)
    mux = Multiplexer(mux_conf, tables, spawner, mux_host, mux_port)

    atexit.register((lambda: mux.__del__()))
    threading.Thread(target=mux.periodic_work, daemon=True).start()

    return mux
