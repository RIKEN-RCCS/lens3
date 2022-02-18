# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from api_manipulation import accesskey_of_a_zone
from api_manipulation import direct_hostname_of_a_zone
from botocore.exceptions import ClientError
import filecmp
import io
from lenticularis.utility import logger
from lenticularis.utility import random_str
import os
import tempfile
import time
from uclient import Uclient
import threading


def test_create_bucket(system_test):
    logger.debug(f"@@@ test_create_bucket")
    s3c = system_test.s3_client()
    bucket = random_s3_name(12)
    got = s3c.create_bucket(bucket)
    assert got is not None
    buckets = set([e.get("Name") for e in s3c.list_buckets()])
    expected = {bucket}
    assert expected.issubset(buckets)
    system_test.rsleep()
    s3c.delete_bucket(bucket)
    system_test.rsleep()

    buckets = set([e.get("Name") for e in s3c.list_buckets()])
    assert expected.intersection(buckets) == set()

    del s3c


def test_list_objects(system_test):
    logger.debug(f"@@@ test_list_objects")
    s3c = system_test.s3_client()
    bucket = random_s3_name(12)
    try:
        got = s3c.list_objects(bucket)
    except ClientError as e:
        got = None
    assert got is None

    s3c.create_bucket(bucket)
    keys = []

    (key, fs) = upload_fileobj_iobuf(s3c, bucket, None, ".txt", 32)
    keys.append(key)

    (key, fs) = upload_fileobj_iobuf(s3c, bucket, None, ".exe", 128)
    keys.append(key)

    (key, fs) = upload_fileobj_iobuf(s3c, bucket, None, "", 64)
    keys.append(key)

    system_test.rsleep()
    objects = set([e.get("Key") for e in s3c.list_objects(bucket)])
    expected = set(keys)
    assert expected.issubset(objects)
    logger.debug(f"OK {keys}")

    logger.debug(f"@@@ test_list_objects: objects =  {objects}")
    logger.debug(f"@@@ test_list_objects: expected = {expected}")

    try:
        s3c.delete_bucket(bucket)
    except Exception as e:
        logger.debug(f"expected failure: OK")

    system_test.rsleep()
    for key in keys:
        s3c.delete_object(bucket, key)
    s3c.delete_bucket(bucket)

    del s3c


def test_object_xfr_spray(system_test):
    thunk = {"bs": 512 * 1024, "count": 1,     # 512 kB
             "loop": 32,                       # 32 times
             "system_test": system_test}
    system_test.rsleep()
    duration = with_two_tmpfiles(object_xfr_body, thunk)
    report_throughput(duration, thunk)
    logger.debug(f"object_xfr_spray OK")


def test_object_xfr(system_test):
    thunk = {"bs": 1024 * 1024, "count": 256,  # 256 MiB
             "loop": 2,                        # 2 times
             "system_test": system_test}
    system_test.rsleep()
    duration = with_two_tmpfiles(object_xfr_body, thunk)
    report_throughput(duration, thunk)
    logger.debug(f"object_xfr OK")


def object_xfr_body(tmpdir, path1, path2, thunk):
    duration = 0
    system_test = thunk["system_test"]
    s3c = system_test.s3_client()
    bucket = random_s3_name(12)
    try:
        got = s3c.list_objects(bucket)
    except ClientError as e:
        got = None
    assert got is None

    s3c.create_bucket(bucket)
    system_test.rsleep()

    loop = thunk["loop"]
    bs = thunk["bs"]
    count = thunk["count"]

    keys = []

    for i in range(loop):
        fill_file(path1, bs, count)
        system_test.rnap()
        with open(path1, "rb") as f:
            start = time.time()
            key = upload_fileobj_fileobj(s3c, bucket, None, ".txt", f)
            end = time.time()
            duration += end - start

        system_test.rnap()
        with open(path2, "wb") as g:
            start = time.time()
            s3c.download_fileobj(g, bucket, key)
            end = time.time()
            duration += end - start

        keys.append(key)

        got = filecmp.cmp(path1, path2, shallow=False)
        assert got == True

        logger.debug(f"OK")

    try:
        s3c.delete_bucket(bucket)
    except Exception as e:
        logger.debug(f"expected failure: OK")

    system_test.rsleep()
    for key in keys:
        s3c.delete_object(bucket, key)
    s3c.delete_bucket(bucket)

    del s3c
    return duration


