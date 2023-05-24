"""Start routines of Gunicorn.  It starts a Gunicorn as a subprocess."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import os
from subprocess import Popen, PIPE, DEVNULL
import sys
from lenticularis.table import read_redis_conf
from lenticularis.table import get_conf
from lenticularis.utility import rephrase_exception_message
from lenticularis.utility import logger, openlog
from lenticularis.utility import copy_minimal_environ


def _run_mux():
    assert os.environ.get("LENS3_CONF") is not None
    conf_file = os.environ.get("LENS3_CONF")
    mux_name = os.environ.get("LENS3_MUX_NAME")

    try:
        redis = read_redis_conf(conf_file)
        mux_conf = get_conf("mux", mux_name, redis)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Lens3 getting a conf failed:"
                         f" exception=({m})\n")
        return

    openlog(mux_conf["log_file"], **mux_conf["log_syslog"])
    servicename = "lenticularis-mux"
    logger.info("Start {servicename} service.")

    gunicorn_conf = mux_conf["gunicorn"]
    _port = gunicorn_conf["port"]
    bind = f"[::]:{_port}"
    env = copy_minimal_environ(os.environ)
    assert "LENS3_CONF" in env
    cmd = [sys.executable, "-m", "gunicorn"]
    args = ["--bind", bind]
    options = _list_gunicorn_command_options(gunicorn_conf)
    args += options
    args += ["lenticularis.mux:app()"]
    _run(servicename, env, cmd, args)
    pass


def _run_api():
    assert os.environ.get("LENS3_CONF") is not None
    conf_file = os.environ.get("LENS3_CONF")

    try:
        redis = read_redis_conf(conf_file)
        api_conf = get_conf("api", None, redis)
    except Exception as e:
        m = rephrase_exception_message(e)
        sys.stderr.write(f"Lens3 getting a conf failed:"
                         f" exception=({m})\n")
        return

    openlog(api_conf["log_file"], **api_conf["log_syslog"])
    servicename = "lenticularis-api"
    logger.info(f"Start {servicename} service.")

    gunicorn_conf = api_conf["gunicorn"]
    _port = gunicorn_conf["port"]
    bind = f"[::]:{_port}"
    env = copy_minimal_environ(os.environ)
    assert "LENS3_CONF" in env
    cmd = [sys.executable, "-m", "gunicorn"]
    args = ["--worker-class", "uvicorn.workers.UvicornWorker", "--bind", bind]
    options = _list_gunicorn_command_options(gunicorn_conf)
    args += options
    args += ["lenticularis.api:app()"]
    _run(servicename, env, cmd, args)
    pass


def _list_gunicorn_command_options(gunicorn_conf):
    workers = gunicorn_conf.get("workers")
    threads = gunicorn_conf.get("threads")
    timeout = gunicorn_conf.get("timeout")
    access_logfile = gunicorn_conf.get("access_logfile")
    log_file = gunicorn_conf.get("log_file")
    log_level = gunicorn_conf.get("log_level")
    log_syslog_facility = gunicorn_conf.get("log_syslog_facility")
    reload = gunicorn_conf.get("reload")
    args = []
    if workers:
        args += ["--workers", str(workers)]
        pass
    if threads:
        args += ["--threads", str(threads)]
        pass
    if timeout:
        args += ["--timeout", str(timeout)]
        pass
    if access_logfile:
        args += ["--access-logfile", access_logfile]
        pass
    if log_file:
        args += ["--log-file", log_file]
        if log_level:
            args += ["--log-level", log_level]
            pass
        pass
    else:
        args += ["--log-syslog"]
        if log_syslog_facility:
            args += ["--log-syslog-facility", log_syslog_facility]
            pass
        pass
    if reload == "yes":
        args += ["--reload"]
        pass
    assert all(isinstance(i, str) for i in args)
    return args


def _run(servicename, env, cmd, args):
    """Starts Gunicorn as a systemd service.  It will not return unless it
    a subprocess exits.  Note the stdout/stderr messages from Gunicorn
    is usually not helpful.  Examine the log file.
    """

    logger.debug(f"{servicename}: Starting Gunicorn ..."
                 f" cmd=({cmd}),"
                 f" args=({args}),"
                 f" env=({env})")

    assert all(isinstance(i, str) for i in (cmd + args))
    (outs, errs) = (b"", b"")
    try:
        with Popen(cmd + args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, env=env) as p:
            (outs, errs) = p.communicate()
            p_status = p.wait()
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.error(f"{servicename} failed to start: exception=({m})",
                     exc_info=True)
        sys.exit(1)
        pass

    if p_status == 0:
        logger.debug(f"{servicename} exited: status={p_status}")
        sys.exit(p_status)
    else:
        logger.error(f"{servicename} exited: status={p_status};"
                     f" EXAMINE THE GUNICORN LOG;"
                     f" stdout=({outs}), stderr=({errs})")
        if p_status is not None and p_status > 0:
            sys.exit(p_status)
        else:
            sys.exit(1)
            pass
        pass
    pass


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("target")
        args = parser.parse_args()
        if args.target == "mux":
            _run_mux()
            assert False
            pass
        elif args.target == "api":
            _run_api()
            assert False
            pass
        else:
            assert False
            pass
    except Exception as e:
        m = rephrase_exception_message(e)
        logger.error(f"Starting a lenticularis service failed:"
                     f" exception=({m})")
        sys.exit(1)
        pass
    pass


if __name__ == "__main__":
    main()
