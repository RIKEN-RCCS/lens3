# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

- Multiplexer + Registrar
- S3 backend server (MinIO)
- Keyval-db (Valkey)

## Brief Description of Keyval-DB Entries

Keys in the keyval-db are prefixed by two characters plus colon, such
as "cf:mux".  All values are stored in json.  Most of the value
records are defined in "table.go".  The other entries for
configuration are defined in "conf.go".

Lens3 uses three keyval-db (by database numbers).  The Lens3 service
(Multiplexer and Registrar) potentially makes three keyval-db clients.
The division of databases is arbitrary as the prefixes in keys are
distinct.

A date+time is in unix seconds.  Registrar communicates a date+time
with Web-UI in unix seconds, too.

NOTE: In the tables below, entries with "(\*1)" are set atomically,
and entries with "(\*e)" are set with expiration.

### Setting Entries (DB-NUMBER=1)

| Key             | Record (struct)   | Notes |
| ----            | ----              | ---- |
| cf:mux          | mux_conf          | Defined in "conf.go" |
| cf:reg          | reg_conf          | Defined in "conf.go" |
| uu:_uid_        | user_record       | User record |
| um:_claim_      | user_claim_record | ID claim mapping |

These are semi-static information.

__cf:reg__ and __cf:mux__ (these are literal key strings) entries
store the settings of the services.  __cf:mux:mux-name__ is a variant
to cf:mux, which is for choosing a specific setting to Multiplexer.
The mux-name may be passed as a command argument to the service.

Primary reason for storing configurations (cf:mux and cf:reg) in the
keyval-db is to let them parsed in advance.  Detecting typos at the
start of a service is annoying.

__uu:uid__ entry is a record of a user with user's GID and the enabled
status.  It may be added by an administrator tool, or, may be added
automatically when a user accesses Registrar.  Automatically added
entries are marked by "Ephemeral=true".

__um:claim__ entry maps a user claim to a UID, where a claim is an ID
passed by an authentication such as OIDC.  It is used when Registrar
is configured with "claim_uid_map=map".

### Storage Entries (DB-NUMBER=2)

| Key            | Record (struct)         | Notes |
| ----           | ----                    | ---- |
| po:_pool-name_ | pool_record             | Pool data |
| bd:_directory_ | bucket_directory_record | (\*1) Directory path |
| px:_pool-name_ | pool_name_record        | (\*1) Mutex for a pool-name |
| bx:_bucket_    | bucket_record           | (\*1) Bucket data |
| sx:_secret_    | secret_record           | (\*1) Access key pair data |

__po:pool-name__ entry is pool data.  It stores the static part of
pool data.

__bd:directory__ entry is a bucket-directory.  It is atomically
assigned, because Lens3 forbids to run multiple backends on the same
directory.  Note, however, links to directories can fool uniqueness.

__px:pool-name__ entry is used to make a pool-name unique.  Lens3 uses
a generated random as a pool-name.

__bx:bucket__ entry stores bucket data.  The bucket name is assigned
in mutex, because the bucket namespace is shared by all users.

__sx:secret__ entry stores access key data.  The key is a generated
random.

### Process Entries (DB-NUMBER=3)

| Key               | Record (struct)      | Notes |
| ----              | ----                 | ---- |
| mu:_mux-endpoint_ | mux_record           | (\*e) Multiplexer endpoint |
| de:_pool-name_    | backend_record       | (\*e) |
| dx:_pool-name_    | backend_mutex_record | (\*1 \*e) |
| tn:_uid_          | csrf_token_record    | Tokens for CSRF countermeasure |
| ps:_pool-name_    | blurred_state_record | Approximate state of a pool |
| pt:_pool-name_    | int64                | Timestamp of last access |
| ut:_uid_          | int64                | Timestamp of last access |

These are dynamic information and updated frequently.

__mu:mux-endpoint__ entry is an endpoint of Multiplexer.  It is
periodically updated by Multiplexer to notify it is running.

__de:pool-name__ entry stores backend process data.  It is used to
forward requests to a backend.  This record exists while a backend is
running.  An entry can be a dummy, when the pool is suspended, which
blocks a backend from starting.  The record includes an access key to
a backend.  "Root_access" + "Root_secret" is an administrator key pair
to a backend.

__dx:pool-name__ entry is a mutex of starting a backend.  It is used
to ensure only a single backend starts.

__tn:uid__ entry stores a token pair for CSRF countermeasure.  CSRF is
cross-site request forgery.

__ps:pool-name__ entry is an approximate pool state.  It is used to
show the state of a pool via Web-UI.  It keeps lingering state
information (of the suspended state), because precise state
information lasts only for a short time.

