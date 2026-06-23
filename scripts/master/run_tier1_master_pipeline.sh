#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-regression}"

# VermAMG portable bootstrap
# Default profile is TRUBA because this validated workflow currently runs on TRUBA.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="truba"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="$VERMAMG_ROOT"
cd "$PROJECT_ROOT"

CONFIG_FILE="${AUTO_ROOT}/config/tier1_master_config.env"
if [[ -f "$CONFIG_FILE" ]]; then
  source "$CONFIG_FILE"
else
  echo "WARN: config file not found: $CONFIG_FILE"
fi

case "$MODE_RAW" in
  smoke|test) MODE="test" ;;
  regression|pilot32) MODE="regression" ;;
  tier1_full|full) MODE="full" ;;
  *)
    echo "HATA: MODE test/regression/full olmalı. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

# Optional second argument: RUN_LABEL isolates downstream results per run.
# If omitted, falls back to MODE — fully backward compatible.
RUN_LABEL_RAW="${2:-}"
RUN_LABEL="${RUN_LABEL_RAW:-${MODE}}"
RESULTS_BASE="results/${RUN_LABEL}"

echo "===== BAPS FAZ C v2 — BÖLÜM 9 MASTER PIPELINE ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "RUN_LABEL: $RUN_LABEL"
echo "RESULTS_BASE: $RESULTS_BASE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "DATE: $(date)"
echo "HOST: $(hostname)"

echo

echo
echo "===== RESOURCE MANIFEST QC ====="
RESOURCE_MANIFEST="config/resource_manifest.tsv"
RESOURCE_QC_SCRIPT="scripts/qc/qc_resource_manifest.sh"
RESOURCE_QC_REPORT="${RESULTS_BASE}/qc/resource_manifest_qc_report.tsv"
RESOURCE_QC_SUMMARY="${RESULTS_BASE}/qc/resource_manifest_qc_summary.tsv"

if [ -x "$RESOURCE_QC_SCRIPT" ]; then
  bash "$RESOURCE_QC_SCRIPT" "$VERMAMG_PROFILE" "$MODE" "$RESOURCE_MANIFEST" "$RESOURCE_QC_REPORT" "$RESOURCE_QC_SUMMARY"
  echo "RESOURCE_MANIFEST=$RESOURCE_MANIFEST"
  echo "RESOURCE_QC_REPORT=$RESOURCE_QC_REPORT"
  echo "RESOURCE_QC_SUMMARY=$RESOURCE_QC_SUMMARY"
  awk -F'\t' '$1=="fail_n"{print "RESOURCE_QC_FAIL_N="$2}' "$RESOURCE_QC_SUMMARY"
  awk -F'\t' '$1=="warn_n"{print "RESOURCE_QC_WARN_N="$2}' "$RESOURCE_QC_SUMMARY"
  awk -F'\t' '$1=="pass_n"{print "RESOURCE_QC_PASS_N="$2}' "$RESOURCE_QC_SUMMARY"
else
  echo "HATA: Resource QC script missing or not executable: $RESOURCE_QC_SCRIPT"
  exit 1
fi


echo "===== MODULE 00: INPUT QC ====="
bash scripts/modules/00_input_qc.sh "$MODE"

echo
echo "===== MODULE 01: PREPARE RUN SET ====="
bash scripts/modules/01_prepare_run_set.sh "$MODE"

echo
echo "===== MODULE 02-04: COLABFOLD LAYER ====="
echo "Bu runner şu an ColabFold job submit/collect işlemlerini ayrı adımlarda yapılmış kabul eder."
echo "Beklenen canonical ColabFold summary:"
echo "01_colabfold/qc_tables/${MODE}/${MODE}_colabfold_model_summary.tsv"

echo
echo "===== MODULE 05: FOLDSEEK QUERY PDB MANIFEST ====="
if [ -x scripts/modules/05_prepare_foldseek_inputs.sh ]; then
  bash scripts/modules/05_prepare_foldseek_inputs.sh "$MODE"
else
  echo "UYARI: scripts/modules/05_prepare_foldseek_inputs.sh bulunamadı; mevcut manifest kullanılacak."
fi

echo
echo "===== MODULE 06: PDB FOLDSEEK CANONICAL OUTPUT CHECK ====="
PDB_PRIMARY="02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_best_hit_rank1_classified.tsv"
PDB_TOP5="02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_top5_hits.tsv"

if [ "$MODE" = "regression" ]; then
  PDB_PRIMARY="02_foldseek/tables/regression/regression_vs_pdb_foldseek_best_hit_rank1_classified.tsv"
  PDB_TOP5="02_foldseek/tables/regression/regression_vs_pdb_foldseek_top5_hits.tsv"
fi

test -s "$PDB_PRIMARY"
test -s "$PDB_TOP5"
echo "PDB_PRIMARY=$PDB_PRIMARY"
echo "PDB_TOP5=$PDB_TOP5"
echo -n "PDB primary records: "
tail -n +2 "$PDB_PRIMARY" | wc -l
echo -n "PDB top5 records: "
tail -n +2 "$PDB_TOP5" | wc -l

echo
echo "===== MODULE 07: AFSP FOLDSEEK CANONICAL OUTPUT CHECK ====="
AFSP_PRIMARY="02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_best_hit_rank1_classified.tsv"
AFSP_TOP5="02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_top5_hits.tsv"

if [ "$MODE" = "regression" ]; then
  AFSP_PRIMARY="02_foldseek/tables/regression/regression_vs_afsp_foldseek_best_hit_rank1_classified.tsv"
  AFSP_TOP5="02_foldseek/tables/regression/regression_vs_afsp_foldseek_top5_hits.tsv"
fi

test -s "$AFSP_PRIMARY"
test -s "$AFSP_TOP5"
echo "AFSP_PRIMARY=$AFSP_PRIMARY"
echo "AFSP_TOP5=$AFSP_TOP5"
echo -n "AFSP primary records: "
tail -n +2 "$AFSP_PRIMARY" | wc -l
echo -n "AFSP top5 records: "
tail -n +2 "$AFSP_TOP5" | wc -l

echo
echo "===== ARTIFACT REGISTRY CHECK ====="
REGISTRY="pipeline_state/artifacts/pipeline_artifact_registry.tsv"
test -s "$REGISTRY"
awk -F'\t' 'NR==1 || $2 ~ /^M06/ || $2 ~ /^M07/' "$REGISTRY" | column -t -s $'\t'

echo
echo "===== MASTER PIPELINE STATUS ====="
echo "M06/M07 canonical Foldseek artifacts are registered and available."

echo
echo "===== MODULE 08: INTEGRATED PDB+AFSP REFERENCE PANEL CHECK ====="

M08_DECISION="05_reference_panel/${MODE}/${MODE}_integrated_reference_decision.tsv"
M08_PANEL="05_reference_panel/${MODE}/${MODE}_reference_panel_targets.tsv"
M08_MANUAL="05_reference_panel/${MODE}/${MODE}_reference_panel_manual_review.tsv"
M08_SUMMARY="05_reference_panel/${MODE}/${MODE}_reference_panel_summary.tsv"

if [ "$MODE" = "regression" ]; then
  M08_DECISION="05_reference_panel/regression/regression_integrated_reference_decision.tsv"
  M08_PANEL="05_reference_panel/regression/regression_reference_panel_targets.tsv"
  M08_MANUAL="05_reference_panel/regression/regression_reference_panel_manual_review.tsv"
  M08_SUMMARY="05_reference_panel/regression/regression_reference_panel_summary.tsv"
fi

test -s "$M08_DECISION"
test -s "$M08_PANEL"
test -s "$M08_MANUAL"
test -s "$M08_SUMMARY"

echo "M08_DECISION=$M08_DECISION"
echo "M08_PANEL=$M08_PANEL"
echo "M08_MANUAL=$M08_MANUAL"
echo "M08_SUMMARY=$M08_SUMMARY"

echo -n "M08 decision records: "
tail -n +2 "$M08_DECISION" | wc -l

echo -n "M08 panel records: "
tail -n +2 "$M08_PANEL" | wc -l

echo -n "M08 manual review records: "
tail -n +2 "$M08_MANUAL" | wc -l

echo "--- M08 summary ---"
cat "$M08_SUMMARY"



echo
echo "===== MODULE 09: P2RANK INPUT + REFERENCE CACHE RESOLUTION CHECK ====="

M09_QUERY_MANIFEST="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_query_model_manifest.tsv"
M09_REF_PANEL_MANIFEST="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_reference_panel_manifest.tsv"
M09_REF_RESOLVED="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_reference_panel_manifest_resolved.tsv"
M09_REF_UNIQUE="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_reference_unique_structure_manifest.tsv"
M09_RESOLUTION_SUMMARY="04_p2rank/${MODE}/reference_resolution/${MODE}_reference_panel_file_resolution_summary.tsv"

if [ "$MODE" = "regression" ]; then
  M09_QUERY_MANIFEST="04_p2rank/regression/input_manifests/regression_p2rank_query_model_manifest.tsv"
  M09_REF_PANEL_MANIFEST="04_p2rank/regression/input_manifests/regression_p2rank_reference_panel_manifest.tsv"
  M09_REF_RESOLVED="04_p2rank/regression/input_manifests/regression_p2rank_reference_panel_manifest_resolved.tsv"
  M09_REF_UNIQUE="04_p2rank/regression/input_manifests/regression_p2rank_reference_unique_structure_manifest.tsv"
  M09_RESOLUTION_SUMMARY="04_p2rank/regression/reference_resolution/regression_reference_panel_file_resolution_summary.tsv"
fi

test -s "$M09_QUERY_MANIFEST"
test -s "$M09_REF_PANEL_MANIFEST"
test -s "$M09_REF_RESOLVED"
test -s "$M09_REF_UNIQUE"
test -s "$M09_RESOLUTION_SUMMARY"

echo "M09_QUERY_MANIFEST=$M09_QUERY_MANIFEST"
echo "M09_REF_PANEL_MANIFEST=$M09_REF_PANEL_MANIFEST"
echo "M09_REF_RESOLVED=$M09_REF_RESOLVED"
echo "M09_REF_UNIQUE=$M09_REF_UNIQUE"
echo "M09_RESOLUTION_SUMMARY=$M09_RESOLUTION_SUMMARY"

