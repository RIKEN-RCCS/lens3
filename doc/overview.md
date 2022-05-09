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

### Bucket naming

Lens3 works with the path-style bucket naming.  The first part of a
path in a URL is considered as a bucket name.

### Bucket policy

Buckets can be public r/w and private r/w.  The public r/w policy is
given by Lens3 UI.  The private r/w policy is determied by the
access-keys associated to the bucket-pool.

### Unsupported

* notifications
* STS
