FROM python:3.12-slim-trixie
# Use the host daemon through the socket; only its CLI belongs in this image.
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs npm docker-cli docker-buildx ca-certificates patch && docker --version && docker buildx version && rm -rf /var/lib/apt/lists/*
RUN npm install -g configurable-http-proxy
ARG BINDERHUB_REV=9282cd4d
RUN git clone https://github.com/RCOSDP/CS-binderhub.git /opt/binderhub && cd /opt/binderhub && git checkout "$BINDERHUB_REV"
# The local builder must forward per-request RDM credentials, as the Kubernetes builder does.
COPY local-build-optional-envs.patch /tmp/local-build-optional-envs.patch
RUN cd /opt/binderhub && patch -p1 < /tmp/local-build-optional-envs.patch && pip install . dockerspawner
WORKDIR /opt/e2e
COPY jupyterhub_config.py binderhub_config.py rdm_spawner.py ./
CMD ["jupyterhub", "--config=/opt/e2e/jupyterhub_config.py"]
