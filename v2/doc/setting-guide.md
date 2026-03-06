# Lenticularis-S3 Setting Guide

## Outline

This document describes setting for Lenticularis-S3 (Lens3).

| ![lens3-overview](lens3-overview.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Installation procedure is described in a separate page
[installation-procedure.md](installation-procedure.md).

## Notes on an HTTP Proxy

HTTP Proxy seeting is highly site dependent.  Please ask the site
manager for setting.

### Proxy Path Choices

A path, "location" or "proxypass", should be "/" for Multiplexer,
because a path cannot be specified for the S3 service.  Thus, when
Multiplexer and Registrar services are co-hosted, the Multiplexer path
should be "/" and the Registrar path should be something like
"/lens3.sts/" that is NOT a legitimate bucket name.  We will use
"lens3.sts" in the following.

MinIO's note mentions URL path usage behind a proxy, saying: "The S3 API
signature calculation algorithm does not support proxy schemes ... on
a subpath".  See near the bottom of the following page.

[Configure NGINX Proxy for MinIO Server](https://min.io/docs/minio/linux/integrations/setup-nginx-proxy-with-minio.html).

### Required HTTP Headers

Registrar requires "X-Remote-User" and "X-Csrf-Token".  Registrar
trusts the "X-Remote-User" header, which holds an authenticated user
claim.  Make sure it is properly set by the proxy.

Multiplexer requires the headers for the S3 protocol, of course.  It
needs "Host".  Thus, set "ProxyPreserveHost On" in the Apache-HTTPD
configuration.

Note {"X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Server"} are
automatically set by Apache-HTTPD.

## Set up a Proxy by Apache-HTTPD

### Common Setup

Set up a configuration file with the needed authentication, and
(re)start the service.

Prepare a configuration file in "/etc/httpd/conf.d/".  Sample files
can be found in $TOP/v2/proxy-apache/.  Copy one as
"/etc/httpd/conf.d/lens3proxy.conf" and edit it.  Note running
"restorecon" sets the "system_u"-user on the file (or, you may run
"chcon -u system_u" on the file).

```
# cp $TOP/v2/proxy-apache/lens3proxy-basic.conf /etc/httpd/conf.d/lens3proxy.conf
# chown root:root /etc/httpd/conf.d/lens3proxy.conf
# chmod 640 /etc/httpd/conf.d/lens3proxy.conf
# vi /etc/httpd/conf.d/lens3proxy.conf
# restorecon -v /etc/httpd/conf.d/lens3proxy.conf
# ls -lZ /etc/httpd/conf.d/lens3proxy.conf
(* Check the context is with system_u on it. *)
```

A note for proxy setting: A trailing slash in
ProxyPass/ProxyPassReverse lines is necessary (in both the pattern
part and the URL part as noted in Apache-HTTPD documents).  It
instructs the proxy to forward directory accesses to Registrar.  As a
consequence, accesses by "https://lens3.exmaple.com/lens3.sts"
(without a slash) will fail.

```
ProxyPass /lens3.sts/ http://localhost:8004/
ProxyPassReverse /lens3.sts/ http://localhost:8004/
```

### Choice: OIDC Authentication

For OIDC (OpenID Connect) authentication, there is a good tutorial for
setting Apache-HTTPD with Keyclock -- "3. Configure OnDemand to authenticate
with Keycloak".  See below.

[https://osc.github.io/ood-documentation/.../install_mod_auth_openidc.html](https://osc.github.io/ood-documentation/latest/authentication/tutorial-oidc-keycloak-rhel7/install_mod_auth_openidc.html)

OIDC logging messages are generated in "ssl_error_log".  Verbosity can
be increased by setting "LogLevel" to "debug" in the "<Location
/lens3.sts>" section.  The "LoadModule" line in the sample file
"lens3proxy-oidc.conf" may be redundant, and it generates a warning
message.

### Choice: Basic Authentication

Prepare passwords for basic authentication.

```
# mkdir /etc/httpd/passwd
# chown apache:apache /etc/httpd/passwd
# chmod 770 /etc/httpd/passwd
# touch /etc/httpd/passwd/passwords
# chown apache:apache /etc/httpd/passwd/passwords
# chmod 660 /etc/httpd/passwd/passwords
# htpasswd -b /etc/httpd/passwd/passwords user pass
......
```

### Start or Restart httpd

Start Apache-HTTPD.

```
# systemctl enable httpd
# systemctl start httpd
```

### Other Settings for Apache-HTTPD (Tips)

To add a cert for Apache-HTTPD, copy the cert and edit the configuration
file.  Change the lines of cert and key in
"/etc/httpd/conf.d/ssl.conf".

```
# cp lens3.crt /etc/pki/tls/certs/lens3.crt
# cp lens3.key /etc/pki/tls/private/lens3.key
# chown root:root /etc/pki/tls/private/lens3.key
# chmod 600 /etc/pki/tls/private/lens3.key
# vi /etc/httpd/conf.d/ssl.conf

+SSLCertificateFile /etc/pki/tls/certs/lens3.crt
+SSLCertificateKeyFile /etc/pki/tls/private/lens3.key
```

## A Note about NGINX

NGINX has a parameter on the limit "client_max_body_size"
(default=1MB).  The default value is too small.  The size "10M" seems
adequate or "0" which means unlimited may also be adequate.

```
server {
    client_max_body_size 10M;
}
```

It is recommended to check the limits of the proxy when encountering a
413 error (Request Entity Too Large).  "client_max_body_size" limits
the payload.  On the other hand, AWS S3 CLI has parameters for file
transfers "multipart_threshold" (default=8MB) and
"multipart_chunksize" (default=8MB).  Especially,
"multipart_chunksize" has the minimum of 5MB.

NGINX parameters are specified in the server section (or in the http
section) in the configuration.  The "client_max_body_size" is defined
in ngx_http_core_module.  See for the NGINX ngx_http_core_module
parameters:
[https://nginx.org/en/docs/http/ngx_http_core_module.html](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)
See also for the AWS S3 CLI parameters:
[https://docs.aws.amazon.com/cli/latest/topic/s3-config.html](https://docs.aws.amazon.com/cli/latest/topic/s3-config.html).

## Store Lens3 Settings in Keyval-DB

Most of the work in this part shall be performed by user
"lenticularis".

However, copying the "lens3.conf" file should be performed by the root
beforehand.

```
# cp /etc/lenticularis/lens3.conf ~lenticularis/lens3.conf
# chown lenticularis:lenticularis ~lenticularis/lens3.conf
# chmod 660 ~lenticularis/lens3.conf
```

Multiplexer and Registrar load the configuration from the keyval-db
(Valkey).  This section prepares it.  It is better to run
`lenticularis-admin` on the same host running the keyval-db.  See the
following description of the fields of the configurations.

- [configuration.md](configuration.md)

First, view the stored configurations.

```
lenticularis-admin -c lens3.conf show-conf
```

Make the configurations in files and load them in the keyval-db.  Note
`lenticularis-admin` needs "lens3.conf" containing connection
information to the keyval-db.  Keep "lens3.conf" secure, when it is
necessary to copy it.

```
cd /var/lib/lenticularis
vi mux-conf.json
vi reg-conf.json
```

Check the syntax of json before loading the configuration.  It can be
checked by tools such as "jq".  "jq" is a command-line JSON processor.

```
lenticularis$ cat mux-conf.json | jq
lenticularis$ cat reg-conf.json | jq
```

Load the configurations from the files.

```
lenticularis-admin -c ./lens3.conf load-conf mux-conf.json
lenticularis-admin -c ./lens3.conf load-conf reg-conf.json
```

Restarting the service is needed after changing the configurations.
Run `systemctl restart lenticularis-mux`.

## (Optional) Set up Log Rotation

Logs from Multiplexer, Registrar, and Valkey are rotated with
"copytruncate".  Note the "copytruncate" method has a minor race.  The
rule for Valkey is a modified copy of /etc/logrotate.d/redis.

```
cp $TOP/v2/unit-file/lenticularis-logrotate /etc/logrotate.d/lenticularis
vi /etc/logrotate.d/lenticularis
chmod 644 /etc/logrotate.d/lenticularis
```

## (Optional) Set up System Logging

Logging in Rocky is in memory by default.  It needs to be
changed in the setting to keep logs across reboots.

```
# vi /etc/systemd/journald.conf

+[Journal]
+Storage=persistent

# systemctl restart systemd-journald
```

## (Optional) Set up a Message Queue (MQTT)

Lens3 can duplicate alert logs to a message queue.  It assumes MQTT v5
and "mosquitto" for the server.  The assigned MQTT password should be
set in "mux-conf.json".

```
# dnf install mosquitto
# mosquitto_passwd -c /etc/mosquitto/password.txt lens3
# mosquitto_passwd -b /etc/mosquitto/password.txt lens3 password
# chmod 440 /etc/mosquitto/password.txt
# vi /etc/mosquitto/mosquitto.conf

-#allow_anonymous true
+allow_anonymous false
-#password_file
+password_file /etc/mosquitto/password.txt
```

```
# systemctl enable mosquitto
# systemctl start mosquitto
# systemctl status mosquitto
```

It is necessary to reload "mux-conf.json" and to restart the service
after changing the password.

```
vi mux-conf.json
lenticularis-admin -c ./lens3.conf load-conf mux-conf.json
```

```
# systemctl restart lenticularis-mux
```

## Check the Status

Proxy status:

```
# systemctl status httpd
Or,
# systemctl status nginx
```

Valkey status:

```
systemctl status lenticularis-valkey
```

Lenticularis status:

```
systemctl status lenticularis-mux
```

The admin command `show-mux` shows the endpoints of Multiplexers
(lenticularis-mux).  An MUX entry is updated periodically, and its
existence of the entry means lenticularis-mux is working.  Something
goes wrong if it were empty.

```
lenticularis-admin -c ./lens3.conf show-mux
```

## Access Test

### Install AWS CLI

Using AWS Command Line Interface (AWS CLI) is an easiest way to access
S3 storage.

Instructions of installing AWS CLI can be found at:
[Install or update to the latest version of the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

### Set Access Keys in the "credentials" File

A bucket and an access key are needed to acess S3 storage.  First,
create a pool, a bucket, and a pair of access keys, by accessing Lens3
Registrar UI by a browser at `http://lens3.example.com/lens3.sts/`,
for example.

AWS CLI needs the created access/secret keys being stored in the
"credentials" file.  Copy the keys in the file.

```
vi ~/.aws/credentials

[default]
aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO
```

Optionally, set the signature version in the "config" file.

```
vi ~/.aws/config

[default]
s3 =
    signature_version = s3v4
```

Access the S3 bucket, here it is "bkt1".

```
aws --endpoint-url https://lens3.example.com/ s3 ls s3://bkt1
aws --endpoint-url https://lens3.example.com/ s3 cp somefile1 s3://bkt1/
aws --endpoint-url https://lens3.example.com/ s3 ls s3://bkt1
```

Note that Lens3 does not support listing of buckets by `aws s3 ls`.

## (Optional) Register Users

Registering users is required when Lens3's configuration has a setting
"user_approval=block".  Lens3 keeps its own a list of users
(UID + GID's) and a list of enablement statuses of users.

See [Administration Guide](admin-guide.md#).

Lens3 loads user information from a CSV-file.  Each entry in CSV is a
"ADD" keyword followed by a UID, a claim string, and a list of groups.
A claim string (3rd column) can be empty, which is a name from
authentication (such as OIDC).  Prepare a list of users in a CSV-file.

```
vi CSV-FILE.csv

ADD,user1,,group1a,group1b,group1c, ...
ADD,user2,,group2a,group2b,group2c, ...
ADD,user3,,group3a,group3b,group3c, ...
...
```

Optionally, a CSV-file may contain a list of users enabled/disabled to
access.  An entry is a "ENABLE"/"DISABLE" prefix followed by a list of
UID's.

```
vi CSV-FILE.csv

+ENABLE,user1,user2,user3, ...
+DISABLE,user4,user5,user6, ...
```

Register users by `lenticularis-admin` command.

```
lenticularis-admin -c ./lens3.conf load-user CSV-FILE.csv
lenticularis-admin -c ./lens3.conf show-user
```

## Troubleshooting

### Early Troubles

Check the systemd logs, first.  Diagnosing errors before a start of
logging is tricky.

```
systemctl status lenticularis-mux
Or,
journalctl
```

### More Verbose Logging

Logs of Lens3 are dumped in "/var/log/lenticularis/lens3-log".

The configuration "logging.logger.tracing=255" can increase logging
verbosity.  It is bit flags, and 255 is all bits on.

The setting of "logging.logger.tracing" is in the configuration
"mux-conf.json".  Reloading the configuration by "lenticularis-admin"
and restarting the service by "systemctl" are needed to make changes
effective.

### Running an S3 Server by Hand

A major trouble is starting an S3 server.  Try to start S3 Baby-server
by hand.

```
/usr/loca/bin/s3-baby-server serve :9000 SOME-PATH
Or,
/usr/bin/sudo -n -u SOME-UID -g SOME-GID \
    /usr/loca/bin/s3-baby-server serve :9000 SOME-PATH
```

### Clean Start for Messy Troubles

Clear Valkey databases.

```
export REDISCLI_AUTH=password
valkey-cli -p 6378 FLUSHALL
valkey-cli -p 6378 -n 1 --scan --pattern '*'
valkey-cli -p 6378 -n 2 --scan --pattern '*'
valkey-cli -p 6378 -n 3 --scan --pattern '*'
```

Use "-a password" instead of an environment variable.

### OIDC Redirect Failure

OIDC may err with "Invalid parameter: redirect_uri" and fail to return
to Lens3, when using an example configuration "lens3proxy-oidc.conf".
It would happen in an https only site.  It may be fixed by modifying a
"OIDCRedirectURI" line to a full URL starting with "https:".

## CAVEAT

- __backend_timeout_ms__ in a configuration should be larger than
  1 sec, and recomended 5 sec.  Error responses from a backend could
  be delayed which cause all errors to be reported as timeouts.

- Current version does not support of multiple hosts.  It requires all
  the frontend proxy, Valkey, Multiplexer, and Registrar run on a
  single host.

- Lens3 works only with the signature algorithm version	 v4 of AWS S3.
  That is, an authentication header must include the string
  "AWS4-HMAC-SHA256".
