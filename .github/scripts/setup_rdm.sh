#!/bin/bash
set -xe

# RDM setup and Docker utility functions for e2e tests
# Note: These functions expect to be called from the appropriate working directory

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/wait_for_service.sh"

# Function to start docker services with health check
start_services() {
    local services="${SERVICES}"
    
    echo "Starting services: $services"
    docker-compose up -d $services
    
    # Basic wait for containers to initialize
    sleep 20
    
    # Show status
    docker-compose ps
}

# Function to check service logs for specific pattern
check_service_logs() {
    local service="${SERVICE}"
    local pattern="${PATTERN}"
    local timeout="${TIMEOUT:-600}"  # Default 10 minutes
    
    echo "Checking $service logs for pattern: $pattern"
    
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if docker-compose logs "$service" 2>&1 | grep -q "$pattern"; then
            echo "$service: Pattern found!"
            return 0
        fi
        sleep 10
        elapsed=$((elapsed + 10))
    done
    
    echo "$service: Pattern not found within timeout"
    return 1
}

# Function to test HTTP endpoint
test_endpoint() {
    local name="${ENDPOINT_NAME}"
    local url="${ENDPOINT_URL}"
    local expected_codes="${EXPECTED_CODES:-200,302}"  # Default acceptable codes
    
    echo "Testing $name..."
    local response=$(curl -s -o /dev/null -w "%{http_code}" --retry 5 --retry-delay 10 --retry-connrefused "$url" || echo "000")
    echo "$name response code: $response"
    
    # Check for errors
    if [[ "$response" == "400" || "$response" == "500" ]]; then
        echo "$name returned HTTP $response - failing" >&2
        return 1
    elif [[ "$response" == "000" ]]; then
        echo "$name connection failed - failing" >&2
        return 1
    fi
    
    # Check if response is in expected codes
    if echo "$expected_codes" | grep -q "$response"; then
        echo "$name is accessible"
        return 0
    else
        echo "$name not accessible (HTTP $response)" >&2
        return 2  # Non-fatal error
    fi
}

# Function to start RDM services
start_rdm_services() {
    local include_admin="${INCLUDE_ADMIN:-false}"
    
    # Define services based on admin flag (excluding assets which will be started separately)
    if [ "$include_admin" = "true" ]; then
        export SERVICES="mfr wb fakecas sharejs wb_worker worker web api ember_osf_web admin"
    else
        export SERVICES="mfr wb fakecas sharejs wb_worker worker web api ember_osf_web"
    fi

    SERVICES="kaken_elasticsearch $SERVICES"
    
    if [ "${MINIO_ENABLED:-false}" = "true" ]; then
        SERVICES="$SERVICES minio"
    fi

    echo "Starting services: $SERVICES"
    
    # Use start_services function
    start_services
    
    # Wait for ember build to complete
    echo "Waiting for Ember build to complete..."
    local timeout="${TIMEOUT:-600}"  # Default 10 minutes
    SERVICE="ember_osf_web" PATTERN="Build successful.*Serving on http://0.0.0.0:4200/" TIMEOUT="$timeout" check_service_logs
}

# Function to test RDM endpoints
test_rdm_endpoints() {
    local include_admin="${INCLUDE_ADMIN:-false}"

    # Test main endpoints
    ENDPOINT_NAME="OSF Web (port 5000)" ENDPOINT_URL="http://192.168.168.167:5000/" test_endpoint
    ENDPOINT_NAME="OSF API (port 8000)" ENDPOINT_URL="http://192.168.168.167:8000/v2/" test_endpoint
    ENDPOINT_NAME="Ember OSF Web (port 4200)" ENDPOINT_URL="http://localhost:4200/" test_endpoint
    ENDPOINT_NAME="WaterButler (port 7777)" ENDPOINT_URL="http://192.168.168.167:7777/status" test_endpoint
    ENDPOINT_NAME="MFR (port 7778)" ENDPOINT_URL="http://localhost:7778/status" test_endpoint
    ENDPOINT_NAME="FakeCAS (port 8080)" ENDPOINT_URL="http://localhost:8080/login" test_endpoint

    # Test admin endpoint if admin is enabled
    if [ "$include_admin" = "true" ]; then
        ENDPOINT_NAME="Admin Web (port 8001)" ENDPOINT_URL="http://localhost:8001/" test_endpoint
    fi
}

