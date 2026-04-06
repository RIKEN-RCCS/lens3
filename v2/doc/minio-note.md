# Information on MinIO

## (Appendix) Installation of MinIO Binaries

### Download MinIO Binaries

Download MinIO binaries "minio" and "mc" from min.io and install them.
"minio" and "mc" are to be accessible by anyone as permission=755.

NOTE: The binaries are taken from the archive to use specific versions
of MinIO and MC -- MinIO RELEASE.2022-05-26T05-48-41Z and
correspondingly MC RELEASE.2022-06-10T22-29-12Z.  Newer versions of
MinIO starting from RELEASE.2022-06-02T02-11-04Z use an erasure-coding
backend, and they store files in chunks and are not suitable for
exporting existing files.  The version of MC is the one released after
MinIO but as close as to it.

See [Deploy MinIO: Single-Node Single-Drive](https://min.io/docs/minio/linux/operations/install-deploy-manage/deploy-minio-single-node-single-drive.html)

```
# su - lenticularis

cd /tmp
wget https://dl.min.io/server/minio/release/linux-amd64/archive/minio-20220526054841.0.0.x86_64.rpm
rpm2cpio minio-20220526054841.0.0.x86_64.rpm | cpio -id --no-absolute-filenames usr/local/bin/minio
mv ./usr/local/bin/minio ./minio
rm -r ./usr
rm ./minio-20220526054841.0.0.x86_64.rpm
wget https://dl.min.io/client/mc/release/linux-amd64/archive/mc.RELEASE.2022-06-10T22-29-12Z
mv ./mc.RELEASE.2022-06-10T22-29-12Z ./mc
exit

install -m 755 -c /tmp/minio /usr/local/bin/minio
install -m 755 -c /tmp/mc /usr/local/bin/mc
```

### Running MinIO by Hand

A major trouble is starting MinIO.  Try to start MinIO by hand.

```
/usr/loca/bin/minio --json --anonymous server --address :9012 SOME-PATH

Or,

/usr/bin/sudo -n -u SOME-UID -g SOME-GID \
    /usr/loca/bin/minio --json --anonymous server --address :9012 SOME-PATH
```

### Examining MinIO Behavior

It is a bit tricky when MinIO won't behave as expected.  In that case,
it will help to connect to MinIO with "mc" command.  It allows to dump
MinIO's tracing information, for example.

The necessary information to use "mc" command is a URL of a MinIO
endpoint, and administrator's key pair.  These can be obtained by
`lenticularis-admin show-be` command ("be" is a short for backend).  It
displays MinIO's endpoint (host:port) in "backend_ep" field.  It also
displays an access-key in "root_access" and a secret-key in
"root_secret".

The "show-be" command shows information on running MinIO instances.
To use "mc" command, it is necessary to keep a MinIO instance running.
Run `lenticularis-admin send-probe POOL-NAME`, repeatedly, to let it running.

```
cd ~lenticularis
lenticularis-admin -c ./lens3.conf show-pool
lenticularis-admin -c ./lens3.conf show-be
lenticularis-admin -c ./lens3.conf send-probe POOL-NAME
```

For example, the sequence of commands below enables to dump tracing
logs from MinIO.  ALIAS-NAME can be any string.  A URL string would be
"http:// + _backend_ep_", like `http://localhost:9012`.

```
mc alias set ALIAS-NAME URL ACCESS-KEY SECRET-KEY
mc admin trace -v ALIAS-NAME
```

### MinIO Vulnerability Information

  - https://github.com/minio/minio/security
  - https://blog.min.io/tag/security-advisory/
  - https://www.cvedetails.com/vulnerability-list/vendor_id-18671/Minio.html

A list in cvedetails.com is a summary of vulnerability databases
created by cvedetails.com.
