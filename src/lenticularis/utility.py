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
import traceback
import contextvars


logger = logging.getLogger(__name__)
tracing = contextvars.ContextVar("tracing")

ERROR_EXCEPTION = 120
ERROR_START_MINIO = 123
ERROR_READCONF = 124
ERROR_FORK = 125
ERROR_ARGUMENT = 126

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


class MicrosecondFilter(logging.Filter):
    def filter(self, record):
        ##record.microsecond = format_rfc3339_z(time.time())
        setattr(record, "microsecond", format_rfc3339_z(time.time()))
        return True


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

    if priority in {
            "EMERG", "ALERT", "CRIT", "ERR", "WARNING",
            "NOTICE", "INFO", "DEBUG"}:
        pr = eval(f"logging.{priority}")
    else:
        pr = logging.INFO

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

    handler.addFilter(HostnameFilter())
    handler.addFilter(MicrosecondFilter())
    handler.setFormatter(logging.Formatter(format))
    logger.addHandler(handler)
    logger.setLevel(pr)

    if priority == logging.DEBUG:
        logger.debug("*** openlog: priority=DEBUG ***")


class Read1Reader():
    amt = 8192  # same size with HTTPResponse.read()
    total = 0
    count = 0
    sniff_offset = 0
    sniff_rest = 512

    def __init__(self, stream, thunk=None,
                 sniff=False, sniff_marker="-", use_read=False):
        #self.response = response

        self.stream = stream
        self.use_read = use_read
        self.thunk = thunk
        self.start = time.time()
        self.sniff = sniff
        self.sniff_marker = sniff_marker
        #AHO
        logger.debug("READ1READER START")

    def __iter__(self):
        return self

    def __next__(self):
        try:
            if self.use_read:
                b = self.stream.read(self.amt)
            else:
                b = self.stream.read1(self.amt)
        except Exception as e:
            #AHO
            logger.debug("READ1READER EXCEPTION")
            logger.exception(e)
            b = b""
        if len(b) == 0:
            self.end = time.time()
            duration = self.end - self.start
            #AHO
            logger.debug(f"READ1READER END total: {self.total} count: {self.count} duration: {duration:.3f}")
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
            bflag = ""
            if any(True for e in bb if chr(e) not in string.printable):
                bflag = "<binary data> "
            logger.debug(f"SNIFF: {self.sniff_marker} {self.sniff_offset} {bflag}{bb}")
            self.sniff_offset += bl
        return b


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


def gen_access_key_id():
    return random_str(ACCESS_KEY_ID_LEN)


def gen_secret_access_key():
    return random_str(SECRET_ACCESS_KEY_LEN)


def forge_s3_auth(access_key):
    """Makes an S3 authorization for an access-key."""
    return f"AWS4-HMAC-SHA256 Credential={access_key}////"


def parse_s3_auth(authorization):
    """Extracts an access-key in an S3 authorization."""
    if authorization is None:
        return None
    components = authorization.split(" ")
    if "AWS4-HMAC-SHA256" not in components:
        return None
    for c in components:
        if c.startswith("Credential="):
            e = c.find("/")
            if e != -1:
                return c[len("Credential="):e]
            else:
                return None
        else:
            pass
        pass
    return None


def access_mux(traceid, ep, access_key, facade_hostname, timeout):
    # It dose not set "X-REAL-IP"; Mux uses a peer-address if
    # X-REAL-IP is missing.
    proto = "http"
    url = f"{proto}://{ep}/"
    headers = {}
    headers["HOST"] = facade_hostname
    authorization = forge_s3_auth(access_key)
    headers["AUTHORIZATION"] = authorization
    headers["X-FORWARDED-PROTO"] = proto
    if traceid is not None:
        headers["X-TRACEID"] = traceid
    else:
        pass
    # headers["X-REAL-IP"] = (unset)
    req = Request(url, headers=headers)
    logger.debug(f"urlopen with url={url}, timeout={timeout},"
                 f" headers={headers}")
    try:
        with urlopen(req, timeout=timeout) as response:
            pass
        status = response.status
        assert isinstance(status, int)
    except urllib.error.HTTPError as e:
        b = e.read()
        logger.debug(f"Exception from urlopen to Mux url=({url}):"
                     f" exception=({e}) body=({b})")
        status = e.code
        assert isinstance(status, int)
    except urllib.error.URLError as e:
        logger.debug(f"Exception from urlopen to Mux url=({url}):"
                     f" exception=({e})")
        status = 400
    except Exception as e:
        logger.debug(f"Exception from urlopen to Mux url=({url}):"
                     f" exception=({e})")
        logger.debug(traceback.format_exc())
        status = 400
        pass
    logger.debug(f"urlopen for access_mux: status={status}")
    return status


