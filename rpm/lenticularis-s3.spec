Name:           lenticularis-s3
Version:        2.2.1
Release:        1%{?dist}
Summary:        A multiplexer for AWS-S3 servers

License:        BSD-2-Clause
URL:            https://github.com/RIKEN-RCCS/lens3
# Source0:

ExclusiveArch:  x86_64

# BuildRequires:

Requires:       httpd mod_ssl mod_proxy_html mod_auth_openidc
Requires:       valkey = 8
Requires:       mosquitto = 2
Requires:       logrotate = 3

%description
RPM of Lenticularis-S3.

# %%autosetup -T

%install

cp -rp * %{buildroot}

%post

systemctl restart systemd-sysusers

chmod 440 /etc/sudoers.d/lenticularis-sudoers
chmod 644 /etc/logrotate.d/lenticularis-logrotate

chown lenticularis:lenticularis /var/log/lenticularis
chmod 700 /var/log/lenticularis

mkdir -p /var/log/lenticularis-valkey
chown lenticularis:lenticularis /var/log/lenticularis-valkey
chmod 700 /var/log/lenticularis-valkey
semanage fcontext -a -t redis_log_t "/var/log/lenticularis-valkey(/.*)?"
restorecon -r -v /var/log/lenticularis-valkey

restorecon -v /etc/httpd/conf.d/lens3proxy.conf

semanage fcontext -l | grep lenticularis-valkey
ls -dlZ /var/log/lenticularis
ls -dlZ /var/log/lenticularis-valkey
ls -lZ /etc/httpd/conf.d/lens3proxy.conf

semanage port -a -t http_port_t -p tcp 8003
semanage port -a -t http_port_t -p tcp 8004
semanage port -a -t redis_port_t -p tcp 6378
semanage port --list
setsebool -P httpd_can_network_connect 1

semanage port --list

firewall-cmd --state
firewall-cmd --list-all
firewall-cmd --zone=public --add-port=443/tcp --add-port=80/tcp --permanent
firewall-cmd --reload

if [ $1 -eq 1 ] ; then
    # Run in first install, not upgrade.
    pw=$(openssl rand -base64 24 | tr '+/' 'XY')
    sed -e "s/\"password\": \"[0-9a-zA-Z]*\"/\"password\": \"${pw}\"/" -i /etc/lenticularis/conf.json
    sed -e "s/requirepass \"[0-9a-zA-Z]*\"/requirepass \"${pw}\"/" -i /etc/lenticularis/valkey.conf
fi

chown lenticularis:lenticularis /etc/lenticularis/conf.json
chmod 660 /etc/lenticularis/conf.json
chown lenticularis:lenticularis /etc/lenticularis/valkey.conf
chmod 660 /etc/lenticularis/valkey.conf

systemctl daemon-reload
systemctl enable lenticularis-valkey
systemctl start lenticularis-valkey

/usr/local/bin/lens3-admin -c /var/lib/lenticularis/conf.json load-conf /var/lib/lenticularis/mux-conf.json
/usr/local/bin/lens3-admin -c /var/lib/lenticularis/conf.json load-conf /var/lib/lenticularis/reg-conf.json
/usr/local/bin/lens3-admin -c /var/lib/lenticularis/conf.json show-conf

systemctl daemon-reload
systemctl enable lenticularis-mux
systemctl start lenticularis-mux

%files
/etc/sudoers.d/lenticularis-sudoers
/etc/lenticularis/conf.json
/etc/lenticularis/valkey.conf
/etc/logrotate.d/lenticularis-logrotate
/etc/httpd/conf.d/lens3proxy.conf
/usr/lib/systemd/system/lenticularis-mux.service
/usr/lib/systemd/system/lenticularis-valkey.service
/usr/lib/sysusers.d/lenticularis-user.conf
/usr/local/bin/lens3-admin
/usr/local/bin/lenticularis-mux
/var/lib/lenticularis
/var/log/lenticularis

%dnl %config(noreplace) %{_sysconfdir}/logrotate.d/%{name}

%license /usr/share/licenses/lenticularis/LICENSE
# %%doc add-docs-here

%changelog
* Mon Mar 02 2026 zzmatu <zzmatu@users.noreply.github.com>
- RPM package provided.
