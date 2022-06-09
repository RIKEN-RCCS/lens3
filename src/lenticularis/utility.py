"""Small functions."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import codecs
import hashlib
import json
import platform
import random
import string
import time
import socket
import select
from urllib.request import Request, urlopen
import urllib.error
import logging
import logging.handlers
import contextvars


logger = logging.getLogger(__name__)
tracing = contextvars.ContextVar("tracing")

ERROR_EXIT_EXCEPTION = 120
ERROR_EXIT_START_MINIO = 123
ERROR_EXIT_READCONF = 124
ERROR_EXIT_FORK = 125
ERROR_EXIT_ARGUMENT = 126

ACCESS_KEY_ID_LEN = 20
SECRET_ACCESS_KEY_LEN = 48


class HostnameFilter(logging.Filter):
    def __init__(self):
        self.hostname = platform.node()
        super().__init__()

    def filter(self, record):
        ##record.hostname = self.hostname
        setattr(record, "hostname", self.hostname)
        return True

    pass


class MicrosecondFilter(logging.Filter):
    def filter(self, record):
        ##record.microsecond = format_rfc3339_z(time.time())
        setattr(record, "microsecond", format_rfc3339_z(time.time()))
        return True

    pass


def openlog(file, facility, priority):
    assert (facility is not None) and (priority is not None)
    address = "/dev/log"

    if file is not None:
        handler = logging.FileHandler(file)
    elif facility in {
            "KERN", "USER", "MAIL", "DAEMON", "AUTH", "LPR",
            "NEWS", "UUCP", "CRON", "SYSLOG",
            "LOCAL0", "LOCAL1", "LOCAL2", "LOCAL3", "LOCAL4",
            "LOCAL5", "LOCAL6", "LOCAL7", "AUTHPRIV"}:
        fa = eval(f"logging.handlers.SysLogHandler.LOG_{facility}")
        handler = logging.handlers.SysLogHandler(address=address, facility=fa)
    else:
        fa = logging.handlers.SysLogHandler.LOG_LOCAL7
        handler = logging.handlers.SysLogHandler(address=address, facility=fa)
        pass

    if priority in {
            "EMERG", "ALERT", "CRIT", "ERR", "WARNING",
            "NOTICE", "INFO", "DEBUG"}:
        pr = eval(f"logging.{priority}")
    else:
        pr = logging.INFO
        pass

    if file is not None:
        format = ("%(asctime)s %(levelname)s: "
                  "%(filename)s:%(lineno)s:%(funcName)s: %(message)s")
    else:
        if pr == logging.DEBUG:
            format = ("lenticularis: %(levelname)s:[%(hostname)s:%(threadName)s.%(thread)d]:"
                      "%(filename)s:%(lineno)s:%(funcName)s: %(message)s")
        else:
            format = ("lenticularis: %(levelname)s: "
                      "%(filename)s:%(lineno)s:%(funcName)s: %(message)s")
            pass
        pass

    handler.addFilter(HostnameFilter())
    handler.addFilter(MicrosecondFilter())
    handler.setFormatter(logging.Formatter(format))
    logger.addHandler(handler)
    logger.setLevel(pr)

    if priority == logging.DEBUG:
        logger.debug("*** openlog: priority=DEBUG ***")
        pass
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
            logger.error(f"Reading network failed: exception=({e})",
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


ROT13_PREFIX = "$13$"


def encrypt_secret(s):
    if s.startswith(ROT13_PREFIX):
        return s
    return f"{ROT13_PREFIX}{rot13(s)}"


def decrypt_secret(s):
    if not s.startswith(ROT13_PREFIX):
        return s
    return rot13(s[len(ROT13_PREFIX):])


def rot13(s):
    return codecs.encode(s, "rot_13")


def sha1(s):
    return hashlib.sha1(s).hexdigest()


def random_str(n):
    astr = string.ascii_letters
    bstr = string.ascii_letters + string.digits
    a = random.SystemRandom().choice(astr)
    b = (random.SystemRandom().choice(bstr) for _ in range(n - 1))
    return a + "".join(b)


def generate_access_key():
    return random_str(ACCESS_KEY_ID_LEN)


def generate_secret_key():
    return random_str(SECRET_ACCESS_KEY_LEN)


def copy_minimal_env(oenv):
    """Copies minimal environ to run services.
    """
    keys = {
        "HOME",
        "LANG",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SHELL",
        "USER",
        "USERNAME",
    }
    return {key: val for key, val in oenv.items() if key in keys}


def list_diff3(left, lkeyfn, right, rkeyfn):
    """Takes an intersection and residues, and returns a three-tuple of
    left-residues, intersection-pairs, and right-residues.  It does
    not expect duplicate keys, but such keys are consumed one by one.
    """

    def _comp(l0, r0):
        lk = lkeyfn(l0)
        rk = rkeyfn(r0)
        if lk < rk:
            return -1
        elif rk < lk:
            return 1
        else:
            return 0
        pass

    ll = sorted(left, key=lkeyfn)
    rr = sorted(right, key=rkeyfn)
    lx = []
    px = []
    rx = []
    while ll != [] and rr != []:
        l0 = ll[0]
        r0 = rr[0]
        e = _comp(l0, r0)
        if e < 0:
            lx.append(l0)
            ll.pop(0)
        elif e > 0:
            rx.append(r0)
            rr.pop(0)
        else:
            px.append((l0, r0))
            ll.pop(0)
            rr.pop(0)
            pass
        pass
    lx.extend(ll)
    rx.extend(rr)
    return (lx, px, rx)


def remove_trailing_slash(s):
    if s.endswith("/"):
        return s[:-1]
    else:
        return s
    pass


#def format_8601_us(t=None):
#    """
#    ISO 8601
#    """
#    if t is None:
#        t = time.time()
#    i = time.strftime("%Y%m%dT%H%M%S", time.gmtime(t))
#    f = (int)((t % 1) * 1000000)
#    return f"{i}.{f:06d}Z"


