#!/usr/bin/env bash
# Compatibility entry point for older setup instructions.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
printf 'Using the maintained installer. Start the app afterward with: bash start_dsfst.sh\n'
exec bash install_dsfst.sh
