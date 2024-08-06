# Lenticularis-S3 Setting Guide

## Outline

This document describes setting for Lenticularis-S3 (Lens3).

| ![lens3-setting](../../v1/doc/lens3-setting.svg) |
|:--:|
| **Fig. Lens3 overview.** |

The steps are:
- Prepare prerequisite software and install Lens3
- Set up a frontend proxy (Apache-HTTPD)
- Start Valkey
- Start Lenticularis-S3 service (Multiplexer and Registrar)

## Assumptions

Lens3 consists of a couple of services as depicted in the
configuration figure above.  A reverse-proxy can be any server, but
Apache HTTP Server is used in this guide.  A keyval-db server, Valkey,
runs at port=6378.  The Lens3 services, Multiplexer and Registrar,
run at port=8003 and port=8004, respectively.  The proxy is set up to
forward requests to Multiplexer and Registrar.

A pseudo user "lens3" is the owner of the services in this guide, who
is given a privilege of sudoers.  Optionally, a second pseudo user,
anyone who can access the Lens3 configuration file, may be prepared as
an administrator.

IT IS HIGHLY RECOMMENDED THE SERVER HOST IS NOT OPEN FOR USERS.

We assume RedHat/Rocky 8.10 and Golang 1.22 at this writing (in Aug
2024).

- Services and thier ports
  - HTTP Proxy (port=433)
  - Valkey (port=6378)
  - Multiplexer (port=8003)
  - Registrar (port=8004)

- User IDs
  - `lens3:lens3` -- a pseudo user for services
  - `httpd`

- Files and directories
  - /usr/lib/systemd/system/lenticularis-mux.service
  - /usr/lib/systemd/system/lenticularis-valkey.service
  - /etc/lenticularis/conf.json
  - /etc/lenticularis/valkey.conf
  - /var/log/lenticularis/
  - /var/log/lenticularis-valkey/
  - /run/lenticularis-valkey/ (temporary)
  - /etc/httpd/

- Software
  - RedHat/Rocky 8.8
  - Golang 1.22 and later
  - Valkey 7
  - git

## Install Prerequisites

Install "Golang-1.22", "Valkey-7", and "Development-Tools" onto the
host.  Some tests in Lens3 use Python.

Install basic tools, first.

```
# dnf groupinstall "Development Tools"
# dnf install rpm-devel
```

Install Valkey.  Valkey is in EPEL.

```
# dnf install epel-release
# dnf repolist
# dnf install valkey
```

Install Apache-HTTPD with OpenID Connect (optional).

```
# dnf install httpd mod_ssl mod_proxy_html
# dnf install mod_auth_openidc
```

Install Golang.  But, Golang in RedHat/Rocky is old.  Download a newer
one from: https://go.dev/dl/

```
# dnf remove 'golang*'
# rm -rf /usr/local/go
# tar -C /usr/local -xzf go1.22.5.linux-amd64.tar.gz
```

## Make Pseudo User Lens3

Make a pseudo user for the services.  UID/GID will be selected from
the lower range below 1000 that won't conflict with real users.  Most
of the installation is performed by the user "lens3".  Fix its umask
appropriately such as by `umask 022`.

```
# useradd -K UID_MIN=301 -K UID_MAX=499 -K GID_MIN=301 -K GID_MAX=499 -U -d /home/lens3 lens3
```

## Install Lens3

Note "$TOP" in the following refers to the top directory in the
downloaded Lens3 package.

Build and install Lens3.  Installation will copy binary files
("lens3-admin" and "lenticularis-mux") in the "~/go/bin" directory.
Copy "lenticularis-mux" binary to "/usr/local/bin".

```
# su - lens3
lens3$ cd $TOP/v2/pkg/lens3
lens3$ go get
lens3$ go build
lens3$ cd $TOP/v2/cmd/lenticularis-mux
lens3$ go install
lens3$ cd $TOP/v2/cmd/lens3-admin/
lens3$ go install
lens3$ exit
# install -m 755 -c /home/lens3/go/bin/lenticularis-mux /usr/local/bin/lenticularis-mux
```

