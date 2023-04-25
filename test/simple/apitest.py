"""Simple Tests on Setting via Web-API."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import time
import yaml
import contextvars
import urllib.error
from lens3client import Client
from lens3client import tracing
from lens3client import random_str


class Api_Test():
    def __init__(self, client):
        self.client = client
        self.working_directory = None
        pass

    def clean_pools_(self):
        pools = self.client.list_pools()
        for pooldesc in pools:
            pid = pooldesc["pool_name"]
            self.client.delete_pool(pid)
            pass
        pass

    def get_user_info__(self):
        self.client.get_user_info()
        pass

    def list_pools__(self):
        pools = self.client.list_pools()
        pools = [p["pool_name"] for p in pools]
        pools = [self.client.get_pool(pid) for pid in pools]
        return pools

    def make_pool_for_test(self):
        """Makes a pool with a random name directory."""
        assert self.working_directory is None
        self.working_directory = (self.client.home + "/00"
                                  + random_str(6).lower())
        pooldesc = self.client.make_pool(self.working_directory)
        # sys.stdout.write(f"make_pool_for_test={pooldesc}\n")
        return pooldesc

    # Failing to send csrf_token.

    def make_buckets_failing(self):
        bad_csrf_token = "x" + self.client.csrf_token
        data = {"CSRF-Token": bad_csrf_token}
        pass

    def run(self):

        # List pools.

        pools = self.client.list_pools()
        pools = [p["pool_name"] for p in pools]
        print(f"pools={pools}")

        for pid in pools:
            pooldesc = self.client.get_pool(pid)
            assert pooldesc["pool_name"] == pid
            pass

        # Find a pool created for testing.

        pooldesc = self.client.find_pool(self.working_directory)
        pool = pooldesc["pool_name"]

        # Make access-keys.

        for policy in self.client.key_policy_set:
            print(f"Making an access-key with policy={policy}")
            self.client.make_secret(pool, policy)
            pass

        # Print an access-key as an aws credential entry.

        print(f"Printing an access-key for pool={pool}")
        policy = "readwrite"
        pooldesc = self.client.find_pool(self.working_directory)
        self.client.get_aws_credential(pooldesc, policy, "default")

        # Make conflicting buckets.

        working_buckets = set()
        policy = "none"
        bucket = ("lenticularis-oddity-" + random_str(6).lower())
        print(f"Makeing a bucket bucket={bucket}")
        self.client.make_bucket(pool, bucket, policy)
        working_buckets.add(bucket)
        print(f"Makeing a duplicate bucket bucket={bucket}")
        try:
            self.client.make_bucket(pool, bucket, policy)
        except urllib.error.HTTPError as e:
            assert e.code == 403
        else:
            assert False
            pass

        # Make buckets.

        for policy in self.client.bkt_policy_set:
            bucket = ("lenticularis-oddity-" + random_str(6).lower())
            while bucket in working_buckets:
                bucket = ("lenticularis-oddity-" + random_str(6).lower())
                pass
            assert bucket not in working_buckets
            print(f"Makeing a bucket bucket={bucket}")
            self.client.make_bucket(pool, bucket, policy)
            working_buckets.add(bucket)
            pass

        # Print created access-keys and buckets.

        pooldesc = self.client.find_pool(self.working_directory)
        keys = pooldesc["access_keys"]
        bkts = pooldesc["buckets"]
        # A key has {"access_key", "secret_key", "key_policy"}.
        # print(f"secrets={keys}")
        # A bucket has {"name", "bkt_policy"}.
        # print(f"buckets={bkts}")

        # Delete access-keys.

        for k in keys:
            print(f"Deleting a secret secret={k}")
            self.client.delete_secret(pool, k["access_key"])
            pass

        # Delete buckets.

        for b in bkts:
            print(f"Deleting a bucket bucket={b}")
            self.client.delete_bucket(pool, b["name"])
            pass

        pass

    pass


def read_test_conf():
    config = "testu.yaml"
    try:
        with open(config, "r") as f:
            conf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"cannot read {config} {e}")
    except Exception as e:
        raise Exception(f"cannot read {config} {e}")
    return conf

def run():
    conf = read_test_conf()
    tracing.set("_random_tracing_value_")
    # sys.stdout.write(f"tracing.get={tracing.get()}\n")
    path = conf["home"]
    uid = conf["uid"]
    home = f"{path}/{uid}"
    proto = conf["proto"]
    ep = conf["apiep"]
    url = f"{proto}://{ep}"
    client = Client(conf["uid"], conf["gid"], conf["password"], home, url)
    client.get_user_info()
    test = Api_Test(client)

    print(f"Makeing a pool for testing")
    pooldesc = test.make_pool_for_test()
    print(f"A pool={pooldesc}")
    pool = pooldesc["pool_name"]
    try:
        test.run()
    finally:
        print(f"Deleting a pool={pool}")
        test.client.delete_pool(pool)
        pass
    print("Done")
    pass


if __name__ == "__main__":
    run()
