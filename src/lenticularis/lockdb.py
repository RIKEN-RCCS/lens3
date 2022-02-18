# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from lenticularis.utility import logger
import time


class LockDB():

    def __init__(self, table):
        self.r = table.dbase.r
        self.key = None
        self.tinfo = dict()

    def trylock(self, key, timeout):
        logger.debug(f"@@@ TRY LOCK: [{key}] {timeout}")

        if not self.r.setnx(key, "1"):
            logger.debug(f"@@@ LOCK FAILED: [{key}]")
            v = self.r.get(key);
            logger.debug(f"@@@ LOCK FAILED: already set: {v}")
            return False
        logger.debug(f"@@@ LOCKED: [{key}]")
        self.lock_start = time.time()
        self.r.expire(key, timeout)
        self.key = key
        logger.debug(f"@@@ EXPIRE: {timeout}")
        return True

    def lock(self, key, timeout):
        delay = 0.2  # NOTE: FIXED VALUE
        while not self.trylock(key, timeout):
            self.wait4_unlock(key, delay)

    def unlock(self):
        if self.key is None:
            return
        try:
            key = self.key
            self.key = None
            self.r.delete(key)
        finally:
            duration = time.time() - self.lock_start if self.lock_start else 0
            logger.debug(f"@@@ UNLOCK: {self.key} DURATION: {duration}")
            self.key = None  # if interrupted, abondon lock.

    def wait4_unlock(self, key, delay):
        logger.debug(f"@@@ WAIT4: [{key}]")
        while self.r.exists(key):
            time.sleep(delay)
        logger.debug(f"@@@ UNLOCKED: [{key}]")
