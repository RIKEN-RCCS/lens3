"""Start routines of gunicorn.  It starts a Gunicorn as a process."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import os
from subprocess import Popen, PIPE
import sys
from lenticularis.readconf import read_mux_conf
from lenticularis.readconf import read_adm_conf
from lenticularis.utility import logger, openlog
from lenticularis.utility import make_clean_env


def start_mux():
    try:
        (mux_conf, configfile) = read_mux_conf()
    except Exception as e:
        sys.stderr.write(f"Lens3 reading conf failed: {e}\n")
        return None

    openlog(mux_conf["log_file"],
            **mux_conf["log_syslog"])
    logger.info("Start Lenticularis-S3 MUX service")

    gunicorn_conf = mux_conf["gunicorn"]
    #bind = gunicorn_conf["bind"]
    _port = gunicorn_conf["port"]
    bind = f"[::]:{_port}"
    workers = gunicorn_conf.get("workers")
    threads = gunicorn_conf.get("threads")
    timeout = gunicorn_conf.get("timeout")
    log_file = gunicorn_conf.get("log_file")
    log_level = gunicorn_conf.get("log_level")
    log_syslog_facility = gunicorn_conf.get("log_syslog_facility")
    reload = gunicorn_conf.get("reload")

    env = make_clean_env(os.environ)
    env["LENTICULARIS_MUX_CONFIG"] = configfile
    cmd = [sys.executable, "-m", "gunicorn"]
    args = ["--bind", bind]
    if workers:
        args += ["--workers", workers]
    if threads:
        args += ["--threads", threads]
    if timeout:
        args += ["--timeout", timeout]
    if log_file:
        args += ["--log-file", log_file]
        if log_level:
            args += ["--log-level", log_level]
    else:
        args.append(f"--log-syslog")
        if log_syslog_facility:
            args += ["--log-syslog-facility", log_syslog_facility]
    if reload == "yes":
        args.append("--reload")
    args.append("lenticularis.mux:app()")

    run("lenticularis-mux", env, cmd, args)


def start_adm():
    try:
        (adm_conf, configfile) = read_adm_conf()
    except Exception as e:
        sys.stderr.write(f"Lens3 reading conf failed: {e}\n")
        return None

    openlog(adm_conf["log_file"],
            **adm_conf["log_syslog"])
    logger.info("Start Lenticularis-S3 Adm service")

    gunicorn_conf = adm_conf["gunicorn"]
    #bind = gunicorn_conf["bind"]
    _port = gunicorn_conf["port"]
    bind = f"[::]:{_port}"
    workers = gunicorn_conf.get("workers")
    #threads = gunicorn_conf.get("threads")
    timeout = gunicorn_conf.get("timeout")
    log_file = gunicorn_conf.get("log_file")
    log_level = gunicorn_conf.get("log_level")
    log_syslog_facility = gunicorn_conf.get("log_syslog_facility")
    reload = gunicorn_conf.get("reload")

    env = make_clean_env(os.environ)
    env["LENTICULARIS_ADM_CONFIG"] = configfile
    cmd = [sys.executable, "-m", "gunicorn"]
    args = ["--worker-class", "uvicorn.workers.UvicornWorker", "--bind", bind]
    if workers:
        args += ["--workers", workers]

    if timeout:
        args += ["--timeout", timeout]
    if log_file:
        args += ["--log-file", log_file]
        if log_level:
            args += ["--log-level", log_level]
    else:
        args.append(f"--log-syslog")
        if log_syslog_facility:
            args += ["--log-syslog-facility", log_syslog_facility]
    if reload == "yes":
        args.append("--reload")
    args.append("lenticularis.adm:app")

    run("lenticularis-api", env, cmd, args)


def run(servicename, env, cmd, args):
    """Starts Gunicorn as a systemd service.  It will not return unless it
    errs or finishes.  Note the messages from a Gunicorn process will
    go to stdout/stderr (until a logger is set).
    """

    logger.debug(f"{servicename}: starting gunicorn ..."
                 f" cmd=({cmd})"
                 f" args=({args})"
                 f" env=({env})")

    try:
        with Popen(cmd + args, stdout=None, stderr=None, env=env) as p:
            #(out, err) = p.communicate()
            status = p.wait()
    except Exception as e:
        logger.exception(f"{servicename} failed to start")
        sys.exit(1)
    logger.debug(f"{servicename} exited: status={status}")
    if status is None or status < 0:
        sys.exit(1)
    else:
        sys.exit(status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    args = parser.parse_args()

    if args.target == "mux":
        start_mux()
    elif args.target == "adm":
        start_adm()
    else:
        assert False
    sys.exit(1)


if __name__ == "__main__":
    main()
