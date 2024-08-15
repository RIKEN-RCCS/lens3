# Lens3

Lenticularis-S3 is an AWS S3 multiplexer to service multiple server
instances at a single access point.

## Overview

Lenticularis-S3 (Lens3) provides an AWS S3 service at a single access
point while using an existing S3 server.  An S3 service is usually
owned by a single user (unix root), but it may not be acceptable by
site's security policy.  Lens3 starts multiple S3 servers (backend
server instances) one for each user, which confines operations by
user's permission.

Lens3 uses MinIO as an S3 object storage server.  MinIO is an
open-source, commercially supported S3 server.  Please refer about
MinIO to [https://min.io](https://min.io/).

| ![lens3-overview](./v2/doc/lens3-overview.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 works as a proxy and a manager of MinIO instances.  It launches
a MinIO instance on an S3 request, redirects access requests to the
instance, and manages the life-time of the instance.  This service,
called "Lens3-Mux", is started as a systemd service.  Lens3 also
provides a simple Web-UI for managing bucket pools.  A "bucket pool"
is a management unit in Lens3 which is associated to each MinIO
instance.  A Web-UI is used to register S3 buckets to a pool.  This
service, called "Lens3-Api", is started as a systemd service, too.

## Guides

- [user-guide.md](./v2/doc/user-guide.md) for users.
- [admin-guide.md](./v2/doc/admin-guide.md) for administrators to
  maintain lens3 services.
- [setting-guide.md](./v2/doc/setting-guide.md) for site managers to
  install lens3 services.
- [design.md](./v2/doc/design.md) for programmers to debug.

## README

- [README v2](./v2/README.md)
- [README v1](./v1/README.md)

## ACKNOWLEDGMENT

Lens3 is copyrighted by RIKEN R-CCS.  Part of the results is
obtained by using Fugaku at RIKEN R-CCS.

Lens3 is developed by RIKEN R-CCS and by the external authors
S. Nishioka and T. Ishibashi.  The code was reviewed by zzmatu and
remaining bugs are his sole responsibility.

Lens3 uses MinIO as a backend S3 server.  Lens3 lacks a way to display
a credit to MinIO, because it blocks accesses to MinIO's user
interfaces.  Please refer to [https://min.io](https://min.io/).

Lens3 UI is created with vuejs+vuetify.  Please refer to
[https://vuejs.org](https://vuejs.org/) and
[https://vuetifyjs.com](https://vuetifyjs.com/en/).

[Third party software for v2](./v2/THIRDPARTY.md)

[Third party software for v1](./v1/THIRDPARTY.md)

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__
