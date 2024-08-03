# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

* Multiplexer
* Registrar
* MinIO (S3 backend server)
* Valkey (keyval-DB)

## Keyval-DB Databases (prefixes of keys)

Lens3 uses three keyval-db (by database numbers), but the division is
arbitrary as distinct prefixes are used.  The entries are json.

NOTE: In the tables below, entries with "\*1" are set atomically (by
"setnx"), and entries with "\*2" are with expiry.

A date+time is by unix seconds.  Registrar also passes a date+time by
unix seconds.

Multiplexer and Registrar make (potentially) many connections to
keyval-db, because they use multiple databases.

### CONSISTENCY OF ENTRIES.

Some entries are dependent each other.  Crash-recovery should remove
orphaned enties.

__uu:uid and um:claim__.  uid ↔︎ claim is one-to-one if a user-info
contains a claim.

__bd:directory and bk:bucket-name__.

### Setting-Table (DB=0)

| Key             | Value     | Notes   |
| ----            | ----      | ---- |
| "cf:reg"        | reg-conf  | |
| "cf:mux"        | mux-conf  | |
| cf:mux:mux-name | mux-conf  | Optional |
| uu:uid          | user-info | |
| um:claim        | uid       | Optional |

The Setting-Table stores semi-static information.

__cf:reg__ and __cf:mux__ (literal strings) entries store the settings
of services.  __cf:mux:mux-name__ is used to choose a specific setting
to each Mux service, whose mux-name is replaced by a string in an
environment variable "LENS3_MUX_NAME" passed to a service.

A __uu:uid__ entry is a record of a user-info: {"uid", "groups",
"claim", "enabled", "modification_time"}, where "groups" is a string
list, "claim" is a string (maybe empty), and "enabled" is a boolean.

A __um:claim__ entry is a map from a user claim to a uid.  It is
optional and an entry is used only when Lens-Reg is configured with
"claim_uid_map=map".

A primary reason for storing configurations in the database is to let
them parsed at storing in the database.  Detecting typos at a start of
a service is very annoying.

### Storage-Table (DB=1)

| Key           | Value         | Notes   |
| ----          | ----          | ---- |
| po:pool-name  | pool-description | |
| ps:pool-name  | pool-state    | |
| bd:directory  | pool-name       | A bucket-directory (path string) \*1 |

A __po:pool-name__ entry is a pool description: {"pool_name",
"owner_uid", "owner_gid", "bucket_directory", "probe_key",
"online_status", "expiration_time", "modification_time"}.  It holds
the semi-static part of pool information.

A __ps:pool-name__ entry is a pool-state which is a record {"state",
"reason", "modification_time"}.  A state is one of: {"initial",
"ready", "suspended", "disabled", "inoperable"}.  A value of reason is
a string, which can be a long string of an error message.

A __bd:directory__ is a bucket-directory entry.  The entry is
atomically assigned.  Scanning of these entries is necessary to find a
list of pool-directories, because Lens3 does not keep a list.

Lens3 forbids running multiple backend instances in the same
directory.  Note, however, directory links can fool the detection of
the same directory.  In addition, backend instances may run in the
same directory transiently in a race in starting/stopping instances.

### Process-Table (DB=2)

| Key             | Value           | Notes   |
| ----            | ----            | ---- |
;;| (ma:pool-name)  | backend-manager   | \*1, \*2 |
;;| mn:pool-name    | backend-process   | |
| mx:mux-endpoint | Mux-description | \*2 |

An __ma:pool-name__ entry records a backend-manager under which a
backend process runs.  It is a record: {"mux_ep", "start_time"}.  It
is atomically set to ensure uniqueness of a running Manager (a loser
will quit).  A start-time makes the chosen entry distinguishable (but
not strictly distinguishable).

An __mn:pool-name__ entry is a backend-process description:
{"backend_ep", "backend_pid", "root_access", "root_secret", "mux_ep",
"manager_pid", "modification_time"}.  A root_access/root_secret pair
specifies an administrator access for a backend instance.
"manager_pid" is unused.

An __mx:mux-endpoint__ entry is a Multiplexer description that is a
record: {"mux_ep", "start_time", "modification_time"}.  A key is
an endpoint of a Multiplexer (a host:port string).  The content has no
particular use.  A start-time is a time Multiplexer started.  A
modification-time is a time the record is refreshed.

### Routing-Table (DB=3)

