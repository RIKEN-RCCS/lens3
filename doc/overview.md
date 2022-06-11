# Configuration of services in Lenticluaris-S3

## Configuration

```
reverse-proxy <+-->︎ Mux <+--> MinIO
               |         +--> MinIO
               |         +--> MinIO
               +--> Wui
                    Redis
```

A reverse-proxy is not a part of Lens3 but it is required for
operation.  Mux is a multiplexer and Wui is the setting Web-UI.  Mux's
can be multiple instances in a load-balanced configuration.  Wui may
access Mux to start a MinIO.  Also, Mux's mutually access each other
to start a MinIO in multiple Mux configurations.

Mux is in charge of starting a MinIO process (via class Controller).
Mux starts a Manager process as a daemon, and then, a Manager starts a
MinIO process and waits until a MinIO process exits.

## Notes

### Bucket naming

Lens3 works with the path-style bucket naming.  The first part of a
path in a URL is considered as a bucket name.

### Bucket policy

Buckets can be public r/w and private r/w.  The public r/w policy is
given by Lens3 UI.  The private r/w policy is determied by the
access-keys associated to the bucket-pool.

### Limitations or unsupported

* Coarse authentication: access-keys are assigned to a bucket-pool
* No STS support
* No event notifications support
