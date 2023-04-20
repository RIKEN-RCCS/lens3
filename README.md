# Lens3

Lenticularis-S3 is a hub of MinIO to service multiple MinIO instances
at a single access point.

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__

## Overview

Lenticularis-S3 (Lens3) is a multiplexer to MinIO.  MinIO is an S3
object storage service.  It starts a MinIO instance as a non-root
process for each user to confine unintended operations.

Refer to [https://min.io](https://min.io) about MinIO.

Lens3 works as a reverse-proxy and a manager of MinIO instances.  It
launches a MinIO instance on a request, redirects S3 file access
requests to the instance, and manages the life-time of the instance.
This service, called "Mux", is started as a systemd service.  Lens3
also provides a simple Web-UI for managing a bucket pool.  A "bucket
pool" is a management unit in Lens3 which is associated to each MinIO
instance.  A Web-UI is used to register S3 buckets to a pool.  This
service, called "Api", is started as a systemd serivce.

## Guides

For users,
see [v1/doc/user-guide.md](v1/doc/user-guide.md).

For administrators,
see [v1/doc/admin-guide.md](v1/doc/admin-guide.md).

For site managers,
see [v1/doc/setting.md](v1/doc/setting.md).

For programmers,
see [v1/doc/design.md](v1/doc/design.md).

## Manifestation

Lens3 is copyrighted by RIKEN R-CCS.  Part of the results is
obtained by using Fugaku at RIKEN R-CCS.

Lens3 is developed by R-CSS and the [authors](AUTHORS.txt).  But, the
code was reviewed by zzmatu and all remaining bugs are his
responsibility.

Lens3 utilizes third-party open source software, which is listed in
[acknowledgement](v1/ACKNOWLEDGEMENT.txt).  The directory
"test/s3-benchmark" is a third-party benchmark program, which is
copyrighted by wasabi-tech and the license is LGPL.

Files.

```
v1/doc           documents
v1/src/lenticularis source code
unit-file/api    configuration templates
unit-file/mux    configuration templates
unit-file/redis  configuration templates
nginx            templates for reverse-proxy configuration
apache           templates for reverse-proxy configuration
test             test code
```
