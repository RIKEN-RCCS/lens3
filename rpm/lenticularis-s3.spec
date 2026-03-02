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
Requires:       valkey
Requires:       mosquitto

%description
RPM of Lenticularis-S3.

# %%autosetup -T

%install
cp -rp * %{buildroot}

%files
/usr/local/bin/lenticularis-mux
/usr/local/bin/lens3-admin
/usr/lib/sysusers.d/lenticularis.conf
# /usr/share/licenses/lenticularis/LICENSE

%license /usr/share/licenses/lenticularis/LICENSE
# %%doc add-docs-here

%changelog
* Mon Mar 02 2026 zzmatu <zzmatu@users.noreply.github.com>
-
