# Lenticularis-S3 Setting Guide

## Outline

This document describes setting for Lenticularis-S3 (Lens3).

| ![lens3-setting](lens3-setting.svg) |
|:--:|
| **Fig. Lens3 overview.** |

The steps are:
* Prepare prerequisite software and install Lens3
* Set up a proxy (Apache HTTPD)
* Start Redis
* Start Lens3-Mux (a Multiplexer service)
* Start Lens3-Api (a Web-API service)
* Register users

## Assumptions

Lens3 consists of a couple of services as depicted in the
configuration figure above.  A reverse-proxy can be any server, but
Apache HTTP Server is used in this guide.  A key-value database
server, Redis, runs at port=6378.  The Lens3 services, Lens3-Mux and
Lens3-Api, run at port=8003 and port=8004, respectively.  The proxy is
set up to forward requests to Lens3-Mux and Lens3-Api.

A pseudo user "lens3" is the owner of the services in this guide, who
is given a privilege of sudoers.  Optionally, a second pseudo user,
anyone who can access the Lens3 configuration file, may be prepared as
an administrator.

We assume RedHat/Rocky 8.8 and Python 3.9 at this writing (in June
2023).

It is highly recommended the server host is not open for users.

* Services and thier ports
  * HTTP Proxy (port=433)
  * Redis (port=6378)
  * Lens3-Mux (port=8003)
  * Lens3-Api (port=8004)

* User IDs
  * `lens3:lens3` -- a pseudo user for services
  * `httpd` or `nginx`

* Files and directories
  * /usr/lib/systemd/system/lenticularis-api.service
  * /usr/lib/systemd/system/lenticularis-mux.service
  * /usr/lib/systemd/system/lenticularis-redis.service
  * /etc/lenticularis/conf.json
  * /etc/lenticularis/redis.conf
  * /var/log/lenticularis/
  * /var/log/lenticularis-redis/
  * /run/lenticularis-redis/ (temporary)
  * /etc/httpd/
  * /etc/nginx/conf.d/

* Software
  * RedHat/Rocky 8.8
  * Python 3.9
  * git

## Install Prerequisites

Install "Python", "Redis", and "Development-Tools" onto the host.

```
# dnf groupinstall "Development Tools"
# dnf install python39
# dnf install redis
```

Ensure using Python3.9, if necessary.

```
# update-alternatives --config python3
```

Check the version of Python3.

```
$ python3 --version
$ update-alternatives --display python3
```

Install a proxy, either Apache or NGINX.  Install Apache (with
optional OpenID Connect).

```
# dnf install httpd mod_ssl mod_proxy_html
# dnf install mod_auth_openidc
```

Or, install NGINX.

```
# dnf install nginx
# dnf install httpd-tools
```

## Install Lens3

Note "$TOP" in the following refers to the top directory in the
downloaded Lens3 package.

Make a pseudo-user for the services.  UID/GID will be selected from a
lower range below 1000 that won't conflict with true users.  Most of
the installation is performed by the user "lens3".  Fix its umask
appropriately such as by `umask 022`.

```
# useradd -K UID_MIN=301 -K UID_MAX=499 -K GID_MIN=301 -K GID_MAX=499 -U -d /home/lens3 lens3
```

Download MinIO binaries "minio" and "mc" from min.io, then fix the
permission.  The home, ~/bin, ~/bin/minio, and ~/bin/mc are set to be
accessible as permission=755 so that anyone can run minio and mc.

NOTE: Use old "minio" that is earlier than
RELEASE.2022-06-02T02-11-04Z.  "mc" is old, too, correspondingly.  It
is because versions from that release use an erasure-coding backend,
which stores files in chunks and does not work for exporting existing
files.

