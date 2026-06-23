#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-regression}"
PROJECT_ROOT="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
cd "$PROJECT_ROOT"

echo "===== PIPELINE CONTRACT QC — COLABFOLD LAYER ====="
echo "MODE=$MODE"
echo "DATE=$(date)"
echo

REQUIRED_FILES=(
  "run_sets/${MODE}/${MODE}_id_map.tsv"
  "01_colabfold/batches/${MODE}/${MODE}_colabfold_batch_manifest.tsv"
  "01_colabfold/${MODE}_colabfold_run_manifest.tsv"
  "01_colabfold/qc_tables/${MODE}/${MODE}_colabfold_model_summary.tsv"
  "01_colabfold/qc_tables/${MODE}/${MODE}_colabfold_missing_outputs.tsv"
  "01_colabfold/qc_tables/${MODE}/${MODE}_colabfold_confidence_class_summary.tsv"
)

FAIL=0

echo "===== REQUIRED FILES ====="
for f in "${REQUIRED_FILES[@]}"; do
  if [ -s "$f" ]; then
    echo -e "OK\t$f"
  else
    echo -e "MISSING_OR_EMPTY\t$f"
    FAIL=1
  fi
done

echo
echo "===== RECORD COUNTS ====="
for f in "${REQUIRED_FILES[@]}"; do
  if [ -s "$f" ]; then
    n=$(( $(wc -l < "$f") - 1 ))
    echo -e "$(basename "$f")\t$n"
  fi
done

echo
echo "===== COLABFOLD TABLE QC ====="
"${PYTHON_BIN:-python3}" scripts/qc/qc_colabfold_tables.py

if [ "$FAIL" -eq 0 ]; then
  echo
  echo "COLABFOLD_CONTRACT_QC: PASS"
else
  echo
  echo "COLABFOLD_CONTRACT_QC: FAIL"
  exit 1
fi
