# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

* Components
  * Mux (Multiplexer)
  * Api (Web-API)
  * MinIO (S3 server)
  * Redis

### Manager (under Mux)

A Manager starts a MinIO instance and manages its life-time.

## Security

## Design Notes

### Redis Database Keys (prefixes)

Lens3 uses a couple of databases (by a database number), but the
division is arbitrary because the distinct prefixes are used.  Most of
the entries are records in json, and the others are simple strings.

Note: In the tables below, entries with "(\*)" are set atomically (by
"setnx"), and entries with "(\*\*)" are with expiry.

#### storage-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| po:pool-id    | pool-description | |
| uu:user       | user-info     | |
| ps:pool-id    | pool-state    | |
| bd:directory  | pool-id       | A bucket-directory (string) (\*) |

A __po:pool-id__ entry is a pool description: {"pool_name",
"owner_uid", "owner_gid", "buckets_directory", "probe_key",
"expiration_date", "online_status", "modification_time"}.  It holds
the semi-static part of pool information.

A __uu:user__ entry is a record of a user: {"groups", "permitted",
"modification_time"} where "groups" is a string list and "permitted"
is a boolean.

A __ps:pool-id__ entry is a pool-state which is one of: "initial",
"ready", "disabled", and "inoperable".

A __bd:directory__ is a bucket-directory entry.  The entry is assigned
in exclusion.  Note it is avoided to run multiple MinIO instances in
the same directory.  However, some MinIO instances may run in a
transient state.

#### process-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| ma:pool-id    | MinIO-manager | (\*, \*\*)|
| mn:pool-id    | MinIO-process | |
| mx:mux-endpoint | Mux-description | (\*\*) |

An __ma:pool-id__ entry is a MinIO-manager under which a MinIO process
runs.  It is a record: {"mux_host", "mux_port", "manager_pid",
"modification_time"}.  It is assigned in exclusion and protects
accesses to mn:pool-id and ep:pool-id.

An __mn:pool-id__ entry is a MinIO-process description: {"minio_ep",
"minio_pid", "admin", "password", "mux_host", "mux_port",
"manager_pid", "modification_time"}.

An __mx:mux-endpoint__ entry is a Mux description that is a record:
{"host", "port", "start_time", "modification_time"}.  A key is an
endpoint (host+port) of a Mux.  The content has no particular use.  A
start-time is a time Mux started.  A modification-time is a time the
record is refreshed, which is renewed when an entry is gone by expiry.

#### routing-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| ep:pool-id    | MinIO-endpoint | |
| bk:bucket-name | bucket-description | A mapping by a bucket-name (\*) |
| ts:pool-id    | timestamp     | Timestamp on the last access (string) |

An __ep:pool-id__ entry is a MinIO-endpoint (a host:port string).

A __bk:bucket-name__ entry is a bucket-description that is a
record: {"pool", "bkt_policy", "modification_time"}.  A bkt-policy
indicates public R/W status of a bucket: {"none", "upload",
"download", "public"}, which are borrowed from MinIO.

#### pickone-table

| Key           | Value         | Description   |
| ----          | ----          | ----          |
| id:random     | key-description | An entry to keep uniqueness (*) |

An id:random entry stores a generated key for pool-id or access-key.
A key-description is a record: {"use", "owner", "secret_key",
"key_policy", "modification_time"}.  A use/owner pair is either
"pool"/user-id or "access_key"/pool-id.  A secret-key and a key-policy
fields are missing for an entry for use=pool.  A key-policy is one of
{"readwrite", "readonly", "writeonly"}, which are borrowed from MinIO.

### Bucket policy

Public r/w policy is given to a bucket by Lens3.  Lens3 invokes the mc
command, one of the following.

```
mc policy set public alias/bucket
mc policy set upload alias/bucket
mc policy set download alias/bucket
mc policy set none alias/bucket
```

Accesses to deleted buckets in Lens3 are refused at Mux, but they
remain accessbile in MinIO, which have access policy "none" and are
accessible using access-keys.

### Redis Database Operations

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

### Pool State Transition

A bucket-pool has a state in: (None), __INITIAL__, __READY__,
__DISABLED__, and __INOPERABLE__.  Mux (a Manager) governs a
transition of states.  A Manager checks conditions of a transition at
some interval (by heartbeat_interval).

* __None__ → __INITIAL__: It is a quick transition.
* __INITIAL__ → __READY__: It is at a start of MinIO.
* ? → __DISABLED__: It is by some disabling condition, including an
  expiry of a pool, disabling a user account, or making a pool
  offline.
* __DISABLED__ → __INITIAL__: It is at a cease of a disabling condition.
* ? → __INOPERABLE__: It is by a failure of starting MinIO.  This
  state is a deadend.

### Mux/Api systemd Services

All states of services are stored in Redis.  systemd services can be
stoped/started.

### Api Processes

Api is not designed as load-balanced.  Api may consist of some
processes started by Gunicorn, but they are not distributed.

### Mux Processes

There exists multiple Mux processes for a single Mux service, as it is
started by Gunicorn.  Some book-keeping periodical operations (running
in background threads) are performed more frequently than expected.

### MinIO Clients

Note that alias commands are local (not connect to a MinIO).

### Manager Processes

A Manager becomes a session leader (by calling setsid), and a MinIO
process will be terminated when a Manager exits.

## Service Tests

#### Forced Heartbeat Failure

"kill -STOP" the MinIO process.  It causes heartbeat failure.  Note
that it leaves "minio" and "sudo" processes in the STOP state.

#### Forced Termination of Mux and MinIO

#### Forced Deletion of Redis Expiring Entries

The action Lens3 takes at a forced removal of a __ma:pool-id__ entry
in Redis should (1) start a new Mux+MinIO pair, and (2) stop an old
Mux+MinIO pair.

## Glossary

* __Probe-key__: An access-key used by Api to tell Mux about a wake up
  of MinIO.  This is key has no corresponding secret.  It is
  distiguished by an empty secret.

## RANDOM MEMO

__Load balancing__: The "scheduler.py" file is not used in v1.2, which
is for distributing the processes.  Lens3 now assumes accesses to Mux
is in itself balanced by a front-end reverse-proxy.

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
