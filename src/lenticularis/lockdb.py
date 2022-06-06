"""Redis table locker (not a lock, a lock is named by a key)."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import time
from lenticularis.utility import logger


class LockDB():

    def __init__(self, table, locker_name):
        self._r = table.dbase.r
        self.key = None
        self.lock_start = 0
        self._locker_name = locker_name
        self._tinfo = dict()
        pass

    def trylock(self, key, timeout):
        """Takes a lock and returns true."""
        ts = int(time.time() * 1000)
        kn = f"{self._locker_name}{ts}"
        if self._r.setnx(key, kn) == 0:
            _ = self._r.get(key)
            return False
        self.key = key
        self.lock_start = ts
        self._r.expire(key, timeout)
        return True

    def lock(self, key, timeout):
        ## NOTE: FIX VALUE.
        delay = 0.2
        while not self.trylock(key, timeout):
            self.wait_for_lock(key, delay)
            pass
        pass

    def unlock(self):
        assert self.key is not None
        kn = f"{self._locker_name}{self.lock_start}"
        v = self._r.get(self.key)
        if v != kn:
            logger.error(f"UNLOCKING OTHERS: locker={kn} holder={v}")
            pass
        self._r.delete(self.key)
        self.key = None
        pass

    def wait_for_lock(self, key, delay):
        while self._r.exists(key):
            time.sleep(delay)
            pass
        pass

    pass
