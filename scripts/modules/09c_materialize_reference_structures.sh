#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-test}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="local_wsl"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"

case "$MODE_RAW" in
  smoke|test) MODE="test" ;;
  pilot32|regression) MODE="regression" ;;
  full|tier1_full) MODE="tier1_full" ;;
  *)
    echo "ERROR: mode must be one of test/regression/tier1_full. Got: $MODE_RAW"
    exit 1
    ;;
esac

PANEL_TSV="${PROJECT_ROOT}/05_reference_panel/${MODE}/${MODE}_reference_panel_targets.tsv"
FOLDSEEK_BIN="${FOLDSEEK_BIN:-}"
PDB_DB="${PDB_FOLDSEEK_DB:-}"
AFSP_DB="${AFSP_FOLDSEEK_DB:-}"

MATERIALIZED_ROOT="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_structures/materialized"
PDB_OUT_DIR="${MATERIALIZED_ROOT}/pdb"
AFSP_OUT_DIR="${MATERIALIZED_ROOT}/afsp"
WORK_DIR="${MATERIALIZED_ROOT}/work"
RESOLUTION_DIR="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_resolution"
REPORT_TSV="${RESOLUTION_DIR}/${MODE}_materialized_reference_structures.tsv"
SUMMARY_TSV="${RESOLUTION_DIR}/${MODE}_materialized_reference_structures_summary.tsv"

STRUCTURE_BASE="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_structures"
RESOLUTION_BASE="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_resolution"

