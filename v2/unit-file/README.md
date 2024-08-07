# Systemd Service Files

See: [v2/doc/setting-guide.md](../doc/setting-guide.md)

## Lenticularis Service

[lenticularis-mux.service](lenticularis-mux.service) is a systemd
service file.  It should be copied in "/lib/systemd/system/".

[conf.json](conf.json) stores connection information to Valkey.  Copy
it in "/etc/lenticularis".  KEEP IT SECURE.  Set "password" with
Valkey's password.

[mux-conf.json](mux-conf.json) and [reg-conf.json](reg-conf.json) are
Lenticularis settings.  It is loaded in keyval-db (Valkey) with
"lens3-admin" command.

## Valkey Service

[lenticularis-valkey.service](lenticularis-valkey.service) is a
systemd service file.  It should be copied in "/lib/systemd/system/".
It is a modified copy of "valkey.service" in the Valkey package.

[valkey.conf](valkey.conf) is a configuration file.  It should be
copied in "/etc/lenticularis".  KEEP IT SECURE.  Set "requirepass"
entry.

After starting systemd service "lenticularis-valkey", a simple test to
check the start of valkey is:

```
$ valkey-cli -p 6378 -a "password-string" -n 1 --scan --pattern '*'`.
```

## Other Setting Files

[lenticularis-logrotate](lenticularis-logrotate) is an optional
settings for logrotate.
