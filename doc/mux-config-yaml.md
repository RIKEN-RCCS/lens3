
    - NOTE: Multiplexer's own hostname is not stored in configuration
      file and, it is obtained by platform.node().
      This value is used by other multiplexers to access this multiplexer.
      In case the value returned by platform.node() is inappropriate for
      this purpose, administrator should explicitly set hostname.
      To set hostname, set environment viable `LENTICULARIS_MUX_NODE`
      in the unit file (1.) or environment file (2.).
      1. /usr/lib/systemd/system/lenticularis-mux.service
      2. /etc/systemd/lenticularis-mux.service

      ```
      gunicorn:
      # designate awaiting port.  we use [::]:8000 to listen both IPv4 and IPv6.
          bind: "[::]:8000"
      # numbers of gunicorn workers
          workers: 2
      # numbers of gunicorn threads per worker
          threads: 40
      # gunicorn timeout
          timeout: 60
      # syslog facility (default: user) of gunicorn
          log_syslog_facility: LOCAL7
          reload: yes


      redis:
      # hostname of Redis-Host
          host: localhost
      # port of Redis (see redis.conf's port above)
          port: 6379
      # password of Redis (see redis.conf's requirepass above)
          password: deadbeef


      lenticularis:

          multiplexer:
      # multiplexer's port
              port: 8000
      # delegate hostname
              delegate_hostname: lent8.example.com
              trusted_proxies:
      # trust reverse-proxy
                  - localhost
      # and also trust Admin-API-Host (in this example, they are same so you can omit it)
                  - localhost
              timer_interval: 30
      # time limit of connecting to minio
              request_timeout: 60

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
      #  failing to respond more than `allowed_down_count` times continuously,
      #  minio will be killed by manager.
              allowed_down_count: 3
      # maximum time allowed to initialize zone
              max_lock_duration: 60
      # minimum duration that manager wait for mc info command
              mc_info_timelimit: 20
      # minimum duration that manager wait for mc stop command
              mc_stop_timelimit: 20
      # minimum duration that manager wait after sending SIGHUP to manager
              kill_supervisor_wait: 60
      # minimum duration that manager wait for mc user add command
              minio_user_install_timelimit: 60
      # max allowed excess time to watch_interval
              refresh_margin: 5
      # absolute path to sudo
              sudo: /usr/bin/sudo

          minio:
      # absolute path to minio
              minio: /usr/local/bin/minio
      # unused.  leave it as is.
              minio_http_trace: /var/log/minio_http_trace
      # absolute path to mc
              mc: /usr/local/bin/mc

          syslog:
      # logging facility (case sensitive)
      # facility: KERN, USER, MAIL, DAEMON, AUTH, LPR, NEWS, UUCP, CRON,
      #           SYSLOG, LOCAL0 to LOCAL7(, AUTHPRIV)
              facility: LOCAL7
      # logging level (case sensitive)
      # priority: EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG
      # WARNING: setting priority to DEBUG, sensitive information may be
      #          recorded in syslog.
              priority: INFO
      ```
