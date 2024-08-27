# Configuration Entries

## conf.json

"conf.json" contains the connection information to the keyval-db
(Valkey).  Only this file is directly read from programs.  Other
configurations are stored in the keyval-db.  It is passed to the
service as "lenticularis-mux -c /etc/lenticularis/conf.json".

- **ep**: is "localhost:6378".  It is an endpoint to the keyval-db.
- **password**: is a password string that should match with
  "requirepass" entry in "valkey.conf".

## mux-conf.json

"mux-conf.json" contains the setting of Multiplexer.  The contents are
stored in the keyval-db.

- **subject**: is "mux".  It identifies the conf is for Multiplexer.
- **version**: is "v2.1".
- **aws_signature**: is "AWS4-HMAC-SHA256".

### "multiplexer" configuration

- **port": 8003,
- **trusted_proxy_list": [
      "localhost"
    ],
- **mux_node_name": "localhost",
- **backend": "minio",
- **mux_ep_update_interval": 307,
- **error_response_delay_ms": 1000

### "manager" configuration

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

- **minio**: is "/usr/local/bin/minio".
- **mc**: is "/usr/local/bin/mc".

### "rclone" configuration

- **rclone**: is "/usr/local/bin/rclone".
- **command_options**: is a list of options passed to rclone command.

### "log" configuration

- **access_log_file**: is "/var/log/lenticularis/lens3-mux-access-log".

### "logging" configuration

- logger.**log_file**: is "/var/log/lenticularis/lens3-log".
- logger.**level**: is one of {"ERR", "WARNING", "INFO", "DEBUG"}.
  Set "DEBUG" for usefulness.
- logger.**tracing**: is bit flags to make logging verbose.  Set 0 or
  255.  Tracing logs are at "DEBUG" level.
- logger.**source_line**: is true or false, to include source line
  information.  See Golang's logging facility.

- **alert**: is an optional section for alerting.
- alert.**queue**: is "syslog" or "mqtt".
- alert.**level**: is a logger level.  Logs of this level or higher
  are sent to the alert queue.  Set "WARNING" for usefulness.

- syslog.**facility**: is "LOCAL7".

- mqtt.**ep**: is "localhost:1883".
- mqtt.**client**: is "lens3-logger".  It is an MQTT client.
- mqtt.**topic**: is "Lens3 Alert".  It is an MQTT topic.
- mqtt.**username**: is "lens3".  It is an MQTT user ID.
- mqtt.**password**: is a password.  It should match the password for
  one for the MQTT user.

- "stats".**sample_period**: is an interval to dump memory stats.

## reg-conf.json

"reg-conf.json" contains the setting of Registrar.  The contents are
stored in the keyval-db.

- **subject**: is "reg".
- **version**: is "v2.1".
- **aws_signature**: is "AWS4-HMAC-SHA256".

### "registrar" configuration

- **port**: is 8004, a port number to be used by Registrar.
- **server_ep**: is "localhost:8004", a concatenation of the hostname
  and the port.  It is used to redirect http requests to Registrar.
- **trusted_proxy_list**: is ["localhost"], a hostname of frontend
  proxy.
- **base_path**: is "/lens3.sts".
- **claim_uid_map**: "id",
- **user_approval**: "allow",
- **uid_allow_range_list**: [[1,99999]],
- **uid_block_range_list**: [[1,999]],
- **gid_drop_range_list**: [[1,999]],
- **gid_drop_list**: [50000],
- **user_expiration_days**: 180,
- **pool_expiration_days**: 180,
- **bucket_expiration_days**: 180,
- **secret_expiration_days**: 180,
- **error_response_delay_ms**: 1000,
- **ui_session_duration**: 1800

### "ui" configuration

- **ui.s3_url**: "https://lens3.exmaple.com",
- **ui.footer_banner**: "This site is operated by exmaple.com"

### "log" configuration

- **log.access_log_file**: "/var/log/lenticularis/lens3-reg-access-log"

### "logging" configuration

- **logging**: entry is optional and the same as mux-conf.  The one in
mux-conf has precedence if both reg-conf and mux-conf define one.
