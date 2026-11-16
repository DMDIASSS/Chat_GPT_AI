#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash colab/_run.sh train --run duel01 --minutes 60 "$@"
