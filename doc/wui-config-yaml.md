# wui-config.yaml

## Redis Part

```
redis:
    host: localhost
    port: 6378
    password: ZXjmrOLwQ8Ri51pb5FI79z51gAHfIQ4oMvtWrG8q
```

## Gunicorn Part

```
gunicorn:
    port: 8003
    workers: 2
    timeout: 120
    access_logfile: "/var/tmp/lenticularis/lens3-gunicorn-wui-access-log"
    log_file: "/var/tmp/lenticularis/lens3-gunicorn-wui-log"
    log_level: debug
    #log_syslog_facility: LOCAL8
    reload: yes
```

## AWS-Signature Part

```
aws_signature: "AWS4-HMAC-SHA256"
```

## Mux Part

```
multiplexer:
    facade_hostname: fgkvm-010-128-008-026.fdcs.r-ccs.riken.jp
    probe_access_timeout: 60
```

## MinIO-Manager Part

```
minio_manager:
    minio_mc_timeout: 10
```

## MinIO Part

```
minio:
    minio: /home/lens3/bin/minio
    mc: /home/lens3/bin/mc
```

## Web-UI Part

```
system:
    trusted_proxies:
        - localhost
    max_pool_expiry: 630720000
    CSRF_secret_key: xyzzy
```

## Logging Part

```
log_file: "/var/tmp/lenticularis/lens3-wui-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```
