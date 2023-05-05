# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

* Lens3-Mux
* Lens3-Api (Web-API)
* Manager: A Manager runs under a Lens3-Mux and starts a MinIO
  instance and manages its lifetime.
* MinIO (S3 server)
* Redis

## Redis Databases (prefixes of keys)

Lens3 uses a couple of Redis databases (by database numbers), but the
division is arbitrary as the distinct prefixes are used.  Most of the
entries are json records, and others are simple strings.

Note: In the tables below, entries with "(\*)" are set atomically (by
"setnx"), and entries with "(\*\*)" are with expiry.

A date+time is by unix seconds.  Web-API also passes a date+time by
unix seconds.

Mux, Api, and Managers make (potentially) many connections to Redis,
because they use multiple databases.

### Setting-Table (DB=0)

The Setting-Table stores semi-static information.

| Key             | Value     | Notes   |
| ----            | ----      | ---- |
| "cf:api"        | api-conf  | |
| "cf:mux"        | mux-conf  | |
| cf:mux:mux-name | mux-conf  | Optional |
| uu:uid          | user-info | |
| um:claim        | uid       | Optional |

__cf:api__ and __cf:mux__ entries store the settings of services.
__cf:mux:mux-name__ is used to give a specific setting to each Mux
service, whose mux-name is given by "LENS3-MUX-NAME" at a start of a
service in environment variables.

A __uu:uid__ entry is a record of a user-info: {"uid", "groups",
"claim", "enabled", "modification_time"}, where "groups" is a string
list, "claim" is a string (maybe empty), and "enabled" is a boolean.

A __um:claim__ entry is a map from a user claim to a uid.  Entries are
used only when Lens-Api is configured with "claim_uid_map=map".

A partial reason of storing configurations in the database is because
typo errors are annoying when detected at a start of a service.

### Storage-Table (DB=1)

| Key           | Value         | Notes   |
| ----          | ----          | ---- |
| po:pool-id    | pool-description | |
| ps:pool-id    | pool-state    | |
| bd:directory  | pool-id       | A bucket-directory (path string) (\*) |

A __po:pool-id__ entry is a pool description: {"pool_name",
"owner_uid", "owner_gid", "buckets_directory", "probe_key",
"online_status", "expiration_time", "modification_time"}.  It holds
the semi-static part of pool information.

A __ps:pool-id__ entry is a pool-state which is one of: "initial",
"ready", "disabled", and "inoperable".

A __bd:directory__ is a bucket-directory entry.  The entry is
atomically assigned.  Lens3 forbids running multiple MinIO instances
in the same directory.  Note, however, MinIO instances may possibly
run in a transient state at a race in starting/stopping an instance.

### Process-Table (DB=2)

| Key             | Value           | Notes   |
| ----            | ----            | ---- |
| ma:pool-id      | MinIO-manager   | (\*, \*\*)|
| mn:pool-id      | MinIO-process   | |
| mx:mux-endpoint | Mux-description | (\*\*) |

An __ma:pool-id__ entry holds a MinIO-manager under which a MinIO
process runs.  It is a record: {"mux_host", "mux_port", "start_time"}.
A start time makes the entry distinct.  It is atomically assigned to
ensure uniqueness of a running Manager (a loser quits).

An __mn:pool-id__ entry is a MinIO-process description: {"minio_ep",
"minio_pid", "admin", "password", "mux_host", "mux_port",
"manager_pid", "modification_time"}.  A admin/password pair specifies
an administrator.

An __mx:mux-endpoint__ entry is a Lens3-Mux description that is a
record: {"host", "port", "start_time", "modification_time"}.  A key is
an endpoint of a Lens3-Mux (a host:port string).  The content has no
particular use.  A start-time is a time Lens3-Mux started.  A
modification-time is a time the record is refreshed, which is renewed
when an entry is gone by expiry.

### Routing-Table (DB=3)

| Key            | Value              | Notes   |
| ----           | ----               | ---- |
| ep:pool-id     | MinIO-endpoint     | |
| bk:bucket-name | bucket-description | A mapping by a bucket-name (\*) |
| ts:pool-id     | timestamp          | Timestamp on the last access (string) |

An __ep:pool-id__ entry is a MinIO-endpoint (a host:port string).

A __bk:bucket-name__ entry is a record of a bucket-description:
{"pool", "bkt_policy", "modification_time"}.  A bkt-policy indicates
public R/W status of a bucket: {"none", "upload", "download",
"public"}, whose names are borrowed from MinIO.

A __ts:pool-id__ entry is a last access timestamp of a pool.

### Monokey-Table (DB=4)

| Key           | Value           | Notes   |
| ----          | ----            | ---- |
| id:random     | key-description | An entry to keep uniqueness (*) |

An id:random entry stores a generated random for a pool-id or an
access-key.  The "use" field distinguishes these, "use"="pool" or
"use"="key".

A "pool" description is a record: {"use"="pool", "owner",
"modification_time"}, where an owner is a uid.

A "key" description is a record: {"use"="key", "owner", "secret_key",
"key_policy", "expiration_time", "modification_time"}, where an owner
is a pool-id.  A key-policy is one of {"readwrite", "readonly",
"writeonly"}, whose names are borrowed from MinIO.