| Key            | Value              | Notes   |
| ----           | ----               | ---- |
;;| (ep:pool-name) | backend-endpoint   | |
| ep:pool-name   | backend-process    | \*1, \*2 |
| bk:bucket-name | bucket-description | A mapping by a bucket-name \*1 |
| ts:pool-name   | timestamp          | Timestamp on an access (string) |
| us:uid         | timestamp          | Timestamp on a user access (string) |

An __ep:pool-name__ entry is a backend-endpoint (a host:port string).

A __bk:bucket-name__ entry is a record of a bucket-description:
{"pool", "bkt_policy", "modification_time"}.  A bkt-policy indicates
public R/W status of a bucket: {"none", "upload", "download",
"public"}, whose names are borrowed from backend.

A __ts:pool-name__ entry is a last access timestamp of a pool.  It is
used to decide whether to stop a backend instance.

A __us:uid__ is an access timestamp of a user.  It is just a record.
It is used to find out inactive users (no tools are provided).

### Monokey-Table (DB=4)

| Key           | Value           | Notes   |
| ----          | ----            | ---- |
| pi:random     | key-description | \*1 |
| ky:random     | key-description | \*1 |

This table stores generated randoms for a pool-name or an access key.
An entry is inserted to keep its uniqueness.

A __pi:random__ entry is a pool-name and it is a record: {"owner",
"modification_time"}, where an owner is a uid.

A __ky:random__ entry is an access key and it is a record: {"owner",
"secret_key", "key_policy", "expiration_time", "modification_time"},
where an owner is a pool-name.  A key-policy is one of {"readwrite",
"readonly", "writeonly"}, whose names are borrowed from backend.

## Bucket policy

Public read/write policy is given to a bucket by Lens3.  Lens3 invokes
the mc command, one of the following.

```
mc policy set public alias/bucket
mc policy set upload alias/bucket
mc policy set download alias/bucket
mc policy set none alias/bucket
```

Accesses to deleted buckets in Lens3 are refused at Multiplexer, but
they remain potentially accessible in backend, which have access policy
"none" and are accessible using access keys.

## Keyval-DB Database Operations

A single keyval-db instance is used, and is not distributed.

It is usually required an uniqueness guarantee, such as for an
access keys and ID's for pools, and atomic set is suffice.  A failure
condition is only considered for MinIO endpoints, and timeouts are set
to "ma:pool-name" entries.  See the section Keyval-DB Database Keys.

Keyval-db client routines catches exceptions related to sockets (including
ConnectionError and TimeoutError).  Others are not checked at all by
Lens3.

Operations by an administrator is NOT mutexed.  Some operations should
be performed carefully.  They include modifications on the user-list.

## Pool State Transition

A bucket-pool will be in a state of: (None), __INITIAL__, __READY__,
__SUSPENDED__, __DISABLED__, and __INOPERABLE__.  A Multiplexer governs
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

### Multiplexer/Registrar systemd Services

All states of services are stored in keyval-db.  It is safe to stop/start
systemd services.

## Access Authorization Checks

Lens3's check is minimal.  A permission of acces-keys is r/w and a
permition of buckets is r/w.  It judges operations as reads by http
GET and writes by http PUT/POST.

Lens3 forwards requests to the backend S3 server that are signed by
the single root credential for the backend.

AWS S3 Documents:

