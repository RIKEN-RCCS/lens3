# Setup Lenticularis-S3 (Minimal)

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

Some services are needed to run Lens3 as depicted in the configuration
figure above.  In this setup, we assume NGINX as a (reverse) proxy.
Lens3-Mux and Lens3-Api are Gunicorn services, and we assume Lens3-Mux
runs at port=8004 and Lens3-Api at port=8003.  A proxy should be set
up for Mux and Api ports.  In addition, Redis is needed running at
port=6378.  A pseudo user "lens3" is the owner of the
daemons/services.  Also, "lens3-admin" sometimes represents an
administrator, anyone who can access the configuration files.  We
assume RedHat8.5 and Python3.9 at this writing (in May 2023).

* Python
  * 3.9 and later

* Services used
  * Lenticularis Lens3-Mux
  * Lenticularis Lens3-Api
  * Redis (port=6378)
  * proxy

* Related user IDs
  * `nginx`
  * `lens3:lens3` -- a pseudo user for services
  * `lens3-admin:lens3` -- a pseudo administrator user

* Used files and directories
  * /usr/lib/systemd/system/lenticularis-api.service
  * /usr/lib/systemd/system/lenticularis-mux.service
  * /usr/lib/systemd/system/lenticularis-redis.service
  * /etc/lenticularis/conf.json
  * /etc/lenticularis/redis.conf
  * /run/lenticularis-redis (temporary)
  * /etc/nginx/conf.d/lens3proxy.conf
  * /etc/nginx/private/htpasswd

## Set up Pseudo-users for Services

```
# groupadd -K GID_MIN=100 -K GID_MAX=499 lens3
# useradd -m -K UID_MIN=100 -K UID_MAX=499 -g lens3 lens3
```

## Install Prerequisites

Install packages Development-Tools, Redis, and Python onto the
hosts.

```
# dnf groupinstall "Development Tools"
# dnf install python39
# dnf install redis
```

Install MinIO binaries minio and mc from min.io.

* Download files as the user "lens3"

```
# su - lens3
$ cd ~
$ mkdir bin
$ curl https://dl.min.io/server/minio/release/linux-amd64/minio -o /tmp/minio
$ install -m 755 -c /tmp/minio ~/bin/minio
$ curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /tmp/mc
# install -m 755 -c /tmp/mc ~/bin/mc
```

## Install Lens3

Install Python packages and Lens3.  Installation should be run in the
"v1" directory.

* Run as the user "lens3"

```
# su - lens3
$ cd $TOP/v1
$ pip3 install --user -r requirements.txt
```

Or, run `make install` in the "v1" directory.

## Prepare a Log-file Directory

* Create a directory for logging

```
# mkdir /var/tmp/lenticularis
# chown lens3:lens3 /var/tmp/lenticularis
# chcon -u system_u -t tmp_t /var/tmp/lenticularis
# ls -dlZ /var/tmp/lenticularis
```

It is expected the directory has the security attributes
"system_u:object_r:tmp_t:s0".

## Enable Local http Connections

* Let SELinux accept connections inside a local host

```
# semanage port -a -t http_port_t -p tcp 8003
# semanage port -a -t http_port_t -p tcp 8004
# semanage port -a -t redis_port_t -p tcp 6378
# semanage port --list
# setsebool -P httpd_can_network_connect 1
```

## Start a Proxy

It is highly site dependent.

### Required Headers

Lens3-Api requires {"X-Remote-User"}, which holds an authenticated
user claim.  Lens3-Api trusts the "X-Remote-User" header passed by a
proxy.  Make sure the header is properly prepared by a proxy and not
faked.

The following headers are passed to the Lens3-Mux and Lens3-Api by a
proxy.  Lens3-Mux requires {"Host", "X-Forwarded-For",
"X-Forwarded-Host", "X-Forwarded-Server", "X-Forwarded-Proto",
"X-Real-IP"}.  "Connection" (for keep-alive) is forced unset for
Lens3-Mux.  These are all practically standard headers.

Note {"X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Server"} are
implicitly set by an Apache proxy.

### Proxy by NGINX

Install NGINX.  The following example uses basic authentication.

```
# dnf install nginx
# dnf install httpd-tools
```

