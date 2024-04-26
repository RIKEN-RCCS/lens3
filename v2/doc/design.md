# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

* Lens3-Mux
* Lens3-Api (Web-UI)
* Manager: A Manager runs under a Lens3-Mux and starts a MinIO
  instance and manages its lifetime.
* MinIO (S3 server)
* Redis

## Redis Databases (prefixes of keys)

Lens3 uses a couple of Redis databases (by database numbers), but the
division is arbitrary as distinct prefixes are used.  Most of the
entries are json records, and others are simple strings.

NOTE: In the tables below, entries with "\*1" are set atomically (by
"setnx"), and entries with "\*2" are with expiry.

A date+time is by unix seconds.  Web-UI also passes a date+time by
unix seconds.

Mux, Api, and Managers make (potentially) many connections to Redis,
because they use multiple databases.

### Setting-Table (DB=0)

| Key             | Value     | Notes   |
| ----            | ----      | ---- |
| "cf:api"        | api-conf  | |
| "cf:mux"        | mux-conf  | |
| cf:mux:mux-name | mux-conf  | Optional |
| uu:uid          | user-info | |
| um:claim        | uid       | Optional |

The Setting-Table stores semi-static information.

__cf:api__ and __cf:mux__ (literal strings) entries store the settings
of services.  __cf:mux:mux-name__ is used to choose a specific setting
to each Mux service, whose mux-name is replaced by a string in an
environment variable "LENS3_MUX_NAME" passed to a service.

A __uu:uid__ entry is a record of a user-info: {"uid", "groups",
"claim", "enabled", "modification_time"}, where "groups" is a string
list, "claim" is a string (maybe empty), and "enabled" is a boolean.

A __um:claim__ entry is a map from a user claim to a uid.  It is
optional and an entry is used only when Lens-Api is configured with
"claim_uid_map=map".

A primary reason for storing configurations in the database is to let
them parsed at storing in the database.  Detecting typos at a start of
a service is very annoying.

### Storage-Table (DB=1)

| Key           | Value         | Notes   |
| ----          | ----          | ---- |
| po:pool-id    | pool-description | |
| ps:pool-id    | pool-state    | |
| bd:directory  | pool-id       | A bucket-directory (path string) \*1 |

A __po:pool-id__ entry is a pool description: {"pool_name",
"owner_uid", "owner_gid", "buckets_directory", "probe_key",
"online_status", "expiration_time", "modification_time"}.  It holds
the semi-static part of pool information.

A __ps:pool-id__ entry is a pool-state which is a record {"state",
"reason", "modification_time"}.  A state is one of: {"initial",
"ready", "suspended", "disabled", "inoperable"}.  A value of reason is
a string, which can be a long string of an error message.

A __bd:directory__ is a bucket-directory entry.  The entry is
atomically assigned.  Scanning of these entries is necessary to find a
list of pool-directories, because Lens3 does not keep a list.

Lens3 forbids running multiple MinIO instances in the same directory.
Note, however, directory links can fool the detection of the same
directory.  In addition, MinIO instances may run in the same directory
transiently in a race in starting/stopping instances.

### Process-Table (DB=2)

| Key             | Value           | Notes   |
| ----            | ----            | ---- |
| ma:pool-id      | MinIO-manager   | \*1, \*2 |
| mn:pool-id      | MinIO-process   | |
| mx:mux-endpoint | Mux-description | \*2 |

An __ma:pool-id__ entry records a MinIO-manager under which a MinIO
process runs.  It is a record: {"mux_host", "mux_port", "start_time"}.
It is atomically set to ensure uniqueness of a running Manager (a
loser will quit).  A start-time makes the chosen entry distinguishable
(but not strictly distinguishable).

An __mn:pool-id__ entry is a MinIO-process description: {"minio_ep",
"minio_pid", "admin", "password", "mux_host", "mux_port",
"manager_pid", "modification_time"}.  A admin/password pair specifies
an administrator of a MinIO instance.

