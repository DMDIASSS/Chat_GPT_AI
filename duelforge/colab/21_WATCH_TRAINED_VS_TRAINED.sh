#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${DUELFORGE_PYTHON:-python}" -u run.py watch --run duel02 --opponent self --scene 5 --seconds 120 --headless
