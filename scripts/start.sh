#!/bin/sh
# Start the Points Are Bad stack.
# Usage:  bash scripts/start.sh
#
# Set API_TOKEN in .env first:  echo "API_TOKEN=$(openssl rand -hex 32)" > .env
set -e

# Load .env so TS_HOSTNAME and other vars are available
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
if [ -f "${ENV_FILE}" ]; then
    set -a
    . "${ENV_FILE}"
    set +a
fi

PORT="${PORT:-5001}"
TS_HOSTNAME="${TS_HOSTNAME:-}"

docker compose up -d

# Verify dashboard is responding.
# Defaults to Tailscale URL when TS_HOSTNAME is set, falls back to localhost.
if [ -n "${TS_HOSTNAME}" ]; then
    HEALTH_URL="https://${TS_HOSTNAME}.ts.net/health"
else
    HEALTH_URL="http://localhost:${PORT}/health"
fi
HEALTH_URL="${HEALTH_CHECK_URL:-${HEALTH_URL}}"

echo "Checking ${HEALTH_URL} ..."
for i in $(seq 1 15); do
    if curl -sf "${HEALTH_URL}" > /dev/null 2>&1; then
        echo "Dashboard ready → ${HEALTH_URL}"
        exit 0
    fi
    sleep 2
done

echo "Warning: dashboard not responding after 30s" >&2
echo "Dashboard → ${HEALTH_URL}"