def check_permission(user, allow_deny_rules):
    if user is None:
        return "denied"
    logger.debug(f"@@@ allow_deny_rules = {allow_deny_rules}")
    for rule in allow_deny_rules:
        action = rule[0]
        subject = rule[1]
        logger.debug(f"@@@ action = {action}")
        logger.debug(f"@@@ subject = {subject}")
        if subject == "*" or subject == user:
            logger.debug(f"@@@ HIT! {action}")
            return "allowed" if action == "allow" else "denied"
    logger.debug("@@@ EOR! allow")
    return "allowed"


def make_clean_env(oenv):
    """
    create_env_for_minio()
    create new environment and
    pick up required environment variables from `oenv`
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


##def _outer_join(left, lkey, right, rkey, fn):
##    left = sorted(left, key=lkey)
##    right = sorted(right, key=rkey)
##
##    def compar_nonetype(a, b):
##        if a is None and b is None:
##            return 0
##        if a is None:
##            return 1
##        if b is None:
##            return -1
##
##    def compar(a, b):
##        if a is None or b is None:
##            return compar_nonetype(a, b)
##
##        ak = lkey(a)
##        bk = rkey(b)
##
##        if ak < bk:
##            return -1
##        if bk < ak:
##            return 1
##        return 0
##
##    def car(lst):
##        if lst == []:
##            return None
##        return lst[0]
##
##    while left != [] or right != []:
##        le = car(left)
##        ri = car(right)
##
##        e = compar(le, ri)
##        if e < 0:
##            fn(le, None)
##            left.pop(0)
##        elif e > 0:
##            fn(None, ri)
##            right.pop(0)
##        else:
##            fn(le, ri)
##            left.pop(0)
##            right.pop(0)


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
    lx.extend(ll)
    rx.extend(rr)
    return (lx, px, rx)


def remove_trailing_shash(s):
    if not s.endswith("/"):
        return s
    return s[:-1]


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
    """
    RFC 3339
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
    return r


def uniform_distribution_jitter():
    ## NOTE: FIX VALUE.
    return random.random() * 2


def get_ip_address(host):
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
            ai = "  " if array_element else ""
    elif isinstance(obj, list):
        if array_element:
            raise Exception("not implemented")
        for v in obj:
            r += dump_object(v, lv=lv, array_element=True, order=order)
    else:
        if array_element:
            r.append(f"{lv}- {obj}\n")
        else:
            r.append(f"{lv}{obj}\n")
    return r


def host_port(host, port):
    """Quotes an ipv6 address."""
    if ":" in host:
        return f"[{host}]:{port}"
    else:
        return f"{host}:{port}"


def _safe_json_loads(s, parse_int=None, default=None):
    if s is None:
        return default
    return json.loads(s, parse_int=None)


def uniq_d(lis):
    seen = set()
    dups = []
    for item in lis:
        if item in seen:
            dups.append(item)
        seen.add(item)
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
    if ip.startswith("::ffff:"):
        return ip[7:]
    else:
        return ip


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
            errs += e0
        if p.stdout in readable:
            o0 = p.stdout.read1()
            if (o0 == b""):
                ss = [s for s in ss if s != p.stdout]
                closed = True
            outs += o0
    return (outs, errs, closed)
