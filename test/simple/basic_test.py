"""Lens3 Simple Test."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import enum
import string
import random
import sys
import time
import json
import subprocess
import contextvars
import urllib.error
import botocore
import boto3
from apiclient import Lens3_Client


class Expectation(enum.Enum):
    OK = "OK"
    E401 = "401"
    E403 = "403"
    EACCESSDENIED = "AccessDenied"

    def __str__(self):
        return self.value

    pass


def random_string(n):
    astr = string.ascii_letters
    bstr = string.ascii_letters + string.digits
    a = random.SystemRandom().choice(astr)
    b = (random.SystemRandom().choice(bstr) for _ in range(n - 1))
    return (a + "".join(b)).lower()


class Test_Base():
    def __init__(self, client):
        self.client = client
        self.working_directory = ""
        self.working_pool = ""
        pass

    def make_pool_for_test(self):
        """Makes a pool in a directory with a random name."""
        assert self.working_directory == ""
        self.working_directory = (self.client.home + "/00"
                                  + random_string(6))
        desc = self.client.make_pool(self.working_directory)
        self.working_pool = desc["pool_name"]
        return desc

    pass


class Api_Test(Test_Base):
    """Simple API Test.  It makes a pool, then makes buckets and
    access-keys.  It tries to make a conflicting bucket and fails.
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
        # (3) Make access-keys -- one for each policy.
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
            assert e.code == 403
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
        # (7) Delete access-keys.  Delete buckets.
        #

        desc7 = self.client.find_pool(self.working_directory)
        keys7 = desc7["access_keys"]
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


