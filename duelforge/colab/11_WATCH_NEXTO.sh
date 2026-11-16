#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash colab/_run.sh watch --run duel01 --opponent nexto --seconds 120 --headless "$@"
