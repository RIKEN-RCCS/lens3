# Lenticularis-S3 User's Guide

## Quick Setup of Buckets

Accessing the Web UI first shows __Manage Pools__ section.  A
_bucket-pool_ or a _pool_ is a directory to hold buckets.  Each pool
corresponds to a single MinIO instance.  Buckets and access keys are
associated to a pool.

The first step is to create a pool.  Fill a directory as a full path
and select a unix group, then click the create button (a plus icon).
The directory needs to be writable to the user:group pair.

![Landing page screenshot](ug1.jpg)

__List Pools__ section shows a list of existing pools.  It is a slider
list.  Check the MinIO-status of the pool just created.  It should be
_ready_.  A pool in _inoperable_ state is unusable (often, the reason
is the directory is not writable).

Select a pool by clicking the edit button (a pencil icon).  It opens
__Edit a Pool__ section.  Or, delete a pool by clicking the delete
button (a trash-can icon).

![Pool list screenshot](ug2.jpg)

__Edit a Pool__ section has two independent subsections -- one for
buckets and the other for access keys.

A bucket has a bucket-policy that specifies a permission to public
access: _none_, _upload_, _download_, or _public_.  A bucket with the
_none_-policy is accessible only with access-keys.  These policy names
are taken from MinIO.

An access-key has a key-policy: _readwrite_, _readonly_, or
_writeonly_.  Accesses to buckets are restricted by these policies.
These policy names are taken from MinIO.  An expiration date must be a
future.  An expiration date is actually a time in second, but the UI
only handles it by date at midnight UTC.

![Pool edit screenshot](ug3.jpg)

The last figure shows a screenshot after some operations.  It has one
private bucket and two access keys (one readwrite, one readonly).

The S3-endpoint URL can be found in the menu at the top-left corner.

![Pool list screenshot](ug4.jpg)

### Simple UI

The current UI is created with vuejs+vuetify.  It is not good for your
taste, try simple UI.  Simple UI reveals interactions with Web-Api.
If you are currently accessing the UI by a URL ending with
".../ui/index.html", the simple UI is avaiable at
".../ui2/index.html".

## S3 Client Access Example

The following example shows accessing an endpoint using the AWS CLI.
An access-key pair can be obtained by Lens3 Web-API.  Lens3 only works
with the signature algorithm v4, and it is specified as "s3v4".

```
$ cat ~/.aws/config
[default]
s3 =
    signature_version = s3v4

$ cat ~/.aws/credentials
[default]
aws_access_key_id = WoRKvRhrdaMNSlkZcJCB
aws_secret_access_key = DzZv57R8wBIuVZdtAkE1uK1HoebLPMzKM6obA4IDqOhaLIBf

$ aws --endpoint-url=http://lens3.example.com/ s3 ls s3://somebucket1/
```

### Diagnosing Access Errors

Accesses rejected at Lens3 only return status numbers but no error
messages.  It is on the todo list.

## Overview of Lens3

