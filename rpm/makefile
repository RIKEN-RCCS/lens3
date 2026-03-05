## makefile

BUILDDIR = ~/rpmbuild/BUILD

all::
	@echo "Run 'make cp' then 'make rpm'"

rpm::
	cp -p lenticularis-s3.spec ~/rpmbuild/SPECS/
	rpmbuild -v -bb ~/rpmbuild/SPECS/lenticularis-s3.spec

cp::
	mkdir -p $(BUILDDIR)/usr/share/licenses/lenticularis
	cp ../LICENSE $(BUILDDIR)/usr/share/licenses/lenticularis/
	##
	mkdir -p $(BUILDDIR)/usr/local/bin
	cp ../v2/cmd/lenticularis-mux/lenticularis-mux $(BUILDDIR)/usr/local/bin/
	cp ../v2/cmd/lenticularis-admin/lenticularis-admin $(BUILDDIR)/usr/local/bin/
	##
	mkdir -p $(BUILDDIR)/usr/lib/sysusers.d
	cp ../v2/unit-file/lenticularis-user.conf $(BUILDDIR)/usr/lib/sysusers.d/
	##
	mkdir -p $(BUILDDIR)/etc/sudoers.d
	cp ../v2/unit-file/lenticularis-sudoers $(BUILDDIR)/etc/sudoers.d/
	##
	mkdir -p $(BUILDDIR)/usr/lib/systemd/system
	cp ../v2/unit-file/lenticularis-mux.service $(BUILDDIR)/usr/lib/systemd/system/
	cp ../v2/unit-file/lenticularis-valkey.service $(BUILDDIR)/usr/lib/systemd/system/
	##
	mkdir -p $(BUILDDIR)/usr/lib/systemd/system-preset
	#cp ../v2/unit-file/lenticularis.preset $(BUILDDIR)/usr/lib/systemd/system-preset/50-lenticularis.preset
	##
	mkdir -p $(BUILDDIR)/etc/lenticularis
	cp ../v2/unit-file/lens3.conf $(BUILDDIR)/etc/lenticularis/
	cp ../v2/unit-file/valkey.conf $(BUILDDIR)/etc/lenticularis/
	##
	mkdir -p $(BUILDDIR)/var/lib/lenticularis
	cp ../v2/unit-file/mux-conf.json $(BUILDDIR)/var/lib/lenticularis/
	cp ../v2/unit-file/reg-conf.json $(BUILDDIR)/var/lib/lenticularis/
	##
	mkdir -p $(BUILDDIR)/etc/httpd/conf.d
	cp ../v2/proxy-apache/lens3proxy-basic.conf $(BUILDDIR)/etc/httpd/conf.d/lens3proxy.conf
	##
	mkdir -p $(BUILDDIR)/var/log/lenticularis
	mkdir -p $(BUILDDIR)/var/log/lenticularis-valkey
	##
	mkdir -p $(BUILDDIR)/etc/logrotate.d
	cp ../v2/unit-file/lenticularis-logrotate $(BUILDDIR)/etc/logrotate.d/

dump::
	rpm --eval '_arch=%{_arch}' \
	--eval 'dist=%{?dist}' \
	--eval 'buildroot=%{buildroot}' \
	--eval '_sysconfdir=%{_sysconfdir}' \
	--eval '_sysusersdir=%{_sysusersdir}' \
	--eval 'S:4=%{S:4}'

	# rpm --showrc

lint::
	rpmlint lenticularis-s3.spec

RPM = ~/rpmbuild/RPMS/x86_64/lenticularis-s3-2.2.1-1.el10.x86_64.rpm

rpm-install::
	dnf -v --rpmverbosity=debug install $(RPM)

rpm-uninstall::
	dnf -v remove lenticularis-s3

del-user::
	userdel lenticularis

test-install::
	rpm -ivvh --test $(RPM)

test-upgrade::
	rpm -Uvvh --test $(RPM)

show-scripts::
	rpm -q --scripts $(RPM)

show-user::
	rpm -q --qf='[%{SYSUSERS}\n]' $(RPM)

show-files::
	rpm -q --list $(RPM)
