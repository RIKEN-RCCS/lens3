# Lenticularis-S3 User's Guide

## Quick Setup of Buckets

Accessing the management Web-API site first shows the two buttons:
"New bucket pool" and "Show bucket pools".  Click "New bucket pool".

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

## Overview of Lens3

| ![lens3-setting](lens3-setting.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 consists of Lens3-Mux and Lens3-Api -- Lens3-Mux is a
multiplexer and Lens3-Api is a setting Web-API.  Others are by
third-parties.  MinIO is an open-source but commercially supported S3
server.  Redis is an open-source database system.  A reverse-proxy is
not specified in Lens3 but it is required for operation.

Lens3-Mux works as a reverse-proxy which forwards file access requests
to an MinIO instance by looking at a bucket name.  Lens3-Mux
determines the target MinIO instance using an association of a bucket
and a user.  This association is stored in a Redis database.
Lens3-Api provides management of buckets.  Lens3-Api manages buckets
by a bucket pool, which is a unit of a management in Lens3 and
corresponds to a single MinIO instance.  A user first creates a bucket
pool, and then registers buckets to the pool.  Lens3-Mux is also in
charge of starting and stopping a MinIO instance.  Lens3-Mux starts a
MinIO instance on receiving an access request, and after a while,
Lens3-Mux stops the instance when accesses become idle.  Lens3-Mux
starts a MinIO instance as a user process using "sudo".

## Bucket-Pool State

A bucket-pool is a management unit of S3 buckets in Lens3 and it has a
state reflecting the state of a MinIO instance.  But, the state does
not include the process status of an instance.

* Bucket-pool state is:
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

Bucket names must be in lowercase alphanums and "-".  Lens3 bans dots.
Also, Lens3 bans names "aws", "amazon", "minio", and the names that
begin with "goog" and "g00g".

### No Control on File and Bucket Properties

Lens3 does not provide control on properties of files and buckets.  A
bucket can only have a public access policy.

### Residue Files

Running MinIO leaves a directory ".minio.sys" in the buckets-directory
of the pool.

### Access Logs

Lens3 does not provide access logs to users, although we understand it
is useful to users.  Administrators may provide access logs to users
by request by filtering server logs.

## Other Limitations

* No STS support.

* No event notifications support.

* Lens3 does not support listing of buckets by `aws s3 ls`.  Simply,
Lens3 prohibits accesses to the "/" of the bucket namespace, because
the bucket namespace is shared by multiple users (and MinIO
instances).

* Lens3 does not support S3 CLI "presign" command.  Lens3 does not
recognize a credential attached in an URL, and denies a bucket access
unless it is public.

* Lens3 does not provide accesses to the rich GUI of MinIO or the MC
  command.

## Glossary

* __bucket pool__: A management unit of S3 buckets.  It corresponds to
  a single MinIO instance.
* __probe access__: Lens3-Api or the administrator tool accesses
  Lens3-Mux to start a MinIO instance.  Such access is called a probe
  access.  A probe access is dropped at Lens3-Mux and not forwarded to
  a MinIO instance.

## Changes from v1.1 to v1.2

* Host-style naming of buckets is dropped.
* Accesses are forwarded by a bucket name.  Accesses were forwarded by
  an access key in v1.1.  This change prohibits bucket operations.
* Bucket name space become shared by all users.  Bucket names must be
  distinct.
* Rich features are dropped.
* Some locking in accessing Redis are omitted.  Operations by the
  administrator tool might be sloppy.
* MC commands are directly invoked at the Lens3-Api host to change the
  setting of a MinIO instance.  MC commands were only invoked at
  Lens3-Mux in v1.1.