An __mx:mux-endpoint__ entry is a Lens3-Mux description that is a
record: {"host", "port", "start_time", "modification_time"}.  A key is
an endpoint of a Lens3-Mux (a host:port string).  The content has no
particular use.  A start-time is a time Lens3-Mux started.  A
modification-time is a time the record is refreshed.

### Routing-Table (DB=3)

| Key            | Value              | Notes   |
| ----           | ----               | ---- |
| ep:pool-id     | MinIO-endpoint     | |
| bk:bucket-name | bucket-description | A mapping by a bucket-name \*1 |
| ts:pool-id     | timestamp          | Timestamp on an access (string) |
| us:uid         | timestamp          | Timestamp on a user access (string) |


An __ep:pool-id__ entry is a MinIO-endpoint (a host:port string).

A __bk:bucket-name__ entry is a record of a bucket-description:
{"pool", "bkt_policy", "modification_time"}.  A bkt-policy indicates
public R/W status of a bucket: {"none", "upload", "download",
"public"}, whose names are borrowed from MinIO.

A __ts:pool-id__ entry is a last access timestamp of a pool.  It is
used to decide whether to stop a MinIO instance.

A __us:uid__ is an access timestamp of a user.  It is just a record.
It is used to find out inactive users (no tools are provided).

### Monokey-Table (DB=4)

| Key           | Value           | Notes   |
| ----          | ----            | ---- |
| pi:random     | key-description | \*1 |
| ky:random     | key-description | \*1 |

This table stores generated randoms for a pool-id or an access-key.
An entry is inserted to keep its uniqueness.

A __pi:random__ entry is a pool-id and it is a record: {"owner",
"modification_time"}, where an owner is a uid.

A __ky:random__ entry is an access-key and it is a record: {"owner",
"secret_key", "key_policy", "expiration_time", "modification_time"},
where an owner is a pool-id.  A key-policy is one of {"readwrite",
"readonly", "writeonly"}, whose names are borrowed from MinIO.

## Bucket policy

Public read/write policy is given to a bucket by Lens3.  Lens3 invokes
the mc command, one of the following.

```
mc policy set public alias/bucket
mc policy set upload alias/bucket
mc policy set download alias/bucket
mc policy set none alias/bucket
```

Accesses to deleted buckets in Lens3 are refused at Lens3-Mux, but
they remain potentially accessible in MinIO, which have access policy
"none" and are accessible using access-keys.

## Redis Database Operations

A single Redis instance is used, and is not distributed.

It is usually required an uniqueness guarantee, such as for an
access-keys and ID's for pools, and atomic set is suffice.  A failure
condition is only considered for MinIO endpoints, and timeouts are set
to "ma:pool-id" entries.  See the section Redis Database Keys.

Redis client routines catches exceptions related to sockets (including
ConnectionError and TimeoutError).  Others are not checked at all by
Lens3.

Operations by an administrator is NOT mutexed.  Some operations should
be performed carefully.  They include modifications on the user-list.

## Pool State Transition

A bucket-pool will be in a state of: (None), __INITIAL__, __READY__,
__SUSPENDED__, __DISABLED__, and __INOPERABLE__.  A Lens3-Mux governs
a transition of a state.  Also, a Manager checks a condition at
heartbeating.

* __None__ → __INITIAL__: It is a quick transition.
* __INITIAL__ → __READY__: It is at a start of MinIO.  Note the READY
  state does not imply a MinIO instance is running.
* {__INITIAL__, __READY__} → __SUSPENDED__: It is on a condition the
  server is busy (all reserved ports are used).
* __SUSPENDED__ → __INITIAL__: It is performed periodically.  It will
  move back again to the __SUSPENDED__ state if a potential condition
  remains.
* {__INITIAL__, __READY__} → __DISABLED__: It is by some setting that
  disables a pool, including disabling a user account, an expiry of a
  pool, or making a pool offline.
