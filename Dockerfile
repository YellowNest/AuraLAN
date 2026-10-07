# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm

ARG AURALAN_VERSION=dev

LABEL org.opencontainers.image.title="AuraLAN" \
      org.opencontainers.image.description="Local-first LAN inventory and network monitoring" \
      org.opencontainers.image.source="https://github.com/YellowNest/AuraLAN" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${AURALAN_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    AURALAN_CONTAINER_MODE=1 \
    AURALAN_DATA_DIR=/data \
    AURALAN_HOST=0.0.0.0 \
    AURALAN_PORT=8787 \
    AURALAN_HOST_PROC=/host/proc \
    AURALAN_HOST_SYS=/host/sys \
    AURALAN_HOSTNAME_FILE=/host/etc/hostname \
    AURALAN_HOSTS_FILE=/host/etc/hosts

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        avahi-utils \
        ca-certificates \
        ieee-data \
        iproute2 \
        iputils-ping \
        iw \
        network-manager \
        samba-common-bin \
        tini \
        wireguard-tools \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 auralan \
    && useradd --system --uid 10001 --gid 10001 --home-dir /data --shell /usr/sbin/nologin auralan \
    && mkdir -p /app/backend /data /host/proc /host/sys /host/etc \
    && chown -R auralan:auralan /data

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --requirement /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY --chown=root:root backend/app /app/backend/app
COPY --chown=root:root frontend /app/frontend
COPY --chown=root:root project.json /app/project.json

VOLUME ["/data"]
EXPOSE 8787

USER 10001:10001
WORKDIR /app/backend

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import json, urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health', timeout=3); d=json.load(r); raise SystemExit(0 if r.status == 200 and d.get('ok') is True else 1)"]

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787", "--no-access-log"]
