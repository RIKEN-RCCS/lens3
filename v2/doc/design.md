# Design Notes of Lenticularis-S3

This describes design notes of Lenticularis-S3.

## Components of Lens3

* Multiplexer
* Registrar
* MinIO (S3 backend server)
* Valkey (keyval-db)

## Brief Description of Keyval-DB Entries

Keys in the keyval-db are prefixed by two characters plus colon, such
as "cf:mux".  All values are stored in json.

Most of the records used in the keyval-db are defined in "table.go".
The entries for configuration are defined in "conf.go".

Lens3 uses three keyval-db (by database numbers).
Multiplexer/Registrar service potentially makes three keyval-db
clients.  The division of databases is arbitrary as distinct prefixes
are added to keys.

A date+time is in unix seconds.  Registrar communicates a date+time
with Web-UI in unix seconds, too.

NOTE: In the tables below, entries with "(\*1)" are set atomically,
and entries with "(\*e)" are set with expiration.

### Setting Entries (DB-NUMBER=1)

| Key             | Record            | Notes |
| ----            | ----              | ---- |
| cf:mux          | mux_conf          | Defined in "conf.go" |
| cf:reg          | reg_conf          | Defined in "conf.go" |
| uu:_uid_        | user_record       | User record |
| um:_claim_      | user_claim_record | ID claim mapping |

These are semi-static information.

__cf:reg__ and __cf:mux__ (these are literal key strings) entries
store the settings of services.  __cf:mux:mux-name__ is a variant to
cf:mux, and used to choose a specific setting to Multiplexer service.
The mux-name is a string passed as a command argument to a service.

Primary reason for storing configuration settings (cf:mux and cf:reg)
in the keyval-db is to let them parsed in advance.  Detecting typos at
the start of a service is very annoying.

__uu:uid__ entry is a record of a user with user's GID and the enabled
status.  It may be added by an administrator tool, or, may be added
automatically when a user accesses Registrar.  Automatically added
entries are marked by ".Ephemeral=true".

__um:claim__ entry is to map a user claim to a UID, where a claim is
an ID passed by authentication.  It is used when Registrar is
configured with "claim_uid_map=map".

### Storage Entries (DB-NUMBER=2)

| Key            | Record                  | Notes |
| ----           | ----                    | ---- |
| po:_pool-name_ | pool_record             | Pool data |
| bd:_directory_ | bucket_directory_record | (\*1) Directory path |
| px:_pool-name_ | pool_name_record        | (\*1) Mutex for a pool-name |
| bx:_bucket_    | bucket_record           | (\*1) Bucket data |
| sx:_secret_    | secret_record           | (\*1) Access key pair data |

__po:pool-name__ entry is pool data.  It holds the static part of pool
information.

__bd:directory__ entry is a bucket-directory.  It is atomically
assigned, because Lens3 forbids to run multiple backends on the same
directory.  Note, however, links to directories can fool the
uniqueness.

__px:pool-name__ entry is used to make a pool-name unique.  Lens3 uses
a generated random for a pool-name.

__bx:bucket__ entry stores bucket data.  It is atomically assigned to
mutex the bucket name.  The bucket namespace is shared by all users.

__sx:secret__ entry stores access key data.  The key is a generated
random.

### Process Entries (DB-NUMBER=3)

| Key               | Record               | Notes |
| ----              | ----                 | ---- |
| mu:_mux-endpoint_ | mux_record           | (\*e) Multiplexer endpoint |
| de:_pool-name_    | backend_record       | (\*e) |
| dx:_pool-name_    | backend_mutex_record | (\*1 \*e) |
| tn:_uid_          | csrf_token_record    | Tokens for CSRF countermeasure |
| ps:_pool-name_    | blurred_state_record | Approximate state of a pool |
| pt:_pool-name_    | int64                | Timestamp of last access |
| ut:_uid_          | int64                | Timestamp of last access |

These are dynamic information and updated frequently.

__mx:mux-endpoint__ entry is an endpoint of Multiplexer.  It is
periodically updated by Multiplexer to notify it is running.

__de:pool-name__ entry stores backend process data.  The data is used
to forward requests to a backend.  A pair of "Root_access" +
"Root_secret" specifies an administrator access to a backend.

__dx:pool-name__ entry is a mutex of starting a backend.  It is used
to ensure only a single backend starts.

__tn:uid__ entry stores a token pair for CSRF countermeasure.

__ps:pool-name__ entry is an approximate pool state.  It is used to
show via Web-UI a pool is in the suspended state.  It keeps lingering
state information, because precise state information lasts only for a
short time.

__pt:pool-name__ entry is a last access timestamp of a pool.  It is
used to decide when to stop a backend.

__ut:uid__ entry is a last access timestamp of a user.  It is used to
find out inactive users.

### CONSISTENCY OF ENTRIES.

Some entries are dependent each other.  Crash-recovery should remove
orphaned enties.

__uu:uid and um:claim__.  UID ↔︎ claim is one-to-one if a user-info
contains a claim.

__bd:directory and bk:bucket-name__.

## Pool State Transition

A bucket pool will be in a state of: __INITIAL__, __READY__,
__SUSPENDED__, __DISABLED__, and __INOPERABLE__.  See the explanation
in [User-Guide](user-guide.md#bucket-pool-state).

Manager governs a transition of a state.  However, transition is
implicit, that is, Lens3 keeps no explicit record.  Manager calculates
the condition.

- __INITIAL__ → __READY__: Don't care.  INITIAL and READY are
  synonymous in Lens3-v2.
- __READY__ → __DISABLED__: It is by some setting that disables a
  pool.  It includes disabling a user account, an expiry of a pool, or
  making a pool offline.
- __DISABLED__ → __READY__: It is by a cease of a disabling condition.
- __READY__ → __SUSPENDED__: The move is on a condition the server is
  busy, when all reserved ports are used.
- __SUSPENDED__ → __READY__: The move is done after some time
  duration.  It will move back and forward between READY and SUSPENDED
  states if the condition remains.
- __READY__ → __INOPERABLE__: It is by a failure of starting a
  backend.  This state is a deadend.  The only operation allowed on an
  INOPERABLE pool is to remove it.

Deleting buckets and secrets during suspension will alter only the
state of Lens3 but not the state of a backend (becuase a backend is
not running).

## Bucket Deletion

Lens3 Registrar never deletes buckets in the backend.  It just removes
it from the namespace.  A user can delete a bucket via the S3 delete
bucket operaion.  However, the deleted status is not reflected in
Lens3's status.

## Keyval-DB Operations

A single keyval-db instance is used and is not distributed in Lens3.

Keyval-db client routines catches exceptions related to sockets (including
ConnectionError and TimeoutError).  Others are not checked at all by
Lens3.

Operations by an administrator tool is NOT mutexed.  Some operations
should be performed carefully.

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

### User Tests

- Disable a user.  It is done by `$ lens3-admin stop-user true uid`
- Delete a user.  It is done by `$ lens3-admin kill-user uid`

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

* Make UI refresh the pool state, when a pool is edited and
  transitions such as from READY to INOPERABLE or from SUSPENDED to
  READY.

* Run a reaper of orphaned directories, buckets, and secrets at a
  Registrar start.  Adding a bucket/secret and removing a pool may
  have a race.  Or, a crash at creation/deletion of a pool may leave
  an orphaned directory.

* Make starting a backend through the frontend proxy.  Currently,
  arbitrary Multiplexer is chosen.  The proxy could balance the loads.

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
