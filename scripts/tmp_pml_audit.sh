#!/usr/bin/env bash
cd /mnt/d/VermAMG
RUN="runs/tier1_tier2_colabfold_postrun_fresh_v1"
MANIFEST="$RUN/06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_manifest.tsv"

echo "=== Sample PML script ==="
pml=$(python3 -c "
import csv
rows = list(csv.DictReader(open('$MANIFEST'), delimiter='\t'))
primary = [r for r in rows if r.get('panel_order','')=='1'][0]
print(primary['pymol_script'])
")
echo "PML path: $pml"
echo ""
cat "$pml" 2>/dev/null | head -40

echo ""
echo "=== PyMOL headless test ==="
PYMOL="06_visual_qc_v6/render_env/bin/pymol"
"$PYMOL" --version 2>&1 | head -3

echo ""
echo "=== Total PML scripts in run ==="
find "$RUN/06_visual_qc_v6/full/all_query_visual_scripts" -name "*.pml" 2>/dev/null | wc -l

echo ""
echo "=== Primary panel PML count (panel_order=1) ==="
python3 -c "
import csv
rows = list(csv.DictReader(open('$MANIFEST'), delimiter='\t'))
primary = [r for r in rows if r.get('panel_order','')=='1']
print('primary_panel_rows:', len(primary))
print('first_pml:', primary[0]['pymol_script'][:100] if primary else 'none')
"

echo ""
echo "=== Query dir structure sample ==="
query_dir=$(python3 -c "
import csv
rows = list(csv.DictReader(open('$MANIFEST'), delimiter='\t'))
print(rows[0]['query_dir'][:120])
")
ls "$query_dir" 2>/dev/null || echo "query_dir: $query_dir"
