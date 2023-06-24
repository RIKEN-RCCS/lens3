# Setup of Lenticularis-S3 (Minimal)

## Outline

This document describes minimal setting for Lenticularis-S3 (Lens3).

| ![lens3-setting](lens3-setting.svg) |
|:--:|
| **Fig. Lens3 overview.** |

The steps are:
* Prepare prerequisite software and install Lens3
* Set up a (reverse) proxy
* Start Redis
* Start Lens3-Mux (a Multiplexer service)
* Start Lens3-Api (a Web-API service)
* Register users

## Assumptions

Lens3 needs a couple of services as depicted in the configuration
figure above.  A (reverse) proxy can be any server, but Apache HTTP
Server is used in this setting.  A key-value database server, Redis,
runs at port=6378.  Lens3-Mux and Lens3-Api are Lens3 services, and
they run at port=8003 and port=8004.  The proxy is set up to forward
requests to Lens3-Mux and Lens3-Api.

A pseudo user "lens3" is the owner of the services, who is given a
privilege of a "sudoers".  An optional second pseudo user
"lens3-admin" represents an administrator, anyone who can can access
Lens3 package and a configuration file.

We assume RedHat/Rocky 8.8 and Python 3.9 at this writing (in June
2023).

* Services
  * HTTP Proxy (port=433)
  * Redis (port=6378)
  * Lens3-Mux (port=8003)
  * Lens3-Api (port=8004)

* User IDs
  * `lens3:lens3` -- a pseudo user for services
  * `lens3-admin:lens3` -- a pseudo administrator user
  * `httpd` or `nginx`

* Files and directories
  * /usr/lib/systemd/system/lenticularis-api.service
  * /usr/lib/systemd/system/lenticularis-mux.service
  * /usr/lib/systemd/system/lenticularis-redis.service
  * /etc/lenticularis/conf.json
  * /etc/lenticularis/redis.conf
  * /run/lenticularis-redis (temporary)
  * /etc/httpd/
  * /etc/nginx/conf.d/lens3proxy.conf
  * /etc/nginx/private/htpasswd

* Software
  * RedHat/Rocky 8.8
  * Python 3.9
  * git

## Install Prerequisites

Install "Python", "Redis", and "Development-Tools" onto the host.
("Development-Tools" may not be necessary).

```
# dnf groupinstall "Development Tools"
# dnf install python39
# dnf install redis
```

Ensure using Python3.9, if necessary.

```
# update-alternatives --config python3
```

Install a proxy, Apache or NGINX.

```
# dnf install httpd mod_ssl mod_proxy_html
# dnf install mod_auth_openidc
```

Or,

```
# dnf install nginx
# dnf install httpd-tools
```

## Install Lens3

Note "$TOP" in the following refers to the top directory in the
downloaded Lens3 package.

Make a pseudo-user for the services.  UID/GID will be selected from a
lower range below 1000 that won't conflict with users.  Most of the
installation is done by the user "lens3".  Fix its umask appropriately
such as by `umask 022`.

```
# useradd -K UID_MIN=300 -K UID_MAX=499 -U -d /home/lens3 lens3
```

Download MinIO binaries "minio" and "mc" from min.io, then fix the
file permission.

```
# su - lens3
lens3$ cd ~
lens3$ mkdir bin
lens3$ curl https://dl.min.io/server/minio/release/linux-amd64/minio -o /tmp/minio
lens3$ install -m 755 -c /tmp/minio ~/bin/minio
lens3$ curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /tmp/mc
lens3$ install -m 755 -c /tmp/mc ~/bin/mc
```

Install Lens3 and Python packages.  Installation should be run in the
"$TOP/v1" directory.  Run `make install` in the "$TOP/v1" directory
does the same work.

```
# su - lens3
lens3$ cd $TOP/v1
lens3$ pip3 install --user -r requirements.txt
lens3$ ls ~/.local/lib/python3.9/site-packages/lenticularis
```

## Prepare a Log File Directory

Create a directory for logging.  It is expected the directory has the
security attributes "system_u:object_r:tmp_t:s0".

```
# mkdir /var/log/lenticularis
# chown lens3:lens3 /var/log/lenticularis
# chmod 700 /var/log/lenticularis
# chcon -u system_u -t tmp_t /var/log/lenticularis
# ls -dlZ /var/log/lenticularis
```

## Enable http Connections

Let SELinux accept connections inside a local host.

```
# semanage port -a -t http_port_t -p tcp 8003
# semanage port -a -t http_port_t -p tcp 8004
# semanage port -a -t redis_port_t -p tcp 6378
# semanage port --list
# setsebool -P httpd_can_network_connect 1
```

Modify the firewall to accept connection to port=443.

