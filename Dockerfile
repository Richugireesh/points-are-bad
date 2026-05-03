FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer until pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv venv .venv && \
    uv pip install --no-cache ".[web]"

# Runtime assets
COPY web/ ./web/
COPY gunicorn.conf.py docker-entrypoint.sh ./

# Non-root user (entrypoint runs as root, fixes permissions, then drops to pab)
RUN groupadd -r pab && useradd -r -g pab -d /app -s /bin/sh pab && \
    chown -R pab:pab /app && \
    chmod +x docker-entrypoint.sh

# Persistent data volume
VOLUME ["/data"]

ENV POINTS_DATA_FILE=/data/points_are_bad_data.json \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/aliases')"

ENTRYPOINT ["./docker-entrypoint.sh"]
