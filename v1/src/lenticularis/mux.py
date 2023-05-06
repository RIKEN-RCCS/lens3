"""Lens3-Mux main started as a Gunicorn service."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import atexit
import os
import platform
import threading
import sys
from lenticularis.spawner import Spawner
from lenticularis.multiplexer import Multiplexer
from lenticularis.table import get_table
from lenticularis.table import read_redis_conf
from lenticularis.table import get_conf
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import host_port
from lenticularis.utility import logger, openlog


def app():
    assert os.environ.get("LENS3_CONF") is not None
    conf_file = os.environ.get("LENS3_CONF")
    mux_name = os.environ.get("LENS3_MUX_NAME")

    try:
        redis = read_redis_conf(conf_file)
        mux_conf = get_conf("mux", mux_name, redis)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Lens3 reading a config file failed:"
                         f" exception=({m})\n")
        return None

    openlog(mux_conf["log_file"], **mux_conf["log_syslog"])
    logger.info(f"START Mux ({mux_name or ''}).")

    tables = get_table(redis)

    mux_host = mux_conf["multiplexer"]["mux_node_name"]
    if mux_host is None or len(mux_host) == 0:
        mux_host = platform.node()
        pass

    gunicorn_conf = mux_conf["gunicorn"]
    mux_port = gunicorn_conf["port"]
    ep = host_port(mux_host, mux_port)
    logger.info(f"Mux is running on a host=({ep})")

    spawner = Spawner(mux_conf, tables, conf_file, mux_host, mux_port)
    mux = Multiplexer(mux_conf, tables, spawner, mux_host, mux_port)

    atexit.register((lambda: mux.__del__()))
    threading.Thread(target=mux.periodic_work, daemon=True).start()

    return mux
