#!/usr/bin/env bash
set -euo pipefail

PROFILE_RAW="${1:-${VERMAMG_PROFILE:-local_wsl}}"
MODE_RAW="${2:-regression}"
MANIFEST_PATH="${3:-config/resource_manifest.tsv}"

if [ ! -s "$MANIFEST_PATH" ]; then
  echo "ERROR: resource manifest missing or empty: $MANIFEST_PATH" >&2
  return 1 2>/dev/null || exit 1
fi

case "$MODE_RAW" in
  regression|pilot32) MODE="regression" ;;
  smoke|test) MODE="test" ;;
  full|tier1_full) MODE="full" ;;
  render) MODE="render" ;;
  foldseek) MODE="foldseek" ;;
  p2rank) MODE="p2rank" ;;
  local) MODE="local" ;;
  *) MODE="$MODE_RAW" ;;
esac

# Lightweight TSV parser. This loader intentionally does not copy/symlink/run tools.
# It exports a compact set of VERMAMG_RESOURCE_* variables for source modules.
while IFS=$'\t' read -r \
  resource_id resource_class profile_scope logical_name current_key current_value exists_now current_kind size_hint \
  preferred_location bundle_mode required_for_modes version_command test_command checksum_policy migration_priority risk notes
do
  # Skip header.
  [ "$resource_id" = "resource_id" ] && continue

  # Profile filter: accept all or matching profile.
  if [ "$profile_scope" != "all" ] && [ "$profile_scope" != "$PROFILE_RAW" ]; then
    continue
  fi

  # Mode filter: accept if mode is listed, or if full/regression resource is broadly useful.
  case ",$required_for_modes," in
    *",$MODE,"*) ;;
    *,full,*) ;;
    *,regression,*) ;;
    *) continue ;;
  esac

  # Convert resource_id to safe env suffix.
  safe_id="$(printf "%s" "$resource_id" | tr '[:lower:].-' '[:upper:]__' | sed 's/[^A-Z0-9_]/_/g')"

  # Export current and preferred path information.
  eval "export VERMAMG_RESOURCE_${safe_id}_CURRENT=\"\$current_value\""
  eval "export VERMAMG_RESOURCE_${safe_id}_PREFERRED=\"\$preferred_location\""
  eval "export VERMAMG_RESOURCE_${safe_id}_CLASS=\"\$resource_class\""
  eval "export VERMAMG_RESOURCE_${safe_id}_BUNDLE_MODE=\"\$bundle_mode\""
  eval "export VERMAMG_RESOURCE_${safe_id}_RISK=\"\$risk\""

done < "$MANIFEST_PATH"

export VERMAMG_RESOURCE_MANIFEST="$MANIFEST_PATH"
export VERMAMG_RESOURCE_PROFILE="$PROFILE_RAW"
export VERMAMG_RESOURCE_MODE="$MODE"

# Convenience aliases for current major resources.
# Existing profile keys remain authoritative; these aliases are for manifest-aware modules later.
if [ -n "${VERMAMG_RESOURCE_TOOL_FOLDSEEK_BINARY_CURRENT:-}" ]; then
  export VERMAMG_MANIFEST_FOLDSEEK_BIN="$VERMAMG_RESOURCE_TOOL_FOLDSEEK_BINARY_CURRENT"
fi
if [ -n "${VERMAMG_RESOURCE_TOOL_P2RANK_JAR_CURRENT:-}" ]; then
  export VERMAMG_MANIFEST_P2RANK_JAR="$VERMAMG_RESOURCE_TOOL_P2RANK_JAR_CURRENT"
fi
if [ -n "${VERMAMG_RESOURCE_DB_FOLDSEEK_PDB_CURRENT:-}" ]; then
  export VERMAMG_MANIFEST_PDB_FOLDSEEK_DB="$VERMAMG_RESOURCE_DB_FOLDSEEK_PDB_CURRENT"
fi
if [ -n "${VERMAMG_RESOURCE_DB_FOLDSEEK_AFSP_CURRENT:-}" ]; then
  export VERMAMG_MANIFEST_AFSP_FOLDSEEK_DB="$VERMAMG_RESOURCE_DB_FOLDSEEK_AFSP_CURRENT"
fi
if [ -n "${VERMAMG_RESOURCE_TOOL_PYMOL_WRAPPER_CURRENT:-}" ]; then
  export VERMAMG_MANIFEST_PYMOL_CMD="$VERMAMG_RESOURCE_TOOL_PYMOL_WRAPPER_CURRENT"
fi
