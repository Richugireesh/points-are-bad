#!/bin/sh
# Ensure the data directory is writable before dropping privileges.
# Docker volumes inherit host directory ownership — the pab user may
# not have write access on first run.
set -e

DATA_DIR=$(dirname "${POINTS_DATA_FILE:-/data/points_are_bad_data.json}")
mkdir -p "$DATA_DIR" 2>/dev/null || true
chown pab:pab "$DATA_DIR" 2>/dev/null || true

exec su pab -c 'exec gunicorn -c gunicorn.conf.py web.server:app'
