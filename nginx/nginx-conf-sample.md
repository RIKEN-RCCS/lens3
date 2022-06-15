# nginx-conf-sample.md

```
server {
    listen 443 ssl;
    listen [::]:443 ssl;

# Declare hostname(s) (using a wildcard).  Hostnames may match the
# webui server_name declared in another section.  Note Nginx prefers
# an exact match to a wildcard.

    server_name lens3.example.com *.lens3.example.com;

    client_max_body_size 0;
    proxy_buffering off;
    proxy_request_buffering off;
    ignore_invalid_headers off;

# Designate a wildcard certificate.

    ssl_certificate_key "/etc/nginx/server_certificates/server.key";
    ssl_certificate "/etc/nginx/server_certificates/server.crt";
    ssl_protocols TLSv1.1 TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host:$server_port;
        proxy_set_header X-Forwarded-Server $host;
        proxy_set_header Host $http_host;

        proxy_connect_timeout 300;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        chunked_transfer_encoding off;

# Transfer connections to the backend.
        proxy_pass http://mux;
    }
}

upstream mux {

# A reverse-proxy can choose backends like a load balancer.  There are
# three choices:
# - (empty) => randomly
# - least_conn => to minimize connections
# - ip_hash => by a hash

    # least_conn;
    server localhost:8000;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;

    index index.html;

# Hostname of WebUI.

    server_name api.lens3.example.com;

# Designate a wildcard certificate.

    ssl_certificate_key "/etc/nginx/server_certificates/server.key";
    ssl_certificate "/etc/nginx/server_certificates/server.crt";
    ssl_protocols TLSv1.1 TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    satisfy all;
    auth_basic "Controlled Area";
    auth_basic_user_file /etc/nginx/htpasswd;

    location / {
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host:$server_port;
        proxy_set_header X-Remote-User $remote_user;
        proxy_set_header Host $http_host;

        proxy_pass http://api;
    }
}

upstream api {
    # least_conn;
    server localhost:8001;
}
```
