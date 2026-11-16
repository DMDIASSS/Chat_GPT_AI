#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash colab/_run.sh pause --run duel01 "$@"
