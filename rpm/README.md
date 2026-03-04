# Binary Package RPM

## Steps to Make a Release RPM

Run the following after some prerequisite steps.  An RPM file will be
created in the usual "~/rpmbuild/RPMS/x86_64/".

  - Build lenticularis-s3 binaries
  - make cp; make rpm (in this directory)

## Prerequisite

```
sudo dnf install rpmdevtools rpmlint
```

Setup.  It creates ~/rpmbuild and subdirectories in it.

```
rpmdev-setuptree
```

(Unnecessary) A SPEC skeleton file is created with the following.

```
rpmdev-newspec lenticularis-s3
```

## What This RPM Does

See setting-guide.md for the manual installation procedure.

  - https://github.com/RIKEN-RCCS/lens3/blob/main/v2/doc/setting-guide.md

This RPM does what is on the setup procedure.

  - Install prerequisites
  - Make a pseudo user
  - Install the binaries in /usr/local/bin
  - Prepare directories for logging
  - Enable HTTP Connections
  - Set up the http-proxy (Apache-HTTPD)
  - Set up the keyval-db (Valkey)
  - Store Lens3 settings in the keyval-db
  - Set up sudoers for Lens3's Multiplexer
  - Set up log rotation
  - Start Lens3's services: Multiplexer and Registrar

But, this procedure skips some of the optional steps.

  - Set up system logging (to persistent storage)
  - Set up MQTT (Mosquitto)

## MEMO on RPM Spec: Pseudo User Creation in RPM

Lens3 needs a pseudo user "lenticularis".  Its UID/GID will be
dynamically assigned by "sysusers", and its home is
"/var/lib/lenticularis".  The pseudo user name is "lenticularis" while
it is "lens3" in the setting-guide.md.

"lenticularis-user.conf" is copied to /usr/lib/sysusers.d/.

RPM supports "sysusers".  Putting a file in /usr/lib/sysusers.d, RPM
will take care of it.  (systemctl restart systemd-sysusers).

https://rpm-software-management.github.io/rpm/manual/users_and_groups.html

Check the user assignment.

```
rpm -q --qf='[%{SYSUSERS}\n]' ~/rpmbuild/RPMS/x86_64/lenticularis-s3-2.2.1-1.el10.x86_64.rpm
```
See
https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/using_image_mode_for_rhel_to_build_deploy_and_manage_operating_systems/appendix-managing-users-groups-ssh-keys-and-secrets-in-image-mode-for-rhel
https://docs.fedoraproject.org/en-US/packaging-guidelines/UsersAndGroups/

## MEMO on RPM Spec: Requires(post)

The script in this RPM uses the following commands.

  - "/usr/sbin/semanage" (in Python) is in "policycoreutils-python-utils"
  - ("/usr/sbin/restorecon" restorecon -> setfiles)
  - "/usr/sbin/setfiles is in "policycoreutils"
  - "/usr/sbin/setsebool" is in "policycoreutils"
  - "/usr/bin/firewall-cmd" is in "firewalld"
  - "/usr/bin/openssl" is in "openssl"

And, it needs packages "policycoreutils-python-utils" and "openssl".
Note other "policycoreutils" and "firewalld" are in @core which is
installed in "Minimal Install".

See `dnf groupinfo core`.

## MEMO on RPM Spec: Requires Version Comparison

Versions of requirement are currently latest.  The spec file does not
specify versions at all.

  - httpd 2.4
  - Valkey 8
  - Mosquitto 2
  - logrotate 3

Version comparison is very poor, and specifying only the major version
is rather complex.  It is because the parts of alhanum are selected
and compared in strcmp's order.  For example, when wanting version=2,
it shall be written like "pkg > 1, pkg < 3" or "pkg >= 2.0.0, pkg <
3.0.0", where shorter "2." does not work.

http://ftp.rpm.org/api/4.4.2.2/rpmvercmp_8c-source.html

## MEMO on RPM: MEMO

In SPEC file, add `%autosetup -T`, where `-T` is to skip unpacking the
source.  See
https://rpm-software-management.github.io/rpm/manual/spec.html

## MEMO on RPM: MEMO

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
