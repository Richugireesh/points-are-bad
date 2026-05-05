#!/bin/sh
# Entrypoint for Points Are Bad Docker container.
# Ensures the data directory exists and is writable, then hands off to gunicorn.

set -e

DATA_DIR=$(dirname "${POINTS_DATA_FILE:-/data/points_are_bad_data.db}")

mkdir -p "$DATA_DIR"

# If a legacy JSON file exists alongside the volume, the app auto-migrates
# it to SQLite on first startup — no manual intervention needed.

exec "$@"
