"""Small functions."""

# Copyright (c) 2022-2023 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import codecs
import hashlib
import platform
import random
import string
import time
import math
import sys
import socket
import select
import traceback
from urllib.request import Request, urlopen
import urllib.error
import logging
import logging.handlers
import contextvars


logger = logging.getLogger(__name__)
tracing = contextvars.ContextVar("tracing")

ERROR_EXIT_EXCEPTION = 120
ERROR_EXIT_START_MINIO = 123
ERROR_EXIT_BADCONF = 124
ERROR_EXIT_FORK = 125
ERROR_EXIT_ARGUMENT = 126

_ACCESS_KEY_LEN = 20
_SECRET_KEY_LEN = 48


class _Hostname_Filter(logging.Filter):
    def __init__(self):
        self._hostname = platform.node()
        super().__init__()
        pass

    def filter(self, record):
        setattr(record, "hostname", self._hostname)
        return True

    pass


class _Microsecond_Filter(logging.Filter):
    def filter(self, record):
        setattr(record, "microsecond", format_time_z(time.time()))
        return True

    pass


def openlog(file, facility, priority):
    assert (facility is not None) and (priority is not None)
    so = "/dev/log"

    if file is not None:
        # FileHandler, WatchedFileHandler, TimedRotatingFileHandler
        # handler = logging.handlers.TimedRotatingFileHandler(file, when="W0")
        handler = logging.FileHandler(file)
    elif facility in {
            "KERN", "USER", "MAIL", "DAEMON", "AUTH", "LPR",
            "NEWS", "UUCP", "CRON", "SYSLOG", "AUTHPRIV", "FTP",
            "LOCAL0", "LOCAL1", "LOCAL2", "LOCAL3", "LOCAL4",
            "LOCAL5", "LOCAL6", "LOCAL7"}:
        fa = eval(f"logging.handlers.SysLogHandler.LOG_{facility}")
        handler = logging.handlers.SysLogHandler(address=so, facility=fa)
    else:
        fa = logging.handlers.SysLogHandler.LOG_LOCAL7
        handler = logging.handlers.SysLogHandler(address=so, facility=fa)
        pass

    if priority in {
            "EMERG", "ALERT", "CRIT", "ERR", "WARNING",
            "NOTICE", "INFO", "DEBUG"}:
        pr = eval(f"logging.{priority}")
    else:
        pr = logging.INFO
        pass

    if file is not None:
        fmt = ("%(asctime)s %(levelname)s:"
               " %(filename)s:%(lineno)s:%(funcName)s: %(message)s")
    else:
        fmt = ("lenticularis: %(levelname)s:"
               " %(filename)s:%(lineno)s:%(funcName)s: %(message)s")
        pass

    handler.addFilter(_Hostname_Filter())
    handler.addFilter(_Microsecond_Filter())
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
    logger.setLevel(pr)

    pass


class Read1Reader():
    # Note 8192 is the same size with HTTPResponse.read().
    amt = 8192
    total = 0
    count = 0
    sniff_offset = 0
    sniff_rest = 512

    def __init__(self, stream, thunk=None,
                 sniff=False, sniff_marker="-", use_read=False):
        # self.response = response
        self.stream = stream
        self.use_read = use_read
        self.thunk = thunk
        self.start = time.time()
        self.sniff = sniff
        self.sniff_marker = sniff_marker
        pass

    def __iter__(self):
        return self

    def __next__(self):
        try:
            if self.use_read:
                b = self.stream.read(self.amt)
            else:
                b = self.stream.read1(self.amt)
        except Exception as e:
            m = rephrase_exception_message(e)
            logger.error(f"Reading network failed: exception=({m})",
                         exc_info=True)
            b = b""
            pass
        if len(b) == 0:
            self.end = time.time()
            duration = self.end - self.start
            # logger.debug(f"READ1READER END total: {self.total} count: {self.count} duration: {duration:.3f}")
            raise StopIteration
        self.total += len(b)
        self.count += 1
        if self.sniff and self.sniff_rest > 0:
            bl = len(b)
            if bl <= self.sniff_rest:
                bb = b
                self.sniff_rest -= bl
            else:
                bl = self.sniff_rest
                bb = b[:bl]
                self.sniff_rest = 0
                pass
            bflag = ""
            if any(True for e in bb if chr(e) not in string.printable):
                bflag = "<binary data> "
                pass
            logger.debug(f"SNIFF: {self.sniff_marker} {self.sniff_offset} {bflag}{bb}")
            self.sniff_offset += bl
            pass
        return b

    pass