# Function to copy configuration files
setup_config_files() {
    local include_admin="${INCLUDE_ADMIN:-false}"  # Use environment variable or default
    
    echo "Setting up configuration files..."
    
    # Copy base configuration files
    cp ./website/settings/local-dist.py ./website/settings/local.py
    echo "" >> ./website/settings/local.py
    echo "from . import defaults" >> ./website/settings/local.py
    echo "import os" >> ./website/settings/local.py
    echo "import logging" >> ./website/settings/local.py
    echo "" >> ./website/settings/local.py
    echo "ENABLE_PRIVATE_SEARCH = True" >> ./website/settings/local.py
    echo "ENABLE_MULTILINGUAL_SEARCH = True" >> ./website/settings/local.py
    echo "SEARCH_ANALYZER = defaults.SEARCH_ANALYZER_JAPANESE" >> ./website/settings/local.py
    echo "LOG_LEVEL = logging.DEBUG" >> ./website/settings/local.py
    # Configure external access via 192.168.168.167
    echo "" >> ./website/settings/local.py
    echo "# External access configuration for CI environment" >> ./website/settings/local.py
    echo "DOMAIN = 'http://192.168.168.167:5000/'" >> ./website/settings/local.py
    echo "INTERNAL_DOMAIN = DOMAIN" >> ./website/settings/local.py
    echo "API_DOMAIN = 'http://192.168.168.167:8000/'" >> ./website/settings/local.py
    echo "WATERBUTLER_URL = 'http://192.168.168.167:7777'" >> ./website/settings/local.py
    echo "WATERBUTLER_INTERNAL_URL = WATERBUTLER_URL" >> ./website/settings/local.py
    echo "OSF_COOKIE_DOMAIN = '192.168.168.167'" >> ./website/settings/local.py

    cp ./api/base/settings/local-dist.py ./api/base/settings/local.py
    echo "" >> ./api/base/settings/local.py
    echo "# External access configuration for CI environment" >> ./api/base/settings/local.py
    echo "ALLOWED_HOSTS.append('192.168.168.167')" >> ./api/base/settings/local.py

    cp ./docker-compose-dist.override.yml ./docker-compose.override.yml
    cp ./tasks/local-dist.py ./tasks/local.py

    # Create admin settings if requested
    if [ "$include_admin" = "true" ]; then
        cp ./admin/base/settings/local-dist.py ./admin/base/settings/local.py
        echo "" >> ./admin/base/settings/local.py
        echo "# External access configuration for CI environment" >> ./admin/base/settings/local.py
        echo "ALLOWED_HOSTS = ['192.168.168.167', 'localhost']" >> ./admin/base/settings/local.py
        echo "SESSION_COOKIE_DOMAIN = '192.168.168.167'" >> ./admin/base/settings/local.py
        echo "Admin configuration files created"
    fi

    # Create binderhub settings
    cat > ./addons/binderhub/settings/local.py << 'BINDERHUB_EOF'
BINDERHUB_DEPLOYMENT_IMAGES = [
    {
        'url': 'yacchin1205/cs-binder-dockerfiles:python-test-lab-4.2.6',
        'name': 'Data Science Notebook (JupyterLab 4.2, TEST)',
        'description_ja': 'データサイエンス向けのパッケージを含むPython, R, Juliaの実行環境です(テスト)。  https://jupyter-docker-stacks.readthedocs.io/en/latest/using/selecting.html#jupyter-datascience-notebook',
        'description_en': 'A Python, R, and Julia environment with popular packages for data analysis. https://jupyter-docker-stacks.readthedocs.io/en/latest/using/selecting.html#jupyter-datascience-notebook',
        'packages': ['conda', 'pip', 'rcran', 'rgithub'],
    },
    {
        'url': '#repo2docker#python=3.12.*,r-base=4.4.*',
        'name': 'Python 3.12 + R 4.4 (JupyterLab 4.x)',
        'description_ja': 'Jupyter Notebook, JupyterLab, RStudio, Shinyが使えます。',
        'description_en': 'Jupyter Notebook, JupyterLab, RStudio, and Shiny are available.',
        'packages': ['conda', 'pip', 'rmran', 'mpm'],
        'recommended': True,
    },
    {
        'url': 'gcr.io/nii-ap-ops/base/datascience-notebook:main-lab4.x',
        'name': 'Data Science Notebook (JupyterLab 4.x)',
        'description_ja': 'データサイエンス向けのパッケージを含むPython, R, Juliaの実行環境です。  https://jupyter-docker-stacks.readthedocs.io/en/latest/using/selecting.html#jupyter-datascience-notebook',
        'description_en': 'A Python, R, and Julia environment with popular packages for data analysis. https://jupyter-docker-stacks.readthedocs.io/en/latest/using/selecting.html#jupyter-datascience-notebook',
        'packages': ['conda', 'pip', 'rcran', 'rgithub'],
    },
    {
        'url': 'gcr.io/nii-ap-ops/base/matlab-notebook:r2023b',
        'name': 'MATLAB (R2023b)',
        'description_ja': 'MATLABがインストールされたJupyterLab実行環境です。  https://github.com/mathworks-ref-arch/matlab-integration-for-jupyter/tree/main/matlab',
        'description_en': 'JupyterLab runtime environment with MATLAB installed.  https://github.com/mathworks-ref-arch/matlab-integration-for-jupyter/tree/main/matlab',
        'packages': ['conda', 'pip'],
    },
    {
        'url': '#repo2docker#python=3.12.*,r-base=4.3.*',
        'name': 'Python 3.12 + R 4.3 (JupyterLab 4.x, deprecated)',
        'description_ja': 'Jupyter Notebook, JupyterLab, RStudio, Shinyが使えます。',
        'description_en': 'Jupyter Notebook, JupyterLab, RStudio, and Shiny are available.',
        'packages': ['conda', 'pip', 'rmran', 'mpm'],
    },
    {
        'url': '#repo2docker#python=3.9.*,r-base=4.1.3',
        'name': 'Python 3.9 + R 4.1.3 (JupyterLab 3.x, deprecated)',
        'description_ja': 'Jupyter Notebook, JupyterLab, RStudio, Shinyが使えます。',
        'description_en': 'Jupyter Notebook, JupyterLab, RStudio, and Shiny are available.',
        'packages': ['conda', 'pip', 'rmran'],
    },
    {
        'url': 'gcr.io/nii-ap-ops/base/datascience-notebook:main',
        'name': 'Data Science Notebook (JupyterLab 3.6, deprecated)',
        'description_ja': 'データサイエンス向けのパッケージを含むPython, R, Juliaの実行環境です。  https://jupyter-docker-stacks.readthedocs.io/en/latest/using/selecting.html#jupyter-datascience-notebook',
        'description_en': 'A Python, R, and Julia environment with popular packages for data analysis. https://jupyter-docker-stacks.readthedocs.io/en/latest/using/selecting.html#jupyter-datascience-notebook',
        'packages': ['conda', 'pip', 'rcran', 'rgithub'],
    },
]
BINDERHUB_EOF
    echo "BinderHub configuration files created"

    echo "Configuration files setup completed"
}

