# Configuration Entries

## conf.json

"conf.json" contains the connection information to the keyval-db
(Valkey).  Only this file is directly read from programs.  Other
configurations are stored in the keyval-db.  It is passed to the
service as "lenticularis-mux -c /etc/lenticularis/conf.json".

- **ep**: is "localhost:6378".  It is an endpoint to the keyval-db.
- **password**: is a password string that should match with
  "requirepass" entry in "valkey.conf".

## Multiplexer Configuration: mux-conf.json

"mux-conf.json" contains the setting of Multiplexer.  The contents are
stored in the keyval-db.

- **subject**: is "mux".  It identifies the conf is for Multiplexer.
- **version**: is "v2.1".
- **aws_signature**: is "AWS4-HMAC-SHA256".

### "multiplexer" configuration

"multiplexer" section defines Multiplexer operations.

- **port**: is 8003.  It is a port number to be used by Multiplexer.
- **trusted_proxy_list**: is ["localhost"].  It is hostnames of the
  frontend proxy and Registrar.
- **mux_node_name**: is "localhost".  It is optional.  It is a
  hostname on which Multiplexer is running, and it is used when
  Registrar accesses Multiplexer.
- **backend**: is "minio" or "rclone".
- **mux_ep_update_interval**: is an interval for which Multiplexer
  repeatedly sets its endpoint in the keyval-db.
- **error_response_delay_ms**: is a delay added when sending a
  response for a failed http request.

### "manager" configuration

"manager" section defines the behavior of backend instances.

- **sudo**: is "/usr/bin/sudo".
- **port_min**: is the range of ports to be used (lower bound).
- **port_max**: is the range of ports to be used (upper bound).
- **backend_awake_duration** (in sec): is a duration a backend is
  running.  A backend will be stopped when it is idle for this
  duration.
- **backend_start_timeout_ms**: is a timeout for starting a backend.
  It is an error when it fails to start in time.
- **backend_timeout_ms**: is a timeout for request processing in a
  backend.  It is an error when it fails to respond in time.
- **backend_timeout_suspension** (in sec): is a duration of keeping a
  backend in the suspended state, when a backend fails to start.  A
  backend won't be started in the suspended state, to avoid
  unnecessary stress to the server.
- **backend_region**: is "us-east-1".
- **heartbeat_interval**: is a heartbeat interval.
- **heartbeat_miss_tolerance**: is a heartbeat misstolerance.

### "minio" configuration

"minio" section is for MinIO backend.

- **minio**: is "/usr/local/bin/minio".
- **mc**: is "/usr/local/bin/mc".

### "rclone" configuration

"rclone" section is for rclone-serve-s3 backend.

- **rclone**: is "/usr/local/bin/rclone".
- **command_options**: is a list of options passed to rclone command.

### "log" configuration

"log" section defines the access log file.

- **access_log_file**: is "/var/log/lenticularis/lens3-mux-access-log".

### "logging" configuration

"logging" section defines logging operation.

- **logger.log_file**: is "/var/log/lenticularis/lens3-log".
- **logger.level**: is one of {"ERR", "WARNING", "INFO", "DEBUG"}.
  Set "DEBUG" for usefulness.
- **logger.tracing**: is bit flags to make logging verbose.  Set 0 or
  255.  Tracing logs are at "DEBUG" level.
- **logger.source_line**: is true or false, to include source code
  line information.  See Golang's logging facility.

- **alert**: is an optional section for alerting.  Some of the logs
  can be sent to syslog or MQTT.
- **alert.queue**: is "syslog" or "mqtt".
- **alert.level**: is a logger level.  Logs of this level or higher
  are sent to the alert queue.  Set "ERR" or "WARNING" usually.

- **syslog.facility**: is "LOCAL7".

- **mqtt.ep**: is "localhost:1883".
- **mqtt.client**: is a client ID.  It is for keeping MQTT sessions.
- **mqtt.topic**: is a topic of messages.
- **mqtt.username**: is "lens3".  A user with its password should be
  registered in the MQTT server.
- **mqtt.password**: is a password for the MQTT user.

- **stats.sample_period** (in sec): is an interval to dump memory
  stats.  Use 0 to disable dumps.

## Registrar Configuration: reg-conf.json

"reg-conf.json" contains the setting of Registrar.  The contents are
stored in the keyval-db.

- **subject**: is "reg".
- **version**: is "v2.1".
- **aws_signature**: is "AWS4-HMAC-SHA256".

### "registrar" configuration

"registrar" section defines Registrar operations.

- **port**: is 8004.  It is a port number to be used by Registrar.
- **server_ep**: is "localhost:8004".  It is a hostname and port pair.
  It is used to redirect http requests (that is, "/lens3.sts/" to
  "/lens3.sts/ui/index.html").  The frontend proxy will translate
  "localhost" appropriately.
- **trusted_proxy_list**: is ["localhost"].  It is a hostname of
  the frontend proxy.
- **base_path**: is "/lens3.sts".
- **claim_uid_map**: is one of {"id", "email-name", "map"}.  It
  selects interpretation of names from authentication (such as OIDC).
  "id" uses a passed name as an UID, "email-name" picks the part
  before at-mark, and "map" uses mapping registered in the keyval-db.
- **user_approval**: is "allow" or "block".  When "block", users need
  to be registered in the keyval-db.  Unregistered users will be
  rejected.
- **uid_allow_range_list**: is a list of ranges.  User's UID should be
  in one of the ranges.
- **uid_block_range_list**: is a list of ranges.  User's UID should
  not be in any of the ranges.  The block list has precedence.
- **gid_drop_range_list**: is a list of ranges.  User's GID list is
  filtered by these ranges.
- **gid_drop_list**: is a list of GID's.  User's GID list is filtered
  by the values.
- **user_expiration_days**: is 180 days.  Accessing Registrar extends
  the expiration.
- **pool_expiration_days**: is 180 days.  A pool will expire in 180
  days after creation.
- **bucket_expiration_days**: is 180 days.  A bucket will expire in
  180 days after creation.
- **secret_expiration_days**: is 180 days.  Creating a secret valid
  longer than 180 days will be rejected.
- **error_response_delay_ms**: is a delay added when sending a
  response for a failed http request.
- **ui_session_duration**: is a duration of UI sessions for CSRF
  prevention.  It needs to refresh a cookie by reloading
  "/ui/index.html".

### "ui" configuration

"ui" section stores messages displayed in Web-UI.

- **ui.s3_url**: is something like "https⦂//lens3․example․com".
- **ui.footer_banner**: is "This site is operated by example.com".

### "log" configuration

"log" section defines the access log file.

- **log.access_log_file**: is "/var/log/lenticularis/lens3-reg-access-log".

### "logging" configuration

"logging" section is optional and the same as mux-conf.  The one in
mux-conf has precedence if both reg-conf and mux-conf define one.