* __DISABLED__ → __INITIAL__: It is at a cease of a disabling condition.
* any → __INOPERABLE__: It is at a failure of starting MinIO.  This
  state is a deadend.  A bucket-pool should be removed.

Deleting buckets and secrets during suspension will alter only the
state of Lens3 but not the state of MinIO (becuase MinIO is not
running).  At waking up from suspension, it moves the state to INITIAL
(not READY) so that it will adjust the state of MinIO to a consistent
state with the state of Lens3 at the next start.

### Lens3-Mux/Lens3-Api systemd Services

All states of services are stored in Redis.  It is safe to stop/start
systemd services.

## Processes

### Lens3-Api Processes

Lens3-Api is not designed to work in distributed for load-balancing.

### Lens3-Mux Processes

There exist multiple Lens3-Mux processes for a single Lens3-Mux
service, as it is started by Gunicorn.  Some book-keeping periodical
operations (running in background threads) are performed more
frequently than expected.

### Manager Processes

A Manager becomes a session leader (by calling setsid), and a MinIO
process will be terminated when a Manager exits.

## Building UI

Lens3 UI is created by vuejs+vuetify.  The code for Vuetify is in the
"v1/ui" directory.  See [v1/ui/README.md](../ui/README.md) for building UI.

## Security

Security mainly depends on the setting of the frontend proxy.  Please
consult experts for setting up the proxy.  Accesses to Lens3-Api are
authenticated as it is behind the proxy, and thus it is of less
concern.  Lens3-Mux restricts accesses by checking a pair of a bucket
and a secret.  Checker functions have names beginning with "ensure_".
Please review those functions intensively.

## HTTP Status Code

Lens3-Api and Lens3-Mux returns a limited set of status codes.  Other
than these, the codes are also from the proxy and from MinIO.

* 200 OK
* 400 Bad Request
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found
* 500 Internal Server Error
* 503 Service Unavailable

## Notes on Testing the Service

### Forced Heartbeat Failure

"kill -STOP" the MinIO process.  It causes heartbeat failure.  Note
that it leaves "minio" and "sudo" processes in the STOP state.

### Forced Termination of Lens3-Mux and MinIO

### Forced Expiration of Lens3-Mux Entries in Redis

The action to fake a forced removal of a __ma:pool-id__ entry in Redis
should (1) start a new Lens3-Mux + MinIO pair, and then (2) stop an
old Lens3-Mux + MinIO pair.

## Notes on MinIO

### Clients (MC)

Note that alias commands are local (not connect to a MinIO).

### MinIO Start Messages

Lens3 recognizes some messages from MinIO at a start to judge a run is
successful.  A failure in starting MinIO make the pool inoperable.  A
message of level=FATAL is treated as erroneous, but level=ERROR is
not.  An exception is a port-in-use error which is level=FATAL.  Lens3
retries to start MinIO in that case.  The patterns of messages in the
source code may require fixing after updating MinIO and MC command.

A successful run will output several messages of level=INFO.  Lens3
looks for a message starting with "S3-API:" to be successful.  The
messages look like as follows (some slots are omitted).

```

{"level":"INFO", ..., "message":"MinIO Object Storage Server"}
...
{"level":"INFO", ..., "message":"S3-API: http://XX.XX.XX.XX:9000
 http://127.0.0.1:9000 "}

{"level":"INFO", ..., "message":"Console: http://XX.XX.XX.XX:38671
 http://127.0.0.1:38671 "}
...
```

Lens3 looks for a message "Specified port is already in use" on a
port-in-use error.  It will be retried.  Messages look like:

```
{"level":"FATAL", ..., "message":"Specified port is already in use:
 listen tcp XX.XX.XX.XX:9000: bind: address already in use",
 "error":{"message":"Specified port is already in use: listen tcp
 XX.XX.XX.XX:9000: bind: address already in use", ...}}
```

