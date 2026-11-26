#!/bin/bash
set -xeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FIXTURE_DIR=$(cd "${SCRIPT_DIR}/../../docker/nextcloud" && pwd)
COMMAND=${1:?Usage: setup_nextcloud.sh <prepare|install|down> [RDM directory]}

case "$COMMAND" in
  prepare)
    RDM_DIR=${2:?RDM directory is required}
    mkdir -p "${FIXTURE_DIR}/.state"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3 \
      -keyout "${FIXTURE_DIR}/.state/server.key" \
      -out "${FIXTURE_DIR}/.state/server.crt" \
      -subj '/CN=192.168.168.167' \
      -addext 'subjectAltName=IP:192.168.168.167' \
      -addext 'basicConstraints=critical,CA:TRUE'
    cat > "${RDM_DIR}/addons/nextcloud/settings/local.py" <<SETTINGS
DEFAULT_HOSTS = ['${NEXTCLOUD_URL}']
USE_SSL = True
SETTINGS
    ;;
  install)
    RDM_DIR=${2:?RDM directory is required}
    docker compose -f "${FIXTURE_DIR}/compose.yaml" up -d
    for ((attempt=1; attempt<=30; attempt++)); do
      if curl --fail --cacert "${FIXTURE_DIR}/.state/server.crt" \
        "${NEXTCLOUD_URL}/status.php" -o "${FIXTURE_DIR}/.state/status.json" \
        && python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["installed"])' \
          "${FIXTURE_DIR}/.state/status.json"; then
        break
      fi
      if [[ "$attempt" == 30 ]]; then
        echo 'Nextcloud installation timed out' >&2
        exit 1
      fi
      sleep 10
    done
    curl --fail --cacert "${FIXTURE_DIR}/.state/server.crt" \
      --user "${NEXTCLOUD_USERNAME}:${NEXTCLOUD_PASSWORD}" -X MKCOL \
      "${NEXTCLOUD_URL}/remote.php/dav/files/${NEXTCLOUD_USERNAME}/e2e"
    cd "$RDM_DIR"
    for service in web api worker wb wb_worker; do
      container=$(docker-compose ps -q "$service")
      docker cp "${FIXTURE_DIR}/.state/server.crt" "${container}:/tmp/nextcloud-ca.crt"
      docker-compose exec -T "$service" python3 - <<'PY'
import ssl
from pathlib import Path
import certifi

certificate = Path('/tmp/nextcloud-ca.crt').read_bytes()
bundle = Path(certifi.where())
if certificate not in bundle.read_bytes():
    with bundle.open('ab') as stream:
        stream.write(b'\n' + certificate)
openssl_bundle = Path(ssl.get_default_verify_paths().openssl_cafile)
openssl_bundle.write_bytes(bundle.read_bytes())
PY
    done
    docker-compose restart web api worker wb wb_worker
    ;;
  down)
    docker compose -f "${FIXTURE_DIR}/compose.yaml" down -v
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    exit 1
    ;;
esac
