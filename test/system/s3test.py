"""Tests on S3 Accesses thru Lens3."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import time
import yaml
import subprocess
import contextvars
import botocore
import boto3
import urllib.error
from lens3client import Client
from lens3client import tracing
from lens3client import random_str


class S3_Test():
    """S3 cleint wrapper."""

    def __init__(self, client):
        url = "http://fgkvm-010-128-008-026.fdcs.r-ccs.riken.jp:8009"
        self.client = client
        self.working_directory = None
        pass

    def _set_traceid(self, traceid):
        """See https://stackoverflow.com/questions/58828800."""
        if self.traceid:
            self.traceid = traceid
            return
        self.traceid = traceid
        event_system = self.s3.meta.events
        event_system.register_first("before-sign.*.*", self._add_header)
        pass

    def _add_header(self, request, **kwargs):
        request.headers.add_header("x-traceid", self.traceid)
        pass

    def make_pool_for_test(self):
        """Makes a pool with a random name directory."""
        if self.working_directory is None:
            self.working_directory = (self.client.home + "/00"
                                      + random_str(6).lower())
            pooldesc = self.client.make_pool(self.working_directory)
            # sys.stdout.write(f"make_pool_for_test={pooldesc}\n")
            return pooldesc
        pass

    def make_s3_clients(self, url):
        pooldesc = self.client.find_pool(self.working_directory)
        pool = pooldesc["pool_name"]
        # Make an access-key for each policy.
        for policy in self.client.key_policy_set:
            print(f"Making an access-key with policy={policy}")
            keydesc = self.client.make_secret(pool, policy)
            pass
        pooldesc = self.client.find_pool(self.working_directory)
        keyslist = pooldesc["access_keys"]
        session = boto3.Session(profile_name="default")
        # s3 = boto3.resource("s3")
        # Make S3 client for each access-key (for each policy).
        self.s3clients = dict()
        for k in keyslist:
            access_key = k["access_key"]
            secret_key = k["secret_key"]
            s3 = session.resource(
                service_name="s3", endpoint_url=url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key)
            policy = k["key_policy"]
            self.s3clients[policy] = s3
            pass
        assert self.s3clients.keys() == self.client.key_policy_set
        # Make a public access client (without a key).
        s3 = session.resource(
            service_name="s3", endpoint_url=url)
        self.s3clients["void"] = s3
        print(f"s3clients={self.s3clients}")
        pass

    def make_buckets(self):
        pooldesc = self.client.find_pool(self.working_directory)
        pool = pooldesc["pool_name"]
        working_buckets = set()
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
        pooldesc = self.client.find_pool(self.working_directory)
        bktslist = pooldesc["buckets"]

        self.buckets = dict()
        for b in bktslist:
            policy = b["bkt_policy"]
            self.buckets[policy] = b["name"]
            pass
        assert self.buckets.keys() == self.client.bkt_policy_set
        pass

    def store_files_in_buckets(self):
        print("Store a file in each bucket with the readwrite key.")
        data = open("gomi-file0.txt", "rb")
        s3 = self.s3clients["readwrite"]
        for (policy, bucket) in self.buckets.items():
            s3.Bucket(bucket).put_object(Key="gomi-file0.txt", Body=data)
            pass
        pass

    expectations = [
        # (bkt, key, op, expectation)
        ("none", "void", "w", False),
        ("none", "readwrite", "w", True),
        ("none", "readonly", "w", False),
        ("none", "writeonly", "w", True),
        ("none", "void", "r", False),
        ("none", "readwrite", "r", True),
        ("none", "readonly", "r", True),
        ("none", "writeonly", "r", False),

        ("upload", "void", "w", False),  #?
        ("upload", "readwrite", "w", True),
        ("upload", "readonly", "w", False), #?
        ("upload", "writeonly", "w", True),
        ("upload", "void", "r", False),
        ("upload", "readwrite", "r", True),
        ("upload", "readonly", "r", True), #?
        ("upload", "writeonly", "r", False), #?

        ("download", "void", "w", False),
        ("download", "readwrite", "w", True),
        ("download", "readonly", "w", False), #?
        ("download", "writeonly", "w", True), #?
        ("download", "void", "r", False), #?
        ("download", "readwrite", "r", True),
        ("download", "readonly", "r", True),
        ("download", "writeonly", "r", False), #?

        ("public", "void", "w", False), #?
        ("public", "readwrite", "w", True),
        ("public", "readonly", "w", False), #?
        ("public", "writeonly", "w", True),
        ("public", "void", "r", False), #?
        ("public", "readwrite", "r", True),
        ("public", "readonly", "r", True),
        ("public", "writeonly", "r", False), #?
    ]

    def match_policy_in_buckets(self):
        data0 = open("gomi-file0.txt", "rb").read()
        for (bkt, key, op, expectation) in self.expectations:
            print(f"Accessing ({op}) a {bkt}-bucket with a {key}-key.")
            s3 = self.s3clients[key]
            bucketname = self.buckets[bkt]
            bucket = s3.Bucket(bucketname)
            obj = bucket.Object("gomi-file0.txt")
            assert op in {"w", "r"}
            try:
                if op == "w":
                    obj.put(Body=data0)
                else:
                    response = obj.get()
                    data1 = response["Body"].read()
                    assert data0 == data1
            except botocore.exceptions.ClientError as e:
                #except urllib.error.HTTPError as e:
                print(f"error={e.response['Error']['Code']}")
                if key == "void":
                    assert e.response["Error"]["Code"] == "403"
                else:
                    assert e.response["Error"]["Code"] == "AccessDenied"
                    pass
                assert expectation == False
            else:
                assert expectation == True
                pass
            pass
        pass

    def upload_file(self):
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        data = open("gomi-file0.txt", "rb")
        #self.s3.Bucket("bktxxx").put_object(Key="gomi-file0.txt", Body=data)
        pass

    # return self.boto3_client.upload_fileobj(f, bucket, key)
    # return self.boto3_client.download_fileobj(bucket, key, f)


    def run(self, url):

        # Make a test file (random 64KB).

        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])

        # Make S3 clients with access-keys.

        self.make_s3_clients(url)
        self.make_buckets()
        self.store_files_in_buckets()
        self.match_policy_in_buckets()

        # Bucket opetarions (they do not work).

        r = self.s3.list_buckets()
        print(f"list_buckets={r}")
        bucket = ("lenticularis-oddity-" + random_str(6).lower())
        r = self.s3.create_bucket(Bucket=bucket)
        print(f"create_bucket={r}")
        r = self.s3.delete_bucket(Bucket=bucket)
        print(f"delete_bucket={r}")

        # List objects.

        r = self.s3.list_objects(Bucket=bucket)
        # return r["Contents"]

        # r = self.s3.upload_fileobj(f, bucket, key)
        # r = self.s3.download_fileobj(bucket, key, f)
        # r = self.s3.delete_object(Bucket=bucket, Key=key)
        pass

    pass


def read_test_conf():
    config = "testv.yaml"
    try:
        with open(config, "r") as f:
            conf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"cannot read {config} {e}")
    except Exception as e:
        raise Exception(f"cannot read {config} {e}")
    conf_keys = {"uid", "gid", "password", "home", "apiep", "s3ep", "proto"}
    assert (conf_keys.issubset(set(conf.keys())))
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
    client.get_user_template()
    test = S3_Test(client)

    print(f"Makeing a pool for testing")
    pooldesc = test.make_pool_for_test()
    print(f"A pool={pooldesc}")
    pool = pooldesc["pool_name"]
    # sys.stdout.write(f"make_pool_for_test={pooldesc}\n")

    proto=conf["proto"]
    ep = conf["s3ep"]
    url = f"{proto}://{ep}"

    try:
        test.run(url)
    finally:
        print(f"Deleting a pool={pool}")
        test.client.delete_pool(pool)
        pass
    print("Done")
    pass


if __name__ == "__main__":
    run()
