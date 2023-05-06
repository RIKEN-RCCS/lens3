# Lenticularis-S3 Administration Guide

## System Maintenance

### Updating MinIO and Mc Binaries

MinIO and Mc should be updated manually.  Note that Lens3 may fail to
operate on updating versions of MinIO or Mc.

```
mc admin update
```

### Redis DB Backup

Lens3 uses Redis's "snapshotting" of the database to a file.  The
interval of a snapshot and the file location can be found under the
keywords "save", "dbfilename", and "dir" in the configuration
"/etc/lenticularis/redis.conf".  Lens3 uses "save 907 1" by default,
which is an interval about 15 minutes.  Since Lens3 does nothing on
the backup file, daily copying/rotating of snapshots should be
performed by cron.

See Redis documents for more information: [Redis
persistence](https://redis.io/docs/manual/persistence/)

### Json File Backup

A database of uses/pools can be saved/restored as a json file.  A json
file backup is done by a lens3-admin dump command.  However, a
backup of a Redis database is preferred.

```
$ lens3-admin dump users > users.json
$ lens3-admin dump pools > pools.jsan
  ......
$ lens3-admin reset-db
$ lens3-admin restore users.json
$ lens3-admin restore pools.json
```

## Administration Command (lens3-admin)

Lens3 provides "lens3-admin" command for direct database
modifications.  Note that it does not change the status of a MinIO
instance, and the modifications will be reflected at the next start of
a MinIO instance.  Moreover, modifications could be inconsistent.

"lens3-admin" command should typically be run on the same host of
Lens3-Api.  See a help by running
"lens3-admin -c api-config.yaml help", for the list of commands.

## Design Assumptions

* Lens3 assumes a proxy (an http front-end) terminates SSL connections
  and performs authentications.  It expects to receive a user identity
  in an http header X-REMOTE-USER.

* Lens3 assumes a running environment isolated from users.  MinIO runs
  as a user process and thus a user can kill/stop the process.  It is
  not a problem because another MinIO process will be started and the
  operation will continue.  However, stopping the MinIO processes will
  leave zombies (due to the behavior of sudo).

## Redis Service

Lens3 calls "redis-shutdown" with a fake configuration parameter
"lenticularis/redis" in lenticularis-redis.service.  It lets point to
a proper file "/etc/lenticularis/redis.conf" in result.

## Reverse-Proxy Settings

The reverse-proxy should not change the "Host:" HTTP header.  (Why?)

```
proxy_set_header Host $ http_host; (for NGINX)
ProxyPreserveHost on (for Apache2)
```

## Load-Balanced Setting

Lens3-Mux's can be run on multiple hosts, and a reverse-proxy will
distribute accesses to Lens3-Mux's.  In contrast, Lens3-Api service is
single.  In a multiple Lens3-Mux setting, firewall settings need to be
fixed.  The port range of communication for both Lens3-Mux's and
MinIO's on hosts must be open to Lens3-Api, since Lens3-Api accesses
both Lens3-Mux's and MinIO's.

## S3 Signature Algorithm Version

Lens3 works only with the signature v4 as MinIO does.  That is, an
authentication header must include the string "AWS4-HMAC-SHA256".  If
"pubic-access-user" appears in the access-log, it indicates the
request has no valid authentication information and it is very likely
the authentication header is wrong.

## RANDOM MEMO

__Increasing Logging verbosity__: Some classes has a `self._verbose`
variable.  Setting it true makes debug logging more verbose.

__Heartbeating Interval__: The expiration of a MinIO manager record in
Redis is set as a little larger than the duration of
(heartbeat-interval * (heartbeat-misses + 2)).  However, heartbeating
would take longer time by the timeout of urlopen, etc., and an
expiration of a MinIO manager record may come earlier than a heartbeat
failure.  That causes starting a new MinIO instance which replaces the
old instance before a heartbeat failure.

__sudo and SIGSTOP__: A sudo shows a peculiar behavior at a stop
signal: It stops itself when a subprocess got stopped.  A sudo process
(which runs as a root) can be stopped by a user, because the MinIO
runs as a usual user under sudo.  This results in the MinIO process is
never waited for.  Implication of this is that Lens3 should be run in
an environment isolated from users.

__Mux Node Name__: Lens3-Mux registers its endpoint obtained by
platform.node() to the database, but it should be explicitly given
when it is inappropriate.  Set the "mux_node_name" in "mux_conf.yaml".

__Failing Proper Shutdown__: A MinIO instance sometimes may stay alive
at a shutdown of the lenticularis-mux service.  Please check a MinIO
process without a manager process and kill it (which has sudo as the
parent and the sudo's parent is the init), when the lenticularis-mux
service is frequently started/stopped.

## Troubleshoot

### Early Troubles

First check the systemd logs.  Diagnosing errors in reading
configuration is a bit tricky.

A log of Lens3-Api may include a string "EXAMINE THE GUNICORN LOG",
which indicates a Gunicorn process finishes by some reason.  Check the
logs.

### Clean Start in Troubles

Clear Redis databases.

```
$ export REDISCLI_AUTH=password
$ redis-cli -p 6378 FLUSHALL
$ redis-cli -p 6378 --scan --pattern '*'
```

### Running MinIO by Hand

```
$ minio server --anonymous --json --address :9001 /home/UUU/pool-directory
```
