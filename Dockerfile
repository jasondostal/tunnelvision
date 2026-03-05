# ============================================================================
# TunnelVision — All-in-one qBittorrent + WireGuard + API
# Multi-stage, multi-arch Dockerfile
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build the React dashboard
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 node:22-alpine AS ui-builder

WORKDIR /build
COPY ui/package*.json ./
RUN npm install --no-audit
COPY ui/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Install Python API dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-alpine AS api-builder

WORKDIR /build
COPY api/requirements.txt ./
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 3: Runtime
# ---------------------------------------------------------------------------
FROM alpine:3.21

LABEL maintainer="Jason Dostal"
LABEL org.opencontainers.image.title="TunnelVision"
LABEL org.opencontainers.image.description="All-in-one qBittorrent + WireGuard VPN + API container"
LABEL org.opencontainers.image.source="https://github.com/jasondostal/tunnelvision"
LABEL org.opencontainers.image.licenses="MIT"

# s6-overlay version
ARG S6_OVERLAY_VERSION=3.2.2.0
ARG TARGETARCH
ARG TARGETVARIANT

# Environment defaults
ENV TZ=America/Chicago \
    PUID=1000 \
    PGID=1000 \
    # VPN
    VPN_ENABLED=true \
    VPN_TYPE=wireguard \
    VPN_PROVIDER=custom \
    KILLSWITCH_ENABLED=true \
    # qBittorrent
    WEBUI_PORT=8080 \
    WEBUI_ALLOWED_NETWORKS=192.168.0.0/16,172.16.0.0/12,10.0.0.0/8 \
    # API
    API_ENABLED=true \
    API_PORT=8081 \
    # UI
    UI_ENABLED=true \
    # Health
    HEALTH_CHECK_INTERVAL=15 \
    # s6
    S6_KEEP_ENV=1 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=0 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=30000 \
    # Python
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install s6-overlay
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz && rm /tmp/s6-overlay-noarch.tar.xz

RUN ARCH= && \
    case "${TARGETARCH}" in \
        amd64)   ARCH="x86_64" ;; \
        arm64)   ARCH="aarch64" ;; \
        arm)     ARCH="armhf" ;; \
        386)     ARCH="i686" ;; \
        ppc64le) ARCH="powerpc64le" ;; \
        *)       ARCH="${TARGETARCH}" ;; \
    esac && \
    wget -qO /tmp/s6-overlay-arch.tar.xz \
        "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-${ARCH}.tar.xz" && \
    tar -C / -Jxpf /tmp/s6-overlay-arch.tar.xz && rm /tmp/s6-overlay-arch.tar.xz

ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-symlinks-noarch.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-symlinks-noarch.tar.xz && rm /tmp/s6-overlay-symlinks-noarch.tar.xz

# Install runtime dependencies
# wireguard-go was removed from Alpine 3.21 stable; pull it from edge community
RUN apk add --no-cache \
    bash \
    bind-tools \
    curl \
    iproute2 \
    jq \
    nftables \
    python3 \
    py3-pip \
    py3-cryptography \
    openvpn \
    qbittorrent-nox \
    shadow \
    tzdata \
    wireguard-tools && \
    apk add --no-cache \
    --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community \
    wireguard-go

# Create app user (will be modified at runtime by init-environment)
RUN addgroup -g 1000 tunnelvision && \
    adduser -D -u 1000 -G tunnelvision -h /config tunnelvision

# Copy Python API dependencies from builder
COPY --from=api-builder /install /usr/lib/python3.12/site-packages/

# Copy API source
COPY api/ /app/api/

# Copy built UI from builder
COPY --from=ui-builder /build/dist /app/ui/dist

# Copy s6 service definitions and scripts
COPY rootfs/ /

# Copy default configs
COPY rootfs/defaults/ /defaults/

# Make scripts executable
RUN find /etc/s6-overlay/scripts -type f -exec chmod +x {} + && \
    find /etc/s6-overlay/s6-rc.d -name "run" -exec chmod +x {} + && \
    find /etc/s6-overlay/s6-rc.d -name "finish" -exec chmod +x {} +

# Volumes
VOLUME ["/config", "/downloads"]

# Expose ports
EXPOSE ${WEBUI_PORT} ${API_PORT} 8888 1080

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD /etc/s6-overlay/scripts/healthcheck.sh || exit 1

ENTRYPOINT ["/init"]
