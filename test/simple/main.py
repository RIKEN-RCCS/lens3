# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import datetime
from common import rconf
from common import wakeup_at
from lentclient import LentClient
from lenticularis.utility import format_time_z
from lenticularis.utility import logger, openlog
from file_manipulation import test_create_bucket
from file_manipulation import test_list_objects
from file_manipulation import test_object_xfr
from file_manipulation import test_object_xfr_spray
from file_manipulation import test_public_access
from file_manipulation import test_keytype
from file_manipulation import test_performance
import random
from s3client import S3client, Credential
import time
import urllib3
from user import cleanup_zone
from user import test_api_manipulation
from user import test_create_a_zone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--reverse_proxy_addr", default="")
    parser.add_argument("--webui_domainname", default="")
    parser.add_argument("--endpoint_url", default="")
    parser.add_argument("--credentials", default="")
    parser.add_argument("--configfile", default="test.yaml")
    parser.add_argument("--max_sleep", type=int, default="30")
    parser.add_argument("--max_nap", type=int, default="5")
    parser.add_argument("--sleep_until_next_slot", type=int, default=None)
    parser.add_argument("--interval_between_wakeups", type=int, default=None)
    parser.add_argument("--verbose", type=bool, default=False)
    args = parser.parse_args()

    conf = rconf(args.configfile)

    openlog(facility="LOCAL7", priority="DEBUG")

    #logger.debug(conf)

    if args.user == "":
        if conf["users"] == []:
            raise Exception(f"no user selected")
        u0 = conf["users"][0]
        user = u0["username"]
        password = u0["password"]
    else:
        user = args.user
        if args.password:
            password = args.password
        else:
            password = next(u["password"] for u in conf["users"] if u["username"] == user)

    if args.endpoint_url == "":
        endpoint_url = conf["endpoint_url"]
    else:
        endpoint_url = args.endpoint_url

    print(f"{format_time_z(time.time())} Start: environ: {user} {password} {endpoint_url}", flush=True)
    logger.debug(f"Start: environ: {user} {password} {endpoint_url}")

    #logger.debug(f"endpoint_url: {endpoint_url}")

    if args.reverse_proxy_addr == "":
        reverse_proxy_addr = conf["reverse_proxy_addr"]
    else:
        reverse_proxy_addr = args.reverse_proxy_addr

    if args.webui_domainname == "":
        webui_domainname = conf["webui_domainname"]
    else:
        webui_domainname = args.webui_domainname

    urllib3.disable_warnings()
    if args.credentials == "":
        cred = Credential(None, reverse_proxy_addr, webui_domainname)
    else:
        cred = Credential(args.credentials,
                          reverse_proxy_addr, webui_domainname)
    system_test = SystemTest(user, password, endpoint_url, cred,
                             reverse_proxy_addr, webui_domainname, 
                             args.max_sleep, args.max_nap)

    if args.sleep_until_next_slot:
        now = time.time()
        slot = args.sleep_until_next_slot
        current_slot = now - now % slot
        next_slot = current_slot + 2 * slot
        n = datetime.datetime.fromtimestamp(next_slot)

        if args.verbose:
            print(f"now:             {datetime.datetime.fromtimestamp(now)}")
            print(f"wakeupat:        {n}")

        def wakeup_at_datetime(n, microsecond, verbose):
            wakeup_at(n.year, n.month, n.day,
                      n.hour, n.minute, n.second, microsecond,
                      verbose=verbose)

        system_test.wakeup_at = lambda : wakeup_at_datetime(n, 0, args.verbose)

        if args.interval_between_wakeups:
            interval = int(args.interval_between_wakeups)
            m = datetime.datetime.fromtimestamp(next_slot + interval)

            system_test.second_wakeup_at = lambda : wakeup_at_datetime(
                m, 0, verbose=args.verbose)

            if args.verbose:
                print(f"second_wakeupat: {m}")

    for test in conf["tests"]:
        try:
            globals()[test](system_test)
            print(f"{format_time_z(time.time())} {test}: OK", flush=True)
            logger.debug(f"{test}: OK")
        except Exception as e:
            print(f"{format_time_z(time.time())} {test}: FAIL {e}", flush=True)
            logger.debug(f"{test}: FAIL {e}")
            logger.exception(f"{e}")
            raise
    print(f"{format_time_z(time.time())} Done", flush=True)
    logger.debug(f"Done")


class SystemTest():

    def __init__(self, user, password, endpoint_url, cred,
                 reverse_proxy_addr, webui_domainname, max_sleep, max_nap):
        self.user = user
        self.password = password
        self.endpoint_url = endpoint_url
        self.cred = cred
        self.reverse_proxy_addr = reverse_proxy_addr
        self.webui_domainname = webui_domainname
        self.max_sleep = max_sleep
        self.max_nap = max_nap
        self.u = dict()
        self.wakeup_at = None
        self.second_wakeup_at = None

    def s3_client(self, policy_name="readwrite"):
        (access_key_id, secret_access_key
         ) = self.cred.read_credentials(self.user, self.password, policy_name)
        logger.debug(f"access_key_id: {access_key_id}")
        logger.debug(f"secret_access_key: {secret_access_key}")
        return S3client(access_key_id, secret_access_key, self.endpoint_url)

    def lent_client(self):
        return LentClient(username=self.user, password=self.password,
                          reverse_proxy_addr=self.reverse_proxy_addr,
                          webui_domainname=self.webui_domainname)

    def rsleep(self, duration=None):
        random_sleep(duration if duration else self.max_sleep)

    def rnap(self, duration=None):
        random_sleep(duration if duration else self.max_nap)


def random_sleep(s):
    ss = random.randint(0, s)
    time.sleep(ss)


if __name__ == "__main__":
    main()
