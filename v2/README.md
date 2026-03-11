# Lens3

Lenticularis-S3 is an AWS-S3 multiplexer to service multiple server
instances at a single access point.

## Overview

Lenticularis-S3 (Lens3) provides an AWS-S3 service at a single access
point while using an existing S3 server.  An S3 service is usually
owned by a single user (unix root), but it may not be acceptable by
site's security policy.  Lens3 starts multiple S3 servers (backend
server instances) one for each user, which confines operations by
user's permission.

| ![lens3-overview](./doc/lens3-overview.svg) |
|:--:|
| **Fig. Lens3 overview.** |

Lens3 works as a proxy and a manager of S3 server instances.  It
launches a server instance on an S3 request, redirects access requests
to the instance, and manages the life-time of the instance.  This
service, called "Lenticularis-Mux", is started as a systemd service.
Lens3 also provides a simple Web-UI for managing bucket pools.  A
"bucket pool" is a management unit in Lens3 which is associated to
each server instance.  A Web-UI is used to register S3 buckets to a
pool.  This service, called "Lenticularis-Reg", is integrated as a
thread to Lenticularis-Mux.

Lens3 uses S3-Baby-server as a backend S3 server.  Baby-server is a
small subset server for S3 designed to share files in usual
filesystems.  It is available in github.com:
[https://github.com/RIKEN-RCCS/s3-baby-server]([https://github.com/RIKEN-RCCS/s3-baby-server).

## Guides

  - [user-guide.md](./doc/user-guide.md) for users.
  - [admin-guide.md](./doc/admin-guide.md) for administrators to
    maintain lens3 services.
  - [setting-guide.md](./doc/setting-guide.md) for site managers to
    install lens3 services.
  - [installation-procedure.md](./doc/installation-procedure.md)
    also for site managers to change server configuration.
  - [design-notes.md](./doc/design-notes.md) for programmers to debug.

## ACKNOWLEDGMENT

Lens3 is copyrighted by RIKEN R-CCS.  Part of the results is
obtained by using Fugaku at RIKEN R-CCS.

Lens3 is developed by RIKEN R-CCS and by the external authors
S. Nishioka and T. Ishibashi.  The code was reviewed by zzmatu and
remaining bugs are his sole responsibility.

User interface of Lens3 is created with vuejs+vuetify.  Please refer
to [https://vuejs.org](https://vuejs.org/) and
[https://vuetifyjs.com](https://vuetifyjs.com/en/).

The lists of third party software Lens3 depends on are: [Third party
software for v2](./THIRDPARTY.md).
