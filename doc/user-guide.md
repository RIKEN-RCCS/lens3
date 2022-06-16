# Lenticularis-S3 User's Guide

## Quick Setup of Buckets

Accessing the management Web-UI site first shows the two buttons: "New
bucket pool" and "Show bucket pools".  Click "New bucket pool".

![Landing page](ug1.jpg)

The pool creation page is to create a _bucket pool_.  A bucket pool is
a management unit in Lens3 and it is associated to a directory in the
filesystem in which a MinIO will run.  Enter a directory (which needs
to be writable) and click the "Create" button.

![Pool creation page](ug2.jpg)

The pool edit page is to add buckets and access keys.  Click "Add" or
"New" buttons.  A bucket has a bucket-policy that specifies a
permission to public accesses: "none", "upload", "download", or
"public".  A bucket with the "none"-policy is accessible only with
access-keys.  These policy names are from MinIO.

Each access-key has a key-policy: "readwrite", "readonly", or
"writeonly".  Accesses to buckets/files are restricted by these
policies.  These policy names are from MinIO.

Clicking "Show bucket pool" on the top moves to a pool list page which
will display summaries of pools created.

![Pool edit page](ug3.jpg)

The pool list page shows a list of pools.  Clicking "Edit" moves back
to the page for addition of buckets and access keys.  Clicking "Delete"
removes the pool.

![Pool list page](ug4.jpg)

## S3 Client Access Example

The followng example shows an access to an endpoint using the AWS CLI.
An access-key pair is provided by Lens3 Web-UI.

```
$ cat .aws/credentials
[default]
aws_access_key_id = WoRKvRhrdaMNSlkZcJCB
aws_secret_access_key = DzZv57R8wBIuVZdtAkE1uK1HoebLPMzKM6obA4IDqOhaLIBf

$ aws --endpoint-url=http://lens3.example.com/ s3 ls s3://somebucket1/
```

## Overview of Lens3

```
(reverse-proxy) <+-->︎ Mux <+--> MinIO (per user)
                 |         +--> MinIO (per user)
                 |         +--> MinIO (per user)
                 +--> Api
                      Redis
```

Lens3 consists of Mux and Api -- Mux is a multiplexer and Api is a
setting Web-UI.  Others are by third party.  MinIO is an open-source
but commercially supported S3 server.  Redis is an open-source
database system.  A reverse-proxy is not a part of Lens3 but it is
required for operation.  Mux works as a reverse-proxy which forwards
file access requests to an MinIO instance by looking at a bucket name.
Mux determines the target MinIO instance using an association of a
bucket and a user.  This association is stored in a Redis database.
Api provides management of buckets.  Api manages buckets by a bucket
pool, which is a unit of management in Lens3 and corresponds to a
single MinIO instance.  A user first creates a bucket pool, and then
registers buckets to the pool.  Mux is also in charge of starting and
stopping a MinIO instance.  Mux starts a MinIO instance on receiving
an access request, and after a while, Mux stops the instance when
accesses become idle.  Mux starts a MinIO instance as a usual user
process using "sudo".

## Restrictions of Lens3

### No Bucket Operations

Lens3 does not accept any bucket operations: creation, deletion, and
listing.  Buckets can only be managed via Api.  Specifically, a bucket
creation request will fail because the request (applying to the root
path) is not forwarded to a MinIO instance.  A bucket deletion will
succeed, but it makes the states of Lens3 and a MinIO instance
inconsistent.  Bucket listing also fails because a request is not
forwarded.

Note: Lens3 manages a run of a MinIO instance and stops the instance
when it becomes idle.  At restarting a MinIO instance, Lens3 tries to
restore the state of buckets and that results in a deleted bucket to
be recreated.

### Bucket Naming Restrictions

Bucket names must be in lowercase alphanums and "-".  Lens3 bans dots.
Also, Lens3 bans names "aws", "amazon", "minio", and the names that
begin with "goog" and "g00g".

### No Control on File and Bucket Properties

Lens3 does not provide control on properties of files and buckets.  A
bucket can only have a public access policy.

### Residue Files

Running MinIO leaves a directory ".minio.sys" in the pool (in the
buckets-directory).

## Bucket-Pool State

A bucket-pool has a state reflecting the state of a MinIO instance.
It does not include the process status of a MinIO instance.

* Bucket-pool state
  * __None__ quickly moves to the INITIAL state.
  * __INITIAL__ indicates some setup is not performed yet on a MinIO
    instance (a transient state).
  * __READY__ indicates a service is ready, a setup for servicing is
    done.  It does not mean a MinIO instance is running.
  * __DISABLED__ indicates a pool is temporarily unusable.  It may
    transition between "READY" and "DISABLED" by actions of a user or
    an administrator.  The causes of a transition include an
    expiry of a pool, disabling a user account, or making a pool
    offline.
  * __INOPERABLE__ indicates an error state and a pool is permanently
    unusable.  Mainly, it has failed to run a MinIO instance.  This
    pool cannot be used and should be removed.

### Other Limitations

* No STS support.

* No event notifications support.

* Lens3 does not support listing of buckets by `aws s3 ls`.  Simply,
Lens3 prohibits accesses to the "/" of the bucket namespace, because
the bucket namespace is shared by multiple users (and MinIO
instances).

* Lens3 does not support S3 CLI "presign" command.  Lens3 does not
recognize a credential attached in an URL, and denies a bucket access
unless it is public.

## Glossary

* __bucket pool__: A management unit of S3 buckets.  It corresponds to
  a single MinIO instance.

## Changes from v1.1 to v1.2

* Host-style naming of buckets is dropped.
* Accesses are forwarded by a bucket name.  Accesses were forwarded by
  a access key in v1.1.  This change prohibits bucket operations.
* Bucket name space become shared by all users.  Bucket names must be
  distinct.
* Rich features are dropped.
* Some locking in accessing Redis are omitted.  Operations by the
  administrator tool might be sloppy.
* A MC command is directly invoked at Api host to change a setting of
  a MinIO instance.  A MC command was only invoked at Mux in v1.1.
