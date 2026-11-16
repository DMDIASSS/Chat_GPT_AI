#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${DUELFORGE_PYTHON:-python}" -u run.py watch --run potential01 --opponent initial --scene 5 --seconds 60 --headless
