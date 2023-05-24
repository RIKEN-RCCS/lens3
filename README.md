# Lens3

Lenticularis-S3 is a multiplexer to MinIO to service multiple MinIO
instances at a single access point.

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__

## Overview

Lenticularis-S3 (Lens3) provides an S3 service by running multiple
MinIO instances at a single access point.  MinIO is an S3 object
storage service, and refer to [https://min.io](https://min.io) about
MinIO.  While MinIO is usually started as a root process, Lens3 starts
MinIO instances as non-root processes to confine unintended operations
to each user.

| ![lens3-overview](v1/doc/lens3-overview.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 works as a reverse-proxy and a manager of MinIO instances.  It
launches a MinIO instance on an S3 request, redirects file access
requests to the instance, and manages the life-time of the instance.
This service, called "Lens3-Mux", is started as a systemd service.
Lens3 also provides a simple Web-UI for managing a bucket pool.  A
"bucket pool" is a management unit in Lens3 which is associated to
each MinIO instance.  A Web-UI is used to register S3 buckets to a
pool.  This service, called "Lens3-Api", is started as a systemd
serivce, too.

## Guides

For users,
see [v1/doc/user-guide.md](v1/doc/user-guide.md).

For administrators,
see [v1/doc/admin-guide.md](v1/doc/admin-guide.md).

For site managers,
see [v1/doc/setting.md](v1/doc/setting.md).

For programmers,
see [v1/doc/design.md](v1/doc/design.md).

## ACKNOWLEDGEMENT

Lens3 is copyrighted by RIKEN R-CCS.  Part of the results is
obtained by using Fugaku at RIKEN R-CCS.

Lens3 utilizes third-party open source software, which is listed in
[acknowledgement](v1/ACKNOWLEDGEMENT.txt).  It may fail to include
software transitively used.  The directory "test/s3-benchmark" is a
third-party benchmark program, which is copyrighted by Wasabi-Tech and
is licensed with LGPL.

Lens3 uses MinIO as a backend S3 server.  Lens3 lacks a way to display
a credit to MinIO, because it blocks accesses to MinIO's user
interfaces.  Please refer to [https://min.io](https://min.io).

Lens3 UI is created with vuejs+vuetify.  Please refer to
[https://vuejs.org](https://vuejs.org/) and
[https://vuetifyjs.com](https://vuetifyjs.com/en/).

Lens3 is developed by R-CSS and the [authors](AUTHORS.txt).  But, the
code was reviewed by zzmatu and remaining bugs are his responsibility.

## Directories

```
v1/doc               documents
v1/src/lenticularis  source code
v1/ui                UI source code (Vuetify)
unit-file            configuration and systemd templates
nginx                example settings of a proxy
apache               example settings of a proxy
test                 test code
```