def test_public_access(system_test):

    public_bucket = system_test.u["public_bucket"]
    logger.debug(f"public_bucket = {public_bucket}")

    key = random_str(12).lower()
    # logger.debug(f"key = {key}")
    s3c = system_test.s3_client()
    (key, fs) = upload_fileobj_iobuf(s3c, public_bucket, key, ".txt", 8192)
    # logger.debug(f"key = {key}")

    lc = system_test.lent_client()
    access_key = accesskey_of_a_zone(lc)
    # logger.debug(f"access_key = {access_key}")
    (_, direct_hostname) = direct_hostname_of_a_zone(lc)
    # logger.debug(f"direct_hostname = {direct_hostname}")

    traceid = random_str(12)
    threading.currentThread().name = traceid
    base_url = f"https://{direct_hostname}/"
    logger.debug(f"[{traceid}] base_url = {base_url}")
    uc = Uclient(base_url)
    path = f"{public_bucket}/{key}"
    # logger.debug(f"path = {path}")
    body = uc.get(traceid, path, noerror=False)
    # logger.debug(f"body = {body}")
    if body != fs:
        logger.debug(f"compare FAILED")
        raise Exception("file conent mismatch")
    else:
        logger.debug(f"compare OK")

    traceid = random_str(12)
    threading.currentThread().name = traceid
    base_url = f"https://{direct_hostname}/"
    logger.debug(f"[{traceid}] base_url = {base_url}")
    uc = Uclient(base_url)
    path = f"{public_bucket}/{key}"
    # logger.debug(f"path = {path}")
    body = uc.get(traceid, path, noerror=False)
    # logger.debug(f"body = {body}")
    if body != fs:
        logger.debug(f"compare FAILED")
        raise Exception("file content mismatch")
    else:
        logger.debug(f"compare OK")


def test_keytype(system_test):
    s3c = system_test.s3_client()
    s3c_readonly = system_test.s3_client(policy_name="readonly")
    s3c_writeonly = system_test.s3_client(policy_name="writeonly")
    bucket = random_s3_name(12)
    s3c.create_bucket(bucket)
    key = random_str(12).lower()

    ## upload with readonly key
    try:
        (key, fs) = upload_fileobj_iobuf(s3c_readonly, bucket, key, ".txt", 32)
    except Exception as e:
        pass

    ## upload with writeonly key
    (key, fs) = upload_fileobj_iobuf(s3c_writeonly, bucket, key, ".txt", 32)

    ## download with writeonly key
    try:
        with io.BytesIO() as g:
            s3c_writeonly.download_fileobj(g, bucket, key)
        logger.debug("writeonly key: fail")
        raise Exception("writeonly user can download files")
    except Exception as e:
        logger.debug("writeonly key: ok")

    ## download with readonly key
    with io.BytesIO() as g:
        s3c_readonly.download_fileobj(g, bucket, key)
        if g.getvalue() != fs:
            logger.debug("readonly key: fail")
            raise Exception("readonly user can upload files")
        else:
            logger.debug("readonly key: ok")

    ## download with readwrite key
    with io.BytesIO() as g:
        s3c.download_fileobj(g, bucket, key)
        if g.getvalue() != fs:
            logger.debug("readwrite key: fail")
            raise Exception("file content mismatch")
        else:
            logger.debug("readwrite key: ok")


##########################################################
##### Utility                                        #####
##########################################################