__pt:pool-name__ entry is a last access timestamp of a pool.  It is
used to decide when to stop a backend.

__ut:uid__ entry is a last access timestamp of a user.  It is used to
find out inactive users.

### Consistency of Entries

Some entries are dependent each other.  Crash-recovery should remove
orphaned entries.  (Crash-recovery is not implemented).

A pool record __po:pool-name__ owns its component records.  The
description of a pool is furnished with the sub-records
__bd:directory__, __bx:bucket__, and __sx:secret__.

A user record __uu:uid__ owns its claim __um:claim__.  They are kept
one-to-one if a user information contains a claim.

## Pool State Transition

A bucket pool will be in one of the states: __INITIAL__, __READY__,
__DISABLED__, __SUSPENDED__, and __INOPERABLE__.  See the explanation
in [User-Guide](user-guide.md#bucket-pool-state).

Manager (a part of Multiplexer) governs the transition of a state.
However, transition is implicit, that is, Lens3 keeps no explicit
records.  Manager calculates the condition.

- __INITIAL__ → __READY__: Don't care.  INITIAL and READY are
  synonymous in Lens3-v2.1.
- __READY__ → __DISABLED__: It is by some setting that disables a
  pool.  It includes disabling a user account, an expiry of a pool, or
  making a pool offline.
- __DISABLED__ → __READY__: It is by a cease of a disabling condition.
- __READY__ → __SUSPENDED__: The move is on conditions that the server
  is busy or starting a backend timeouts.  The server is busy when all
  the reserved ports are used.
- __SUSPENDED__ → __READY__: The move is done after some duration.
  The state will move back and forward between READY and SUSPENDED
  while the condition remains.
- __READY__ → __INOPERABLE__: It is by a failure of starting a
  backend.  This state is a dead end.  The only operation allowed on
  INOPERABLE pools is to remove them.

Creating buckets and secrets during suspension will be rejected until
a backend resumes.

## Implementation Specifics

### Keyval-DB Operations

A single keyval-db instance is used, and it cannot be distributed in
Lens3-v2.1.

Operations by the administrator tool are not mutexed.  Some operations
should be performed carefully.

Keyval-db client routines don't catch exceptions at all in Lens3-v2.1
(including ones related to sockets).  Errors in the keyval-db are
fatal (it raises a panic).

### Authorization Checks

Lens3's authorization check is minimal.  It is only by
readable/writable.  A permission of access-keys can be R/W and a
permission of buckets can be R/W.  It judges operations as reads for
http GET and writes for http PUT/POST.

Lens3 forwards requests to the backend by signing with the root
credential for the backend.

AWS S3 Documents:

[How Amazon S3 authorizes a request](https://docs.aws.amazon.com/AmazonS3/latest/userguide/how-s3-evaluates-access-control.html)

### Security

Security mainly depends on the setting of the frontend proxy.  Please
consult experts for setting up the proxy.

Accesses to Registrar are assumed to be authenticated by the proxy.
Thus, security is of less concern for Registrar.

Accesses to Multiplexer is checked on a pair of a bucket and a secret.
The checks are performed in functions "serve_XXX_access()".  Please
review those functions intensively.

### Multiplexer systemd Service

All states of the service are stored in keyval-db.  It is safe to
stop/start systemd service.

## Building UI

Lens3 UI is created by vuejs+vuetify.  Lens3-v2.1 uses the same UI
code as v1.3.  The code for Vuetify is in the "v1/ui" directory.  See
[v1/ui/README.md](../../v1/ui/README.md) for building UI.

## Testing the Service

Release test on Web-UI shall be performed manually.  Obvious errors
should be reported to users properly (hopefully).

#### Unwritable bucket-directory

Making a pool with an unwritable bucket-directory is an error.  Check
the pool become inoperable.

#### Unwritable bucket-directory for a bucket

First make a pool normally, and then make the bucket-directory
unwritable.  Making a bucket should fail.  This error should be
noticeable to users.  The pool should NOT become inoperable.

#### Unwritable bucket

Making a bucket should be an error when a regular file exists with the
same name.  This error should be noticeable to users.  The pool should
NOT become inoperable.

#### User tests

Disable a user.  It is done by `$ lens3-admin stop-user true uid`

Delete a user.  It is done by `$ lens3-admin kill-user uid`

#### Forced backend start failure

A timeout in starting a backend make the pool suspended.  It happens,
for example, when the remote filesystem blocks its operations.  In
particular, MinIO doesn't even output the servicing URL in such cases.

To test such a condition, replace /usr/local/bin/minio with a dummy
command such as "sleep 3600".  It should cause a timeout.  Check the
pool should become suspended.

#### Forced backends down

Kill the backend process by STOP.  It causes heartbeat failure.  The
backend should be terminated.  Note that it would leave the backend
and "sudo" processes in the STOP state.

Or, kill the backend process, randomly.

#### Forced keyval-db down

Stopping the keyval-db is fatal.  Check an error is noticeable to
users.  Restarting Lens3 is needed.

- Stop the keybal-db service.

- Or, do "chmod" on the keybal-db's store file or directory.

#### Force MQTT server down

Start/stop the MQTT server, randomly.

#### Forced termination of the service

Stop or kill  the Lens3 service.

#### Generated garbage in tests

Test programs will create garbage as bucket names
"lenticularis-oddity-XXX".

## Notes on Backends

### MinIO Start Messages

Lens3 recognizes some messages from MinIO at its start to judge a run
is successful.  A failure in starting MinIO makes the pool inoperable.
A message of level=FATAL is treated as erroneous, but level=ERROR is
not.  An exception is a port-in-use error which is level=FATAL.  Lens3
retries to start MinIO in that case.  The patterns of messages will
change by MinIO and MC versions.

The samples of messages from MinIO can be found in
[msg_minio.txt](../lens3/lens3/msg_minio.txt).

Lens3 looks for a message starting with "S3-API:" as a successful
start.

Lens3 also looks for a message "Specified port is already in use" for
a port-in-use error.  Starting a backend will be retried when this
message is found.

### MinIO Clients (MC)

Note that alias commands are local (not connect to a MinIO).

### rclone "rclone serve s3"

The current version of rclone (v1.66.0) does not work on (1) listing
objects and (2) uploading large objects.

It does not support ListObjectsV2.  The old ListObjects works.  In AWS
CLI, it is necessary to use the low level API `$ aws s3api
list-objects`.

It does not support multipart transfer.  Uploads fail but downloads
work.  Note that the default of multipart threshold is 8MB.  It is
maybe extremely slow on large objects.

## Glossary

- __Probe-key__: It is an access key used by Registrar to access
  Multiplexer.  This key has no corresponding secret.  It is used to
  to make absent buckets in the backend.  It makes bucket records
  consistent in Lens3 and in the backend.

## Short-Term TODO, or Deficiency

- Avoid polling of a start of a backend.  Multiplexer waits for a start
  of a backend by polling in the keyval-db.

- Make Multiplexer reply messages in XML instead of json on an access
  rejection.  It only returned an http status code in v1.x.

- Make it not an error when MinIO returns the
  "BucketAlreadyOwnedByYou" error.  It can be ignored safely.

- Make access key generation of Registrar like STS.

- Make UI refresh the pool state, when a pool is edited and the state
  transitions.

- Run a reaper of orphaned records (bd:directory, bx:bucket, and
  sx:secret) at a Registrar restart.  Adding a bucket/secret and
  removing a pool may have a race.  Or, a crash at creation/deletion
  of a pool may leave an orphaned entry.

- Make starting a backend through the frontend proxy.  The proxy could
  balance the loads.  (It currently lacks the support for multiple
  hosts at all).

- Possible options
  - confirmation of terms-of-use at the first use.
  - disable public buckets.
  - description field to keys (just a memo).

## Random MEMO

- __Removing buckets__: Lens3 does not remove buckets at all.  It just
makes them inaccessible.  It is because the contents of a bucket is
useful usually.

- __MC command concurrency__: Lens3 assumes concurrently running
multiple MC commands with distinct aliases and distinct config-dirs do
not interfere.

- __Backend start delay__: Lens3 responds to a request in slow on
starting a backend.  Alternatively, it can be returning 503 with a
"Retry-After" http header.  NGINX (a proxy in front of Lens3) seems to
return 502 on long delays.  See
[rfc7231](https://httpwg.org/specs/rfc7231.htm).

- __Proxying errors__: Lens3 returns HTTP status 503 on an error in
proxying a request (that is, when it fails to perform proxying itself
such as by a connection error).  It is because backends refuse
connections when they are busy.  For example,

- __Accepting pool creation in busy situations__: Lens3 accepts
creation of a pool even if it cannot start a backend due to busyness
of the server.  It is done on purpose to display the error condition
in UI's "backend_state" slot.

- __HTTP status__: AWS S3 clients retries for status 50x except 501.
See https://pkg.go.dev/github.com/aws/aws-sdk-go-v2/aws/retry

- MinIO refuses a connection by ECONNRESET sometimes, maybe, at a
slightly high load (not checked for Lens3-v2.1).

- MinIO also refuses a connection by EPIPE for some illegal accesses.
That is, when trying to put an object by a readonly-key or to put an
object to a download-bucket without a key (never happens in Lens3-v2.1
because checkes on keys are done in Lens3).
