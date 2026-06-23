#!/bin/bash
#SBATCH -J B9_M10F_CANV6_PIL
#SBATCH -A yugur
#SBATCH -p debug
#SBATCH -c 4
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH -o logs/modules/06_visual_qc_v6/b9_step6g_fix2_canonical_v6_all32_%j.out
#SBATCH -e logs/modules/06_visual_qc_v6/b9_step6g_fix2_canonical_v6_all32_%j.err

set -euo pipefail

echo "===== ÇIKTI BAŞI ====="
echo "===== BÖLÜM 9 — ADIM 6G-FIX2: CANONICAL V6 ENGINE ALL32 REGRESSION RUN WITH PIL PYTHONPATH ====="

ROOT="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
PIL_SITE="/arf/home/yugur/containers/pymol_pydeps/lib/python3.9/site-packages"

echo
echo "===== 0) ROOT / ENV KONTROL ====="
echo "ROOT=$ROOT"
echo "PIL_SITE=$PIL_SITE"

if [ ! -d "$ROOT" ]; then
  echo "ERROR: ROOT klasörü yok: $ROOT"
  echo "===== ÇIKTI SONU ====="
  exit 1
fi

if [ ! -d "$PIL_SITE/PIL" ]; then
  echo "ERROR: PIL klasörü yok: $PIL_SITE/PIL"
  echo "===== ÇIKTI SONU ====="
  exit 1
fi

cd "$ROOT" || {
  echo "ERROR: ROOT içine girilemedi: $ROOT"
  echo "===== ÇIKTI SONU ====="
  exit 1
}

export PYTHONPATH="$PIL_SITE:${PYTHONPATH:-}"

echo
echo "PWD:"
pwd

echo
echo "DATE:"
date

echo
echo "HOST:"
hostname

echo
echo "SLURM_JOB_ID:"
echo "${SLURM_JOB_ID:-NA}"

echo
echo "===== 1) Python/PIL smoke ====="
python3 - <<'PYTEST'
import sys
print("python=", sys.executable)
print("version=", sys.version)
print("PYTHONPATH_first=", sys.path[:5])
from PIL import Image, ImageDraw, ImageFont, ImageChops
import PIL
print("PIL_OK", PIL.__version__)
PYTEST

SRC="06_visual_qc_v6/regression/golden_v6_exactrun"
RUN="06_visual_qc_v6/regression/canonical_v6_engine_all32_regression"
PYMOL_BIN_DIR="$ROOT/06_visual_qc_v6/regression/v6_standard_portable/bin"

echo
echo "===== 2) KAYNAK VE RUN KLASÖRÜ ====="
echo "SRC=$SRC"
echo "RUN=$RUN"
echo "PYMOL_BIN_DIR=$PYMOL_BIN_DIR"

if [ ! -d "$SRC" ]; then
  echo "ERROR: SRC yok: $SRC"
  echo "===== ÇIKTI SONU ====="
  exit 1
fi

if [ ! -x "$PYMOL_BIN_DIR/pymol" ]; then
  echo "ERROR: PyMOL wrapper yok veya executable değil: $PYMOL_BIN_DIR/pymol"
  echo "===== ÇIKTI SONU ====="
  exit 1
fi

rm -rf "$RUN"
mkdir -p "$(dirname "$RUN")"

echo
echo "===== 3) Canonical paket all32 regression klasörüne kopyalanıyor ====="
cp -a "$SRC" "$RUN"

echo
echo "===== 4) Input sayımları ====="
echo "manifest_rows=$(($(wc -l < "$RUN/overlay_manifest/pilot32_overlay_manifest_chainaware_residuefixed.tsv")-1))"
echo "summary_rows=$(($(wc -l < "$RUN/merged_tables/pilot32_structural_pocket_integrated_summary.tsv")-1))"
echo "query_pdb_count=$(find "$RUN/query_pdb" -maxdepth 1 -type f -name '*.pdb' | wc -l)"
echo "ref_pdb_chain_count=$(find "$RUN/reference_pdb/pdb_chains" -maxdepth 1 -type f -name '*.pdb' | wc -l)"
echo "ref_afsp_count=$(find "$RUN/reference_pdb/afsp" -maxdepth 1 -type f -name '*.pdb' | wc -l)"

echo
echo "===== 5) Canonical all32 runner çalıştırılıyor ====="
cd "$RUN" || {
  echo "ERROR: RUN içine girilemedi"
  echo "===== ÇIKTI SONU ====="
  exit 1
}

export PATH="$PYMOL_BIN_DIR:$PATH"

echo "PWD_FOR_RUN:"
pwd
echo "PYMOL_IN_PATH:"
command -v pymol || true
echo "PYTHONPATH=$PYTHONPATH"
echo

python3 scripts/run_pilot32_visual_qc_pipeline.py

RUN_STATUS=$?

echo
echo "===== 6) RUN_STATUS ====="
echo "RUN_STATUS=$RUN_STATUS"

echo
echo "===== 7) Çıktı sayımları ====="
echo "final_png_count=$(find rendered_png/pilot32_v6_standard -maxdepth 1 -type f -name '*_v6_standard_600dpi.png' | wc -l)"
echo "panel_png_count=$(find rendered_png/pilot32_v6_standard/panels -type f -name '*.png' | wc -l)"
echo "pml_count=$(find rendered_png/pilot32_v6_standard/pml -type f -name '*.pml' | wc -l)"
echo "pml_residue_count=$(find rendered_png/pilot32_v6_standard/pml_residue_tables -type f -name '*.pml' | wc -l)"
echo "table_tsv_count=$(find rendered_png/pilot32_v6_standard/tables -type f -name '*.tsv' | wc -l)"

echo
echo "===== 8) Failed tabloları ====="
for f in \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_failed.tsv \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_residue_table_failed.tsv
do
  echo
  echo "----- $f -----"
  if [ -s "$f" ]; then
    wc -l "$f"
    cat "$f"
  else
    echo "MISSING_OR_EMPTY"
  fi
done

echo
echo "===== 9) Ana birleşik tablo satır sayıları ====="
for f in \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_produced.tsv \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_metrics.tsv \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_metrics_detail.tsv \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_pocket_residue_details.tsv \
  rendered_png/pilot32_v6_standard/tables/pilot32_v6_standard_alignment_pocket_classification.tsv
do
  echo
  echo "----- $f -----"
  if [ -s "$f" ]; then
    echo "rows=$(($(wc -l < "$f")-1))"
    head -n 3 "$f"
  else
    echo "MISSING_OR_EMPTY"
  fi
done

echo
echo "===== 10) T1P001 PML referans kontrolü ====="
grep -nE 'load |1poi|reference_pdb|query_pdb' rendered_png/pilot32_v6_standard/pml/T1P001_CoA_trans_v6_standard.pml || true

echo
echo "===== 11) Örnek PNG liste ====="
find rendered_png/pilot32_v6_standard -maxdepth 1 -type f -name '*_v6_standard_600dpi.png' | sort | sed -n '1,40p'

echo
echo "===== BÖLÜM 9 — ADIM 6G-FIX2 BİTTİ ====="
echo "===== ÇIKTI SONU ====="