See [Deploy MinIO: Single-Node Single-Drive](https://min.io/docs/minio/linux/operations/install-deploy-manage/deploy-minio-single-node-single-drive.html)

```
# su - lens3
lens3$ cd ~
lens3$ mkdir bin
lens3$ chmod 755 ~ ~/bin
lens3$ cd /tmp
lens3$ wget https://dl.min.io/server/minio/release/linux-amd64/archive/minio-20220526054841.0.0.x86_64.rpm
lens3$ rpm2cpio minio-20220526054841.0.0.x86_64.rpm | cpio -id --no-absolute-filenames usr/local/bin/minio
lens3$ install -m 755 -c ./usr/local/bin/minio ~/bin/minio
lens3$ rm -r usr
lens3$ wget https://dl.min.io/client/mc/release/linux-amd64/archive/mc.RELEASE.2022-06-10T22-29-12Z
lens3$ install -m 755 -c ./mc.RELEASE.2022-06-10T22-29-12Z ~/bin/mc
```

Install Lens3 and Python packages.  Installation should be run in the
"$TOP/v1" directory.  Running `make install` in the "$TOP/v1"
directory does the same work.

```
# su - lens3
lens3$ cd $TOP/v1
lens3$ pip3 install --user -r requirements.txt
lens3$ ls ~/.local/lib/python3.9/site-packages/lenticularis
```

## Prepare Log File Directories

Create directories for logging, and modify their security attributes.
Redis usually requires "redis_log_t" to write its logs, and
"logrotate" requires "var_log_t" or "redis_log_t".  Note "tmp_t"-type
won't work due to the policy for "logrotate".  Enforce the attribute
by "restorecon" (or using "chcon -t redis_log_t").

```
# mkdir /var/log/lenticularis
# chown lens3:lens3 /var/log/lenticularis
# chmod 700 /var/log/lenticularis
# ls -dlZ /var/log/lenticularis
(* Check the context is with var_log_t on /var/log/lenticularis. *)

# mkdir /var/log/lenticularis-redis
# chown lens3:lens3 /var/log/lenticularis-redis
# chmod 700 /var/log/lenticularis-redis
# semanage fcontext -a -t redis_log_t /var/log/lenticularis-redis
# restorecon -v /var/log/lenticularis-redis
# ls -dlZ /var/log/lenticularis-redis
(* Check the context is with redis_log_t on /var/log/lenticularis-redis. *)
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

## Set up an HTTP Proxy

HTTP Proxy seeting is highly site dependent.  Please ask the site
manager for setting.

### A Note on Proxy Path Choices

A path, "location" or "proxypass", should be "/" for Lens3-Mux,
because a path cannot be specified for the S3 service.  Thus, when
Lens3-Mux and Lens3-Api services are co-hosted, the Lens3-Mux path
should be "/" and the Lens3-Api path should be something like
"/lens3.sts/" that is NOT a legitimate bucket name.  We will use
"lens3.sts" in the following.

Please refer to the note on running MinIO with a proxy, saying: "The
S3 API signature calculation algorithm does not support proxy schemes
... on a subpath".  See near the bottom of the following page:

[Configure NGINX Proxy for MinIO
Server](https://min.io/docs/minio/linux/integrations/setup-nginx-proxy-with-minio.html).

### A Note on Required HTTP Headers

Lens3-Api trusts the "X-Remote-User" header passed by the proxy, which
holds an authenticated user claim.  Make sure the header is properly
filtered and prepared by the proxy.

Lens3-Mux requires {"Host", "X-Forwarded-For", "X-Forwarded-Host",
"X-Forwarded-Server", "X-Forwarded-Proto", "X-Real-IP"}.  "Connection"
(for keep-alive) is forced unset for Lens3-Mux.

These are all practically standard headers.  Note {"X-Forwarded-For",
"X-Forwarded-Host", "X-Forwarded-Server"} are implicitly set by Apache
HTTPD.

## CASE1: Proxy by Apache

Set up a configuration file with the needed authentication, and
(re)start the service.

Prepare a configuration file in "/etc/httpd/conf.d/".  Sample files
can be found in $TOP/apache/.  Copy one as
"/etc/httpd/conf.d/lens3proxy.conf" and edit it.  Note running
"restorecon" sets the "system_u"-user on the file (or, you may run
"chcon -u system_u" on the file).

```
# cp $TOP/apache/lens3proxy-basic.conf /etc/httpd/conf.d/lens3proxy.conf
# chown root:root /etc/httpd/conf.d/lens3proxy.conf
# chmod 640 /etc/httpd/conf.d/lens3proxy.conf
# vi /etc/httpd/conf.d/lens3proxy.conf
# restorecon -v /etc/httpd/conf.d/lens3proxy.conf
# ls -lZ /etc/httpd/conf.d/lens3proxy.conf
(* Check the context is with system_u on it. *)
```

A note for proxy setting: A trailing slash in
ProxyPass/ProxyPassReverse lines is necessary (in both the pattern
part and the URL part as noted in Apache documents).  It instructs the
proxy to forward directory accesses to Lens3-Api.  As a consequence,
accesses by "https://lens3.exmaple.com/lens3.sts" (without a slash)
will fail.

```
ProxyPass /lens3.sts/ http://localhost:8004/
ProxyPassReverse /lens3.sts/ http://localhost:8004/
```

For OIDC (OpenID Connect) authentication, there is a good tutorial for
setting Apache with Keyclock -- "3. Configure OnDemand to authenticate
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

Start Apache HTTPD.

```
# systemctl enable httpd
# systemctl start httpd
```

### Other Settings for Apache (Tips)

To add a cert for Apache, copy the cert and edit the configuration
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

## CASE2: Proxy by NGINX

The following example is for basic authentication.  First, prepare a
configuration file in "/etc/nginx/conf.d/", maybe by copying a sample
file in $TOP/nginx/.

```
# cp $TOP/nginx/lens3proxy-basic.conf /etc/nginx/conf.d/lens3proxy.conf
# vi /etc/nginx/conf.d/lens3proxy.conf
```

Prepare passwords for basic authentication.

```
# mkdir /etc/nginx/private
# chown nginx:nginx /etc/nginx/private
# chmod 770 /etc/nginx/private
# touch /etc/nginx/private/htpasswd
# chown nginx:nginx /etc/nginx/private/htpasswd
# chmod 660 /etc/nginx/private/htpasswd
# htpasswd -b /etc/nginx/private/htpasswd user pass
# ......
```

Stop/start NGINX during configuration changes.

```
# systemctl stop nginx
......
# systemctl enable nginx
# systemctl start nginx
```

### A Note about NGINX parameters

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

## Start Redis

Lens3 uses a separate Redis instance running at port=6378 (not
well-known port=6379).

Prepare a configuration file as "/etc/lenticularis/redis.conf".
Change the owner and edit the fields.  Starting Redis will fail when
the owner of /etc/lenticularis/redis.conf is not "lens3".  Keep it
secure.  The following fields need be changed from the sample file:

* bind: Network interfaces; localhost by default
* port: A port for Redis
* requirepass: A passhprase for Redis

```
# mkdir /etc/lenticularis
# cp $TOP/unit-file/redis/redis.conf /etc/lenticularis/redis.conf
# chown lens3:lens3 /etc/lenticularis/redis.conf
# chmod 660 /etc/lenticularis/redis.conf
# vi /etc/lenticularis/redis.conf
```

Prepare a systemd unit file for Redis, and start/restart Redis.

```
# cp $TOP/unit-file/redis/lenticularis-redis.service /usr/lib/systemd/system/
# systemctl daemon-reload
# systemctl enable lenticularis-redis
# systemctl start lenticularis-redis
```

Lens3-Mux and Lens3-Api connect to Redis using the information held in
"/etc/lenticularis/conf.json".  Copy and edit the configuration file.
Keep it secure as it holds the password to Redis.

```
# cp $TOP/unit-file/conf.json /etc/lenticularis/conf.json
# chown lens3:lens3 /etc/lenticularis/conf.json
# chmod 660 /etc/lenticularis/conf.json
# vi /etc/lenticularis/conf.json
```

## Store Lens3 Settings in Redis

Lens3-Mux and Lens3-Api load the configuration from Redis.  This
section prepares it.  It is better to run `lens3-admin` on the same
host running Redis.  See the following descriptions of the fields of
the configurations.

* [mux-conf-yaml.md](mux-conf-yaml.md)
* [api-conf-yaml.md](api-conf-yaml.md)

Make the configurations in files to load them in Redis.

```
# su - lens3
lens3$ cd ~
lens3$ cp $TOP/unit-file/api-conf.yaml api-conf.yaml
lens3$ cp $TOP/unit-file/mux-conf.yaml mux-conf.yaml
lens3$ vi api-conf.yaml
lens3$ vi mux-conf.yaml
```

Load the Lens3 configuration from the files.  Note `lens3-admin` needs
"conf.json" containing connection information to Redis.  KEEP
"conf.json" SECURE ALL THE TIME -- access keys to S3 are stored in the
database in raw text.

```
# cp /etc/lenticularis/conf.json /home/lens3/conf.json
# chown lens3:lens3 /home/lens3/conf.json
# chmod 660 /home/lens3/conf.json
# su - lens3
lens3$ cd ~
lens3$ lens3-admin -c conf.json load-conf api-conf.yaml
lens3$ lens3-admin -c conf.json load-conf mux-conf.yaml
lens3$ lens3-admin -c conf.json show-conf
```

## Set up sudoers for Lens3-Mux

Lens3 runs MinIO as a non-root process, and thus, it uses sudo to
start MinIO.  The provided example setting is that the user "lens3" is
only allowed to run "/home/lens3/bin/minio".  Copy and edit an entry
in "/etc/sudoers.d/lenticularis-sudoers".

```
# cp $TOP/unit-file/mux/lenticularis-sudoers /etc/sudoers.d/
# vi /etc/sudoers.d/lenticularis-sudoers
# chmod 440 /etc/sudoers.d/lenticularis-sudoers
```

## (Optional) Set up Log Rotation

Logs from Lens3-Mux, Lens3-Api, Gunicorn, and Redis are rotated with
"copytruncate".  Note the "copytruncate" method has a minor race.  The
USR1 signal to Gunicorn is not used because it would terminate the
process (in our environment), contrary to the Gunicorn document.  A
rule for Redis is a modified copy of /etc/logrotate.d/redis.  We
didn't use Python's logging.handlers.TimedRotatingFileHandler, because
its work differs from what we expected.

```
# cp $TOP/unit-file/logrotate/lenticularis /etc/logrotate.d/
# vi /etc/logrotate.d/lenticularis
# chmod 644 /etc/logrotate.d/lenticularis
```

## Start Lens3-Mux and Lens3-Api Services

Lens3-Mux and Lens3-Api will be started as a system service with
uid:gid=lens3:lens3.  Copy (and edit) the systemd unit files for
Lens3-Api and Lens3-Mux.

```
# cp $TOP/unit-file/api/lenticularis-api.service /usr/lib/systemd/system/
# cp $TOP/unit-file/mux/lenticularis-mux.service /usr/lib/systemd/system/
```

```
# systemctl daemon-reload
# systemctl enable lenticularis-mux
# systemctl start lenticularis-mux
# systemctl enable lenticularis-api
# systemctl start lenticularis-api
# systemctl status lenticularis-mux
# systemctl status lenticularis-api

```

## Register Users

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

## Check the Status

Proxy status:

```
# systemctl status http
Or,
# systemctl status nginx
```

Redis status:

```
# systemctl status lenticularis-redis
```

Lens3-Mux and Lens3-Api status:

```
# systemctl status lenticularis-mux
# systemctl status lenticularis-api
# su - lens3
lens3$ cd ~
lens3$ lens3-admin -c conf.json show-ep
```

The admin command `show-ep` shows the endpoints of Lens3-Mux and MinIO
instances.  Something goes wrong if there are no entries of Lens3-Mux.

## Test Accesses

Access Lens3-Api by a browser (for example):
`http://lens3.example.com/lens3.sts/`

For accessing buckets from S3 client, copy the access/secret keys
created in UI to the AWS "credentials" file.  Note that Lens3 does not
support listing of buckets by `aws s3 ls`.

```
lens3$ vi ~/.aws/config
[default]
s3 =
    signature_version = s3v4

lens3$ vi $HOME/.aws/credentials
[default]
aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO

lens3$ aws --endpoint-url https://lens3.example.com/ s3 ls s3://bkt1
lens3$ aws --endpoint-url https://lens3.example.com/ s3 cp s3://bkt1/somefile1 -
```

## Troubleshooting

### Early Troubles

First check the systemd logs.  Diagnosing errors before a start of
logging is tricky.

A log of Lens3-Api may include a string "EXAMINE THE GUNICORN LOG",
which indicates a Gunicorn process finishes by some reason.  Check the
logs of Gunicorn.

### Examining MinIO Behavior

It is a bit tricky when MinIO does not behave as expected.  In that
case, it will help to connect to MinIO with "mc" command.

The necessary information to use "mc" command, URL, ACCESSKEY and
SECRETKEY, can be taken by "show-minio" command of "lens3-admin".
First, run "show-pool" to list all the pools.  Then, run "show-minio"
with a pool-id to display the information.  It displays URL
(host+port) of MinIO as "minio_ep".  It also displays admin's
ACCESSKEY under the key "admin" and SECRETKEY under "password".  Note
that the "show-minio" command is only useful while a MinIO instance is
running.  To keep a MinIO instance running, call the "access-mux"
command periodically.  Otherwise, it will stop after a while.

```
lens3$ lens3-admin -c conf.json show-pool
lens3$ lens3-admin -c conf.json show-minio POOLID
lens3$ lens3-admin -c conf.json access-mux POOLID
```

For example, the following commands can be used to dump tracing logs
from MinIO.  ALIAS can be any string, and URL would be something like
"http://lens3.example.com:9012".

```
lens3$ mc alias set ALIAS URL ACCESSKEY SECRETKEY
lens3$ mc admin trace -v ALIAS
```

### Clean Start for Messy Troubles

Clear Redis databases.

```
lens3$ export REDISCLI_AUTH=password
lens3$ redis-cli -p 6378 FLUSHALL
lens3$ redis-cli -p 6378 --scan --pattern '*'
```

### Running MinIO by Hand

```
lens3$ minio --json --anonymous server --address :9001 /home/UUU/pool-directory
```

### No Support for Multiple Hosts

Current version requires all the proxy, Lens3-Mux, and Lens3-Api run
on a single host.  To set up for multiple hosts, it needs at least to
specify options to Gunicorn to accept non-local connections.
