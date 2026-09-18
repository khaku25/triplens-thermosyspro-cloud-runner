#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python3 scripts/update_triplens_logic.py "$@"
