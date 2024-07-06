# Contents of "unit-file" Directory

See "doc/setting-guide.md".

## Valkey Setting

[valkey/lenticularis-valkey.service](valkey/lenticularis-valkey.service)
is a systemd service file.  It should be copied in
"/lib/systemd/system/".  It is a copy of "valkey.service", whose some
of the settings are moved in "valkey.conf".

[valkey/valkey.conf](valkey/valkey.conf) is a configuration file.  It
should be copied in "/etc/lenticularis".  Its "requirepass" entry
should be set.

After starting systemd service "lenticularis-valkey", simple testing
of is `% valkey-cli -p 6378 -a "password-string" -n 1 --scan --pattern '*'`.
