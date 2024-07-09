# Simple Tests

## Tests

* Basic Test -- Tests upload/download by AWS CLI.
  * [basic-copy](basic-copy)
* Registrar Test -- Tests Registrar operations, e.g., make buckets.
  * [registrar-access](registrar-access)
* Access Permission -- Tests accesses with various key policies.
  * [access-permission](access-permission)
* Sporadic Access -- Tests start/stop of S3 backend servers.
  * [sporadic-access](sporadic-access)
* Busy Server Test -- Tests running too many S3 backend servers.
  * [busy-server](busy-server)
* User Disable
  * [disable-user](disable-user)
* Admin Tool
  * [admin-tool](admin-tool)

## Client Setting

These tests read a configuration file "client.json".  It includes the
endpoints for S3 and Lens3 Registrar.  Copy "client-example.json" as
"client.json" and edit it.

The entries of "client.json" are:

* __s3_ep__: S3 endpoint, "https://lens3.example.com".
* __reg_ep__: Registrar endpoint, "https://lens3.example.com/lens3.sts".
* __gid__: A unix group of a user.
* __home__: A directory of a pool (anywhere writable).
* __auth__: One of "oidc", "basic", or "x-remote-user".
* __cred__: A credential, a list of strings depending on "auth".
* __ssl_verify__: A flag to use https.
* __pools_count__: Number of MinIO instances.
* __backend_awake_duration__: Wait time, use the value in Lens3 configuration.

__auth__ and __cred__ specify a credential used in the test.  __auth__
has three choices: {"oidc", "basic", "x-remote-user"}; and "oidc" for
Apache OIDC authentication, "basic" for basic authentication, and
"x-remote-user" for bypassing authentication.  __cred__ is a list of
strings.  __cred__ is a single entry list [cookie-value] for "oidc", a
list [user-id, password] for "basic", and a list [user-id] for
"x-remote-user".  A given user-id is set in the http header
"x-remote-user".

To use auth="oidc", the secret for Apache OIDC authentication should
be taken from a "mod_auth_openidc_session" cookie.  The cookie is
recorded in a web-brower but it is protected and not accessible in js,
and it should be taken by web-browser's js-console (for debugging).

To use auth="x-remote-user" (bypassing authentication), the test needs
to access Lens3-Registrar directly from the host that runs Lens3
services (thus, skipping the proxy).

__pools_count__ and __backend_awake_duration__ are used in the test
"busy-server".

## Info

For S3 CLI, refer to the links:
* [S3 CLI commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3/index.html)
* [S3 CLI API commands](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/s3api/index.html)
