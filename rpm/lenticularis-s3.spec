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

%install

cp -rp * %{buildroot}

%post

%__systemd_sysusers
# systemctl restart systemd-sysusers

if [ $1 -eq 1 ] ; then
    semanage fcontext -a -t redis_log_t "/var/log/lenticularis-valkey(/.*)?"
    restorecon -r -v /var/log/lenticularis-valkey
    restorecon -v /etc/httpd/conf.d/lens3proxy.conf
fi

echo "Print selinux state"
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

# Set a password for Valkey access.

if [ $1 -eq 1 ] ; then
    # Run in first install, not upgrade.
    pw=$(openssl rand -base64 24 | tr '+/' 'XY')
    sed -e "s/\"password\": \"[0-9a-zA-Z]*\"/\"password\": \"${pw}\"/" -i /etc/lenticularis/lens3.conf
    sed -e "s/requirepass \"[0-9a-zA-Z]*\"/requirepass \"${pw}\"/" -i /etc/lenticularis/valkey.conf
    chown lenticularis:lenticularis /etc/lenticularis/lens3.conf
    chmod 660 /etc/lenticularis/lens3.conf
    chown lenticularis:lenticularis /etc/lenticularis/valkey.conf
    chmod 660 /etc/lenticularis/valkey.conf
fi

# systemctl daemon-reload
# systemctl enable lenticularis-valkey
# systemctl start lenticularis-valkey

%systemd_post lenticularis-valkey.service

/usr/local/bin/lens3-admin -c /etc/lenticularis/lens3.conf load-conf /var/lib/lenticularis/mux-conf.json
/usr/local/bin/lens3-admin -c /etc/lenticularis/lens3.conf load-conf /var/lib/lenticularis/reg-conf.json
/usr/local/bin/lens3-admin -c /etc/lenticularis/lens3.conf show-conf

# systemctl daemon-reload
# systemctl enable lenticularis-mux
# systemctl start lenticularis-mux

%systemd_post lenticularis-mux.service

%files
%attr(755, -, -) /usr/local/bin/lens3-admin
%attr(755, -, -) /usr/local/bin/lenticularis-mux
%attr(644, -, -) /usr/lib/systemd/system/lenticularis-mux.service
%attr(644, -, -) /usr/lib/systemd/system/lenticularis-valkey.service
%attr(644, -, -) /usr/lib/systemd/system-preset/50-lenticularis.preset
%attr(644, -, -) /usr/lib/sysusers.d/lenticularis-user.conf
%attr(644, -, -) /etc/logrotate.d/lenticularis-logrotate
%attr(770, lenticularis, lenticularis) /var/lib/lenticularis
%dir %attr(700, lenticularis, lenticularis) /var/log/lenticularis
%dir %attr(700, lenticularis, lenticularis) /var/log/lenticularis-valkey
%attr(700, lenticularis, lenticularis) /etc/lenticularis
# %%attr(660, lenticularis, lenticularis) /etc/lenticularis/lens3.conf
# %%attr(660, lenticularis, lenticularis) /etc/lenticularis/valkey.conf
%attr(440, -, -) /etc/sudoers.d/lenticularis-sudoers
%attr(660, -, -) /etc/httpd/conf.d/lens3proxy.conf
%license /usr/share/licenses/lenticularis/LICENSE
%dnl %config(noreplace) %{_sysconfdir}/logrotate.d/%{name}
# %%doc add-docs-here

%changelog
* Mon Mar 02 2026 zzmatu <zzmatu@users.noreply.github.com>
- RPM package provided.
