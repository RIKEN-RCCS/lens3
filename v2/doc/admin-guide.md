# Lenticularis-S3 Administration Guide

## Administration Command (lens3-admin)

The "lens3-admin" command is used to modify keyval-db entries.  It is
installed in "~lens3/go/bin". Note that it does not mutex accesses by
Registrar, and moreover, modifications can be inconsistent.  The
command should typically be run on the same host of Lens3 services.
It will print the list of sub-commands by running
"lens3-admin -c conf.json".

### User and Pool Mangement

"lens3-admin" is used to list users or pools.

```
lens3$ lens3-admin -c conf.json show-user
lens3$ lens3-admin -c conf.json show-pool
```

Or, it can disable users or pools.

```
lens3$ lens3-admin -c conf.json stop-user true uid
lens3$ lens3-admin -c conf.json stop-pool true pool-name
```

### User Registration

"lens3-admin" is used to register users.  Registering users is
necessary when the configuration is "user_approval=block".

User list is modified by loading/storing a CSV file.  Loading a CSV file is
incremental, that is, it does not reset the whole data.

```
lens3$ lens3-admin -c conf.json load-user user-list.csv
lens3$ lens3-admin -c conf.json dump-user > user-list.csv
```

A CSV file consists of lines of {ADD, MODIFY, DELETE, ENABLE,
DISABLE}-rows.

ADD-row is: ADD,uid,claim,group,... (the rest is a group list).

It is one for each user.  The "claim" field is optional and only used
when the configuration is "claim_uid_map=map".  It is a user's key of
authentication returned by OIDC (OpenID Connect).  A group list needs
at least one entry.

MODIFY-row is simliar to ADD-row.  Adding resets the existing user and
deletes the pools it owned.  Modifying keeps the pools.

DELETE-row is: DELETE,uid,...

ENABLE-row and DISABLE-row are similar.

Rows in a CSV file are processed in the order that the all ADD/MODIFY
rows first, then DELETE, ENABLE, and DISABLE rows in this order.

Spaces around a comma or trailing commas are not allowed in CSV.

## System Maintenance

### Updating MinIO and Mc Binaries

MinIO and Mc commands should NOT be updated.  Note that Lens3 only
works with a specific old version of MinIO.

### Valkey Snapshot

Lens3 uses Valkey's "snapshotting" of the database.  The file location
and the snapshot interval can be found under the keywords
"dbfilename", "dir", and "save" in the configuration
"/etc/lenticularis/valkey.conf".  Lens3 uses "save 907 1", which is an
interval about 15 minutes.  Log-rotating of snapshots is recommended.

### Keyval-DB Backup

Backup of the keyval-db is done by dump-db and fill-db commands.  A
dump is a text file with keys and values.  A key part is a string, and
a value part is in json and it is indented by four spaces.

```
lens3$ lens3-admin -c conf.json dump-db
lens3$ lens3-admin -c conf.json fill-db dump.json
lens3$ lens3-admin -c conf.json wipe-out-db everything
```

## S3 Signature Algorithm Version

Lens3 works only with the signature v4.  That is, an authentication
header must include the string "AWS4-HMAC-SHA256".

## MinIO Vulnerability Information

* https://github.com/minio/minio/security
* https://blog.min.io/tag/security-advisory/
* https://www.cvedetails.com/vulnerability-list/vendor_id-18671/Minio.html

A list in cvedetails.com is a summary of vulnerability databases
created by cvedetails.com.

## More Verbose Logging

The configuration "logging.logger.tracing=255" can increase logging
verbosity.  It is bit flags, and 255 is all bits on.
