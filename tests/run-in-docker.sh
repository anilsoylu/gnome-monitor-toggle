#!/usr/bin/env bash
# Build the headless test image (cached) and run a command in it with the repo mounted.
#
#   tests/run-in-docker.sh python3 -m unittest discover -s tests -v
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
IMAGE="${GMT_IMAGE:-gnome-monitor-toggle-test}"

docker build -q -t "$IMAGE" -f "$HERE/docker/Dockerfile" "$HERE/docker" >/dev/null
docker run --rm --network none -e VIRTUAL_MONITORS -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$ROOT:/src:ro" "$IMAGE" tests/run-headless.sh "$@"
