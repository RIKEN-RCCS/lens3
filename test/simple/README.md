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
exists.  Copy "copy-file-conf-example.sh" as "copy-file-conf.sh" and
edit it.  It may include variables "SIZ" for the file size, and "DBG"
for the options to AWS CLI.

Running "copy-file.sh" leaves garbage files in the current directory.

Note that it does not test the commands __presign__ and __website__.
__presign__ is useless because Lens3 does not understand a secret in
URL.  __website__ will fail in Lens3.

## Basic Tests

"test_api.py" and "test_access.py" run tests on basic functions.
"test_api.py" tests Lens3-Api.  "test_access.py" tests Lens3-Mux for
bucket accesses.  Tests require Python3.9 and later.  Run
"test_access.py" after testing with "test_api.py", because
"test_access.py" uses Lens3-Api operations.

### Client Setting

These tests read a configuration file "client.json".  It includes the
endpoints for S3 and Lens3-Api.  Copy "client-example.json" as
"client.json" and edit it.

The entries of "client.json" are:
* __api_ep__: A Lens3 API endpoint like "https://lens3.example.com/lens3.sts".
* __s3_ep__: An S3 endpoint like "https://lens3.example.com".
* __gid__: A unix group of a user.
* __home__: A directory of a pool (anywhere writable).
* __cred__: A credential key-value pair.
* __ssl_verify__: A flag to use https.
* __pools_count__: Number of MinIO instances.
* __minio_awake_duration__: Wait time, use the value in Lens3 configuration.

__pools_count__ and __minio_awake_duration__ are used in the test
"busy_server_prepare.py"

"client.json" has a credential to access Lens3-Api.  __cred__
specifies a credential by a key-value pair and it has three choices:
{"mod_auth_openidc_session": cookie-value} for Apache OIDC
authentication, {"x-remote-user": user-id} for bypassing
authentication, or {user-id: password} for a basic-authentication,
otherwise.

The secret for Apache OIDC authentication is stored in a
"mod_auth_openidc_session" cookie.  The cookie is recorded in a
web-brower after authentication.  Web-browser's js-console can be used
to obtain the cookie value.  To use bypassing authentication, the test
needs to access Lens3-Api directly from the host that runs Lens3
services (thus, skipping the proxy).

### test_api.py

[test_api.py](test_api.py) runs Lens3-Api operations.  It makes a
pool, then makes buckets and access-keys.  It tries to make a
conflicting bucket which will fail.  Finally, it cleans up.  It leaves
directories with random names ("00xxxxxx") in the directory specified
as "home".

### test_access.py

[test_access.py](test_access.py) runs S3 access test.  It uses "boto3"
library.  It tests various combinations of key policies and bucket
policies, along with key's expiration states.

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

Set "pools_count" and "minio_awake_duration" slots appropriately in
the "client.json" file.  "pools_count" should be something that
exceeds the number of server instances simultaneously run -- exceeding
by 3 to 5 will be enough.  The limit is specified by the value of the
port range in the Lens3 configuration ("mux-conf.yaml").
"minio_awake_duration" should be the same value in the Lens3
configuration ("mux-conf.yaml").  The "minio_awake_duration" is the
lifetime of a server instance after it becomes idle.

Running "busy_server_prepare.py" will take a long time (hours),
because it will wait for some server instances expire its lifetime.

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

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
* [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
