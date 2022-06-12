# mux-config.yaml

## Entries

```
redis:
    host: localhost
    port: 6379
    password: deadbeef

gunicorn:
    port: _8000_
    # is a port.  The bind argument is "[::]:8000" to listen both IP v4/v6.
    workers: _
    # is passed to gunicorn.
    threads: _
    # is passed to gunicorn.
    timeout: _
    # is passed to gunicorn.
    log_syslog, log_syslog_facility
    # are passed to gunicorn.
    reload: _
    # is passed to gunicorn.

aws_signature: "AWS4-HMAC-SHA256"

multiplexer:
    * port: 8000
    * facade_hostname: lens3.example.com
    * trusted_proxies:
      are proxies and hosts running adminitorator commands.
    * mux_endpoint_update: 30
      is a time limit of connecting to minio
    * forwarding_timeout: 60

controller:
    # port for MinIO (lower)
    port_min: 9000
    # port for MinIO (upper, inclusive)
    port_max: 18999
    # polling interval for MinIO
    watch_interval: 30
    # minimal inactive time that MinIO is stopped
    keepalive_limit: 600
    # allowed max times without responding mc's query.
    #  failing to respond more than `heartbeat_miss_tolerance` times continuously,
    #  minio will be killed by manager.
    heartbeat_miss_tolerance: 3
    # maximum time allowed to initialize zone
    max_lock_duration: 60
    # minimum duration that manager wait for mc info command
    heartbeat_timeout: 20
    # minimum duration that manager wait for mc stop command
    minio_stop_timeout: 20
    # minimum duration that manager wait after sending SIGHUP to manager
    kill_supervisor_wait: 60
    # minimum duration that manager wait for mc user add command
    minio_setup_timeout: 60
    # max allowed excess time to watch_interval
    refresh_margin: 5
    # absolute path to sudo
    sudo: /usr/bin/sudo

minio:
    # absolute path to minio
    minio: /usr/local/bin/minio
    # absolute path to mc
    mc: /usr/local/bin/mc

syslog:
    # logging facility (case sensitive)
    facility: KERN, USER, MAIL, DAEMON, AUTH, LPR, NEWS, UUCP, CRON,
    #          SYSLOG, LOCAL0 to LOCAL7(, AUTHPRIV)
    #          facility: LOCAL7
    #logging level (case sensitive)
    priority: EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG
    # WARNING: setting priority to DEBUG, sensitive information may be
    #         recorded in syslog.
    #         priority: INFO
```
