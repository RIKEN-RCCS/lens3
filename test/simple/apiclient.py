"""Http Client -- A base class of Lens3Client."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import platform
import base64
import json
import ssl
import urllib
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def _basic_auth_token(user, password):
    basic = f"{user}:{password}"
    s = base64.b64encode(basic.encode()).decode()
    return f"Basic {s}"


def _read_cred_file(file):
    """Reads a file containing a credential and returns a tuple.
    """
    with open(file) as f:
        d = json.loads(f.read())
        pass
    (k, v) = next(iter(d.items()))
    return (k, v)


class Api_Client():

    def __init__(self, client_json):
        """Creates a Client, with a client setting file.  It contains a
        credential pair.  The key part is "mod_auth_openidc_session"
        for OIDC in Apache, "x-remote-user" for bypassing
        authentication (in case directly connecting to Lens3-Mux), or
        else a user name for basic-authentication.  For bypassing
        authentication, the endpoint should be a localhost.
        """
        self.running_host = platform.node()
        with open(client_json) as f:
            ci = json.loads(f.read())
            pass
        self.api_ep = ci["api_ep"]
        self.s3_ep = ci["s3_ep"]
        cred = ci.get("cred")
        assert cred is not None
        (k, v) = next(iter(cred.items()))
        if k not in {"mod_auth_openidc_session", "x-remote-user"}:
            token = _basic_auth_token(k, v)
            self.headers = {"AUTHORIZATION": token}
        elif k == "mod_auth_openidc_session":
            cookies = {k: v}
            self.headers = {"Cookie": urllib.parse.urlencode(cookies)}
        elif k == "x-remote-user":
            self.headers = {"X-REMOTE-USER": v}
        else:
            assert False
            pass
        pass

    def access(self, method, path, data):
        headers = dict()
        headers.update(self.headers)
        #headers["HOST"] = "localhost"
        #headers["X-REAL-IP"] = self.running_host
        #headers["X-Forwarded-For"] = self.running_host
        #headers["REMOTE-ADDR"] = self.running_host
        url = f"{self.api_ep}{path}"
        req = Request(url, headers=headers, method=method, data=data)
        # print(f"headers={headers}")
        # print(f"url={url}; request={req}")
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        try:
            res = urlopen(req, context=context, timeout=300)
            s = res.read().decode()
            v = json.loads(s)
            assert v["status"] == "success"
            # print(f"value={v}")
            return v
        except HTTPError as e:
            print(f"error={e}")
            s = e.read()
            #v = json.loads(s)
            print(f"urlopen failed with: ({s})")
            raise
        pass


def _main():
    client = Api_Client("client.json")
    #ep = "http://localhost:8003/api~"
    #ep = "http://localhost:8003"
    path = "/user-info"
    client.access("GET", path, data=None)
    pass


# >>> exec(open("apiclient.py").read())


if __name__ == "__main__":
    _main()