Other typical messages are listed below.  Note some messages of
level=ERROR precede a message of level=FATAL.  Messages from a run
specifying a non-writable directory look like:

```
{"level":"ERROR", ..., "error":{...}}
{"level":"ERROR", ..., "error":{...}}
{"level":"FATAL", ..., "message":"Invalid arguments specified",
 "error":{"message":"Invalid arguments specified", "source":[...]}}
```

Messages from a run with exisiting incompatible ".minio.sys" (created
by an older version of MinIO) look like:

```
{"level":"FATAL", ..., "message":"Invalid arguments specified",
 "error":{"message":"Invalid arguments specified", "source":[...]}}
```

MESSAGES from older versions

```
{"level": "INFO", ..., "message": "API: http://n.n.n.n:n  http://n.n.n.n:n"}
{"level": "FATAL", ..., "message": "Specified port is already in use:
  listen tcp :n: bind: address already in use", ...}
{"level": "FATAL", ..., "message": "Unable to write to the backend:
  file access denied", ...}
```

## Glossary

* __Probe-key__: An access-key used by Lens3-Api to tell Lens3-Mux
  about a wake up of MinIO.  This is key has no corresponding secret.
  It is distiguished by an empty secret.

## Short-Term Todo, or Deficiency

* Rewrite in Go-lang.  The code will be in Go in the next release
  (v2.1.1).

* Avoid polling of a start of MinIO.  Currently, a Lens3-Mux waits for
  MinIO by frequent polling in the database.  See
  wait_for_service_starts().

* Reject certain bucket-directory paths so that it does service in
  directories with dots.  Servicing in ".ssh" should be avoided, for
  example.

* Make Lens3-Mux reply a message containing a reason of an access
  rejection.  It returns only a status code in v1.2.

* Make it not an error when an MC command returns
  "Code=BucketAlreadyOwnedByYou".  It can be ignored safely.

* Make access-key generation of Lens3-Api like STS.

* Make UI refresh the MinIO state, when a pool is edited and
  transitions such as from READY to INOPERABLE or from SUSPENDED to
  READY.

* Run a reaper of orphaned directories, buckets, and secrets at a
  Lens3-Api start.  Adding a bucket/secret and removing a pool may
  have a race.  Or, a crash at creation/deletion of a pool may leave
  an orphaned directory.

* Make starting a MinIO instance through the frontend proxy.
  Currently, an arbitrary Mux is chosen.  The proxy can balance the
  loads.

* Add a control on the pool status "online".  It is always online,
  currently.

* Add site setting variations.  Examples: Enable users by default (it
  needs explicit enabling users currently); Disallow public access
  buckets at all.

* Add options
  - confirmation at the first use: terms-of-use.
  - description field (just memo) to keys.
  - disable public buckets.

## RANDOM MEMO

__Load balancing__: The "scheduler.py" file is not used in v1.2, which
is for distributing the processes.  Lens3 now assumes accesses to
Lens3-Mux is in itself balanced by a front-end proxy.

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
http header.  NGINX (a proxy in front of Lens3) seems to return 502 on
long delays.  See [rfc7231](https://httpwg.org/specs/rfc7231.htm).

__Python Modules__: "FastAPI" uses "Starlette".  There are no direct
uses of "Starlette" in the source code.

__MinIO behavior__: MinIO refuses a connection by ECONNRESET
sometimes, maybe at a slightly high load.  Lens3 returns 503 on
ECONNRESET.

__MinIO behavior__: MinIO refuses a connection by EPIPE for some
illegal accesses.  That is, when trying to put an object by a
readonly-key or to put an object to a download-bucket without a key.
Lens3 returns 503 on EPIPE, but, it makes clients retry badly.

__Accepting pool creation in busy situations__: Lens3 accepts creation
of a pool even if it cannot start MinIO due to busyness of the server.
It is done on purpose to display the error condition in UI's
"minio_state" slot.
