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
https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/using_image_mode_for_rhel_to_build_deploy_and_manage_operating_systems/appendix-managing-users-groups-ssh-keys-and-secrets-in-image-mode-for-rhel
https://docs.fedoraproject.org/en-US/packaging-guidelines/UsersAndGroups/

## MEMO

In SPEC file, add `%autosetup -T`, where `-T` is to skip unpacking the
source.  See
https://rpm-software-management.github.io/rpm/manual/spec.html

## MEMO

RPM supports "sysusers".  Putting a file in /usr/lib/sysusers.d, RPM
will take care of it.  (systemctl restart systemd-sysusers).

https://rpm-software-management.github.io/rpm/manual/users_and_groups.html

## MEMO

In building RPM, we refer to the following descriptions:
  - https://rpm-software-management.github.io/rpm/manual/spec.html
  - https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/packaging_and_distributing_software/introduction-to-rpm
  - https://docs.fedoraproject.org/en-US/package-maintainers/Packaging_Tutorial/

Very basic ("create-rpm-package" is in Nov. 2020):
  - https://www.redhat.com/en/blog/create-rpm-package

Software Collections for Red Hat:
  - https://docs.redhat.com/en/documentation/red_hat_software_collections/2/html/packaging_guide/index

Example:
- https://rockylinux.pkgs.org/10/rockylinux-appstream-x86_64/valkey-8.0.7-1.el10_1.x86_64.rpm.html
- https://git.rockylinux.org/staging/rpms/valkey/-/tree/r10/SPECS

Sections of SPEC file:

- Preamble
- Build scriptlets
  - %build
  - %install
- Runtime scriptlets
- %files section
- %changelog section

;; install -p -D -m 0644 %{S:4} %{buildroot}%{_sysusersdir}/%{name}.conf

Selinux configuration:

- dnf info "selinux-policy-targeted"
- dnf info "policycoreutils"

Hints:

https://fedoraproject.org/wiki/PackagingDrafts/SELinux

RPM Macros:

https://github.com/systemd/systemd/blob/main/src/rpm/macros.systemd.in