def random_str(n):
    astr = string.ascii_letters
    bstr = string.ascii_letters + string.digits
    a = random.SystemRandom().choice(astr)
    b = (random.SystemRandom().choice(bstr) for _ in range(n - 1))
    return a + "".join(b)


def generate_access_key():
    return random_str(_ACCESS_KEY_LEN)


def generate_secret_key():
    return random_str(_SECRET_KEY_LEN)


def copy_minimal_environ(oenv):
    """Copies minimal environment variables to run services.  It includes
    Lens3 specific variables.
    """
    keys = {
        "HOME",
        "LANG",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SHELL",
        "USER",
        #"USERNAME",
        "LENS3_CONF",
        "LENS3_MUX_NAME",
    }
    return {key: val for key, val in oenv.items() if key in keys}


def remove_trailing_slash(s):
    if s.endswith("/"):
        return s[:-1]
    else:
        return s
    pass


def format_time_z(t):
    """Returns a time string by RFC3339/ISO8601 in milliseconds."""
    f, i = math.modf(t)
    s = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(i))
    m = (int)(f * 1000)
    return f"{s}.{m:03d}Z"


def pick_one(m):
    if m == []:
        return None
    ms = m.copy()
    random.shuffle(ms)
    return ms[0]


def uniform_distribution_jitter():
    # NOTE: FIX VALUE.
    return random.random() * 2


def get_ip_addresses(host):
    """Returns a list of addresses for the host name, which are formatted
    to be compared for equality.
    """
    return [make_typical_ip_address(addr[0])
            for (_, _, _, _, addr) in socket.getaddrinfo(host, None)]


def host_port(host, port):
    """Returns a host + port concatenation.  It quotes an ipv6 address."""
    if ":" in host:
        return f"[{host}]:{port}"
    else:
        return f"{host}:{port}"
    pass


def log_access(status_, client_, user_, method_, url_, *,
               upstream=None, downstream=None):
    access_time = format_time_z(time.time())
    user_ = user_ if user_ else "-"
    upstream = upstream if upstream else "-"
    downstream = downstream if downstream else "-"
    logger.info(f"{access_time} {status_} {client_} {user_} {method_} {url_} {upstream} {downstream}")
    pass


def make_typical_ip_address(ip):
    """Makes IP address strings comparable.  It drops the hex part (not
    RFC-5952).
    """
    if ip.startswith("::ffff:"):
        return ip[7:]
    else:
        return ip
    pass


def wait_line_on_stdout(p, outs, errs, limit):
    """Waits until at-least one line is on stdout.  It collects
    stdout/stderr in (outs, errs) as a pair of byte-strings.  It can
    return more than one line.  It returns a 4-tuple
    (outs,err,closed,timeout).  Note that a closure is undetectable on
    a pipe created by Popen until a subprocess exits.
    """
    (closed, timeout) = (False, False)
    ss = [p.stdout, p.stderr]
    while len(ss) > 0:
        if limit is None:
            to = None
        else:
            to = limit - int(time.time())
            if to <= 0:
                timeout = True
                break
            pass
        (readable, _, _) = select.select(ss, [], [], to)
        if readable == []:
            timeout = True
            break
        if p.stderr in readable:
            e1 = p.stderr.read1()
            if (e1 == b""):
                ss = [s for s in ss if s != p.stderr]
                pass
            errs += e1
            pass
        if p.stdout in readable:
            o1 = p.stdout.read1()
            if (o1 == b""):
                ss = [s for s in ss if s != p.stdout]
                closed = True
                break
            outs += o1
            if b"\n" in o1:
                break
            pass
        pass
    return (outs, errs, closed, timeout)


def rephrase_exception_message(e):
    """Returns an error message of an AssertionError.  It is needed
    because simply printing an AssertionError returns an empty string.
    """
    if not isinstance(e, AssertionError):
        return f"{e}"
    else:
        (_, _, tb) = sys.exc_info()
        tr = traceback.extract_tb(tb)
        (filename, line, func, text) = tr[-1]
        return f"AssertionError: {text}; File {filename}, Line {line}"
    pass
