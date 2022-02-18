# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import argparse
from lenticularis.utility import logger, openlog
import json
import os
from subprocess import Popen, PIPE
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    openlog(facility="LOCAL7", priority="DEBUG")

    arg = ["show", "zone", "--format=json"]
    admin(arg, "show-zone-json")

    arg = ["show", "zone"]
    admin(arg, "show-zone-txt")

    insert_allow_deny_rule(b"deny,*\n")

    arg = ["show", "zone", "--format=json"]
    admin(arg, "show-zone-json")

    insert_allow_deny_rule(b"allow,user1\n")

    arg = ["show", "zone", "--format=json"]
    admin(arg, "show-zone-json")

def insert_allow_deny_rule(rule):
    with tempfile.TemporaryDirectory() as tmpdirname:
        # print(f"temporary directory {tmpdirname}")
        with tempfile.NamedTemporaryFile(dir=tmpdirname) as tmpfile:
            # print(f"temporary file: {tmpfile.name}")
            tmpfile.write(rule)
            tmpfile.flush()
            csvfile = tmpfile.name
            arg = ["insert", "allow-deny-rules", csvfile]
            admin(arg, "insert-allow-deny-rule")


def admin(args, testnm):
    executable = sys.executable

    logger.debug(f"executable = {executable}")
    admin = "lenticularis.admin"
    cmd = [executable, "-m", admin]

    try:
        (status, out, err, j) = (None, None, None, None)
        with Popen(cmd + args, stdout=PIPE, stderr=PIPE, env=os.environ) as p:
            out = p.stdout.read()
            err = p.stderr.read()
            status = p.wait()
    except Exception as e:
        logger.error(f"(EE): cmd = {cmd}")
        logger.error(f"(EE): args = {args}")
        logger.error(f"(EE): status = {status}")
        logger.error(f"(EE): out = {out}")
        logger.error(f"(EE): err = {err}")
        logger.exception(e)
    logger.debug(f"(OK): {cmd} {args} {out.decode()}")
    print(f"(OK): {testnm} {status}")


def usage():
    progname = os.path.basename(sys.argv[0])
    sys.stderr.write(
        "usage:\n"
        f"     {progname} arg1 [opt1]\n"
    )
    sys.exit(126)


if __name__ == "__main__":
    main()
