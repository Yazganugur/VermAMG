#!/usr/bin/env bash
cd /mnt/d/VermAMG

echo "=== M10F scripts in repository ==="
find scripts -name '*10f*' -o -name '*10e*' 2>/dev/null | sort

echo ""
echo "=== Stage 200 wiring in executor.py ==="
grep -n "200_m10f\|m10f_render\|10e_prepare" scripts/vermamg_lib/executor.py | head -20

echo ""
echo "=== Stage 200 in stage_registry.py ==="
grep -n "200_m10f\|m10f" scripts/vermamg_lib/stage_registry.py

echo ""
echo "=== Fresh run visual outputs ==="
ls runs/tier1_tier2_colabfold_postrun_fresh_v1/06_visual_qc_v6/full/ 2>/dev/null

echo ""
echo "=== Visual script manifest ==="
wc -l runs/tier1_tier2_colabfold_postrun_fresh_v1/06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_manifest.tsv

echo ""
echo "=== First manifest row fields ==="
python3 - <<'PYEOF'
import csv
path = "runs/tier1_tier2_colabfold_postrun_fresh_v1/06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_manifest.tsv"
rows = list(csv.DictReader(open(path), delimiter="\t"))
print("total_rows:", len(rows))
r = rows[0]
for k, v in r.items():
    print(k, ":", (v[:100] if v else ""))
PYEOF

echo ""
echo "=== PyMOL checks ==="
which pymol 2>/dev/null && pymol --version 2>/dev/null | head -1 || echo "pymol: NOT in PATH"
ls 06_visual_qc_v6/render_env/bin/pymol 2>/dev/null || echo "project-root render_env: NOT FOUND"
find resources containers -name 'pymol' -type f 2>/dev/null || echo "no pymol in resources/containers"
ls resources/containers/*.sif 2>/dev/null | grep -i pymol || echo "no pymol sif in resources/containers"

echo ""
echo "=== Existing PNG count in fresh run ==="
find runs/tier1_tier2_colabfold_postrun_fresh_v1 -name "*.png" 2>/dev/null | wc -l

echo ""
echo "=== 10e local runner script ==="
head -20 scripts/modules/10e_prepare_local_pymol_render_runner.sh 2>/dev/null || echo "NOT FOUND"