def upload_fileobj_fileobj(s3c, bucket, key, ext, f):
    if not key:
        # key = f"{random_s3_name(12)}{ext}"
        key = f"{random_str(12)}{ext}"
    # logger.debug(f"key = {key}")
    s3c.upload_fileobj(f, bucket, key)
    return key


def upload_fileobj_iobuf(s3c, bucket, key, ext, size):
    if not key:
        # key = f"{random_s3_name(12)}{ext}"
        key = f"{random_str(12)}{ext}"
    #logger.debug(f"key = {key}")
    # logger.debug(f"@@@ size = {size}")
    fs = open("/dev/urandom","rb").read(size)
    f = io.BytesIO(fs)
    s3c.upload_fileobj(f, bucket, key)
    return (key, fs)


def fill_file(path, bs, count):
    # logger.debug(f"@@@ size = {bs * count}")
    with open(path, "wb") as f:
       for m in range(count):
           f.write(os.urandom(bs))


def with_two_tmpfiles(fn, thunk):
    with tempfile.TemporaryDirectory() as tmpdirname:
        logger.debug(f"tmpdirname = {tmpdirname}")
        with tempfile.NamedTemporaryFile(dir = tmpdirname) as file1:
            with tempfile.NamedTemporaryFile(dir = tmpdirname) as file2:
                return fn(tmpdirname, file1.name, file2.name, thunk)


def random_s3_name(n):
    return random_str(n).lower()


def report_throughput(duration, thunk):
    size_mb = thunk["bs"] * thunk["count"] / (1024 * 1024)
    number = thunk["loop"] * 2  # round trip
    print(f"Transferred {number} files "
          f"(each {size_mb:.3f} MiB, total {number * size_mb :.3f} MiB) "
          f"in {duration:.3f} secs, "
          f"{number * size_mb / duration:.3f} MiB / sec", flush=True)


class RandomFile():
    def __init__(self, size, random=True):
        self.rest = size
        # sz * cn => 8 MiB
        sz = 1024
        cn = 8 * 1024
        if random:
            self.buf = os.urandom(sz) * cn
        else:
            self.buf = b' ' * sz * cn
        self.bufsize = len(self.buf)
        self.sent = 0
        self.recv = 0

    def read(self, size=-1):
        if self.rest <= 0:
            return b''

        if size == -1:
            size = self.rest

        size = min(size, self.bufsize)

        if size == self.bufsize:
            self.rest -= size
            self.sent += size
            return self.buf
        else:
            self.rest -= size
            self.sent += size
            return self.buf[:size]

    def write(self, buf):
        self.recv += len(buf)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass


def test_performance(system_test):
    s3c = system_test.s3_client()

    size = 2 * 1024 * 1024 * 1024

    bucket = random_s3_name(12)
    s3c.create_bucket(bucket)
    if system_test.wakeup_at:
        system_test.wakeup_at()

    with RandomFile(size) as f:
        start = time.time()
        key = upload_fileobj_fileobj(s3c, bucket, None, ".txt", f)
        end = time.time()
        sent = f.sent
    duration = end - start
    sent_mb = sent / (1024 * 1024)

    print(f"Uploaded "
          f"{sent_mb:.3f} MiB "
          f"in {duration:.3f} secs, "
          f"{sent_mb / duration:.3f} MiB / sec", flush=True)

    if system_test.second_wakeup_at:
        system_test.second_wakeup_at()

    with RandomFile(0) as g:
        start = time.time()
        s3c.download_fileobj(g, bucket, key)
        end = time.time()
        recv = g.recv
    duration = end - start
    recv_mb = recv / (1024 * 1024)

    print(f"Downloaded "
          f"{recv_mb:.3f} MiB "
          f"in {duration:.3f} secs, "
          f"{recv_mb / duration:.3f} MiB / sec", flush=True)

    s3c.delete_object(bucket, key)
    s3c.delete_bucket(bucket)

    del s3c
