#!/bin/bash
set -xeuo pipefail

# Usage:
#   ./setup_minio.sh apply <rdm_root_dir>
#
# Generates docker-compose override entries and s3compat settings
# required for MinIO usage within the E2E environment.

COMMAND=${1:-}
RDM_ROOT=${2:-}

if [[ -z "${COMMAND}" || -z "${RDM_ROOT}" ]]; then
  echo "Usage: $0 apply <rdm_root_dir>" >&2
  exit 1
fi

case "${COMMAND}" in
  apply)
    ;;
  *)
    echo "Unknown command: ${COMMAND}" >&2
    exit 1
    ;;
esac

if [[ ! -d "${RDM_ROOT}" ]]; then
  echo "RDM root directory not found: ${RDM_ROOT}" >&2
  exit 1
fi

MINIO_IMAGE_DEFAULT=${MINIO_IMAGE:-minio/minio:latest}
MINIO_MC_IMAGE_DEFAULT=${MINIO_MC_IMAGE:-minio/mc:latest}

MINIO_DOMAIN_SETTING=""
if [[ "${S3_MINIO_ENABLED:-false}" = "true" ]]; then
  MINIO_DOMAIN_SETTING="      MINIO_DOMAIN: s3.amazonaws.com,s3.us-east-1.amazonaws.com,s3-us-east-1.amazonaws.com"
fi

MINIO_DOCKER_SNIPPET=$(cat <<YAML
  minio:
    image: ${MINIO_IMAGE_DEFAULT}
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
${MINIO_DOMAIN_SETTING}
    command: server /data --console-address :9001
    expose:
      - "9000"
      - "9001"

  minio-mc:
    image: ${MINIO_MC_IMAGE_DEFAULT}
    entrypoint: ["mc"]
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minioadmin}
    depends_on:
      - minio
YAML
)

compose_override="${RDM_ROOT}/docker-compose.override.yml"

if ! grep -q '^services:' "${compose_override}"; then
  echo "services:" > "${compose_override}"
fi

if ! grep -q '^  minio:' "${compose_override}"; then
  printf '\n%s\n' "${MINIO_DOCKER_SNIPPET}" >> "${compose_override}"
fi

if [[ "${S3_MINIO_ENABLED:-false}" = "true" ]]; then
  if ! grep -q '^  s3-minio-proxy:' "${compose_override}"; then
    cat >> "${compose_override}" <<'YAML'

  s3-minio-proxy:
    image: nginx:alpine
    depends_on:
      - minio
    ports:
      - "127.0.0.1:443:443"
    volumes:
      - ./.s3-minio:/certs:ro
      - ./.s3-minio/nginx.conf:/etc/nginx/nginx.conf:ro
    networks:
      default:
        aliases:
          - s3.amazonaws.com
          - s3.us-east-1.amazonaws.com
          - s3-us-east-1.amazonaws.com
          - s3-e2e-a.s3.amazonaws.com
          - s3-e2e-b.s3.amazonaws.com
          - s3-e2e-a.s3.us-east-1.amazonaws.com
          - s3-e2e-b.s3.us-east-1.amazonaws.com
          - s3-e2e-a.s3-us-east-1.amazonaws.com
          - s3-e2e-b.s3-us-east-1.amazonaws.com
YAML
  fi

  # This fixture exercises signing and file operations without an external KMS.
  python - "${RDM_ROOT}/addons/s3/static/settings.json" <<'PY'
import json
import sys
from pathlib import Path

settings = Path(sys.argv[1])
data = json.loads(settings.read_text())
data['encryptUploads'] = False
settings.write_text(json.dumps(data, indent=4) + '\n')
PY
fi

settings_json="${RDM_ROOT}/addons/s3compat/static/settings.json"

if [[ ! -f "${settings_json}" ]]; then
  echo "s3compat settings.json not found: ${settings_json}" >&2
  exit 1
fi

tmp_json=$(mktemp)

python - "$settings_json" "$tmp_json" <<'PY'
import json
import sys

src, dst = sys.argv[1:3]
with open(src) as f:
    data = json.load(f)

service_name = "MinIO (CI)"
host = "minio:9000"

available_services = data.setdefault("availableServices", [])

if not any(s.get("name") == service_name for s in available_services):
    available_services.append({
        "name": service_name,
        "host": host,
        "bucketLocations": {
            "us-east-1": {
                "name": "us-east-1",
                "host": host,
            },
            "": {
                "name": "us-east-1",
            },
        },
        "serverSideEncryption": False,
    })

with open(dst, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
    f.write("\n")
PY

mv "${tmp_json}" "${settings_json}"

# Also register MinIO service for s3compatsigv4 addon if available
sigv4_settings_json="${RDM_ROOT}/addons/s3compatsigv4/static/settings.json"

if [[ -f "${sigv4_settings_json}" ]]; then
  tmp_json_sigv4=$(mktemp)

  python - "$sigv4_settings_json" "$tmp_json_sigv4" <<'PY'
import json
import sys

src, dst = sys.argv[1:3]
with open(src) as f:
    data = json.load(f)

service_name = "MinIO (CI)"
host = "minio:9000"

available_services = data.setdefault("availableServices", [])

if not any(s.get("name") == service_name for s in available_services):
    available_services.append({
        "name": service_name,
        "host": host,
        "bucketLocations": {
            "us-east-1": {
                "name": "us-east-1",
                "host": host,
            },
            "": {
                "name": "us-east-1",
            },
        },
        "serverSideEncryption": False,
    })

with open(dst, "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
    f.write("\n")
PY

  mv "${tmp_json_sigv4}" "${sigv4_settings_json}"
  echo "MinIO configuration applied for s3compatsigv4"
else
  echo "WARNING: s3compatsigv4 settings.json not found: ${sigv4_settings_json} (skipping)"
fi

echo "MinIO configuration applied"
