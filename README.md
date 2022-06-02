# Lens3

Lenticularis-S3, a hub of MinIO to service multiple MinIO services at
a single access point.

## Overview

Lenticularis-S3 (Lens3) is a multiplexer to MinIO, S3 object storage
service.  It starts a MinIO instance as a non-root process for each
user to confine unintended operations.

Lens3 works as a reverse-proxy and a manager of MinIO instances.  It
launches a MinIO instance on a request, redirects S3 file access
requests to the instance, and manages the life-time of the instance.
Lens3 also provides simple Web-UI, a pool manager, for registering S3
buckets.  A pool is a management unit of buckets and is associated to
a single directory in a filesystem.  A pool manager registers buckets
to a pool.

See [MinIO](https://min.io).

## Installation

* See [doc/setting.md](doc/setting.md).

## Guides

For users,
see [doc/user-guide.md](doc/user-guide.md).

For administrators,
see [doc/admin-guide.md](doc/admin-guide.md).

## Manifestation

```
doc              documents
src/lenticularis source code
unit-file/amd    configuration templates
unit-file/mux    configuration templates
unit-file/redis  configuration templates
nginx            templates for reverse-proxy configuration
test             test code
redis            (Redis related files)
devel            for developer
devel/lxc        lxc environment for developer
devel/install    install script for lxc
```
