Install Manual of Lenticularis
================================================================

# Overview

  + Hardware
    - The system requires following nodes:
      - Note: All services can be hosted by one physical node.
      - See `administrators-guide.md` for details.

    - Redis node: (one or more)
    - reverse-proxy node (one or more)
    - API (Administrator's) node: (one or more)
    - Multiplexer node: (one or more)

    - RedHat family OS are expected.
      This document shows example for AlmaLinux8.5.

  + Overview

    - Procedure Flow

    1. Preparation
      - Prepare network
      - Install prerequisite software

    2. Install
      - Install Redis onto Redis node.
      - Install reverse proxy (NGINX) onto reverse-proxy node.
      - Install Lenticularis modules onto API node.
      - Install MinIO and Mc onto multiplexer nodes.
      - Install Lenticularis modules onto multiplexer nodes.

    3. Configuration
      - Configure Redis
      - Configure reverse proxy
      - Configure API
      - Configure multiplexer
      - Register end users (on API node)

    4. Confirm Installation

  + Required Privileges
    - Install requires sudo
    - End users can run MinIO on multiplexer nodes.

  + Get Source Code
    - In this example, source code is placed in `$SRCDIR`
    - `$SRCDIR` matches root directory of `hpc-object-storage` 

  + Notation
    - This document assumes all node are hosted on different physical node.
    - `#` denotes the operation requires sudo, otherwise (`$`) unprivileged
      account is suffice.

  + Example
    For information, example install procedure are shown in
    `$SRCDIR/develop/lxc/makefile` and
    `$SRCDIR/develop/install/makefile`.


# Prepare Network

  + Goal: 
    1. Setup wildcard DNS to assign domain to reverse-proxy node.
    2. Prepare SSL Certificate for reverse-proxy.

  + Procedure

    - Register domain name on DNS and prepare SSL Certificate.

    - Delegate Hostname: common (shared) hostname for end user to access 
      the system.
      - Configure reverse proxy to transfer all connections that targeting
        to Delegate Hostname to multiplexers.

    - Direct Hostname Domain: domain part of dedicated hostname for each end
      user to access their zone.
      - End user may choose leaf label.  Direct Hostname Domain is parent
        domain of all Direct Hostname.
      - Configure reverse proxy to transfer all connections that targeting
        Direct Hostname, i.e. sub-domain of Direct Hostname Domain,
        to multiplexers.
      - Configure DNS and SSL Certificate to match above requirements.

    - WebUI Hostname
      - Hostname of WebUI which is used by end users.
      - Configure reverse proxy to transfer all connections that targeting
        WebUI Hostname to API node.

    - In this document, we use following examples:
      - Delegate Hostname      : `lens3.example.com`
      - Direct Hostname Domain : `lens3.example.com`
      - WebUI Hostname         : `webui.lens3.example.com`
      - Delegate Hostname, subdomain of Direct Hostname Domain, and WebUI 
        Hostname should point reverse-proxy node.
      - Reverse Proxy's Certificate should valid for all above domain names.

      - NOTE:
        - Delegate Hostname and Direct Hostname Domain may be same.
        - WebUI Hostname can be a subdomain of Direct Hostname Domain.
          In this case, WebUI Hostname should be reserved by configuration.


# Install Prerequisite Software

  + Goal: 
    1. Install Redis
    2. Install NGINX(used as a reverse proxy),
    3. Install Python environment

  + OS
    - Install a RedHat family operation system
    - This document shows example for AlmaLinux8.5.

  + Install Procedure
    - Install `Development Tools` onto Redis node, API node, 
      and multiplexer's node.
      ```
      # dnf update
      # dnf upgrade
      # dnf groupinstall "Development Tools"
      ```

    - Install `redis` onto Redis node.
      ```
      # dnf install redis
      ```

    - Install `python39' onto API node and multiplexer node.
      ```
      # dnf install python39
      ```

  + Configure Reverse Proxy
    - In this document, utilize NGINX as a reverse proxy.
    - Install `nginx` onto reverse-proxy node.
      ```
      # dnf install nginx
      # dnf install httpd-tools
      ```
    - Note: `httpd-tools` is required only if you use basic authentication.


# Administrator's Account Creation

  + Goal:
    1. Create a daemon owner account.
    2. Create an account for administrators.

  + Daemon Owner
    - Create a daemon owner account.
       - To avoid collision with end user's username, the name should
         start with `_`.
       - To distinguish normal user, assign small (less than 1000) uid and gid.
       - same rule for primary group of these users.
    - Create an account for administrators, which belongs to daemon owner's 
      group.

  + Redis Owner
    - Follow system settings.
    - In this example, we use user `redis`, which dnf creates as default user.

  + NGINX Owner
    - Follow system settings.
    - In this example, we use user `nginx`, which dnf creates as default user.

  + API daemon owner
    - Create account as API daemon owner on API node.
    - In this example, we use `_lens3:_lens3`.
    - Procedure
      ```
      # groupadd -K GID_MIN=100 -K GID_MAX=499 _lens3
      # useradd -m -K UID_MIN=100 -K UID_MAX=499 -g _lens3 _lens3
      ```

  + Administrator's Account
    - Create account for administrator on API node.
    - Make the account belongs to API daemon owner's group.
    - In this example, we use `admin`.
    - Procedure
      ```
      # useradd -m -U admin
      # usermod -a -G _lens3 admin
      ```

  + Multiplexer Owner
    - Create account as multiplexer owner on multiplexer node.
    - In this example, we use `_lens3:_lens3`.
    - May share with API daemon owner.
    - Procedure
      ```
      # groupadd -K GID_MIN=100 -K GID_MAX=499 _lens3
      # useradd -m -K UID_MIN=100 -K UID_MAX=499 -g _lens3 _lens3
      ```

# Install API

  + Goal: 
    1. Install python modules for API.

  + Install API Module
    - Install depending python modules and Lenticularis module on API node.
    - Install location: for daemon owner and administrator.
    - Procedure
      ```
      $ cd $SRCDIR
      # su admin -c "pip3 install -r requirements.txt --user"
      # su _lens3 -c "pip3 install -r requirements.txt --user"
      ```

# Install Multiplexer

  + Goal: 
    1. Install python module for Multiplexer
    2. Install MinIO and Mc

  + Install Multiplexer Module
    - Install depending python modules and Lenticularis module on 
      multiplexer node.
    - Install location: for daemon owner and administrator.
    - Procedure
      ```
      $ cd $SRCDIR
      # su _lens3 -c "pip3 install -r requirements.txt --user"
      ```

  + Install MinIO and Mc

    - Install MinIO procedure
      ```
      $ curl https://dl.min.io/server/minio/release/linux-amd64/minio > /tmp/minio
      # install -m 755 -c /tmp/minio /usr/local/bin/minio
      ```

    - Install Mc procedure
      ```
      $ curl https://dl.min.io/client/mc/release/linux-amd64/mc > /tmp/mc
      # install -m 755 -c /tmp/mc /usr/local/bin/mc
      ```

# Configure Redis

  + Goal: Configure Redis making API and multiplexer can access Redis.
    1. Make Redis accept API and multiplexer's IP address
    2. Set passphrase

  + Configure Redis
    - Example:
      ```
      $ $EDITOR /etc/redis/redis.conf
      # bind  -- Comment out bind interface to choose ANY.
      port    -- Use default port.  leave unchanged.
                 This value is also used configuring API and multiplexers.
      requirepass deadbeef
              -- Set a secret passphrase.
                 This passphrase is also used configuring API and multiplexers.
      ```

    - An example for generating a Redis's passphrase (requirepass)
      ```
      echo $(openssl rand --base64 $((12 * 3)) | tr -dc 'a-zA-Z0-9' | cut -b 1-12)
      ```

    - Restart Redis
      ```
      # systemctl restart redis
      # systemctl status redis
      ```

# Configure Reverse-Proxy

  + Goal: Configure NGINX as reverse proxy
    1. Proxy all session to WebUI to API node.
    2. Proxy S3 session to multiplexer node.
    3. Make reverse-proxy authenticate end users, and set username
        to HTTP header `X-REMOTE-USER`.
    4. Reverse proxy may choose multiplexer arbitrary, if there
        are more than one multiplexer nodes.

  + Configuration Detail
    - In this document we use NGINX as a reverse proxy.

    - NGINX configuration procedure
      - Configuration file: `/etc/nginx/conf.d/reverse-proxy.conf`
      - Template: `$SRCDIR/reverseproxy/reverse-proxy-sample.in`
      - Copy template:
        ```
        # systemctl stop nginx
        # cp $SRCDIR/reverseproxy/reverse-proxy-sample.in \
              /etc/nginx/conf.d/reverse-proxy.conf
        ```

    - Edit configuration file (`/etc/nginx/conf.d/reverse-proxy.conf`) 
      as following:
      ```
      server {
          listen 443 ssl;
          listen [::]:443 ssl;

      # designate Delegate Hostname and Direct Hostname (wild card)
      # In this example, Direct Hostname also matches webui section's
      # server_name.  NGINX prefer exact match (webui section's definition)
      # rather than wildcard match (this section).
          server_name lens3.example.com *.lens3.example.com;

          client_max_body_size 0;
          proxy_buffering off;
          proxy_request_buffering off;
          ignore_invalid_headers off;

      # designate wildcard certificate (key and crt)
          ssl_certificate_key "/etc/nginx/server_certificates/server.key";
          ssl_certificate "/etc/nginx/server_certificates/server.crt";
          ssl_protocols TLSv1.1 TLSv1.2 TLSv1.3;
          ssl_ciphers HIGH:!aNULL:!MD5;
          ssl_prefer_server_ciphers on;

          location / {
              proxy_set_header X-Real-IP $remote_addr;
              proxy_set_header X-Forwarded-For $remote_addr;
              proxy_set_header X-Forwarded-Proto $scheme;
              proxy_set_header X-Forwarded-Host $host:$server_port;
              proxy_set_header X-Forwarded-Server $host;
              proxy_set_header Host $http_host;

              proxy_connect_timeout 300;
              proxy_http_version 1.1;
              proxy_set_header Connection "";
              chunked_transfer_encoding off;

      # transfer all connections to backend
              proxy_pass http://backend;
          }
      }

      upstream backend {
      # reverse-proxy may choose backend like a load balancer.
      # there are three behavior.  choices are:
      # (empty) => choose random
      # least_conn => minimize active connections.
      # ip_hash => use client ip to choose a server
          # least_conn;
      # define multiplexers, in form of
      # "server server_name:port;"
      # example:
      # server Se:8000;
      # server 10.131.205.52:8000;
      # server [fd42:8f47:6519:e4c7:216:3eff:fef0:d859]:8000;
          server localhost:8000;
      }

      server {
          listen 443 ssl;
          listen [::]:443 ssl;

          index index.html;

      # hostname of WebUI
          server_name webui.lens3.example.com;

      # designate wildcard certificate (key and crt)
          ssl_certificate_key "/etc/nginx/server_certificates/server.key";
          ssl_certificate "/etc/nginx/server_certificates/server.crt";
          ssl_protocols TLSv1.1 TLSv1.2 TLSv1.3;
          ssl_ciphers HIGH:!aNULL:!MD5;
          ssl_prefer_server_ciphers on;

          satisfy all;
          auth_basic "Controlled Area";
      # in this example, we use basic authentication
          auth_basic_user_file /etc/nginx/htpasswd;

          location / {
              proxy_set_header X-Real-IP $remote_addr;
              proxy_set_header X-Forwarded-For $remote_addr;
              proxy_set_header X-Forwarded-Proto $scheme;
              proxy_set_header X-Forwarded-Host $host:$server_port;
              proxy_set_header X-Remote-User $remote_user;
              proxy_set_header Host $http_host;

              proxy_pass http://api;
          }
      }

      upstream api {
          # least_conn;
      # specify API node
      # example: 10.131.205.39:8001
          server localhost:8001;
      }
      ```

    - Create password table for basic authentication
      ```
      # touch /nginx/etc/htpasswd
      # for u in $(seq 0 9); do
          htpasswd -b /etc/nginx/htpasswd user$u pass$u
      done
      ```

    - Make firewall to pass HTTP connections
      ```
      # apt-get install apache2-utils
      # firewall-cmd --permanent --add-service=https
      # firewall-cmd --reload
      ```

    - Make SELinux to allow HTTP activity
      ```
      # semanage port -a -t http_port_t -p tcp 8001
      # semanage port -a -t http_port_t -p tcp 8000
      # setsebool -P httpd_can_network_connect 1
      ```

    - Start NGINX
      ```
      # systemctl start nginx
      ```

# Configure API Node

  + Goal: Configure API Node
    1. Set Redis password
    2. Set API's own domain name
    3. Add reverse-proxy to trusted hosts
    4. Secure configuration file (as it have passwords in plain text)
    5. Create unit file for API service

  + Configuration File for API
    - Copy configuration file
      - Configuration file: `/etc/lenticularis/adm-config.yaml`
      - Template: `$SRCDIR/webui/adm-config.yaml.in`
        ```
        # mkdir -p /etc/lenticularis/
        # cp $SRCDIR/webui/adm-config.yaml.in /etc/lenticularis/adm-config.yaml
        ```

    - Secure configuration file
      ```
      # chown _lens3:_lens3 /etc/lenticularis/adm-config.yaml
      # chmod 440 /etc/lenticularis/adm-config.yaml
      ```

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
      # hostname of Redis node
          host: localhost
      # port of Redis (see redis.conf's port above)
          port: 6379
      # password of Redis (see redis.conf's requirepass above)
          password: deadbeef

      lenticularis:

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

    - An example for generating a CSRF_secret_key
      ```
      echo $(openssl rand --base64 $((12 * 3)) | tr -dc 'a-zA-Z0-9' | cut -b 1-12)
      ```

    - Set `default_zone_lifetime` to -1 for forever.
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

  + Unit File for API Service
    - Copy the template
      - Unit file: `/usr/lib/systemd/system/lenticularis-api.service`
      - Template: `$SRCDIR/webui/lenticularis-api.service.in`
      - Procedure:
        ```
        # cp $SRCDIR/webui/lenticularis-api.service.in \
              /usr/lib/systemd/system/lenticularis-api.service
        ```

    - Edit
      ```
      [Unit]
      Description = lenticularis webapi (gunicorn app)
      After = syslog.target network-online.target remote-fs.target nss-lookup.target
      Wants = network-online.target

      [Service]
      # API daemon's owner
      User = _lens3
      WorkingDirectory = /
      # set absolute path to adm-config.yaml to LENTICULARIS_ADM_CONFIG
      Environment = LENTICULARIS_ADM_CONFIG=/etc/lenticularis/adm-config.yaml

      ExecStart = python3 -m lenticularis.start_service api

      PrivateTmp = true

      [Install]
      WantedBy = multi-user.target
      ```

  + Start API Daemon
    - Procedure
      ```
      # systemctl enable lenticularis-api
      # systemctl start lenticularis-api
      ```

# Configure Multiplexer (1)

  + Goal: 
    1. Make multiplexer process can use sudo to promote target user 
      and run MinIO

  + Edit Sudoers
    - Make multiplexer owner can use sudo without a password.
    - Make multiplexer owner can promote to be any user, other than root.
    - Make multiplexer owner can execute minio.
    - Tell sudo to keep `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
      `MINIO_HTTP_TRACE`, and `MINIO_BROWSER`.
    - Example:
      ```
      # cat <<-EOF | sudo dd of=/etc/sudoers.d/lenticularis 2>/dev/null
          Defaults env_keep += "MINIO_ROOT_USER MINIO_ROOT_PASSWORD MINIO_HTTP_TRACE MINIO_BROWSER"
          _lens3	ALL=(ALL, !root)	NOPASSWD: /usr/local/bin/minio
      EOF
      ```

# Configure Multiplexer (2)

  + Goal: Configure Multiplexer
    1. Set Redis password
    2. Set Multiplexer's own domain name
    3. Add reverse-proxy to trusted hosts
    4. Secure configuration file (as it holds passwords in plain text)
    5. Create a unit file for multiplexer service
      - In this document, we skip end user's settings. 

  + Configuration File for Multiplexer
    - Copy configuration file
      - Configuration file: `/etc/lenticularis/mux-config.yaml`
      - Template: `$SRCDIR/multiplexer/mux-config.yaml.in`
      ```
      # mkdir -p /etc/lenticularis/
      # cp $SRCDIR/multiplexer/mux-config.yaml.in /etc/lenticularis/mux-config.yaml
      ```
    - Secure configuration file
      ```
      # chown _lens3:_lens3 /etc/lenticularis/mux-config.yaml
      # chmod 440 /etc/lenticularis/mux-config.yaml
      ```

    - Edit configuration file
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
      # hostname of Redis node
          host: localhost
      # port of Redis (see redis.conf's port above)
          port: 6379
      # password of Redis (see redis.conf's requirepass above)
          password: deadbeef


      lenticularis:

          multiplexer:
      # multiplexer's port
              port: 8000
      # facade hostname
              facade_hostname: lens3.example.com
              trusted_proxies:
      # trust reverse-proxy
                  - localhost
      # and also trust API node (in this example, they are same so you can omit it)
                  - localhost
              mux_endpoint_update: 30
      # time limit of connecting to minio
              forwarding_timeout: 60

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
              mc_info_timelimit: 20
      # minimum duration that manager wait for mc stop command
              minio_stop_timeout: 20
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

    - NOTE: Multiplexer's own hostname is not stored in configuration
      file and, it is obtained by platform.node().
      This value is used by other multiplexers to access this multiplexer.
      In case the value returned by platform.node() is inappropriate for
      this purpose, administrator should explicitly set hostname.
      To set hostname, set environment viable `LENTICULARIS_MUX_NODE`
      in the unit file (1.) or environment file (2.).
      1. /usr/lib/systemd/system/lenticularis-mux.service
      2. /etc/systemd/lenticularis-mux.service

  + Unit File for Multiplexer Service
    - Copy the template
      - Unit file: `/usr/lib/systemd/system/lenticularis-mux.service`
      - Template: `$SRCDIR/multiplexer/lenticularis-mux.service.in`
      ```
      # cp $SRCDIR/multiplexer/lenticularis-mux.service.in \
            /usr/lib/systemd/system/lenticularis-mux.service
      ```

    - Edit
      ```
      [Unit]
      Description = lenticularis multiplexer and controller (gunicorn app)
      After = syslog.target network-online.target remote-fs.target nss-lookup.target
      Wants = network-online.target

      [Service]
      # multiplexer daemon's owner
      User = _lens3
      WorkingDirectory = /
      # set absolute path to mux-config.yaml to LENTICULARIS_MUX_CONFIG
      Environment = LENTICULARIS_MUX_CONFIG=/etc/lenticularis/mux-config.yaml

      ExecStart = python3 -m lenticularis.start_service mux

      PrivateTmp = true

      [Install]
      WantedBy = multi-user.target
      ```

  + Start Multiplexer Daemon
    - Procedure
      ```
      # systemctl enable lenticularis-mux
      # systemctl start lenticularis-mux
      ```

# Register End Users (on API node)

  + Goal: 
    1. Register end users to the system
    2. Allow registered users to use the system

  + Register End Users on API node
    - Create user list.  (see administrators-guide.md for detail)
      - Example:
        ```
        admin$ tmpfile=$(mktemp)
        cat <<EOF > $tmpfile
        user1,user1,group-a
        user2,user2,group-a
        user3,member
        EOF
        ```

    - Register user list to the system by `lenticularis-admin` command.
      ```
      admin$ lenticularis-admin insert user-info $tmpfile
      admin$ lenticularis-admin show user-info
      ```

  + Allow End Users to Use the System
    - Create allow-deny-rules.  (see administrators-guide.md for detail)
      - Example:
        ```
        admin$ tmpfile=$(mktemp)
        cat <<EOF > $tmpfile
        allow,*
        EOF
        ```

    - Register allow-deny-rule to the system by `lenticularis-admin` command.
      ```
      admin$ lenticularis-admin insert allow-deny-rules $tmpfile
      admin$ lenticularis-admin show allow-deny-rules --format=json
      ```

# Confirm Installation

  + Procedure

    - Confirm Redis is running on Redis node
      ```
      $ systemctl status redis.service
      $ ps xa|egrep '([r]edis)'
      $ netstat -an|grep '\<6379\>.*LISTEN'
      ```

    - Confirm NGINX is running on reverse-proxy node
      ```
      $ systemctl status nginx.service
      $ ps xa|egrep '([n]ginx)'
      $ netstat -an|egrep '(\<443\>|\<80\>).*LISTEN'
      ```

    - Confirm gunicorn is running on API node
      ```
      $ systemctl status lenticularis-api.service
      $ ps xa|egrep '([g]unicorn)'
      $ netstat -an|grep '\<8001\>.*LISTEN'
      ```

    - Confirm gunicorn is running on multiplexer's node
      ```
      $ systemctl status lenticularis-mux.service
      $ ps xa|egrep '([g]unicorn)'
      $ netstat -an|grep '\<8000\>.*LISTEN'
      ```

    - List running multiplexers on API node.  (use admin account)
      ```
      admin$ lenticularis-admin show multiplexer
      ```

    - Access following website by Web Browser, and create a zone.
      - URL: `http://webui.lens3.example.com/`

    - Access to the create zone by S3 client.
      - Use Access Key created above.
        ```
        user$ cat <<EOF > $HOME/.aws/credentials
        [user1]
        aws_access_key_id = zHb9uscWUDgcJ9ZdYzr6
        aws_secret_access_key = uDUHMYKSmbqyqB1MGYN57CWMC8eXNHwUL4pcNwROu3xWgpsO
        EOF
        user$ AWS_PROFILE=user1 ENDPOINT_URL=https://lens3.example.com \
        aws s3 ls s3://
        ```

    - Access following website by Web Browser, again.
      - URL: `http://webui.lens3.example.com/`
      - Create public bucket
        ```
        Public (download only for Access Key-less user): bucket2
        ```

      - Register direct hostname
        ```
        Direct Hostname (label or FQDN): release.lens3.example.com
        ```

    - Back to client host.
      - Put an object into public bucket create above.
        ```
        user$ tmpfile=$(mktemp)
        user$ date > $tmpfile
        user$ AWS_PROFILE=user1 ENDPOINT_URL=https://lens3.example.com \
        user$ aws s3 cp $tmpfile s3://bucket2/foo
        ```

    - Try to access the public object via directHostname.
      ```
      stranger$ ENDPOINT_URL=https://release.lens3.example.com
      stranger$ curl -k $ENDPOINT_URL/bucket2/foo
      ```

[eof]
