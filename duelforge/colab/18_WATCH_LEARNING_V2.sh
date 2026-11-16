#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash colab/_run.sh watch --run duel02 --scene 5 --seconds 120 --headless "$@"