```
# firewall-cmd --state
# firewall-cmd --list-all
# firewall-cmd --zone=public --add-port=443/tcp --permanent
# firewall-cmd --reload
```

## Set up an HTTP Proxy

It is highly site dependent.

### Required Headers

Lens3-Api requires {"X-Remote-User"}, which holds an authenticated
user claim.  Lens3-Api trusts the "X-Remote-User" header passed by the
proxy.  Make sure the header is properly prepared by the proxy.

The following headers are passed to the Lens3-Mux and Lens3-Api by the
proxy.  Lens3-Mux requires {"Host", "X-Forwarded-For",
"X-Forwarded-Host", "X-Forwarded-Server", "X-Forwarded-Proto",
"X-Real-IP"}.  "Connection" (for keep-alive) is forced unset for
Lens3-Mux.  These are all practically standard headers.

Note {"X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Server"} are
implicitly set by Apache proxy.

### Proxy Path Choices

A path, "location" or "proxypass", should be "/" for Lens3-Mux,
because a path cannot be specified for S3 service.  If Lens3-Mux and
Lens3-Api are co-hosted, the Lens3-Mux path should be "/" and the
Lens3-Api path should be something like "/lens3.api/" that is NOT
legitimate bucket names.  We will use "lens3.api" in the following.

Please refer to the note on running MinIO with a proxy, saying: "The
S3 API signature calculation algorithm does not support proxy schemes
... on a subpath".  See the bottom of the following page:

