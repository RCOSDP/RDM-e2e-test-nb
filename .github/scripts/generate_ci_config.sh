#!/bin/bash
set -xeuo pipefail

if [[ $# -lt 2 ]]; then
  cat >&2 <<'USAGE'
Usage: generate_ci_config.sh <output_path> <base_config_yaml> [--minio] [--aws-s3] [--jupyterhub] [--weko] [--flowable] [--s3compatsigv4] [--s3compatsigv4-inst] [--wiki]
USAGE
  exit 1
fi

OUTPUT=$1
BASE_CONFIG=$2
shift 2
MINIO=false
AWS_S3=false
JUPYTERHUB=false
WEKO=false
FLOWABLE=false
S3COMPATSIGV4=false
S3COMPATSIGV4_INST=false
WIKI=false

for arg in "$@"; do
  case "$arg" in
    --minio)
      MINIO=true
      ;;
    --aws-s3)
      AWS_S3=true
      ;;
    --jupyterhub)
      JUPYTERHUB=true
      ;;
    --weko)
      WEKO=true
      ;;
    --flowable)
      FLOWABLE=true
      ;;
    --s3compatsigv4)
      S3COMPATSIGV4=true
      ;;
    --s3compatsigv4-inst)
      S3COMPATSIGV4_INST=true
      ;;
    --wiki)
      WIKI=true
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 1
      ;;
  esac

done

if [[ "${MINIO}" == "true" && "${AWS_S3}" == "true" ]]; then
  echo "--minio and --aws-s3 both write storages_s3 and cannot be used together" >&2
  exit 1
fi

cp "${BASE_CONFIG}" "${OUTPUT}"

if [[ "${MINIO}" == "true" ]]; then
  if [[ -z "${S3COMPAT_ACCESS_KEY_1:-}" || -z "${S3COMPAT_SECRET_KEY_1:-}" ]]; then
    echo "S3 compat credentials are not set" >&2
    exit 1
  fi

  cat >> "${OUTPUT}" <<EOF

storages_s3:
  - id: 's3compat'
    name: 'S3 Compatible Storage'
    skip_too_many_files_check: true

s3compat_access_key_1: '${S3COMPAT_ACCESS_KEY_1}'
s3compat_secret_access_key_1: '${S3COMPAT_SECRET_KEY_1}'
s3compat_default_region_1: '${S3COMPAT_REGION}'
s3compat_test_bucket_name_1: '${S3COMPAT_BUCKET_NAME_1}'

s3compat_access_key_2: '${S3COMPAT_ACCESS_KEY_2}'
s3compat_secret_access_key_2: '${S3COMPAT_SECRET_KEY_2}'
s3compat_default_region_2: '${S3COMPAT_REGION}'
s3compat_test_bucket_name_2: '${S3COMPAT_BUCKET_NAME_2}'

s3compat_type_name_1: '${S3COMPAT_SERVICE_NAME}'
s3compat_type_name_2: '${S3COMPAT_SERVICE_NAME}'
EOF
elif [[ "${AWS_S3}" != "true" ]]; then
  cat >> "${OUTPUT}" <<'EOF'

storages_s3: []
EOF
fi

