#!/usr/bin/env bash
# m10g_composite_smoke_render.sh
# Smoke render for 10g composite figure generator.
# Run on TRUBA cluster after sourcing a VermAMG profile.
#
# Usage:
#   cd /arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full
#   source profile/vermamg_profile.sh   # sets VERMAMG_ROOT, PATH
#   bash scripts/submit/m10g_composite_smoke_render.sh
#
# After smoke PASS and visual layout confirmed, run full:
#   bash scripts/submit/m10g_composite_full_render.sh

set -euo pipefail

WORKSPACE="${VERMAMG_ROOT:-$(pwd)}"
cd "$WORKSPACE"

FRESH_RUN="runs/tier1_tier2_colabfold_postrun_fresh_v1"
SCRIPT="scripts/modules/10g_generate_full_composite_figures.py"
PYMOL="06_visual_qc_v6/render_env/bin/pymol"
OUTDIR="${FRESH_RUN}/06_visual_qc_v6/full/composite_png_smoke"
LOG="logs/m10g_smoke_$(date +%Y%m%d_%H%M%S).log"

# ── smoke protein set ────────────────────────────────────────────────────────
# 1. CoA_trans ADVANCE (LITE_STRUCTURAL_SUPPORT_WITH_QUERY_POCKET_REFERENCE_UNRELIABLE)
# 2. REVIEW with query pocket (LITE_REFERENCE_POCKET_UNRELIABLE_REVIEW, 3HCDH_N)
# 3. Zero-pocket query (ALS_ss_C, query_pocket_present=NO)
SMOKE_IDS=$(cat << 'EOF'
T1_Alistipes_shahii__GCA_963640155.1_-_H07649-L1_cleanbin_000055_GreatApes__CAVHYL010000025.1__26__328814_23,T1_Acidobacteriota_bacterium__GCA_020848535.1_-_ASM2084853v1__JADLHX010000001.1__112__1978231_63,T1_Acidobacteriota_bacterium__GCA_947470805.1_-_RH-18aug17-384__CANIVU010000084.1__43__1978231_29
EOF
)
SMOKE_IDS=$(echo "$SMOKE_IDS" | tr -d '\n' | xargs)

# ── pre-flight checks ────────────────────────────────────────────────────────
echo "===== M10G COMPOSITE SMOKE RENDER ====="
echo "DATE:      $(date)"
echo "HOST:      $(hostname)"
echo "WORKSPACE: $WORKSPACE"
echo "OUTDIR:    $OUTDIR"
echo ""

test -s "$SCRIPT"            || { echo "FATAL: generator script not found: $SCRIPT"; exit 1; }
test -x "$PYMOL"             || { echo "FATAL: pymol wrapper not executable: $PYMOL"; exit 1; }
test -s "${FRESH_RUN}/06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv" \
                             || { echo "FATAL: input contract not found"; exit 1; }
test -s "${FRESH_RUN}/results/full/07_decision_matrix/full_primary_decision_matrix.tsv" \
                             || { echo "FATAL: decision matrix not found"; exit 1; }
command -v apptainer >/dev/null 2>&1 || { echo "FATAL: apptainer not in PATH"; exit 1; }

mkdir -p "$(dirname "$LOG")"
echo "LOG: $LOG"
echo ""

# ── run smoke ────────────────────────────────────────────────────────────────
echo "SMOKE_IDS: $SMOKE_IDS"
echo ""
echo "--- Starting smoke render ---"

python3 "$SCRIPT" \
  --workspace "$WORKSPACE" \
  --outdir    "$OUTDIR" \
  --pymol     "$PYMOL" \
  --only      "$SMOKE_IDS" \
  2>&1 | tee "$LOG"

echo ""
echo "===== M10G SMOKE RENDER COMPLETE ====="

# ── smoke QC check ────────────────────────────────────────────────────────────
SMOKE_QC="${OUTDIR}/composite_png_qc.tsv"
SMOKE_MANIFEST="${OUTDIR}/composite_png_manifest.tsv"
SMOKE_FAILED="${OUTDIR}/composite_png_failed.tsv"

if [ -s "$SMOKE_QC" ]; then
  echo "--- Smoke QC ---"
  cat "$SMOKE_QC"
fi

PRODUCED_N=$(tail -n +2 "$SMOKE_MANIFEST" 2>/dev/null | grep -v "PML_ONLY" | wc -l || echo 0)
FAILED_N=$(tail -n +2 "$SMOKE_FAILED" 2>/dev/null | wc -l || echo 0)

echo ""
echo "SMOKE_PRODUCED: $PRODUCED_N"
echo "SMOKE_FAILED:   $FAILED_N"

if [ "$PRODUCED_N" -ge 3 ] && [ "$FAILED_N" -eq 0 ]; then
  echo "M10G_SMOKE_COMPOSITE_QC: PASS"
  echo ""
  echo "Smoke PNGs in: $OUTDIR"
  find "$OUTDIR" -maxdepth 1 -name '*_v6_standard_600dpi.png' | sort
  echo ""
  echo "Visually verify the 3 smoke PNGs, then run:"
  echo "  bash scripts/submit/m10g_composite_full_render.sh"
else
  echo "M10G_SMOKE_COMPOSITE_QC: FAIL — produced=$PRODUCED_N failed=$FAILED_N"
  echo "Check log: $LOG"
  echo "Check failed: $SMOKE_FAILED"
  exit 1
fi
