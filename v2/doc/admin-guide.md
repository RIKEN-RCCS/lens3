# Lenticularis-S3 Administration Guide

## Administration Command (lens3-admin)

The "lens3-admin" command is used to modify keyval-db entries.  It is
installed in "~lens3/go/bin".  The command should typically be run on
the same host of Lens3 services.  Note that it does not mutex accesses
with Registrar, and moreover, modifications can make the contents in
the keyval-db inconsistent.

It will print the list of sub-commands by running
"lens3-admin -c conf.json".

```
lens3$ lens3-admin -c conf.json
Or,
lens3$ lens3-admin -c conf.json help
```

### User and Pool Mangement

"lens3-admin" is used to list users or pools.

```
lens3$ lens3-admin -c conf.json show-user
lens3$ lens3-admin -c conf.json show-pool
```

It can disable users or pools.

```
lens3$ lens3-admin -c conf.json stop-user true UID
lens3$ lens3-admin -c conf.json stop-pool true POOL-NAME
```

### User Registration

"lens3-admin" is used to register users.  Registering users is
necessary when the configuration is "user_approval=block".

The user list can be modified by loading a CSV-file.  Loading a
CSV-file is incremental, that is, it does not reset the whole data.

```
lens3$ lens3-admin -c conf.json load-user USER-LIST.csv
lens3$ lens3-admin -c conf.json dump-user > USER-LIST.csv
```

A CSV-file consists of lines of {ADD, MODIFY, DELETE, ENABLE,
DISABLE}-rows.

An ADD-row is: ADD,uid,claim,group,... (the rest is a group list).

It is one for each user.  The "claim" field is optional and only used
when the configuration is "claim_uid_map=map".  It is a user's name
returned by authentication, such as OIDC (OpenID Connect).  A group
list needs at least one entry.

A MODIFY-row is simliar to an ADD-row.  Adding resets the existing
user and deletes the pools it owned.  Modifying keeps the pools.

A DELETE-row is: DELETE,uid,...

An ENABLE-row and a DISABLE-row are similar.

Rows in a CSV-file are processed in the order that all ADD/MODIFY rows
first, then DELETE, ENABLE, and DISABLE rows in this order.

Spaces around a comma or trailing commas are not allowed in CSV.

## System Maintenance

### No Updating MinIO and Mc Binaries

MinIO and Mc commands should NOT be updated.  Note that Lens3 only
works with a specific old version of MinIO.

### Valkey Snapshot

Lens3 uses Valkey's "snapshotting" of the database.  The file location
and the snapshot interval can be found under the keywords
"dbfilename", "dir", and "save" in the configuration
"/etc/lenticularis/valkey.conf".  Lens3 uses "save 907 1", which is an
interval about 15 minutes.  Log-rotating of snapshots is recommended.

### Keyval-DB Backup

Backup of the keyval-db is done by "lens3-admin" with dump-db and
fill-db commands.  A dump is a text file with keys and values.  A key
part is a string, and a value part is a record in json and it is
indented by four spaces.

```
lens3$ lens3-admin -c conf.json dump-db > DUMP.txt
lens3$ lens3-admin -c conf.json wipe-out-db everything
lens3$ lens3-admin -c conf.json fill-db DUMP.txt
```
