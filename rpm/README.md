# Building Binary Package RPM

## What This RPM Does

See setting-guide.md for the manual installation procedure.

  - https://github.com/RIKEN-RCCS/lens3/blob/main/v2/doc/setting-guide.md

This RPM does what is on the setup procedure.

  - Install prerequisites
  - Make a pseudo user
  - Install the binaries in /usr/local/bin
  - Prepare directories for logging
  - Enable HTTP Connections
  - Set up and start the http-proxy (Apache-HTTPD)
  - Set up and start the keyval-db (Valkey)
  - Store Lens3 settings in the keyval-db
  - Set up sudoers for Lens3's Multiplexer
  - Set up log rotation
  - Start Lens3's services: Multiplexer and Registrar

But, this procedure skips some of the steps.

  - Set up system logging
  - Set up MQTT

In building RPM, we refer to the following descriptions:

  - https://www.redhat.com/en/blog/create-rpm-package
  - https://rpm-software-management.github.io/rpm/manual/spec.html
  - https://docs.fedoraproject.org/en-US/package-maintainers/Packaging_Tutorial/

"create-rpm-package" is in Nov. 2020.

## Prerequisite

```
sudo dnf install rpmdevtools rpmlint
```

Setup.  It creates ~/rpmbuild and subdirectories in it.

```
rpmdev-setuptree
```

A SPEC skeleton file is created with the following.

```
rpmdev-newspec lenticularis-s3
```

## Run make

```
make cp
make rpm
```

## Pseudo User Creation in RPM

Lens3 needs a pseudo user "lenticularis".  Its UID/GID will be
dynamically assigned by "sysusers", and its home is
"/var/lib/lenticularis".  The pseudo user name is "lenticularis" while
it is "lens3" in the setting-guide.md.

"lenticularis.conf" is copied to /usr/lib/sysusers.d/.

Check the user assignment.

```
rpm -q --qf='[%{SYSUSERS}\n]' ~/rpmbuild/RPMS/x86_64/lenticularis-s3-2.2.1-1.el10.x86_64.rpm
```

See
https://docs.fedoraproject.org/en-US/packaging-guidelines/UsersAndGroups/

## MEMO

In SPEC file, add `%autosetup -T`, where `-T` is to skip unpacking the
source.  See
https://rpm-software-management.github.io/rpm/manual/spec.html
