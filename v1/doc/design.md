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
division is arbitrary as the distinct prefixes are used.  Most of the
entries are json records, and others are simple strings.

Note: In the tables below, entries with "\*1" are set atomically (by
"setnx"), and entries with "\*2" are with expiry.

A date+time is by unix seconds.  Web-API also passes a date+time by
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
of services.  __cf:mux:mux-name__ is used to give a specific setting
to each Mux service, whose mux-name is given by "LENS3_MUX_NAME" at a
start of a service in environment variables.

A __uu:uid__ entry is a record of a user-info: {"uid", "groups",
"claim", "enabled", "modification_time"}, where "groups" is a string
list, "claim" is a string (maybe empty), and "enabled" is a boolean.

A __um:claim__ entry is a map from a user claim to a uid.  Entries are
used only when Lens-Api is configured with "claim_uid_map=map".

One reason for storing configurations in the database is to let them
parsed at storing in the database.  Detecting typos at a start of a
service is very annoying.

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
"reason", "modification_time"}.  A state is one of: "initial",
"ready", "disabled", and "inoperable".  Reason is a string.  Sometimes
a reason string may be a long error message.

A __bd:directory__ is a bucket-directory entry.  The entry is
atomically assigned.  Lens3 forbids running multiple MinIO instances
in the same directory.  Note, however, MinIO instances may possibly
run in a transient state at a race in starting/stopping an instance.

### Process-Table (DB=2)

| Key             | Value           | Notes   |
| ----            | ----            | ---- |
| ma:pool-id      | MinIO-manager   | \*1, \*2 |
| mn:pool-id      | MinIO-process   | |
| mx:mux-endpoint | Mux-description | \*2 |

An __ma:pool-id__ entry holds a MinIO-manager under which a MinIO
process runs.  It is a record: {"mux_host", "mux_port", "start_time"}.
A start time makes the entry distinguishable.  It is atomically set to
ensure uniqueness of a running Manager (a loser will quit).

An __mn:pool-id__ entry is a MinIO-process description: {"minio_ep",
"minio_pid", "admin", "password", "mux_host", "mux_port",
"manager_pid", "modification_time"}.  A admin/password pair specifies
an administrator.

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
It is to check inactive users.

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
__SUSPENDED__, __DISABLED__, and __INOPERABLE__.  A Lens3-Mux governs
a transition of a state.  Also, a Manager checks a condition at
heartbeating.

* __None__ → __INITIAL__: It is a quick transition.
* __INITIAL__ → __READY__: It is at a start of MinIO.
* {__INITIAL__, __READY__} → __SUSPENDED__: It is on a condition the
  server is busy (all ports are used).
* __SUSPENDED__ → __INITIAL__: It is performed periodically.  It will
  move back again to the __SUSPENDED__ state if a potential condition
  remains.
* {__INITIAL__, __READY__} → __DISABLED__: It is by some setting that
  disables a pool, including disabling a user account, an expiry of a
  pool, or making a pool offline.
* __DISABLED__ → __INITIAL__: It is at a cease of a disabling condition.
* ? → __INOPERABLE__: It is at a failure of starting MinIO.  This
  state is a deadend.  A bucket-pool should be removed.

Deleting buckets and secrets may act only on Lens3 during suspension.
It moves not to READY but INITIAL, which adjusts MinIO in a consistent
state with Lens3 at the next start.

### Lens3-Mux/Lens3-Api systemd Services

All states of services are stored in Redis.  systemd services can be
stoped/started.

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

## UI

Lens3 UI is created by vuejs+vuetify.  The code for Vuetify is in the
"v1/ui" directory.  See README.md in [ui](../ui/) for building UI
code.

## Security

Security mainly depends on the setting of the frontend proxy.  Please
consult experts for setting up the proxy.  Accesses to Lens3-Api are
authenticated as it is behind the proxy, and thus it is less concern.
Lens3-Mux restricts accesses by checking a pair of a bucket and a
secret.  The checker functions are named as beginning with "ensure_".
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

### MinIO Startup Messages

Lens3 recognizes a few of the messages at a MinIO startup.  It retries
starting MinIO on a port-in-use error.  The code to match messages
needs to be updated after updating MinIO, because these messages may
change in versions of MinIO,

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

* Rewrite in Go-lang.  The code will be in Go in the next release.
* Let a reply contain a message on a rejected access at Lens3-Mux.  It
  returns only a status number in v1.2.
* UI does not refresh the MinIO state, when it is edited and it
  transitions from SUSPENDED to READY.
* Run a remover of orphaned directories, buckets, and keys at
  Lens3-Api startup.  Adding a bucket/key and removing a pool have a
  race.  A crash at creation/deletion of a pool may leave an orphaned
  directory.
* Make access-key generation of Lens3-Api behave like STS.
* Add control on the pool status "online".  It is always online currently.
* Make starting a MinIO instance through the frontend proxy.
  Currently, arbitrary Mux is chosen.  The proxy can balance the
  loads.

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
(Connection reset by peer) at a high load (not too high), instead of
an expected 503 reply.

__Accepting pool creation in busy situations__: Lens3 accepts creation
of a pool even if it cannot start MinIO due to busyness of the server.
It is to display the error condition in the UI's "minio_state" slot.
