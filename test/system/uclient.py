# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from lenticularis.utility import logger, openlog
from urllib.request import Request, urlopen
#from urllib.error import HTTPError, URLError
import ssl


class Uclient(object):

    def __init__(self, base_url):
        self.base_url = base_url
        ssl._create_default_https_context = ssl._create_unverified_context

    def get(self, traceid, path, noerror=False):
        logger.debug(f"get: {path} {noerror}")
        url = f"{self.base_url}{path}"
        logger.debug(f"url = {url}")
        headers = {}
        headers["X-TRACEID"] = traceid
        req = Request(url, headers=headers)
        try:
            logger.debug(f"@@@ [{traceid}] urlopen")
            res = urlopen(req, timeout=300)
            logger.debug(f"@@@ [{traceid}] Status: {res.status}")
            return res.read()
        except Exception as e:
            if noerror:
                return None
            logger.error(f"(EE) exception = {e}")
            raise


#def main():
#    base_url = "https://www.soum.co.jp/"
#    uc = Uclient(base_url)
#    body = uc.get("", noerror=True)
#    print(f"body = {type(body)}")
#
#
#if __name__ == "__main__":
#    main()
