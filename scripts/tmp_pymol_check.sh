#!/usr/bin/env bash
cd /mnt/d/VermAMG

echo "=== render_env/bin/pymol content ==="
cat 06_visual_qc_v6/render_env/bin/pymol 2>/dev/null | head -30

echo ""
echo "=== render_env structure ==="
find 06_visual_qc_v6/render_env -name 'pymol*' -o -name '*.so' -o -name 'lib' 2>/dev/null | head -20

echo ""
echo "=== Apptainer/Singularity ==="
which apptainer 2>/dev/null || echo "apptainer: NOT in PATH"
which singularity 2>/dev/null || echo "singularity: NOT in PATH"

echo ""
echo "=== pymol.sif container ==="
ls -lh resources/containers/pymol_deb12_2.5.0_sc.sif 2>/dev/null || echo "NOT FOUND"

echo ""
echo "=== Python pymol module ==="
python3 -c "import pymol; print('pymol module available:', pymol.__version__)" 2>/dev/null || echo "python pymol module: NOT AVAILABLE"
python3 -c "import pymol2; print('pymol2 available')" 2>/dev/null || echo "pymol2: NOT AVAILABLE"

echo ""
echo "=== render_env python ==="
ls 06_visual_qc_v6/render_env/lib/python*/site-packages/pymol* 2>/dev/null | head -5
ls 06_visual_qc_v6/render_env/lib/python*/ 2>/dev/null | head -5