M09_QUERY_N=$(tail -n +2 "$M09_QUERY_MANIFEST" | wc -l)
M09_QUERY_EXIST_N=$(awk -F'\t' 'NR>1 && $6=="YES"{c++} END{print c+0}' "$M09_QUERY_MANIFEST")
M09_REF_PANEL_N=$(tail -n +2 "$M09_REF_PANEL_MANIFEST" | wc -l)
M09_REF_RESOLVED_N=$(awk -F'\t' 'NR>1 && $12=="YES"{c++} END{print c+0}' "$M09_REF_RESOLVED")
M09_REF_CACHE_MISSING_N=$(awk -F'\t' 'NR>1 && $12!="YES"{c++} END{print c+0}' "$M09_REF_RESOLVED")
M09_REF_UNIQUE_N=$(tail -n +2 "$M09_REF_UNIQUE" | wc -l)

echo "M09_QUERY_N=$M09_QUERY_N"
echo "M09_QUERY_EXIST_N=$M09_QUERY_EXIST_N"
echo "M09_REF_PANEL_N=$M09_REF_PANEL_N"
echo "M09_REF_RESOLVED_N=$M09_REF_RESOLVED_N"
echo "M09_REF_CACHE_MISSING_N=$M09_REF_CACHE_MISSING_N"
echo "M09_REF_UNIQUE_N=$M09_REF_UNIQUE_N"

echo "--- M09B resolution summary ---"
cat "$M09_RESOLUTION_SUMMARY"

echo
echo "===== MODULE 09 DUPLICATE PANEL QC ====="
"${PYTHON_BIN:-python3}" - "$M09_REF_RESOLVED" <<'PYQC'
import csv
import sys
from pathlib import Path
from collections import Counter

path = Path(sys.argv[1])
rows = list(csv.DictReader(path.open(), delimiter="\t"))

c = Counter((r["query"], r["reference_layer"], r["target"]) for r in rows)
dups = [(k,v) for k,v in c.items() if v > 1]

print("panel_rows:", len(rows))
print("duplicate_query_layer_target_n:", len(dups))

if dups:
    print("DUPLICATE_EXAMPLES:")
    for (q, layer, target), n in dups[:20]:
        print(q, layer, target, n)
    raise SystemExit(1)

print("M09_REFERENCE_PANEL_DUPLICATE_QC: PASS")
PYQC

if [ "$MODE" = "regression" ]; then
  if [ "$M09_QUERY_N" -eq 32 ] && [ "$M09_QUERY_EXIST_N" -eq 32 ] && [ "$M09_REF_PANEL_N" -eq 160 ]; then
    echo "M09_INPUT_AND_REFERENCE_CACHE_QC: PASS_WITH_CACHE_MISSING_REPORT"
  else
    echo "M09_INPUT_AND_REFERENCE_CACHE_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$M09_QUERY_N" -gt 0 ] && [ "$M09_QUERY_EXIST_N" -gt 0 ] && [ "$M09_REF_PANEL_N" -gt 0 ]; then
    echo "M09_INPUT_AND_REFERENCE_CACHE_QC: PASS_WITH_CACHE_MISSING_REPORT"
  else
    echo "M09_INPUT_AND_REFERENCE_CACHE_QC: CHECK_NEEDED"
    exit 1
  fi
fi



echo
echo
echo "===== MODULE 09D-PREP: P2RANK QUERY + REFERENCE SBATCH GENERATOR ====="
if [ -x scripts/modules/09d_prepare_p2rank_query_and_reference_sbatch.sh ]; then
  bash scripts/modules/09d_prepare_p2rank_query_and_reference_sbatch.sh "$MODE"
else
  echo "UYARI: scripts/modules/09d_prepare_p2rank_query_and_reference_sbatch.sh bulunamadı; mevcut P2Rank sbatch dosyaları kullanılacak."
fi

echo "===== MODULE 09D/09E: QUERY-MODEL P2RANK RUN + MERGE CHECK ====="

M09D_RUN_MANIFEST="04_p2rank/${MODE}/query_models/all/query_p2rank_run_manifest.tsv"
M09D_FAIL_LIST="04_p2rank/${MODE}/query_models/all/query_p2rank_failed.tsv"
M09D_POCKET_COUNTS="04_p2rank/${MODE}/qc/${MODE}_p2rank_query_all32_pocket_counts.tsv"
M09D_QC_REPORT="04_p2rank/${MODE}/qc/${MODE}_p2rank_query_all32_qc_report.tsv"

M09E_PRED_MERGED="04_p2rank/${MODE}/query_models/merged_tables/${MODE}_query_p2rank_predictions_merged.tsv"
M09E_RES_MERGED="04_p2rank/${MODE}/query_models/merged_tables/${MODE}_query_p2rank_residues_merged.tsv"
M09E_TOP1="04_p2rank/${MODE}/query_models/merged_tables/${MODE}_query_p2rank_top1_pockets.tsv"
M09E_FAMILY="04_p2rank/${MODE}/query_models/merged_tables/${MODE}_query_p2rank_family_summary.tsv"
M09E_QC_REPORT="04_p2rank/${MODE}/qc/${MODE}_query_p2rank_merge_qc_report.tsv"

if [ "$MODE" = "regression" ]; then
  M09D_RUN_MANIFEST="04_p2rank/regression/query_models/all/query_p2rank_run_manifest.tsv"
  M09D_FAIL_LIST="04_p2rank/regression/query_models/all/query_p2rank_failed.tsv"
  M09D_POCKET_COUNTS="04_p2rank/regression/qc/regression_p2rank_query_all32_pocket_counts.tsv"
  M09D_QC_REPORT="04_p2rank/regression/qc/regression_p2rank_query_all32_qc_report.tsv"

  M09E_PRED_MERGED="04_p2rank/regression/query_models/merged_tables/regression_query_p2rank_predictions_merged.tsv"
  M09E_RES_MERGED="04_p2rank/regression/query_models/merged_tables/regression_query_p2rank_residues_merged.tsv"
  M09E_TOP1="04_p2rank/regression/query_models/merged_tables/regression_query_p2rank_top1_pockets.tsv"
  M09E_FAMILY="04_p2rank/regression/query_models/merged_tables/regression_query_p2rank_family_summary.tsv"
  M09E_QC_REPORT="04_p2rank/regression/qc/regression_query_p2rank_merge_qc_report.tsv"
fi

if [ "$MODE" = "regression" ]; then
  for f in \
    "$M09D_RUN_MANIFEST" "$M09D_FAIL_LIST" "$M09D_POCKET_COUNTS" \
    "$M09E_PRED_MERGED" "$M09E_RES_MERGED" "$M09E_TOP1" "$M09E_FAMILY" "$M09E_QC_REPORT"
  do
    test -s "$f"
  done
else
  for f in \
    "$M09D_RUN_MANIFEST" "$M09D_FAIL_LIST" \
    "$M09E_PRED_MERGED" "$M09E_RES_MERGED" "$M09E_TOP1" "$M09E_FAMILY" "$M09E_QC_REPORT"
  do
    test -s "$f"
  done
fi

echo "M09D_RUN_MANIFEST=$M09D_RUN_MANIFEST"
echo "M09D_FAIL_LIST=$M09D_FAIL_LIST"
echo "M09D_POCKET_COUNTS=$M09D_POCKET_COUNTS"
echo "M09E_PRED_MERGED=$M09E_PRED_MERGED"
echo "M09E_RES_MERGED=$M09E_RES_MERGED"
echo "M09E_TOP1=$M09E_TOP1"
echo "M09E_FAMILY=$M09E_FAMILY"
echo "M09E_QC_REPORT=$M09E_QC_REPORT"

M09D_RUN_N=$(tail -n +2 "$M09D_RUN_MANIFEST" | wc -l)
M09D_OK_N=$(awk -F'\t' 'NR>1 && $5=="OK"{c++} END{print c+0}' "$M09D_RUN_MANIFEST")
M09D_FAIL_N=$(tail -n +2 "$M09D_FAIL_LIST" | wc -l)
if [ "$MODE" = "regression" ] && [ -s "$M09D_POCKET_COUNTS" ]; then
  M09D_ZERO_POCKET_N=$(awk -F'\t' 'NR>1 && $6==0{c++} END{print c+0}' "$M09D_POCKET_COUNTS")
else
  M09D_ZERO_POCKET_N=0
fi

M09E_PRED_ROWS=$(tail -n +2 "$M09E_PRED_MERGED" | wc -l)
M09E_RES_ROWS=$(tail -n +2 "$M09E_RES_MERGED" | wc -l)
M09E_TOP1_N=$(tail -n +2 "$M09E_TOP1" | wc -l)
M09E_FAMILY_N=$(tail -n +2 "$M09E_FAMILY" | wc -l)

echo "M09D_RUN_N=$M09D_RUN_N"
echo "M09D_OK_N=$M09D_OK_N"
echo "M09D_FAIL_N=$M09D_FAIL_N"
echo "M09D_ZERO_POCKET_N=$M09D_ZERO_POCKET_N"
echo "M09E_PRED_ROWS=$M09E_PRED_ROWS"
echo "M09E_RES_ROWS=$M09E_RES_ROWS"
echo "M09E_TOP1_N=$M09E_TOP1_N"
echo "M09E_FAMILY_N=$M09E_FAMILY_N"

echo "--- M09E merge QC report ---"
cat "$M09E_QC_REPORT"

echo "--- M09E family summary ---"
cat "$M09E_FAMILY" | column -t -s $'\t'

if [ "$MODE" = "regression" ]; then
  if [ "$M09D_RUN_N" -eq 32 ] && [ "$M09D_OK_N" -eq 32 ] && [ "$M09D_FAIL_N" -eq 0 ] && [ "$M09D_ZERO_POCKET_N" -eq 0 ] && [ "$M09E_TOP1_N" -eq 32 ] && [ "$M09E_PRED_ROWS" -gt 32 ] && [ "$M09E_RES_ROWS" -gt 1000 ]; then
    echo "M09D_M09E_QUERY_P2RANK_MASTER_QC: PASS"
  else
    echo "M09D_M09E_QUERY_P2RANK_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$M09D_FAIL_N" -eq 0 ] && [ "$M09E_TOP1_N" -gt 0 ] && [ "$M09E_PRED_ROWS" -gt 0 ]; then
    echo "M09D_M09E_QUERY_P2RANK_MASTER_QC: PASS"
  else
    echo "M09D_M09E_QUERY_P2RANK_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
fi



echo
echo "===== MODULE 09F/09G: REFERENCE-PANEL P2RANK RUN + MERGE CHECK ====="

M09F_RUN_MANIFEST="04_p2rank/${MODE}/reference_models/resolved_unique/reference_p2rank_run_manifest.tsv"
M09F_FAIL_LIST="04_p2rank/${MODE}/reference_models/resolved_unique/reference_p2rank_failed.tsv"
M09F_POCKET_COUNTS="04_p2rank/${MODE}/qc/${MODE}_p2rank_reference_resolved_unique_pocket_counts.tsv"
M09F_ZERO_REPORT="04_p2rank/${MODE}/qc/${MODE}_p2rank_reference_zero_pocket_report.tsv"
M09F_QC_REPORT="04_p2rank/${MODE}/qc/${MODE}_p2rank_reference_resolved_unique_qc_report.tsv"

