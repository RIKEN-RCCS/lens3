"""Redis DB wrapper."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
import json
from redis import ConnectionError
from redis import Redis
from lenticularis.utility import logger
from lenticularis.utility import safe_json_loads

class DBase():
    def __init__(self, host, port, db, password):

        def wait_for_redis():
            while True:
                try:
                    self.r.ping()
                    logger.debug("@@@ Redis is Ready")
                    return
                except ConnectionError as e:
                    logger.debug("@@@ Redis is not Ready.")
                    time.sleep(1)

        self.r = Redis(host=host, port=port, db=db, password=password,
                             charset="utf-8", decode_responses=True)

        logger.debug(f"@@@ Redis = {self.r}")
        wait_for_redis()

    def set(self, name, value):
        self.r.set(name, value)

    def get(self, name, default=None):
        val = self.r.get(name)
        return val if val is not None else default

    def hexists(self, name, key):
        return self.r.hexists(name, key)

    def hset_map(self, name, mapping, structured):
        if structured:
            mapping = marshal(mapping.copy(), structured)
        self.r.hset(name, mapping=mapping)

    def hset(self, name, key, val, structured):
        if key in structured:
            val = json.dumps(val)
        self.r.hset(name, key, val)

    def hget(self, name, key, structured, default=None):
        val = self.r.hget(name, key)
        if val and key in structured:
            val = safe_json_loads(val, parse_int=str)
        return val if val is not None else default

    def hget_map(self, name, structured, default=None):
        val = self.r.hgetall(name)
        if structured:
            return unmarshal(val, structured)
        return val if val is not None else default

    def delete(self, name):
        self.r.delete(name)

def marshal(dict, keys):
    for key in keys:
        val = dict.get(key)
        if val is not None:
            dict[key] = json.dumps(val)
    return dict

def unmarshal(dict, keys):
    for key in keys:
        val = dict.get(key)
        if val is not None:
            dict[key] = safe_json_loads(val, parse_int=str)
    return dict
