#!/usr/bin/env bash
set -euo pipefail

PROFILE_RAW="${1:-${VERMAMG_PROFILE:-local_wsl}}"
MODE_RAW="${2:-regression}"
MANIFEST_PATH="${3:-config/resource_manifest.tsv}"
OUT_REPORT="${4:-results/regression/99_vermamg_audit/resource_manifest_qc_report.tsv}"
OUT_SUMMARY="${5:-results/regression/99_vermamg_audit/resource_manifest_qc_summary.tsv}"

mkdir -p "$(dirname "$OUT_REPORT")" "$(dirname "$OUT_SUMMARY")"

if [ ! -s "$MANIFEST_PATH" ]; then
  echo "ERROR: resource manifest missing or empty: $MANIFEST_PATH" >&2
  exit 1
fi


expand_resource_path() {
  local raw="$1"
  local expanded="$raw"

  expanded="${expanded//'${VERMAMG_ROOT}'/$VERMAMG_ROOT}"
  expanded="${expanded//'\${VERMAMG_ROOT}'/$VERMAMG_ROOT}"
  expanded="${expanded//'$VERMAMG_ROOT'/$VERMAMG_ROOT}"

  expanded="${expanded//'${VERMAMG_TOOLS_ROOT}'/${VERMAMG_TOOLS_ROOT:-}}"
  expanded="${expanded//'\${VERMAMG_TOOLS_ROOT}'/${VERMAMG_TOOLS_ROOT:-}}"
  expanded="${expanded//'$VERMAMG_TOOLS_ROOT'/${VERMAMG_TOOLS_ROOT:-}}"

  expanded="${expanded//'${VERMAMG_DATABASES_ROOT}'/${VERMAMG_DATABASES_ROOT:-}}"
  expanded="${expanded//'\${VERMAMG_DATABASES_ROOT}'/${VERMAMG_DATABASES_ROOT:-}}"
  expanded="${expanded//'$VERMAMG_DATABASES_ROOT'/${VERMAMG_DATABASES_ROOT:-}}"

  expanded="${expanded//'${VERMAMG_CONTAINERS_ROOT}'/${VERMAMG_CONTAINERS_ROOT:-}}"
  expanded="${expanded//'\${VERMAMG_CONTAINERS_ROOT}'/${VERMAMG_CONTAINERS_ROOT:-}}"
  expanded="${expanded//'$VERMAMG_CONTAINERS_ROOT'/${VERMAMG_CONTAINERS_ROOT:-}}"

  printf "%s" "$expanded"
}


printf "resource_id\tresource_class\tprofile_scope\tcurrent_key\tcurrent_value\texists_now_manifest\tactual_exists\tactual_kind\tstatus\tmessage\n" > "$OUT_REPORT"

HEADER_COLS="$(awk -F'\t' 'NR==1{print NF}' "$MANIFEST_PATH")"
ROW_N="$(awk 'NR>1{c++} END{print c+0}' "$MANIFEST_PATH")"
BAD_COL_N="$(awk -F'\t' 'NR>1 && NF!=18{c++} END{print c+0}' "$MANIFEST_PATH")"
DUP_N="$(awk -F'\t' 'NR>1{c[$1]++} END{for(k in c) if(c[k]>1) d++; print d+0}' "$MANIFEST_PATH")"

PASS_N=0
WARN_N=0
FAIL_N=0

while IFS=$'\t' read -r \
  resource_id resource_class profile_scope logical_name current_key current_value exists_now current_kind size_hint \
  preferred_location bundle_mode required_for_modes version_command test_command checksum_policy migration_priority risk notes
do
  [ "$resource_id" = "resource_id" ] && continue

  actual_exists="NO"
  actual_kind="missing"
  status="PASS"
  message="ok"

  if [ -z "$resource_id" ] || [ -z "$current_key" ] || [ -z "$current_value" ]; then
    status="FAIL"
    message="missing required manifest value"
  else
    current_value_expanded="$(expand_resource_path "$current_value")"
  fi

  if [ "$status" = "FAIL" ]; then
    :
  elif [ -e "$current_value_expanded" ]; then
    actual_exists="YES"
    if [ -d "$current_value_expanded" ]; then
      actual_kind="dir"
    elif [ -f "$current_value_expanded" ]; then
      actual_kind="file"
    else
      actual_kind="other"
    fi

    if [ "$exists_now" != "YES" ]; then
      status="WARN"
      message="manifest says not YES but path exists"
    fi
  else
    # Commands such as foldseek may be command-like later; current manifest stores absolute paths, so missing is warning/fail by priority.
    actual_exists="NO"
    actual_kind="missing"

    if [ "$migration_priority" = "P1" ]; then
      status="FAIL"
      message="P1 resource path missing"
    else
      status="WARN"
      message="resource path missing or externally managed"
    fi
  fi

  # Foldseek DB prefixes are special: the prefix itself can be a file, but sidecars are what matter.
  if [ "$resource_class" = "large_structure_database" ]; then
    if [ -s "${current_value_expanded}.dbtype" ]; then
      if [ "$status" = "PASS" ]; then
        message="db prefix sidecar .dbtype exists"
      fi
    else
      if [ "$status" = "PASS" ]; then
        status="WARN"
        message="db prefix exists but .dbtype sidecar not found"
      else
        message="${message}; .dbtype sidecar not found"
      fi
    fi
  fi

  case "$status" in
    PASS) PASS_N=$((PASS_N+1)) ;;
    WARN) WARN_N=$((WARN_N+1)) ;;
    FAIL) FAIL_N=$((FAIL_N+1)) ;;
  esac

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "$resource_id" "$resource_class" "$profile_scope" "$current_key" "$current_value" "$exists_now" "$actual_exists" "$actual_kind" "$status" "$message" >> "$OUT_REPORT"

done < "$MANIFEST_PATH"

printf "metric\tvalue\n" > "$OUT_SUMMARY"
{
  printf "profile\t%s\n" "$PROFILE_RAW"
  printf "mode\t%s\n" "$MODE_RAW"
  printf "manifest\t%s\n" "$MANIFEST_PATH"
  printf "header_cols\t%s\n" "$HEADER_COLS"
  printf "resource_rows\t%s\n" "$ROW_N"
  printf "bad_column_rows\t%s\n" "$BAD_COL_N"
  printf "duplicate_resource_ids\t%s\n" "$DUP_N"
  printf "pass_n\t%s\n" "$PASS_N"
  printf "warn_n\t%s\n" "$WARN_N"
  printf "fail_n\t%s\n" "$FAIL_N"
} >> "$OUT_SUMMARY"

if [ "$HEADER_COLS" -ne 18 ] || [ "$BAD_COL_N" -ne 0 ] || [ "$DUP_N" -ne 0 ] || [ "$FAIL_N" -ne 0 ]; then
  exit 1
fi

exit 0
