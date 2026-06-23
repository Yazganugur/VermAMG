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
cd "$PROJECT_ROOT"

case "$MODE_RAW" in
  smoke|test) MODE="test" ;;
  pilot32|regression) MODE="regression" ;;
  full|tier1_full) MODE="tier1_full" ;;
  *)
    echo "HATA: MODE smoke, test, pilot32, regression, full veya tier1_full olmali. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

PYTHON="${PYTHON_BIN:-python3}"
FOLDSEEK_ROOT="${PROJECT_ROOT}/02_foldseek"
RUN_SET_ROOT="${RUN_SET_ROOT:-${PROJECT_ROOT}/run_sets}"

TABLE_DIR="${FOLDSEEK_ROOT}/tables/${MODE}"
QC_DIR="${FOLDSEEK_ROOT}/qc/${MODE}"
IDMAP="${RUN_SET_ROOT}/${MODE}/${MODE}_id_map.tsv"

PDB_ALL_HITS="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_all_hits.tsv"
AFSP_ALL_HITS="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_all_hits.tsv"

PDB_PRODUCER="${PROJECT_ROOT}/scripts/modules/06b_make_pdb_canonical_besthit_outputs.py"
AFSP_PRODUCER="${PROJECT_ROOT}/scripts/modules/07b_make_afsp_canonical_besthit_outputs.py"

fatal() {
  echo "HATA: $*" >&2
  exit 1
}

require_under_foldseek() {
  local label="$1"
  local path="$2"
  [ -n "$path" ] || fatal "$label is empty"
  case "$path" in
    "$FOLDSEEK_ROOT"/*) ;;
    *) fatal "$label outside FOLDSEEK_ROOT: $path" ;;
  esac
}

echo "===== MODULE 06B/07B: PREPARE FOLDSEEK CANONICAL OUTPUTS ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "EXECUTION_BACKEND=${EXECUTION_BACKEND:-NA}"
echo "PYTHON=$PYTHON"
echo "DATE=$(date)"
echo

require_under_foldseek "TABLE_DIR" "$TABLE_DIR"
require_under_foldseek "QC_DIR" "$QC_DIR"

test -s "$PDB_PRODUCER" || fatal "PDB producer missing: $PDB_PRODUCER"
test -s "$AFSP_PRODUCER" || fatal "AFSP producer missing: $AFSP_PRODUCER"
test -s "$PDB_ALL_HITS" || fatal "PDB all-hits table missing: $PDB_ALL_HITS"
test -s "$AFSP_ALL_HITS" || fatal "AFSP all-hits table missing: $AFSP_ALL_HITS"
test -s "$IDMAP" || fatal "id_map missing: $IDMAP"
command -v "$PYTHON" >/dev/null 2>&1 || fatal "PYTHON not found: $PYTHON"

mkdir -p "$TABLE_DIR" "$QC_DIR"

PDB_PRIMARY_BEST="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_best_hit_rank1.tsv"
PDB_PRIMARY_CLASSIFIED="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_best_hit_rank1_classified.tsv"
PDB_TOP5="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_top5_hits.tsv"
PDB_QTMMAX="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_qtmmax_audit.tsv"
PDB_RANK_AUDIT="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_rank1_vs_qtmmax_audit.tsv"
PDB_NEARTIE="${TABLE_DIR}/${MODE}_vs_pdb_foldseek_neartie_top5_audit.tsv"
PDB_SUMMARY="${QC_DIR}/${MODE}_vs_pdb_foldseek_canonical_summary.tsv"
PDB_POINTER="${QC_DIR}/${MODE}_vs_pdb_foldseek_canonical_pointer.tsv"

AFSP_PRIMARY_BEST="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_best_hit_rank1.tsv"
AFSP_PRIMARY_CLASSIFIED="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_best_hit_rank1_classified.tsv"
AFSP_TOP5="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_top5_hits.tsv"
AFSP_QTMMAX="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_qtmmax_audit.tsv"
AFSP_RANK_AUDIT="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_rank1_vs_qtmmax_audit.tsv"
AFSP_NEARTIE="${TABLE_DIR}/${MODE}_vs_afsp_foldseek_neartie_top5_audit.tsv"
AFSP_SUMMARY="${QC_DIR}/${MODE}_vs_afsp_foldseek_canonical_summary.tsv"
AFSP_POINTER="${QC_DIR}/${MODE}_vs_afsp_foldseek_canonical_pointer.tsv"

echo "--- PDB canonical producer ---"
"$PYTHON" "$PDB_PRODUCER" \
  "$PDB_ALL_HITS" \
  "$IDMAP" \
  "$PDB_PRIMARY_BEST" \
  "$PDB_PRIMARY_CLASSIFIED" \
  "$PDB_TOP5" \
  "$PDB_QTMMAX" \
  "$PDB_RANK_AUDIT" \
  "$PDB_NEARTIE" \
  "$PDB_SUMMARY" \
  "$PDB_POINTER"

echo
echo "--- AFSP canonical producer ---"
"$PYTHON" "$AFSP_PRODUCER" \
  "$AFSP_ALL_HITS" \
  "$IDMAP" \
  "$AFSP_PRIMARY_BEST" \
  "$AFSP_PRIMARY_CLASSIFIED" \
  "$AFSP_TOP5" \
  "$AFSP_QTMMAX" \
  "$AFSP_RANK_AUDIT" \
  "$AFSP_NEARTIE" \
  "$AFSP_SUMMARY" \
  "$AFSP_POINTER"

echo
echo "--- canonical outputs ---"
ls -lh \
  "$PDB_PRIMARY_BEST" "$PDB_PRIMARY_CLASSIFIED" "$PDB_TOP5" "$PDB_QTMMAX" "$PDB_RANK_AUDIT" "$PDB_NEARTIE" "$PDB_SUMMARY" "$PDB_POINTER" \
  "$AFSP_PRIMARY_BEST" "$AFSP_PRIMARY_CLASSIFIED" "$AFSP_TOP5" "$AFSP_QTMMAX" "$AFSP_RANK_AUDIT" "$AFSP_NEARTIE" "$AFSP_SUMMARY" "$AFSP_POINTER"

echo
echo "MODULE06B07B_PREPARE_FOLDSEEK_CANONICAL_OUTPUTS: OK"
