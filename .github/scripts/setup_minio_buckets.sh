#!/bin/bash
set -xeuo pipefail

# Usage:
#   ./setup_minio_buckets.sh <rdm_root_dir> <alias> <endpoint> <root_user> <root_password> \
#     <access_key_1> <secret_key_1> <bucket_name_1> <access_key_2> <secret_key_2> <bucket_name_2>

if [[ $# -ne 11 ]]; then
  cat >&2 <<'EOF'
Usage: setup_minio_buckets.sh <rdm_root_dir> <alias> <endpoint> <root_user> <root_password> \
  <access_key_1> <secret_key_1> <bucket_name_1> <access_key_2> <secret_key_2> <bucket_name_2>
EOF
  exit 1
fi

RDM_ROOT=$1
ALIAS=$2
ENDPOINT=$3
ROOT_USER=$4
ROOT_PASSWORD=$5
ACCESS_KEY_1=$6
SECRET_KEY_1=$7
BUCKET_NAME_1=$8
ACCESS_KEY_2=$9
SECRET_KEY_2=${10}
BUCKET_NAME_2=${11}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MINIO_VERIFY_LARGE_UPLOAD=${MINIO_VERIFY_LARGE_UPLOAD:-false}
MINIO_VERIFY_LARGE_UPLOAD_SIZE_MB=${MINIO_VERIFY_LARGE_UPLOAD_SIZE_MB:-130}
MINIO_VERIFY_LARGE_UPLOAD_KEY=${MINIO_VERIFY_LARGE_UPLOAD_KEY:-diagnostics/minio-large-upload.bin}

if [[ ! -d "${RDM_ROOT}" ]]; then
  echo "RDM root directory not found: ${RDM_ROOT}" >&2
  exit 1
fi

pushd "${RDM_ROOT}" >/dev/null
source "${SCRIPT_DIR}/lib/wait_for_service.sh"

SERVICE_NAME="MinIO"
CHECK_COMMAND="docker-compose exec -T minio /bin/sh -c 'curl -fs http://localhost:9000/minio/health/ready'"
TIMEOUT=180
INTERVAL=5
wait_for_service

docker-compose run --rm --entrypoint /bin/sh minio-mc <<EOF
set -xeu
mc alias set "${ALIAS}" "${ENDPOINT}" "${ROOT_USER}" "${ROOT_PASSWORD}"
mc rb "${ALIAS}/${BUCKET_NAME_1}" --force || true
mc rb "${ALIAS}/${BUCKET_NAME_2}" --force || true
mc mb "${ALIAS}/${BUCKET_NAME_1}"
mc mb "${ALIAS}/${BUCKET_NAME_2}"

if [ "${S3_MINIO_ENABLED:-false}" = "true" ] && [ "${S3_MINIO_INST_ENABLED:-false}" != "true" ]; then
  mc version enable "${ALIAS}/${BUCKET_NAME_2}"
  mkdir /tmp/s3-pagination
  for number in \$(seq 1 1500); do
    touch "/tmp/s3-pagination/\$(printf '%04d' "\$number")"
  done
  mc cp --recursive /tmp/s3-pagination/ "${ALIAS}/${BUCKET_NAME_2}/"
fi
mc admin user remove "${ALIAS}" "${ACCESS_KEY_1}" || true
mc admin user remove "${ALIAS}" "${ACCESS_KEY_2}" || true
mc admin user add "${ALIAS}" "${ACCESS_KEY_1}" "${SECRET_KEY_1}"
mc admin policy attach "${ALIAS}" readwrite --user "${ACCESS_KEY_1}"
mc admin user add "${ALIAS}" "${ACCESS_KEY_2}" "${SECRET_KEY_2}"
mc admin policy attach "${ALIAS}" readwrite --user "${ACCESS_KEY_2}"

if [ "${MINIO_VERIFY_LARGE_UPLOAD}" = "true" ]; then
  echo "[diagnostic] Uploading ${MINIO_VERIFY_LARGE_UPLOAD_SIZE_MB}MiB test object to ${ALIAS}/${BUCKET_NAME_1}/${MINIO_VERIFY_LARGE_UPLOAD_KEY}" >&2
  dd if=/dev/zero of=/tmp/minio-large-upload-test.bin bs=1M count=${MINIO_VERIFY_LARGE_UPLOAD_SIZE_MB}
  mc cp /tmp/minio-large-upload-test.bin "${ALIAS}/${BUCKET_NAME_1}/${MINIO_VERIFY_LARGE_UPLOAD_KEY}"
  mc stat "${ALIAS}/${BUCKET_NAME_1}/${MINIO_VERIFY_LARGE_UPLOAD_KEY}"
  rm -f /tmp/minio-large-upload-test.bin
fi
EOF

popd >/dev/null

echo "MinIO buckets and users have been initialized"