def format_rfc3339_z(t):
    """RFC 3339
    """
    i = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))
    f = (int)((t % 1) * 1000000)
    return f"{i}.{f:06d}Z"


def pick_one(m):
    if m == []:
        return None
    ms = m.copy()
    random.shuffle(ms)
    return ms[0]


def dict_diff(e, z):
    e_keys = set(e.keys())
    z_keys = set(z.keys())
    r = [{"reason": "key deleted", "existing": only_in_e}
          for only_in_e in e_keys - z_keys]
    r += [{"reason": "key appeared", "new": only_in_z}
          for only_in_z in z_keys - e_keys]
    for common_key in e_keys.intersection(z_keys):
        ei = e[common_key]
        zi = z[common_key]
        if ei != zi:
            r.append({"reason": "value changed", "key": common_key, "existing": ei, "new": zi})
            pass
        pass
    return r


def uniform_distribution_jitter():
    ## NOTE: FIX VALUE.
    return random.random() * 2


def get_ip_addresses(host):
    return [make_typical_ip_address(addr[0])
            for (_, _, _, _, addr) in socket.getaddrinfo(host, None)]


def objdump(obj, order=None):
    return "".join(dump_object(obj, order=order))


def dump_object(obj, lv="", array_element=False, order=None):
    r = []
    if isinstance(obj, dict):
        keys = sorted(list(obj.keys()), key=order)
        ai = "- " if array_element else ""
        for k in keys:
            v = obj[k]
            if isinstance(v, str) or isinstance(v, int):
                r += [f"{lv}{ai}{k}: "] + dump_object(v, order=order)
            elif not array_element and isinstance(v, list):
                r += [f"{lv}{ai}{k}:\n"] + dump_object(v, lv=lv, order=order)
            else:
                r += [f"{lv}{ai}{k}:\n"] + dump_object(v, lv=lv+" "*4, order=order)
                pass
            ai = "  " if array_element else ""
            pass
        pass
    elif isinstance(obj, list):
        if array_element:
            raise Exception("not implemented")
        for v in obj:
            r += dump_object(v, lv=lv, array_element=True, order=order)
            pass
        pass
    else:
        if array_element:
            r.append(f"{lv}- {obj}\n")
        else:
            r.append(f"{lv}{obj}\n")
            pass
        pass
    return r


def host_port(host, port):
    """Quotes an ipv6 address."""
    if ":" in host:
        return f"[{host}]:{port}"
    else:
        return f"{host}:{port}"
    pass


def uniq_d(lis):
    seen = set()
    dups = []
    for item in lis:
        if item in seen:
            dups.append(item)
            pass
        seen.add(item)
        pass
    return dups


def log_access(status_, client_, user_, method_, url_, *,
                  upstream=None, downstream=None):
    access_time = format_rfc3339_z(time.time())
    user_ = user_ if user_ else "-"
    upstream = upstream if upstream else "-"
    downstream = downstream if downstream else "-"
    logger.info(f"{access_time} {status_} {client_} {user_} {method_} {url_} {upstream} {downstream}")
    return


def make_typical_ip_address(ip):
    """Makes IP address strings comparable.  It drops the hex part (not
    RFC-5952).
    """
    if ip.startswith("::ffff:"):
        return ip[7:]
    else:
        return ip
    pass


def wait_one_line_on_stdout(p, timeout):
    """Waits until a line is on stdout.  A returned line can be more than
    one.  Note that a closure is undetectable on pipes created by
    Popen (until a subprocess exits).  It drains stdout/stderr and
    returns (outs, errs).
    """
    (outs, errs, closed) = (b"", b"", False)
    ss = [p.stdout, p.stderr]
    while ss != [] and not b"\n" in outs and not closed:
        (readable, _, _) = select.select(ss, [], [], timeout)
        if readable == []:
            break
        if p.stderr in readable:
            e0 = p.stderr.read1()
            if (e0 == b""):
                ss = [s for s in ss if s != p.stderr]
                pass
            errs += e0
            pass
        if p.stdout in readable:
            o0 = p.stdout.read1()
            if (o0 == b""):
                ss = [s for s in ss if s != p.stdout]
                closed = True
                pass
            outs += o0
            pass
        pass
    return (outs, errs, closed)


def _check_direct_hostname_flat(host_label):
    if "." in host_label:
        raise Exception(f"invalid direct hostname: {host_label}: only one level label is allowed")
    _check_rfc1035_label(host_label)
    _check_rfc1122_hostname(host_label)
    pass


def _check_rfc1035_label(label):
    if len(label) > 63:
        raise Exception(f"{label}: too long")
    if len(label) < 1:
        raise Exception(f"{label}: too short")
    pass


def _check_rfc1122_hostname(label):
    alnum = string.ascii_lowercase + string.digits
    if not all(c in alnum + "-" for c in label):
        raise Exception(f"{label}: contains invalid char(s)")
    if not label[0] in alnum:
        raise Exception(f"{label}: must start with a letter or a digit")
    if not label[-1] in alnum:
        raise Exception(f"{label}: must end with a letter or a digit")
    pass


def _is_subdomain(host_fqdn, domain):
    return host_fqdn.endswith("." + domain)


def _strip_domain(host_fqdn, domain):
    domain_len = 1 + len(domain)
    return host_fqdn[:-domain_len]
