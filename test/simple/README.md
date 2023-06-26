# Simple Tests

## copy-file.sh

[copy-file.sh](copy-file.sh) runs a very simple test using AWS S3 CLI.
It runs commands: __cp__, __ls__, __mv__, __rm__, __presign__,
__website__.  It generates a file of 32MB randoms, and uploads and
downloads it.  That file is large enough to start a multipart upload
(8MB is the default threshold to use a multipart upload).

An S3 secret should be prepared in ".aws/*".  A bucket needs to be
created in advance, too.  The shell variables "EP" and "BKT" are the
target, "EP" as an endpoint and "BKT" as a bucket.  It reads (sources
by ".") a file "epbkt.sh" if it exists.

Note it leaves garbage files.  Run the tests in the "test/simple"
directory, because it needs sample files in the directory.

__presign__ is useless.  Lens3 does not understand a secret in URL.

__website__ will fail in Lens3.

## Basic Tests

### Client Setting (credential)

The following tests "test_api.py" and "test_access.py" read a
configuration file "client.json".  It includes endpoints for S3 and
Lens3-Api.  Copy "client-example.json" to "client.json" and edit it.
It also includes a credential to access Lens3-Api.  A credential may
be a user+password pair for basic-authentication, a cookie for Apache
OIDC, or a user name to bypass authentication.  To bypass
authentication, it needs to access Lens3-Api directly (i.e., skipping
the proxy).  A credential for Apache OIDC can be found in a cookie
named "mod_auth_openidc_session".  Web browser's js-console may be
used to check the cookie value.

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

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
* [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
