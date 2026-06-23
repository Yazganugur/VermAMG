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

PYTHON="${PYTHON_BIN:-python3}"

QUERY_MANIFEST="${PROJECT_ROOT}/02_foldseek/query_pdb_manifest/${MODE}_query_pdb_manifest.tsv"
M08_DECISION="${PROJECT_ROOT}/05_reference_panel/${MODE}/${MODE}_integrated_reference_decision.tsv"
M08_PANEL="${PROJECT_ROOT}/05_reference_panel/${MODE}/${MODE}_reference_panel_targets.tsv"

OUT_ROOT="${PROJECT_ROOT}/04_p2rank/${MODE}"
INPUT_DIR="${OUT_ROOT}/input_manifests"
QC_DIR="${OUT_ROOT}/qc"
RESOLUTION_DIR="${OUT_ROOT}/reference_resolution"

REF_ROOT_QUERYDB="${PROJECT_ROOT}/02_foldseek/querydb/${MODE}/pdb_inputs"
REF_ROOT_COLABFOLD="${PROJECT_ROOT}/01_colabfold/outputs/${MODE}"
REF_ROOT_PDB_DB="${PROJECT_ROOT}/resources/databases/foldseek/pdb"
REF_ROOT_AFSP_DB="${PROJECT_ROOT}/resources/databases/foldseek/alphafold_swissprot"
REF_ROOT_MATERIALIZED_PDB="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_structures/materialized/pdb"
REF_ROOT_MATERIALIZED_AFSP="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_structures/materialized/afsp"

MANDATORY_REF_RESOLVE_ROOTS=(
  "$REF_ROOT_QUERYDB"
  "$REF_ROOT_COLABFOLD"
  "$REF_ROOT_PDB_DB"
  "$REF_ROOT_AFSP_DB"
)
OPTIONAL_REF_RESOLVE_ROOTS=(
  "$REF_ROOT_MATERIALIZED_PDB"
  "$REF_ROOT_MATERIALIZED_AFSP"
)
REF_RESOLVE_ROOTS=("${MANDATORY_REF_RESOLVE_ROOTS[@]}")

case "$OUT_ROOT" in
  "${PROJECT_ROOT}/04_p2rank/"*) ;;
  *)
    echo "ERROR: refusing to write outside PROJECT_ROOT/04_p2rank: $OUT_ROOT"
    exit 1
    ;;
esac

for input in "$QUERY_MANIFEST" "$M08_DECISION" "$M08_PANEL"; do
  if [ ! -s "$input" ]; then
    echo "ERROR: required input missing or empty: $input"
    exit 1
  fi
done

for root in "${MANDATORY_REF_RESOLVE_ROOTS[@]}" "${OPTIONAL_REF_RESOLVE_ROOTS[@]}"; do
  case "$root" in
    "${PROJECT_ROOT}/"*) ;;
    *)
      echo "ERROR: refusing reference resolve root outside PROJECT_ROOT: $root"
      exit 1
      ;;
  esac
done

for root in "${OPTIONAL_REF_RESOLVE_ROOTS[@]}"; do
  if [ -d "$root" ]; then
    REF_RESOLVE_ROOTS+=("$root")
  fi
done

mkdir -p "$INPUT_DIR" "$QC_DIR" "$RESOLUTION_DIR"

QUERY_OUT="${INPUT_DIR}/${MODE}_p2rank_query_model_manifest.tsv"
REF_PANEL_OUT="${INPUT_DIR}/${MODE}_p2rank_reference_panel_manifest.tsv"
PREP_RESOLUTION_REPORT="${RESOLUTION_DIR}/${MODE}_reference_panel_file_resolution_pending.tsv"
PREP_SUMMARY="${QC_DIR}/${MODE}_p2rank_input_manifest_summary.tsv"
PREP_POINTER="${QC_DIR}/${MODE}_p2rank_input_manifest_pointer.tsv"

RESOLVED_MANIFEST="${INPUT_DIR}/${MODE}_p2rank_reference_panel_manifest_resolved.tsv"
UNIQUE_REF_MANIFEST="${INPUT_DIR}/${MODE}_p2rank_reference_unique_structure_manifest.tsv"
RESOLUTION_REPORT="${RESOLUTION_DIR}/${MODE}_reference_panel_file_resolution_report.tsv"
RESOLUTION_SUMMARY="${RESOLUTION_DIR}/${MODE}_reference_panel_file_resolution_summary.tsv"
RESOLUTION_POINTER="${QC_DIR}/${MODE}_reference_panel_file_resolution_pointer.tsv"

echo "===== MODULE 09: PREPARE P2RANK INPUT MANIFESTS ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "PYTHON=$PYTHON"
echo
echo "--- inputs ---"
echo "QUERY_MANIFEST=$QUERY_MANIFEST"
echo "M08_DECISION=$M08_DECISION"
echo "M08_PANEL=$M08_PANEL"
echo
echo "--- outputs ---"
echo "QUERY_OUT=$QUERY_OUT"
echo "REF_PANEL_OUT=$REF_PANEL_OUT"
echo "RESOLVED_MANIFEST=$RESOLVED_MANIFEST"
echo "UNIQUE_REF_MANIFEST=$UNIQUE_REF_MANIFEST"
echo "RESOLUTION_SUMMARY=$RESOLUTION_SUMMARY"
echo
echo "--- reference resolve roots ---"
for root in "${MANDATORY_REF_RESOLVE_ROOTS[@]}" "${OPTIONAL_REF_RESOLVE_ROOTS[@]}"; do
  if [ -d "$root" ]; then
    echo "PRESENT $root"
  elif [ "$root" = "$REF_ROOT_MATERIALIZED_PDB" ] || [ "$root" = "$REF_ROOT_MATERIALIZED_AFSP" ]; then
    echo "MISSING_OPTIONAL $root"
  else
    echo "MISSING $root"
  fi
done
echo

"$PYTHON" "${PROJECT_ROOT}/scripts/modules/09_prepare_p2rank_input_manifests.py" \
  "$QUERY_MANIFEST" \
  "$M08_DECISION" \
  "$M08_PANEL" \
  "$QUERY_OUT" \
  "$REF_PANEL_OUT" \
  "$PREP_RESOLUTION_REPORT" \
  "$PREP_SUMMARY" \
  "$PREP_POINTER"

"$PYTHON" "${PROJECT_ROOT}/scripts/modules/09b_resolve_reference_panel_files.py" \
  "$M08_PANEL" \
  "$REF_PANEL_OUT" \
  "$RESOLVED_MANIFEST" \
  "$UNIQUE_REF_MANIFEST" \
  "$RESOLUTION_REPORT" \
  "$RESOLUTION_SUMMARY" \
  "$RESOLUTION_POINTER" \
  "${REF_RESOLVE_ROOTS[@]}"

echo
echo "MODULE09_PREPARE_P2RANK_INPUT_MANIFESTS_WRAPPER: OK"
