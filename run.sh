#!/usr/bin/env bash
# Convenience launcher for CIPHERHOUND on macOS / Linux.
# Equivalent to `python3 -m cipherhound "$@"`.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m cipherhound "$@"