M09G_PRED_MERGED="04_p2rank/${MODE}/reference_models/merged_tables/${MODE}_reference_p2rank_predictions_merged.tsv"
M09G_RES_MERGED="04_p2rank/${MODE}/reference_models/merged_tables/${MODE}_reference_p2rank_residues_merged.tsv"
M09G_TOP1="04_p2rank/${MODE}/reference_models/merged_tables/${MODE}_reference_p2rank_top1_pockets.tsv"
M09G_LAYER="04_p2rank/${MODE}/reference_models/merged_tables/${MODE}_reference_p2rank_layer_summary.tsv"
M09G_QC_REPORT="04_p2rank/${MODE}/qc/${MODE}_reference_p2rank_merge_qc_report.tsv"

if [ "$MODE" = "regression" ]; then
  M09F_RUN_MANIFEST="04_p2rank/regression/reference_models/resolved_unique/reference_p2rank_run_manifest.tsv"
  M09F_FAIL_LIST="04_p2rank/regression/reference_models/resolved_unique/reference_p2rank_failed.tsv"
  M09F_POCKET_COUNTS="04_p2rank/regression/qc/regression_p2rank_reference_resolved_unique_pocket_counts.tsv"
  M09F_ZERO_REPORT="04_p2rank/regression/qc/regression_p2rank_reference_zero_pocket_report.tsv"
  M09F_QC_REPORT="04_p2rank/regression/qc/regression_p2rank_reference_resolved_unique_qc_report.tsv"

  M09G_PRED_MERGED="04_p2rank/regression/reference_models/merged_tables/regression_reference_p2rank_predictions_merged.tsv"
  M09G_RES_MERGED="04_p2rank/regression/reference_models/merged_tables/regression_reference_p2rank_residues_merged.tsv"
  M09G_TOP1="04_p2rank/regression/reference_models/merged_tables/regression_reference_p2rank_top1_pockets.tsv"
  M09G_LAYER="04_p2rank/regression/reference_models/merged_tables/regression_reference_p2rank_layer_summary.tsv"
  M09G_QC_REPORT="04_p2rank/regression/qc/regression_reference_p2rank_merge_qc_report.tsv"
fi

if [ "$MODE" = "regression" ]; then
  for f in \
    "$M09F_RUN_MANIFEST" "$M09F_FAIL_LIST" "$M09F_POCKET_COUNTS" "$M09F_ZERO_REPORT" "$M09F_QC_REPORT" \
    "$M09G_PRED_MERGED" "$M09G_RES_MERGED" "$M09G_TOP1" "$M09G_LAYER" "$M09G_QC_REPORT"
  do
    test -s "$f"
  done
else
  for f in \
    "$M09F_RUN_MANIFEST" "$M09F_FAIL_LIST" "$M09F_POCKET_COUNTS" \
    "$M09G_PRED_MERGED" "$M09G_RES_MERGED" "$M09G_TOP1" "$M09G_LAYER" "$M09G_QC_REPORT"
  do
    test -s "$f"
  done
fi

echo "M09F_RUN_MANIFEST=$M09F_RUN_MANIFEST"
echo "M09F_FAIL_LIST=$M09F_FAIL_LIST"
echo "M09F_POCKET_COUNTS=$M09F_POCKET_COUNTS"
echo "M09F_ZERO_REPORT=$M09F_ZERO_REPORT"
echo "M09F_QC_REPORT=$M09F_QC_REPORT"
echo "M09G_PRED_MERGED=$M09G_PRED_MERGED"
echo "M09G_RES_MERGED=$M09G_RES_MERGED"
echo "M09G_TOP1=$M09G_TOP1"
echo "M09G_LAYER=$M09G_LAYER"
echo "M09G_QC_REPORT=$M09G_QC_REPORT"

M09F_RUN_N=$(tail -n +2 "$M09F_RUN_MANIFEST" | wc -l)
M09F_OK_N=$(awk -F'\t' 'NR>1 && $6=="OK"{c++} END{print c+0}' "$M09F_RUN_MANIFEST")
M09F_NO_POCKET_N=$(awk -F'\t' 'NR>1 && $6=="NO_POCKETS_OR_EMPTY_OUTPUT"{c++} END{print c+0}' "$M09F_RUN_MANIFEST")
M09F_FAIL_N=$(tail -n +2 "$M09F_FAIL_LIST" | wc -l)
if [ -s "$M09F_ZERO_REPORT" ]; then
  M09F_ZERO_REPORT_N=$(tail -n +2 "$M09F_ZERO_REPORT" | wc -l)
else
  M09F_ZERO_REPORT_N=0
fi

M09G_PRED_ROWS=$(tail -n +2 "$M09G_PRED_MERGED" | wc -l)
M09G_RES_ROWS=$(tail -n +2 "$M09G_RES_MERGED" | wc -l)
M09G_TOP1_N=$(tail -n +2 "$M09G_TOP1" | wc -l)
M09G_LAYER_N=$(tail -n +2 "$M09G_LAYER" | wc -l)
M09G_ZERO_N=$(awk -F'\t' 'NR>1 && $19=="YES"{c++} END{print c+0}' "$M09G_TOP1")

echo "M09F_RUN_N=$M09F_RUN_N"
echo "M09F_OK_N=$M09F_OK_N"
echo "M09F_NO_POCKET_N=$M09F_NO_POCKET_N"
echo "M09F_FAIL_N=$M09F_FAIL_N"
echo "M09F_ZERO_REPORT_N=$M09F_ZERO_REPORT_N"
echo "M09G_PRED_ROWS=$M09G_PRED_ROWS"
echo "M09G_RES_ROWS=$M09G_RES_ROWS"
echo "M09G_TOP1_N=$M09G_TOP1_N"
echo "M09G_LAYER_N=$M09G_LAYER_N"
echo "M09G_ZERO_N=$M09G_ZERO_N"

echo "--- M09F QC report ---"
if [ -s "$M09F_QC_REPORT" ]; then cat "$M09F_QC_REPORT"; else echo "(M09F_QC_REPORT not present in this mode — skipped)"; fi

echo "--- M09G merge QC report ---"
cat "$M09G_QC_REPORT"

echo "--- M09G layer summary ---"
cat "$M09G_LAYER" | column -t -s $'\t'

if [ "$MODE" = "regression" ]; then
  if [ "$M09F_RUN_N" -eq 36 ] && [ "$M09F_FAIL_N" -eq 0 ] && [ "$M09F_ZERO_REPORT_N" -eq 2 ] && [ "$M09G_TOP1_N" -eq 36 ] && [ "$M09G_ZERO_N" -eq 2 ] && [ "$M09G_PRED_ROWS" -gt 100 ] && [ "$M09G_RES_ROWS" -gt 1000 ]; then
    echo "M09F_M09G_REFERENCE_P2RANK_MASTER_QC: PASS_WITH_ZERO_POCKET_REPORT"
  else
    echo "M09F_M09G_REFERENCE_P2RANK_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$M09F_FAIL_N" -eq 0 ] && [ "$M09G_TOP1_N" -gt 0 ] && [ "$M09G_RES_ROWS" -gt 0 ]; then
    echo "M09F_M09G_REFERENCE_P2RANK_MASTER_QC: PASS_WITH_ZERO_POCKET_REPORT"
  else
    echo "M09F_M09G_REFERENCE_P2RANK_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
fi



echo
echo "===== MODULE 10A: VISUAL/OVERLAY INPUT CONTRACT CHECK ====="

M10A_CONTRACT="06_visual_qc_v6/${MODE}/input_manifests/${MODE}_visual_overlay_input_contract.tsv"
M10A_QUERY_SUMMARY="06_visual_qc_v6/${MODE}/input_manifests/${MODE}_visual_overlay_query_summary.tsv"
M10A_STATUS_SUMMARY="06_visual_qc_v6/${MODE}/input_manifests/${MODE}_visual_overlay_reference_status_summary.tsv"
M10A_QC_REPORT="06_visual_qc_v6/${MODE}/qc/${MODE}_visual_overlay_input_contract_qc_report.tsv"

if [ "$MODE" = "regression" ]; then
  M10A_CONTRACT="06_visual_qc_v6/regression/input_manifests/regression_visual_overlay_input_contract.tsv"
  M10A_QUERY_SUMMARY="06_visual_qc_v6/regression/input_manifests/regression_visual_overlay_query_summary.tsv"
  M10A_STATUS_SUMMARY="06_visual_qc_v6/regression/input_manifests/regression_visual_overlay_reference_status_summary.tsv"
  M10A_QC_REPORT="06_visual_qc_v6/regression/qc/regression_visual_overlay_input_contract_qc_report.tsv"
fi


# M10A producer: regenerate visual/overlay input contract before QC.
# This makes M10A reproducible and allows patched 10A to add portable path columns.
M10A_MODULE="scripts/modules/10a_prepare_visual_overlay_input_contract.py"

M10A_PANEL="05_reference_panel/${MODE}/${MODE}_reference_panel_targets.tsv"
M10A_DECISION="${M08_DECISION}"
M10A_QUERY_MANIFEST="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_query_model_manifest.tsv"
M10A_QUERY_TOP1="04_p2rank/${MODE}/query_models/merged_tables/${MODE}_query_p2rank_top1_pockets.tsv"
M10A_REF_RESOLVED="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_reference_panel_manifest_resolved.tsv"
M10A_REF_UNIQUE="04_p2rank/${MODE}/qc/${MODE}_p2rank_reference_resolved_unique_pocket_counts.tsv"
M10A_REF_TOP1="04_p2rank/${MODE}/reference_models/merged_tables/${MODE}_reference_p2rank_top1_pockets.tsv"

for f in "$M10A_MODULE" "$M10A_PANEL" "$M10A_DECISION" "$M10A_QUERY_MANIFEST" "$M10A_QUERY_TOP1" "$M10A_REF_RESOLVED" "$M10A_REF_UNIQUE" "$M10A_REF_TOP1"; do
  test -s "$f"
done

mkdir -p "$(dirname "$M10A_CONTRACT")" "$(dirname "$M10A_QUERY_SUMMARY")" "$(dirname "$M10A_STATUS_SUMMARY")" "$(dirname "$M10A_QC_REPORT")"

M10A_POINTER="pipeline_state/${MODE}_visual_overlay_input_contract_pointer.tsv"
mkdir -p "$(dirname "$M10A_POINTER")"

