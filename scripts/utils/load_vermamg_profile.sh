#!/usr/bin/env bash
# VermAMG profile loader
#
# Usage:
#   source scripts/utils/load_vermamg_profile.sh truba
#   source scripts/utils/load_vermamg_profile.sh local_wsl

_profile="${1:-${VERMAMG_PROFILE:-local_wsl}}"

# Auto-detect project root from this file location:
# scripts/utils/load_vermamg_profile.sh -> project root is ../..
_loader_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_auto_root="$(cd "${_loader_dir}/../.." && pwd)"

export VERMAMG_ROOT="${VERMAMG_ROOT:-$_auto_root}"

_defaults="$VERMAMG_ROOT/config/vermamg_defaults.env"
_profile_file="$VERMAMG_ROOT/config/profiles/${_profile}.env"

if [ ! -s "$_defaults" ]; then
  echo "ERROR: VermAMG defaults file missing: $_defaults" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$_defaults"

if [ ! -s "$_profile_file" ]; then
  echo "ERROR: VermAMG profile file missing: $_profile_file" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$_profile_file"

# Re-assert auto root if profile left it empty.
export VERMAMG_ROOT="${VERMAMG_ROOT:-$_auto_root}"

# Add utility scripts to PATH.
case ":$PATH:" in
  *":$VERMAMG_ROOT/scripts/utils:"*) ;;
  *) export PATH="$VERMAMG_ROOT/scripts/utils:$PATH" ;;
esac

echo "VERMAMG_PROFILE_LOADED=$VERMAMG_PROFILE"
echo "VERMAMG_ROOT=$VERMAMG_ROOT"
echo "EXECUTION_BACKEND=$EXECUTION_BACKEND"
