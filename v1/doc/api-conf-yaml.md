# api-conf.yaml

This is for Lens3 version v1.2.  Time values are all in seconds.

## Header Part

```
subject: "api"
version: "v1.2"
aws_signature: "AWS4-HMAC-SHA256"
```
Do not change these lines.

## Redis Part

They specify a connection to Redis.

```
redis:
    host: localhost
    port: 6378
    password: "long-string-for-redis-password"
```

## Gunicorn Part

See the documents of Gunicorn.

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

## MinIO Part

These specify commands of MinIO.

```
minio:
    minio: /home/lens3/bin/minio
    mc: /home/lens3/bin/mc
```

## Logging Part

```
log_file: "/var/tmp/lenticularis/lens3-api-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```