[Configure NGINX Proxy for MinIO
Server](https://min.io/docs/minio/linux/integrations/setup-nginx-proxy-with-minio.html).

### Proxy by Apache

Set up a configuration file with needed authentication, and (re)start
the service.

Prepare a configuration file in "/etc/httpd/conf.d/" Sample files can
be found in $TOP/apache/.  Copy one as
"/etc/httpd/conf.d/lens3proxy.conf" and edit it.

```
# cp $TOP/apache/lens3proxy-basic.conf /etc/httpd/conf.d/lens3proxy.conf
# vi /etc/httpd/conf.d/lens3proxy.conf
# chown apache:apache /etc/httpd/conf.d/lens3proxy.conf
# chmod 660 /etc/httpd/conf.d/lens3proxy.conf
# chcon -u system_u -u system_u /etc/httpd/conf.d/lens3proxy.conf
# ls -lZ /etc/httpd/conf.d/lens3proxy.conf
```

Hints for setting: Since a proxy forwards directory accesses to
Lens3-Api, a trailing slash is necessary (in both the pattern part and
the URL part as noted in the Apache documents).  As a result, accesses
by `https://lens3.exmaple.com/lens3.api` (without a slash) will fail.

```
ProxyPass /lens3.api/ http://localhost:8004/
ProxyPassReverse /lens3.api/ http://localhost:8004/
```

For OIDC (OpenID Connect) authentication, there is a good tutorial for
setting Apache with Keyclock -- "3. Configure OnDemand to authenticate
with Keycloak".  See below.

[https://osc.github.io/ood-documentation/.../install_mod_auth_openidc.html](https://osc.github.io/ood-documentation/latest/authentication/tutorial-oidc-keycloak-rhel7/install_mod_auth_openidc.html)

#### Other Settings for Apache (Tips)

To add a cert for Apache, copy the cert and edit the configuration
file.  Change the lines of crt and key in "/etc/httpd/conf.d/ssl.conf".

```
# cp lens3.crt /etc/pki/tls/certs/lens3.crt
# cp lens3.key /etc/pki/tls/private/lens3.key
# chown apache:apache /etc/pki/tls/private/lens3.key
# chmod 400 /etc/pki/tls/private/lens3.key
# vi /etc/httpd/conf.d/ssl.conf
> SSLCertificateFile /etc/pki/tls/certs/lens3.crt
> SSLCertificateKeyFile /etc/pki/tls/private/lens3.key
```

### Proxy by NGINX

The following example is for basic authentication.  First, prepare a
configuration file in "/etc/nginx/conf.d/" maybe by copying a sample
file in $TOP/nginx/.

```
# cp $TOP/nginx/lens3proxy-basic.conf /etc/nginx/conf.d/lens3proxy.conf
# vi /etc/nginx/conf.d/lens3proxy.conf
```

Prepare password for basic authentication.

```
# mkdir /etc/nginx/private
# touch /etc/nginx/private/htpasswd
# htpasswd -b /etc/nginx/private/htpasswd user pass
# chown nginx:nginx /etc/nginx/private
# chmod 660 /etc/nginx/private
# chown nginx:nginx /etc/nginx/private/htpasswd
# chmod 660 /etc/nginx/private/htpasswd
```

Stop/start NGINX during configuration changes.

```
# systemctl stop nginx
......
# systemctl enable nginx
# systemctl start nginx
```

### A Note about NGINX parameters

NGINX has a parameter of the limit "client_max_body_size"
(default=1MB).  The default value is too small.  The size "10M" seems
adequate or "0" which means unlimited may also be adequate.

```
server {
    client_max_body_size 10M;
}
```

"client_max_body_size" limits the payload.  On the other hand, AWS S3
CLI has parameters for file transfers "multipart_threshold"
(default=8MB) and "multipart_chunksize" (default=8MB).  Especially,
"multipart_chunksize" has the minimum 5MB.

It is recommended to check the limits of a proxy when encountering a
413 error (Request Entity Too Large).

NGINX parameters are specified in the server section (or in the http
section).  Refer to "lens3proxy.conf".  The "client_max_body_size" is
defined in ngx_http_core_module.  See for the NGINX
ngx_http_core_module parameters:
[https://nginx.org/en/docs/http/ngx_http_core_module.html](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)

See for the AWS S3 CLI parameters:
[https://docs.aws.amazon.com/cli/latest/topic/s3-config.html](https://docs.aws.amazon.com/cli/latest/topic/s3-config.html).

## Start Redis

Lens3 uses a separate Redis instance running at port=6378.

Prepare a configuration file as "/etc/lenticularis/redis.conf".
Change the owner and edit the fields.  Note starting Redis will fail
when the owner of /etc/lenticularis/redis.conf is not "lens3".

* bind: Network interfaces; localhost by default
* port: A port for Redis
* requirepass: A passhprase for Redis

```
# mkdir /etc/lenticularis
# cp $TOP/unit-file/redis/redis.conf /etc/lenticularis/redis.conf
# vi /etc/lenticularis/redis.conf
# chown lens3:lens3 /etc/lenticularis/redis.conf
# chmod 660 /etc/lenticularis/redis.conf
```

Prepare a systemd unit file for Redis, and start/restart Redis.

```
# cp $TOP/unit-file/redis/lenticularis-redis.service /usr/lib/systemd/system/
# systemctl daemon-reload
# systemctl enable lenticularis-redis
# systemctl start lenticularis-redis
```

Lens3-Mux and Lens3-Api connect to Redis using the information held in
"/etc/lenticularis/conf.json".  Copy and edit a Lens3 configuration
file.

```
# cp $TOP/unit-file/conf.json /etc/lenticularis/conf.json
# vi /etc/lenticularis/conf.json
# chown lens3:lens3 /etc/lenticularis/conf.json
# chmod 660 /etc/lenticularis/conf.json
```

## Store Settings in Redis

Lens3-Mux and Lens3-Api load the configuration from Redis.  This
section prepares it.  It is better to run `lens3-admin` on the same
host running Redis.  See the following descriptions of the fields of
the configurations.

* [mux-conf-yaml.md](mux-conf-yaml.md)
* [api-conf-yaml.md](api-conf-yaml.md)

Make the configurations in files, then load them in Redis.  Note
`lens3-admin` needs "conf.json" containing connection information to
Redis.  Keep "conf.json" secure.

```
# su - lens3
lens3$ cd ~
lens3$ cp $TOP/unit-file/api-conf.yaml api-conf.yaml
lens3$ cp $TOP/unit-file/mux-conf.yaml mux-conf.yaml
lens3$ vi api-conf.yaml
lens3$ vi mux-conf.yaml
```

* Load the Lens3 configuration from files

```
# cp /etc/lenticularis/conf.json /home/lens3/conf.json
# chown lens3 /home/lens3/conf.json
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
lens3$ lens3-admin -c conf.json list-user
```

(Optionally) Prepare a list of users enabled to access.  An entry is a
"ENABLE" prefix and a list of uid's

```
ENABLE,user1,user2,user3, ...
```

Register an enabled-user list by `lens3-admin` command.

```
lens3$ lens3-admin -c conf.json load-user {csv-file}
lens3$ lens3-admin -c conf.json list-user
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
`http://lens3.example.com/lens3.api/`

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
case, it will help to connect to MinIO with "mc" command.  The
necessary information to use "mc" command, especially ACCESSKEY and
SECRETKEY, can be taken by "show-minio" command of "lens3-admin".  The
command is only useful when a MinIO instance is running.

```
lens3$ lens3-admin -c conf.json show-minio POOLID
lens3$ lens3-admin -c conf.json access-mux POOLID
```

Running "show-minio" displays the information under the keys "admin"
and "password", where admin corresponds to ACCESSKEY and password to
SECRETKEY.  Running "access-mux" periodically keeps the MinIO instance
alive, otherwise it will stop after a while.

As an example, the following commands can be used to dump tracing logs
from MinIO.

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