python3 "$M10A_MODULE" \
  "$M10A_PANEL" \
  "$M10A_DECISION" \
  "$M10A_QUERY_MANIFEST" \
  "$M10A_QUERY_TOP1" \
  "$M10A_REF_RESOLVED" \
  "$M10A_REF_UNIQUE" \
  "$M10A_REF_TOP1" \
  "$M10A_CONTRACT" \
  "$M10A_QUERY_SUMMARY" \
  "$M10A_STATUS_SUMMARY" \
  "$M10A_QC_REPORT" \
  "$M10A_POINTER"

for f in "$M10A_CONTRACT" "$M10A_QUERY_SUMMARY" "$M10A_STATUS_SUMMARY" "$M10A_QC_REPORT"; do
  test -s "$f"
done

echo "M10A_CONTRACT=$M10A_CONTRACT"
echo "M10A_QUERY_SUMMARY=$M10A_QUERY_SUMMARY"
echo "M10A_STATUS_SUMMARY=$M10A_STATUS_SUMMARY"
echo "M10A_QC_REPORT=$M10A_QC_REPORT"

M10A_CONTRACT_N=$(tail -n +2 "$M10A_CONTRACT" | wc -l)
M10A_QUERY_N=$(tail -n +2 "$M10A_QUERY_SUMMARY" | wc -l)
M10A_DUP_N=$(awk -F'\t' '$1=="duplicate_query_layer_target"{print $2}' "$M10A_QC_REPORT")
M10A_QUERY_MISSING_N=$(awk -F'\t' '$1=="query_models_missing"{print $2}' "$M10A_QC_REPORT")

echo "M10A_CONTRACT_N=$M10A_CONTRACT_N"
echo "M10A_QUERY_N=$M10A_QUERY_N"
echo "M10A_DUP_N=$M10A_DUP_N"
echo "M10A_QUERY_MISSING_N=$M10A_QUERY_MISSING_N"

echo "--- M10A QC report ---"
cat "$M10A_QC_REPORT"

echo "--- M10A visual status summary ---"
cat "$M10A_STATUS_SUMMARY" | column -t -s $'\t'

if [ "$MODE" = "regression" ]; then
  if [ "$M10A_CONTRACT_N" -eq 160 ] && [ "$M10A_QUERY_N" -eq 32 ] && [ "$M10A_DUP_N" -eq 0 ] && [ "$M10A_QUERY_MISSING_N" -eq 0 ]; then
    echo "M10A_VISUAL_OVERLAY_INPUT_CONTRACT_MASTER_QC: PASS"
  else
    echo "M10A_VISUAL_OVERLAY_INPUT_CONTRACT_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$M10A_CONTRACT_N" -gt 0 ] && [ "$M10A_QUERY_N" -gt 0 ] && [ "$M10A_DUP_N" -eq 0 ] && [ "$M10A_QUERY_MISSING_N" -eq 0 ]; then
    echo "M10A_VISUAL_OVERLAY_INPUT_CONTRACT_MASTER_QC: PASS"
  else
    echo "M10A_VISUAL_OVERLAY_INPUT_CONTRACT_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
fi



echo
echo "===== MODULE 10B: VISUAL/OVERLAY SMOKE PACKAGE CHECK ====="

M10B_SMOKE_MANIFEST="06_visual_qc_v6/${MODE}/smoke_package/${MODE}_visual_overlay_smoke_manifest.tsv"
M10B_PYMOL="06_visual_qc_v6/${MODE}/smoke_package/${MODE}_visual_overlay_smoke.pml"
M10B_CHIMERAX="06_visual_qc_v6/${MODE}/smoke_package/${MODE}_visual_overlay_smoke.cxc"
M10B_README="06_visual_qc_v6/${MODE}/smoke_package/README_smoke_visual_overlay.txt"
M10B_QC_REPORT="06_visual_qc_v6/${MODE}/qc/${MODE}_visual_overlay_smoke_qc_report.tsv"

if [ "$MODE" = "regression" ]; then
  M10B_SMOKE_MANIFEST="06_visual_qc_v6/regression/smoke_package/regression_visual_overlay_smoke_manifest.tsv"
  M10B_PYMOL="06_visual_qc_v6/regression/smoke_package/regression_visual_overlay_smoke.pml"
  M10B_CHIMERAX="06_visual_qc_v6/regression/smoke_package/regression_visual_overlay_smoke.cxc"
  M10B_README="06_visual_qc_v6/regression/smoke_package/README_smoke_visual_overlay.txt"
  M10B_QC_REPORT="06_visual_qc_v6/regression/qc/regression_visual_overlay_smoke_qc_report.tsv"
fi


# M10B producer: regenerate smoke visual package after M10A contract generation.
# This keeps smoke_package artifacts reproducible and preserves portable manifest columns.
M10B_MODULE="scripts/modules/10b_prepare_visual_overlay_smoke_package.py"

test -s "$M10B_MODULE"
test -s "$M10A_CONTRACT"

mkdir -p "$(dirname "$M10B_SMOKE_MANIFEST")" "$(dirname "$M10B_PYMOL")" "$(dirname "$M10B_CHIMERAX")" "$(dirname "$M10B_README")" "$(dirname "$M10B_QC_REPORT")"

python3 "$M10B_MODULE" \
  "$M10A_CONTRACT" \
  "$M10B_SMOKE_MANIFEST" \
  "$M10B_PYMOL" \
  "$M10B_CHIMERAX" \
  "$M10B_README" \
  "$M10B_QC_REPORT"

for f in "$M10B_SMOKE_MANIFEST" "$M10B_PYMOL" "$M10B_CHIMERAX" "$M10B_README" "$M10B_QC_REPORT"; do
  test -s "$f"
done

echo "M10B_SMOKE_MANIFEST=$M10B_SMOKE_MANIFEST"
echo "M10B_PYMOL=$M10B_PYMOL"
echo "M10B_CHIMERAX=$M10B_CHIMERAX"
echo "M10B_README=$M10B_README"
echo "M10B_QC_REPORT=$M10B_QC_REPORT"

Q_EXISTS=$(awk -F'\t' '$1=="query_model_pdb_exists"{print $2}' "$M10B_QC_REPORT")
R_EXISTS=$(awk -F'\t' '$1=="reference_file_exists"{print $2}' "$M10B_QC_REPORT")
PML_EXISTS=$(awk -F'\t' '$1=="pymol_script_exists"{print $2}' "$M10B_QC_REPORT")
CXC_EXISTS=$(awk -F'\t' '$1=="chimerax_script_exists"{print $2}' "$M10B_QC_REPORT")
MANIFEST_EXISTS=$(awk -F'\t' '$1=="smoke_manifest_exists"{print $2}' "$M10B_QC_REPORT")
QUERY_RES_N=$(awk -F'\t' '$1=="query_top1_residue_count_used"{print $2}' "$M10B_QC_REPORT")
REF_RES_N=$(awk -F'\t' '$1=="reference_top1_residue_count_used"{print $2}' "$M10B_QC_REPORT")

echo "Q_EXISTS=$Q_EXISTS"
echo "R_EXISTS=$R_EXISTS"
echo "PML_EXISTS=$PML_EXISTS"
echo "CXC_EXISTS=$CXC_EXISTS"
echo "MANIFEST_EXISTS=$MANIFEST_EXISTS"
echo "QUERY_RES_N=$QUERY_RES_N"
echo "REF_RES_N=$REF_RES_N"

echo "--- M10B smoke QC report ---"
cat "$M10B_QC_REPORT"

if [ "$Q_EXISTS" = "YES" ] && [ "$R_EXISTS" = "YES" ] && [ "$PML_EXISTS" = "YES" ] && [ "$CXC_EXISTS" = "YES" ] && [ "$MANIFEST_EXISTS" = "YES" ]; then
  echo "M10B_VISUAL_OVERLAY_SMOKE_MASTER_QC: PASS"
else
  echo "M10B_VISUAL_OVERLAY_SMOKE_MASTER_QC: CHECK_NEEDED"
  exit 1
fi


echo "Sonraki modül: M10C all-query visual/overlay script package."


echo
echo "===== MODULE 10C: ALL-QUERY VISUAL/OVERLAY SCRIPT PACKAGE CHECK ====="

M10C_MANIFEST="06_visual_qc_v6/${MODE}/all_query_visual_scripts/${MODE}_all_query_visual_script_manifest.tsv"
M10C_QUERY_SUMMARY="06_visual_qc_v6/${MODE}/all_query_visual_scripts/${MODE}_all_query_visual_script_query_summary.tsv"
M10C_SKIPPED="06_visual_qc_v6/${MODE}/all_query_visual_scripts/${MODE}_all_query_visual_script_skipped_reference_report.tsv"
M10C_README="06_visual_qc_v6/${MODE}/all_query_visual_scripts/README_all_query_visual_scripts.txt"
M10C_QC_REPORT="06_visual_qc_v6/${MODE}/qc/${MODE}_all_query_visual_script_package_qc_report.tsv"

if [ "$MODE" = "regression" ]; then
  M10C_MANIFEST="06_visual_qc_v6/regression/all_query_visual_scripts/regression_all_query_visual_script_manifest.tsv"
  M10C_QUERY_SUMMARY="06_visual_qc_v6/regression/all_query_visual_scripts/regression_all_query_visual_script_query_summary.tsv"
  M10C_SKIPPED="06_visual_qc_v6/regression/all_query_visual_scripts/regression_all_query_visual_script_skipped_reference_report.tsv"
  M10C_README="06_visual_qc_v6/regression/all_query_visual_scripts/README_all_query_visual_scripts.txt"
  M10C_QC_REPORT="06_visual_qc_v6/regression/qc/regression_all_query_visual_script_package_qc_report.tsv"
fi


# M10C producer: regenerate all-query visual/overlay script package after M10B smoke package.
# This keeps all-query visual artifacts reproducible and preserves portable manifest columns.
M10C_MODULE="scripts/modules/10c_prepare_all_query_visual_script_package.py"

M10C_OUT_ROOT="06_visual_qc_v6/${MODE}/all_query_visual_scripts"
M10C_POINTER="pipeline_state/${MODE}_all_query_visual_script_package_pointer.tsv"

if [ "$MODE" = "regression" ]; then
  M10C_OUT_ROOT="06_visual_qc_v6/regression/all_query_visual_scripts"
  M10C_POINTER="pipeline_state/regression_all_query_visual_script_package_pointer.tsv"
fi

test -s "$M10C_MODULE"
test -s "$M10A_CONTRACT"

mkdir -p "$M10C_OUT_ROOT" "$(dirname "$M10C_QC_REPORT")" "$(dirname "$M10C_POINTER")"

