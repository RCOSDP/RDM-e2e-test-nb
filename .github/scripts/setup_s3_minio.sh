#!/bin/bash
set -euo pipefail

COMMAND=${1:?Usage: setup_s3_minio.sh <prepare|install> <RDM directory>}
RDM_ROOT=$(realpath "${2:?RDM directory is required}")
STATE_DIR="${RDM_ROOT}/.s3-minio"
DOMAINS=(s3.amazonaws.com s3.us-east-1.amazonaws.com s3-us-east-1.amazonaws.com)
HOSTS=("${DOMAINS[@]}")
for domain in "${DOMAINS[@]}"; do
    HOSTS+=("s3-e2e-a.${domain}" "s3-e2e-b.${domain}")
done

case "$COMMAND" in
  prepare)
    mkdir -p "$STATE_DIR"
    san=$(printf 'DNS:%s,' "${HOSTS[@]}")
    openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
        -keyout "${STATE_DIR}/server.key" -out "${STATE_DIR}/server.crt" \
        -subj '/CN=s3.amazonaws.com' \
        -addext "subjectAltName=${san%,}" \
        -addext 'basicConstraints=critical,CA:TRUE'

    cat > "${STATE_DIR}/nginx.conf" <<'NGINX'
events {}
http {
    map "$http_authorization $request_uri" $s3_signature {
        default none;
        ~AWS4-HMAC-SHA256 v4;
        ~AWSAccessKeyId= v2;
        ~^AWS\s v2;
    }
    log_format s3 '$request_method $host $uri $status signature=$s3_signature';
    access_log /dev/stdout s3;
    server {
        listen 443 ssl;
        ssl_certificate /certs/server.crt;
        ssl_certificate_key /certs/server.key;
        client_max_body_size 0;
        location / {
            proxy_pass http://minio:9000;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_http_version 1.1;
            proxy_request_buffering off;
            proxy_buffering off;
        }
    }
}
NGINX
    ;;
  install)
    cd "$RDM_ROOT"
    docker-compose up -d s3-minio-proxy
    printf '127.0.0.1 %s\n' "${HOSTS[*]}" | sudo tee -a /etc/hosts

    for service in web api worker wb wb_worker; do
        container=$(docker-compose ps -q "$service")
        docker cp "${STATE_DIR}/server.crt" "${container}:/usr/local/share/ca-certificates/s3-minio.crt"
        docker-compose exec -T "$service" update-ca-certificates
        docker-compose exec -T "$service" python3 - <<'PY'
from pathlib import Path
import certifi

certificate = Path('/usr/local/share/ca-certificates/s3-minio.crt').read_bytes()
with Path(certifi.where()).open('ab') as stream:
    stream.write(b'\n' + certificate)
PY
    done
    docker-compose restart web api worker wb wb_worker
    docker-compose exec -T wb python3 - <<'PY'
import asyncio
import aiohttp

async def check_tls():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://s3.amazonaws.com/minio/health/ready') as response:
            response.raise_for_status()

asyncio.get_event_loop().run_until_complete(check_tls())
PY
    sudo apt-get install -y libnss3-tools
    mkdir -p "$HOME/.pki/nssdb"
    if [[ ! -f "$HOME/.pki/nssdb/cert9.db" ]]; then
        certutil -N -d "sql:$HOME/.pki/nssdb" --empty-password
    fi
    certutil -A -d "sql:$HOME/.pki/nssdb" -n s3-minio-e2e -t 'C,,' \
        -i "${STATE_DIR}/server.crt"
    curl --fail --cacert "${STATE_DIR}/server.crt" \
        https://s3.amazonaws.com/minio/health/ready
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    exit 1
    ;;
esac
