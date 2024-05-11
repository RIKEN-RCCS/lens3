"""Test Disabling User."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import enum
import sys
import time
import json
import redis
from redis import Redis
import subprocess
import botocore
import boto3


_SETTING_DB = 0
_user_info_prefix = "uu:"


class User_Disable_Test():
    """...
    """

    def __init__(self):
        self.conf = None
        self.s3_client = None
        self.db = None
        with open("user_disable_conf.json") as f:
            self.conf = json.loads(f.read())
            pass
        pass

    def connect_to_redis(self):
        redis_conf = self.conf["redis"]
        host = redis_conf["host"]
        port = redis_conf["port"]
        db = _SETTING_DB
        password = redis_conf["password"]
        self.db = Redis(host=host, port=port, db=db, password=password,
                        charset="utf-8", decode_responses=True)
        while True:
            try:
                self.db.ping()
                return
            except redis.ConnectionError:
                print("Connecting to Redis failed, sleeping in 10 sec.")
                time.sleep(10)
                pass
            pass
        pass

    def toggle_enabled(self, uid, onoff):
        assert isinstance(onoff, bool)
        key = f"{_user_info_prefix}{uid}"
        v1 = self.db.get(key)
        if v1 is None:
            raise Error(f"User not registered: {uid}")
        userinfo = json.loads(v1)
        # Set {"uid", "claim", "groups", "enabled", "modification_time"}.
        userinfo["enabled"] = onoff
        v2 = json.dumps(userinfo)
        self.db.set(key, v2)
        pass

    def make_s3_client(self):
        ep = self.conf["endpoint"]
        ssl_verify = self.conf["ssl_verify"]
        access1 = self.conf["access_key"]
        secret1 = self.conf["secret_key"]
        session1 = boto3.Session(
            aws_access_key_id=access1,
            aws_secret_access_key=secret1)
        client1 = session1.resource(
            service_name="s3",
            endpoint_url=ep,
            verify=ssl_verify)
        self.s3_client = client1
        pass

    def make_data_file(self):
        print("Making a file.")
        subprocess.run(["rm", "-f", "gomi-file0.txt"])
        subprocess.run(["touch", "gomi-file0.txt"])
        subprocess.run(["shred", "-n", "1", "-s", "64K", "gomi-file0.txt"])
        pass

    def run(self):
        self.connect_to_redis()
        self.make_s3_client()
        self.make_data_file()
        with open("gomi-file0.txt", "rb") as f:
            data = f.read()
            pass
        s3 = self.s3_client
        bucketname = self.conf["bucket"]
        bucket = s3.Bucket(bucketname)
        obj = bucket.Object("gomi-file0.txt")
        uid = self.conf["user"]
        #
        # Expect no error...
        #
        print("Set a user enabled=true, and put an object...")
        self.toggle_enabled(uid, True)
        obj.put(Body=data)
        #
        # Expect an error...
        #
        print("Set a user enabled=false, and put an object...")
        self.toggle_enabled(uid, False)
        try:
            obj.put(Body=data)
        except botocore.exceptions.ClientError as ex:
            assumed_error_code = "403"
            if not ex.response["Error"]["Code"] == assumed_error_code:
                raise
            pass
        #
        # Expect no error...
        #
        print("Set a user enabled=true, and put an object...")
        self.toggle_enabled(uid, True)
        obj.put(Body=data)
        pass

    pass


def main():
    print(f"NOTICE: THIS MAY LEAVE A USER IN DISABLED STATE.")
    print(f"DISABLING USER TEST...")
    testcase = User_Disable_Test()
    testcase.run()
    print("Done")
    pass


# >>> exec(open("run-admin-work.py").read())

if __name__ == "__main__":
    main()
    pass