python3 "$M10C_MODULE" \
  "$M10A_CONTRACT" \
  "$M10C_OUT_ROOT" \
  "$M10C_MANIFEST" \
  "$M10C_QUERY_SUMMARY" \
  "$M10C_SKIPPED" \
  "$M10C_README" \
  "$M10C_QC_REPORT" \
  "$M10C_POINTER"

for f in "$M10C_MANIFEST" "$M10C_QUERY_SUMMARY" "$M10C_SKIPPED" "$M10C_README" "$M10C_QC_REPORT"; do
  test -s "$f"
done

echo "M10C_MANIFEST=$M10C_MANIFEST"
echo "M10C_QUERY_SUMMARY=$M10C_QUERY_SUMMARY"
echo "M10C_SKIPPED=$M10C_SKIPPED"
echo "M10C_README=$M10C_README"
echo "M10C_QC_REPORT=$M10C_QC_REPORT"

M10C_MANIFEST_N=$(tail -n +2 "$M10C_MANIFEST" | wc -l)
M10C_QUERY_N=$(tail -n +2 "$M10C_QUERY_SUMMARY" | wc -l)
M10C_SKIPPED_N=$(tail -n +2 "$M10C_SKIPPED" | wc -l)

echo "M10C_MANIFEST_N=$M10C_MANIFEST_N"
echo "M10C_QUERY_N=$M10C_QUERY_N"
echo "M10C_SKIPPED_N=$M10C_SKIPPED_N"

echo "--- M10C QC report ---"
cat "$M10C_QC_REPORT"

if [ "$M10C_QUERY_N" -gt 0 ] && [ "$M10C_MANIFEST_N" -gt 0 ]; then
  echo "M10C_ALL_QUERY_VISUAL_SCRIPT_PACKAGE_MASTER_QC: PASS"
else
  echo "M10C_ALL_QUERY_VISUAL_SCRIPT_PACKAGE_MASTER_QC: CHECK_NEEDED"
  exit 1
fi

echo
echo "===== MODULE 10D: VISUAL SCRIPT PACKAGE QC ====="
# Produces the visual_script_package_lite_qc_report used by M12A-lite.
# CA-only overlay guard QC is embedded here.

M10D_ROW_QC="06_visual_qc_v6/${MODE}/qc/${MODE}_visual_script_package_lite_row_qc.tsv"
M10D_QC="06_visual_qc_v6/${MODE}/qc/${MODE}_visual_script_package_lite_qc_report.tsv"
M10D_POINTER="pipeline_state/${MODE}_visual_script_package_lite_qc_pointer.tsv"

mkdir -p "$(dirname "$M10D_QC")" "$(dirname "$M10D_POINTER")"

python3 scripts/modules/10d_qc_visual_script_package.py \
  "${M10C_MANIFEST}" \
  "${M10D_ROW_QC}" \
  "${M10D_QC}" \
  "${M10D_POINTER}"

test -s "${M10D_QC}"
echo "M10D_QC=${M10D_QC}"
echo "M10D_ROW_QC=${M10D_ROW_QC}"

echo
echo "===== MODULE 10F-PREP: PROFILE-AWARE CANONICAL VISUAL RENDER SBATCH GENERATOR ====="
M10F_GENERATOR="scripts/modules/10f_prepare_canonical_visual_render_sbatch.sh"
M10F_GENERATED_SBATCH="scripts/submit/m10f_canonical_visual_render_${VERMAMG_PROFILE:-truba}_${MODE}.sbatch"

if [ -x "$M10F_GENERATOR" ]; then
  bash "$M10F_GENERATOR" "$MODE"
  echo "M10F_GENERATOR=$M10F_GENERATOR"
  echo "M10F_GENERATED_SBATCH=$M10F_GENERATED_SBATCH"
  if [ -s "$M10F_GENERATED_SBATCH" ]; then
    echo "M10F_GENERATED_SBATCH_STATUS: OK"
  else
    echo "M10F_GENERATED_SBATCH_STATUS: SKIPPED_OR_LOCAL (sbatch not generated in this backend)"
  fi
  if [ "${M10F_ENABLE_RENDER_SUBMIT:-0}" = "1" ]; then
    echo "M10F_ENABLE_RENDER_SUBMIT=1 but automatic submit is intentionally not wired in master yet."
    echo "Submit manually after reviewing: sbatch $M10F_GENERATED_SBATCH"
  else
    echo "M10F_ENABLE_RENDER_SUBMIT=${M10F_ENABLE_RENDER_SUBMIT:-0}; generated sbatch only, no submit."
  fi
else
  echo "UYARI: M10F generator missing or not executable: $M10F_GENERATOR"
fi


echo "===== MODULE 10F: CANONICAL V6 VISUAL ENGINE CHECK ====="

# M10F is the accepted canonical Bölüm 6-style visual engine.
# It replaces the deleted old M10R_C/v6_standard_portable branch.
# Regression currently checks the validated all32 canonical run.
# Full/test execution wiring will use the same accepted render env and primary-reference contract.

M10F_PTR="pipeline_state/artifacts/m10f_canonical_v6_engine_all32_pointer.tsv"
M10F_ENV_PTR="pipeline_state/artifacts/m10f_render_env_pointer.tsv"
M10F_QC="06_visual_qc_v6/regression/qc/canonical_v6_engine_all32_regression_qc_report.tsv"
M10F_RUN="06_visual_qc_v6/regression/canonical_v6_engine_all32_regression"
M10F_FINAL_DIR="$M10F_RUN/rendered_png/pilot32_v6_standard"
M10F_TABLE_DIR="$M10F_FINAL_DIR/tables"
M10F_ENV="06_visual_qc_v6/render_env"
M10F_PYMOL="$M10F_ENV/bin/pymol"

for f in "$M10F_PTR" "$M10F_ENV_PTR" "$M10F_QC" "$M10F_PYMOL"; do
  test -s "$f"
done

test -d "$M10F_RUN"
test -d "$M10F_FINAL_DIR"
test -d "$M10F_TABLE_DIR"
test -x "$M10F_PYMOL"

M10F_FINAL_PNG_N=$(find "$M10F_FINAL_DIR" -maxdepth 1 -type f -name '*_v6_standard_600dpi.png' | wc -l)
M10F_PANEL_PNG_N=$(find "$M10F_FINAL_DIR/panels" -type f -name '*.png' | wc -l)
M10F_PML_N=$(find "$M10F_FINAL_DIR/pml" -type f -name '*.pml' | wc -l)
M10F_TABLE_TSV_N=$(find "$M10F_TABLE_DIR" -type f -name '*.tsv' | wc -l)
M10F_FAILED_N=$(($(wc -l < "$M10F_TABLE_DIR/pilot32_v6_standard_failed.tsv")-1))
M10F_RES_FAILED_N=$(($(wc -l < "$M10F_TABLE_DIR/pilot32_v6_standard_residue_table_failed.tsv")-1))

echo "M10F_PTR=$M10F_PTR"
echo "M10F_ENV_PTR=$M10F_ENV_PTR"
echo "M10F_QC=$M10F_QC"
echo "M10F_RUN=$M10F_RUN"
echo "M10F_FINAL_DIR=$M10F_FINAL_DIR"
echo "M10F_TABLE_DIR=$M10F_TABLE_DIR"
echo "M10F_PYMOL=$M10F_PYMOL"

echo "M10F_FINAL_PNG_N=$M10F_FINAL_PNG_N"
echo "M10F_PANEL_PNG_N=$M10F_PANEL_PNG_N"
echo "M10F_PML_N=$M10F_PML_N"
echo "M10F_TABLE_TSV_N=$M10F_TABLE_TSV_N"
echo "M10F_FAILED_N=$M10F_FAILED_N"
echo "M10F_RES_FAILED_N=$M10F_RES_FAILED_N"

echo "--- M10F QC report ---"
cat "$M10F_QC"

if [ "$MODE" = "regression" ]; then
  if [ "$M10F_FINAL_PNG_N" -eq 32 ] && [ "$M10F_PANEL_PNG_N" -eq 192 ] && [ "$M10F_PML_N" -eq 32 ] && [ "$M10F_TABLE_TSV_N" -eq 135 ] && [ "$M10F_FAILED_N" -eq 0 ] && [ "$M10F_RES_FAILED_N" -eq 0 ]; then
    echo "M10F_CANONICAL_V6_VISUAL_ENGINE_MASTER_QC: PASS"
  else
    echo "M10F_CANONICAL_V6_VISUAL_ENGINE_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
else
  echo "M10F_CANONICAL_V6_VISUAL_ENGINE_MASTER_QC: REGRESSION_REFERENCE_READY"
  echo "NOTE: full/test automatic M10F execution requires next patch: primary-only manifest builder + canonical visual runner."
fi

echo
echo "===== MODULE 11: SUPPORTING REFERENCE AUDIT ====="
# Retains rank-2 to rank-5 supporting references as TSV/audit evidence.
# Must not generate PNGs. M12 decision matrix uses the conflict flags output.

M11_OUTDIR="${RESULTS_BASE}/06_supporting_reference_audit"
mkdir -p "${M11_OUTDIR}"

python3 scripts/modules/11_supporting_reference_audit.py \
  --mode "${MODE}" \
  --panel "${M08_PANEL}" \
  --decision "${M08_DECISION}" \
  --visual-contract "${M10A_CONTRACT}" \
  --query-top1 "${M09E_TOP1}" \
  --reference-top1 "${M09G_TOP1}" \
  --outdir "${M11_OUTDIR}"

echo "M11_AUDIT_PRODUCED=${RESULTS_BASE}/06_supporting_reference_audit/${MODE}_supporting_reference_audit.tsv"
echo "M11_CONFLICT_PRODUCED=${RESULTS_BASE}/06_supporting_reference_audit/${MODE}_supporting_reference_conflict_flags.tsv"

echo
echo "===== MODULE 11: SUPPORTING REFERENCE AUDIT CHECK ====="

# M11 retains rank-2 to rank-5 supporting references as TSV/audit evidence.
# It must not generate PNGs.
# M12 decision matrix will use these supporting context/conflict flags.

M11_PTR="pipeline_state/artifacts/m11_supporting_reference_audit_pointer.tsv"
M11_AUDIT="${RESULTS_BASE}/06_supporting_reference_audit/${MODE}_supporting_reference_audit.tsv"
M11_CONFLICT="${RESULTS_BASE}/06_supporting_reference_audit/${MODE}_supporting_reference_conflict_flags.tsv"
M11_FAMILY="${RESULTS_BASE}/06_supporting_reference_audit/${MODE}_supporting_reference_family_summary.tsv"
M11_QC="${RESULTS_BASE}/06_supporting_reference_audit/${MODE}_supporting_reference_audit_qc.tsv"

