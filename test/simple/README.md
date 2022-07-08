# Simple Tests

## Prerequisite

* boto3

## Brief Descriptions

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
bucket policies and access-key policies.  It tests using small files
(64KB).

It also reads a file "testu.yaml".
