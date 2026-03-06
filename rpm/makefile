## makefile

BUILD = ~/rpmbuild/BUILD

all::
	@echo "Run 'make cp', 'make lint' then 'make rpm'"
	@echo "  - 'make cp' copies files to ~/rpmbuild/BUILD."
	@echo "  - 'make rpm' runs rpmbuild -bb on lenticularis-s3.spec."

rpm::
	cp -p lenticularis-s3.spec ~/rpmbuild/SPECS/
	rpmbuild -v -bb ~/rpmbuild/SPECS/lenticularis-s3.spec

s3-baby-server:
	$(error RPM needs the s3-baby-server binary. Copy and place it here.)

cp:: s3-baby-server
	mkdir -p $(BUILD)/usr/share/licenses/lenticularis
	cp ../LICENSE $(BUILD)/usr/share/licenses/lenticularis/
	##
	mkdir -p $(BUILD)/usr/local/bin
	cp ../v2/cmd/lenticularis-mux/lenticularis-mux $(BUILD)/usr/local/bin/
	cp ../v2/cmd/lenticularis-admin/lenticularis-admin $(BUILD)/usr/local/bin/
	cp ./s3-baby-server $(BUILD)/usr/local/bin/
	##
	mkdir -p $(BUILD)/usr/lib/sysusers.d
	cp ../v2/unit-file/lenticularis-user.conf $(BUILD)/usr/lib/sysusers.d/
	##
	mkdir -p $(BUILD)/etc/sudoers.d
	cp ../v2/unit-file/lenticularis-sudoers $(BUILD)/etc/sudoers.d/
	##
	mkdir -p $(BUILD)/usr/lib/systemd/system
	cp ../v2/unit-file/lenticularis-mux.service $(BUILD)/usr/lib/systemd/system/
	cp ../v2/unit-file/lenticularis-valkey.service $(BUILD)/usr/lib/systemd/system/
	##
	mkdir -p $(BUILD)/usr/lib/systemd/system-preset
	#cp ../v2/unit-file/lenticularis.preset $(BUILD)/usr/lib/systemd/system-preset/50-lenticularis.preset
	##
	mkdir -p $(BUILD)/etc/lenticularis
	cp ../v2/unit-file/lens3.conf $(BUILD)/etc/lenticularis/
	cp ../v2/unit-file/valkey.conf $(BUILD)/etc/lenticularis/
	##
	mkdir -p $(BUILD)/var/lib/lenticularis
	cp ../v2/unit-file/mux-conf.json $(BUILD)/var/lib/lenticularis/
	cp ../v2/unit-file/reg-conf.json $(BUILD)/var/lib/lenticularis/
	##
	mkdir -p $(BUILD)/etc/httpd/conf.d
	cp ../v2/proxy-apache/lens3proxy-basic.conf $(BUILD)/etc/httpd/conf.d/lens3proxy.conf
	##
	mkdir -p $(BUILD)/var/log/lenticularis
	mkdir -p $(BUILD)/var/log/lenticularis-valkey
	##
	mkdir -p $(BUILD)/etc/logrotate.d
	cp ../v2/unit-file/lenticularis-logrotate $(BUILD)/etc/logrotate.d/

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
