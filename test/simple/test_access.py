"""Simple Access Test.  It accesses the store using boto3."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import enum
import sys
import time
import json
import subprocess
import botocore
import boto3
from lens3_client import Lens3_Client
from lens3_client import random_string
from test_api import Test_Base


class Respn(enum.Enum):
    OK = "OK"
    E401 = "401"
    E403 = "403"
    E503 = "503"
    EACCESSDENIED = "AccessDenied"

    def __str__(self):
        return self.value

    pass


class Access_Test(Test_Base):
    """S3 Access Test.  It tests various combinations of key policies and
    bucket policies.  Some uses keys that are expired -- they are
    created with 10 seconds and it assumes time elapses in some tests.
    self.s3_clients[0] holds S3 clients by access key policies, and
    self.s3_clients[1] is the same but with all keys expired.
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
            print(f"Making a bucket with policy={policy} bucket={bucket}")
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
                aws_access_key_id=access2,
                aws_secret_access_key=secret2)
            client1 = session1.resource(
                service_name="s3",
                endpoint_url=self.client.s3_ep,
                verify=self.client.ssl_verify)
            self.s3_clients[expired][policy2] = client1
            pass
        assert self.s3_clients[expired].keys() == self.client.key_policy_set
        #
        # Make an S3 client for public access (without a key).
        #
        session2 = boto3.Session()
        client2 = session2.resource(
            service_name="s3",
            endpoint_url=self.client.s3_ep,
            config=botocore.config.Config(signature_version=botocore.UNSIGNED),
            verify=self.client.ssl_verify)
        self.s3_clients[expired]["nokey"] = client2
        #
        # Make an S3 client with an unusable key (a key for another pool).
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
            aws_access_key_id=access3,
            aws_secret_access_key=secret3)
        client3 = session3.resource(
            service_name="s3",
            endpoint_url=self.client.s3_ep,
            verify=self.client.ssl_verify)
        self.s3_clients[expired]["other"] = client3
        print(f"s3clients={self.s3_clients[expired]}")
        pass

    def put_file_in_buckets(self):
        print("Storing a file in each bucket with the readwrite key.")
        subprocess.run(["rm", "-f", "gomi-file0.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        with open("gomi-file0.txt", "rb") as f:
            data = f.read()
            pass
        expired = 0
        s3 = self.s3_clients[expired]["readwrite"]
        for (policy, bucket) in self.buckets.items():
            s3.Bucket(bucket).put_object(Key="gomi-file0.txt", Body=data)
            pass
        pass

    # Expected responses.  Expectations in the table are fixed for
    # expired access keys as Respn("403") (excluding nokey and other
    # keys).

    expectations = [
        # (buket-policy, key-policy, op, expectation)
        ("none", "nokey", "w", Respn("401")),
        ("none", "other", "w", Respn("403")),
        ("none", "readwrite", "w", Respn.OK),
        ("none", "readonly", "w", Respn("AccessDenied")),
        ("none", "writeonly", "w", Respn.OK),
        ("none", "nokey", "r", Respn("401")),
        ("none", "other", "r", Respn("403")),
        ("none", "readwrite", "r", Respn.OK),
        ("none", "readonly", "r", Respn.OK),
        ("none", "writeonly", "r", Respn("AccessDenied")),

        ("upload", "nokey", "w", Respn.OK),
        ("upload", "other", "w", Respn("403")),
        ("upload", "readwrite", "w", Respn.OK),
        ("upload", "readonly", "w", Respn("AccessDenied")),
        ("upload", "writeonly", "w", Respn.OK),
        ("upload", "nokey", "r", Respn("AccessDenied")),
        ("upload", "other", "r", Respn("403")),
        ("upload", "readwrite", "r", Respn.OK),
        ("upload", "readonly", "r", Respn.OK),
        ("upload", "writeonly", "r", Respn("AccessDenied")),

        ("download", "nokey", "w", Respn("AccessDenied")),
        ("download", "other", "w", Respn("403")),
        ("download", "readwrite", "w", Respn.OK),
        ("download", "readonly", "w", Respn("AccessDenied")),
        ("download", "writeonly", "w", Respn.OK),
        ("download", "nokey", "r", Respn.OK),
        ("download", "other", "r", Respn("403")),
        ("download", "readwrite", "r", Respn.OK),
        ("download", "readonly", "r", Respn.OK),
        ("download", "writeonly", "r", Respn("AccessDenied")),

        ("public", "nokey", "w", Respn.OK),
        ("public", "other", "w", Respn("403")),
        ("public", "readwrite", "w", Respn.OK),
        ("public", "readonly", "w", Respn("AccessDenied")),
        ("public", "writeonly", "w", Respn.OK),
        ("public", "nokey", "r", Respn.OK),
        ("public", "other", "r", Respn("403")),
        ("public", "readwrite", "r", Respn.OK),
        ("public", "readonly", "r", Respn.OK),
        ("public", "writeonly", "r", Respn("AccessDenied"))
    ]

    def get_put_by_varying_policies(self, expired):
        assert expired == 0 or expired == 1
        with open("gomi-file0.txt", "rb") as f:
            data0 = f.read()
            pass
        for (bkt, key, op, expectation) in self.expectations:
            #time.sleep(10)
            # Fix an expectation for an expired key.
            if expired == 1 and key not in {"nokey", "other"}:
                expectation = Respn("403")
                pass
            expiration = "" if expired == 0 else ", expired"
            print(f"Accessing ({op}) a {bkt}-bucket"
                  f" with a {key}-key{expiration}.")
            s3 = self.s3_clients[expired][key]
            bucketname = self.buckets[bkt]
            bucket = s3.Bucket(bucketname)
            obj = bucket.Object("gomi-file0.txt")
            assert op in {"w", "r"}
            result = Respn.OK
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
                result = Respn(error)
                pass
            else:
                result = Respn.OK
                pass
            if not result == expectation:
                print(f"result={result}; expectation={expectation}")
                pass
            assert result == expectation
            pass
        pass

    def upload_file__(self):
        subprocess.run(["rm", "-f", "gomi-file0.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        data = open("gomi-file0.txt", "rb")
        #self.s3.Bucket("bktxxx").put_object(Key="gomi-file0.txt", Body=data)
        pass

    # return self.boto3_client.upload_fileobj(f, bucket, key)
    # return self.boto3_client.download_fileobj(bucket, key, f)

    def run(self):

        #
        # (1) Prepare for test.
        #

        self.make_s3_clients(0)
        self.make_s3_clients(1)
        self.make_buckets()

        #
        # (2) Test with various combinations of key+bucket policies.
        #

        self.put_file_in_buckets()
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
        subprocess.run(["rm", "-f", "gomi-file0.txt", "gomi-file1.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        # upload_file(file, key); download_file(key, file)
        r = bucket.upload_file("gomi-file0.txt", "gomi-file1.txt")
        r = bucket.download_file("gomi-file1.txt", "gomi-file1.txt")
        object = bucket.Object("gomi-file1.txt")
        r = object.delete()

        #
        # (6) Upload/download files with varying sizes.
        #

        src6 = "gomi-file0.txt"
        dst6 = "gomi-file1.txt"
        subprocess.run(["rm", "-f", src6, dst6])
        for i in [0, 1, 2, 3]:
            size = 6113 * (13 ** i)
            print(f"Uploading/downloading a file (size={size}).")
            subprocess.run(["touch", src6])
            subprocess.run(["shred", "-n", "1", "-s", f"{size}", src6])
            name = f"gomi-file{i+3}.txt"
            r = bucket.upload_file(src6, name)
            r = bucket.download_file(name, dst6)
            with open(src6, "rb") as f:
                data0 = f.read()
                pass
            with open(dst6, "rb") as f:
                data1 = f.read()
                pass
            assert data0 == data1
            del data0
            del data1
            subprocess.run(["rm", "-f", src6, dst6])
            pass
        pass

    pass


def main2():
    global client2, test2
    print(f"ACCESS TEST...")
    client2 = Lens3_Client("client.json")
    client2.get_user_info()

    test2 = Access_Test(client2)
    print(f"Making working pools for test...")
    test2.make_working_pool()
    test2.make_another_pool()
    try:
        test2.run()
    finally:
        clean_working_pools = True
        if clean_working_pools:
            print(f";; Deleting a working pool={test2.working_pool}")
            test2.client.delete_pool(test2.working_pool)
            print(f";; Deleting a working pool={test2.another_pool}")
            test2.client.delete_pool(test2.another_pool)
        else:
            print(f";; Leave a working pool={test2.working_pool}")
            print(f";; Leave a working pool={test2.another_pool}")
            pass
        pass
    print("Done")
    pass


# >>> exec(open("test_access.py").read())

if __name__ == "__main__":
    main2()
    pass
