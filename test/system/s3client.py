# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from api_manipulation import accesskey_of_a_zone
import configparser
import boto3
from botocore.config import Config
#from botocore.exceptions import ClientError
from lentclient import LentClient
from lenticularis.utility import logger
from lenticularis.utility import random_str
import sys
import threading


class S3client(object):

    def __init__(self, access_key_id, secret_access_key, endpoint_url):
        self.traceid = None
        self.boto3_client = self.create_boto3_client(access_key_id,
                                              secret_access_key, endpoint_url)

    def create_boto3_client(self, access_key_id, secret_access_key, endpoint_url):
        logger.debug(f"access_key_id: {access_key_id}")
        logger.debug(f"secret_access_key: {secret_access_key}")
        logger.debug(f"endpoint_url: {endpoint_url}")

        config = Config(
           retries = {
              "max_attempts": 10,
              "mode": "standard"
           }
        )

        return boto3.client("s3",
                            verify=False,
                            aws_access_key_id=access_key_id,
                            aws_secret_access_key=secret_access_key,
                            endpoint_url=endpoint_url,
                            config=config)

    def close_connection(self):
        pass

    def list_buckets(self):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] list_buckets")
        r = self.boto3_client.list_buckets()
        logger.debug(f"list_buckets => {r['Buckets']}")
        return r["Buckets"]

    def create_bucket(self, bucket_name):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] create_bucket: {bucket_name}")
        return self.boto3_client.create_bucket(Bucket=bucket_name)

    def delete_bucket(self, bucket_name):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] delete_bucket: {bucket_name}")
        return self.boto3_client.delete_bucket(Bucket=bucket_name)

    def list_objects(self, bucket):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] list_objects: {bucket}")
        r = self.boto3_client.list_objects(Bucket=bucket)
        return r["Contents"]

    def upload_fileobj(self, f, bucket, key):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] upload_fileobj: {bucket} {key}")
        return self.boto3_client.upload_fileobj(f, bucket, key)

    def download_fileobj(self, f, bucket, key):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] download_fileobj: {bucket} {key}")
        return self.boto3_client.download_fileobj(bucket, key, f)

    def delete_object(self, bucket_name, key):
        traceid = random_str(12)
        threading.currentThread().name = traceid
        r = self.set_traceid(traceid)
        logger.debug(f"[{traceid}] delete_object: {bucket_name} {key}")
        return self.boto3_client.delete_object(Bucket=bucket_name, Key=key)

    def set_traceid(self, traceid):
        if self.traceid:
            self.traceid = traceid
            return
        self.traceid = traceid
        def _add_header(request, **kwargs):
            request.headers.add_header("x-traceid", self.traceid)
            # print(request.headers)
        event_system = self.boto3_client.meta.events
        event_system.register_first("before-sign.*.*", _add_header)


class Credential():
    def __init__(self, credentials, reverse_proxy_addr, webui_domainname):
        if credentials:
            self.credentials = os.path.expanduser(credentials)
        else:
            self.credentials = None
        self.cached_value = None
        self.reverse_proxy_addr = reverse_proxy_addr
        self.webui_domainname = webui_domainname

    def read_credentials(self, user, password, policy_name):
        def read_access_key_from_api(user, password, policy_name):
            lc = LentClient(username=user, password=password,
                            reverse_proxy_addr=self.reverse_proxy_addr,
                            webui_domainname=self.webui_domainname)
            (user, access_key_id, secret_access_key) = accesskey_of_a_zone(lc, policy_name=policy_name)
            return (access_key_id, secret_access_key)
            # sys.stderr.write(f"AAA {(access_key_id, secret_access_key)}\n")

        if policy_name != "readwrite":
            read_access_key_from_api(user, password, policy_name)

        if self.cached_value:
            #print("cache hit")
            return self.cached_value
        #print("cache miss")

        if self.credentials is None:
            self.cached_value = read_access_key_from_api(user, password, policy_name)
            return self.cached_value

        config = configparser.ConfigParser()
        try:
            with open(self.credentials, "r") as f:
                config.read_file(f)
        except Exception as e:
            raise Exception(f"{self.credentials}: {e}")

        profile = user
        access_key_id = config[profile]["aws_access_key_id"]
        secret_access_key = config[profile]["aws_secret_access_key"]

        sys.stderr.write(f"BBB {(access_key_id, secret_access_key)}\n")
        self.cached_value = (access_key_id, secret_access_key)
        return self.cached_value

#def main():
#    pass
#
#
#if __name__ == "__main__":
#    main()
