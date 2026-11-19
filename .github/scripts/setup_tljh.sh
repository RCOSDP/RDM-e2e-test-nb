#!/bin/bash
set -xeuo pipefail

COMMAND=${1:-}

if [[ -z "${COMMAND}" ]]; then
  echo "Usage: $0 <install|down>" >&2
  exit 1
fi

wait_for_url() {
  local url="$1"
  local attempts=30
  local delay=10
  for ((i=1; i<=attempts; i++)); do
    if curl -k --fail "$url"; then
      echo "${url} is reachable"
      return 0
    fi
    echo "Attempt ${i}/${attempts} failed for ${url}" >&2
    sleep "$delay"
  done
  echo "Timed out waiting for ${url}" >&2
  return 1
}

case "$COMMAND" in
  install)
    # Install Node.js
    sudo apt-get update
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
    sudo chmod a+r /etc/apt/keyrings/nodesource.gpg

    NODE_MAJOR=22
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | \
      sudo tee /etc/apt/sources.list.d/nodesource.list
    sudo apt-get update
    sudo apt-get install -y nodejs
    sudo npm install -g yarn

    sudo modprobe fuse

    # Pull the repo2docker image
    sudo docker pull "${REPO2DOCKER_IMAGE}"
    sudo docker pull "${RDMFS_IMAGE}"

    # Install TLJH
    curl -L https://tljh.jupyter.org/bootstrap.py \
      | sudo python3 - \
        --version "${TLJH_VERSION}" \
        --admin admin:change-your-password \
        --plugin "git+https://github.com/${TLJH_PLUGIN%%@*}.git@${TLJH_PLUGIN#*@}"

    # Configure the plugin
    cat <<'EOF' | sudo tee /opt/tljh/config/jupyterhub_config.d/repo2docker.py
from tljh_repo2docker import TLJH_R2D_ADMIN_SCOPE
import sys


c.JupyterHub.allow_named_servers = True

c.JupyterHub.services.extend(
    [
        {
            "name": "tljh_repo2docker",
            "url": "http://127.0.0.1:6789",
            "command": [
                "env",
                'REPO2DOCKER_RDM_PROVIDER_HOSTS=[{"hostname":["http://192.168.168.167:5000"],"api":"http://192.168.168.167:8000/v2/"}]',
                sys.executable,
                "-m",
                "tljh_repo2docker",
                "--ip",
                "127.0.0.1",
                "--port",
                "6789"
            ],
            "oauth_no_confirm": True,
            "oauth_client_allowed_scopes": [
                TLJH_R2D_ADMIN_SCOPE,
            ],
        }
    ]
)

c.JupyterHub.custom_scopes = {
    TLJH_R2D_ADMIN_SCOPE: {
        "description": "Admin access to tljh_repo2docker",
    },
}

c.JupyterHub.load_roles = [
    {
        "description": "Role for tljh_repo2docker service",
        "name": "tljh-repo2docker-service",
        "scopes": [
            "read:users",
            "read:roles:users",
            "admin:servers",
            "access:services!service=binder",
        ],
        "services": ["tljh_repo2docker"],
    },
    {
        "name": "user",
        "scopes": [
            "self",
            "access:services!service=tljh_repo2docker",
        ],
    },
    {
        "name": 'tljh-repo2docker-service-admin',
        "groups": ["repo2docker"],
        "scopes": [TLJH_R2D_ADMIN_SCOPE],
    },
]

c.JupyterHub.tornado_settings = {
    "slow_spawn_timeout": 30
}
EOF

    sudo systemctl restart jupyterhub
    wait_for_url "http://localhost"
    ;;
  down)
    sudo systemctl stop jupyterhub || true
    ;;
  *)
    echo "Unknown command: ${COMMAND}" >&2
    exit 1
    ;;
esac
