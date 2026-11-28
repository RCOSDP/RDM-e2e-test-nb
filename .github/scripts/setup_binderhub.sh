#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_ROOT="${SCRIPT_DIR}/../../docker/binderhub"
COMMAND=${1:-}
case "$COMMAND" in
  prepare)
    : "${2:?Usage: setup_binderhub.sh prepare <rdm_root>}"
    default_interface=$(ip -4 route show default | awk 'NR==1 {print $5}')
    host_ip=${BINDERHUB_HOST_IP:-$(ip -4 addr show "$default_interface" scope global | awk '/inet / {split($2, address, "/"); print address[1]; exit}')}
    python3 "${SCRIPT_DIR}/setup_binderhub.py" "$2" --host-ip "$host_ip"
    ;;
  install)
    mount_root=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["mount_root"])' "${STACK_ROOT}/.state/config.json")
    mkdir -p "$mount_root"
    sudo modprobe fuse
    if ! mountpoint -q "$mount_root"; then
      sudo mount --bind "$mount_root" "$mount_root"
    fi
    sudo mount --make-rshared "$mount_root"
    docker pull gcr.io/nii-ap-ops/rdmfs:2026.02.1
    : "${JUPYTERHUB_IMAGE:?Set JUPYTERHUB_IMAGE to a JupyterHub image}" "${BINDERHUB_IMAGE:?Set BINDERHUB_IMAGE to a BinderHub image}"
    docker build -f "${STACK_ROOT}/Dockerfile.hub" --build-arg JUPYTERHUB_IMAGE="$JUPYTERHUB_IMAGE" --build-arg BINDERHUB_IMAGE="$BINDERHUB_IMAGE" -t rdm-e2e-jupyterhub "$STACK_ROOT"
    docker build -f "${STACK_ROOT}/Dockerfile.binder" --build-arg BINDERHUB_IMAGE="$BINDERHUB_IMAGE" -t rdm-e2e-binderhub "$STACK_ROOT"
    docker compose -f "${STACK_ROOT}/compose.yaml" up -d
    # Fail during setup if the spawner or the builder cannot reach the host Docker daemon.
    docker compose -f "${STACK_ROOT}/compose.yaml" exec -T hub python -c 'import docker; print(docker.from_env().version()["Version"])'
    docker compose -f "${STACK_ROOT}/compose.yaml" exec -T binder docker version
    for attempt in $(seq 1 90); do
      if status=$(curl --silent --show-error -o /dev/null -w '%{http_code}' http://192.168.168.167:18010/api/services); then
        if [ "$status" = 302 ]; then exit 0; fi
      fi
      sleep 2
    done
    echo 'BinderHub did not become ready' >&2
    exit 1
    ;;
  down)
    docker compose -f "${STACK_ROOT}/compose.yaml" down
    docker ps -aq --filter name=rdm-e2e-binder- | xargs -r docker rm -f
    if [ -f "${STACK_ROOT}/.state/config.json" ]; then
      mount_root=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["mount_root"])' "${STACK_ROOT}/.state/config.json")
      if mountpoint -q "$mount_root"; then
        sudo umount --recursive --lazy "$mount_root"
      fi
    fi
    ;;
  *)
    echo 'Usage: setup_binderhub.sh <prepare|install|down> [rdm_root]' >&2
    exit 1
    ;;
esac
