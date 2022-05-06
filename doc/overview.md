# Configuration of services in Lenticluaris-S3
----


```
reverse-proxy <+-->︎ Mux <+--> MinIO
               |         +--> MinIO
               |         +--> MinIO
               +--> Adm (<---> Mux)
Redis
```

A reverse-proxy is not a part of Lens3 but it is required for
operation.  Adm (admin Web-UI) accesses to Mux to manage MinIO.

## Notes

It works with:

* Path-style bucket naming.  The first part of a path in a URL is
  considered as a bucket name.

It does not support:

* notifications
* STS
