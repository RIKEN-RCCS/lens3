# api-conf.yaml

This is for Lens3 version v1.2.  Time values are all in seconds.

## Header Part

```
subject: "api"
version: "v1.2"
aws_signature: "AWS4-HMAC-SHA256"
```
Do not change these lines.

## Redis Part (required but not used)

```
redis:
    host: localhost
    port: 6378
    password: "long-string-for-redis-password"
```

## Gunicorn Part

```
gunicorn:
    port: 8003
    workers: 2
    timeout: 120
    access_logfile: "/var/tmp/lenticularis/lens3-gunicorn-api-access-log"
    log_file: "/var/tmp/lenticularis/lens3-gunicorn-api-log"
    log_level: debug
    #log_syslog_facility: LOCAL8
    reload: yes
```

See the documents of Gunicorn.

## Lens3-Api Part

```
controller:
    front_host: lens3.example.com
    trusted_proxies:
        - localhost
    base_path: "/api"
    claim_uid_map: email-name
    probe_access_timeout: 60
    minio_mc_timeout: 10
    max_pool_expiry: 630720000
    CSRF_secret_key: xyzzy
```

* __front_host__ is a host name of a proxy.  It is used as a HOST
  header when a Lens3-Api accesses Mux.

* __trusted_proxies__ is host names of the proxies.  The ip-addresses
  of them are checked when Lens3 receives a request.

* __base_path__ is a base-URL.  It is used when a proxy drops paths.
  It can be "".  Do not add a trailing slash.

* __claim_uid_map__ is one of "id", "email-name", "map".  It specifies
  a mapping of a claim (an X-REMOTE-USER) to an uid.  "id" means
  unchanged, "email-name" takes a name part of an email (before "@"),
  and "map" is a mapping which is defined in the configuration.

* __probe_access_timeout__: is a tolerance when Lens3-Api accesses a
  Mux.

* __minio_mc_timeout__ is a tolerance when Lens3-Api issues an MC
  command.

* __max_pool_expiry__ is a time limit of a pool is active.  630720000
  is 10 years.

* __CSRF_secret_key__: is a key used by fastapi_csrf_protect module.

## MinIO Part

```
minio:
    minio: /home/lens3/bin/minio
    mc: /home/lens3/bin/mc
```

These specify commands of MinIO.

## Logging Part

```
log_file: "/var/tmp/lenticularis/lens3-api-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```
