# LENS3
Lenticularis-S3, a multiplexer to MinIO to service multiple MinIO instances at a single access point.

## Overview

Lenticularis-S3 (Lens3) is a multiplexer to MinIO for S3 object
storage service.  It starts a MinIO instance as a non-root process for
each user to confine unintended operations.  Lens3 launches a MinIO
instance on a request, redirects file access requests to an instance,
and manages the life-time of an instance.  Lens3 also provides simple
Web UI to service a pool manager.  A pool manager associates a bucket
pool to a directory, and the bucket names in the pool to the entries
in the directory.

## Installation

* See [doc/setting.md](doc/setting.md)

## Guides

For users,
see [doc/user-guide.md](doc/user-guide.md)

For administrators,
see [doc/admin-guide.md](doc/admin-guide.md)

## Manifestation

```
doc             documents
src             source code
test            test tools
redis           (Redis related files)
nginx           templates for reverse-proxy configuration
unit-file/webui         templates for configuration
unit-file/multiplexer   templates for configuration
devel           for developer
devel/lxc       lxc environment for developer
devel/install   install script for lxc
```
