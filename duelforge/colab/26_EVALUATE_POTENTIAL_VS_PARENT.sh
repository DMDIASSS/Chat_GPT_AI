#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${DUELFORGE_PYTHON:-python}" -u run.py evaluate --run potential01 --context match --games 200 --seconds 100
