#!/usr/bin/env bash
# Upgrade Cognition Engine to latest GitHub master (re-downloads source + pip install).
exec env CE_REFRESH="${CE_REFRESH:-0}" "$(dirname "$0")/install-ce.sh" "$@"
