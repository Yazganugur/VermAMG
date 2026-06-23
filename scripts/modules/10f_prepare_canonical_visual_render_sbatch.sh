#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-regression}"
PROFILE_RAW="${VERMAMG_PROFILE:-truba}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$PROFILE_RAW"

MODE="$MODE_RAW"
case "$MODE_RAW" in
  regression|pilot32) MODE="regression" ;;
  smoke|test) MODE="test" ;;
  full|tier1_full) MODE="full" ;;
  *)
    echo "HATA: MODE test/regression/full olmalı. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

if [ "${EXECUTION_BACKEND:-local}" != "slurm" ]; then
  echo "M10F sbatch generator skipped because EXECUTION_BACKEND=${EXECUTION_BACKEND:-local}"
  echo "For local execution, a separate local runner should be used later."
  exit 0
fi

if [ "$MODE" != "regression" ]; then
  echo "M10F canonical visual render currently supports regression/all32 only."
  echo "MODE=$MODE"
  exit 0
fi

ROOT="$VERMAMG_ROOT"
RUN_REL="${M10F_CANONICAL_RUN_DIR:-06_visual_qc_v6/regression/canonical_v6_engine_all32_regression}"
RUN_DIR="$ROOT/$RUN_REL"

OUT="scripts/submit/m10f_canonical_visual_render_${PROFILE_RAW}_${MODE}.sbatch"
mkdir -p "$(dirname "$OUT")" logs/modules/06_visual_qc_v6

PYMOL_CMD_RESOLVED="${PYMOL_CMD:-pymol}"
PYMOL_BIN_DIR="$(dirname "$PYMOL_CMD_RESOLVED")"
PYMOL_PIL_SITE_RESOLVED="${PYMOL_PIL_SITE:-}"
PYMOL_PYDEPS_ROOT_RESOLVED="${PYMOL_PYDEPS_ROOT:-}"

cat > "$OUT" <<SBATCH
#!/bin/bash
#SBATCH -J M10F_CANV6
#SBATCH -A ${SLURM_ACCOUNT:-}
#SBATCH -p ${SLURM_PARTITION_DEBUG:-debug}
#SBATCH -c ${SLURM_CPUS:-4}
#SBATCH --mem=${SLURM_MEM:-24G}
#SBATCH --time=${SLURM_TIME_CPU:-02:00:00}
#SBATCH -o logs/modules/06_visual_qc_v6/m10f_canonical_visual_render_%j.out
#SBATCH -e logs/modules/06_visual_qc_v6/m10f_canonical_visual_render_%j.err

set -euo pipefail

echo "===== ÇIKTI BAŞI ====="
echo "===== VERMAMG M10F CANONICAL VISUAL RENDER ====="
echo "PROFILE=$PROFILE_RAW"
echo "MODE=$MODE"
echo "ROOT=$ROOT"
echo "RUN_DIR=$RUN_DIR"
echo "PYMOL_CMD=$PYMOL_CMD_RESOLVED"
echo "PYMOL_BIN_DIR=$PYMOL_BIN_DIR"
echo "PYMOL_PYDEPS_ROOT=$PYMOL_PYDEPS_ROOT_RESOLVED"
echo "PYMOL_PIL_SITE=$PYMOL_PIL_SITE_RESOLVED"

cd "$ROOT"
test -d "$RUN_DIR"

if [ -n "$PYMOL_PIL_SITE_RESOLVED" ]; then
  export PYTHONPATH="$PYMOL_PIL_SITE_RESOLVED:\${PYTHONPATH:-}"
fi

if [ -n "$PYMOL_BIN_DIR" ] && [ -d "$PYMOL_BIN_DIR" ]; then
  export PATH="$PYMOL_BIN_DIR:\$PATH"
fi

cd "$RUN_DIR"

echo "PYMOL_IN_PATH:"
command -v pymol || true
echo "PYTHONPATH=\${PYTHONPATH:-}"

python3 scripts/run_pilot32_visual_qc_pipeline.py

echo "final_png_count=\$(find rendered_png/pilot32_v6_standard -maxdepth 1 -type f -name '*_v6_standard_600dpi.png' | wc -l)"
echo "panel_png_count=\$(find rendered_png/pilot32_v6_standard/panels -type f -name '*.png' | wc -l)"
echo "pml_count=\$(find rendered_png/pilot32_v6_standard/pml -type f -name '*.pml' | wc -l)"
echo "pml_residue_count=\$(find rendered_png/pilot32_v6_standard/pml_residue_tables -type f -name '*.pml' | wc -l)"
echo "table_tsv_count=\$(find rendered_png/pilot32_v6_standard/tables -type f -name '*.tsv' | wc -l)"
echo "===== ÇIKTI SONU ====="
SBATCH

echo "generated_sbatch=$OUT"
