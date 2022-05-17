# (Minimal) Setup of Lenticularis-S3

## Configuration

```
reverse-proxy <-->︎ multiplexer <--> MinIO
                               <--> MinIO
                               <--> MinIO
              <--> pool-manager (web-ui)
                   redis
```


## Assuption

Some number of services running for Lenticularis-S3 as shown in the
configuration section.  In this setup, we assume Nginx as a
reverse-proxy, ....  A pseudo user "lens3" is used for the owner of
the daemons/services.  We also assume RedHat8.5 and Python3.9 at this
writing (in March 2022).

* Python
  * 3.9 and later

* Services used
  * Lenticularis Multiplexers
  * Lenticularis Web-UI
  * Redis (port=6378)
  * Reverse-proxy

* Related user IDs
  * `nginx`
  * `lens3:lens3` -- a pseudo user for daemons
  * `lens3-admin:lens3` -- a pseudo user for administraion

* Used files and directories
  * /usr/lib/systemd/system/lenticularis-adm.service
  * /usr/lib/systemd/system/lenticularis-mux.service
  * /usr/lib/systemd/system/lenticularis-redis.service
  * /etc/lenticularis/adm-config.yaml
  * /etc/lenticularis/mux-config.yaml
  * /etc/lenticularis/redis.conf
  * /etc/nginx/conf.d/lens3proxy.conf
  * /etc/nginx/private
  * /etc/nginx/private/htpasswd
  * /run/lenticularis-redis (temporary)

## Setup pseudo users for daemons

```
# groupadd -K GID_MIN=100 -K GID_MAX=499 lens3
# useradd -m -K UID_MIN=100 -K UID_MAX=499 -g lens3 lens3
# useradd -m -U lens3-admin
# usermod -a -G lens3 lens3-admin
```

## Install prerequisite software

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

* Do as "lens3"

```
# su - lens3
$ cd $TOP
$ pip3 install --user -r requirements.txt
```

<!-- # su lens3-admin -c "pip3 install -r python-packages.txt --user" -->

Install MinIO binaries minio and mc from min.io.

* Do as "lens3"

```
$ cd ~
$ mkdir bin
$ curl https://dl.min.io/server/minio/release/linux-amd64/minio -o /tmp/minio
$ install -m 755 -c /tmp/minio ~/bin/minio
$ curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /tmp/mc
# install -m 755 -c /tmp/mc ~/bin/mc
```

## Enable local http connections

* Let SELinux accept connections inside a local host.

```
# semanage port -a -t http_port_t -p tcp 8003
# semanage port -a -t http_port_t -p tcp 8004
# semanage port --list
# setsebool -P httpd_can_network_connect 1
```

## Start reverse-proxy

It is highly site dependent.
See [overview.md](overview.md).

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

* Start Nginx during configuration changes

```
# systemctl stop nginx
......
# systemctl enable nginx
# systemctl start nginx
```

    - Make firewall to pass HTTP connections
      ```
      # apt-get install apache2-utils
      # firewall-cmd --permanent --add-service=https
      # firewall-cmd --reload
      ```

## Start Redis

* Copy the Redis configuration file
  * Configuration file: `/etc/lenticularis/redis.conf`
* Change the fields of redis.conf.
  * bind: Network interfaces; localhost by default
  * port: A port for Redis
  * requirepass: A passhprase for Redis

```
# mkdir -p /etc/lenticularis
# cp $TOP/unit-file/redis/redis.conf /etc/lenticularis/redis.conf
# vi /etc/lenticularis/redis.conf
```

* Copy the systemd unit file for Redis

```
# cp $TOP/unit-file/redis/lenticularis-redis.service /usr/lib/systemd/system/
```

* Start/restart Redis

```
# systemctl daemon-reload
# systemctl enable lenticularis-redis
# systemctl start lenticularis-redis
```

* Note: Starting Redis will fail when the file owner of
  /etc/lenticularis/redis.conf is not "lens3".

## Setup Web-UI

* Copy the Web-UI configuration file
  * Configuration file: `/etc/lenticularis/adm-config.yaml`

```
# mkdir -p /etc/lenticularis
# cp $TOP/unit-file/adm/adm-config.yaml.in /etc/lenticularis/adm-config.yaml
# vi /etc/lenticularis/adm-config.yaml
# chown lens3:lens3 /etc/lenticularis/adm-config.yaml
# chmod o-rwx /etc/lenticularis/adm-config.yaml
```

* Modify it
  * See [adm-config-yaml.md](adm-config-yaml.md) for the fields
  * Replace placeholders: @REDIS_HOST@, @REDIS_PORT@, @REDIS_PASSWORD@
  * Replace placeholders: @DELEGATE_HOSTNAME@, @DIRECT_HOSTNAME_DOMAIN@, @RESERVED_HOSTNAME@
  * Replace placeholders: @FACILITY@, @PRIORITY@
  * Replace placeholders: @REVERSE_PROXY_ADDRESS@, @CSRF_SECRET_KEY@
  * (Use a random for CSRF_secret_key)