## Bucket policy

Public r/w policy is given to a bucket by Lens3.  Lens3 invokes the mc
command, one of the following.

```
mc policy set public alias/bucket
mc policy set upload alias/bucket
mc policy set download alias/bucket
mc policy set none alias/bucket
```

Accesses to deleted buckets in Lens3 are refused at Lens3-Mux, but
they remain accessbile in MinIO, which have access policy "none" and
are accessible using access-keys.

## Redis Database Operations

A single Redis instance is used, and not distributed.

Usually, it is required an uniqueness guarantee, such as for an
access-keys and ID's for pools, and atomic set is suffice.  A failure
is concidered only for MinIO endpoints, and timeouts are set for
"ma:pool-id" entries.  See the section Redis Database Keys.

Redis client routines catches socket related exceptions (including
ConnectionError and TimeoutError).  Others are not checked at all by
Lens3.

Operations by an administrator is NOT mutexed.  They include
modifications on the user-list.

## Pool State Transition

A bucket-pool will be in a state of: (None), __INITIAL__, __READY__,
__DISABLED__, and __INOPERABLE__.  A Manager started by Lens3-Mux
governs a transition of a state.  A Manager checks conditions of a
transition at intervals (by heartbeat_interval).

* __None__ → __INITIAL__: It is a quick transition.
* __INITIAL__ → __READY__: It is at a start of MinIO.
* ? → __DISABLED__: It is by some disabling condition, including an
  expiry of a pool, disabling a user account, or making a pool
  offline.
* __DISABLED__ → __INITIAL__: It is at a cease of a disabling condition.
* ? → __INOPERABLE__: It is by a failure of starting MinIO.  This
  state is a deadend.  A bucket-pool should be removed.

### Lens3-Mux/Lens3-Api systemd Services

All states of services are stored in Redis.  systemd services can be
stoped/started.

## Lens3-Api Processes

Lens3-Api is not designed as load-balanced.  Lens3-Api may consist of
some processes started by Gunicorn, but they are not distributed.

## Lens3-Mux Processes

There exists multiple Lens3-Mux processes for a single Lens3-Mux
service, as it is started by Gunicorn.  Some book-keeping periodical
operations (running in background threads) are performed more
frequently than expected.

## MinIO Clients

Note that alias commands are local (not connect to a MinIO).

## Manager Processes

A Manager becomes a session leader (by calling setsid), and a MinIO
process will be terminated when a Manager exits.

## Service Tests

### Forced Heartbeat Failure

"kill -STOP" the MinIO process.  It causes heartbeat failure.  Note
that it leaves "minio" and "sudo" processes in the STOP state.

### Forced Termination of Lens3-Mux and MinIO

### Forced Expiration of Lens3-Mux Entries in Redis

The action to fake a forced removal of a __ma:pool-id__ entry in Redis
should (1) start a new Lens3-Mux + MinIO pair, and then (2) stop an
old Lens3-Mux + MinIO pair.

## Short Term TODO, or Deficiency

* Add control on the pool statuses "online" and "expiration" via
  Web-API.  They are of fixed values currently.
* Start MinIO with the --json option.  It will make parsing the output
  reliable.
* Rewrite in Go-lang.  The code will be in Go in the next release.
* Make access-key generation of Web-API behave like STS.
* Make starting a MinIO instance via the frontend proxy.  Currently,
  an arbitrary Mux is chosen, but the proxy can balance loads.

## Security

Security totally depends on the setting of the proxy.  Ask experts for
setting up the proxy.

## Glossary

* __Probe-key__: An access-key used by Lens3-Api to tell Lens3-Mux
  about a wake up of MinIO.  This is key has no corresponding secret.
  It is distiguished by an empty secret.

## RANDOM MEMO

__Load balancing__: The "scheduler.py" file is not used in v1.2, which
is for distributing the processes.  Lens3 now assumes accesses to
Lens3-Mux is in itself balanced by a front-end reverse-proxy.

__Removing buckets__: Lens3 does not remove buckets at all.  It just
makes them inaccessible.  It is because MinIO's "mc rb" command
removes the contents of a bucket that is not useful usually.

__Python Popen behavior__: A closure of a pipe created by Popen is not
detectable until the process exits.  Lens3 uses a one line message on
stdout to detect a start of a subprocess, but it does not wait for an
EOF.  In addition, p.communicate() on an exited process waits.  A
check of a process status is needed.

__Python alarm behavior__: Raising an exception at an alarm signal
does not wake-up the python waiting for a subprocess to finish.
Instead, a timeout of p.comminicate() will be in effect.

__MC command concurrency__: Lens3 assumes concurrently running
multiple MC commands with distinct aliases and distinct config-dirs do
not interfere.

__MinIO start delay__: Lens3 delays request handling on starting
MinIO.  Alternatively, it can be returning 503 with a "Retry-After"
http header.  NGINX (a reverse-proxy in front of Lens3) seems
returning 502 on long delays.  See
[rfc7231](https://httpwg.org/specs/rfc7231.htm).
