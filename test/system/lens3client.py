"""Lenticularis-S3 Api Client."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import sys
import base64
import json
import ssl
import time
import string
import random
import platform
import contextvars
from urllib.request import Request, urlopen
from urllib.error import HTTPError


tracing = contextvars.ContextVar("tracing")


def random_str(n):
    astr = string.ascii_letters
    bstr = string.ascii_letters + string.digits
    a = random.SystemRandom().choice(astr)
    b = (random.SystemRandom().choice(bstr) for _ in range(n - 1))
    return a + "".join(b)


class Client():
    def __init__(self, uid, gid, password, home, hostname, *, proto="https"):
        self._api_version = "v1.2"
        self.uid = uid
        self.gid = gid
        self.password = password
        self.home = home
        self.hostname = hostname
        self.running_host = platform.node()
        self.url = f"{proto}://{self.hostname}"
        self.csrf_token = None
        pass

    def _auth_token(self):
        basic_auth = f"{self.uid}:{self.password}"
        return base64.b64encode(basic_auth.encode()).decode()

    def access(self, method, path, *, data=None):
        headers = dict()
        headers["HOST"] = self.running_host
        headers["X-TRACEID"] = tracing.get()
        headers["REMOTE-ADDR"] = self.running_host
        if self.uid and self.password:
            s = self._auth_token()
            authorization = f"Basic {s}"
            headers["AUTHORIZATION"] = authorization
            pass

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        assert path.startswith("/")
        url = f"{self.url}{path}"
        req = Request(url, headers=headers, method=method, data=data)

        # sys.stdout.write(f"url={url}; request={req}\n")

        try:
            res = urlopen(req, timeout=300, context=context)
            s = res.read().decode()
            v = json.loads(s)
            assert v["status"] == "success"
            return v
        except HTTPError as e:
            s = e.read().decode()
            v = json.loads(s)
            sys.stderr.write(f"urlopen failed with: ({e}) ({v})\n")
            raise
        pass

    def get_user_template(self):
        path = "/template"
        template = self.access("GET", path)
        api_version = template["pool_list"][0]["api_version"]
        sys.stdout.write(f"api_version=({api_version})\n")
        assert api_version == self._api_version
        self.csrf_token = template.get("CSRF-Token")
        sys.stdout.write(f"csrf_token=({self.csrf_token})\n")
        return template

    def make_pool(self, directory):
        assert self.csrf_token is not None
        desc = {"buckets_directory": directory,
                "owner_gid": self.gid}
        body = {"CSRF-Token": self.csrf_token,
                "pool": desc}
        path = f"/pool"
        data = json.dumps(body).encode()
        return self.access("POST", path, data=data)

    def get_pool(self, pool):
        path = f"/pool/{pool}"
        desc = self.access("GET", path)
        return desc["pool_list"][0]

    def list_pools(self):
        path = f"/pool"
        desc = self.access("GET", path)
        pools = desc["pool_list"] 
        return pools

    def delete_pool(self, pool):
        assert self.csrf_token is not None
        path = f"/pool/{pool}"
        body = {"CSRF-Token": self.csrf_token}
        data = json.dumps(body).encode()
        return self.access("DELETE", path, data=data)

    def make_bucket(self, pool, bucket, bkt_policy):
        assert bkt_policy in {"none", "public", "upload", "download"}
        (_, self.csrf_token) = self.get_pool(pool)
        path = f"/pool/{pool}/bucket"
        body = {"CSRF-Token": self.csrf_token,
                "bucket": {"name": bucket, "bkt_policy": bkt_policy}}
        data = json.dumps(body).encode()
        return self.access("POST", path, data=data)

    def delete_bucket(self, pool, bucket):
        assert self.csrf_token is not None
        path = f"/pool/{pool}/bucket/{bucket}"
        body = {"CSRF-Token": self.csrf_token}
        data = json.dumps(body).encode()
        return self.access("DELETE", path, data=data)

    def make_secret(self, pool, key_policy):
        assert key_policy in {"readwrite", "readonly", "writeonly"}
        path = f"/pool/{pool}/secret"
        body = {"CSRF-Token": self.csrf_token,
                "key_policy": key_policy}
        data = json.dumps(body).encode()
        return self.access("POST", path, data=data)

    def delete_secret(self, pool, key):
        path = f"/pool/{pool}/secret/{key}"
        body = {"CSRF-Token": self.csrf_token}
        data = json.dumps(body).encode()
        return self.access("DELTE", path, data=data)

    pass
