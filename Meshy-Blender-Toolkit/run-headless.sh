#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/../blender-4.5.13-linux-x64/blender" --background --factory-startup "$@"
