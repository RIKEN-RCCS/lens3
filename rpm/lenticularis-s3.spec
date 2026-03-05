Name:           lenticularis-s3
Version:        2.2.1
Release:        1%{?dist}
Summary:        Multiplexer for AWS-S3 servers

License:        BSD-2-Clause
URL:            https://github.com/RIKEN-RCCS/lens3
# Source0:

ExclusiveArch:  x86_64

# BuildRequires:

Requires:       httpd mod_ssl mod_proxy_html mod_auth_openidc
Requires:       valkey
Requires:       mosquitto
Requires:       logrotate

Requires(post): policycoreutils-python-utils openssl

%description
Lenticularis-S3 is an AWS-S3 access multiplexer for servicing multiple
server instances at a single access point.

# %%autosetup -T

# %%pre

%install

cp -rp * %{buildroot}

# Generate a random string password for Valkey.

pw=$(openssl rand -base64 24 | tr '+/' 'XY')
sed -e "s/\"password\": \"[0-9a-zA-Z]*\"/\"password\": \"${pw}\"/" -i %{buildroot}/etc/lenticularis/lens3.conf
sed -e "s/requirepass \"[0-9a-zA-Z]*\"/requirepass \"${pw}\"/" -i %{buildroot}/etc/lenticularis/valkey.conf

%post

echo "Running Lenticularis-S3 post install."

systemd-sysusers

chown lenticularis:lenticularis /etc/lenticularis
chown lenticularis:lenticularis /etc/lenticularis/lens3.conf
chown lenticularis:lenticularis /etc/lenticularis/valkey.conf
chown lenticularis:lenticularis /var/lib/lenticularis
chown lenticularis:lenticularis /var/lib/lenticularis/mux-conf.json
chown lenticularis:lenticularis /var/lib/lenticularis/reg-conf.json
chown lenticularis:lenticularis /var/log/lenticularis
chown lenticularis:lenticularis /var/log/lenticularis-valkey

if [ $1 -eq 1 ] ; then
    # Run in first install, not upgrade.
    semanage fcontext -a -t redis_log_t "/var/log/lenticularis-valkey(/.*)?"
    restorecon -r -v /var/log/lenticularis-valkey
    restorecon -v /etc/httpd/conf.d/lens3proxy.conf
fi

semanage fcontext -l | grep lenticularis-valkey
ls -dlZ /var/log/lenticularis
ls -dlZ /var/log/lenticularis-valkey
ls -lZ /etc/httpd/conf.d/lens3proxy.conf

if [ $1 -eq 1 ] ; then
    semanage port -a -t http_port_t -p tcp 8003
    semanage port -a -t http_port_t -p tcp 8004
    semanage port -a -t redis_port_t -p tcp 6378
    # semanage port --list
    setsebool -P httpd_can_network_connect 1
fi

if [ $1 -eq 1 ] ; then
    firewall-cmd --reload --quiet
    firewall-cmd --state
    firewall-cmd --list-all
    firewall-cmd --zone=public --add-port=443/tcp --add-port=80/tcp --permanent
    firewall-cmd --reload
fi

# %%systemd_post lenticularis-valkey.service

systemctl daemon-reload
systemctl enable lenticularis-valkey
systemctl start lenticularis-valkey

/usr/local/bin/lenticularis-admin -c /etc/lenticularis/lens3.conf load-conf /var/lib/lenticularis/mux-conf.json
/usr/local/bin/lenticularis-admin -c /etc/lenticularis/lens3.conf load-conf /var/lib/lenticularis/reg-conf.json
/usr/local/bin/lenticularis-admin -c /etc/lenticularis/lens3.conf show-conf

# %%systemd_post lenticularis-mux.service

systemctl daemon-reload
systemctl enable lenticularis-mux
systemctl start lenticularis-mux

%files
%attr(440, -, -) /etc/sudoers.d/lenticularis-sudoers
%attr(644, -, -) /usr/lib/sysusers.d/lenticularis-user.conf
%attr(644, -, -) /usr/lib/systemd/system/lenticularis-mux.service
%attr(644, -, -) /usr/lib/systemd/system/lenticularis-valkey.service
# %%attr(644, -, -) /usr/lib/systemd/system-preset/50-lenticularis.preset
%attr(755, -, -) /usr/local/bin/lenticularis-admin
%attr(755, -, -) /usr/local/bin/lenticularis-mux
%dir %attr(770, -, -) /etc/lenticularis
%config(noreplace) %attr(660, -, -) /etc/lenticularis/lens3.conf
%config(noreplace) %attr(660, -, -) /etc/lenticularis/valkey.conf
%dir %attr(770, -, -) /var/lib/lenticularis
%config(noreplace) %attr(660, -, -) /var/lib/lenticularis/mux-conf.json
%config(noreplace) %attr(660, -, -) /var/lib/lenticularis/reg-conf.json
%config(noreplace) %attr(660, -, -) /etc/httpd/conf.d/lens3proxy.conf
%config(noreplace) %attr(644, -, -) /etc/logrotate.d/lenticularis-logrotate
%dir %attr(770, -, -) /var/log/lenticularis
%dir %attr(770, -, -) /var/log/lenticularis-valkey
%license /usr/share/licenses/lenticularis/LICENSE
%dnl %config(noreplace) %{_sysconfdir}/logrotate.d/%{name}
# %%doc add-docs-here

%changelog
* Mon Mar 02 2026 zzmatu <zzmatu@users.noreply.github.com>
- RPM package provided.
