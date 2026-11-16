#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${DUELFORGE_PYTHON:-python}" -u run.py report --run potential01
