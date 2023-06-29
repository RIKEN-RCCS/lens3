"""Busy Server Test Preparation."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import re
import sys
import time
import json
import urllib.error
from lens3_client import Lens3_Client
from lens3_client import random_string


def _check_lens3_message(code, s):
    """Checks if the error reason is a known one.  It returns one of
    {"pool-taken", "bucket-taken", "server-busy", "unknown"}.  It
    checks the "reason" part in the message.  One message is:
    "Buckets-directory is already used: path=({path}), holder={uid}".
    """
    try:
        d = json.loads(s)
    except json.JSONDecodeError as ex:
        d = dict()
        pass
    reason = d.get("reason", "")
    if code == 400 and reason.startswith("Buckets-directory is already used"):
        return "pool-taken"
    elif code == 403 and reason.startswith("Bucket name taken"):
        return "bucket-taken"
    elif code == 503 and reason.startswith("Cannot start MinIO for pool"):
        return "server-busy"
    else:
        return "unknown"
    pass


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


class Busy_Test_Prepare():
    def __init__(self, client):
        self.client = client
        self.n_pools = int(client.conf["clients"])
        self.duration = (int(client.conf["minio_awake_duration"]) / 3)
        self.pools = None
        self.buckets = None
        pass

    def make_many_pools(self):
        print(f"Making many pools for test, n_pools={self.n_pools}...")
        for i in range(self.n_pools):
            self.make_pool(i)
            pass
        pools = self.client.list_pools()
        self.pools = [p for p in pools
                      if _pool_for_this_test_p(p)]
        print(f"len(pools)={len(self.pools)}, n_pools={self.n_pools}")
        print(f"pools={self.pools}")
        assert len(self.pools) == self.n_pools
        pass

    def make_pool(self, i):
        name = (self.client.home + "/00xxx" + f"{i:03d}")
        pools = self.client.list_pools()
        pool = next((p for p in pools if p["buckets_directory"] == name), None)
        got400 = 0
        if pool is None:
            while True:
                print(f"Making pool={name}...")
                try:
                    pool = self.client.make_pool(name)
                    break
                except urllib.error.HTTPError as ex:
                    print(f"Making a pool got an exception: ({ex})")
                    msg = self.client.urlopen_error_message
                    how = _check_lens3_message(ex.code, msg)
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
                    self.client.make_bucket(pid, bucket, bucket_policy)
                    break
                except urllib.error.HTTPError as ex:
                    print(f"Making a bucket got an exception: ({ex})")
                    msg = self.client.urlopen_error_message
                    how = _check_lens3_message(ex.code, msg)
                    if how == "server-busy":
                        got400 += 1
                        print(f"SERVER BUSY, SLEEP IN {self.duration} SEC...")
                        time.sleep(self.duration)
                        continue
                    raise
                pass
            pass
        if len(pool["access_keys"]) == 0:
            print(f"Making secret...")
            while True:
                try:
                    self.client.make_secret(pid, secret_policy, expiration)
                    break
                except urllib.error.HTTPError as ex:
                    print(f"Making a secret got an exception: ({ex})")
                    msg = self.client.urlopen_error_message
                    how = _check_lens3_message(ex.code, msg)
                    if how == "server-busy":
                        got400 += 1
                        print(f"SERVER BUSY, SLEEP IN {self.duration} SEC...")
                        time.sleep(self.duration)
                        continue
                    raise
                pass
            pass
        pass
    pass

    def run(self):
        self.make_many_pools()
        pass

    pass


def main():
    print(f"PREPARE FOR BUSY SERVER TEST...")
    print(f"NOTICE: THIS WILL TAKE A LONG TIME.")
    client1 = Lens3_Client("client.json")
    print(f";; Client for ep={client1.api_ep}")
    client1.get_user_info()
    prepare = Busy_Test_Prepare(client1)
    try:
        prepare.run()
    finally:
        pass
    print("Done")
    pass


# >>> exec(open("busy_server.py").read())

if __name__ == "__main__":
    main()
    pass
