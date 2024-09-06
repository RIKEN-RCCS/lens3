"""Busy Server Test."""

# Copyright 2022-2024 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
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


def _pool_for_this_test_p(pool):
    path = pool["buckets_directory"]
    last = path.rsplit("/", 1)[-1]
    m = re.match(r"^00xxx[0-9][0-9][0-9]$", last)
    return m is not None


def _index_of_test_pool(pool):
    path = pool["buckets_directory"]
    last = path.rsplit("/", 1)[-1]
    m = re.match(r"^00xxx([0-9][0-9][0-9])$", last)
    assert m is not None
    return int(m.group(1))


class Busy_Test():
    def __init__(self, registrar):
        self.registrar = registrar
        self.n_pools = int(registrar.conf["pools_count"])
        duration = registrar.conf["backend_awake_duration"]
        self.duration = int(max(duration / 3, 60))
        self.pools = None
        self.buckets = None
        self.clients = None
        pass

    #
    # Test Preparation.
    #

    def make_many_pools(self):
        print(f"Making many pools for test, n_pools={self.n_pools}...")
        for i in range(self.n_pools):
            self.make_pool(i)
            pass
        pools = self.registrar.list_pools()
        self.pools = [p for p in pools
                      if _pool_for_this_test_p(p)]
        print(f"len(pools)={len(self.pools)}, n_pools={self.n_pools}")
        print(f"pools={self.pools}")
        assert len(self.pools) == self.n_pools
        pass

    def make_pool(self, i):
        name = (self.registrar.home + "/00xxx" + f"{i:03d}")
        pools = self.registrar.list_pools()
        pool = next((p for p in pools if p["buckets_directory"] == name), None)
        got400 = 0
        if pool is None:
            while True:
                print(f"Making pool={name}...")
                try:
                    pool = self.registrar.make_pool(name)
                    break
                except urllib.error.HTTPError as x:
                    print(f"Making a pool got an exception: ({x})")

                    # Making a pool never fails, even when the server
                    # is busy.  So, the following code will never be
                    # executed.

                    msg = self.registrar.urlopen_error_message
                    how = check_lens3_message(x.code, msg)
                    if how == "server-busy":
                        got400 += 1
                        print(f"SERVER BUSY, SLEEP IN {self.duration} SEC...")
                        time.sleep(self.duration)
                        continue
                    raise
                pass
            pass
        assert pool is not None
        self.make_bucket_and_secret(pool)
        pass

    def make_bucket_and_secret(self, pool):
        i = _index_of_test_pool(pool)
        assert 0 <= i and i < self.n_pools
        pid = pool["pool_name"]
        bucket = ("lenticularis-oddity-" + "00xxx" + f"{i:03d}")
        bucket_policy = "none"
        secret_policy = "readwrite"
        now = int(time.time())
        expiration = now + (24 * 3600)
        got400 = 0
        if len(pool["buckets"]) == 0:
            print(f"Making bucket={bucket}...")
            while True:
                try:
                    self.registrar.make_bucket(pid, bucket, bucket_policy)
                    break
                except urllib.error.HTTPError as x:
                    print(f"Making a bucket got an exception: ({x})")
                    msg = self.registrar.urlopen_error_message
                    how = check_lens3_message(x.code, msg)
                    if how == "server-busy":
                        got400 += 1
                        print(f"SERVER BUSY, SLEEP IN {self.duration} SEC...")
                        time.sleep(self.duration)
                        continue
                    raise
                pass
            pass
        if len(pool["secrets"]) == 0:
            print(f"Making secret...")
            while True:
                try:
                    self.registrar.make_secret(pid, secret_policy, expiration)
                    break
                except urllib.error.HTTPError as x:
                    print(f"Making a secret got an exception: ({x})")
                    msg = self.registrar.urlopen_error_message
                    how = check_lens3_message(ex.code, msg)
                    if how == "server-busy":
                        got400 += 1
                        print(f"SERVER BUSY, SLEEP IN {self.duration} SEC...")
                        time.sleep(self.duration)
                        continue
                    raise
                pass
            pass
        pass

    def remove_test_pools(self):
        pools = self.registrar.list_pools()
        for p in pools:
            if _pool_for_this_test_p(p):
                self.registrar.delete_pool(p["pool_name"])
                pass
            pass
        pass

    #
    # Test Body.
    #

    def checkout_many_pools(self):
        print(f"List many pools for test...")
        pools = self.registrar.list_pools()
        self.pools = [None] * self.n_pools
        for i in range(self.n_pools):
            name = (self.registrar.home + "/00xxx" + f"{i:03d}")
            pool = next((p for p in pools if p["buckets_directory"] == name),
                        None)
            if pool == None:
                print(f"Pool not found, do prepare first: {name}")
                return
            self.pools[i] = pool
            pass
        print(f"pools={self.pools}")
        pass

    def make_clients(self):
        self.buckets = [None] * self.n_pools
        self.clients = [None] * self.n_pools
        region = "us-east-1"
        for i in range(self.n_pools):
            pool = self.pools[i]
            bucket = pool["buckets"][0]["name"]
            secret = pool["secrets"][0]
            c = boto3.client(
                service_name="s3",
                region_name=region,
                endpoint_url=self.registrar.s3_ep,
                aws_access_key_id=secret["access_key"],
                aws_secret_access_key=secret["secret_key"],
                config=botocore.config.Config(signature_version="s3v4"))
            self.buckets[i] = bucket
            self.clients[i] = c
            pass
        print(f"clients={self.clients}")
        pass

    def access_pools(self, loops):
        subprocess.run(["rm", "-f", "gomi-file0.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        with open("gomi-file0.txt", "rb") as f:
            data = f.read()
            pass
        for j in range(loops):
            print(f"*** Test {j}/{loops}-th repeat.")
            for i in range(self.n_pools):
                s3 = self.clients[i]
                bucket = self.buckets[i]
                # Loop for taking exceptions.
                while True:
                    try:
                        response = s3.put_object(
                            Body=data,
                            Bucket=bucket,
                            Key="gomi-file0.txt")
                        break
                    except botocore.exceptions.ClientError as x:
                        pool = self.pools[i]["pool_name"]
                        print(f"ClientError pool={pool} exception: {x}")
                        code = x.response["ResponseMetadata"]["HTTPStatusCode"]
                        if code != 503:
                            print(f"Unexpected error code {code}")
                            raise
                        print(f"SERVER BUSY, SLEEP IN {self.duration} SEC...")
                        time.sleep(self.duration)
                        continue
                    except Exception as x:
                        print("Unknown exception", x)
                        raise
                    pass
                pass
            pass
        pass

    def run(self):
        self.checkout_many_pools()
        self.make_clients()
        self.access_pools(40)
        pass

    def prepare(self):
        print(f"NOTICE: THIS WILL TAKE A LONG TIME.")
        self.make_many_pools()
        pass

    def destroy(self):
        self.remove_test_pools()
        pass

    pass


def _usage():
    print(f"USAGE {sys.argv[0]} prepare/destroy/run")
    print(f"\tprepare creates a number of pools")
    print(f"\tdestroy wipes out pools for test")
    print(f"\trun test")
    pass

def main():
    print(f"BUSY SERVER TEST.")
    registrar = Lens3_Registrar("client.json")
    print(f";; Client for ep={registrar.reg_ep}")
    registrar.get_user_info()

    testcase = Busy_Test(registrar)
    if len(sys.argv) != 2:
        _usage()
    elif sys.argv[1] == "prepare":
        testcase.prepare()
        print("Done")
    elif sys.argv[1] == "destroy":
        testcase.destroy()
        print("Done")
    elif sys.argv[1] == "run":
        testcase.run()
        print("Done")
    else:
        _usage()
        pass
    pass

# >>> exec(open("test_busy_server.py").read())

if __name__ == "__main__":
    main()
    pass
