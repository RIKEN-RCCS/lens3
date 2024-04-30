# Lens3

Lenticularis-S3 is a multiplexer to multiple S3 server instances at a
single access point.

## Overview

Lenticularis-S3 (Lens3) provides an S3 service by running multiple S3
server instances at a single access point.  While an S3 server is
usually owned by a single user, Lens3 starts multiple S3 server
instances one for each user to confine operations by user's
permission.

| ![lens3-overview](./doc/lens3-overview.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 works as a proxy and a manager of S3 server instances.  It
launches a S3 server instance on an S3 request, redirects access
requests to the instance, and manages the life-time of the instance.
This service, called "Lens3-Mux", is started as a systemd service.
Lens3 also provides a simple Web-UI for managing bucket pools.  A
"bucket pool" is a management unit in Lens3 which is associated to
each S3 server instance.  A Web-UI is used to register S3 buckets to a
pool.  This service, called "Lens3-Api", is started as a systemd
serivce, too.

## Guides

[user-guide.md](./doc/user-guide.md) for users.

[admin-guide.md](./doc/admin-guide.md) for administrators to maintain
lens3 services.

[setting-guide.md](./doc/setting-guide.md) for site managers to install
lens3 services.

[design.md](./doc/design.md) for programmers to debug.

## ACKNOWLEDGEMENT

Lens3 is copyrighted by RIKEN R-CCS.  Part of the results is
obtained by using Fugaku at RIKEN R-CCS.

Lens3 uses MinIO as a backend S3 server.  Lens3 lacks a way to display
a credit to MinIO, because it blocks accesses to MinIO's user
interfaces.  Please refer to [https://min.io](https://min.io).

Lens3 is written in Golang-1.22.

Lens3 utilizes third-party open source software, which is listed in
[acknowledgement](./ACKNOWLEDGEMENT.txt).  It may fail to include
software transitively used.

Lens3 UI is created with vuejs+vuetify.  Please refer to
[https://vuejs.org](https://vuejs.org/) and
[https://vuetifyjs.com](https://vuetifyjs.com/en/).

Lens3 is developed by R-CSS and the [authors](AUTHORS.txt).  But, the
code was reviewed by zzmatu and remaining bugs are his responsibility.

__Lenticularis-S3 comes with ABSOLUTELY NO WARRANTY.__
