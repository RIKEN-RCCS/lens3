"""Lens3-Api Client."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import json
import contextvars
from apiclient import Api_Client


tracing = contextvars.ContextVar("tracing")


def _trunc100(x):
    return (int(x/100)*100)


class Lens3_Error(Exception):
    def __init__(self, *args):
        super().__init__(*args)
        pass

    pass


class Lens3_Client(Api_Client):
    """Lens3-Api client.  It represents an access endpoint."""

    bkt_policy_set = {"none", "public", "upload", "download"}
    key_policy_set = {"readwrite", "readonly", "writeonly"}

    def __init__(self, client_json):
        super().__init__(client_json)
        with open(client_json) as f:
            ci = json.loads(f.read())
            pass
        # print(f"client_setting={ci}")
        self.api_version = "v1.2"
        self._verbose = False
        self.gid = ci.get("gid")
        self.home = ci.get("home")
        pass

    # Lens3-Api Primitives.

    def get_user_info(self):
        path = "/user-info"
        v = self.access("GET", path, data=None)
        self.csrf_token = v.get("CSRF-Token")
        assert self.csrf_token is not None
        info = v.get("user_info")
        api_version = info.get("api_version")
        # sys.stdout.write(f"api_version=({api_version})\n")
        assert api_version == self.api_version
        # sys.stdout.write(f"csrf_token=({self.csrf_token})\n")
        return info

    def make_pool(self, directory):
        assert self.csrf_token is not None
        body = {
            "buckets_directory": directory,
            "owner_gid": self.gid,
            "CSRF-Token": self.csrf_token,
        }
        path = f"/pool"
        data = json.dumps(body).encode()
        desc = self.access("POST", path, data=data)
        pooldesc = desc["pool_desc"]
        assert pooldesc is not None
        return pooldesc

    def get_pool(self, pool):
        path = f"/pool/{pool}"
        desc = self.access("GET", path, data=None)
        return desc["pool_list"][0]

    def list_pools(self):
        path = f"/pool"
        desc = self.access("GET", path, data=None)
        pools = desc["pool_list"]
        return pools

    def delete_pool(self, pool):
        assert self.csrf_token is not None
        path = f"/pool/{pool}"
        body = {"CSRF-Token": self.csrf_token}
        data = json.dumps(body).encode()
        return self.access("DELETE", path, data=data)

    def make_bucket(self, pool, bucket, bkt_policy):
        assert bkt_policy in self.bkt_policy_set
        path = f"/pool/{pool}/bucket"
        body = {
            "name": bucket,
            "bkt_policy": bkt_policy,
            "CSRF-Token": self.csrf_token,
        }
        data = json.dumps(body).encode()
        return self.access("PUT", path, data=data)

    def delete_bucket(self, pool, bucket):
        assert self.csrf_token is not None
        path = f"/pool/{pool}/bucket/{bucket}"
        body = {"CSRF-Token": self.csrf_token}
        data = json.dumps(body).encode()
        return self.access("DELETE", path, data=data)

    def make_secret(self, pool, key_policy, expiration):
        assert key_policy in self.key_policy_set
        path = f"/pool/{pool}/secret"
        body = {
            "key_policy": key_policy,
            "expiration_time": expiration,
            "CSRF-Token": self.csrf_token,
        }
        data = json.dumps(body).encode()
        return self.access("POST", path, data=data)

    def delete_secret(self, pool, key):
        path = f"/pool/{pool}/secret/{key}"
        body = {"CSRF-Token": self.csrf_token}
        data = json.dumps(body).encode()
        return self.access("DELETE", path, data=data)

    # Auxiliary.

    def find_pool(self, directory):
        pools = self.list_pools()
        pooldesc = next((pooldesc for pooldesc in pools
                         if pooldesc["buckets_directory"] == directory),
                        None)
        return pooldesc

    def get_aws_credential(self, pooldesc, policy, section_title):
        assert policy in self.key_policy_set
        keys = pooldesc["access_keys"]
        # {"use", "owner", "access_key", "secret_key", "key_policy"}
        pair = next(((k["access_key"], k["secret_key"]) for k in keys
                     if k["key_policy"] == policy),
                    None)
        if pair is None:
            raise Lens3_Error(f"No access-key for a policy {policy}")
        else:
            print(f"[{section_title}]\n"
                  f"aws_access_key_id = {pair[0]}\n"
                  f"aws_secret_access_key = {pair[1]}\n", end="")
            pass
        pass

    pass


def _main():
    client = Lens3_Client("client.json")
    path = "/user-info"
    v = client.get_user_info()
    print(f"client.get_user_info={v}")
    pass


# >>> exec(open("lens3client.py").read())


if __name__ == "__main__":
    _main()
