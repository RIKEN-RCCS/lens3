# mux-conf.yaml

This is for Lens3 version v1.2.  Time values are all in seconds.

## Header Part

```
subject: "mux"
version: "v1.2"
aws_signature: "AWS4-HMAC-SHA256"
```

Do not change these lines.

The subject name can be something like "mux:**mux-name**".  It is used
to store multiple settings, when it is necessary run it parallel with
different settings.  A mux-name can be specified by an environment
variable "LENS3_MUX_NAME" set in the service script
"lenticularis-mux.service".

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
    port: 8004
    workers: 4
    threads: 4
    timeout: 60
    reload: yes
    access_logfile: "/var/tmp/lenticularis/lens3-gunicorn-mux-access-log"
    log_file: "/var/tmp/lenticularis/lens3-gunicorn-mux-log"
    log_level: debug
    #log_syslog_facility: LOCAL7
```

## Lens3-Mux Part

```
multiplexer:
    front_host: lens3.example.com
    trusted_proxies:
        - localhost
    mux_ep_update_interval: 307
    forwarding_timeout: 60
    probe_access_timeout: 60
    bad_response_delay: 1
```

* FRONT_HOST is a host name of a proxy.  It is used when a Lens3-Mux
  accesses the other Mux's.

* TRUSTED_PROXIES lists names of the proxies.  The ip-addresses of
  them are checked when Lens3-Mux receives a request.

* MUX_EP_UPDATE_INTERVAL is an interval that Lens3-Mux tells its
  end-point in Redis.

* FORWARDING_TIMEOUT is a tolerance when Lens3-Mux forwards a request
  to MinIO and waits for the reply.

* (PROBE_ACCESS_TIMEOUT) IS NOT USED.  It is a tolerance when Lens3-Mux
  starts a MinIO instance on a remote node.

* BAD_RESPONSE_DELAY is a wait to avoid denial attacks,
  when an error response is going to be returned.

## Manager Part

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

* SUDO is a path of the sudo command.

* PORT_MIN and PORT_MAX specifies the port range used to run a
  Manager.

* MINIO_AWAKE_DURATION specifies a duration until an MinIO instance
  will be shutdown.

* MINIO_SETUP_AT_RESTART specifies to reinitialized an MinIO instance.
  If it is true, bucket settings are reinitialized as to the states
  known to Lens3 service.

* HEARTBEAT_INTERVAL and HEARTBEAT_MISS_TOLERANCE specify an interval
  and a count of a heartbeat failure.  HEARTBEAT_TIMEOUT is a
  tolerance when a Manager sends a request to a MinIO instance as a
  heartbeat.

* MINIO_START_TIMEOUT, MINIO_SETUP_TIMEOUT, and MINIO_STOP_TIMEOUT
  specifies timeout values when a Manager starts or stops a MinIO
  instance.

* MINIO_MC_TIMEOUT specifies a timeout when a Manager sends a MC
  command to a MinIO instance.

## MinIO Part

These specify commands of MinIO.

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