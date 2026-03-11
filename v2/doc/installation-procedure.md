# Lenticularis-S3 Installation Procedure

## Outline

This document describes initial setting for Lenticularis-S3 (Lens3).
It is what are performed by installing an RPM.  Further settings are
in [setting-guide.md](setting-guide.md).

The steps are:

  - Install Lens3
  - Prepare prerequisite software
  - Start Valkey
  - Start Lens3 service (lenticularis-mux)

## Summary of System Changes

Lens3 consists of a couple of services.  A reverse-proxy can be any
server, but Apache HTTP Server is used in this document.  A keyval-db
server, Valkey, runs at port=6378.  The Lens3 services, Multiplexer
and Registrar, run at port=8003 and port=8004, respectively.  The
proxy is set up to forward requests to Multiplexer and Registrar.

New user with sudo (a pseudo user for the services)
  - lenticularis:lenticularis (home at /var/lib/lenticularis)
  - /usr/lib/sysusers.d/lenticularis-user.conf
  - /etc/sudoers.d/lenticularis-sudoers

Firewall: services and thier ports
  - HTTP Proxy (port=443,80)
  - Valkey (port=6378)
  - Multiplexer (port=8003)
  - Registrar (port=8004)

Selinux: changes on files and ports
  - /var/log/lenticularis-valkey
  - TCP ports 8003, 8004, 6378

Files and directories
  - /usr/lib/sysusers.d/lenticularis-user.conf
  - /etc/sudoers.d/lenticularis-sudoers
  - /usr/lib/systemd/system/lenticularis-mux.service
  - /usr/lib/systemd/system/lenticularis-valkey.service
  - /etc/lenticularis/lens3.conf
  - /etc/lenticularis/valkey.conf
  - /var/lib/lenticularis/
  - /var/log/lenticularis/
  - /var/log/lenticularis-valkey/
  - /usr/local/bin/
  - /etc/httpd/
  - /run/lenticularis-valkey/ (temporary)

Software
  - httpd 2.4
  - Valkey 8
  - Mosquitto 2
  - logrotate 3
  - Golang
  - Git
  - Rocky Linux 10

__IT IS HIGHLY RECOMMENDED THE SERVER HOST IS NOT OPEN TO USERS__.

We assume Rocky 10.1 at this writing (in Mar 2026).

A pseudo user "lenticularis" is the owner of the services in this
document, who is given a privilege of sudoers.  Logs and Valkey-DB are
ownen by "lenticularis".

## Build and Install Lens3

Note "$TOP" in the following refers to the top directory in the
downloaded Lens3 package.

Install basic tools, first.  Install "Development-Tools" and "Golang"
onto the host.  Some tests in Lens3 use Python.

```
# dnf groupinstall "Development Tools"
# dnf install golang
# dnf install rpm-devel
```

Build and install Lens3.  Copy the binary files ("lenticularis-mux"
and "lenticularis-admin") to "/usr/local/bin".

```
$ cd $TOP/v2/
$ make get
$ make build
$ exit
# su -
# install -m 755 -c $TOP/v2/cmd/lenticularis-mux/lenticularis-mux /usr/local/bin/
# install -m 755 -c $TOP/v2/cmd/lenticularis-admin/lenticularis-admin /usr/local/bin/
```

Lens3 needs "s3-baby-server".  Install the binary in "/usr/local/bin".
"s3-baby-server" is a small AWS-S3 server, which is a separate
software and can be found in github.com:

  - https://github.com/RIKEN-RCCS/s3-baby-server

## Install Prerequisites

Install "Valkey".

```
# dnf install valkey
```

In earlier releases of Rocky Linux, Valkey may be in EPEL.  Then, add
EPEL to the repository list.

```
# dnf install epel-release
# dnf repolist
```

Install Apache-HTTPD with OpenID Connect (optional).

```
# dnf install httpd mod_ssl mod_proxy_html
# dnf install mod_auth_openidc
```

## Make Pseudo User

Make a pseudo user "lenticularis" for the services.  Most of the
installation is performed by "lenticularis".

When using systemd-sysusers, copy
"$TOP/v2/unit-file/lenticularis-user.conf" to "/usr/lib/sysusers.d/",
and run "systemd-sysusers".

