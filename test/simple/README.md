# Simple Tests

## copy-file.sh

[copy-file.sh](copy-file.sh) runs a very simple test using AWS S3 CLI.
It runs commands: __cp__, __ls__, __mv__, __rm__, __presign__,
__website__.  It generates a file of 32MB, and uploads and downloads
it.  That file is large enough to start a multipart upload (8MB is the
default threshold to use a multipart upload).

A secret of S3 should be prepared in ".aws/*".  A bucket needs to be
created in advance, too.  The shell variables "EP" and "BKT" are set
to the target, "EP" as an endpoint and "BKT" as a bucket.  Note it
leaves garbage files.  Run the tests in the "test/simple" directory,
because it needs sample files in the directory.

__presign__ is useless.  Lens3 denies a bucket access unless it is
public.

__website__ will fail in Lens3.

## Prerequisite

* boto3

## Other Tests -- Brief Descriptions

Run "apitest.py" first, and then run "s3test.py".

* (NOT YET) Tests include one sending a false csrf_token.

### apitest.py

It tests API operations: pool creation/deletion, access-key
creation/deletion, and bucket creation/deletion.

It reads a file "testu.yaml", whose contents are as following.  apiep
is an endpoint of Web-API, and s3ep is an access point of S3.
home+uid is used as a directory to create a pool.  The password is
used as a basic authentication key at the http reverse-proxy.

```
apiep: "lens3.example.com:8008"
s3ep: "lens3.example.com:8009"
proto: "http"
home: "/home"
uid: "user1"
gid: "group1"
password: "xxxxxx"
```

### s3test.py

It tests S3 operations: file upload/download for combinations of
bucket policies and access-key policies.  Test uses 64KB file.

It also reads a file "testu.yaml".

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
* [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
