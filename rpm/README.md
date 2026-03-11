# Binary Package RPM

## Steps to Make a Release RPM

Run the following steps after installing some prerequisites.  An RPM
file will be created in the usual place "~/rpmbuild/RPMS/x86_64/".

  - Build lenticularis-s3 binaries
  - Copy "s3-baby-server" binary
  - make cp; make rpm (in this directory)

"s3-baby-server" is a small AWS-S3 server, which is a separate
software and can be found in github.com:

  https://github.com/RIKEN-RCCS/s3-baby-server

## Prerequisite

```
sudo dnf install rpmdevtools rpmlint
```

Setup.  It creates ~/rpmbuild and subdirectories in it.

```
rpmdev-setuptree
```

(Unnecessary) A SPEC skeleton file "lenticularis-s3.spec" is created
with the following.

```
rpmdev-newspec lenticularis-s3
```

## What This RPM Does

See "installation-procedure.md" for manual installation.

  - https://github.com/RIKEN-RCCS/lens3/blob/main/v2/doc/installation-procedure.md

This RPM does what is on the setup procedure.

  - Install prerequisites
  - Make a pseudo user ("lenticularis")
  - Install the binaries in /usr/local/bin
  - Prepare directories for logging
  - Enable HTTP Connections
  - Set up the http-proxy (Apache-HTTPD)
  - Set up the keyval-db (Valkey)
  - Store Lens3 settings in the keyval-db
  - Set up sudoers for Lens3's Multiplexer
  - Set up log rotation
  - Start services: Valkey and Lens3 Multiplexer

This procedure requires some setups manually.

  - Leave HTTPD service not started

This procedure skips some of the optional steps.

  - Set up system logging (to persistent storage)
  - Set up MQTT (Mosquitto)

## MEMO on RPM Spec: Pseudo User Creation in RPM

Lens3 needs a pseudo user "lenticularis".  Its UID/GID will be
dynamically assigned by "sysusers".  Its home is
"/var/lib/lenticularis".

Note the user by "sysusers" is not yet visible at copying by the
"%file" section.  So, it explicitly chowns in the "%post" section.

RPM says it supports "sysusers" -- by putting a file in
/usr/lib/sysusers.d, RPM will take care of it.  However, it seems not.
This spec-file runs "systemd-sysusers" in the "%post" section.

https://rpm-software-management.github.io/rpm/manual/users_and_groups.html

Check the user assignment.

```
rpm -q --qf='[%{SYSUSERS}\n]' ~/rpmbuild/RPMS/x86_64/lenticularis-s3-2.2.1-1.el10.x86_64.rpm
```
See

  - https://rpm.org/docs/4.19.x/manual/users_and_groups.html

## MEMO on RPM Spec: Starting services

"%systemd_post" does not start the service, even when "system-preset"
is specified.  This spec-file uses "systemctl start".

## MEMO on RPM Spec: Requires(post)

This spec-file uses the following commands.

  - "/usr/sbin/semanage" (in Python) is in "policycoreutils-python-utils"
  - ("/usr/sbin/restorecon" restorecon -> setfiles)
  - "/usr/sbin/setfiles is in "policycoreutils"
  - "/usr/sbin/setsebool" is in "policycoreutils"
  - "/usr/bin/firewall-cmd" is in "firewalld"
  - "/usr/bin/openssl" is in "openssl"

It needs packages "policycoreutils-python-utils" and "openssl".
Remaining "policycoreutils" and "firewalld" are in @core and are
expected to be installed.

See `dnf groupinfo core`.

## MEMO on RPM Spec: Requires Version Comparison

Requirement of versions are current latest.  This spec-file does not
specify versions at all.

  - httpd 2.4
  - Valkey 8
  - logrotate 3

Note that version comparison in RPM Spec is very poor.  Specifying
only the major version is rather boring.  Version comparison extracts
the parts of alhanum and compares them in strcmp's order.  For
example, when wanting version=2, it shall be written like "pkg > 1,
pkg < 3" or "pkg >= 2.0.0, pkg < 3.0.0", where shorter "2." does not
work.

http://ftp.rpm.org/api/4.4.2.2/rpmvercmp_8c-source.html

## MEMO on RPM Spec: Printing Messages

"echo" will print a message while installation, but only when with
verbose (-v).  But, stderr is printed always.

## MEMO on RPM Spec: BASICS OF RPM SPEC

The following descriptions are maybe in writing RPM Spec:

  - https://rpm-software-management.github.io/rpm/manual/spec.html
  - https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/packaging_and_distributing_software/introduction-to-rpm

Sections of SPEC file consist of:

  - Preamble
  - Build scriptlets
    - %build
    - %install
  - Runtime scriptlets
  - %files section
  - %changelog section

RPM Spec Examples (httpd and valkey):

  - https://git.rockylinux.org/staging/rpms/httpd/-/tree/r10/SPECS
  - https://git.rockylinux.org/staging/rpms/valkey/-/tree/r10/SPECS
  - https://rockylinux.pkgs.org/10/rockylinux-appstream-x86_64/valkey-8.0.7-1.el10_1.x86_64.rpm.html

RPM Macro Source:

  - https://github.com/systemd/systemd/blob/main/src/rpm/macros.systemd.in

## MEMO: Timestamps

File timestamps are the date of "%changelog".