# Function to create docker-compose override with NII Cloud Operation images
create_docker_override() {
    # Use environment variables for images
    local osf_image="${OSF_IMAGE:-niicloudoperation/rdm-osf.io:latest}"
    local ember_image="${EMBER_IMAGE:-niicloudoperation/rdm-ember-osf-web:latest}"
    local cas_image="${CAS_IMAGE:-niicloudoperation/rdm-cas-overlay:latest}"
    local mfr_image="${MFR_IMAGE:-niicloudoperation/rdm-modular-file-renderer:latest}"
    local wb_image="${WB_IMAGE:-niicloudoperation/rdm-waterbutler:latest}"
    local elasticsearch_image="${ELASTICSEARCH_IMAGE:-elasticsearch:2}"
    local y_websocket_url="${Y_WEBSOCKET_URL:-}"

    echo "Creating docker-compose override with:"
    echo "  OSF: $osf_image"
    echo "  Ember: $ember_image"
    echo "  CAS: $cas_image"
    echo "  MFR: $mfr_image"
    echo "  WaterButler: $wb_image"
    echo "  Elasticsearch: $elasticsearch_image"
    if [ -n "$y_websocket_url" ]; then
        echo "  Y-WebSocket: $y_websocket_url"
    fi

    cat > docker-compose.override.yml << EOL
# NII Cloud Operation images override
services:
  fakecas:
    image: niicloudoperation/rdm-fakecas:latest
    command: fakecas -host=0.0.0.0:8080 -osfhost=192.168.168.167:5000 -dbaddress=postgres://postgres@postgres:5432/osf?sslmode=disable
  admin:
    image: ${osf_image}
    environment:
      AWS_EC2_METADATA_DISABLED: "true"
      KAKEN_ELASTIC_URI: http://kaken_elasticsearch:9200
  admin_assets:
    image: ${osf_image}
  api:
    image: ${osf_image}
    environment:
      KAKEN_ELASTIC_URI: http://kaken_elasticsearch:9200
  assets:
    image: ${osf_image}
  requirements:
    image: ${osf_image}
    command:
      - /bin/bash
      - -c
      - apk add --no-cache --virtual .build-deps build-base linux-headers python3-dev musl-dev libxml2-dev libxslt-dev postgresql-dev libffi-dev libpng-dev freetype-dev jpeg-dev &&
        invoke requirements --all &&
        (python3 -m compileall /usr/lib/python3.6 || true) &&
        rm -Rf /python3.6/* &&
        cp -Rf -p /usr/lib/python3.6 /
  web:
    image: ${osf_image}
    environment:
      OAUTHLIB_INSECURE_TRANSPORT: '1'
      KAKEN_ELASTIC_URI: http://kaken_elasticsearch:9200
      Y_WEBSOCKET_URL: '${y_websocket_url}'
  worker:
    image: ${osf_image}
    environment:
      KAKEN_ELASTIC_URI: http://kaken_elasticsearch:9200
  ember_osf_web:
    image: ${ember_image}
    environment:
      OSF_URL: http://192.168.168.167:5000/
      OSF_API_URL: http://192.168.168.167:8000
      OSF_FILE_URL: http://192.168.168.167:7777/
  cas:
    image: ${cas_image}
  mfr:
    image: ${mfr_image}
  mfr_requirements:
    image: ${mfr_image}
  wb:
    image: ${wb_image}
  wb_worker:
    image: ${wb_image}
  wb_requirements:
    image: ${wb_image}
  kaken_elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.14.3
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "19200:9200"
  elasticsearch:
    image: ${elasticsearch_image}
EOL

    echo "Docker compose override created"

    # Replace localhost with 192.168.168.167 in all .docker-compose*.env files for external access
    for envfile in .docker-compose*.env; do
        if [ -f "$envfile" ]; then
            sed -i.bak \
                -e 's|localhost:5000|192.168.168.167:5000|g' \
                -e 's|localhost:8000|192.168.168.167:8000|g' \
                -e 's|localhost:7777|192.168.168.167:7777|g' \
                -e 's|localhost:7778|192.168.168.167:7778|g' \
                -e 's|localhost:8001|192.168.168.167:8001|g' \
                "$envfile"
            rm -f "${envfile}.bak"
            echo "Updated $envfile for external access:"
            cat "$envfile"
        fi
    done

    # Add WaterButler DOMAIN for external access
    echo "" >> .docker-compose.wb.env
    echo "SERVER_CONFIG_DOMAIN=http://192.168.168.167:7777" >> .docker-compose.wb.env

    if [ "${MINIO_ENABLED:-false}" = "true" ]; then
        local script_dir
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        bash "${script_dir}/setup_minio.sh" apply "${PWD}"
    fi

    if [ "${WEKO_ENABLED:-false}" = "true" ]; then
        local script_dir
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        python3 "${script_dir}/weko_setup_cert.py" \
            "${PWD}/docker-compose.override.yml" \
            "${script_dir}/../../../weko/nginx/keys/server.crt"
    fi
}

# Function to run Django migrations
run_migrations() {
    echo "Running Django migrations..."
    echo "Ensuring Elasticsearch is ready..."
    docker-compose up -d elasticsearch
    SERVICE_NAME="Elasticsearch" \
    CHECK_COMMAND="curl -f \"http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=120s\"" \
    TIMEOUT=240 wait_for_service
    docker-compose up -d kaken_elasticsearch
    SERVICE_NAME="KAKEN Elasticsearch" \
    CHECK_COMMAND="curl -f \"http://localhost:19200/_cluster/health?wait_for_status=yellow&timeout=120s\"" \
    TIMEOUT=240 wait_for_service
    docker-compose run --rm web python3 manage.py migrate
    echo "Running search migrations..."
    docker-compose run --rm web invoke migrate_search
    echo "Migrations completed"
}

# Function to enable feature flags
enable_feature_flags() {
    local flags="${FEATURE_FLAGS:-}"  # Use environment variable
    
    if [ -z "$flags" ]; then
        echo "No feature flags to enable"
        return 0
    fi
    
    for flag in $flags; do
        echo "Enabling feature flag: $flag"
        docker-compose run --rm web python3 manage.py waffle_flag "$flag" --everyone
    done
    
    echo "Feature flags enabled"
}

# Function to compile translations
compile_translations() {
    local include_admin="${INCLUDE_ADMIN:-false}"
    
    echo "Compiling translation files..."
    docker-compose run --rm web pybabel compile -d ./website/translations
    
    if [ "$include_admin" = "true" ]; then
        echo "Compiling admin translation files..."
        docker-compose run --rm web pybabel compile -D django -d ./admin/translations
    fi
    
    echo "Translation compilation completed"
}

# Function to start asset services after translations are compiled
start_asset_services() {
    local include_admin="${INCLUDE_ADMIN:-false}"
    
    # Start asset services
    export SERVICES="assets"
    echo "Starting asset services: $SERVICES"
    start_services
    
    if [ "$include_admin" = "true" ]; then
        # Start admin_assets separately to avoid volume conflicts
        export SERVICES="admin_assets"
        echo "Starting admin asset services: $SERVICES"
        start_services
    fi
}

# Function to install requirements
install_requirements() {
    echo "Installing requirements..."
    docker-compose run --rm requirements
    docker-compose run --rm mfr_requirements
    docker-compose run --rm wb_requirements
    echo "Requirements installation completed"
}

# Main execution if called directly with arguments
if [ $# -gt 0 ]; then
    command="$1"
    shift
    
    case "$command" in
        setup_config_files)
            setup_config_files "$@"
            ;;
        create_docker_override)
            create_docker_override "$@"
            ;;
        install_requirements)
            install_requirements "$@"
            ;;
        run_migrations)
            run_migrations "$@"
            ;;
        enable_feature_flags)
            enable_feature_flags "$@"
            ;;
        compile_translations)
            compile_translations "$@"
            ;;
        start_asset_services)
            start_asset_services "$@"
            ;;
        start_rdm_services)
            start_rdm_services "$@"
            ;;
        test_rdm_endpoints)
            test_rdm_endpoints "$@"
            ;;
        wait_for_service)
            wait_for_service
            ;;
        start_services)
            start_services
            ;;
        check_service_logs)
            check_service_logs
            ;;
        test_endpoint)
            test_endpoint
            ;;
        *)
            echo "Unknown command: $command"
            exit 1
            ;;
    esac
fi
