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

See the documents of Gunicorn.

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
    mux_node_name: ""
```

* __front_host__ is a host name of a proxy.  It is used as a HOST
  header when a Lens3-Mux accesses the other Mux's.

* __trusted_proxies__ lists names of the proxies.  The ip-addresses of
  them are checked when Lens3 receives a request.

* __mux_ep_update_interval__ is an interval that Lens3-Mux tells its
  end-point in Redis.

* __forwarding_timeout__ is a tolerance when Lens3-Mux forwards a
  request to MinIO and waits for the reply.

* (__probe_access_timeout__) IS NOT USED.  It is a tolerance when
  Lens3-Mux starts a MinIO instance on a remote node.

* __bad_response_delay__ is a wait to avoid denial attacks, when an
  error response is going to be returned.

* __mux_node_name__ is optional.  It is used as a host name on which
  Lens3-Mux is running, when a host name the system returns is not
  appropriate.

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

* __sudo__ is a path of the sudo command.

* __port_min__ and __port_max__ specifies the port range used to run a
  Manager.

* __minio_awake_duration__ specifies a duration until an MinIO
  instance will be shutdown.

* __minio_setup_at_restart__ specifies to reinitialized an MinIO
  instance.  If it is true, bucket settings are reinitialized as to
  the states known to Lens3 service.

* __heartbeat_interval__ and __heartbeat_miss_tolerance__ specify an
  interval and a count of a heartbeat failure.

* __heartbeat_timeout__ is a tolerance when a Manager sends a request
  to a MinIO instance as a heartbeat.

* __minio_start_timeout__, __minio_setup_timeout__, and
  __minio_stop_timeout__ specifies timeout values when a Manager
  starts or stops a MinIO instance.

* __minio_mc_timeout__ specifies a timeout when a Manager sends a MC
  command to a MinIO instance.

## MinIO Part

```
minio:
    minio: /home/lens3/bin/minio
    mc: /home/lens3/bin/mc
```

These specify commands of MinIO.

## Logging Part

```
log_file: "/var/tmp/lenticularis/lens3-mux-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```