* Prepare a configuration file in /etc/nginx/conf.d/
  * Sample files are in $TOP/nginx/
  * Copy one as /etc/nginx/conf.d/lens3proxy.conf
  * Edit it

```
# cp $TOP/nginx/lens3proxy.conf /etc/nginx/conf.d/
# vi /etc/nginx/conf.d/lens3proxy.conf
```

* Prepare password for basic authentication

```
# mkdir /etc/nginx/private
# touch /etc/nginx/private/htpasswd
# htpasswd -b /etc/nginx/private/htpasswd user pass
# chown nginx:nginx /etc/nginx/private
# chmod og-rwx /etc/nginx/private
# chown nginx:nginx /etc/nginx/private/htpasswd
# chmod og-rwx /etc/nginx/private/htpasswd
```

* Stop/start NGINX during configuration changes

```
# systemctl stop nginx
......
# systemctl enable nginx
# systemctl start nginx
```

* Let the firewall pass HTTP connections

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

### Proxy by Apache

The steps are similar to the NGINX case.  Set up a configuration file
with needed authentication, and (re)start a service.  Note here we
assume Redhat variant Linux.

Install Apache.

```
# dnf install httpd mod_proxy_html
# dnf install mod_auth_openidc
# dnf install httpd-tools
```

* Prepare a configuration file in /etc/httpd/conf.d/
  * Sample files are in $TOP/apache/
  * Copy one as /etc/httpd/conf.d/lens3proxy.conf
  * Edit it

```
# cp $TOP/apache/lens3proxy80.conf /etc/httpd/conf.d/lens3proxy.conf
# vi /etc/httpd/conf.d/lens3proxy.conf
# chcon -u system_u -u system_u /etc/httpd/conf.d/lens3proxy.conf
# chown apache:apache /etc/httpd/conf.d/lens3proxy.conf
# chmod og-rwx /etc/httpd/conf.d/lens3proxy.conf
# ls -lZ /etc/httpd/conf.d/lens3proxy.conf
```

Hints for setting: Since a proxy forwards directory accesses to
Lens3-Api, a trailing slash is necessary (in both the pattern part and
the URL part as noted in the Apache documents).  As a result, accesses
by `https://lens3.exmaple.com/api` (without a slash) will fail.

```
ProxyPass /api/ http://localhost:8003/
ProxyPassReverse /api/ http://localhost:8003/
```

## Set up Redis

* Copy the Redis configuration file
  * Configuration file is: `/etc/lenticularis/redis.conf`
* Edit the fields of redis.conf.
  * bind: Network interfaces; localhost by default
  * port: A port for Redis
  * requirepass: A passhprase for Redis
* Change the owner of redis.conf

Note: Starting Redis will fail when the file owner of
/etc/lenticularis/redis.conf is not "lens3".

```
# mkdir -p /etc/lenticularis
# cp $TOP/unit-file/redis/redis.conf /etc/lenticularis/redis.conf
# vi /etc/lenticularis/redis.conf
# chown lens3:lens3 /etc/lenticularis/redis.conf
# chmod o-rwx /etc/lenticularis/redis.conf
```

* Copy the systemd unit file for Redis, and start/restart Redis

```
# cp $TOP/unit-file/redis/lenticularis-redis.service /usr/lib/systemd/system/
# systemctl daemon-reload
# systemctl enable lenticularis-redis
# systemctl start lenticularis-redis
```

* Copy and edit a Lens3 configuration file.  It shoul hold a Redis
  connection information.

```
# cp $TOP/unit-file/conf.json /etc/lenticularis/conf.json
# vi /etc/lenticularis/conf.json
# chown lens3:lens3 /etc/lenticularis/conf.json
# chmod o-rwx /etc/lenticularis/conf.json
```

## Set up Lens3-Api and Lens3-Mux

* Copy (and edit) the systemd unit file for Lens3-Api

```
# cp $TOP/unit-file/api/lenticularis-api.service /usr/lib/systemd/system/
```

* Copy (and edit) the systemd unit file for Lens3-Mux

```
# cp $TOP/unit-file/mux/lenticularis-mux.service /usr/lib/systemd/system/
```

## Set up sudoers for Lens3-Mux

