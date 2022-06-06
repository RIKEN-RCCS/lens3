"""Start routines of Gunicorn.  It starts a Gunicorn as a subprocess."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import os
from subprocess import Popen, PIPE, DEVNULL
import sys
from lenticularis.readconf import read_mux_conf
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import logger, openlog
from lenticularis.utility import copy_minimal_env


def start_mux():
    try:
        (mux_conf, configfile) = read_mux_conf()
    except Exception as e:
        sys.stderr.write(f"Lens3 reading config file failed: {e}\n")
        return

    openlog(mux_conf["log_file"],
            **mux_conf["log_syslog"])
    logger.info("Start Lenticularis-S3 MUX service")

    gunicorn_conf = mux_conf["gunicorn"]
    _port = gunicorn_conf["port"]
    bind = f"[::]:{_port}"
    env = copy_minimal_env(os.environ)
    env["LENTICULARIS_MUX_CONFIG"] = configfile
    cmd = [sys.executable, "-m", "gunicorn"]
    args = ["--bind", bind]
    options = list_gunicorn_command_options(gunicorn_conf)
    args += options
    args += ["lenticularis.mux:app()"]
    run("lenticularis-mux", env, cmd, args)
    return


def start_adm():
    try:
        (adm_conf, configfile) = read_adm_conf()
    except Exception as e:
        sys.stderr.write(f"Lens3 reading config file failed: {e}\n")
        return

    openlog(adm_conf["log_file"],
            **adm_conf["log_syslog"])
    logger.info("Start Lenticularis-S3 Adm service")

    gunicorn_conf = adm_conf["gunicorn"]
    _port = gunicorn_conf["port"]
    bind = f"[::]:{_port}"
    env = copy_minimal_env(os.environ)
    env["LENTICULARIS_ADM_CONFIG"] = configfile
    cmd = [sys.executable, "-m", "gunicorn"]
    args = ["--worker-class", "uvicorn.workers.UvicornWorker", "--bind", bind]
    options = list_gunicorn_command_options(gunicorn_conf)
    args += options
    args += ["lenticularis.adm:app"]
    run("lenticularis-adm", env, cmd, args)
    return

def list_gunicorn_command_options(gunicorn_conf):
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
        args += ["--workers", workers]
        pass
    if threads:
        args += ["--threads", threads]
        pass
    if timeout:
        args += ["--timeout", timeout]
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
    return args

def run(servicename, env, cmd, args):
    """Starts Gunicorn as a systemd service.  It will not return unless it
    a subprocess exits.  Note the stdout/stderr messages from Gunicorn
    is usually not helpful.  Examine the log file.
    """

    logger.debug(f"{servicename}: Starting Gunicorn ..."
                 f" cmd=({cmd}),"
                 f" args=({args}),"
                 f" env=({env})")

    (outs, errs) = (b"", b"")
    try:
        with Popen(cmd + args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, env=env) as p:
            (outs, errs) = p.communicate()
            p_status = p.wait()
    except:
        logger.error(f"{servicename} failed to start.",
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
        if p_status is None or p_status < 0:
            sys.exit(1)
        else:
            sys.exit(p_status)
            pass
        pass
    return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    args = parser.parse_args()

    if args.target == "mux":
        start_mux()
        pass
    elif args.target == "adm":
        start_adm()
        pass
    else:
        assert False
        pass
    sys.exit(1)
    return


if __name__ == "__main__":
    main()
