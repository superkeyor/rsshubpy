# =============================================================================
# Base Image
# =============================================================================
# chromiumkit: Debian + Chromium + Xvfb + x11vnc + noVNC (`vnc-start`, ENABLE_VNC, VNC_PASSWORD, port 6080)
# https://hub.docker.com/r/superkeyor/chromiumkit
# Miniforge (mamba + conda environments) is added below, as in dockerapp_template.
# Install steps borrowed from the official (Ubuntu-only) miniforge3 image:
# https://github.com/conda-forge/miniforge-images/blob/main/ubuntu/Dockerfile
FROM superkeyor/chromiumkit:latest
ARG MINIFORGE_VERSION=26.9.4-0

# =============================================================================
# Labels
# =============================================================================
LABEL maintainer="superkeyor"
LABEL description="RSSHub in Python (Flask) with one container-lifetime headed Chromium (SeleniumBase UC + CDP mode)"
LABEL org.opencontainers.image.title="rsshubpy"

# =============================================================================
# Miniforge
# =============================================================================
ENV CONDA_DIR=/opt/conda
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PATH=${CONDA_DIR}/bin:${PATH}

# tini: PID 1 init (signal forwarding, zombie reaping), as in the official image
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends wget ca-certificates tini && \
    rm -rf /var/lib/apt/lists/* && \
    wget --no-hsts -q "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-$(uname -m).sh" -O /tmp/miniforge.sh && \
    bash /tmp/miniforge.sh -b -p ${CONDA_DIR} && \
    rm /tmp/miniforge.sh && \
    find ${CONDA_DIR} -follow -type f \( -name '*.a' -o -name '*.pyc' \) -delete && \
    conda clean -afy

# =============================================================================
# Environment Variables
# =============================================================================
# cron rebuilds the cached feeds (crontab)
ARG ENABLE_CRON=true
ENV ENABLE_CRON=$ENABLE_CRON
ENV TZ=America/Chicago
ENV APP_ENV=production
ENV LOG_LEVEL=INFO

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_ROOT_USER_ACTION=ignore

# Browser (app/browser.py); all overridable at runtime
# Persistent Chrome profile; bind-mount a host folder here (docker-compose.yml)
ENV CHROME_USER_DATA_DIR=/app/chromiumprofile
# At most this many Chrome windows at once (one per site)
ENV MAX_WINDOWS=3
# At start, if the profile is bigger than this (MB), its cache folders are deleted; 0 = never trim
ENV PROFILE_MAX_MB=2000

# =============================================================================
# System Dependencies
# =============================================================================
# tzdata for timezone config. Chromium, chromedriver and Xvfb come from the base image.
RUN export DEBIAN_FRONTEND=noninteractive && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo "$TZ" > /etc/timezone && \
    apt-get update && \
    PKGS="tzdata"; [ "$ENABLE_CRON" = "true" ] && PKGS="$PKGS cron"; \
    apt-get install -y --no-install-recommends $PKGS && \
    rm -rf /var/lib/apt/lists/*

# Verify the Chromium binary (Debian's, from the base image)
RUN chromium --version && chromedriver --version

# =============================================================================
# Application Setup & Python Package Installation
# =============================================================================
WORKDIR /app
COPY environment.yml .

RUN mamba env create -y -f environment.yml && \
    echo "source activate app" >> ~/.bashrc && \
    mamba clean -afy

ENV PATH=/opt/conda/envs/app/bin:$PATH

# arm64 + SeleniumBase uc=True: SeleniumBase downloads Google's x86-64-only chromedriver, so uc mode dies
# ("Dynamic loader not found: ld-linux-x86-64"). Point it at Debian's driver (matches Chromium on every arch).
RUN D=$(python -c "import seleniumbase,os;print(os.path.dirname(seleniumbase.__file__))")/drivers && \
    ln -sf /usr/bin/chromedriver $D/uc_driver && ln -sf /usr/bin/chromedriver $D/chromedriver

# =============================================================================
# Application Files
# =============================================================================
COPY app/ .
COPY start.sh crontab /

RUN if [ "$ENABLE_CRON" = "true" ]; then crontab /crontab; fi

# =============================================================================
# Container Configuration
# =============================================================================
# 5000: Flask/gunicorn. The base image already exposes 6080 (noVNC, only with ENABLE_VNC=true).
EXPOSE 5000
ENTRYPOINT ["tini", "--"]
CMD ["bash", "/start.sh"]