```
systemd-sysusers
```

Or, create a user manaully.  Her UID/GID will be selected from the
lower range below 1000 that won't conflict with real users.  Fix her
umask appropriately such as by `umask 022`.

```
sudo useradd -K UID_MIN=301 -K UID_MAX=499 -K GID_MIN=301 -K GID_MAX=499 -U -d /home/lenticularis lenticularis
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
# chown lenticularis:lenticularis /var/log/lenticularis
# chmod 700 /var/log/lenticularis
# ls -dlZ /var/log/lenticularis
(* Check the context is with var_log_t on /var/log/lenticularis. *)

# mkdir /var/log/lenticularis-valkey
# chown lenticularis:lenticularis /var/log/lenticularis-valkey
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

## Start Valkey

Lens3 uses a separate Valkey instance running at port=6378 (not
well-known port=6379).

Prepare a configuration file as "/etc/lenticularis/valkey.conf".
Change the owner and edit the fields.  KEEP IT SECURE, because it
includes a password.  Starting Valkey will fail when the owner of
/etc/lenticularis/valkey.conf is not "lenticularis".  The
"requirepass" field needs be changed from the sample file.

Some of the fields:
- "bind": Network interfaces; localhost by default
- "port": A port for Valkey
- "requirepass": A passhprase for Valkey

```
# mkdir /etc/lenticularis
# cp $TOP/v2/unit-file/valkey.conf /etc/lenticularis/valkey.conf
# chown lenticularis:lenticularis /etc/lenticularis/valkey.conf
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
in "/etc/lenticularis/lens3.conf".  KEEP IT SECURE ALL THE TIME.  Copy
and edit the configuration file.  Set the Valkey's password in it.
Note that Lens3 stores everything in Valkey, including S3 access keys
which are stored in raw text.

```
# cp $TOP/v2/unit-file/lens3.conf /etc/lenticularis/lens3.conf
# chown lenticularis:lenticularis /etc/lenticularis/lens3.conf
# chmod 660 /etc/lenticularis/lens3.conf
# vi /etc/lenticularis/lens3.conf
```

## Store Lens3 Settings in Keyval-DB

Multiplexer and Registrar load the configuration from the keyval-db
(Valkey).  This section prepares it.  It is better to run
`lenticularis-admin` on the same host running the keyval-db.  See the
following description of the fields of the configurations.

- [configuration.md](configuration.md)

Make the configurations in files to load them in the keyval-db.

```
# su - lenticularis
lenticularis$ cd ~
lenticularis$ cp $TOP/v2/unit-file/mux-conf.json mux-conf.json
lenticularis$ cp $TOP/v2/unit-file/reg-conf.json reg-conf.json
lenticularis$ vi mux-conf.json
lenticularis$ vi reg-conf.json
```

Load the Lens3 configuration from the files.  Note
`lenticularis-admin` needs "lens3.conf" containing connection
information to the keyval-db.  Keep "lens3.conf" secure, when it is
necessary to copy it.

```
# cp /etc/lenticularis/lens3.conf ~lenticularis/lens3.conf
# chown lenticularis:lenticularis ~lenticularis/lens3.conf
# chmod 660 ~lenticularis/lens3.conf
# su - lenticularis
lenticularis$ cd ~
lenticularis$ lenticularis-admin -c ./lens3.conf load-conf mux-conf.json
lenticularis$ lenticularis-admin -c ./lens3.conf load-conf reg-conf.json
lenticularis$ lenticularis-admin -c ./lens3.conf show-conf
```

Check the syntax of json before loading the configuration.  It can be
checked by tools such as "jq".  "jq" is a command-line JSON processor.

```
lenticularis$ cat mux-conf.json | jq
lenticularis$ cat reg-conf.json | jq
```

We do not start the service, lenticularis-mux, yet.  But, in general,
restarting the service is needed after changing the configuration.
Run `systemctl restart lenticularis-mux`.

## Set up sudoers for Multiplexer

Lens3 runs an S3 backend server as a non-root process, and it uses
sudo for it.  Copy and edit an entry in
"/etc/sudoers.d/lenticularis-sudoers".  The provided example setting
is that the user "lenticularis" is only allowed to run
"/usr/local/bin/s3-baby-server" via sudo.

