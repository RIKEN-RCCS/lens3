# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import argparse
from api_manipulation import accesskey_of_a_zone
from lenticularis.utility import openlog
from lentclient import LentClient
from user import zone_list
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="u0000")
    parser.add_argument("--password", default="p0000")
    parser.add_argument("--reverse_proxy_addr", default="lent8.example.com")
    parser.add_argument("--webui_domainname", default="webui.lent8.example.com")
    args = parser.parse_args()

    openlog(facility="LOCAL7", priority="DEBUG")

    lc = LentClient(username=args.user, password=args.password,
                    reverse_proxy_addr=args.reverse_proxy_addr,
                    webui_domainname=args.webui_domainname)

    (user, accessKeyID, secretAccessKey) = accesskey_of_a_zone(lc)

    write_credentials(user, accessKeyID, secretAccessKey)


def write_credentials(profile, accessKeyID, secretAccessKey):
    print(""
          f"[{profile}]\n"
          f"aws_access_key_id = {accessKeyID}\n"
          f"aws_secret_access_key = {secretAccessKey}\n", end="")


def usage():
    progname = os.path.basename(sys.argv[0])
    sys.stderr.write(
        "usage:\n"
        f"     {progname} arg1 [opt1]\n"
    )
    sys.exit(126)


if __name__ == "__main__":
    main()
