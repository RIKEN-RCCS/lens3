"""Lens3-Registrar Client."""

# Copyright 2022-2024 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

# For cookies, See https://datatracker.ietf.org/doc/html/rfc2965.html

import platform
import string
import random
import contextvars
import json
import base64
import socket
import ssl
import urllib
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# tracing = contextvars.ContextVar("tracing")


def random_string(n):
    astr = string.ascii_letters
    bstr = string.ascii_letters + string.digits
    a = random.SystemRandom().choice(astr)
    b = (random.SystemRandom().choice(bstr) for _ in range(n - 1))
    return (a + "".join(b)).lower()


class Lens3_Error(Exception):
    def __init__(self, *args):
        super().__init__(*args)
        pass

    pass


def _basic_auth_token(user, password):
    basic = f"{user}:{password}"
    s = base64.b64encode(basic.encode()).decode()
    return f"Basic {s}"


def _cookie_join(d):
    """Returns a string by concatenating the entries as "key=value;" in a
    dictionary.
    """
    return ";".join([urllib.parse.urlencode({k1: v1})
                     for (k1, v1) in d.items()])


def _cookie_split(ss):
    """Returns a dictionary by taking the first "key=value;" string in a
    cookie entry.
    """
    ee = ss.split(";")
    if len(ee) >= 1:
        kv = urllib.parse.unquote(ee[0]).split("=", 1)
        if len(kv) == 2:
            return {kv[0]: kv[1]}
        else:
            return dict()
    else:
        return dict()
    pass


_verbose = False

def _verbose_print(*args):
    if _verbose:
        print(*args)
        pass
    pass


class Reg_Client():
    """Http-client.  It represents an access endpoint."""

    def __init__(self, client_json):
        """Creates a Client with a client setting file.  A credential is
        required in the setting, and it should be given by a pair.
        The key part of a pair determines the authentication method.
        There are three methods: Apache OIDC, basic authentication,
        and no-authentication.  For Apache OIDC, the key is
        "mod_auth_openidc_session" and a value is a cookie value.  For
        basic authentication, a key is user name and a value is a
        password.  For no-authentication, the key is "x-remote-user"
        and a value is a user name.  No-authentication means directly
        connecting to Lens3-Mux.  The endpoint must be a localhost for
        using no-authentication.
        """

        self.running_host = platform.node()
        with open(client_json) as f:
            ci = json.loads(f.read())
            pass
        self.conf = ci
        self.urlopen_error_message = b""
        self.s3_ep = self.conf["s3_ep"]
        self.reg_ep = self.conf["reg_ep"]
        self.ssl_verify = self.conf.get("ssl_verify", True)
        self.cred_cookie = ""
        self.csrf_token = ""
        self.csrf_cookie = ""
        auth = self.conf.get("auth")
        assert auth is not None
        cred = self.conf.get("cred")
        assert cred is not None
        # (k1, v1) = next(iter(cred.items()))
        # if k1 not in {"mod_auth_openidc_session", "x-remote-user"}:
        #     self.cred_cookie = ""
        #     token = _basic_auth_token(k1, v1)
        #     self.headers = {"AUTHORIZATION": token}
        # elif k1 == "mod_auth_openidc_session":
        #     self.cred_cookie = v1
        #     self.headers = {}
        # elif k1 == "x-remote-user":
        #     self.cred_cookie = ""
        #     self.headers = {"X-REMOTE-USER": v1}
        # else:
        #     assert False
        #     pass
        if auth == "oidc":
            #"mod_auth_openidc_session"
            v1 = cred[0]
            self.cred_cookie = v1
            self.headers = {}
        elif auth == "basic":
            (k1, v1) = tuple(cred)
            self.cred_cookie = ""
            token = _basic_auth_token(k1, v1)
            self.headers = {"AUTHORIZATION": token}
        elif auth == "x-remote-user":
            v1 = cred[0]
            self.cred_cookie = ""
            self.headers = {"X-REMOTE-USER": v1}
        else:
            assert False
            pass
        pass

    def do_access(self, method, path, data):
        """Calls urlopen() with specified arguments."""
        headers = dict()
        headers.update(self.headers)
        if data is not None:
            headers["Content-Type"] = "application/json"
            pass
        if not len(self.csrf_token) == 0:
            headers["X-CSRF-Token"] = self.csrf_token
            pass
        cookies1 = dict()
        if not len(self.cred_cookie) == 0:
            cookies1["mod_auth_openidc_session"] = self.cred_cookie
            pass
        if not len(self.csrf_cookie) == 0:
            cookies1["fastapi-csrf-token"] = self.csrf_cookie
            pass
        if not len(cookies1) == 0:
            headers["Cookie"] = ("$Version=1;"
                                 + _cookie_join(cookies1))
            pass
        #headers["HOST"] = "localhost"
        #headers["X-REAL-IP"] = self.running_host
        #headers["X-Forwarded-For"] = self.running_host
        #headers["REMOTE-ADDR"] = self.running_host
        url = f"{self.reg_ep}{path}"
        req = Request(url, headers=headers, method=method, data=data)
        _verbose_print(f"request.headers={req.header_items()}")
        _verbose_print(f"url={url}; request={req}")
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        try:
            _verbose_print(f"urlopen(url={url})...")
            res = urlopen(req, context=context, timeout=90)
            s = res.read().decode()
            v = json.loads(s)
            assert v["status"] == "success"
            # _verbose_print(f"response.headers={res.getheaders()}")
            # _verbose_print(f"response={v}")
            cv = [hv for (hk, hv) in res.getheaders()
                  if hk.lower() == "set-cookie"]
            if len(cv) > 0:
                cookies2 = {k: v for cc in cv
                            for (k, v) in _cookie_split(cc).items()}
                cookie = cookies2.get("fastapi-csrf-token", "")
                if not len(cookie) == 0:
                    self.csrf_cookie = cookie
                    # _verbose_print(f"csrf_cookie={cookie}")
                    pass
                pass
            tv = v.get("x_csrf_token", None)
            if tv is not None:
                self.csrf_token = tv
                # _verbose_print(f"csrf_token={self.csrf_token}")
                pass
            return v
        except HTTPError as ex:
            print(f"error={ex}")
            s = ex.read()
            #v = json.loads(s)
            self.urlopen_error_message = s
            _verbose_print(f"urlopen failed with: ({s})")
            raise
        pass