```
cp $TOP/v2/unit-file/lenticularis-sudoers /etc/sudoers.d/
vi /etc/sudoers.d/lenticularis-sudoers
chmod 440 /etc/sudoers.d/lenticularis-sudoers
```

## Start Multiplexer and Registrar Services

Multiplexer and Registrar are two threads in a single binary.  They
will be started as a system service as "lenticularis-mux".  Copy the
systemd unit file for the service.  It is started with the user
"lenticularis" (UID:GID=lenticularis:lenticularis).

```
cp $TOP/v2/unit-file/lenticularis-mux.service /usr/lib/systemd/system/
```

```
systemctl daemon-reload
systemctl enable lenticularis-mux
systemctl start lenticularis-mux
systemctl status lenticularis-mux
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

Lenticularis status:

```
# systemctl status lenticularis-mux
# su - lenticularis
lenticularis$ cd ~
lenticularis$ lenticularis-admin -c ./lens3.conf show-mux
```

The admin command `show-mux` shows the endpoints of Multiplexers.
Something goes wrong if it were empty.

## (Appendix) Installation of MinIO Binaries

### Download MinIO Binaries

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
# su - lenticularis
lenticularis$ cd /tmp
lenticularis$ wget https://dl.min.io/server/minio/release/linux-amd64/archive/minio-20220526054841.0.0.x86_64.rpm
lenticularis$ rpm2cpio minio-20220526054841.0.0.x86_64.rpm | cpio -id --no-absolute-filenames usr/local/bin/minio
lenticularis$ mv ./usr/local/bin/minio ./minio
lenticularis$ rm -r ./usr
lenticularis$ rm ./minio-20220526054841.0.0.x86_64.rpm
lenticularis$ wget https://dl.min.io/client/mc/release/linux-amd64/archive/mc.RELEASE.2022-06-10T22-29-12Z
lenticularis$ mv ./mc.RELEASE.2022-06-10T22-29-12Z ./mc
lenticularis$ exit
# install -m 755 -c /tmp/minio /usr/local/bin/minio
# install -m 755 -c /tmp/mc /usr/local/bin/mc
```

### Running MinIO by Hand

A major trouble is starting MinIO.  Try to start MinIO by hand.

```
lenticularis$ /usr/loca/bin/minio --json --anonymous server --address :9012 SOME-PATH
Or,
lenticularis$ /usr/bin/sudo -n -u SOME-UID -g SOME-GID \
    /usr/loca/bin/minio --json --anonymous server --address :9012 SOME-PATH
```

### Examining MinIO Behavior

It is a bit tricky when MinIO won't behave as expected.  In that case,
it will help to connect to MinIO with "mc" command.  It allows to dump
MinIO's tracing information, for example.

The necessary information to use "mc" command is a URL of a MinIO
endpoint, and administrator's key pair.  These can be obtained by
`lenticularis-admin show-be` command ("be" is a short for backend).  It
displays MinIO's endpoint (host:port) in "backend_ep" field.  It also
displays an access-key in "root_access" and a secret-key in
"root_secret".

The "show-be" command shows information on running MinIO instances.
To use "mc" command, it is necessary to keep a MinIO instance running.
Run `lenticularis-admin send-probe POOL-NAME`, repeatedly, to let it running.

```
lenticularis$ cd ~
lenticularis$ lenticularis-admin -c ./lens3.conf show-pool
lenticularis$ lenticularis-admin -c ./lens3.conf show-be
lenticularis$ lenticularis-admin -c ./lens3.conf send-probe POOL-NAME
```

For example, the sequence of commands below enables to dump tracing
logs from MinIO.  ALIAS-NAME can be any string.  A URL string would be
"http:// + _backend_ep_", like `http://localhost:9012`.

```
lenticularis$ mc alias set ALIAS-NAME URL ACCESS-KEY SECRET-KEY
lenticularis$ mc admin trace -v ALIAS-NAME
```

### MinIO Vulnerability Information

* https://github.com/minio/minio/security
* https://blog.min.io/tag/security-advisory/
* https://www.cvedetails.com/vulnerability-list/vendor_id-18671/Minio.html

A list in cvedetails.com is a summary of vulnerability databases
created by cvedetails.com.