* Copy the systemd unit file for Web-UI

```
# cp $TOP/unit-file/adm/lenticularis-adm.service /usr/lib/systemd/system/
```

* Modify it if necessary
  * See the template `$TOP/unit-file/mux/lenticularis-adm.service.in`
  * Replace placeholders: @API_USER@, @ADM_CONFIG@

## Setup sudoers for Multiplexer

* Copy a sudoers entry in /etc/sudoers.d
  * Modify it if necessary

```
# cp $TOP/unit-file/mux/lenticularis-sudoers /etc/sudoers.d/
# chmod -w /etc/sudoers.d/lenticularis-sudoers
# chmod o-rwx /etc/sudoers.d/lenticularis-sudoers
```

## Setup Multiplexer

* Copy the Multiplexer configuration file
  * Configuration file: `/etc/lenticularis/mux-config.yaml`

```
# mkdir -p /etc/lenticularis/
# cp $TOP/multiplexer/mux-config.yaml.in /etc/lenticularis/mux-config.yaml
# vi /etc/lenticularis/mux-config.yaml
# chown lens3:lens3 /etc/lenticularis/mux-config.yaml
# chmod o-rwx /etc/lenticularis/mux-config.yaml
```

* Modify it
  * See [mux-config-yaml.md](mux-config-yaml.md) for the fields
  * Replace placeholders: @REDIS_HOST@, @REDIS_PORT@, @REDIS_PASSWORD@
  * Replace placeholders: @SERVER_PORT@, @DELEGATE_HOSTNAME@, @REVERSE_PROXY_ADDRESS@, @API_ADDRESS@
  * Replace placeholders: @PORT_MIN@, @PORT_MAX@, @MINIO@, @MINIO_HTTP_TRACE@, @MC@
  * Replace placeholders: @FACILITY@, @PRIORITY@

* Copy the systemd unit file for Multiplexer

```
# cp $TOP/unit-file/mux/lenticularis-mux.service /usr/lib/systemd/system/
```

* Modify it if necessary
  * See the template `$TOP/unit-file/mux/lenticularis-mux.service.in`
  * Replace placeholders: @MUX_USER@, @MUX_CONFIG@

## Start services (Web-UI and Muxiplexer)

```
# systemctl daemon-reload
# systemctl enable lenticularis-adm
# systemctl start lenticularis-adm
# systemctl enable lenticularis-mux
# systemctl start lenticularis-mux
```

## Register users

See [administrators-guide.md](administrators-guide.md#).

* Prepare a list of users in a CSV file
  * An entry is a user name and a list of groups

```
user1,group1a,group1b,group1c
user2,group2a
```

* Register user list to the system by `lenticularis-admin` command

```
lens3-admin$ lenticularis-admin insert user-info {csv-file}
lens3-admin$ lenticularis-admin show user-info
```

* Prepare a list of users allowed to access
  * An entry is a "allow" prefix and a list of user names

```
allow,user1,user2
```

* Register allow-deny-rule to the system by `lenticularis-admin` command.

```
lens3-admin$ lenticularis-admin insert allow-deny-rules {csv-file}
lens3-admin$ lenticularis-admin show allow-deny-rules --format=json
```

## Check the status

*  Redis status

```
$ systemctl status redis
```

* Nginx status

```
$ systemctl status nginx
```

* Web-UI status

```
$ systemctl status lenticularis-adm
```

* Multiplexer status

```
$ systemctl status lenticularis-mux.service
lens3-admin$ lenticularis-admin show multiplexer
```

## Access test

* Access website by a browser, and create a zone.
  * URL: `http://webui.lent8.example.com/`

* Access to the create zone by S3 client.
    * Use Access Key created above.

```
user$ cat <<EOF > $HOME/.aws/credentials
[user1]
aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO
EOF
user$ AWS_PROFILE=user1 ENDPOINT_URL=https://lent8.example.com \
aws s3 ls s3://
```

    - Access following website by Web Browser, again.
      - URL: `http://webui.lent8.example.com/`
      - Create public bucket

```
Public (download only for Access Key-less user): bucket2
```

      - Register direct hostname

```
Direct Hostname (label or FQDN): release.lent8.example.com
```

    - Back to client host.
      - Put an object into public bucket create above.

```
user$ tmpfile=$(mktemp)
user$ date > $tmpfile
user$ AWS_PROFILE=user1 ENDPOINT_URL=https://lent8.example.com \
user$ aws s3 cp $tmpfile s3://bucket2/foo
```

    - Try to access the public object via directHostname.

```
stranger$ ENDPOINT_URL=https://release.lent8.example.com
stranger$ curl -k $ENDPOINT_URL/bucket2/foo
```
