#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-regression}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="local_wsl"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"
CONFIG="${PROJECT_ROOT}/config/tier1_master_config.env"
source "$CONFIG"

case "$MODE_RAW" in
  smoke) MODE="test" ;;
  pilot32) MODE="regression" ;;
  tier1_full) MODE="full" ;;
  test|regression|full) MODE="$MODE_RAW" ;;
  *)
    echo "HATA: MODE test, regression veya full olmalı."
    exit 1
    ;;
esac

echo "===== MODULE 04: COLLECT COLABFOLD OUTPUTS ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "DATE: $(date)"
echo

RUN_SET_ROOT="${RUN_SET_ROOT:-${PROJECT_ROOT}/run_sets}"
RUN_DIR="${RUN_SET_ROOT}/${MODE}"
IDMAP="${RUN_DIR}/${MODE}_id_map.tsv"
BATCH_MANIFEST="${PROJECT_ROOT}/01_colabfold/batches/${MODE}/${MODE}_colabfold_batch_manifest.tsv"
OUT_ROOT="${PROJECT_ROOT}/01_colabfold/outputs/${MODE}"
QC_DIR="${COLABFOLD_QC_TABLE_ROOT:-${PROJECT_ROOT}/01_colabfold/qc_tables}/${MODE}"

MODEL_SUMMARY="${QC_DIR}/${MODE}_colabfold_model_summary.tsv"
MISSING_TABLE="${QC_DIR}/${MODE}_colabfold_missing_outputs.tsv"
CLASS_SUMMARY="${QC_DIR}/${MODE}_colabfold_confidence_class_summary.tsv"

case "$QC_DIR" in
  "$PROJECT_ROOT"/01_colabfold/qc_tables/*) ;;
  *)
    echo "HATA: Unsafe QC_DIR outside PROJECT_ROOT: $QC_DIR"
    exit 1
    ;;
esac

mkdir -p "$QC_DIR"

test -s "$IDMAP"
test -s "$BATCH_MANIFEST"
test -d "$OUT_ROOT"

"${PYTHON_BIN:-python3}" "${PROJECT_ROOT}/scripts/utils/collect_colabfold_outputs.py" \
  "$MODE" \
  "$IDMAP" \
  "$BATCH_MANIFEST" \
  "$OUT_ROOT" \
  "$MODEL_SUMMARY" \
  "$MISSING_TABLE" \
  "$CLASS_SUMMARY"

echo
echo "--- output tables ---"
ls -lh "$QC_DIR"

echo
echo "--- model summary preview ---"
head -5 "$MODEL_SUMMARY"

echo
echo "--- class summary ---"
cat "$CLASS_SUMMARY"

echo
echo "--- missing outputs ---"
cat "$MISSING_TABLE"

MODEL_N=$(tail -n +2 "$MODEL_SUMMARY" | wc -l)
MISS_N=$(tail -n +2 "$MISSING_TABLE" | wc -l)

echo
echo "model_summary_records=$MODEL_N"
echo "missing_output_records=$MISS_N"

if [ "$MODE" = "regression" ]; then
  if [ "$MODEL_N" -eq 32 ] && [ "$MISS_N" -eq 0 ]; then
    echo "MODULE04_COLABFOLD_COLLECTOR_QC: PASS"
  else
    echo "MODULE04_COLABFOLD_COLLECTOR_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$MISS_N" -eq 0 ]; then
    echo "MODULE04_COLABFOLD_COLLECTOR_QC: PASS"
  else
    echo "MODULE04_COLABFOLD_COLLECTOR_QC: CHECK_NEEDED"
    exit 1
  fi
fi