if [[ "${AWS_S3}" == "true" ]]; then
  required_aws_s3_vars=(
    AWS_S3_ACCESS_KEY_1
    AWS_S3_SECRET_KEY_1
    AWS_S3_ACCESS_KEY_2
    AWS_S3_SECRET_KEY_2
    AWS_S3_LEGACY_REGION
    AWS_S3_LEGACY_BUCKET_NAME
    AWS_S3_V4_REGION
    AWS_S3_V4_BUCKET_NAME
  )

  missing_aws_s3_vars=()
  for var_name in "${required_aws_s3_vars[@]}"; do
    if [[ -z "${!var_name:-}" ]]; then
      missing_aws_s3_vars+=("${var_name}")
    fi
  done

  if [[ ${#missing_aws_s3_vars[@]} -gt 0 ]]; then
    echo "AWS S3 test credentials are not set: ${missing_aws_s3_vars[*]}" >&2
    exit 1
  fi

  if [[ "${AWS_S3_ACCESS_KEY_1}" == "${AWS_S3_ACCESS_KEY_2}" ]]; then
    echo "AWS_S3_ACCESS_KEY_1 and AWS_S3_ACCESS_KEY_2 must be different" >&2
    exit 1
  fi

  if [[ "${AWS_S3_SECRET_KEY_1}" == "${AWS_S3_SECRET_KEY_2}" ]]; then
    echo "AWS_S3_SECRET_KEY_1 and AWS_S3_SECRET_KEY_2 must be different" >&2
    exit 1
  fi

  cat >> "${OUTPUT}" <<EOF

storages_s3:
  - id: 's3'
    name: 'Amazon S3'
    skip_too_many_files_check: true

s3_access_key_1: '${AWS_S3_ACCESS_KEY_1}'
s3_secret_access_key_1: '${AWS_S3_SECRET_KEY_1}'
s3_default_region_1: '${AWS_S3_LEGACY_REGION}'
s3_test_bucket_name_1: '${AWS_S3_LEGACY_BUCKET_NAME}'

s3_access_key_2: '${AWS_S3_ACCESS_KEY_2}'
s3_secret_access_key_2: '${AWS_S3_SECRET_KEY_2}'
s3_default_region_2: '${AWS_S3_V4_REGION}'
s3_test_bucket_name_2: '${AWS_S3_V4_BUCKET_NAME}'
EOF
fi

if [[ "${JUPYTERHUB}" == "true" ]]; then
  if [[ -z "${TLJH_URL:-}" || -z "${TLJH_USERNAME:-}" || -z "${TLJH_PASSWORD:-}" ]]; then
    echo "TLJH connection information is not set" >&2
    exit 1
  fi

  cat >> "${OUTPUT}" <<EOF

jupyterhub_enabled: true
tljh_url: '${TLJH_URL}'
tljh_username: '${TLJH_USERNAME}'
tljh_password: '${TLJH_PASSWORD}'
EOF
else
  cat >> "${OUTPUT}" <<'EOF'

jupyterhub_enabled: false
EOF
fi

if [[ "${WEKO}" == "true" ]]; then
  WEKO_URL_VALUE=${WEKO_URL:-http://localhost}
  WEKO_ADMIN_EMAIL_VALUE=${WEKO_ADMIN_EMAIL:-}
  WEKO_ADMIN_PASSWORD_VALUE=${WEKO_ADMIN_PASSWORD:-}
  WEKO_USER_EMAIL_VALUE=${WEKO_USER_EMAIL:-}
  WEKO_USER_PASSWORD_VALUE=${WEKO_USER_PASSWORD:-}
  WEKO_INSTITUTION_NAME_VALUE=${WEKO_INSTITUTION_NAME:-}
  WEKO_INDEX_NAME_VALUE=${WEKO_INDEX_NAME:-'Sample Index'}
  WEKO_DOCKER_COMPOSE_PATH_VALUE=${WEKO_DOCKER_COMPOSE_PATH:-}
  SWORD_MAPPING_ID_VALUE=${SWORD_MAPPING_ID:-30002}
  WEKO_TEST_MODE_VALUE=${WEKO_TEST_MODE:-direct}
  IGNORE_HTTPS_ERRORS_VALUE=${IGNORE_HTTPS_ERRORS:-false}

  cat >> "${OUTPUT}" <<EOF

# WEKO / JAIRO Cloud settings
weko_url: '${WEKO_URL_VALUE}'
weko_admin_email: '${WEKO_ADMIN_EMAIL_VALUE}'
weko_admin_password: '${WEKO_ADMIN_PASSWORD_VALUE}'
weko_user_email: '${WEKO_USER_EMAIL_VALUE}'
weko_user_password: '${WEKO_USER_PASSWORD_VALUE}'
weko_institution_name: '${WEKO_INSTITUTION_NAME_VALUE}'
weko_index_name: '${WEKO_INDEX_NAME_VALUE}'
weko_docker_compose_path: '${WEKO_DOCKER_COMPOSE_PATH_VALUE}'
sword_mapping_id: ${SWORD_MAPPING_ID_VALUE}
weko_test_mode: '${WEKO_TEST_MODE_VALUE}'
ignore_https_errors: ${IGNORE_HTTPS_ERRORS_VALUE}
EOF
fi

if [[ "${FLOWABLE}" == "true" ]]; then
  GATEWAY_BASE_URL_VALUE=${GATEWAY_BASE_URL:-http://192.168.168.167:8088/}
  WORKFLOW_BATCH_PROJECT_COUNT_VALUE=${WORKFLOW_BATCH_PROJECT_COUNT:-50}
  if [[ -z "${WORKFLOW_TEST_MODE:-}" ]]; then
    echo "Error: WORKFLOW_TEST_MODE must be set when --flowable is enabled (one of: roles, forms, batch)" >&2
    exit 1
  fi

  cat >> "${OUTPUT}" <<EOF

# Flowable Workflow settings
workflow_enabled: true
gateway_base_url: '${GATEWAY_BASE_URL_VALUE}'
workflow_batch_project_count: ${WORKFLOW_BATCH_PROJECT_COUNT_VALUE}
workflow_test_mode: '${WORKFLOW_TEST_MODE}'
EOF
else
  cat >> "${OUTPUT}" <<'EOF'

workflow_enabled: false
EOF
fi

if [[ "${S3COMPATSIGV4}" == "true" ]]; then
  if [[ -z "${S3COMPATSIGV4_ACCESS_KEY_1:-}" || -z "${S3COMPATSIGV4_SECRET_KEY_1:-}" ]]; then
    echo "S3 compat sigv4 credentials are not set" >&2
    exit 1
  fi

  cat >> "${OUTPUT}" <<EOF

s3compatsigv4_enabled: true

s3compatsigv4_access_key_1: '${S3COMPATSIGV4_ACCESS_KEY_1}'
s3compatsigv4_secret_access_key_1: '${S3COMPATSIGV4_SECRET_KEY_1}'
s3compatsigv4_endpoint_1: '${S3COMPATSIGV4_ENDPOINT}'
s3compatsigv4_test_bucket_name_1: '${S3COMPATSIGV4_BUCKET_NAME_1}'

s3compatsigv4_access_key_2: '${S3COMPATSIGV4_ACCESS_KEY_2}'
s3compatsigv4_secret_access_key_2: '${S3COMPATSIGV4_SECRET_KEY_2}'
s3compatsigv4_endpoint_2: '${S3COMPATSIGV4_ENDPOINT}'
s3compatsigv4_test_bucket_name_2: '${S3COMPATSIGV4_BUCKET_NAME_2}'

s3compatsigv4_type_name_1: '${S3COMPATSIGV4_SERVICE_NAME}'
s3compatsigv4_type_name_2: '${S3COMPATSIGV4_SERVICE_NAME}'
EOF
fi

if [[ "${S3COMPATSIGV4_INST}" == "true" ]]; then
  if [[ -z "${S3COMPATSIGV4_INST_ACCESS_KEY:-}" || -z "${S3COMPATSIGV4_INST_SECRET_KEY:-}" ]]; then
    echo "S3 compat sigv4 institutional storage credentials are not set" >&2
    exit 1
  fi

  cat >> "${OUTPUT}" <<EOF

s3compatsigv4_institutional_storage_enabled: true
s3compatsigv4_inst_endpoint_url: '${S3COMPATSIGV4_INST_ENDPOINT}'
s3compatsigv4_inst_access_key: '${S3COMPATSIGV4_INST_ACCESS_KEY}'
s3compatsigv4_inst_secret_key: '${S3COMPATSIGV4_INST_SECRET_KEY}'
s3compatsigv4_inst_bucket: '${S3COMPATSIGV4_INST_BUCKET}'
EOF
fi

if [[ "${WIKI}" == "true" ]]; then
  cat >> "${OUTPUT}" <<'EOF'

wiki_enabled: true
EOF
else
  cat >> "${OUTPUT}" <<'EOF'

wiki_enabled: false
EOF
fi

cat "${OUTPUT}"
