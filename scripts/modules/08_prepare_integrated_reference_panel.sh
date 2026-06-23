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
SELECTOR="${PROJECT_ROOT}/scripts/modules/08_integrated_reference_panel_selector.py"

PDB_PRIMARY="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_best_hit_rank1_classified.tsv"
PDB_TOP5="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_top5_hits.tsv"
PDB_QTMMAX="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_qtmmax_audit.tsv"
PDB_RANK_AUDIT="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_rank1_vs_qtmmax_audit.tsv"
PDB_NEARTIE="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_neartie_top5_audit.tsv"

AFSP_PRIMARY="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_best_hit_rank1_classified.tsv"
AFSP_TOP5="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_top5_hits.tsv"
AFSP_QTMMAX="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_qtmmax_audit.tsv"
AFSP_RANK_AUDIT="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_rank1_vs_qtmmax_audit.tsv"
AFSP_NEARTIE="${PROJECT_ROOT}/02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_neartie_top5_audit.tsv"

OUT_DIR="${PROJECT_ROOT}/05_reference_panel/${MODE}"
DECISION="${OUT_DIR}/${MODE}_integrated_reference_decision.tsv"
PANEL="${OUT_DIR}/${MODE}_reference_panel_targets.tsv"
MANUAL="${OUT_DIR}/${MODE}_reference_panel_manual_review.tsv"
SUMMARY="${OUT_DIR}/${MODE}_reference_panel_summary.tsv"
POINTER="${OUT_DIR}/${MODE}_reference_panel_pointer.tsv"

fatal() {
  echo "HATA: $*" >&2
  exit 1
}

echo "===== MODULE 08: PREPARE INTEGRATED REFERENCE PANEL ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "EXECUTION_BACKEND=${EXECUTION_BACKEND:-NA}"
echo "PYTHON=$PYTHON"
echo "DATE=$(date)"
echo

case "$OUT_DIR" in
  "$PROJECT_ROOT"/05_reference_panel/*) ;;
  *) fatal "Unsafe OUT_DIR outside PROJECT_ROOT/05_reference_panel: $OUT_DIR" ;;
esac

command -v "$PYTHON" >/dev/null 2>&1 || fatal "PYTHON not found: $PYTHON"
test -s "$SELECTOR" || fatal "M08 selector missing: $SELECTOR"

for f in \
  "$PDB_PRIMARY" "$PDB_TOP5" "$PDB_QTMMAX" "$PDB_RANK_AUDIT" "$PDB_NEARTIE" \
  "$AFSP_PRIMARY" "$AFSP_TOP5" "$AFSP_QTMMAX" "$AFSP_RANK_AUDIT" "$AFSP_NEARTIE"
do
  test -s "$f" || fatal "Required M08 canonical input missing or empty: $f"
done

mkdir -p "$OUT_DIR"

"$PYTHON" "$SELECTOR" \
  "$PDB_PRIMARY" \
  "$PDB_TOP5" \
  "$PDB_QTMMAX" \
  "$PDB_RANK_AUDIT" \
  "$PDB_NEARTIE" \
  "$AFSP_PRIMARY" \
  "$AFSP_TOP5" \
  "$AFSP_QTMMAX" \
  "$AFSP_RANK_AUDIT" \
  "$AFSP_NEARTIE" \
  "$DECISION" \
  "$PANEL" \
  "$MANUAL" \
  "$SUMMARY" \
  "$POINTER"

echo
echo "--- M08 outputs ---"
ls -lh "$DECISION" "$PANEL" "$MANUAL" "$SUMMARY" "$POINTER"

echo
echo "MODULE08_PREPARE_INTEGRATED_REFERENCE_PANEL: OK"
