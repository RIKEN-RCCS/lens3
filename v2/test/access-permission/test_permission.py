"""Access Permission Test.  It accesses the store using boto3."""

# Copyright 2022-2024 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# Boto3 API reference is
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html

import enum
import sys
import time
import json
import subprocess
import botocore
import boto3

sys.path.append("../lib/")

from lens3_client import Lens3_Registrar
from lens3_client import random_string


_verbose = True

def _verbose_print(*args):
    if _verbose:
        print(*args)
        pass
    pass


class Respn(enum.Enum):
    OK = "OK"
    E401 = "401"
    E403 = "403"
    E503 = "503"
    EACCESSDENIED = "AccessDenied"

    def __str__(self):
        return self.value

    pass


# Expected responses.  Expectations in the table are fixed for
# expired access keys as Respn("403") (excluding nokey and other
# keys).
#
# (key-policy, buket-policy, op, expectation)

_expectations = [
    ("nokey", "download", "head",       Respn.OK),
    ("nokey", "download", "get",        Respn.OK),
    ("nokey", "download", "put",        Respn("403")),
    ("nokey", "download", "delete",     Respn("403")),
    ("nokey", "download", "post",       Respn("403")),

    ("nokey", "none", "head",           Respn("403")),
    ("nokey", "none", "get",            Respn("403")),
    ("nokey", "none", "put",            Respn("403")),
    ("nokey", "none", "delete",         Respn("403")),
    ("nokey", "none", "post",           Respn("403")),

    ("nokey", "public", "head",         Respn.OK),
    ("nokey", "public", "get",          Respn.OK),
    ("nokey", "public", "put",          Respn.OK),
    ("nokey", "public", "delete",       Respn.OK),
    ("nokey", "public", "post",         Respn.OK),

    ("nokey", "upload", "head",         Respn("403")),
    ("nokey", "upload", "get",          Respn("403")),
    ("nokey", "upload", "put",          Respn.OK),
    ("nokey", "upload", "delete",       Respn.OK),
    ("nokey", "upload", "post",         Respn.OK),

    ("badkey", "download", "head",      Respn("403")),
    ("badkey", "download", "get",       Respn("403")),
    ("badkey", "download", "put",       Respn("403")),
    ("badkey", "download", "delete",    Respn("403")),
    ("badkey", "download", "post",      Respn("403")),

    ("badkey", "none", "head",          Respn("403")),
    ("badkey", "none", "get",           Respn("403")),
    ("badkey", "none", "put",           Respn("403")),
    ("badkey", "none", "delete",        Respn("403")),
    ("badkey", "none", "post",          Respn("403")),

    ("badkey", "public", "head",        Respn("403")),
    ("badkey", "public", "get",         Respn("403")),
    ("badkey", "public", "put",         Respn("403")),
    ("badkey", "public", "delete",      Respn("403")),
    ("badkey", "public", "post",        Respn("403")),

    ("badkey", "upload", "head",        Respn("403")),
    ("badkey", "upload", "get",         Respn("403")),
    ("badkey", "upload", "put",         Respn("403")),
    ("badkey", "upload", "delete",      Respn("403")),
    ("badkey", "upload", "post",        Respn("403")),

    ("readonly", "download", "head",    Respn.OK),
    ("readonly", "download", "get",     Respn.OK),
    ("readonly", "download", "put",     Respn("403")),
    ("readonly", "download", "delete",  Respn("403")),
    ("readonly", "download", "post",    Respn("403")),

    ("readonly", "none", "head",        Respn.OK),
    ("readonly", "none", "get",         Respn.OK),
    ("readonly", "none", "put",         Respn("403")),
    ("readonly", "none", "delete",      Respn("403")),
    ("readonly", "none", "post",        Respn("403")),

    ("readonly", "public", "head",      Respn.OK),
    ("readonly", "public", "get",       Respn.OK),
    ("readonly", "public", "put",       Respn("403")),
    ("readonly", "public", "delete",    Respn("403")),
    ("readonly", "public", "post",      Respn("403")),

    ("readonly", "upload", "head",      Respn.OK),
    ("readonly", "upload", "get",       Respn.OK),
    ("readonly", "upload", "put",       Respn("403")),
    ("readonly", "upload", "delete",    Respn("403")),
    ("readonly", "upload", "post",      Respn("403")),

    ("readwrite", "download", "head",   Respn.OK),
    ("readwrite", "download", "get",    Respn.OK),
    ("readwrite", "download", "put",    Respn.OK),
    ("readwrite", "download", "delete", Respn.OK),
    ("readwrite", "download", "post",   Respn.OK),

    ("readwrite", "none", "head",       Respn.OK),
    ("readwrite", "none", "get",        Respn.OK),
    ("readwrite", "none", "put",        Respn.OK),
    ("readwrite", "none", "delete",     Respn.OK),
    ("readwrite", "none", "post",       Respn.OK),

    ("readwrite", "public", "head",     Respn.OK),
    ("readwrite", "public", "get",      Respn.OK),
    ("readwrite", "public", "put",      Respn.OK),
    ("readwrite", "public", "delete",   Respn.OK),
    ("readwrite", "public", "post",     Respn.OK),

    ("readwrite", "upload", "head",     Respn.OK),
    ("readwrite", "upload", "get",      Respn.OK),
    ("readwrite", "upload", "put",      Respn.OK),
    ("readwrite", "upload", "delete",   Respn.OK),
    ("readwrite", "upload", "post",     Respn.OK),

    ("writeonly", "download", "head",   Respn("403")),
    ("writeonly", "download", "get",    Respn("403")),
    ("writeonly", "download", "put",    Respn.OK),
    ("writeonly", "download", "delete", Respn.OK),
    ("writeonly", "download", "post",   Respn.OK),

    ("writeonly", "none", "head",       Respn("403")),
    ("writeonly", "none", "get",        Respn("403")),
    ("writeonly", "none", "put",        Respn.OK),
    ("writeonly", "none", "delete",     Respn.OK),
    ("writeonly", "none", "post",       Respn.OK),

    ("writeonly", "public", "head",     Respn("403")),
    ("writeonly", "public", "get",      Respn("403")),
    ("writeonly", "public", "put",      Respn.OK),
    ("writeonly", "public", "delete",   Respn.OK),
    ("writeonly", "public", "post",     Respn.OK),

    ("writeonly", "upload", "head",     Respn("403")),
    ("writeonly", "upload", "get",      Respn("403")),
    ("writeonly", "upload", "put",      Respn.OK),
    ("writeonly", "upload", "delete",   Respn.OK),
    ("writeonly", "upload", "post",     Respn.OK),
]