class Lens3_Client(Reg_Client):
    """Lens3-Registrar client.  It defines Registrar operations."""

    bkt_policy_set = {"none", "public", "upload", "download"}
    key_policy_set = {"readwrite", "readonly", "writeonly"}

    def __init__(self, client_json):
        super().__init__(client_json)
        with open(client_json) as f:
            ci = json.loads(f.read())
            pass
        # _verbose_print(f"client_setting={ci}")
        self.api_version = "v1.2"
        self._verbose = False
        self.gid = ci.get("gid")
        self.home = ci.get("home")
        pass

    # Lens3-Registrar Oprations.

    def get_user_info(self):
        path = "/user-info"
        self.csrf_token = ""
        reply = self.do_access("GET", path, data=None)
        self.csrf_token = reply.get("x_csrf_token")
        assert self.csrf_token is not None
        info = reply["user_info"]
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
        }
        path = f"/pool"
        data = json.dumps(body).encode()
        reply = self.do_access("POST", path, data=data)
        desc = reply["pool_desc"]
        assert desc is not None
        return desc

    def get_pool(self, pool):
        path = f"/pool/{pool}"
        reply = self.do_access("GET", path, data=None)
        desc = reply["pool_list"][0]
        return desc

    def list_pools(self):
        path = f"/pool"
        reply = self.do_access("GET", path, data=None)
        pools = reply["pool_list"]
        return pools

    def delete_pool(self, pool):
        assert self.csrf_token is not None
        path = f"/pool/{pool}"
        #body = dict()
        #data = json.dumps(body).encode()
        reply = self.do_access("DELETE", path, data=None)
        return None

    def make_bucket(self, pool, bucket, policy):
        assert policy in self.bkt_policy_set
        path = f"/pool/{pool}/bucket"
        body = {
            "name": bucket,
            "bkt_policy": policy,
        }
        data = json.dumps(body).encode()
        reply = self.do_access("PUT", path, data=data)
        desc = reply["pool_desc"]
        return desc

    def delete_bucket(self, pool, bucket):
        assert self.csrf_token is not None
        path = f"/pool/{pool}/bucket/{bucket}"
        #body = dict()
        #data = json.dumps(body).encode()
        reply = self.do_access("DELETE", path, data=None)
        desc = reply["pool_desc"]
        return desc

    def make_secret(self, pool, policy, expiration):
        assert policy in self.key_policy_set
        path = f"/pool/{pool}/secret"
        body = {
            "key_policy": policy,
            "expiration_time": expiration,
        }
        data = json.dumps(body).encode()
        reply = self.do_access("POST", path, data=data)
        desc = reply["pool_desc"]
        return desc

    def delete_secret(self, pool, key):
        path = f"/pool/{pool}/secret/{key}"
        #body = dict()
        #data = json.dumps(body).encode()
        reply = self.do_access("DELETE", path, data=None)
        desc = reply["pool_desc"]
        return desc

    # Auxiliary Functions.

    def find_pool(self, directory):
        pools = self.list_pools()
        pooldesc = next((pooldesc for pooldesc in pools
                         if pooldesc["buckets_directory"] == directory),
                        None)
        return pooldesc

    def get_aws_credential(self, pooldesc, policy, section_title):
        assert policy in self.key_policy_set
        keys = pooldesc["secrets"]
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
    # client = Reg_Client("client.json")
    # path = "/user-info"
    # client.do_access("GET", path, data=None)
    client = Lens3_Client("client.json")
    v = client.get_user_info()
    print(f"client.get_user_info={v}")
    pass


# >>> exec(open("lens3_client.py").read())


if __name__ == "__main__":
    _main()
