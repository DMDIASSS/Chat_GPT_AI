#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash colab/setup.sh "$@"
