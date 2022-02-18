# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import datetime
import time
import yaml


def rconf(configfile):
    try:
        with open(configfile, "r") as f:
            conf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"cannot read {configfile} {e}")
    except Exception as e:
        raise Exception(f"cannot read {configfile} {e}")

    return conf


def wakeup_at(year, month, day, hour, minute, second, microsecond, verbose=False):
    now = datetime.datetime.today()

    year = year if year is not None else now.year
    month = month if month is not None else now.month
    day = day if day is not None else now.day
    hour = hour if hour is not None else now.hour
    minute = minute if minute is not None else now.minute
    second = second if second is not None else now.second
    microsecond = microsecond if microsecond is not None else now.microsecond

    wakeup_at = datetime.datetime(year, month, day, hour, minute, second, microsecond)
    d = (wakeup_at - now).total_seconds()
    if verbose:
        print(f"wakeup_at: {wakeup_at}, now: {now}, sleep: {d}", flush=True)
    if d > 0:
        time.sleep(d)
    now = datetime.datetime.today()
    if verbose:
        print(f"now {now}", flush=True)
