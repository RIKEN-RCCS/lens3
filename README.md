# LENS3
Lenticularis-S3, a multiplexer to MinIO to service multiple MinIO instances at a single access point.

# Overview

Lenticularis-S3 (LenS3) is a multiplexer to MinIO for S3 object
storage service.  LenS3 launches a MinIO instance for each user on
request, manages the lift-time of the instances, and redirects file
access requests to each instance.

End users can launch their own object storage service (called zone)
via Web UI.  Zone consists of Access Key set, location of buckets on
file system, and meta information such as expiration date or
user/group-id for the S3 server.

Once a zone is launched, on an S3 access to the zone, the system automatically
initiates S3 server (minio) for the targeted zone and start relaying the
session.  Zones are identified by Access Key and multiplexer distributes
S3 session to appropriate S3 server.  Inactive S3 server is automatically
purged to save system resources.

End users can give individual domain name to their zone, which can
be used as an dedicated endpoint (direct hostname) for the zone.
Access to direct hostname requires no S3 Access Key,
therefore access to a bucket of a zone that has direct hostname is
appropriately relayed by the system.  Putting the bucket to be public,
anonymous user may access to the bucket.

# Installation

* See [doc/overview.md](doc/overview.md)
* See [doc/setting.md](doc/setting.md)

# Guides

For administrators,
see [doc/administrator-guide.md](doc/administrator-guide.md)

For users,
see [doc/user-guide.md](doc/user-guide.md)

# Manifestation

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
