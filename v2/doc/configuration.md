# Configuration Entries

## conf.json

"conf.json" contains the connection information to the keyval-db
(Valkey).  It is passed to the service as
"lenticularis-mux -c /etc/lenticularis/conf.json".

- **ep**: is "localhost:6378", an endpoint to the keyval-db.
- **password**: is a password string that should match with
  "requirepass" entry in "valkey.conf".

## mux-conf.json

"mux-conf.json" contains the setting of Multiplexer.

- **subject**: is "mux".  It identifies the conf is for Multiplexer.
- **version**: is "v2.1".
- **aws_signature**: is "AWS4-HMAC-SHA256".

  "multiplexer": {
    "port": 8003,
    "trusted_proxy_list": [
      "localhost"
    ],
    "mux_node_name": "localhost",
    "backend": "minio",
    "mux_ep_update_interval": 307,
    "error_response_delay_ms": 1000
  },
  "manager": {
    "sudo": "/usr/bin/sudo",
    "port_min": 9000,
    "port_max": 9029,
    "backend_awake_duration": 300,
    "backend_start_timeout_ms": 60000,
    "backend_timeout_ms": 5000,
    "backend_timeout_suspension": 600,
    "backend_region": "us-east-1",
    "heartbeat_interval": 61,
    "heartbeat_miss_tolerance": 4
  },
  "minio": {
    "minio": "/usr/local/bin/minio",
    "mc": "/usr/local/bin/mc"
  },
  "rclone": {
    "rclone": "/usr/local/bin/rclone",
    "command_options": []
  },
  "log": {
    "access_log_file": "/var/log/lenticularis/lens3-mux-access-log"
  },
  "logging": {
    "logger": {
      "log_file": "/var/log/lenticularis/lens3-log",
      "level": "DEBUG",
      "tracing": 0,
      "source_line": false
    },
    "alert": {
      "queue": "mqtt",
      "level": "WARNING"
    },
    "syslog": {
      "facility": "LOCAL7"
    },
    "mqtt": {
      "ep": "localhost:1883",
      "client": "lens3-logger",
      "topic": "Lens3 Alert",
      "username": "lens3",
      "password": "lEXw0tR6cB5ueTRkSFLZLsjMEPgQ9ah8QeKwdKUZ"
    },
    "stats": {
      "sample_period": 600
    }
  }
}

## reg-conf.json

"reg-conf.json" contains the setting of Registrar.

- **subject**: is "reg".
- **version**: is "v2.1".
- **aws_signature**: is "AWS4-HMAC-SHA256".

### "registrar" subfields

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

### "ui" subfields

- **ui.s3_url**: "https://lens3.exmaple.com",
- **ui.footer_banner**: "This site is operated by exmaple.com"

### "log" subfields

- **log.access_log_file**: "/var/log/lenticularis/lens3-reg-access-log"

### "logging**" subfields

- **logging**: entry is optional and the same as mux-conf.  The one in
mux-conf has precedence if both reg-conf and mux-conf define one.
