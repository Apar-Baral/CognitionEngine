#!/usr/bin/env bash
# Legacy name — delegates to install-ce.sh (slim install).
exec "$(dirname "$0")/install-ce.sh" "$@"
