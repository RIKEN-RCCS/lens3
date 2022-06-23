"""Tests on S3 Accesses thru Lens3."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import time
import yaml
import subprocess
import contextvars
import boto3
from lens3client import tracing
from lens3client import random_str


class S3_Test():
    """S3 cleint wrapper."""

    def __init__(self):
        url = "http://fgkvm-010-128-008-026.fdcs.r-ccs.riken.jp:8009"
        self.access_key = None
        self.secret_key = None
        self.session = boto3.Session(profile_name="default")
        self.s3 = self.session.resource(
            service_name="s3", endpoint_url=url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key)
        #self.s3 = boto3.resource("s3")
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

    def upload_file(self):
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        data = open("gomi-file0.txt", "rb")
        self.s3.Bucket("bktxxx").put_object(Key="gomi-file0.txt", Body=data)
        pass

    pass


# self.boto3_client = boto3.client
# self.s3 = boto3.client()

# r = self.s3.list_buckets()
# return r["Buckets"]

# r = self.s3.create_bucket(Bucket=bucket)
# r = self.s3.delete_bucket(Bucket=bucket)

# r = self.s3.list_objects(Bucket=bucket)
# return r["Contents"]

# r = self.s3.upload_fileobj(f, bucket, key)
# r = self.s3.download_fileobj(bucket, key, f)
# r = self.s3.delete_object(Bucket=bucket, Key=key)

def read_test_conf():
    try:
        with open("testv.yaml", "r") as f:
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
    test = S3_Test()
    test.upload_file()
    pass


if __name__ == "__main__":
    run()
