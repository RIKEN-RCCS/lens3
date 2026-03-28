# Configuration Entries

## Keyval-DB Connection (lens3.conf)

"lens3.conf" contains the connection information to the keyval-db
(Valkey).  It is installed as "/etc/lenticularis/lens3.conf".  As all
configurations are stored in the keyval-db, this is the only file
directly read from the programs.  KEEP IT SECURE, because it includes
a password.  It is passed to the service as:

```
lenticularis-mux -c /etc/lenticularis/lens3.conf
```

The entries in "lens3.conf" are:

  - __ep__: is "localhost:6378".  It is an endpoint to the keyval-db.
  - __password__: is a password string that should match with
    "requirepass" entry in "valkey.conf".

## Multiplexer Configuration (mux.conf)

It is recommended to copy "mux-default.conf" as "mux.conf" (for
example) in "/var/lib/lenticularis/" and use it.  Existence of other
files named "mux*.conf" in the directory will prevent reloading the
configuration during RPM installation.  Moreover, the default
configuration "mux-default.conf" will be overwritten during RPM
installation.

"mux.conf" contains the setting of Multiplexer.  The contents are
stored in the keyval-db.

  - __subject__: is "mux".  It identifies the conf is for Multiplexer.
  - __version__: is "v2.2".
  - __aws_signature__: is "AWS4-HMAC-SHA256".

### "multiplexer" configuration

"multiplexer" section defines Multiplexer operations.

  - __port__: is 8003.  It is a port number to be used by Multiplexer.
  - __trusted_proxy_list__: is ["localhost"].  It is hostnames of the
    frontend proxy and Registrar.
  - __mux_node_name__: is "localhost".  It is optional.  It is a
    hostname on which Multiplexer is running, and it is used when
    Registrar accesses Multiplexer.
  - __backend__: is "baby-server" (other choice is "minio" or "rclone").
  - __mux_ep_update_interval__: is an interval for which Multiplexer
    repeatedly sets its endpoint in the keyval-db.
  - __error_response_delay_ms__: is a delay added when sending a
    response for a failed http request.

### "manager" configuration

"manager" section defines the behavior of backend instances.

  - __sudo__: is "/usr/bin/sudo".
  - __port_min__: is the range of ports to be used (lower bound).
  - __port_max__: is the range of ports to be used (upper bound).
  - __backend_awake_duration__ (in sec): is a duration a backend is
    running.  A backend will be stopped when it is idle for this
    duration.
  - __backend_start_timeout_ms__: is a timeout for starting a backend.
    It is an error when it fails to start in time.
  - __backend_timeout_ms__: is a timeout for request processing in a
    backend.  It is an error when it fails to respond in time.
  - __backend_timeout_suspension__ (in sec): is a duration of keeping a
    backend in the suspended state, when a backend fails to start.  A
    backend won't be started in the suspended state, to avoid
    unnecessary stress to the server.
  - __backend_region__: is "us-east-1".
  - __heartbeat_interval__: is a heartbeat interval.
  - __heartbeat_miss_tolerance__: is a heartbeat misstolerance.

### "baby-server" configuration

"baby-server" section defines S3 Baby-server backend.

  - __path__: is  "/usr/local/bin/s3-baby-server"
  - __command_options__: is [].  It is appended to the command line.
  - __control__: is "bbs.ctl".  It is the URL path for controlling
    Baby-server, to shutdown the server or to dump memory statistics.

### ("minio" configuration)

"minio" section is for MinIO backend.

  - __minio__: is "/usr/local/bin/minio".
  - __mc__: is "/usr/local/bin/mc".

### ("rclone" configuration)

"rclone" section is for rclone-serve-s3 backend.

  - __path__: is "/usr/local/bin/rclone".
  - __command_options__: is a list of options passed to rclone command.

### "access_log" configuration

"access_log" section defines the access log file.

- __access_log_file__: is "/var/log/lenticularis/lens3-mux-access-log".

### "logging" configuration

