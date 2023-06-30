# api-conf.yaml

This is for Lens3 version v1.2.  Time values are all in seconds.

## Header Part

```
subject: "api"
version: "v1.2"
aws_signature: "AWS4-HMAC-SHA256"
```
Do not change these lines.

## Gunicorn Part

```
gunicorn:
    port: 8004
    workers: 2
    timeout: 120
    access_logfile: "/var/log/lenticularis/lens3-gunicorn-api-access-log"
    log_file: "/var/log/lenticularis/lens3-gunicorn-api-log"
    log_level: debug
    #log_syslog_facility: LOCAL8
    reload: yes
```

See the documents of Gunicorn.  Entires other than __port__ are
optional.

## Lens3-Api Part

```
controller:
    front_host: lens3.example.com
    trusted_proxies:
        - localhost
    base_path: "/api~"
    claim_uid_map: email-name
    probe_access_timeout: 60
    minio_mc_timeout: 10
    max_pool_expiry: 630720000
    csrf_secret_seed: xyzxyz
```

* __front_host__ is a host name of a proxy.  It is used as a HOST
  header when a Lens3-Api accesses Mux.

* __trusted_proxies__ is host names of the proxies.  The ip-addresses
  of them are checked when Lens3 receives a request.

* __base_path__ is a base-URL.  It is a path that a proxy drops.  It
  can be "".  Do not add a trailing slash.  A path shall usually
  include non-alphanumeric characters to avoid confusion with bucket
  names, when a single server co-hosts both S3 and Lens3-Api.

* __claim_uid_map__ is one of "id", "email-name", "map".  It specifies
  a mapping of a claim (an X-REMOTE-USER) to an uid.  "id" means
  unchanged, "email-name" takes the name part of an email (that is,
  before "@"), and "map" is a mapping which is defined by user
  registration.

* __probe_access_timeout__: is a tolerance when Lens3-Api accesses a
  Mux.

* __minio_mc_timeout__ is a tolerance when Lens3-Api issues an MC
  command.

* __max_pool_expiry__ is a time limit of a pool is active.  630720000
  is 10 years.

* __csrf_secret_seed__: is a seed used by CSRF prevention in
  fastapi_csrf_protect module.

## UI Part

```
ui:
    s3_url: https://lens3.example.com
    footer_banner: This site is operated by example.com
```

* __s3_url__: is just information.  It is displayed as an S3 endpoint
  in the UI.

* __footer_banner__: is also just information.  It is displayed as a
  footer in the UI.

## MinIO Part

```
minio:
    minio: /home/lens3/bin/minio
    mc: /home/lens3/bin/mc
```

These specify commands of MinIO.

## Logging Part

```
log_file: "/var/log/lenticularis/lens3-api-log"
log_syslog:
    facility: LOCAL7
    priority: DEBUG
```

* __log_file__: specifies a log file.  This entry is optional.  If
  log_file is specified, the log_syslog section is ignored.
