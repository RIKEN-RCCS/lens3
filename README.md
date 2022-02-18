Copyright (c) 2022 RIKEN R-CCS

# lens3
Lenticularis-S3, a multiplexer to MinIO to service multiple MinIO instances at a single access point.

# OVERVIEW

Lenticularis is an S3 compatible autonomous object storage service system.  
End users can launch their own object storage service (called zone) 
via Web UI.  Zone consists of Access Key set, location of buckets on file 
system, and meta information such as expiration date or user/group-id 
for the S3 server.

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

# INSTALL

see docs/install.md

# Documents

for Administrator,
see docs/administrators-guide.md

for User,
see docs/users-manual.md


# MANIFESTO

devel		for developer
devel/lxc       lxc environment for developer
devel/install   install script for lxc
docs		documents
etc		templates for multiplexer's configuration files
reverseproxy	templates for reverse proxy's configuration files
src		source code
test		test tools
webui		templates for API's configuration files

[eof]