"logging" section defines logging operation.

  - __logger.log_file__: is "/var/log/lenticularis/lens3-mux-log".
  - __logger.level__: is one of {"ERR", "WARNING", "INFO", "DEBUG"}.
    Set "DEBUG" for usefulness.
  - __logger.tracing__: is bit flags to make logging verbose.  Set 0 or
    255.  Tracing logs are at "DEBUG" level.
  - __logger.source_line__: is true or false, to include source code
    line information.  See Golang's logging facility.

  - __alert__: is an optional section for alerting.  Some of the logs
    can be sent to syslog or MQTT.
  - __alert.queue__: is "syslog" or "mqtt".
  - __alert.level__: is a logger level.  Logs of this level or higher
    are sent to the alert queue.  Set "ERR" or "WARNING" usually.
  - __alert.off__: disabes alerting when it is true.

  - __syslog.facility__: is "LOCAL7".

  - __mqtt.ep__: is "localhost:1883".
  - __mqtt.client__: is a client ID.  It is for keeping MQTT sessions.
  - __mqtt.topic__: is a topic of messages.
  - __mqtt.username__: is "lens3".  A user with its password should be
    registered in the MQTT server.
  - __mqtt.password__: is a password for the MQTT user.

  - __stats.sample_period__ (in sec): is an interval to dump memory
    stats.  Use 0 to disable dumps.

## Registrar Configuration (reg.conf)

It is recommended to copy "mux-default.conf" as "mux.conf" (for
example) in "/var/lib/lenticularis/" and use it.  See Section about
"mux.conf".

"reg.conf" contains the setting of Registrar.  The contents are
stored in the keyval-db.

  - __subject__: is "reg".
  - __version__: is "v2.2".
  - __aws_signature__: is "AWS4-HMAC-SHA256".

### "registrar" configuration

"registrar" section defines Registrar operations.

  - __port__: is 8004.  It is a port number to be used by Registrar.
  - __server_ep__: is "localhost:8004".  It is a hostname and port pair.
    It is used to redirect http requests (that is, "/lens3.sts/" to
    "/lens3.sts/ui/index.html").  The frontend proxy will translate
    "localhost" appropriately.
  - __trusted_proxy_list__: is ["localhost"].  It is a hostname of
    the frontend proxy.
  - __base_path__: is "/lens3.sts".
  - __claim_uid_map__: is one of {"id", "email-name", "map"}.  It
    selects interpretation of names from authentication (such as OIDC).
    "id" uses a passed name as an UID, "email-name" picks the part
    before at-mark, and "map" uses mapping registered in the keyval-db.
  - __user_approval__: is "allow" or "block".  When "block", users need
    to be registered in the keyval-db.  Unregistered users will be
    rejected.
  - __uid_allow_range_list__: is a list of ranges.  User's UID should be
    in one of the ranges.
  - __uid_block_range_list__: is a list of ranges.  User's UID should
    not be in any of the ranges.  The block list has precedence.
  - __gid_drop_range_list__: is a list of ranges.  User's GID list is
    filtered by these ranges.
  - __gid_drop_list__: is a list of GID's.  User's GID list is filtered
    by the values.
  - __user_expiration_days__: is 180 days.  Accessing Registrar extends
    the expiration.
  - __pool_expiration_days__: is 180 days.  A pool will expire in 180
    days after creation.
  - __bucket_expiration_days__: is 180 days.  A bucket will expire in
    180 days after creation.
  - __secret_expiration_days__: is 180 days.  Creating a secret valid
    longer than 180 days will be rejected.
  - __error_response_delay_ms__: is a delay added when sending a
    response for a failed http request.
  - __ui_session_duration__: is a duration of UI sessions for CSRF
    prevention.  It needs to refresh a cookie by reloading
    "/ui/index.html".

### "ui" configuration

"ui" section stores messages displayed in Web-UI.

  - __ui.s3_url__: is something like "https⦂//lens3․example․com".
  - __ui.footer_banner__: is "This site is operated by example.com".

### "access_log" configuration

"access_log" section defines the access log file.

  - __log.access_log_file__: is "/var/log/lenticularis/lens3-reg-access-log".

### "logging" configuration

"logging" section is the same as mux.conf.

  - __logger.log_file__: is "/var/log/lenticularis/lens3-reg-log".
