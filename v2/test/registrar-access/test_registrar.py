"""Test Lens3 Registrar."""

# Copyright 2022-2024 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import time
import json
import urllib.error
import subprocess
import botocore
import boto3

sys.path.append("../lib/")

from lens3_client import Lens3_Registrar
from lens3_client import check_lens3_message
from lens3_client import random_string


class Test_Base():
    def __init__(self, client):
        self.client = client
        self.working_directory = ""
        self.working_pool = ""
        pass

    def make_working_pool(self):
        """Makes a pool in a directory with a random name."""
        assert self.working_directory == ""
        self.working_directory = (self.client.home + "/00"
                                  + random_string(6))
        desc = self.client.make_pool(self.working_directory)
        self.working_pool = desc["pool_name"]
        return desc

    pass


class Registrar_Test(Test_Base):
    """Registrar Test.  It makes a pool, then makes buckets and
    access keys.  It tries to make a conflicting bucket and fails.
    Finally, it cleans up, but it leaves a directory with a random
    name in the filesystem.
    """

    def __init__(self, client):
        super().__init__(client)
        pass

    # Failing to send csrf_token.

    def make_buckets_failing(self):
        bad_csrf_token = "x" + self.client.csrf_token
        data = {"CSRF-Token": bad_csrf_token}
        pass

    def run(self):

        #
        # (1) List pools.
        #

        pools1 = self.client.list_pools()
        pids1 = [p["pool_name"] for p in pools1]
        print(f"pools={pids1}")

        for pid in pids1:
            desc1 = self.client.get_pool(pid)
            assert desc1["pool_name"] == pid
            pass

        #
        # (2) Find a pool created for this test.
        #

        desc2 = self.client.find_pool(self.working_directory)
        assert self.working_pool == desc2["pool_name"]

        #
        # (3) Make access keys -- one for each policy.
        #

        now = int(time.time())
        expiration = now + (24 * 3600)
        for policy in self.client.key_policy_set:
            print(f"Making an access-key with policy={policy}")
            self.client.make_secret(self.working_pool, policy, expiration)
            pass

        #
        # (4) Print an access-key as an aws credential entry.
        #

        print(f"Printing an AWS credential:")
        desc4 = self.client.find_pool(self.working_directory)
        self.client.get_aws_credential(desc4, "readwrite", "default")

        #
        # (5) Make conflicting buckets.
        #

        working_buckets5 = set()
        bucket5 = ("lenticularis-oddity-" + random_string(6))
        policy5 = "none"
        print(f"Making a bucket bucket={bucket5}")
        self.client.make_bucket(self.working_pool, bucket5, policy5)
        working_buckets5.add(bucket5)

        print(f"Making a duplicate bucket bucket={bucket5}")
        try:
            self.client.make_bucket(self.working_pool, bucket5, policy5)
        except urllib.error.HTTPError as e:
            assert e.code == 409
        else:
            assert False
            pass

        #
        # (6) Make buckets.
        #

        for policy in self.client.bkt_policy_set:
            while True:
                bucket = ("lenticularis-oddity-" + random_string(6))
                if bucket not in working_buckets5:
                    break
                pass
            assert bucket not in working_buckets5
            print(f"Making a bucket bucket={bucket}")
            self.client.make_bucket(self.working_pool, bucket, policy)
            working_buckets5.add(bucket)
            pass

        #
        # (7) Delete access keys.  Delete buckets.
        #

        desc7 = self.client.find_pool(self.working_directory)
        keys7 = desc7["secrets"]
        bkts7 = desc7["buckets"]
        # A key has {"access_key", "secret_key", "key_policy"}.
        # print(f"secrets={keys}")
        # A bucket has {"name", "bkt_policy"}.
        # print(f"buckets={bkts}")

        for k in keys7:
            print(f"Deleting a secret secret={k}")
            self.client.delete_secret(self.working_pool, k["access_key"])
            pass

        for b in bkts7:
            print(f"Deleting a bucket bucket={b}")
            self.client.delete_bucket(self.working_pool, b["name"])
            pass
        pass

    pass


def main1():
    print(f"REGISTRAR TEST...")
    global registrar, test1
    registrar = Lens3_Registrar("client.json")
    print(f";; client: ep={registrar.reg_ep}, auth={registrar.headers}")
    registrar.get_user_info()

    test1 = Registrar_Test(registrar)
    print(f"Making a working pool for test...")
    test1.make_working_pool()
    try:
        test1.run()
    finally:
        print(f";; Deleting a working pool={test1.working_pool}")
        test1.client.delete_pool(test1.working_pool)
        pass
    print("Done")
    pass


# >>> exec(open("test_registrar.py").read())

if __name__ == "__main__":
    main1()
    pass
