# Lenticularis-S3 Administration Guide

## System Overview

  + Hardware
    - The system requires following nodes:
      - Note: all services can be hosted by one physical node.
      - In this document, we use settings for individual nodes as examples.
        The examples can applied to a physical node.

    - Redis node: (one or more)
      - Must be reachable from all multiplexer node.
      - Must be reachable from the API (administrator's) node.
      - Note: may be hosted by one of a multiplexer node.
      - Do not share redis with another services.

    - Reverse-proxy Node (one or more)
      - Note: May be hosted by one of a multiplexer node.

    - API (Administrator's) node: (one or more)
      - Runs administrator's CLI commands.
      - Runs API for WebUI.
      - Must be reachable from the reverse-proxy node.
      - Note: May be hosted by one of a multiplexer node.

    - Multiplexer node: (one or more)
      - Runs multiplexer, controller, S3 server (MinIO)
      - Must be reachable from the reverse-proxy node.
      - Must be reachable from multiplexer nodes mutually.
      - Must be reachable from API (administrator's) node.
      - MinIO can access end user's home directory (or end user writable storage).


  + Software

    - Redis node
      - Redis
      - Follow redis's recommended configuration.
        - /etc/redis/redis.conf

    - Reverse-proxy node:
      - NGINX or Apache2 -- Utilized as an reverse proxy.
        - In this document we use NGINX as an example.
      - Configuration
        - Follow application's recommended settings.

    - API (Administrator's) node:
      - python3
      - gunicorn
      - fastapi
      - python modules of Lenticularis

      - Configuration
        - `/etc/lenticularis/adm-config.yaml`                 # main config
        - `/usr/lib/systemd/system/lenticularis-api.service`  # unit file
        - `$PYTHONLIB/lenticularis/`                          # modules
        - `$PYENV_SHIMS/lenticularis-admin`                   # CLI

    - Multiplexer node:
      - python3
      - gunicorn
      - python modules of Lenticularis
        - Recommended to use "pip3 install --user" to install modules.
        - Install modules into system area ("sudo pip3 install") does well,
          but not recommended.
        - Using pyenv (or another virtual environments for python) also does 
          well.  (not documented here)
      - MinIO, Mc
      - sudo

      - Configuration:
        - `/etc/lenticularis/mux-config.yaml`                 # main config
        - `/usr/lib/systemd/system/lenticularis-mux.service`  # unit file
        - `$PYTHONLIB/lenticularis/`                          # modules
        - `/etc/sudoers.d/lenticularis`                       # settings for sudoers

    - Users
      - System Account (daemon owner)
        - In this documents we use `_lens3` as an example.  (see `install.md`)
        - Daemon owner can use sudo to switch any end user and run MinIO
        - Only daemon owner can read configuration file
      - Administrator
        - In this documents we use 'admin' as an example.  (see `install.md`)
      - End users
        - End users that run MinIO on multiplexer node.
        - There are no need to login multiplexer node.

  + Backups:
    - Information that must backed up to restore from serious hazards:
      - Storage Zone Table
        - This table is created by end users.
      - Permission Table -- stores allow/deny rules, written by the 
        administrator.
      - Users Table -- stores all end users information, written by the 
        administrator.
      - `lenticularis-admin dump` will dump all above tables.
      - `lenticularis-admin restore dumpfile` registers all dumped tables.

    - As the following table (or entry) is dynamic, there are no need to 
      back up.
      - Mode flag of Storage Zone Table
      - Routing Table
      - MinIO Address Table
      - Multiplexer Address Table

  + Log
    - All log is stored in /var/log/local7
      - Facility can be changed by configuration file

## Installation

  - See `install.md`

## Databases (Information)

  In this section describes databases stored on redis by Lenticularis.

  + Storage Zone
    - A set of UNIX userid, buckets directory, Access Key, and expiration dates.
      corresponds to an Endpoint.

  + Databases
    - Administrator uses cli-command to manipulates databases.
      - There are no need to issue database commands.
    - End users only use WebUI and WebUI will manipulate databases for 
      the end user.

      ```
      ----  --------------------  ----------------------
      db#   Table name            Description
      ----  --------------------  ----------------------
      0     Allow/Deny Table      lists allowed or denied users
      0     Users Table           lists all users and their groups
      0     Storage Zone Table    Storage Zone
      2     Multiplexer Table     all active multiplexers.  (autogen)
      2     MinIO Address Table   all active MinIO processes.  (autogen)
      4     Routing Table         (autogen)
      ----  --------------------  ----------------------
      ```

    - Allow/Deny Table:
      - All allow-deny rules is stored as an string (json).
        1 record
      - The system doesn't check existence of user that allowed or denied in 
        this table.
    - Users Table:
      - Lists all end users and their groups.
      - A zone is disabled if the zone's owner is missing in this table.
    - Storage Zone Table:
      - Static part: set of zone settings
      - Dynamic part: zone's mode (status), last access time
    - Multiplexer Table:
      - Lists all active multiplexers.  dynamic.
    - MinIO Address Table:
      - Lists all active MinIO processes.  dynamic.
    - Routing Table:
      - Multiplexer uses this table to determine destination node for S3 
        session to redirect.
      - Dynamic.

## System Management

  + Commands for Administrator
    - All commands can be run by administrator's account (`admin`)
      or daemon owner's account (`_lens3`).
      - Administrator's account must be able to read setting file 
       (`/etc/lenticularis/adm-config.yaml`) to use commands.

    - Operations on Allow/Deny Table
      ```
      $ lenticularis-admin insert allow-deny-rules file
      $ lenticularis-admin show allow-deny-rules
      ```
      - Give allow-deny rules in `file` in above example.
        - For notation, refer to `install.md`
      - Drop command that delete entire allow-deny-rules is not provided. 
        To restore to default value, insert "[]"
      - `deny`-ed end user's zone is disabled.  (not deleted)

    - Operations on Users Table
      ```
      $ lenticularis-admin insert user-info file
      $ lenticularis-admin show user-info
      ```
      - Drop command is not provided.  To restore to default value, insert empty file
      - Removed end user's zone is disabled.  (not deleted)
      - Zones that group is removed from this list is disabled.  (not deleted)

    - Operations on Storage Zone Table
      ```
      $ lenticularis-admin insert zone Zone-ID zonefile
      $ lenticularis-admin delete|disable zone Zone-ID...
      $ lenticularis-admin enable zone Zone-ID...
      $ lenticularis-admin show zone [Zone-ID...]
      ```
      - Options: --skip-initialize
      - This command does not initialize MinIO.
        - (MinIO is initialized on the first access of end user)
      - Zones can be created, which owned by end users who does not appear 
        in the Users Table or owned by denied user.

    - Backup and Restore
      ```
      $ lenticularis-admin dump
      $ lenticularis-admin restore
      $ lenticularis-admin --reset-database
      $ lenticularis-admin drop
      ```
      - Zone, user-info, allow-deny-rules are affected

    - Show Multiplexer Table
      ```
      $ lenticularis-admin show multiplexer
      ```

    - Show MinIO Address Table
      ```
      $ lenticularis-admin show server-processes
      ```
      - Displays active MinIO processes.

    - Deleting MinIO Address Table
      ```
      $ lenticularis-admin flush server-processes
      $ lenticularis-admin delete server-processes [server-ID...]
      ```
      - Deleting entry from MinIO Address Table, the corresponding
        MinIO process is killed by manager.

    - Trigger MinIO to start
      ```
      $ lenticularis-admin throw decoy Zone-ID
      ```
      - This command throws forged S3 packet to specified zone.
      - As a side effect, a MinIO of the zone start running.
      - Because secret Access Key and payload is invalid, this operation
        will rejected by MinIO.

    - Routing Table
      ```
      $ lenticularis-admin show routing-table
      $ lenticularis-admin flush routing-table
      ```
      - Routing table is automatically built by managers.
      - Deleting routing table does not impact service.

    - Debug commands
      ```
      $ lenticularis-admin printall
      $ lenticularis-admin resetall
      ```
      - Show raw database.
      - Reset database.


  + Allow/Deny Rule
    - The system uses Allow/Deny Rule to determine a user may use the system or not.

    - Format is CSV
      - Separator is `,`
      - Use `"` to quote
      - Note: spaces surrounding `,` are preserved

    - Write one rule for a line
    - The first column is keyword: `allow` or `deny`
      - Case insensitive (the system converts keyword to lowercase 
        before saving them)
    - The second line is a username or an asterisk (`*`)
      - This field is compared against testing username, case sensitive
      - `*` matches any username.
      - Group cannot use specify users in this rules.

    - Interpretation
      - The rules are applied to subject line by line, in order.
      - If the second column is `*` or the second column matches subject's 
        username, search stops.
      - The first column of matched line becomes the result.

      - Assume implicit `ALLOW,*` at the end of rules. 
        - Any users allowed that does not match are allowed.
        - Empty rule set means all users are allowed.  (system default)

    - Example:
      ```
      $ cat /tmp/perm.txt
      allow,user1
      deny,user2
      $ lenticularis-admin insert allow-deny-rules /tmp/perm.txt
      ```

  + UNIX User Info
    - Register users and their groups who may use the system.

    - Format is CSV
      - Use `,` as a separator
      - Use `"` to quote
      - Note: spaces surrounding `,` are preserved

    - One user information per line
    - The first column represents the username
      following columns represents groups of the user, one group per one column

    - Username and group name are case sensitive

    - Example:
      ```
      $ cat /tmp/users.txt
      user1,user1,group-a
      user2,user2,group-a
      user3,member
      $ lenticularis-admin insert user-info /tmp/users.txt
      ```

  + Auditing Activity
    - Access log and error log are saved syslog (/var/log/local7)
      - Check logfile regulatory.
      - `{systemd_private_tmp}`/gunicorn.log --  programming error
      - /var/log/{facility} -- any other log other than above
    - Note: The system does not provide alert mechanism.

  + Access Log
    - Access log is sent to syslog with INFO level.
    - Use a keyword "accesslog" to extract access log from logfile.
    - Access Log consists following fields:
    - format:
      ```
      "{access_time} {status} {client_addr} {user} {method} {url} \
       {content_length_upstream} {content_length_downstream}"
      ```

    - fields:
      - `access_time`: access time
      - `status`: status code of HTTP response
      - `client_addr`: address of end user's client
      - `user`: see below
      - `method`: HTTP request method
      - `url`: original request url
      - `content_length_upstream`: content-length of request (`-` for API access)
      - `content_length_downstream`:  content-length of response (`-` for API access)

      - recorded `user` varies on access types or status:
        - API: the authorized user by reverse proxy
        - S3/HTTP: zone resolved => zone owner (by authorization / by directhostname)
        - S3/HTTP: zone not resolved => access_key_id (or None)
        - NOTE: Access Key ID is not logged.



  + System Maintenance
    - Updating MinIO and Mc
      - MinIO and Mc are actively developed 2022-01.
      - Follow application's message to update them.
        ```
          You are running an older version of MinIO released 2 weeks ago
          Update: Run `mc admin update`
        ```

    - Updating OS and Software
      - Follow individual instruction to update OS and other software.

    - Maintenance Mode
      - Shutdown end user's access to the system during updating OS or
        other software's.
      - To shutdown end users' access, stop multiplexers and API.
        - In this mode, end user will receive "503 service unavailable" 
          messages.  (because reverse proxy believes multiplexers are refusing
          connection) 
      - Shutdown the system procedure:
        ```
        # systemctl stop lenticularis-mux    # execute on multiplexer's node
        # systemctl stop lenticularis-api    # execute on API's node
        ```
      - Resume system procedure:
        ```
        # systemctl start lenticularis-mux    # execute on multiplexer's node
        # systemctl start lenticularis-api    # execute on API's node
        ```
      - Note: while the system is shutdown, `lenticularis-admin throw decoy`
        is also unusable.

    - Deep Shutdown
      - To update redis and reverse-proxy, shutdown the system deeply.
      - Note: in this mode, all sub-commands of `lenticularis-admin` are 
        also unusable.

    - Deep Shutdown Procedure
      ```
      # systemctl stop lenticularis-mux    # execute on multiplexer's node
      # systemctl stop lenticularis-api    # execute on API's node
      # systemctl stop redis               # execute on Redis's node
      # systemctl stop nginx               # execute on reverse-proxy node
      ```

    - Emergency Shutdown
      - To stop service in hurry, stop all services. 
      - Same as deep shutdown procedure, in any order.
        - Once NGINX is stopped, all new connection is shutdown.
        - Once redis is stopped, all new S3 connection is shutdown.
          in this case, access to API is still allowed, but no modification
          can be made to the db.
      ```
      # systemctl stop nginx               # reverse-proxy Node
      # systemctl stop redis               # Redis Node
      # systemctl stop lenticularis-mux    # multiplexer's node
      # systemctl stop lenticularis-api    # API's node
      ```

    - Check status of the system 
      (Assume that `admin` belongs to `systemd-journal` group)
      ```
      admin$ systemctl status redis.service
      admin$ systemctl status nginx.service
      admin$ systemctl status lenticularis-mux.service
      admin$ systemctl status lenticularis-api.service
      ```

  + Error
    - Procedure to recover error

      - CASE: A MinIO process does note respond at all.
        - Kill problematic MinIO process (TERM, KILL).
          manager will cleanup messed up state automatically.
        - Kill manager process (TERM).
          manager will gracefully kill MinIO, then cleanup all states.
          If manager is killed by signal KILL, manager do not execute
          cleanup procedure.

      - CASE strive node hang up
        - Restart the service node.  multiplexer and redis automatically
          restore normal state.

  + Security

    - Secrets
      - Secret key for Redis is stored in config file as a plain text.
        - Config file should not be read by other than daemon owner and
          administrator.
      - Secret CSRF key is stored in config file as a plain text.
        - Config file should not be read by other than daemon owner.
      - Secret Access Keys for MinIO are stored on Redis, encoded
        by rot13.  As rot13 is virtually plain text, access to redis
        should be protected by anonymous users.
        - Secret key for Redis should be secured.

    - Privilege
      - Manager can run MinIO as another user.
        - (a) Multiplexer that is a parent process of manager, 
          accepts connection from reverse-proxy and other multiplexers.
        - (b) Manager does not switch to any user, but specified by HTTP
          header X-REMOTE-USER.
        - (c) Only, reverse-proxy authorizes users and add X-REMOTE-USER.
        - (a), (b) and, (c) implies manager switches authorized users only.
        - Exception: Administrator can bypass this mechanism.

## Redis DB Backup

Lens3 uses "Snapshotting" of the database to a file.  The interval of
a snapshot and the file location can be found under the keywords
"save", "dbfilename", and "dir" in the configuration
"/etc/lenticularis/redis.conf".  Daily copying of snapshots should be
performed by cron, since Lens3 does nothing on the backup.  Lens3 uses
"save 907 1" by default, which is an interval about 15 minutes.

See Redis documents for more information: [Redis
persistence](https://redis.io/docs/manual/persistence/)

## Redis Service

Lens3 calls "redis-shutdown" with a fake configuration
"lenticularis/redis" in lenticularis-redis.service.  It lets point to
a file "/etc/lenticularis/redis.conf" in result.