Lens3 runs MinIO as a non-root process, and thus, it uses sudo to
start MinIO.  The provided example setting is that the user "lens3" is
only allowed to run "/home/lens3/bin/minio".

* Copy and edit a sudoers entry in /etc/sudoers.d

```
# cp $TOP/unit-file/mux/lenticularis-sudoers /etc/sudoers.d/
# vi /etc/sudoers.d/lenticularis-sudoers
# chmod -w /etc/sudoers.d/lenticularis-sudoers
# chmod o-rwx /etc/sudoers.d/lenticularis-sudoers
```

## Load Settings to Redis

Lens3-Mux and Lens3-Api load configurations from Redis.  This section
prepares for it.  See [mux-conf-yaml.md](mux-conf-yaml.md) and
[api-conf-yaml.md](api-conf-yaml.md) for the description of the
fields.  Probably, it is better to run `lens3-admin` on the same node
running Lens3-Api.

* Prepare the Lens3-Api configuration from files somewhere
  * Copy and edit configuration files
  * (Use a random for CSRF_secret_key)

```
# cp /etc/lenticularis/conf.json /home/lens3/conf.json
# chown lens3-admin /home/lens3/conf.json
# su - lens3
$ cd ~
lens3$ cp $TOP/unit-file/api/api-conf.yaml api-conf.yaml
lens3$ cp $TOP/unit-file/mux/mux-conf.yaml mux-conf.yaml
lens3$ vi api-conf.yaml
lens3$ vi mux-conf.yaml
```

* Load the Lens3 configuration from files

```
lens3$ lens3-admin -c conf.json load-conf api-conf.yaml
lens3$ lens3-admin -c conf.json load-conf mux-conf.yaml
lens3$ lens3-admin -c conf.json list-conf
```

## Start Services (Lens3-Mux and Lens3-Api)

Lens3-Mux and Lens3-Api will be started as a system service with
uid:gid="lens3":"lens3".

```
# systemctl daemon-reload
# systemctl enable lenticularis-mux
# systemctl start lenticularis-mux
# systemctl enable lenticularis-api
# systemctl start lenticularis-api
```

## Register Users

Lens3 has its own a list of users (with uid+gid) and a list of
enablement status of the users.  It does not look at the databases of
the underlying system whereas it uses uid+gid of the system.

See [Administration Guide](admin-guide.md#).

Lens3 stores user information from a CSV file.  An entry in CSV is a
"ADD" keyword, a uid, a (maybe empty) claim string, and a list of
groups

* Prepare a list of users in a CSV file.

```
ADD,user1,,group1a,group1b,group1c, ...
ADD,user2,,group2a,group2b,group2c, ...
...
```

* Register users by `lens3-admin` command

```
lens3$ lens3-admin -c conf.json load-user {csv-file}
lens3$ lens3-admin -c conf.json list-user
```

* (Optionally) Prepare a list of users enabled to access
  * An entry is a "enable" prefix and a list of uid's

```
ENABLE,user1,user2,user3, ...
```

* Register an enabled-user list by `lens3-admin` command

```
lens3$ lens3-admin -c conf.json load-user {csv-file}
lens3$ lens3-admin -c conf.json list-user
```

## Check the Status

* NGINX status

```
$ systemctl status nginx
```

* Redis status

```
$ systemctl status lenticularis-redis
```

* Lens3-Mux status and Lens3-Api status

```
# systemctl status lenticularis-mux
# systemctl status lenticularis-api
# su - lens3
lens3$ cd ~
lens3$ lens3-admin -c conf.json show-muxs
```

## Test Accesses

* Access the website by a browser
  * `http://webui.lens3.example.com/`

* Access buckets from S3 client
    * Copy the access keys created above
    * List files in the bucket
    * Cat contents of a file

```
$ vi ~/.aws/config
[default]
s3 =
    signature_version = s3v4

$ vi $HOME/.aws/credentials
[default]
aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO

$ aws --endpoint-url https://lens3.example.com s3 ls s3://bkt1
$ aws --endpoint-url https://lens3.example.com s3 cp s3://bkt1/somefile1 -
```

Note that Lens3 does not support listing of buckets by `aws s3 ls`.

## Memo on Python Modules

"FastAPI" uses "Starlette".  There are no direct uses of "Starlette"
in the source code .
