# Lens3

Lenticularis-S3 is a multiplexer to MinIO to service multiple MinIO
instances at a single access point.

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__

## Overview

Lenticularis-S3 (Lens3) provides an S3 service at a single access
point by running multiple MinIO instances.  MinIO is an S3 object
storage service.  Refer to [https://min.io](https://min.io) about
MinIO.  MinIO is usually started as a service running as a root
process, but Lens3 starts MinIO instances as non-root processes for
each user to confine unintended operations.

![lens3-overview](v1/doc/lens3-overview.svg)

Lens3 works as a reverse-proxy and a manager of MinIO instances.  It
launches a MinIO instance on an S3 request, redirects file access
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
code was reviewed by zzmatu and remaining bugs are his responsibility.

Lens3 utilizes third-party open source software, which is listed in
[acknowledgement](v1/ACKNOWLEDGEMENT.txt).  The directory
"test/s3-benchmark" is a third-party benchmark program, which is
copyrighted by wasabi-tech and the license is LGPL.

Files.

```
v1/doc           documents
v1/src/lenticularis source code
unit-file/api    daemon configuration templates
unit-file/mux    daemon configuration templates
unit-file/redis  daemon configuration templates
nginx            example templates of reverse-proxy configuration
apache           example templates of reverse-proxy configuration
test             test code
```
