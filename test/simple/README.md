# Simple Tests

## Copy Test by AWS CLI

### copy-file.sh

[copy-file.sh](copy-file.sh) runs simple tests using AWS CLI.  It runs
commands: __cp__, __ls__, __mv__, __rm__.  It generates a file of 32MB
randoms, and uploads and downloads it.  The file is large enough to
start a multipart upload (8MB is the default threshold to use a
multipart upload).

First prepare the files for AWS CLI.  An S3 secret should be created
and set in ".aws/credentials".  The S3 signature version may be needed
in the configuration file ".aws/config" as:

```
[default]
s3 =
    signature_version = s3v4
```

The shell variables "EP" and "BKT" specify the target -- "EP" for an
endpoint and "BKT" for a bucket.  A bucket needs to be created in
advance.  It reads (sources by ".") a file "copy-file-conf.sh" if
exists.  First, copy "copy-file-conf-example.sh" as
"copy-file-conf.sh" and modify it.  It may include variables "SIZ" for
the file size, and "DBG" for the options to AWS CLI.

Running "copy-file.sh" leaves garbage files in the current directory.

Note that it does not test the commands __presign__ and __website__.
__presign__ is useless because Lens3 does not understand a secret in
URL.  __website__ will fail in Lens3.

## Basic Tests

The "test_api.py" and "test_access.py" run tests on basic functions.
"test_api.py" tests Lens3-Api.  "test_access.py" tests Lens3-Mux for
bucket accesses.

### Client Setting

These tests read a configuration file "client.json".  It includes the
endpoints for S3 and Lens3-Api.  Copy "client-example.json" to
"client.json" and edit it.

"client.json" also includes a credential to access Lens3-Api.  A
credential may be a cookie for Apache OIDC, a user+password pair for
basic-authentication, or a user name to bypass authentication.  To
bypass authentication, it needs to access Lens3-Api directly (i.e.,
skipping the proxy).  A credential for Apache OIDC can be found in a
"mod_auth_openidc_session" cookie.  Web browser's js-console may be
used to obtain the cookie value.

### test_api.py

[test_api.py](test_api.py) runs Lens3-Api operations.  It makes a
pool, then makes buckets and access-keys.  It tries to make a
conflicting bucket which will fail.  Finally, it cleans up.  It leaves
directories with random names ("00xxxxxx") in the user's home
directory.

### test_access.py

[test_access.py](test_access.py) runs S3 access test.  It uses "boto3"
library.  It tests various combinations of key policies and bucket
policies, and also tests with expired keys.  It uses Lens3-Api
operations, and thus it is better to run after "test_api.py".

## User Disable Test

### user_disable.py

[user_disable.py](user_disable.py) checks if a put fails after
disabling a user.  It directly modifies the Redis database to disable
a user.  Thus, it should be run on the host where the Lens3 service is
running.  It reads a "user_disable_conf.json".  Use
"user_disable_conf-example.json" as a template of
"user_disable_conf.json".  It is necessary to create a bucket and an
access-key in advance.  Keep "conf.json" secure, because it includes
the password of Redis.

## Busy Server Test

### busy_server_prepare.py

[busy_server_prepare.py](busy_server_prepare.py) prepares for the busy
server test.  It creates many pools exceeding the number of MinIO
instances that can run at the same time.  The number of instances is
controlled by the port range for connections.  Simultaneously
accessing many pools would suspend some of the pools, and the
operations on the pools are rejected.  Running
"busy_server_prepare.py" creates many pools, and the preparation work
itself behaves as the busy server test.

Set "clients" and "minio_awake_duration" slots appropriately in the
"client.json" file.  For "clients", the value should be something that
exceeds the numbers in the port range -- exceeding by 3 to 5 will be
enough.  For "minio_awake_duration", take the same value in the
"mux-conf.yaml" file.  The "minio_awake_duration" value is the
lifetime of a MinIO instance after it becomes idle.

Running "busy_server_prepare.py" will take a long time, because it
will wait for some MinIO instances expire its lifetime.

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
* [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
