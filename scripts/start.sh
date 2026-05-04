#!/bin/sh
# Start the Points Are Bad stack.
# Set API_TOKEN in .env first:  echo "API_TOKEN=$(openssl rand -hex 32)" > .env
set -e
docker compose up -d
echo "Dashboard → http://localhost:${PORT:-5001}"