class Access_Test(Test_Base):
    """S3 Access Test.  self.s3_clients[0] holds S3 clients by access key
    policies, and self.s3_clients[1] is the same but with all keys
    expired.
    """

    def __init__(self, client):
        super().__init__(client)
        self.s3_clients = [dict(), dict()]
        self.working_buckets = set()
        self.buckets = dict()
        self.another_pool = ""
        pass

    def make_another_pool(self):
        while True:
            directory = (self.client.home + "/00" + random_string(6))
            if directory != self.working_directory:
                break
            pass
        assert directory != self.working_directory
        desc = self.client.make_pool(directory)
        self.another_pool = desc["pool_name"]
        return

    def _set_traceid(self, traceid):
        """Adds a header entry.  See [Adding custom headers to all boto3
        requests] https://stackoverflow.com/questions/58828800
        """
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

    def make_buckets(self):
        """Makes buckets one for each policy."""
        desc1 = self.client.find_pool(self.working_directory)
        pid = desc1["pool_name"]
        for policy in self.client.bkt_policy_set:
            bucket = ("lenticularis-oddity-" + random_string(6))
            while bucket in self.working_buckets:
                bucket = ("lenticularis-oddity-" + random_string(6))
                pass
            assert bucket not in self.working_buckets
            print(f"Making a bucket bucket={bucket}")
            self.client.make_bucket(self.working_pool, bucket, policy)
            self.working_buckets.add(bucket)
            pass
        desc2 = self.client.find_pool(self.working_directory)
        bktslist = desc2["buckets"]
        for b in bktslist:
            policy = b["bkt_policy"]
            self.buckets[policy] = b["name"]
            pass
        assert self.buckets.keys() == self.client.bkt_policy_set
        pass

    def make_s3_clients(self, expired):
        """Makes S3 clients one for each access-key (for each policy)."""
        assert expired == 0 or expired == 1
        now = int(time.time())
        if expired == 0:
            expiration = now + (24 * 3600)
        else:
            expiration = now + 10
            pass
        #
        # Make an S3 client for each access-key.
        #
        for policy in self.client.key_policy_set:
            print(f"Making an access-key with policy={policy}")
            self.client.make_secret(self.working_pool, policy, expiration)
            pass
        desc2 = self.client.get_pool(self.working_pool)
        keyslist2 = [k for k in desc2["access_keys"]
                     if k["expiration_time"] == expiration]
        assert len(keyslist2) == len(self.client.key_policy_set)
        # s3 = boto3.resource("s3")
        for k in keyslist2:
            access2 = k["access_key"]
            secret2 = k["secret_key"]
            policy2 = k["key_policy"]
            session1 = boto3.Session(
                profile_name="default",
                aws_access_key_id=access2,
                aws_secret_access_key=secret2)
            sc1 = session1.resource(
                service_name="s3",
                endpoint_url=self.client.s3_ep,
                verify=self.client.ssl_verify)
            self.s3_clients[expired][policy2] = sc1
            pass
        assert self.s3_clients[expired].keys() == self.client.key_policy_set
        #
        # Make a public access client (without a key).
        #
        session2 = boto3.Session(profile_name="default")
        sc2 = session2.resource(
            service_name="s3",
            endpoint_url=self.client.s3_ep,
            config=botocore.config.Config(signature_version=botocore.UNSIGNED),
            verify=self.client.ssl_verify)
        self.s3_clients[expired]["nokey"] = sc2
        #
        # Make a readwrite access client for another pool.
        #
        policy3 = "readwrite"
        assert policy3 in self.client.key_policy_set
        desc3 = self.client.make_secret(self.another_pool, policy3, expiration)
        keyslist3 = [k for k in desc3["access_keys"]
                     if k["expiration_time"] == expiration]
        assert len(keyslist3) == 1
        k3 = keyslist3[0]
        access3 = k3["access_key"]
        secret3 = k3["secret_key"]
        session3 = boto3.Session(
            profile_name="default",
            aws_access_key_id=access3,
            aws_secret_access_key=secret3)
        sc3 = session3.resource(
            service_name="s3",
            endpoint_url=self.client.s3_ep,
            verify=self.client.ssl_verify)
        self.s3_clients[expired]["other"] = sc3
        print(f"s3clients={self.s3_clients[expired]}")
        pass

    def put_files_in_buckets(self):
        expired = 0
        print("Storing a file in each bucket with the readwrite key.")
        data = open("gomi-file0.txt", "rb")
        s3 = self.s3_clients[expired]["readwrite"]
        for (policy, bucket) in self.buckets.items():
            s3.Bucket(bucket).put_object(Key="gomi-file0.txt", Body=data)
            pass
        pass

    expectations = [
        # (buket-policy, key-policy, op, expectation)
        ("none", "nokey", "w", Expectation("401")),
        ("none", "other", "w", Expectation("403")),
        ("none", "readwrite", "w", Expectation.OK),
        ("none", "readonly", "w", Expectation("AccessDenied")),
        ("none", "writeonly", "w", Expectation.OK),
        ("none", "nokey", "r", Expectation("401")),
        ("none", "other", "r", Expectation("403")),
        ("none", "readwrite", "r", Expectation.OK),
        ("none", "readonly", "r", Expectation.OK),
        ("none", "writeonly", "r", Expectation("AccessDenied")),

        ("upload", "nokey", "w", Expectation.OK),
        ("upload", "other", "w", Expectation("403")),
        ("upload", "readwrite", "w", Expectation.OK),
        ("upload", "readonly", "w", Expectation("AccessDenied")),
        ("upload", "writeonly", "w", Expectation.OK),
        ("upload", "nokey", "r", Expectation("AccessDenied")),
        ("upload", "other", "r", Expectation("403")),
        ("upload", "readwrite", "r", Expectation.OK),
        ("upload", "readonly", "r", Expectation.OK),
        ("upload", "writeonly", "r", Expectation("AccessDenied")),

        ("download", "nokey", "w", Expectation("AccessDenied")),
        ("download", "other", "w", Expectation("403")),
        ("download", "readwrite", "w", Expectation.OK),
        ("download", "readonly", "w", Expectation("AccessDenied")),
        ("download", "writeonly", "w", Expectation.OK),
        ("download", "nokey", "r", Expectation.OK),
        ("download", "other", "r", Expectation("403")),
        ("download", "readwrite", "r", Expectation.OK),
        ("download", "readonly", "r", Expectation.OK),
        ("download", "writeonly", "r", Expectation("AccessDenied")),

        ("public", "nokey", "w", Expectation.OK),
        ("public", "other", "w", Expectation("403")),
        ("public", "readwrite", "w", Expectation.OK),
        ("public", "readonly", "w", Expectation("AccessDenied")),
        ("public", "writeonly", "w", Expectation.OK),
        ("public", "nokey", "r", Expectation.OK),
        ("public", "other", "r", Expectation("403")),
        ("public", "readwrite", "r", Expectation.OK),
        ("public", "readonly", "r", Expectation.OK),
        ("public", "writeonly", "r", Expectation("AccessDenied"))
    ]

    def get_put_by_varying_policies(self, expired):
        assert expired == 0 or expired == 1
        data0 = open("gomi-file0.txt", "rb").read()
        for (bkt, key, op, expectation) in self.expectations:
            # Fix an expectation for an expired key.
            if expired == 1 and key not in {"nokey", "other"}:
                expectation = Expectation("403")
                pass
            expiration = "" if expired == 0 else ", expired"
            print(f"Accessing ({op}) a {bkt}-bucket"
                  f" with a {key}-key{expiration}.")
            s3 = self.s3_clients[expired][key]
            bucketname = self.buckets[bkt]
            bucket = s3.Bucket(bucketname)
            obj = bucket.Object("gomi-file0.txt")
            assert op in {"w", "r"}
            result = Expectation.OK
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
                result = Expectation(error)
                pass
            else:
                result = Expectation.OK
                pass
            if not result == expectation:
                print(f"result={result}; expectation={expectation}")
            assert result == expectation
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

    def run(self):

        #
        # (1) Prepare for test.  Make a test file (random 64KB).
        #

        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])

        self.make_s3_clients(0)
        self.make_s3_clients(1)
        self.make_buckets()

        #
        # (2) Test S3 clients with access-keys vs. bucket policies.
        #

        self.put_files_in_buckets()
        self.get_put_by_varying_policies(0)
        self.get_put_by_varying_policies(1)

        #
        # (3) Bucket operations that will fail (in Lens3).
        #

        s3 = self.s3_clients[0]["readwrite"]

        #
        # (3.1) Listing buckets (fails).
        #

        try:
            r = list(s3.buckets.all())
            print(f"buckets.all()={r}")
        except botocore.exceptions.ClientError as e:
            error = e.response["Error"]["Code"]
            assert error == "401"
            pass
        bucket = ("lenticularis-oddity-" + random_string(6))
        while bucket in self.working_buckets:
            bucket = ("lenticularis-oddity-" + random_string(6))
            pass

        #
        # (3.2) Creating a bucket (fails).
        #

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

        #
        # (4) List objects.
        #

        bucket = s3.Bucket(bucketname)
        r = list(bucket.objects.all())
        print(f"bucket.objects.all()={r}")

        #
        # (5) Upload/download objects.
        #

        print(f"Uploading/downloading a file via S3.Bucket API.")
        # upload_file(file, key); download_file(key, file)
        r = bucket.upload_file("gomi-file0.txt", "gomi-file1.txt")
        r = bucket.download_file("gomi-file1.txt", "gomi-file1.txt")
        object = bucket.Object("gomi-file1.txt")
        r = object.delete()

        #
        # (6) Upload/download files with varying sizes.
        #

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


def main1():
    global client1, test1
    client1 = Lens3_Client("client.json")
    client1.get_user_info()

    test1 = Api_Test(client1)
    print(f"API TEST...")
    print(f"Making a pool for test...")
    desc1 = test1.make_pool_for_test()
    print(f"A pool={desc1}")
    try:
        test1.run()
    finally:
        print(f"Deleting a pool={test1.working_pool}")
        test1.client.delete_pool(test1.working_pool)
        pass
    print("Done")
    pass


def main2():
    global client2, test2
    client2 = Lens3_Client("client.json")
    client2.get_user_info()

    test2 = Access_Test(client2)
    print(f"ACCESS TEST...")
    print(f"Making a pool for test...")
    desc2 = test2.make_pool_for_test()
    print(f"A pool={desc2}")
    test2.make_another_pool()
    try:
        test2.run()
    finally:
        print(f"Deleting a pool={test2.working_pool}")
        test2.client.delete_pool(test2.working_pool)
        print(f"Deleting a pool={test2.another_pool}")
        test2.client.delete_pool(test2.another_pool)
        pass
    print("Done")
    pass


# >>> exec(open("basic_test.py").read())

if __name__ == "__main__":
    main1()
    main2()
    pass
