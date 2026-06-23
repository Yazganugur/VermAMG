#!/bin/bash
#SBATCH -J M10F_CANV6
#SBATCH -A yugur
#SBATCH -p debug
#SBATCH -c 20
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH -o logs/modules/06_visual_qc_v6/m10f_canonical_visual_render_%j.out
#SBATCH -e logs/modules/06_visual_qc_v6/m10f_canonical_visual_render_%j.err

set -euo pipefail

echo "===== ÇIKTI BAŞI ====="
echo "===== VERMAMG M10F CANONICAL VISUAL RENDER ====="
echo "PROFILE=truba"
echo "MODE=regression"
echo "ROOT=/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
echo "RUN_DIR=/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/regression/canonical_v6_engine_all32_regression"
echo "PYMOL_CMD=/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/render_env/bin/pymol"
echo "PYMOL_BIN_DIR=/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/render_env/bin"
echo "PYMOL_PYDEPS_ROOT=/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/resources/tools/pymol_pydeps"
echo "PYMOL_PIL_SITE=/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/resources/tools/pymol_pydeps/lib/python3.9/site-packages"

cd "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
test -d "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/regression/canonical_v6_engine_all32_regression"

if [ -n "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/resources/tools/pymol_pydeps/lib/python3.9/site-packages" ]; then
  export PYTHONPATH="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/resources/tools/pymol_pydeps/lib/python3.9/site-packages:${PYTHONPATH:-}"
fi

if [ -n "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/render_env/bin" ] && [ -d "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/render_env/bin" ]; then
  export PATH="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/render_env/bin:$PATH"
fi

cd "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full/06_visual_qc_v6/regression/canonical_v6_engine_all32_regression"

echo "PYMOL_IN_PATH:"
command -v pymol || true
echo "PYTHONPATH=${PYTHONPATH:-}"

python3 scripts/run_pilot32_visual_qc_pipeline.py

echo "final_png_count=$(find rendered_png/pilot32_v6_standard -maxdepth 1 -type f -name '*_v6_standard_600dpi.png' | wc -l)"
echo "panel_png_count=$(find rendered_png/pilot32_v6_standard/panels -type f -name '*.png' | wc -l)"
echo "pml_count=$(find rendered_png/pilot32_v6_standard/pml -type f -name '*.pml' | wc -l)"
echo "pml_residue_count=$(find rendered_png/pilot32_v6_standard/pml_residue_tables -type f -name '*.pml' | wc -l)"
echo "table_tsv_count=$(find rendered_png/pilot32_v6_standard/tables -type f -name '*.tsv' | wc -l)"
echo "===== ÇIKTI SONU ====="
