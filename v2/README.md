# Lens3

Lenticularis-S3 is a multiplexer to make multiple S3 server instances
accessible at a single access point.

## Overview

Lenticularis-S3 (Lens3) provides an S3 service by running multiple S3
server instances at a single access point.  While an S3 server is
usually owned by a single user, Lens3 starts multiple S3 servers one
for each user to confine operations by user's permission.

| ![lens3-overview](./doc/lens3-overview.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 works as a proxy and a manager of S3 servers.  It launches a S3
server instance on an S3 request, redirects access requests to the
instance, and manages the life-time of the instance.  This service,
called "Lens3-Multiplexer", is started as a systemd service.  Lens3
includes simple Web-UI for managing buckets and access keys.  They are
managed as a unit "bucket pool", which is associated to each S3 server
instance.  A Web-UI is used to register buckets and access keys to a
pool.

## Guides

- [user-guide.md](./doc/user-guide.md) for users.
- [admin-guide.md](./doc/admin-guide.md) for administrators to
  maintain lens3 services.
- [setting-guide.md](./doc/setting-guide.md) for site managers to
  install lens3 services.
- [design-notes.md](./doc/design-notes.md) for programmers to debug.

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

[THIRDPARTY](THIRDPARTY.md)

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__
