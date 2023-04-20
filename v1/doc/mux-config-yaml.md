# mux-config.yaml

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
    port: 8004
    workers: 4
    threads: 4
    timeout: 60
    access_logfile: "/var/tmp/lenticularis/lens3-gunicorn-mux-access-log"
    log_file: "/var/tmp/lenticularis/lens3-gunicorn-mux-log"
    log_level: debug
    #log_syslog_facility: LOCAL7
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
    trusted_proxies:
        - localhost
    mux_ep_update_interval: 307
    forwarding_timeout: 60
    probe_access_timeout: 60
    bad_response_delay: 1
```

## MinIO-Manager Part

```
minio_manager:
    sudo: /usr/bin/sudo
    port_min: 9000
    port_max: 9999
    minio_awake_duration: 1800
    minio_setup_at_restart: true
    heartbeat_interval: 61
    heartbeat_miss_tolerance: 3
    heartbeat_timeout: 30
    minio_start_timeout: 60
    minio_setup_timeout: 60
    minio_stop_timeout: 30
    minio_mc_timeout: 10
```

## MinIO Part

```
minio:
    minio: /home/lens3/bin/minio
    mc: /home/lens3/bin/mc
```

## Logging Part

```
log_file: "/var/tmp/lenticularis/lens3-mux-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```