#!/bin/sh
# Build the Points Are Bad Docker image.
# Usage:  bash scripts/build.sh [version]
# Example: bash scripts/build.sh v0.5
set -e

TAG="${1:-latest}"

echo "Building points-are-bad:${TAG} ..."
docker compose build

IMAGE=$(docker compose images -q web)
if [ "${TAG}" != "latest" ]; then
    docker tag "${IMAGE}" "points-are-bad:${TAG}"
    echo "Tagged ${IMAGE} → points-are-bad:${TAG}"
fi

echo "Done.  Image: points-are-bad:${TAG}"
