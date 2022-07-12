"""Tests on S3 Accesses thru Lens3."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import enum
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


class Expectation(enum.Enum):
    OK = "OK"
    E401 = "401"
    EACCESSDENIED = "AccessDenied"

    def __str__(self):
        return self.value

    pass


class S3_Test():
    """S3 cleint wrapper."""

    def __init__(self, client):
        self.client = client
        self.working_directory = None
        self.working_buckets = set()
        pass

    def _set_traceid(self, traceid):
        """See https://stackoverflow.com/questions/58828800."""
        if self.traceid:
            self.traceid = traceid
            return
        self.traceid = traceid
        # event_system = self.s3.meta.events
        # event_system.register_first("before-sign.*.*", self._add_header)
        pass

    def _add_header(self, request, **kwargs):
        request.headers.add_header("x-traceid", self.traceid)
        pass

    def make_pool_for_test(self):
        """Makes a pool with a random name directory."""
        assert self.working_directory is None
        self.working_directory = (self.client.home + "/00"
                                  + random_str(6).lower())
        pooldesc = self.client.make_pool(self.working_directory)
        # sys.stdout.write(f"make_pool_for_test={pooldesc}\n")
        return pooldesc

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
        # s3 = boto3.resource("s3")
        # Make S3 client for each access-key (for each policy).
        self.s3clients = dict()
        for k in keyslist:
            access_key = k["access_key"]
            secret_key = k["secret_key"]
            session0 = boto3.Session(
                profile_name="default",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key)
            s3 = session0.resource(
                service_name="s3", endpoint_url=url)
            policy = k["key_policy"]
            self.s3clients[policy] = s3
            pass
        assert self.s3clients.keys() == self.client.key_policy_set
        # Make a public access client (without a key).
        session1 = boto3.Session(profile_name="default")
        s3 = session1.resource(
            service_name="s3", endpoint_url=url,
            config=botocore.config.Config(signature_version=botocore.UNSIGNED))
        self.s3clients["void"] = s3
        print(f"void-s3={s3}")
        print(f"s3clients={self.s3clients}")
        pass

    def make_buckets(self):
        pooldesc = self.client.find_pool(self.working_directory)
        pool = pooldesc["pool_name"]
        for policy in self.client.bkt_policy_set:
            bucket = ("lenticularis-oddity-" + random_str(6).lower())
            while bucket in self.working_buckets:
                bucket = ("lenticularis-oddity-" + random_str(6).lower())
                pass
            assert bucket not in self.working_buckets
            print(f"Makeing a bucket bucket={bucket}")
            self.client.make_bucket(pool, bucket, policy)
            self.working_buckets.add(bucket)
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
        print("Storing a file in each bucket with the readwrite key.")
        data = open("gomi-file0.txt", "rb")
        s3 = self.s3clients["readwrite"]
        for (policy, bucket) in self.buckets.items():
            s3.Bucket(bucket).put_object(Key="gomi-file0.txt", Body=data)
            pass
        pass

    expectations = [
        # (bkt-policy, key-policy, op, expectation)
        ("none", "void", "w", Expectation("401")),
        ("none", "readwrite", "w", Expectation.OK),
        ("none", "readonly", "w", Expectation("AccessDenied")),
        ("none", "writeonly", "w", Expectation.OK),
        ("none", "void", "r", Expectation("401")),
        ("none", "readwrite", "r", Expectation.OK),
        ("none", "readonly", "r", Expectation.OK),
        ("none", "writeonly", "r", Expectation("AccessDenied")),

        ("upload", "void", "w", Expectation.OK),
        ("upload", "readwrite", "w", Expectation.OK),
        ("upload", "readonly", "w", Expectation("AccessDenied")),
        ("upload", "writeonly", "w", Expectation.OK),
        ("upload", "void", "r", Expectation("AccessDenied")),
        ("upload", "readwrite", "r", Expectation.OK),
        ("upload", "readonly", "r", Expectation.OK),
        ("upload", "writeonly", "r", Expectation("AccessDenied")),

        ("download", "void", "w", Expectation("AccessDenied")),
        ("download", "readwrite", "w", Expectation.OK),
        ("download", "readonly", "w", Expectation("AccessDenied")),
        ("download", "writeonly", "w", Expectation.OK),
        ("download", "void", "r", Expectation.OK),
        ("download", "readwrite", "r", Expectation.OK),
        ("download", "readonly", "r", Expectation.OK),
        ("download", "writeonly", "r", Expectation("AccessDenied")),

        ("public", "void", "w", Expectation.OK),
        ("public", "readwrite", "w", Expectation.OK),
        ("public", "readonly", "w", Expectation("AccessDenied")),
        ("public", "writeonly", "w", Expectation.OK),
        ("public", "void", "r", Expectation.OK),
        ("public", "readwrite", "r", Expectation.OK),
        ("public", "readonly", "r", Expectation.OK),
        ("public", "writeonly", "r", Expectation("AccessDenied"))
    ]

    def transfer_by_varying_policies(self):
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
                error = e.response["Error"]["Code"]
                # print(f"error={error}")
                assert expectation == Expectation(error)
            else:
                assert expectation == Expectation.OK
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

        # Test S3 clients with access-keys vs. bucket policies.

        self.make_s3_clients(url)
        self.make_buckets()
        self.store_files_in_buckets()
        self.transfer_by_varying_policies()

        # Bucket operations will fail (they do not work in Lens3).

        s3 = self.s3clients["readwrite"]

        # Listing buckets fails.

        try:
            r = list(s3.buckets.all())
            print(f"buckets.all()={r}")
        except botocore.exceptions.ClientError as e:
            error = e.response["Error"]["Code"]
            assert error == "401"
            pass
        bucket = ("lenticularis-oddity-" + random_str(6).lower())
        while bucket in self.working_buckets:
            bucket = ("lenticularis-oddity-" + random_str(6).lower())
            pass

        # Creating a bucket fails.

        try:
            r = s3.create_bucket(Bucket=bucket)
            print(f"create_bucket={r}")
        except botocore.exceptions.ClientError as e:
            error = e.response["Error"]["Code"]
            assert error == "404"
            pass

        # r = s3.delete_bucket(Bucket=bucket)
        # print(f"delete_bucket={r}")

        bucketname = self.buckets["none"]

        # List objects.

        bucket = s3.Bucket(bucketname)
        r = list(bucket.objects.all())
        print(f"bucket.objects.all()={r}")

        # Upload/download objects.

        print(f"Uploading/downloading a file via S3.Bucket API.")
        # upload_file(file, key); download_file(key, file)
        r = bucket.upload_file("gomi-file0.txt", "gomi-file1.txt")
        r = bucket.download_file("gomi-file1.txt", "gomi-file1.txt")
        object = bucket.Object("gomi-file1.txt")
        r = object.delete()

        # Upload/download files with varying sizes.

        for i in [0, 1, 2, 3]:
            size = 6113 * (13 ** i)
            print(f"Uploading/downloading a file (size={size}).")
            subprocess.run(["touch", "gomi0.txt"])
            subprocess.run(["shred", "-n", "1", "-s", f"{size}", "gomi0.txt"])
            name = f"gomi-file{i}.txt"
            r = bucket.upload_file("gomi0.txt", name)
            r = bucket.download_file(name, "gomi1.txt")
            with open("gomi0.txt", "rb") as f:
                data0 = f.read()
                pass
            with open("gomi1.txt", "rb") as f:
                data1 = f.read()
                pass
            assert data0 == data1
            del data0
            del data1
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