for f in "$M11_PTR" "$M11_AUDIT" "$M11_CONFLICT" "$M11_FAMILY" "$M11_QC"; do
  test -s "$f"
done

M11_AUDIT_N=$(tail -n +2 "$M11_AUDIT" | wc -l)
M11_CONFLICT_N=$(tail -n +2 "$M11_CONFLICT" | wc -l)
M11_FAMILY_N=$(tail -n +2 "$M11_FAMILY" | wc -l)
M11_QC_N=$(tail -n +2 "$M11_QC" | wc -l)

M11_PNG_GENERATED=$(awk -F'\t' '$1=="png_generated"{print $2}' "$M11_QC" | head -n 1 | tr -d '[:space:]\r')
M11_SUPPORTING_EXPECTED=$(awk -F'\t' '$1=="supporting_expected_rows"{print $2}' "$M11_QC" | head -n 1 | tr -d '[:space:]\r')
M11_SUPPORTING_AUDIT=$(awk -F'\t' '$1=="supporting_audit_rows"{print $2}' "$M11_QC" | head -n 1 | tr -d '[:space:]\r')

echo "M11_PTR=$M11_PTR"
echo "M11_AUDIT=$M11_AUDIT"
echo "M11_CONFLICT=$M11_CONFLICT"
echo "M11_FAMILY=$M11_FAMILY"
echo "M11_QC=$M11_QC"

echo "M11_AUDIT_N=$M11_AUDIT_N"
echo "M11_CONFLICT_N=$M11_CONFLICT_N"
echo "M11_FAMILY_N=$M11_FAMILY_N"
echo "M11_QC_N=$M11_QC_N"
echo "M11_PNG_GENERATED=$M11_PNG_GENERATED"
echo "M11_SUPPORTING_EXPECTED=$M11_SUPPORTING_EXPECTED"
echo "M11_SUPPORTING_AUDIT=$M11_SUPPORTING_AUDIT"

echo "--- M11 QC report ---"
cat "$M11_QC"

if [ "$MODE" = "regression" ]; then
  echo "M11_QC_EXPECT_AUDIT_N=128"
  echo "M11_QC_EXPECT_CONFLICT_N=32"
  echo "M11_QC_EXPECT_FAMILY_N=11"
  echo "M11_QC_EXPECT_PNG_GENERATED=NO"
  echo "M11_QC_EXPECT_SUPPORTING_EXPECTED_EQ_AUDIT=YES"

  if [ "$M11_AUDIT_N" -eq 128 ] && \
     [ "$M11_CONFLICT_N" -eq 32 ] && \
     [ "$M11_FAMILY_N" -eq 11 ] && \
     [ "$M11_PNG_GENERATED" = "NO" ] && \
     [ "$M11_SUPPORTING_EXPECTED" = "$M11_SUPPORTING_AUDIT" ]; then
    echo "M11_SUPPORTING_REFERENCE_AUDIT_MASTER_QC: PASS"
  else
    echo "M11_SUPPORTING_REFERENCE_AUDIT_MASTER_QC: CHECK_NEEDED"
    echo "DEBUG_M11_AUDIT_N=$M11_AUDIT_N"
    echo "DEBUG_M11_CONFLICT_N=$M11_CONFLICT_N"
    echo "DEBUG_M11_FAMILY_N=$M11_FAMILY_N"
    echo "DEBUG_M11_PNG_GENERATED=[$M11_PNG_GENERATED]"
    echo "DEBUG_M11_SUPPORTING_EXPECTED=[$M11_SUPPORTING_EXPECTED]"
    echo "DEBUG_M11_SUPPORTING_AUDIT=[$M11_SUPPORTING_AUDIT]"
    exit 1
  fi
else
  if [ "$M11_AUDIT_N" -gt 0 ] && [ "$M11_CONFLICT_N" -gt 0 ] && [ "$M11_PNG_GENERATED" = "NO" ]; then
    echo "M11_SUPPORTING_REFERENCE_AUDIT_MASTER_QC: PASS"
  else
    echo "M11_SUPPORTING_REFERENCE_AUDIT_MASTER_QC: CHECK_NEEDED"
    echo "DEBUG_M11_AUDIT_N=$M11_AUDIT_N"
    echo "DEBUG_M11_CONFLICT_N=$M11_CONFLICT_N"
    echo "DEBUG_M11_PNG_GENERATED=[$M11_PNG_GENERATED]"
    exit 1
  fi
fi

echo
echo "===== MODULE 12A: PRIMARY DECISION MATRIX (LITE/DYNAMIC) ====="
# M12A-lite is the production dynamic path for Tier1 and local runs.
# It does not require old Pilot32 calibration matrix or M10F canonical tables.
# 12a_primary_decision_matrix.py is legacy (Pilot32 regression calibration only).

M10D_QC="06_visual_qc_v6/${MODE}/qc/${MODE}_visual_script_package_lite_qc_report.tsv"
M10E_RENDER_MANIFEST="06_visual_qc_v6/${MODE}/${MODE}_pymol_render_local_run_manifest.tsv"

python3 scripts/modules/12a_lite_primary_decision_matrix.py \
  --mode "${MODE}" \
  --m08-decision "${M08_DECISION}" \
  --pdb-rank1 "${PDB_PRIMARY}" \
  --afsp-rank1 "${AFSP_PRIMARY}" \
  --visual-contract "${M10A_CONTRACT}" \
  --m10d-qc "${M10D_QC}" \
  --m10e-render-manifest "${M10E_RENDER_MANIFEST}" \
  --m11-conflict "${M11_CONFLICT}" \
  --outdir "${RESULTS_BASE}/07_decision_matrix"

echo "M12A_LITE_MATRIX=${RESULTS_BASE}/07_decision_matrix/${MODE}_primary_decision_matrix.tsv"

echo
echo "===== MODULE 12B: SUPPORTING REFERENCE DECISION MATRIX ====="
# M12A_MATRIX defined here for use by M12B and M12C before the QC block.
M12A_MATRIX="${RESULTS_BASE}/07_decision_matrix/${MODE}_primary_decision_matrix.tsv"

python3 scripts/modules/12b_supporting_reference_decision_matrix.py \
  --mode "${MODE}" \
  --primary "${M12A_MATRIX}" \
  --m11-audit "${M11_AUDIT}" \
  --m11-conflict "${M11_CONFLICT}" \
  --visual-contract "${M10A_CONTRACT}" \
  --panel "${M08_PANEL}" \
  --outdir "${RESULTS_BASE}/07_decision_matrix"

echo "M12B_MATRIX_PRODUCED=${RESULTS_BASE}/07_decision_matrix/${MODE}_supporting_reference_decision_matrix.tsv"

echo
echo "===== MODULE 12C: COMBINED DECISION SUMMARY ====="

python3 scripts/modules/12c_combined_decision_summary.py \
  --mode "${MODE}" \
  --primary "${M12A_MATRIX}" \
  --supporting "${RESULTS_BASE}/07_decision_matrix/${MODE}_supporting_reference_decision_matrix.tsv" \
  --m11-conflict "${M11_CONFLICT}" \
  --outdir "${RESULTS_BASE}/07_decision_matrix"

echo "M12C_SUMMARY_PRODUCED=${RESULTS_BASE}/07_decision_matrix/${MODE}_combined_decision_summary.tsv"

echo
echo "===== MODULE 12: DECISION MATRIX LAYER CHECK ====="

# M12A: primary/rank-1 decision matrix
# M12B: supporting rank-2-to-rank-5 decision matrix
# M12C: combined one-row-per-protein structural summary
# Supporting references must not override primary decisions.

M12A_PTR="pipeline_state/artifacts/m12a_primary_decision_matrix_pointer.tsv"
M12B_PTR="pipeline_state/artifacts/m12b_supporting_reference_decision_matrix_pointer.tsv"
M12C_PTR="pipeline_state/artifacts/m12c_combined_decision_summary_pointer.tsv"

M12A_MATRIX="${RESULTS_BASE}/07_decision_matrix/${MODE}_primary_decision_matrix.tsv"
M12A_CLASS_SUMMARY="${RESULTS_BASE}/07_decision_matrix/${MODE}_primary_decision_class_summary.tsv"
M12A_QC="${RESULTS_BASE}/07_decision_matrix/${MODE}_primary_decision_matrix_qc.tsv"

M12B_MATRIX="${RESULTS_BASE}/07_decision_matrix/${MODE}_supporting_reference_decision_matrix.tsv"
M12B_CLASS_SUMMARY="${RESULTS_BASE}/07_decision_matrix/${MODE}_supporting_reference_decision_class_summary.tsv"
M12B_QC="${RESULTS_BASE}/07_decision_matrix/${MODE}_supporting_reference_decision_matrix_qc.tsv"

M12C_SUMMARY="${RESULTS_BASE}/07_decision_matrix/${MODE}_combined_decision_summary.tsv"
M12C_REC_SUMMARY="${RESULTS_BASE}/07_decision_matrix/${MODE}_combined_decision_recommendation_summary.tsv"
M12C_QC="${RESULTS_BASE}/07_decision_matrix/${MODE}_combined_decision_summary_qc.tsv"

for f in \
  "$M12A_PTR" "$M12B_PTR" "$M12C_PTR" \
  "$M12A_MATRIX" "$M12A_CLASS_SUMMARY" "$M12A_QC" \
  "$M12B_MATRIX" "$M12B_CLASS_SUMMARY" "$M12B_QC" \
  "$M12C_SUMMARY" "$M12C_REC_SUMMARY" "$M12C_QC"
do
  test -s "$f"
done

M12A_ROWS=$(tail -n +2 "$M12A_MATRIX" | wc -l)
M12B_ROWS=$(tail -n +2 "$M12B_MATRIX" | wc -l)
M12C_ROWS=$(tail -n +2 "$M12C_SUMMARY" | wc -l)

M12A_STATUS=$(awk -F'\t' '$1=="status"{print $2}' "$M12A_QC" | head -n 1 | tr -d '[:space:]\r')
M12B_STATUS=$(awk -F'\t' '$1=="status"{print $2}' "$M12B_QC" | head -n 1 | tr -d '[:space:]\r')
M12C_STATUS=$(awk -F'\t' '$1=="status"{print $2}' "$M12C_QC" | head -n 1 | tr -d '[:space:]\r')

