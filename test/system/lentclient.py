# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import base64
import json
from lenticularis.utility import logger
import ssl
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class LentClient():
    def __init__(self, username=None, password=None,
                 reverse_proxy_addr=None, webui_domainname=None):
        self.username = username
        self.password = password
        self.reverse_proxy_addr = reverse_proxy_addr
        self.webui_domainname = webui_domainname
        self.base_url = f"https://{self.reverse_proxy_addr}"

    def request(self, traceid, path, data=None, method="GET"):

        def authtoken():
            basic_auth = f"{self.username}:{self.password}"
            return base64.b64encode(basic_auth.encode()).decode()

        def set_authorization():
            base64string = authtoken()
            authorization = f"Basic {base64string}"
            headers["AUTHORIZATION"] = authorization

        logger.debug(f"requst: {method} {path}")

        headers = {}
        headers["HOST"] = self.webui_domainname
        if self.username and self.password:
            set_authorization()
        headers["X-TRACEID"] = traceid

        logger.debug(f"headers: {headers}")

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        url = f"{self.base_url}{path}"
        logger.debug(f"url: {url}")

        req = Request(url, data=data, headers=headers, method=method)

        try:
            logger.debug(f"@@@ [{traceid}] urlopen")
            res = urlopen(req, timeout=300, context=context)
            logger.debug(f"@@@ [{traceid}] Status: {res.status}")
            r = res.read().decode()
            logger.debug(f"@@@ r: {r}")
            return json.loads(r)

        except HTTPError as e:
            logger.error(f"HTTPError: {e}")
            logger.exception(f"HTTPError: {e}")
            r = e.read().decode()
            logger.debug(f"HTTPError: {r}")
            # raise Exception(f"HTTPError: {e} {r}")
            raise
            #return json.loads(r)
