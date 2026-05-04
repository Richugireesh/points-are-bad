# ── Stage 1: build dependencies ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only the files needed to resolve the dependency graph first, so Docker
# caches this layer and skips re-downloading packages when only source changes.
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install the package and its web dependencies into a venv under /build/.venv
RUN uv venv .venv && \
    uv pip install --no-cache -e ".[web]"

# ── Stage 2: runtime image ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user — defense-in-depth
RUN groupadd -r pab && useradd -r -g pab -d /app -s /sbin/nologin pab

WORKDIR /app

# Copy the pre-built venv and source from the builder stage
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src
COPY web/ ./web/
COPY gunicorn.conf.py ./
COPY docker-entrypoint.sh /usr/local/bin/

# Persistent data volume — mount a host directory here to survive container restarts
VOLUME ["/data"]

ENV POINTS_DATA_FILE=/data/points_are_bad_data.json \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Gunicorn needs the src/ package on PYTHONPATH since it's an editable install
ENV PYTHONPATH=/app/src

USER pab

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/aliases')"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "web.server:app"]
