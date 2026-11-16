#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"${DUELFORGE_PYTHON:-python}" -u tools/check_sides.py --run duel02
