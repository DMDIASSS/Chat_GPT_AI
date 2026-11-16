#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash colab/_run.sh evaluate --run duel01 --games 20 --seconds 60 "$@"