* [How Amazon S3 authorizes a request](https://docs.aws.amazon.com/AmazonS3/latest/userguide/how-s3-evaluates-access-control.html)

## Building UI

Lens3 UI is created by vuejs+vuetify.  Lens3-v2.1 uses the same UI
code as v1.2.  The code for Vuetify is in the "v1/ui" directory.  See
[v1/ui/README.md](../../v1/ui/README.md) for building UI.

## Security

Security mainly depends on the setting of the frontend proxy.  Please
consult experts for setting up the proxy.  Accesses to Registrar are
authenticated as it is behind the proxy, and thus it is of less
concern.  Accesses to Multiplexer is restricted by checks on a pair of a
bucket and a secret.  The checks are in functions
"serve_XXX_access()".  Please review those functions intensively.

## Testing the Service

Release tests on Web-UI shall be performed manually.  Some of the
obvious errors of users should be reported properly.

### Unwritable bucket-directory

Making a pool for an unwritable bucket-directory is an error.  Check
the pool become inoperable.

### Unwritable bucket-directory for a bucket

Or, first make a pool, and then make the bucket-directory unwritable.
Making a bucket should fail.  This error should be visible to users as a
Web-UI error.  Check the pool does not become inoperable.

### Unwritable bucket

Making a bucket should be an error when a regular file exists with the
same name as the bucket.  This error should be visible to users as a
Web-UI error.  Check the pool does not become inoperable.

### Forced Heartbeat Failure

Kill by STOP the backend process.  It causes heartbeat failure.  Note
that it leaves backend and "sudo" processes in the STOP state.

### Forced Termination of Multiplexer and a backend

Kill the Lens3 services or the backend process.

### Forced Keyval-DB Server Down

Stopping the keyval-db is fatal.  Restarting Lens3 is needed.

- Do "chmod" on the keybal-db's store file or directory.
- Or, stop the keybal-db service.

### Forced Expiration of Multiplexer Entries in Keyval-DB

The action to fake a forced removal of a __ma:pool-name__ entry in
keyval-db should (1) start a new Multiplexer + backend pair, and then
(2) stop an old Multiplexer + backend pair.

### Force MQTT Server Down

Start/stop the MQTT server, randomly.

### Test Generated Garbages

Test programs will create garbages as bucket names
"lenticularis-oddity-XXX".

## Notes on Backends

### MinIO Clients (MC)

Note that alias commands are local (not connect to a MinIO).

### MinIO Start Messages

Lens3 recognizes some messages from MinIO at its start to judge a run
is successful.  A failure in starting MinIO makes the pool inoperable.
A message of level=FATAL is treated as erroneous, but level=ERROR is
not.  An exception is a port-in-use error which is level=FATAL.  Lens3
retries to start MinIO in that case.  The patterns of messages will
change by MinIO and MC versions.

The samples of messages from MinIO can be found in
[msg_minio.txt](../pkg/lens3/msg_minio.txt).

Lens3 looks for a message starting with "S3-API:" as a successful
start.

Lens3 also looks for a message "Specified port is already in use" for
a port-in-use error.  Starting a backend will be retried when this
message is found.

### rclone "rclone serve s3"

The current version of rclone (v1.66.0) does not work on (1) listing
objects (2) uploading large objects.

It does not support ListObjectsV2.  The old ListObjects works.

It does not support multipart transfer.  Uploads fail but downloads
work.  Note that the default of multipart threshold is 8MB.  It is
maybe extremely slow on large objects.

## Glossary

* __Probe-key__: It is an access key used by Registrar to access
  Multiplexer.  This key has no corresponding secret.  It is used to
  to make absent buckets in the backend.  It makes bucket records
  consistent in Lens3 and in the backend.

## Short-Term Todo, or Deficiency

* Avoid polling of a start of a backend.  Multiplexer waits for a start
  of a backend by polling in the keyval-db.

* Reject certain bucket-directory paths so that it does service in
  directories with dots.  Servicing in ".ssh" should be avoided, for
  example.

* Make Multiplexer reply a message containing a reason of an access
  rejection.  It returns only a status code in v1.2.

* Make it not an error when an MC command returns
  "Code=BucketAlreadyOwnedByYou".  It can be ignored safely.

* Make access key generation of Registrar like STS.

* Make UI refresh the MinIO state, when a pool is edited and
  transitions such as from READY to INOPERABLE or from SUSPENDED to
  READY.

* Run a reaper of orphaned directories, buckets, and secrets at a
  Registrar start.  Adding a bucket/secret and removing a pool may
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

__Removing buckets__: Lens3 does not remove buckets at all.  It just
makes them inaccessible.  It is because the contents of a bucket is
useful usually.

__MC command concurrency__: Lens3 assumes concurrently running
multiple MC commands with distinct aliases and distinct config-dirs do
not interfere.

__Backend start delay__: Lens3 responds to a request in slow on
starting a backend.  Alternatively, it can be returning 503 with a
"Retry-After" http header.  NGINX (a proxy in front of Lens3) seems to
return 502 on long delays.  See
[rfc7231](https://httpwg.org/specs/rfc7231.htm).

__Proxying errors__: Lens3 returns HTTP status 503 on an error in
proxying a request (that is, when it fails to perform proxying itself
such as by a connection error).  It is because backends refuse
connections when they are busy.  For example,

* MinIO refuses a connection by ECONNRESET sometimes, maybe, at a
slightly high load (not checked for Lens3-v2).

* MinIO also refuses a connection by EPIPE for some illegal accesses.
That is, when trying to put an object by a readonly-key or to put an
object to a download-bucket without a key (never happens in Lens3-v2
because checkes on keys are done in Lens3).

__Accepting pool creation in busy situations__: Lens3 accepts creation
of a pool even if it cannot start a backend due to busyness of the
server.  It is done on purpose to display the error condition in UI's
"backend_state" slot.

__HTTP status__: AWS S3 clients retries for status 50x except 501.
See https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/aws/retry
