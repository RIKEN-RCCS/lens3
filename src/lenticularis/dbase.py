"""Redis DB wrapper."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
import json
from redis import ConnectionError
from redis import Redis
from lenticularis.utility import logger


def _wait_for_redis(r):
    while True:
        try:
            r.ping()
            logger.debug("Connected to Redis.")
            return
        except ConnectionError as e:
            logger.debug("Connection to Redis failed (sleeping).")
            time.sleep(30)
            pass
        pass
    pass


class DBase():
    def __init__(self, host, port, db, password):
        self.r = Redis(host=host, port=port, db=db, password=password,
                             charset="utf-8", decode_responses=True)
        _wait_for_redis(self.r)
        pass

    def set(self, name, value):
        self.r.set(name, value)
        pass

    def get(self, name, default=None):
        val = self.r.get(name)
        return val if val is not None else default

    def hexists(self, name, key):
        return self.r.hexists(name, key)

    def hset_map(self, name, dict, structured):
        # hset returns the number of added fields, but ignored.
        dict = _marshal(dict, structured)
        self.r.hset(name, mapping=dict)
        pass

    def hget_map(self, name, structured, default=None):
        val = self.r.hgetall(name)
        if val is None:
            return default
        else:
            return _unmarshal(val, structured)
        pass

    def hset(self, name, key, val, structured):
        # hset returns the number of added fields, but ignored.
        if key in structured:
            val = json.dumps(val)
            pass
        self.r.hset(name, key, val)
        pass

    def hget(self, name, key, structured, default=None):
        val = self.r.hget(name, key)
        if val is None:
            return default
        elif key in structured:
            return json.loads(val, parse_int=None)
        else:
            return val
        pass

    def delete(self, name):
        self.r.delete(name)
        pass

    pass


def _marshal(dict, keys):
    if keys is None:
        return dict
    else:
        dict = dict.copy()
        for key in keys:
            val = dict.get(key)
            if val is not None:
                dict[key] = json.dumps(val)
        return dict
    pass


def _unmarshal(dict, keys):
    ### It destructively modifies a dict.
    if keys is None:
        return dict
    else:
        for key in keys:
            val = dict.get(key)
            if val is not None:
                dict[key] = json.loads(val, parse_int=None)
        return dict
    pass
