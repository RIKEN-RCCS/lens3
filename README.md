# Lens3

Lenticularis-S3 is a hub of MinIO to service multiple MinIO instances
at a single access point.

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__

## Overview

Lenticularis-S3 (Lens3) is a multiplexer to MinIO, an S3 object
storage service.  It starts a MinIO instance as a non-root process for
each user to confine unintended operations.

Lens3 works as a reverse-proxy and a manager of MinIO instances.  It
launches a MinIO instance on a request, redirects S3 file access
requests to the instance, and manages the life-time of the instance.
This service, called "Mux", is started as a systemd service.  Lens3
also provides a simple Web-UI for managing a bucket pool.  A "bucket
pool" is a management unit in Lens3 which is associated to each MinIO
instance.  A Web-UI is used to register S3 buckets to a pool.  This
service, called "Wui", is started as a systemd serivce.

See [MinIO](https://min.io).

## Installation

* See [doc/setting.md](doc/setting.md).

## Guides

For users,
see [doc/user-guide.md](doc/user-guide.md).

For administrators,
see [doc/admin-guide.md](doc/admin-guide.md).

For programmers,
see [doc/design.md](doc/design.md).

## Manifestation

This product is copyrighted by RIKEN R-CCS.  Part of the results is
obtained by using Fugaku at RIKEN R-CCS.

This system is developed by the [Authors](AUTHORS.txt).  But, the
code was reviewed by zzmatu and all remaining bugs are his
responsibility.

Files.

```
doc              documents
src/lenticularis source code
unit-file/mux    configuration templates
unit-file/redis  configuration templates
unit-file/wui    configuration templates
nginx            templates for reverse-proxy configuration
test             test code
```
