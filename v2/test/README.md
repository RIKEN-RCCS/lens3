# Simple Tests

## Tests

- [basic-copy](basic-copy) tests uploading/downloading by AWS CLI.  It
  is the simplest test.

- [registrar-access](registrar-access) tests some of the Registrar
  operations.

- [access-permission](access-permission) tests accesses with various
  key policies.  It checks accesses are properly granted/blocked.  It
  should be tested before each software release.

- [busy-server](busy-server) tests running many backend servers.

- [sporadic-access](sporadic-access) tests starting/stopping backend
  servers.

## Client Setting

Some tests read a configuration file "client.json".  It includes the
endpoints for S3 and Lens3 Registrar.  Copy "client-example.json" as
"client.json" and edit it.

The entries of "client.json" are:

- __s3_ep__: S3 endpoint, "https://lens3.example.com".
- __reg_ep__: Registrar endpoint, "https://lens3.example.com/lens3.sts".
- __gid__: A unix group of a user.
- __home__: A directory of a pool (anywhere writable).
- __auth__: One of "basic", "oidc", or "x-remote-user".
- __cred__: A credential, a list of strings depending on "auth".
- __ssl_verify__: A flag to use https.
- __pools_count__: Number of MinIO instances.
- __backend_awake_duration__: Wait time, use the value in Lens3 configuration.

__auth__ and __cred__ specify a credential used in the tests.
__auth__ has three choices: {"basic", "oidc", "x-remote-user"}, where
"basic" for basic authentication, "oidc" for Apache OIDC
authentication, and "x-remote-user" for bypassing authentication.
__cred__ is a list of strings.

For auth="basic", cred is a two entry list cred=[user-id, password].

For auth="oidc", cred is a single entry list cred=[cookie-value].  It
needs the secret for Apache OIDC authentication, which is stored in
the "mod_auth_openidc_session" cookie.  The cookie is recorded in a
web-brower but it is protected and not accessible in js.  It should be
taken by web-browser's js console or debugger.

For auth="x-remote-user", cred is a single entry list cred=[user-id].
It sets a given user-id in the http header "x-remote-user".  Since it
bypasses authentication, tests need to access Lens3 Registrar directly
from the host that runs Lens3 services.

__pools_count__ and __backend_awake_duration__ are used in the test
"busy-server".

## Python Setting

Tests uses "boto3".  Installing "boto3" is system dependent, ie, by
pip3 or dnf/apt, etc.

By pip3, do
```
$ pip3 install --user -r requirements.txt
```

Or, on Ubuntu, do
```
$ apt install python3-boto3
```

## Install AWS CLI

Some tests use AWS Command Line Interface (AWS CLI).  Instructions of
installing AWS CLI can be found at:
[Install or update to the latest version of the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

## Info on AWS CLI

For S3 CLI, refer to the links:
- [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
- [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
