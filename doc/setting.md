# Setup of Lenticularis-S3 (Minimal)

## Outline

This document describes minimal setting for Lenticularis-S3 (Lens3).

```
reverse-proxy <-->︎ Mux (Multiplexer) <--> MinIO
                                     <--> MinIO
                                     <--> ...
                                     <--> MinIO
              <--> Api (Setting Web-UI)
                   Redis
```

The steps are:
* Prepare prerequisite software and install Lens3
* Setup a reverse-proxy
* Start Redis
* Start Mux (a Multiplexer service)
* Start Api (a Web-UI service)
* Register users

## Assumptions

Some services are needed to use Lens3 as shown in the configuration
figure above.  In this setup, we assume Nginx as a reverse-proxy.  Mux
and Api are Gunicorn services, and we assume Mux runs at port=8004 and
Api at port=8003.  A reverse-proxy should be setup for Mux and Api
ports.  In addition, Redis is needed and Redis runs at port=6378.  A
pseudo user "lens3" is used for the owner of the daemons/services.  We
also assume RedHat8.5 and Python3.9 at this writing (in March 2022).

* Python
  * 3.9 and later

* Services used
  * Lenticularis Mux
  * Lenticularis Api
  * Redis (port=6378)
  * Reverse-proxy

* Related user IDs
  * `nginx`
  * `lens3:lens3` -- a pseudo user for services
  * `lens3-admin:lens3` -- a pseudo user for administration

* Used files and directories
  * /usr/lib/systemd/system/lenticularis-api.service
  * /usr/lib/systemd/system/lenticularis-mux.service
  * /usr/lib/systemd/system/lenticularis-redis.service
  * /etc/lenticularis/api-config.yaml
  * /etc/lenticularis/mux-config.yaml
  * /etc/lenticularis/redis.conf
  * /etc/nginx/conf.d/lens3proxy.conf
  * /etc/nginx/private/htpasswd
  * /run/lenticularis-redis (temporary)

## Setup Pseudo-users for Services

```
# groupadd -K GID_MIN=100 -K GID_MAX=499 lens3
# useradd -m -K UID_MIN=100 -K UID_MAX=499 -g lens3 lens3
# useradd -m -U lens3-admin
# usermod -a -G lens3 lens3-admin
```

## Install Prerequisite Software

Install packages Development-Tools, Redis, Python, and Nginx onto the
hosts.  httpd-tools is only required if you use basic authentication.

```
# dnf groupinstall "Development Tools"
# dnf install redis
# dnf install python39
# dnf install nginx
# dnf install httpd-tools
```

Install Python packages.

* Do as the user "lens3"

```
# su - lens3
$ cd $TOP
$ pip3 install --user -r requirements.txt
```

<!-- # su lens3-admin -c "pip3 install -r python-packages.txt --user" -->

Install MinIO binaries minio and mc from min.io.

* Download files as the user "lens3"

```
$ cd ~
$ mkdir bin
$ curl https://dl.min.io/server/minio/release/linux-amd64/minio -o /tmp/minio
$ install -m 755 -c /tmp/minio ~/bin/minio
$ curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /tmp/mc
# install -m 755 -c /tmp/mc ~/bin/mc
```

## Prepare a Log-file Directory

* Create a directory for logging (as root)

```
# mkdir /var/tmp/lenticularis
# chown lens3:lens3 /var/tmp/lenticularis
# chcon -u system_u -t tmp_t /var/tmp/lenticularis
# ls -dlZ /var/tmp/lenticularis
```

It is expected ls will show ... "system_u:object_r:tmp_t:s0".

## Enable Local http Connections

* Let SELinux accept connections inside a local host

```
# semanage port -a -t http_port_t -p tcp 8003
# semanage port -a -t http_port_t -p tcp 8004
# semanage port -a -t redis_port_t -p tcp 6378
# semanage port --list
# setsebool -P httpd_can_network_connect 1
```

## Start a Reverse-proxy (Nginx)

It is highly site dependent.

* Copy a configuration file to /etc/nginx/conf.d/
  * A sample file is in $TOP/nginx/lens3proxy.conf
  * Copy it as /etc/nginx/conf.d/lens3proxy.conf
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

* Stop/start Nginx during configuration changes

```
# systemctl stop nginx
......
# systemctl enable nginx
# systemctl start nginx
```

* Let the firewall pass HTTP connections

<!--
```
# apt-get install apache2-utils
# firewall-cmd --permanent --add-service=https
# firewall-cmd --reload
```
-->

### A Note about Nginx parameters

Nginx has a parameter of the limit "client_max_body_size"
(default=1MB).  The default value is too small.  The size "10M" seems
adequate or "0" which means unlimited may also be adequate.

```
server {
    client_max_body_size 10M;
}
```

"client_max_body_size" limits the payload.  On the other hand, AWS S3
CLI has parameters for file transfers, "multipart_threshold"
(default=8MB) and "multipart_chunksize" (default=8MB).  Especially,
"multipart_chunksize" has the minimum 5MB.  Nginx parameters are
specified in the server section (or in the http section).  Refer to
"lens3proxy.conf".