M12B_PNG_GENERATED=$(awk -F'\t' '$1=="png_generated"{print $2}' "$M12B_QC" | head -n 1 | tr -d '[:space:]\r')
M12B_PRIMARY_OVERRIDE=$(awk -F'\t' '$1=="primary_override_allowed"{print $2}' "$M12B_QC" | head -n 1 | tr -d '[:space:]\r')
M12C_OVERRIDE_COUNT=$(awk -F'\t' '$1=="primary_override_count"{print $2}' "$M12C_QC" | head -n 1 | tr -d '[:space:]\r')
M12C_SUPPORT4=$(awk -F'\t' '$1=="queries_with_four_supporting_refs"{print $2}' "$M12C_QC" | head -n 1 | tr -d '[:space:]\r')

echo "M12A_MATRIX=$M12A_MATRIX"
echo "M12B_MATRIX=$M12B_MATRIX"
echo "M12C_SUMMARY=$M12C_SUMMARY"
echo "M12A_ROWS=$M12A_ROWS"
echo "M12B_ROWS=$M12B_ROWS"
echo "M12C_ROWS=$M12C_ROWS"
echo "M12A_STATUS=$M12A_STATUS"
echo "M12B_STATUS=$M12B_STATUS"
echo "M12C_STATUS=$M12C_STATUS"
echo "M12B_PNG_GENERATED=$M12B_PNG_GENERATED"
echo "M12B_PRIMARY_OVERRIDE_ALLOWED=$M12B_PRIMARY_OVERRIDE"
echo "M12C_PRIMARY_OVERRIDE_COUNT=$M12C_OVERRIDE_COUNT"
echo "M12C_QUERIES_WITH_FOUR_SUPPORTING_REFS=$M12C_SUPPORT4"

echo
echo "--- M12A QC ---"
cat "$M12A_QC"

echo
echo "--- M12B QC ---"
cat "$M12B_QC"

echo
echo "--- M12C QC ---"
cat "$M12C_QC"

if [ "$MODE" = "regression" ]; then
  if [ "$M12A_ROWS" -eq 32 ] && \
     [ "$M12B_ROWS" -eq 128 ] && \
     [ "$M12C_ROWS" -eq 32 ] && \
     [ "$M12A_STATUS" = "OK" ] && \
     [ "$M12B_STATUS" = "OK" ] && \
     [ "$M12C_STATUS" = "OK" ] && \
     [ "$M12B_PNG_GENERATED" = "NO" ] && \
     [ "$M12B_PRIMARY_OVERRIDE" = "NO" ] && \
     [ "$M12C_OVERRIDE_COUNT" -eq 0 ] && \
     [ "$M12C_SUPPORT4" -eq 32 ]; then
    echo "M12_DECISION_MATRIX_LAYER_MASTER_QC: PASS"
  else
    echo "M12_DECISION_MATRIX_LAYER_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$M12A_ROWS" -gt 0 ] && \
     [ "$M12B_ROWS" -gt 0 ] && \
     [ "$M12C_ROWS" -gt 0 ] && \
     [ "$M12A_STATUS" = "OK" ] && \
     [ "$M12B_STATUS" = "OK" ] && \
     [ "$M12C_STATUS" = "OK" ] && \
     [ "$M12B_PNG_GENERATED" = "NO" ] && \
     [ "$M12B_PRIMARY_OVERRIDE" = "NO" ] && \
     [ "$M12C_OVERRIDE_COUNT" -eq 0 ]; then
    echo "M12_DECISION_MATRIX_LAYER_MASTER_QC: PASS"
  else
    echo "M12_DECISION_MATRIX_LAYER_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
fi

echo
echo "===== MODULE 13A-C: RULEBOOK CONTEXT + CLASSIFICATION + MISMATCH ====="

M13_OUTDIR="${RESULTS_BASE}/08_rulebook_evidence"
M13_DISCOVERY_DIR="${M13_OUTDIR}/discovery"
mkdir -p "${M13_OUTDIR}" "${M13_DISCOVERY_DIR}"

FAMILY_COVERAGE="results/regression/08_rulebook_evidence/discovery/m13_existing_rulebook_family_coverage.tsv"
KNOWN_RULES="08_rulebook_evidence/rulebook/known_residue_rules.tsv"
LIGAND_CLASSES="08_rulebook_evidence/rulebook/ligand_biological_classes.tsv"
CASE_DEFINITIONS="08_rulebook_evidence/rulebook/section8_case_definitions.tsv"
OLD_AUTO="09_regression_pilot32/old_pilot32_outputs/section8_final_auto_evidence_classification_refined_known_residue.tsv"
MISMATCH_TAXONOMY="pipeline_contracts/b9_m13_rulebook_mismatch_taxonomy.tsv"

M13A_CONTEXT="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_rulebook_context_collector.tsv"
M13B_CLASSIFIED="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_existing_rulebook_classified.tsv"
M13C_MISMATCH="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_rulebook_mismatch_reasons.tsv"
M13C_SUPPORT_NOTES="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_rulebook_supporting_context_notes.tsv"

python3 scripts/modules/13a_rulebook_context_collector.py \
  --mode "${MODE}" \
  --m12a "${M12A_MATRIX}" \
  --m12b "${M12B_MATRIX}" \
  --m12c "${M12C_SUMMARY}" \
  --family-coverage "${FAMILY_COVERAGE}" \
  --known-rules "${KNOWN_RULES}" \
  --ligand-classes "${LIGAND_CLASSES}" \
  --case-definitions "${CASE_DEFINITIONS}" \
  --outdir "${M13_OUTDIR}"

echo "M13A_CONTEXT_PRODUCED=${M13A_CONTEXT}"

python3 scripts/modules/13b_existing_rulebook_classifier.py \
  --mode "${MODE}" \
  --context "${M13A_CONTEXT}" \
  --m12a "${M12A_MATRIX}" \
  --known-rules "${KNOWN_RULES}" \
  --case-definitions "${CASE_DEFINITIONS}" \
  --old-auto "${OLD_AUTO}" \
  --outdir "${M13_OUTDIR}"

echo "M13B_CLASSIFIED_PRODUCED=${M13B_CLASSIFIED}"

python3 scripts/modules/13c_rulebook_coverage_mismatch_detector.py \
  --mode "${MODE}" \
  --context "${M13A_CONTEXT}" \
  --classified "${M13B_CLASSIFIED}" \
  --supporting "${M12B_MATRIX}" \
  --combined "${M12C_SUMMARY}" \
  --mismatch-taxonomy "${MISMATCH_TAXONOMY}" \
  --outdir "${M13_OUTDIR}"

echo "M13C_MISMATCH_PRODUCED=${M13C_MISMATCH}"
echo "M13C_SUPPORT_NOTES_PRODUCED=${M13C_SUPPORT_NOTES}"

echo
echo "===== MODULE 13D-LITE: LIGAND SCAN INPUTS (LOCAL/PORTABLE) ====="

python3 scripts/modules/13d_prepare_ligand_scan_inputs_lite.py \
  --mode "${MODE}" \
  --visual-contract "${M10A_CONTRACT}" \
  --outdir "${M13_DISCOVERY_DIR}"

M13D_SCAN_MAP="${M13_DISCOVERY_DIR}/${MODE}_m13d_primary_supporting_reference_ligand_scan_map.tsv"
M13D_HETATM_INVENTORY="${M13_DISCOVERY_DIR}/${MODE}_m13d_reference_pdb_hetatm_inventory.tsv"

test -s "${M13D_SCAN_MAP}"
test -s "${M13D_HETATM_INVENTORY}"
echo "M13D_SCAN_MAP=${M13D_SCAN_MAP}"
echo "M13D_HETATM_INVENTORY=${M13D_HETATM_INVENTORY}"

echo
echo "===== MODULE 13D: LIGAND / COFACTOR CONTEXT SCAN ====="

M13D_PRIMARY="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_ligand_cofactor_primary_context.tsv"
M13D_SUPPORT="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_ligand_cofactor_supporting_context.tsv"

python3 scripts/modules/13d_ligand_cofactor_context_scan.py \
  --mode "${MODE}" \
  --scan-map "${M13D_SCAN_MAP}" \
  --hetatm-inventory "${M13D_HETATM_INVENTORY}" \
  --ligand-dictionary "${LIGAND_CLASSES}" \
  --fallback "pipeline_contracts/b9_m13d_ligand_fallback_classes.tsv" \
  --m13b "${M13B_CLASSIFIED}" \
  --m13c-notes "${M13C_SUPPORT_NOTES}" \
  --outdir "${M13_OUTDIR}"

echo "M13D_PRIMARY_PRODUCED=${M13D_PRIMARY}"
echo "M13D_SUPPORT_PRODUCED=${M13D_SUPPORT}"

echo
echo "===== MODULE 13E: FINAL RULEBOOK EVIDENCE MATRIX ====="

M13E_FINAL="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_final_rulebook_evidence_matrix.tsv"
M13E_COMPACT="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_final_rulebook_evidence_compact.tsv"
M13E_QC="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_final_rulebook_evidence_matrix_qc.tsv"

python3 scripts/modules/13e_final_rulebook_evidence_matrix.py \
  --mode "${MODE}" \
  --m13b "${M13B_CLASSIFIED}" \
  --m13c-mismatch "${M13C_MISMATCH}" \
  --m13c-suggest "${M13_OUTDIR}/${MODE}_rulebook_new_class_suggestions.tsv" \
  --m13c-notes "${M13C_SUPPORT_NOTES}" \
  --m13d-primary "${M13D_PRIMARY}" \
  --m13d-support "${M13D_SUPPORT}" \
  --m12c "${M12C_SUMMARY}" \
  --outdir "${M13_OUTDIR}"

echo "M13E_FINAL_PRODUCED=${M13E_FINAL}"
echo "M13E_COMPACT_PRODUCED=${M13E_COMPACT}"

echo
echo "===== MODULE 13: RULEBOOK / LIGAND / COFACTOR EVIDENCE CHECK ====="

# M13A: rulebook context collector
# M13B: existing rulebook classifier
# M13C: true mismatch / new-rule-needed detector + supporting context notes
# M13D: ligand/cofactor primary/supporting context
# M13E: final one-row-per-protein rulebook evidence matrix
# Supporting references provide context only; they do not override primary/rank-1 or M13B classes.

M13A_CONTEXT="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_rulebook_context_collector.tsv"
M13B_CLASSIFIED="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_existing_rulebook_classified.tsv"
M13C_MISMATCH="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_rulebook_mismatch_reasons.tsv"
M13C_SUPPORT_NOTES="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_rulebook_supporting_context_notes.tsv"
M13D_PRIMARY="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_ligand_cofactor_primary_context.tsv"
M13D_SUPPORT="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_ligand_cofactor_supporting_context.tsv"
M13E_FINAL="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_final_rulebook_evidence_matrix.tsv"
M13E_COMPACT="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_final_rulebook_evidence_compact.tsv"
M13E_QC="${RESULTS_BASE}/08_rulebook_evidence/${MODE}_final_rulebook_evidence_matrix_qc.tsv"

