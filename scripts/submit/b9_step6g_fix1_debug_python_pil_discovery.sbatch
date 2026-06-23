#!/bin/bash
#SBATCH -J B9_M10F_PIL_DISC
#SBATCH -A yugur
#SBATCH -p debug
#SBATCH -c 2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH -o logs/modules/06_visual_qc_v6/b9_step6g_fix1_python_pil_discovery_%j.out
#SBATCH -e logs/modules/06_visual_qc_v6/b9_step6g_fix1_python_pil_discovery_%j.err

set -u

echo "===== ÇIKTI BAŞI ====="
echo "===== BÖLÜM 9 — ADIM 6G-FIX1: DEBUG NODE PYTHON/PIL ENV DISCOVERY ====="

ROOT="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
cd "$ROOT" || exit 1

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
echo "===== 1) Python adayları ====="
for py in \
  python3 \
  /usr/bin/python3 \
  /usr/local/bin/python3 \
  /arf/home/yugur/containers/pymol_pydeps/bin/python \
  /arf/home/yugur/containers/pymol_pydeps/bin/python3 \
  /arf/home/yugur/containers/pymol_pydeps/venv/bin/python \
  /arf/home/yugur/containers/pymol_pydeps/venv/bin/python3
do
  echo
  echo "----- PYTHON_CANDIDATE: $py -----"
  if command -v "$py" >/dev/null 2>&1 || [ -x "$py" ]; then
    "$py" -V 2>&1
    "$py" - <<'PYTEST'
import sys
print("executable=", sys.executable)
print("sys.path_first5=", sys.path[:5])
try:
    import PIL
    from PIL import Image
    print("PIL_OK", PIL.__version__)
except Exception as e:
    print("PIL_FAIL", repr(e))
PYTEST
  else
    echo "NOT_FOUND_OR_NOT_EXECUTABLE"
  fi
done

echo
echo "===== 2) pymol_pydeps dosya keşfi ====="
for d in \
  /arf/home/yugur/containers/pymol_pydeps \
  /arf/home/yugur/containers \
  "$ROOT/06_visual_qc_v6/regression/v6_standard_portable"
do
  echo
  echo "----- DIR: $d -----"
  if [ -d "$d" ]; then
    find "$d" -maxdepth 4 \( -iname '*PIL*' -o -iname '*pillow*' -o -name 'site-packages' -o -name 'python3*' -o -name 'python' \) 2>/dev/null | sort | sed -n '1,120p'
  else
    echo "MISSING_DIR"
  fi
done

echo
echo "===== 3) Mevcut PyMOL wrapper ====="
PYMOL="$ROOT/06_visual_qc_v6/regression/v6_standard_portable/bin/pymol"
if [ -x "$PYMOL" ]; then
  echo "PYMOL=$PYMOL"
  head -n 80 "$PYMOL"
else
  echo "MISSING_OR_NOT_EXECUTABLE: $PYMOL"
fi

echo
echo "===== 4) Python module path hızlı arama ====="
find /arf/home/yugur/containers/pymol_pydeps -maxdepth 6 -type d -name 'PIL' 2>/dev/null | sort || true
find /arf/home/yugur/containers/pymol_pydeps -maxdepth 6 -type d -name 'site-packages' 2>/dev/null | sort || true

echo
echo "===== BÖLÜM 9 — ADIM 6G-FIX1 BİTTİ ====="
echo "===== ÇIKTI SONU ====="
