"""Tests on Lens3 Web-UI."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import time
import yaml
import contextvars
from lens3client import Client
from lens3client import tracing
from lens3client import random_str


class Api_Test():
    def __init__(self, client):
        self.client = client
        self.directory = None
        pass

    def get_user_template(self):
        self.client.get_user_template()
        pass

    def clean_pools_(self):
        pools = self.client.list_pools()
        for pooldesc in pools:
            pid = pooldesc["pool_name"]
            self.client.delete_pool(pid)
            pass
        pass

    def list_pools(self):
        pools = self.client.list_pools()
        pools = [p["pool_name"] for p in pools]
        pools = [self.client.get_pool(pid) for pid in pools]
        return pools

    # Failing to send csrf_token.

    def make_buckets_failing(self):
        bad_csrf_token = "x" + self.client.csrf_token
        data = {"CSRF-Token": bad_csrf_token}
        pass

    def make_pool(self):
        """Makes a pool with a directory of a random name."""
        if self.directory is None:
            self.directory = self.client.home + "/" + random_str(8).lower()
            pooldesc = self.client.make_pool(self.directory)
            sys.stdout.write(f"make_pool={pooldesc}\n")
            return pooldesc
        pass

    pass


def read_test_conf():
    try:
        with open("testu.yaml", "r") as f:
            conf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"cannot read {configfile} {e}")
    except Exception as e:
        raise Exception(f"cannot read {configfile} {e}")
    return conf

def run():
    conf = read_test_conf()
    tracing.set("_random_tracing_value_")
    # sys.stdout.write(f"tracing.get={tracing.get()}\n")
    client = Client(conf["uid"], conf["gid"], conf["password"], conf["home"],
                    conf["host"], proto=conf["proto"])
    test = Api_Test(client)
    test.get_user_template()
    pools = test.list_pools()
    # sys.stdout.write(f"pools={pools}\n")
    pooldesc = test.make_pool()
    pass


if __name__ == "__main__":
    run()