| ![lens3-setting](lens3-setting.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 consists of Lens3-Mux and Lens3-Api -- Lens3-Mux is a
multiplexer and Lens3-Api is a setting Web-API.  Others are by
third-parties.  MinIO is an open-source but commercially supported S3
server.  Redis is an open-source database system.  A reverse-proxy is
not specified in Lens3 but it is required for operation.

Lens3-Mux works as a proxy which forwards file access requests to a
MinIO instance by looking at a bucket name.  Lens3-Mux determines the
target MinIO instance using an association of a bucket and a user.
This association is stored in the Redis database.

Lens3-Mux is also in charge of starting and stopping a MinIO instance.
Lens3-Mux starts a MinIO instance on receiving an access request, and
after a while, Lens3-Mux stops the instance when it becomes idle.
Lens3-Mux starts a MinIO instance as a user process using "sudo".

Lens3-Api provides management of buckets.  Lens3-Api manages buckets
by a bucket pool, which is a unit of management in Lens3 and
corresponds to a single MinIO instance.  A user first creates a bucket
pool, then registers buckets to the pool.

## Bucket-Pool State (MinIO-state)

A bucket-pool is a management unit of S3 buckets in Lens3 and it has a
state reflecting the state of a MinIO instance (MinIO-state).  But,
the state does not include the process status of an instance.

Bucket-pool state is:
* __None__ quickly moves to the __INITIAL__ state.
* __INITIAL__ indicates a setup is not performed on a MinIO
    instance.
* __READY__ indicates a service is ready, a setup for servicing is
    done.  It does not mean a MinIO instance is running.
* __SUSPENED__ indicates a pool is temporarily unusable by server
    busyness.  It needs several minutes for a cease of the
    condition.
* __DISABLED__ indicates a pool is set unusable.  A transition
    between __READY__ and __DISABLED__ is by actions by an
    administrator.  The causes of a transition include an expiry of a
    pool, disabling a user account, or making a pool offline.
* __INOPERABLE__ indicates an error state and a pool is permanently
    unusable.  Mainly, it has failed to run a MinIO instance.  This
    pool cannot be used and should be removed.

Deletions of buckets and secrets are accepted during the suspension
state of a pool.  However, it delays to make a user's action take
effect, since it is unable to start a MinIO instance in the suspension
state.  In contrast, additions of buckets and secrets are rejected
immediately.

## Troubleshooting (Typical Problems)

* A failure in starting MinIO makes the pool INOPERABLE.  For
  diagnosing, the reason button on UI shows the message from MinIO.
  However, it may not help much.  It is just `"Invalid arguments
  specified"` that is the same despite of the reason.  A message of
  earlier versions of MinIO was more helpful.

* Starting MinIO may fail after updating MinIO and its MC command.
  MinIO server stores its state in a directory ".minio.sys" in the
  directory it services for.  The state can be incompatible between
  versions, and it makes the pool INOPERABLE.  Recovering from the
  problem needs two steps: remove the directory ".minio.sys", and
  delete the pool.

* Recreating a bucket once removed in the same directory causes an
  internal error.  Lens3 leaves the contents of a removed bucket, and
  the residue state causes an error.  It is necessary to remove the
  directory of the bucket, first.  Internally, MinIO issues an error
  with "Code=BucketAlreadyOwnedByYou".

## Restrictions of Lens3

### No Bucket Operations

Lens3 does not accept any bucket operations: creation, deletion, and
listing.  Buckets can only be managed via Lens3-Api.  Specifically, a
bucket creation request will fail because the request (applying to the
root path) is not forwarded to a MinIO instance.  A bucket deletion
will succeed, but it makes the states of Lens3 and a MinIO instance
inconsistent.  Bucket listing also fails because a request is not
forwarded.

Note: Lens3 manages a run of a MinIO instance and stops the instance
when it becomes idle.  At restarting a MinIO instance, Lens3 tries to
restore the state of buckets and that results in a deleted bucket to
be recreated.

### Bucket Naming Restrictions

Bucket names must be in lowercase alphanums and "-" (minus).  Note
that Lens3 bans a dot.  In addition, Lens3 bans names "aws", "amazon",
"minio" and the names that begin with "goog" and "g00g".

### No Control on File and Bucket Properties

Lens3 does not provide control on properties of files and buckets.
Buckets can only have a public access policy.

### Residue Files

Running MinIO leaves a directory ".minio.sys" in the buckets-directory
of the pool.

### No Access Logs

Lens3 does not provide access logs to users, although we understand it
is useful to users.  Administrators may provide access logs to users
by request by filtering server logs.

## Other Limitations

* S3 operations are restricted to simple ones to objects.
* No STS support.
* No event notifications support.
* Lens3 does not support listing of buckets by `aws s3 ls`.  Simply,
  Lens3 prohibits accesses to the "/" of the bucket namespace.  It is
  because the bucket namespace is shared by multiple users (and MinIO
  instances).
* Lens3 does not support S3 CLI "presign" command.  Lens3 does not
  recognize a credential attached in a URL.
* Lens3 does not provide accesses to the rich UI of MinIO or the MC
  command.

## Glossary

* __bucket pool__: A management unit of S3 buckets.  It corresponds to
  a single MinIO instance.
* __probe access__: Lens3-Api or the administrator tool accesses
  Lens3-Mux to start a MinIO instance.  Such access is called a probe
  access.  A probe access is dropped at Lens3-Mux and not forwarded to
  a MinIO instance.

## Changes from v1.2 to v1.3

* MinIO version is fixed to use the legacy "fs"-mode (it is quite
  old).  In a recent development of erasure-coding, MinIO uses chunked
  files in storage, which would not be suitable for
  importing/exporting existing files.

## Changes from v1.1 to v1.2

* Host-style naming of buckets is dropped.
* Accesses are forwarded to MinIO with respect to a pair of a bucket
  name and an access key.  Forwarding decision was only by an access
  key in v1.1.  This change prohibits performing S3's bucket
  operations, because bucket operations are not forwarded.
* Bucket name space is shared by all users.  Bucket names must be
  distinct.
* Access keys have expiration.
* Rich features are dropped.
* Some locks in accessing a database are omitted.  Operations by
  Lens3-Api and the administrator tool is sloppy.
* MC commands are directly invoked from Lens3-Api to change the
  setting of a MinIO instance.  MC commands were invoked at Lens3-Mux
  in v1.1.