## Download MinIO Binaries

Download MinIO binaries "minio" and "mc" from min.io and install them.
"minio" and "mc" are to be accessible by anyone as permission=755.

NOTE: The binaries are taken from the archive to use specific versions
of MinIO and MC -- MinIO RELEASE.2022-05-26T05-48-41Z and
correspondingly MC RELEASE.2022-06-10T22-29-12Z.  Newer versions of
MinIO starting from RELEASE.2022-06-02T02-11-04Z use an erasure-coding
backend, and they store files in chunks and are not suitable for
exporting existing files.  The version of MC is the one released after
MinIO but as close as to it.

See [Deploy MinIO: Single-Node Single-Drive](https://min.io/docs/minio/linux/operations/install-deploy-manage/deploy-minio-single-node-single-drive.html)

```
# su - lens3
lens3$ cd /tmp
lens3$ wget https://dl.min.io/server/minio/release/linux-amd64/archive/minio-20220526054841.0.0.x86_64.rpm
lens3$ rpm2cpio minio-20220526054841.0.0.x86_64.rpm | cpio -id --no-absolute-filenames usr/local/bin/minio
lens3$ mv ./usr/local/bin/minio ./minio
lens3$ rm -r ./usr
lens3$ rm ./minio-20220526054841.0.0.x86_64.rpm
lens3$ wget https://dl.min.io/client/mc/release/linux-amd64/archive/mc.RELEASE.2022-06-10T22-29-12Z
lens3$ mv ./mc.RELEASE.2022-06-10T22-29-12Z ./mc
lens3$ exit
# install -m 755 -c /tmp/minio /usr/local/bin/minio
# install -m 755 -c /tmp/mc /usr/local/bin/mc
```

## Prepare Log File Directories

Valkey seems using Redis's selinux settings.

Create directories for logging, and modify their security attributes.
Valkey requires "redis_log_t" to write its logs, and logrotate
requires "var_log_t" or "redis_log_t".  Note "tmp_t"-type won't work
due to the policy for logrotate.  Enforce the attribute by restorecon
(or using "chcon -t redis_log_t").

```
# mkdir /var/log/lenticularis
# chown lens3:lens3 /var/log/lenticularis
# chmod 700 /var/log/lenticularis
# ls -dlZ /var/log/lenticularis
(* Check the context is with var_log_t on /var/log/lenticularis. *)

# mkdir /var/log/lenticularis-valkey
# chown lens3:lens3 /var/log/lenticularis-valkey
# chmod 700 /var/log/lenticularis-valkey
# semanage fcontext -a -t redis_log_t "/var/log/lenticularis-valkey(/.*)?"
# semanage fcontext -l | grep lenticularis-valkey
# restorecon -r -v /var/log/lenticularis-valkey
# ls -dlZ /var/log/lenticularis-valkey
(* Check the context is with redis_log_t on /var/log/lenticularis-valkey. *)
```

## Enable HTTP Connections

Let SELinux accept connections inside a local host.

```
# semanage port -a -t http_port_t -p tcp 8003
# semanage port -a -t http_port_t -p tcp 8004
# semanage port -a -t redis_port_t -p tcp 6378
# semanage port --list
# setsebool -P httpd_can_network_connect 1
```

Modify the firewall to accept connections to port=443 and port=80.

```
# firewall-cmd --state
# firewall-cmd --list-all
# firewall-cmd --zone=public --add-port=443/tcp --add-port=80/tcp --permanent
# firewall-cmd --reload
```

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

## Set up Proxy by Apache-HTTPD

Set up a configuration file with the needed authentication, and
(re)start the service.

Prepare a configuration file in "/etc/httpd/conf.d/".  Sample files
can be found in $TOP/v2/apache/.  Copy one as
"/etc/httpd/conf.d/lens3proxy.conf" and edit it.  Note running
"restorecon" sets the "system_u"-user on the file (or, you may run
"chcon -u system_u" on the file).

```
# cp $TOP/v2/apache/lens3proxy-basic.conf /etc/httpd/conf.d/lens3proxy.conf
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

For OIDC (OpenID Connect) authentication, there is a good tutorial for
setting Apache-HTTPD with Keyclock -- "3. Configure OnDemand to authenticate
with Keycloak".  See below.

[https://osc.github.io/ood-documentation/.../install_mod_auth_openidc.html](https://osc.github.io/ood-documentation/latest/authentication/tutorial-oidc-keycloak-rhel7/install_mod_auth_openidc.html)

OIDC logging messages are generated in "ssl_error_log".  Verbosity can
be increased by setting "LogLevel" to "debug" in the "<Location
/lens3.sts>" section.  The "LoadModule" line in the sample file
"lens3proxy-oidc.conf" may be redundant, and it generates a warning
message.

Or, prepare passwords for basic authentication.

```
# mkdir /etc/httpd/passwd
# chown apache:apache /etc/httpd/passwd
# chmod 770 /etc/httpd/passwd
# touch /etc/httpd/passwd/passwords
# chown apache:apache /etc/httpd/passwd/passwords
# chmod 660 /etc/httpd/passwd/passwords
# htpasswd -b /etc/httpd/passwd/passwords user pass
# ......
```

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
> SSLCertificateFile /etc/pki/tls/certs/lens3.crt
> SSLCertificateKeyFile /etc/pki/tls/private/lens3.key
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

## Start Valkey

Lens3 uses a separate Valkey instance running at port=6378 (not
well-known port=6379).

Prepare a configuration file as "/etc/lenticularis/valkey.conf".
Change the owner and edit the fields.  KEEP IT SECURE, because it
includes a password.  Starting Valkey will fail when the owner of
/etc/lenticularis/valkey.conf is not "lens3".  The "requirepass" field
needs be changed from the sample file.

Some of the fields:
- "bind": Network interfaces; localhost by default
- "port": A port for Valkey
- "requirepass": A passhprase for Valkey

```
# mkdir /etc/lenticularis
# cp $TOP/v2/unit-file/valkey.conf /etc/lenticularis/valkey.conf
# chown lens3:lens3 /etc/lenticularis/valkey.conf
# chmod 660 /etc/lenticularis/valkey.conf
# vi /etc/lenticularis/valkey.conf
```

Prepare a systemd unit file for Valkey, and start/restart Valkey.

```
# cp $TOP/v2/unit-file/lenticularis-valkey.service /usr/lib/systemd/system/
# systemctl daemon-reload
# systemctl enable lenticularis-valkey
# systemctl start lenticularis-valkey
```

Multiplexer and Registrar connect to Valkey using the information held
in "/etc/lenticularis/conf.json".  Copy and edit the configuration
file.  Set the password to Valkey in it.  KEEP "conf.json" SECURE ALL
THE TIME.  Access keys are stored in Valkey in raw text.

```
# cp $TOP/v2/unit-file/conf.json /etc/lenticularis/conf.json
# chown lens3:lens3 /etc/lenticularis/conf.json
# chmod 660 /etc/lenticularis/conf.json
# vi /etc/lenticularis/conf.json
```

## Store Lens3 Settings in Valkey

Multiplexer and Registrar load the configuration from Valkey.  This
section prepares it.  It is better to run `lens3-admin` on the same
host running Valkey.  See the following descriptions of the fields of
the configurations.

- [mux-conf-json.md](mux-conf-json.md)
- [reg-conf-json.md](reg-conf-json.md)

Make the configurations in files to load them in Valkey.

```
# su - lens3
lens3$ cd ~
lens3$ cp $TOP/v2/unit-file/mux-conf.json mux-conf.json
lens3$ cp $TOP/v2/unit-file/reg-conf.json reg-conf.json
lens3$ vi mux-conf.json
lens3$ vi reg-conf.json
```

Load the Lens3 configuration from the files.  Note `lens3-admin` needs
"conf.json" containing connection information to the keyval-db.  Keep
"conf.json" secure, when it is necessary to copy it.

```
# cp /etc/lenticularis/conf.json /home/lens3/conf.json
# chown lens3:lens3 /home/lens3/conf.json
# chmod 660 /home/lens3/conf.json
# su - lens3
lens3$ cd ~
lens3$ lens3-admin -c conf.json load-conf mux-conf.json
lens3$ lens3-admin -c conf.json load-conf reg-conf.json
lens3$ lens3-admin -c conf.json show-conf
```

Restarting the service, lenticularis-mux, is needed after setting
configurations.  Run `systemctl restart lenticularis-mux`.

Check the syntax of json before loading the configuration.  It can be
checked by tools such as "jq".  "jq" is a command-line JSON processor.

```
lens3$ cat mux-conf.json | jq
lens3$ cat reg-conf.json | jq
```

## Set up sudoers for Multiplexer

Lens3 runs a backend S3 server as a non-root process, and it uses sudo
for it.  Copy and edit an entry in
"/etc/sudoers.d/lenticularis-sudoers".  The provided example setting
is that the user "lens3" is only allowed to run "/usr/local/bin/minio"
via sudo.

```
# cp $TOP/v2/unit-file/lenticularis-sudoers /etc/sudoers.d/
# vi /etc/sudoers.d/lenticularis-sudoers
# chmod 440 /etc/sudoers.d/lenticularis-sudoers
```

## (Optional) Set up Log Rotation

Logs from Multiplexer, Registrar, and Valkey are rotated with
"copytruncate".  Note the "copytruncate" method has a minor race.  The
rule for Valkey is a modified copy of /etc/logrotate.d/redis.

```
# cp $TOP/v2/unit-file/logrotate/lenticularis /etc/logrotate.d/
# vi /etc/logrotate.d/lenticularis
# chmod 644 /etc/logrotate.d/lenticularis
```

## (Optional) Set up System Logging

Logging in RedHat/Rocky is in memory by default.  It needs to be
changed in the setting to keep logs across reboots.

```
# vi /etc/systemd/journald.conf
[Journal]
Storage=persistent

# systemctl restart systemd-journald
```

## Start Multiplexer and Registrar Services

Multiplexer and Registrar is a single binary, and it will be started
as a system service as "lenticularis-mux".  Copy (and edit) the
systemd unit file for the service.  It is started with the user
uid:gid=lens3:lens3.

```
# cp $TOP/v2/unit-file/lenticularis-mux.service /usr/lib/systemd/system/
```

```
# systemctl daemon-reload
# systemctl enable lenticularis-mux
# systemctl start lenticularis-mux
# systemctl status lenticularis-mux

```

## Check the Status

Proxy status:

```
# systemctl status http
Or,
# systemctl status nginx
```

Valkey status:

```
# systemctl status lenticularis-valkey
```

Multiplexer status:

```
# systemctl status lenticularis-mux
# su - lens3
lens3$ cd ~
lens3$ lens3-admin -c conf.json show-mux
```

The admin command `show-mux` shows the endpoints of Multiplexers.
Something goes wrong if it were empty.

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
lens3$ vi ~/.aws/credentials
[default]
aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO
```

Optionally, set the signature version in the "config" file.

```
lens3$ vi ~/.aws/config
[default]
s3 =
    signature_version = s3v4
```

Access the S3 bucket, here it is "bkt1".

```
lens3$ aws --endpoint-url https://lens3.example.com/ s3 ls s3://bkt1
lens3$ aws --endpoint-url https://lens3.example.com/ s3 cp somefile1 s3://bkt1/
lens3$ aws --endpoint-url https://lens3.example.com/ s3 ls s3://bkt1
```

Note that Lens3 does not support listing of buckets by `aws s3 ls`.

## (Optional) Register Users

Lens3 has its own a list of users (with uid+gid) and a list of
enablement status of the users.  It does not look at the databases of
the underlying OS.

See [Administration Guide](admin-guide.md#).

Lens3 stores user information from a CSV file.  An entry in CSV is a
"ADD" keyword, a uid, a (maybe empty) claim string, and a list of
groups.  Prepare a list of users in a CSV file.  The 3rd column is
used for OIDC.

```
ADD,user1,,group1a,group1b,group1c, ...
ADD,user2,,group2a,group2b,group2c, ...
...
```

Register users by `lens3-admin` command.

```
lens3$ lens3-admin -c conf.json load-user {csv-file}
lens3$ lens3-admin -c conf.json show-user
```

(Optionally) Prepare a list of users enabled to access.  An entry is a
"ENABLE" prefix and a list of uid's

```
ENABLE,user1,user2,user3, ...
```

Register an enabled-user list by `lens3-admin` command.

```
lens3$ lens3-admin -c conf.json load-user {csv-file}
lens3$ lens3-admin -c conf.json show-user
```

## Troubleshooting

### Early Troubles

First check the systemd logs.  Diagnosing errors before a start of
logging is tricky.

### Examining MinIO Behavior

It is a bit tricky when MinIO does not behave as expected.  In that
case, it will help to connect to MinIO with "mc" command.

The necessary information to use "mc" command, URL, ACCESSKEY and
SECRETKEY, can be taken by "show-be" command of "lens3-admin".  First,
run "show-pool" to list all the pools.  Then, run "show-be" with a
pool-name to display the information.  It displays URL (host+port) of
MinIO as "minio_ep".  It also displays admin's ACCESSKEY under the key
"admin" and SECRETKEY under "password".  Note that the "show-be"
command is only useful while a MinIO instance is running.  To keep a
MinIO instance running, call the "access-mux" command periodically.
Otherwise, it will stop after a while.

```
lens3$ lens3-admin -c conf.json show-pool
lens3$ lens3-admin -c conf.json show-be
lens3$ lens3-admin -c conf.json access-mux POOL-NAME
```

For example, the following commands can be used to dump tracing logs
from MinIO.  ALIAS can be any string, and URL would be something like
`http://lens3.example.com:9012`.

```
lens3$ mc alias set ALIAS URL ACCESSKEY SECRETKEY
lens3$ mc admin trace -v ALIAS
```

### Clean Start for Messy Troubles

Clear Valkey databases.

```
lens3$ export REDISCLI_AUTH=password
lens3$ valkey-cli -p 6378 FLUSHALL
lens3$ valkey-cli -p 6378 -n 1 --scan --pattern '*'
lens3$ valkey-cli -p 6378 -n 2 --scan --pattern '*'
lens3$ valkey-cli -p 6378 -n 3 --scan --pattern '*'
```

Use "-a password" instead of an environment variable.

### Running MinIO by Hand

```
lens3$ minio --json --anonymous server --address :9001 /home/UUU/pool-directory
```

### OIDC Redirect Failure

OIDC may err with "Invalid parameter: redirect_uri" and fail to return
to lens3, when using an example configuration "lens3proxy-oidc.conf".
It would happen in an https only site.  It may be fixed by modifying a
"OIDCRedirectURI" line to a full URL starting with "https:".

### No Support for Multiple Hosts

Current version requires all the proxy, Multiplexer, and Registrar run
on a single host.

## CAVEAT

- __backend_timeout_ms__ in a configuration should be larger than
  1 sec, and recomended 5 sec.  Error responses from a backend could
  be delayed which cause all errors to be reported as timeouts.
