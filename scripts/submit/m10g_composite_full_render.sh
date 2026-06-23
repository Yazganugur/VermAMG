#!/usr/bin/env bash
# m10g_composite_full_render.sh
# Full composite figure render — 665 proteins.
# Run ONLY after smoke PASS and visual layout confirmed.
#
# Usage:
#   cd /arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full
#   source profile/vermamg_profile.sh
#   bash scripts/submit/m10g_composite_full_render.sh

set -euo pipefail

WORKSPACE="${VERMAMG_ROOT:-$(pwd)}"
cd "$WORKSPACE"

FRESH_RUN="runs/tier1_tier2_colabfold_postrun_fresh_v1"
SCRIPT="scripts/modules/10g_generate_full_composite_figures.py"
PYMOL="06_visual_qc_v6/render_env/bin/pymol"
OUTDIR="${FRESH_RUN}/06_visual_qc_v6/full/composite_png"
LOG="logs/m10g_full_$(date +%Y%m%d_%H%M%S).log"

echo "===== M10G COMPOSITE FULL RENDER ====="
echo "DATE:      $(date)"
echo "HOST:      $(hostname)"
echo "WORKSPACE: $WORKSPACE"
echo "OUTDIR:    $OUTDIR"
echo "EXPECTED:  665 composite PNGs"
echo ""

test -s "$SCRIPT"  || { echo "FATAL: generator script not found: $SCRIPT"; exit 1; }
test -x "$PYMOL"   || { echo "FATAL: pymol wrapper not executable: $PYMOL"; exit 1; }
command -v apptainer >/dev/null 2>&1 || { echo "FATAL: apptainer not in PATH"; exit 1; }

mkdir -p "$(dirname "$LOG")"
echo "LOG: $LOG"
echo ""

python3 "$SCRIPT" \
  --workspace "$WORKSPACE" \
  --outdir    "$OUTDIR" \
  --pymol     "$PYMOL" \
  2>&1 | tee "$LOG"

echo ""
echo "===== M10G FULL RENDER COMPLETE ====="

MANIFEST="${OUTDIR}/composite_png_manifest.tsv"
FAILED="${OUTDIR}/composite_png_failed.tsv"
QC="${OUTDIR}/composite_png_qc.tsv"

PRODUCED_N=$(tail -n +2 "$MANIFEST" 2>/dev/null | grep -v "PML_ONLY" | wc -l || echo 0)
FAILED_N=$(tail -n +2 "$FAILED" 2>/dev/null | wc -l || echo 0)

echo "PRODUCED: $PRODUCED_N"
echo "FAILED:   $FAILED_N"

if [ -s "$QC" ]; then
  cat "$QC"
fi

if [ "$PRODUCED_N" -ge 660 ] && [ "$FAILED_N" -le 5 ]; then
  echo "M10G_FULL_COMPOSITE_QC: PASS"
else
  echo "M10G_FULL_COMPOSITE_QC: CHECK_NEEDED — produced=$PRODUCED_N failed=$FAILED_N"
  echo "Check: $FAILED"
  exit 1
fi
