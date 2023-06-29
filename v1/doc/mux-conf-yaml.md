# mux-conf.yaml

This is for Lens3 version v1.2.  Time values are all in seconds.

## Header Part

```
subject: "mux"
version: "v1.2"
aws_signature: "AWS4-HMAC-SHA256"
```

Do not change these lines.

The subject name can be something like "mux:mux-name".  It is used to
store multiple settings, when it is necessary run it in parallel with
different settings.  A setting can be chosen by an environment
variable "LENS3_MUX_NAME" which is set in the service script
"lenticularis-mux.service".  For example, LENS3_MUX_NAME="mux1" will
choose the setting with subject="mux:mux1".

## Gunicorn Part

```
gunicorn:
    port: 8003
    workers: 4
    threads: 4
    timeout: 60
    reload: yes
    access_logfile: "/var/log/lenticularis/lens3-gunicorn-mux-access-log"
    log_file: "/var/log/lenticularis/lens3-gunicorn-mux-log"
    log_level: debug
    #log_syslog_facility: LOCAL7
```

See the documents of Gunicorn.  Entires other than __port__ are
optional.

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
    busy_suspension_time: 180
    # mux_node_name: ""
```

* __front_host__ is a host name of a proxy.  It is used as a HOST
  header when a Lens3-Mux accesses other Mux's.

* __trusted_proxies__ lists names of the proxies.  The ip-addresses of
  them are checked when Lens3 receives a request.

* __mux_ep_update_interval__ is an interval that Lens3-Mux tells its
  end-point in Redis.

* __forwarding_timeout__ is a tolerance when Lens3-Mux forwards a
  request to MinIO and waits for the reply.

* (__probe_access_timeout__) IS NOT USED.  It is a tolerance when
  Lens3-Mux starts a MinIO instance on a remote node.

* __bad_response_delay__ is an added wait when an error response is to
  be returned.  It is to avoid denial attacks.

* __busy_suspension_time__ is an interval waited in by a suspended
  pool before retrying to start MinIO.  It can tentatively be a few
  minutes or a fraction of the minio_awake_duration, becuase it takes
  a minio_awake_duration before each MinIO instance to stop.

* __mux_node_name__ is optional.  It is used as a host name on which
  Lens3-Mux is running.  It needs to be set when a host name that the
  system returns is not appropriate.

## Manager Part

```
minio_manager:
    sudo: /usr/bin/sudo
    port_min: 9000
    port_max: 9029
    minio_awake_duration: 900
    minio_setup_at_start: true
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
  Manager.  The range of ports may be used to limit the number of
  MinIO instances running on the server host.

* __minio_awake_duration__ specifies a duration until an MinIO
  instance will be shutdown.

* __minio_setup_at_start__ specifies to reinitialize an MinIO
  instance.  If it is true, access-key and bucket settings are reset
  to the state known to the Lens3 service.

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
log_file: "/var/log/lenticularis/lens3-mux-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```

* __log_file__: specifies a log file.  This entry is optional.  If
  log_file is specified, the log_syslog section is ignored.