_UNEXPIRED = 0


class Access_Test():
    """S3 Access Test.  It tests various combinations of key policies and
    bucket policies.  Some uses keys that are expired -- they are
    created with 10 seconds and it assumes time elapses in some tests.
    self.s3_clients[0] holds S3 clients by access key policies, and
    self.s3_clients[1] is the same but with all keys expired.
    """

    def __init__(self, client):
        self.client = client
        self.working_directory = ""
        self.working_pool = ""
        # super().__init__(client)
        self.s3_clients = [dict(), dict()]
        self.working_buckets = set()
        self.buckets = dict()
        self.another_pool = ""
        pass

    def make_working_pool(self):
        """Makes a pool in a directory with a random name."""
        assert self.working_directory == ""
        self.working_directory = (self.client.home + "/00"
                                  + random_string(6))
        desc = self.client.make_pool(self.working_directory)
        self.working_pool = desc["pool_name"]
        return desc


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
        print(f"Making buckets...")
        desc1 = self.client.find_pool(self.working_directory)
        pid = desc1["pool_name"]
        for policy in self.client.bkt_policy_set:
            bucket = ("lenticularis-oddity-" + random_string(6))
            while bucket in self.working_buckets:
                bucket = ("lenticularis-oddity-" + random_string(6))
                pass
            assert bucket not in self.working_buckets
            print(f";; Bucket with policy={policy} bucket={bucket}")
            self.client.make_bucket(self.working_pool, bucket, policy)
            self.working_buckets.add(bucket)
            pass
        desc2 = self.client.find_pool(self.working_directory)
        bktslist = desc2["buckets"]
        for b in bktslist:
            # _verbose_print(f";; b={b}")
            policy = b["bkt_policy"]
            self.buckets[policy] = b["name"]
            pass
        assert self.buckets.keys() == self.client.bkt_policy_set
        pass

    def make_s3_clients(self, expired):
        """Makes S3 clients one for each access-key and for each policy.  Use
10 sec durlation for making quickly expiring keys.
        """
        region = "us-east-1"
        assert expired == 0 or expired == 1
        now = int(time.time())
        if expired == 0:
            expiration = now + (24 * 3600)
        else:
            expiration = now + 10
            pass

        #
        # (1) Make an S3 client for each access-key.
        #

        print(f"Making access keys...")
        for policy in self.client.key_policy_set:
            print(f";; Access-key with policy={policy} expired={expired}")
            self.client.make_secret(self.working_pool, policy, expiration)
            pass
        desc2 = self.client.get_pool(self.working_pool)
        keyslist2 = [k for k in desc2["secrets"]
                     if k["expiration_time"] == expiration]
        assert len(keyslist2) == len(self.client.key_policy_set)
        print(f"Making S3 cleints...")
        for k in keyslist2:
            access2 = k["access_key"]
            secret2 = k["secret_key"]
            policy2 = k["key_policy"]
            client1 = boto3.client(
                service_name="s3",
                region_name=region,
                endpoint_url=self.client.s3_ep,
                aws_access_key_id=access2,
                aws_secret_access_key=secret2,
                config=botocore.config.Config(signature_version="s3v4"))
            _verbose_print(f";; s3-client {policy2}; {access2}, {secret2}")
            self.s3_clients[expired][policy2] = client1
            pass
        assert self.s3_clients[expired].keys() == self.client.key_policy_set

        #
        # (2) Make an S3 client without a key (for public access).
        #

        c = boto3.client(
            service_name="s3",
            region_name=region,
            endpoint_url=self.client.s3_ep,
            config=botocore.config.Config(signature_version=botocore.UNSIGNED))
        self.s3_clients[expired]["nokey"] = c

        #
        # (3) Make an S3 client with an unusable key (a key for another pool).
        #

        policy3 = "readwrite"
        assert policy3 in self.client.key_policy_set
        desc3 = self.client.make_secret(self.another_pool, policy3, expiration)
        keyslist3 = [k for k in desc3["secrets"]
                     if k["expiration_time"] == expiration]
        # _verbose_print(f";; keyslist3={keyslist3}")
        assert len(keyslist3) == 1
        k3 = keyslist3[0]
        access3 = k3["access_key"]
        secret3 = k3["secret_key"]
        client3 = boto3.client(
            service_name="s3",
            region_name=region,
            endpoint_url=self.client.s3_ep,
            aws_access_key_id=access3,
            aws_secret_access_key=secret3,
            config=botocore.config.Config(signature_version="s3v4"))
        self.s3_clients[expired]["badkey"] = client3
        #print(f"s3clients[expired={expired}]={client3}")
        pass

    def put_file_in_buckets(self):
        print("Storing a file in each bucket with the readwrite key...")
        subprocess.run(["rm", "-f", "gomi-file0.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        with open("gomi-file0.txt", "rb") as f:
            data = f.read()
            pass
        s3 = self.s3_clients[_UNEXPIRED]["readwrite"]
        for (policy, bucket) in self.buckets.items():
            _verbose_print(f";; Store to bucket={bucket}")
            #- s3.Bucket(bucket).put_object(Key="gomi-file0.txt", Body=data)
            s3.put_object(
                Body=data,
                Bucket=bucket,
                Key="gomi-file0.txt")
            pass
        pass

    def get_put_by_varying_policies(self, expired):
        assert expired == 0 or expired == 1
        with open("gomi-file0.txt", "rb") as f:
            data0 = f.read()
            pass
        for (key, bkt, op, expectation) in _expectations:
            bucket = self.buckets[bkt]
            # Copy a file each time for delete operations.
            s3rw = self.s3_clients[_UNEXPIRED]["readwrite"]
            s3rw.put_object(
                Body=data0,
                Bucket=bucket,
                Key="gomi-file0.txt")
            # Fix an expectation for an expired key.
            if expired == 1 and key not in {"nokey", "badkey"}:
                expectation = Respn("403")
                pass
            #expiration = "" if expired == 0 else ", expired"
            #print(f"Accessing ({op}) a {bkt}-bucket"
            #      f" with a {key}-key{expiration}.")
            s3 = self.s3_clients[expired][key]
            assert op in {"head", "get", "put", "delete", "post"}
            result = Respn.OK
            try:
                if op == "head":
                    response = s3.head_object(
                        Bucket=bucket,
                        Key="gomi-file0.txt")
                    len1 = response["ContentLength"]
                    assert len(data0) == len1
                elif op == "get":
                    response = s3.get_object(
                        Bucket=bucket,
                        Key="gomi-file0.txt")
                    data1 = response["Body"].read()
                    assert data0 == data1
                elif op == "put":
                    response = s3.put_object(
                        Body=data0,
                        Bucket=bucket,
                        Key="gomi-file0.txt")
                elif op == "delete":
                    response = s3.delete_object(
                        Bucket=bucket,
                        Key="gomi-file0.txt")
                elif op == "post":
                    response = s3.delete_objects(
                        Bucket=bucket,
                        Delete={
                            "Objects": [
                                {
                                    "Key": "gomi-file0.txt"
                                },
                            ]
                        })
                else:
                    assert False
            except botocore.exceptions.ClientError as e:
                #except urllib.error.HTTPError as e:
                error = e.response["Error"]["Code"]
                result = Respn(error)
                pass
            else:
                result = Respn.OK
                pass
            flag = "" if expired == 0 else "/expired"
            print(f"Accessing {bkt}-bucket with {key}-key{flag}"
                  f" by {op}: {result}")
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
            #- r = list(s3.buckets.all())
            r = list(s3.list_buckets())
            print(f"buckets.all()={r}")
        except botocore.exceptions.ClientError as e:
            error = e.response["Error"]["Code"]
            assert error == "400"
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

        #
        # (4) List objects.
        #

        bucketname = self.buckets["none"]
        r = s3.list_objects_v2(
            Bucket=bucketname)
        objects = r["Contents"]
        # print(f"bucket.objects.all()={objects}")

        #
        # (5) Upload/download objects.
        #

        print(f"Uploading/downloading a file via S3.Bucket API.")
        subprocess.run(["rm", "-f", "gomi-file0.txt", "gomi-file1.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        r = s3.upload_file("gomi-file0.txt", bucketname, "gomi-file1.txt")
        r = s3.download_file(bucketname, "gomi-file1.txt", "gomi-file1.txt")
        r = s3.delete_object(
            Bucket=bucketname,
            Key="gomi-file1.txt")

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
            r = s3.upload_file(src6, bucketname, name)
            r = s3.download_file(bucketname, name, dst6)
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


def main():
    global registrar, testcase
    print(f"ACCESS TEST...")
    registrar = Lens3_Registrar("client.json")
    registrar.get_user_info()

    testcase = Access_Test(registrar)
    print(f"Making working pools for test...")
    testcase.make_working_pool()
    testcase.make_another_pool()
    try:
        testcase.run()
    finally:
        clean_working_pools = True
        if clean_working_pools:
            print(f";; Deleting a working pool={testcase.working_pool}")
            testcase.client.delete_pool(testcase.working_pool)
            print(f";; Deleting a working pool={testcase.another_pool}")
            testcase.client.delete_pool(testcase.another_pool)
        else:
            print(f";; Leave a working pool={testcase.working_pool}")
            print(f";; Leave a working pool={testcase.another_pool}")
            pass
        pass
    print("Done")
    pass


# >>> exec(open("test_access.py").read())

if __name__ == "__main__":
    main()
    pass
