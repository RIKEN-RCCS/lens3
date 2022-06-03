  * Set `default_zone_lifetime` to -1 for forever.
      otherwise, when an end user create a zone, the "current time plus
      this value" is set to new zone's default expiration date time.
      if `allowed_maximum_zone_exp_date` is also set, use earlier one.

    - `reserved_hostnames`:
      list reserved hostnames.
      - In this example, we show 2. below.
        1. In case facade-hostname is a subdomain of`direct_hostname_domain`,
            facade-hostname(FQDN)
        2. In case WebUI hostname is a subdomain of `direct_hostname_domain`
            WebUI hostname(FQDN)
        3. Other hostnames that administrator disallows end users to use.(FQDN)

    - `direct_hostname_validator`:
      - This validate restricts label name of direct hostname.
      - `flat`: disallow including `.` in the label.
        label length must shorter than 64 characters.


    - Edit configuration file
      ```
      gunicorn:
      # designate awaiting port.  we use [::]:8001 to listen both IPv4 and IPv6.
          bind: "[::]:8001"
      # numbers of gunicorn workers
          workers: 24
      # gunicorn timeout
          timeout: 120
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

      multiplexer:
          # set facade hostname
          facade_hostname: lens3.example.com

      controller:
              # maximum allowed time during initializing a zone
              max_lock_duration: 60

          system_settings:
      # maximum number of zones per end user
              max_zone_per_user: 3
      # maximum number of direct hostname per end user
              max_direct_hostnames_per_user: 2
              default_zone_lifetime: 630720000
              allowed_maximum_zone_exp_date: 2279404800
      # endpoint_url is used to display Endpoint URL to user in WebUI
              endpoint_url: https://{hostname}/
      # function name that validate direct hostname
              direct_hostname_validator: flat
      # Direct Hostname Domain
              direct_hostname_domain: lens3.example.com
      # reserved domain names, preventing end users to accidentally use webui hostname.
              reserved_hostnames:
                  - webui.lens3.example.com
      # time limit of connecting to multiplexer (for sending decoy)
              probe_access_timeout: 60

          syslog:
      # logging facility (case sensitive)
      # facility: KERN, USER, MAIL, DAEMON, AUTH, LPR, NEWS, UUCP, CRON,
      #           SYSLOG, LOCAL0 to LOCAL7(, AUTHPRIV)
              facility: LOCAL7
      # logging priority (case sensitive)
      # priority: EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG
      # WARNING: setting priority to DEBUG, sensitive information may be
      #          recorded in syslog.
              priority: INFO


      webui:
          trusted_proxies:
      # trust reverse-proxy
              - localhost
      # secret key for CSRF protector. (DO NOT USE REDIS'S PASSWORD HERE)
          CSRF_secret_key: xyzzy
      ```
