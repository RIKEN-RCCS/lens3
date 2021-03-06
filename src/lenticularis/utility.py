# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

import codecs
import hashlib
import json
import logging
from logging import getLogger
from logging.handlers import SysLogHandler
import platform
import random
import string
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import socket


logger = getLogger(__name__)


ERROR_EXCEPTION = 120
ERROR_START_MINIO = 123
ERROR_READCONF = 124
ERROR_FORK = 125
ERROR_ARGUMENT = 126

ACCESS_KEY_ID_LEN = 20
SECRET_ACCESS_KEY_LEN = 48


class HostnameFilter(logging.Filter):
    hostname = platform.node()
    def filter(self, record):
        record.hostname = self.hostname
        return True


class MicrosecondFilter(logging.Filter):
    def filter(self, record):
        record.microsecond = format_rfc3339_z(time.time())
        return True


def openlog(facility=None, priority=None):
    address = "/dev/log"

    if facility in {
            "KERN", "USER", "MAIL", "DAEMON", "AUTH", "LPR",
            "NEWS", "UUCP", "CRON", "SYSLOG",
            "LOCAL0", "LOCAL1", "LOCAL2", "LOCAL3", "LOCAL4",
            "LOCAL5", "LOCAL6", "LOCAL7", "AUTHPRIV"}:
        facility = eval(f"SysLogHandler.LOG_{facility}")
    else:
        facility = SysLogHandler.LOG_LOCAL7

    if priority in {
            "EMERG", "ALERT", "CRIT", "ERR", "WARNING",
            "NOTICE", "INFO", "DEBUG"}:
        priority = eval(f"logging.{priority}")
    else:
        priority = logging.INFO

    if priority == logging.DEBUG:
        format = ("%(microsecond)s - %(levelname)s:[%(hostname)s:%(threadName)s.%(thread)d]:"
                  "%(filename)s:%(lineno)s:%(funcName)s: %(message)s")
    else:
        format = ("%(asctime)s - %(levelname)s:"
                  "%(filename)s:%(lineno)s:%(funcName)s: %(message)s")
    handler = SysLogHandler(address=address, facility=facility)
    handler.addFilter(HostnameFilter())
    handler.addFilter(MicrosecondFilter())
    handler.setFormatter(logging.Formatter(format))
    logger.addHandler(handler)
    logger.setLevel(priority)

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
            logger.debug("READ1READER EXCEPTION")
            logger.exception(e)
            b = b''
        if len(b) == 0:
            self.end = time.time()
            duration = self.end - self.start
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


def forge_s3_auth(access_key_id):
    return f"AWS4-HMAC-SHA256 Credential={access_key_id}////"


def parse_s3_auth(authorization):
    components = authorization.split(' ')
    if "AWS4-HMAC-SHA256" not in components:
        return None
    for e in components:
        if e.startswith("Credential="):
            end = e.find('/')
            if end == -1:
                return None
            return e[len("Credential="):end]
    return None


def send_decoy_packet(traceid, host, access_key_id, delegate_hostname, timeout):
    logger.debug(f"@@@ SEND DECOY PACKET")
    proto = "http"
    url = f"{proto}://{host}/"
    headers = {}
    headers["HOST"] = delegate_hostname
    authorization = forge_s3_auth(access_key_id)
    headers["AUTHORIZATION"] = authorization
    headers["X-TRACEID"] = traceid
    # headers["X-REAL-IP"] = (unset)   # if X-REAL-IP is missing, multiplexer will use peer_addr instead.
    headers["X-FORWARDED-PROTO"] = proto
    logger.debug(f"@@@ traceid = {traceid}")
    logger.debug(f"@@@ host = {host}")
    logger.debug(f"@@@ url = {url}")
    logger.debug(f"@@@ headers = {headers}")
    req = Request(url, headers=headers)
    logger.debug(f"@@@ request = {req}")
    try:
        logger.debug("@@@ (try)")
        res = urlopen(req, timeout=timeout)
    except HTTPError as e:
        logger.debug(f"@@@ EXCEPTTION: {e}")
        b = e.read()
        logger.debug(f"@@@ ERROR BODY: {b}")
        # logger.exception(e)  # do not record exception detail
        # OK. expected behaviour
        res = e
    status = f"{res.status}"
    logger.debug(f"@@@ status {status}")
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
        if subject == '*' or subject == user:
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


def outer_join(left, lkey, right, rkey, fn):
    left = sorted(left, key=lkey)
    right = sorted(right, key=rkey)

    def compar_nonetype(a, b):
        if a is None and b is None:
            return 0
        if a is None:
            return 1
        if b is None:
            return -1

    def compar(a, b):
        if a is None or b is None:
            return compar_nonetype(a, b)

        ak = lkey(a)
        bk = rkey(b)

        if ak < bk:
            return -1
        if bk < ak:
            return 1
        return 0

    def car(lst):
        if lst == []:
            return None
        return lst[0]

    while left != [] or right != []:
        le = car(left)
        ri = car(right)

        e = compar(le, ri)
        if e < 0:
            fn(le, None)
            left.pop(0)
        elif e > 0:
            fn(None, ri)
            right.pop(0)
        else:
            fn(le, ri)
            left.pop(0)
            right.pop(0)


def remove_trailing_shash(s):
    if not s.endswith('/'):
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


def get_mux_addr(v):
    lenticularis_param = v["lenticularis"]
    host = lenticularis_param["multiplexer"]["host"]
    port = lenticularis_param["multiplexer"]["port"]
    return (host, port)


def uniform_distribution_jitter():
    return random.random() * 2  # NOTE: FIXED VALUE


def get_ip_address(host):
    return [normalize_address(addr[0])
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
                r += [f"{lv}{ai}{k}:\n"] + dump_object(v, lv=lv+' '*4, order=order)
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


def hostport(host, port):
    if ':' in host:
        host = f"[{host}]"
    return f"{host}:{port}"


def safe_json_loads(s, parse_int=None, default=None):
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


def normalize_address(ip):
    if ip.startswith("::ffff:"):
        ip = ip[7:]
    return ip


def accesslog(status, client_addr, user, method, url,
              content_length_upstream=None,
              content_length_downstream=None):
    access_time = format_rfc3339_z(time.time())
    user = user if user else "-"
    content_length_upstream = content_length_upstream if content_length_upstream else "-"
    content_length_downstream = content_length_downstream if content_length_downstream else "-"
    logger.info(f"{access_time} {status} {client_addr} {user} {method} {url} {content_length_upstream} {content_length_downstream}")
