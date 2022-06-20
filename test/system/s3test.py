"""Tests on S3 (thru Lens3)."""

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
        self.session = boto3.Session(profile_name="default")
        self.s3 = self.session.resource(service_name="s3", endpoint_url=url)
        #self.s3 = boto3.resource("s3")
        pass
 
    def upload_file(self):
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        data = open("gomi-file0.txt", "rb")
        self.s3.Bucket("bktxxx").put_object(Key="gomi-file0.txt", Body=data)
        pass

    pass


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
