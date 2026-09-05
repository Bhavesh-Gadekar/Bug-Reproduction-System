# -- Stage 1: base image with Python ------------------------------------------
FROM python:3.11-slim AS base

# Install the Docker CLI so the service can invoke `docker run`.
# We install docker-ce-cli from the official Docker apt repo — just the CLI,
# no daemon runs inside this container. The host daemon is reached via the
# /var/run/docker.sock bind-mount added in docker-compose.yml.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        lsb-release && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
        > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -- Stage 2: install Python dependencies --------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -- Stage 3: copy application source ------------------------------------------
# Build context is ./sandbox, so files land at:
#   /app/app/__init__.py
#   /app/app/main.py        <-- uvicorn target: app.main:app
#   /app/app/config.py
#   /app/app/runner.py
COPY . .

# Expose the service port
EXPOSE 8001

# Health-check: poll /health every 10 s
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Module path is relative to WORKDIR (/app), NOT the repo root.
# Build context = ./sandbox, so the package is "app", not "sandbox.app".
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