It is recommended to check the limits of the reverse-proxy, when
encountering the 413 error (Request Entity Too Large).

The "client_max_body_size" is defined in ngx_http_core_module.  See
for Nginx ngx_http_core_module parameters:
[https://nginx.org/en/docs/http/ngx_http_core_module.html](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size)

See for AWS S3 CLI parameters:
[https://docs.aws.amazon.com/cli/latest/topic/s3-config.html](https://docs.aws.amazon.com/cli/latest/topic/s3-config.html).

## Setup  Redis

* Copy the Redis configuration file
  * Configuration file is: `/etc/lenticularis/redis.conf`
* Change the fields of redis.conf.
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

## Setup Api (Web-UI)

* Copy the Api configuration file
  * Configuration file is: `/etc/lenticularis/api-config.yaml`
  * Modify it
  * See [api-config-yaml.md](api-config-yaml.md) for the fields
  * (Use a random for CSRF_secret_key)

```
# mkdir -p /etc/lenticularis
# cp $TOP/unit-file/api/api-config.yaml.in /etc/lenticularis/api-config.yaml
# vi /etc/lenticularis/api-config.yaml
# chown lens3:lens3 /etc/lenticularis/api-config.yaml
# chmod o-rwx /etc/lenticularis/api-config.yaml
```

* Copy the systemd unit file for Api

```
# cp $TOP/unit-file/api/lenticularis-api.service /usr/lib/systemd/system/
```

* Modify it if necessary

## Setup sudoers for Mux

Lens3 runs MinIO as a usual user process, and thus, it uses sudo to
start MinIO.  The provided example setting is that the user "lens3" is
only allowed to run "/home/lens3/bin/minio".

* Copy a sudoers entry in /etc/sudoers.d
  * Modify it if necessary

```
# cp $TOP/unit-file/mux/lenticularis-sudoers /etc/sudoers.d/
# chmod -w /etc/sudoers.d/lenticularis-sudoers
# chmod o-rwx /etc/sudoers.d/lenticularis-sudoers
```

## Setup Mux (Multiplexer)

* Copy the Mux configuration file
  * Configuration file is: `/etc/lenticularis/mux-config.yaml`
  * Modify it
  * See [mux-config-yaml.md](mux-config-yaml.md) for the fields

```
# mkdir -p /etc/lenticularis/
# cp $TOP/unit-file/mux/mux-config.yaml.in /etc/lenticularis/mux-config.yaml
# vi /etc/lenticularis/mux-config.yaml
# chown lens3:lens3 /etc/lenticularis/mux-config.yaml
# chmod o-rwx /etc/lenticularis/mux-config.yaml
```

* Copy the systemd unit file for Mux
  * Modify it if necessary

```
# cp $TOP/unit-file/mux/lenticularis-mux.service /usr/lib/systemd/system/
```

## Start Services (Mux and Api)

```
# systemctl daemon-reload
# systemctl enable lenticularis-mux
# systemctl start lenticularis-mux
# systemctl enable lenticularis-api
# systemctl start lenticularis-api
```

## Register Users

Lens3 has its own a list of users (with uid + gid) and a list of
enablement status of the users.  It does not look at the databases of
the underlying OS whereas it uses uid + gid of the system.

See [Administration Guide](admin-guide.md#).

* Prepare a list of users in a CSV file
  * An entry is a user name and a list of groups

```
ADD,user1,group1a,group1b,group1c, ...
ADD,user2,group2a,group2b,group2c, ...
...
```

* Register users to Lens3 by `lenticularis-admin` command

```
lens3-admin$ lenticularis-admin -c api-config.yaml load-user {csv-file}
lens3-admin$ lenticularis-admin -c api-config.yaml list-user
```

* (Optionally) Prepare a list of users enabled to access
  * An entry is a "enable" prefix and a list of user names

```
ENABLE,user1,user2,user3, ...
```

* Register permit-list to Lens3 by `lenticularis-admin` command.

```
lens3-admin$ lenticularis-admin -c api-config.yaml load-permit {csv-file}
lens3-admin$ lenticularis-admin -c api-config.yaml list-permit
```

## Check the Status

* Nginx status

```
$ systemctl status nginx
```

*  Redis status

```
$ systemctl status lenticularis-redis
```

* Mux (Multiplexer) status

```
$ systemctl status lenticularis-mux
lens3-admin$ lenticularis-admin -c api-config.yaml show-muxs
```

* Api (Web-UI) status

```
$ systemctl status lenticularis-api
```

## Test Accesses

* Access the website by a browser
  * `http://webui.lens3.example.com/`

* Access buckets from S3 client
    * Copy the access keys created above
    * List files in the bucket
    * Cat contents of a file

```
$ vi $HOME/.aws/credentials
[default]
aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO

$ aws --endpoint-url https://lens3.example.com s3 ls s3://bkt1
$ aws --endpoint-url https://lens3.example.com s3 cp s3://bkt1/somefile1 -
```

Note that Lens3 does not support listing of buckets by `aws s3 ls`.