require_under() {
  local path="$1"
  local base="$2"
  case "$path" in
    "$base"|"$base"/*) ;;
    *)
      echo "ERROR: refusing path outside allowed root: path=$path base=$base"
      exit 1
      ;;
  esac
}

require_under "$MATERIALIZED_ROOT" "$STRUCTURE_BASE"
require_under "$PDB_OUT_DIR" "$STRUCTURE_BASE"
require_under "$AFSP_OUT_DIR" "$STRUCTURE_BASE"
require_under "$WORK_DIR" "$STRUCTURE_BASE"
require_under "$RESOLUTION_DIR" "$RESOLUTION_BASE"
require_under "$REPORT_TSV" "$RESOLUTION_BASE"
require_under "$SUMMARY_TSV" "$RESOLUTION_BASE"

if [ ! -s "$PANEL_TSV" ]; then
  echo "ERROR: required panel TSV missing or empty: $PANEL_TSV"
  exit 1
fi
if [ ! -x "$FOLDSEEK_BIN" ]; then
  echo "ERROR: FOLDSEEK_BIN missing or not executable: ${FOLDSEEK_BIN:-NA}"
  exit 1
fi
if [ ! -s "${PDB_DB}.dbtype" ]; then
  echo "ERROR: PDB Foldseek DB dbtype missing: ${PDB_DB:-NA}.dbtype"
  exit 1
fi
if [ ! -s "${AFSP_DB}.dbtype" ]; then
  echo "ERROR: AFSP Foldseek DB dbtype missing: ${AFSP_DB:-NA}.dbtype"
  exit 1
fi

mkdir -p "$PDB_OUT_DIR" "$AFSP_OUT_DIR" "$WORK_DIR" "$RESOLUTION_DIR"

PDB_TARGET_IDS="${WORK_DIR}/${MODE}_pdb_target_ids.txt"
AFSP_TARGET_IDS="${WORK_DIR}/${MODE}_afsp_target_ids.txt"
: > "$PDB_TARGET_IDS"
: > "$AFSP_TARGET_IDS"

awk -F'\t' -v pdb_out="$PDB_TARGET_IDS" -v afsp_out="$AFSP_TARGET_IDS" '
  NR == 1 {
    for (i = 1; i <= NF; i++) {
      key = $i
      gsub(/\r$/, "", key)
      h[key] = i
    }
    layer_col = h["reference_layer"] ? h["reference_layer"] : h["source_layer"]
    target_col = h["target_id"] ? h["target_id"] : h["target"]
    if (!layer_col || !target_col) {
      print "ERROR: panel TSV must contain reference_layer/source_layer and target_id/target columns" > "/dev/stderr"
      exit 2
    }
    next
  }
  {
    layer = $(layer_col)
    target = $(target_col)
    gsub(/\r$/, "", layer)
    gsub(/\r$/, "", target)
    gsub(/^[ \t]+|[ \t]+$/, "", layer)
    gsub(/^[ \t]+|[ \t]+$/, "", target)
    layer_upper = toupper(layer)
    if (target == "") {
      next
    }
    if (layer_upper == "PDB") {
      print target >> pdb_out
    } else if (layer_upper == "AFSP") {
      print target >> afsp_out
    }
  }
' "$PANEL_TSV"

sort -u "$PDB_TARGET_IDS" -o "$PDB_TARGET_IDS"
sort -u "$AFSP_TARGET_IDS" -o "$AFSP_TARGET_IDS"

PDB_TARGET_N="$(wc -l < "$PDB_TARGET_IDS" | tr -d ' ')"
AFSP_TARGET_N="$(wc -l < "$AFSP_TARGET_IDS" | tr -d ' ')"
MATERIALIZED_N=0
MISSING_AFTER_EXPORT_N=0
EXPORT_FAILED_N=0

printf "mode\tsource_layer\ttarget_id\tdb_prefix\ttarget_id_file\tsubset_db_prefix\toutput_dir\tmaterialized_file\tstatus\tnote\n" > "$REPORT_TSV"

safe_name() {
  printf "%s" "$1" | sed 's/[^A-Za-z0-9_.-]/_/g'
}

basename_list() {
  local file
  for file in "$@"; do
    basename "$file"
  done | paste -sd ';' -
}

process_group() {
  local source_layer="$1"
  local db_prefix="$2"
  local target_file="$3"
  local final_out_dir="$4"
  local group_lc="$5"

  local target_count
  target_count="$(wc -l < "$target_file" | tr -d ' ')"
  if [ "$target_count" -eq 0 ]; then
    return 0
  fi

  local group_work="${WORK_DIR}/${group_lc}"
  local export_dir="${group_work}/exported_pdb"
  local subset_db="${group_work}/${group_lc}_subset_db"
  local create_log="${group_work}/createsubdb.log"
  local convert_log="${group_work}/convert2pdb.log"

  require_under "$group_work" "$WORK_DIR"
  require_under "$export_dir" "$WORK_DIR"
  require_under "$subset_db" "$WORK_DIR"
  require_under "$final_out_dir" "$STRUCTURE_BASE"

  rm -rf "$group_work"
  mkdir -p "$export_dir" "$final_out_dir"

  set +e
  "$FOLDSEEK_BIN" createsubdb --id-mode 1 "$target_file" "$db_prefix" "$subset_db" > "$create_log" 2>&1
  local create_status=$?
  if [ "$create_status" -eq 0 ]; then
    "$FOLDSEEK_BIN" convert2pdb "$subset_db" "$export_dir" --pdb-output-mode 1 > "$convert_log" 2>&1
    local convert_status=$?
  else
    local convert_status=99
  fi
  set -e

  mapfile -t exported_files < <(find "$export_dir" -type f -iname '*.pdb' 2>/dev/null | sort)

  local target
  while IFS= read -r target; do
    [ -n "$target" ] || continue

    if [ "$create_status" -ne 0 ] || [ "$convert_status" -ne 0 ]; then
      printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t\tEXPORT_FAILED\tcreatesubdb_exit=%s;convert2pdb_exit=%s;logs=%s,%s\n" \
        "$MODE" "$source_layer" "$target" "$db_prefix" "$target_file" "$subset_db" "$final_out_dir" \
        "$create_status" "$convert_status" "$create_log" "$convert_log" >> "$REPORT_TSV"
      EXPORT_FAILED_N=$((EXPORT_FAILED_N + 1))
      continue
    fi

    local match=""
    local file
    local target_lc
    target_lc="$(printf "%s" "$target" | tr '[:upper:]' '[:lower:]')"
    for file in "${exported_files[@]}"; do
      local base
      local stem
      local stem_lc
      base="$(basename "$file")"
      stem="${base%.*}"
      stem_lc="$(printf "%s" "$stem" | tr '[:upper:]' '[:lower:]')"
      if [ "$stem_lc" = "$target_lc" ]; then
        match="$file"
        break
      fi
    done
    if [ -z "$match" ]; then
      for file in "${exported_files[@]}"; do
        local base
        local base_lc
        base="$(basename "$file")"
        base_lc="$(printf "%s" "$base" | tr '[:upper:]' '[:lower:]')"
        case "$base_lc" in
          *"$target_lc"*)
            match="$file"
            break
            ;;
        esac
      done
    fi
    if [ -z "$match" ] && [ "$target_count" -eq 1 ] && [ "${#exported_files[@]}" -eq 1 ]; then
      match="${exported_files[0]}"
    fi

    if [ -n "$match" ] && [ -s "$match" ]; then
      local final_file="${final_out_dir}/$(safe_name "$target").pdb"
      require_under "$final_file" "$STRUCTURE_BASE"
      cp -f "$match" "$final_file"
      printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tMATERIALIZED\tsource_export=%s\n" \
        "$MODE" "$source_layer" "$target" "$db_prefix" "$target_file" "$subset_db" "$final_out_dir" \
        "$final_file" "$match" >> "$REPORT_TSV"
      MATERIALIZED_N=$((MATERIALIZED_N + 1))
    else
      local exported_list
      exported_list="$(basename_list "${exported_files[@]}")"
      printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t\tMISSING_AFTER_EXPORT\texported_pdb_files=%s\n" \
        "$MODE" "$source_layer" "$target" "$db_prefix" "$target_file" "$subset_db" "$final_out_dir" \
        "$exported_list" >> "$REPORT_TSV"
      MISSING_AFTER_EXPORT_N=$((MISSING_AFTER_EXPORT_N + 1))
    fi
  done < "$target_file"
}

echo "===== MODULE 09C: MATERIALIZE REFERENCE STRUCTURES FROM FOLDSEEK DB ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "FOLDSEEK_BIN=$FOLDSEEK_BIN"
echo "PANEL_TSV=$PANEL_TSV"
echo "PDB_FOLDSEEK_DB=$PDB_DB"
echo "AFSP_FOLDSEEK_DB=$AFSP_DB"
echo "PDB_TARGETS=$PDB_TARGET_N"
echo "AFSP_TARGETS=$AFSP_TARGET_N"
echo "REPORT_TSV=$REPORT_TSV"
echo "SUMMARY_TSV=$SUMMARY_TSV"
echo
echo "--- foldseek commands ---"
echo "foldseek createsubdb --id-mode 1 <target_ids.txt> <DB_PREFIX> <subset_db>"
echo "foldseek convert2pdb <subset_db> <OUT_DIR> --pdb-output-mode 1"
echo

process_group "PDB" "$PDB_DB" "$PDB_TARGET_IDS" "$PDB_OUT_DIR" "pdb"
process_group "AFSP" "$AFSP_DB" "$AFSP_TARGET_IDS" "$AFSP_OUT_DIR" "afsp"

{
  printf "metric\tvalue\n"
  printf "pdb_targets\t%s\n" "$PDB_TARGET_N"
  printf "afsp_targets\t%s\n" "$AFSP_TARGET_N"
  printf "materialized\t%s\n" "$MATERIALIZED_N"
  printf "missing_after_export\t%s\n" "$MISSING_AFTER_EXPORT_N"
  printf "export_failed\t%s\n" "$EXPORT_FAILED_N"
} > "$SUMMARY_TSV"

echo "--- summary ---"
cat "$SUMMARY_TSV"
echo
echo "MODULE09C_MATERIALIZE_REFERENCE_STRUCTURES: OK"