for f in \
  "$M13A_CONTEXT" \
  "$M13B_CLASSIFIED" \
  "$M13C_MISMATCH" \
  "$M13C_SUPPORT_NOTES" \
  "$M13D_PRIMARY" \
  "$M13D_SUPPORT" \
  "$M13E_FINAL" \
  "$M13E_COMPACT" \
  "$M13E_QC"
do
  if [ ! -s "$f" ]; then
    echo "M13_RULEBOOK_EVIDENCE_MASTER_QC: CHECK_NEEDED"
    echo "ERROR_M13_MISSING_OR_EMPTY=$f"
    exit 1
  fi
done

M13A_ROWS=$(tail -n +2 "$M13A_CONTEXT" | wc -l)
M13B_ROWS=$(tail -n +2 "$M13B_CLASSIFIED" | wc -l)
M13C_MISMATCH_ROWS=$(tail -n +2 "$M13C_MISMATCH" | wc -l)
M13C_SUPPORT_NOTE_ROWS=$(tail -n +2 "$M13C_SUPPORT_NOTES" | wc -l)
M13D_PRIMARY_ROWS=$(tail -n +2 "$M13D_PRIMARY" | wc -l)
M13D_SUPPORT_ROWS=$(tail -n +2 "$M13D_SUPPORT" | wc -l)
M13E_FINAL_ROWS=$(tail -n +2 "$M13E_FINAL" | wc -l)
M13E_COMPACT_ROWS=$(tail -n +2 "$M13E_COMPACT" | wc -l)

M13E_STATUS=$(awk -F'\t' '$1=="status"{print $2}' "$M13E_QC" | head -n 1 | tr -d '[:space:]\r')
M13E_TRUE_MISMATCH=$(awk -F'\t' '$1=="m13c_true_mismatch_rows"{print $2}' "$M13E_QC" | head -n 1 | tr -d '[:space:]\r')
M13E_OVERRIDE_COUNT=$(awk -F'\t' '$1=="override_count"{print $2}' "$M13E_QC" | head -n 1 | tr -d '[:space:]\r')
M13B_CALIBRATED_ROWS=$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i=="m13b_classification_status") c=i; next} c && $c=="CLASSIFIED_EXISTING_CASE_RULE_CALIBRATED"{n++} END{print n+0}' "$M13B_CLASSIFIED")
M13B_KNOWN_RULE_ROWS=$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i=="m13b_classification_status") c=i; next} c && $c=="CLASSIFIED_EXISTING_KNOWN_RESIDUE_RULE"{n++} END{print n+0}' "$M13B_CLASSIFIED")
M13B_CLASSIFIED_ROWS=$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i=="m13b_classification_status") c=i; next} c && $c ~ /^CLASSIFIED/{n++} END{print n+0}' "$M13B_CLASSIFIED")
M13E_SECTION8_CLASS_COUNTS_OK=$(awk -F'\t' '
BEGIN{
  expected["DOMAIN_PARTIAL_REANALYZE"]=2
  expected["MODERATE_REVIEW_NO_LIGAND_CONTACT"]=4
  expected["NONBIOLOGICAL_HETATM_NO_UPGRADE"]=5
  expected["PDB_COFACTOR_METAL_SUPPORTED_STRUCTURAL_POCKET"]=2
  expected["PDB_LIGAND_SUPPORTED_STRUCTURAL_POCKET"]=3
  expected["PDB_PLP_SUPPORTED_STRUCTURAL_POCKET"]=1
  expected["QUERY_SUPPORTED_PLUS_CATALYTIC_RESIDUE_CONSERVED"]=5
  expected["SPECIAL_CASE_NO_QUERY_POCKET_REFERENCE_ONLY"]=1
  expected["STRONG_STRUCTURAL_POCKET_SUPPORT_NO_CURATED_RESIDUE"]=5
  expected["WEAK_OR_NEGATIVE_POCKET_SUPPORT"]=4
}
NR==1{for(i=1;i<=NF;i++) if($i=="final_rulebook_evidence_class") c=i; next}
c{obs[$c]++; total++}
END{
  ok=(total==32)
  for(k in expected) if(obs[k] != expected[k]) ok=0
  for(k in obs) if(!(k in expected)) ok=0
  print ok ? "YES" : "NO"
}' "$M13E_FINAL")

echo "M13A_CONTEXT=$M13A_CONTEXT"
echo "M13B_CLASSIFIED=$M13B_CLASSIFIED"
echo "M13C_MISMATCH=$M13C_MISMATCH"
echo "M13C_SUPPORT_NOTES=$M13C_SUPPORT_NOTES"
echo "M13D_PRIMARY=$M13D_PRIMARY"
echo "M13D_SUPPORT=$M13D_SUPPORT"
echo "M13E_FINAL=$M13E_FINAL"
echo "M13E_COMPACT=$M13E_COMPACT"

echo "M13A_ROWS=$M13A_ROWS"
echo "M13B_ROWS=$M13B_ROWS"
echo "M13C_TRUE_MISMATCH_ROWS=$M13C_MISMATCH_ROWS"
echo "M13C_SUPPORTING_CONTEXT_NOTE_ROWS=$M13C_SUPPORT_NOTE_ROWS"
echo "M13D_PRIMARY_ROWS=$M13D_PRIMARY_ROWS"
echo "M13D_SUPPORT_ROWS=$M13D_SUPPORT_ROWS"
echo "M13E_FINAL_ROWS=$M13E_FINAL_ROWS"
echo "M13E_COMPACT_ROWS=$M13E_COMPACT_ROWS"
echo "M13E_STATUS=$M13E_STATUS"
echo "M13E_TRUE_MISMATCH_QC=$M13E_TRUE_MISMATCH"
echo "M13E_OVERRIDE_COUNT=$M13E_OVERRIDE_COUNT"
echo "M13B_CLASSIFIED_ROWS=$M13B_CLASSIFIED_ROWS"
echo "M13B_CALIBRATED_ROWS=$M13B_CALIBRATED_ROWS"
echo "M13B_KNOWN_RULE_ROWS=$M13B_KNOWN_RULE_ROWS"
echo "M13E_SECTION8_CLASS_COUNTS_OK=$M13E_SECTION8_CLASS_COUNTS_OK"

if [ "$MODE" = "regression" ]; then
  if [ "$M13A_ROWS" -eq 32 ] && \
     [ "$M13B_ROWS" -eq 32 ] && \
     [ "$M13B_CLASSIFIED_ROWS" -eq 32 ] && \
     [ "$M13C_MISMATCH_ROWS" -eq 0 ] && \
     [ "$M13C_SUPPORT_NOTE_ROWS" -eq 32 ] && \
     [ "$M13D_PRIMARY_ROWS" -eq 32 ] && \
     [ "$M13D_SUPPORT_ROWS" -eq 128 ] && \
     [ "$M13E_FINAL_ROWS" -eq 32 ] && \
     [ "$M13E_COMPACT_ROWS" -eq 32 ] && \
     [ "$M13E_STATUS" = "OK" ] && \
     [ "$M13E_TRUE_MISMATCH" -eq 0 ] && \
     [ "$M13E_OVERRIDE_COUNT" -eq 0 ] && \
     [ "$M13E_SECTION8_CLASS_COUNTS_OK" = "YES" ]; then
    echo "M13_RULEBOOK_EVIDENCE_MASTER_QC: PASS"
  else
    echo "M13_RULEBOOK_EVIDENCE_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$M13A_ROWS" -gt 0 ] && \
     [ "$M13B_ROWS" -gt 0 ] && \
     [ "$M13D_PRIMARY_ROWS" -gt 0 ] && \
     [ "$M13E_FINAL_ROWS" -gt 0 ] && \
     [ "$M13E_STATUS" = "OK" ] && \
     [ "$M13E_OVERRIDE_COUNT" -eq 0 ]; then
    echo "M13_RULEBOOK_EVIDENCE_MASTER_QC: PASS"
  else
    echo "M13_RULEBOOK_EVIDENCE_MASTER_QC: CHECK_NEEDED"
    exit 1
  fi
fi

echo
echo "===== MODULE 14: FINAL EXPORT ====="
# M14 joins M13E output with optional metadata and PNG manifest.
# Metadata is context-only; it does not override M12/M13 decisions.
# Missing metadata or PNG manifest is handled silently by M14.

M14_EXPORT_OUTDIR="exports/${RUN_LABEL}"

python3 scripts/modules/14_final_export.py \
  --mode "${MODE}" \
  --m13e-final "${M13E_FINAL}" \
  --m13e-compact "${M13E_COMPACT}" \
  --metadata "${FULL_CANDIDATE_METADATA:-}" \
  --run-label "${RUN_LABEL}" \
  --outdir "${M14_EXPORT_OUTDIR}"

M14_FULL="${M14_EXPORT_OUTDIR}/${MODE}_final_export_full.tsv"
M14_COMPACT="${M14_EXPORT_OUTDIR}/${MODE}_final_export_compact.tsv"
M14_QC="${M14_EXPORT_OUTDIR}/${MODE}_final_export_qc.tsv"

test -s "$M14_FULL"
test -s "$M14_COMPACT"
test -s "$M14_QC"

M14_ROWS=$(tail -n +2 "$M14_FULL" | wc -l)
M14_STATUS=$(awk -F'\t' '$1=="status"{print $2}' "$M14_QC" | head -n 1 | tr -d '[:space:]\r')
M14_META_COV=$(awk -F'\t' '$1=="metadata_join_coverage_fraction"{print $2}' "$M14_QC" | head -n 1 | tr -d '[:space:]\r')

echo "M14_FULL=${M14_FULL}"
echo "M14_COMPACT=${M14_COMPACT}"
echo "M14_ROWS=${M14_ROWS}"
echo "M14_STATUS=${M14_STATUS}"
echo "M14_METADATA_COVERAGE=${M14_META_COV}"
echo "M14_EXPORT_OUTDIR=${M14_EXPORT_OUTDIR}"

if [ "${M14_STATUS}" = "OK" ] || [ "${M14_STATUS}" = "WARN" ]; then
  echo "M14_FINAL_EXPORT_MASTER_QC: PASS"
else
  echo "M14_FINAL_EXPORT_MASTER_QC: CHECK_NEEDED"
  exit 1
fi

echo
echo "===== MASTER PIPELINE CURRENT ENDPOINT ====="
echo "Current accepted endpoint: M14 final export."
echo "Next development modules: portable tool packaging / results delivery."
