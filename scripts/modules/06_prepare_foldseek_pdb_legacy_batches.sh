#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
cd "$PROJECT_ROOT"

MODE="regression_legacy_batches"
SOURCE_MODE="regression"

FOLDSEEK_BIN="/arf/home/yugur/tools/foldseek_tm_tools/foldseek/bin/foldseek"
PDB_DB="/arf/scratch/yugur/baps_faz_c_v2/structural_validation/foldseek_tm_align/refdb/pdb/pdb"

QUERY_MANIFEST="02_foldseek/query_pdb_manifest/${SOURCE_MODE}_query_pdb_manifest.tsv"

BATCH_ROOT="02_foldseek/querydb/${MODE}"
SEARCH_ROOT="02_foldseek/pdb_search/${MODE}"
TABLE_ROOT="02_foldseek/tables/${MODE}"
QC_ROOT="02_foldseek/qc/${MODE}"
LOG_ROOT="02_foldseek/logs/${MODE}"
TMP_ROOT="02_foldseek/tmp/${MODE}"
SBATCH_ROOT="02_foldseek/sbatch/${MODE}"

SBATCH_SCRIPT="${SBATCH_ROOT}/run_${MODE}_pdb_search_debug.sbatch"

mkdir -p "$BATCH_ROOT" "$SEARCH_ROOT" "$TABLE_ROOT" "$QC_ROOT" "$LOG_ROOT" "$TMP_ROOT" "$SBATCH_ROOT"

test -x "$FOLDSEEK_BIN"
test -s "${PDB_DB}.dbtype"
test -s "$QUERY_MANIFEST"

echo "===== MODULE 06 LEGACY BATCH PREP ====="
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "QUERY_MANIFEST=$QUERY_MANIFEST"
echo "DATE=$(date)"

echo
echo "===== 1) 4 LEGACY BATCH PDB KLASÖRÜ HAZIRLANIYOR ====="

rm -rf "$BATCH_ROOT"/batch*
mkdir -p "$BATCH_ROOT"/batch01 "$BATCH_ROOT"/batch02 "$BATCH_ROOT"/batch03 "$BATCH_ROOT"/batch04

"${PYTHON_BIN:-python3}" - "$QUERY_MANIFEST" "$BATCH_ROOT" <<'PY'
import csv
import shutil
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
batch_root = Path(sys.argv[2])

with manifest.open() as f:
    rows = list(csv.DictReader(f, delimiter="\t"))

if len(rows) != 32:
    raise SystemExit(f"Expected 32 regression rows, observed {len(rows)}")

for i, r in enumerate(rows):
    batch_no = i // 8 + 1
    batch_id = f"batch{batch_no:02d}"
    out_dir = batch_root / batch_id
    src = Path(r["query_pdb_file"])
    dst = out_dir / f'{r["run_id"]}.pdb'
    if not src.exists():
        raise SystemExit(f"Missing PDB: {src}")
    shutil.copy2(src, dst)

print("legacy_batches_created=4")
print("proteins_total=32")
PY

echo
echo "--- batch PDB counts ---"
for b in batch01 batch02 batch03 batch04; do
  echo -n "$b: "
  find "$BATCH_ROOT/$b" -maxdepth 1 -type f -name "*.pdb" | wc -l
done

echo
echo "===== 2) LEGACY DEBUG SBATCH YAZILIYOR ====="

cat > "$SBATCH_SCRIPT" <<SBATCH
#!/bin/bash
#SBATCH -J fs_pdb_legacy
#SBATCH -A yugur
#SBATCH -p debug
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 20
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH -o ${PROJECT_ROOT}/${LOG_ROOT}/legacy_pdb.%j.out
#SBATCH -e ${PROJECT_ROOT}/${LOG_ROOT}/legacy_pdb.%j.err

set -euo pipefail

cd ${PROJECT_ROOT}

echo "===== FOLDSEEK PDB LEGACY 4-BATCH SEARCH START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "PWD: \$(pwd)"

FOLDSEEK_BIN="${FOLDSEEK_BIN}"
PDB_DB="${PDB_DB}"
BATCH_ROOT="${BATCH_ROOT}"
SEARCH_ROOT="${SEARCH_ROOT}"
TABLE_ROOT="${TABLE_ROOT}"
QC_ROOT="${QC_ROOT}"
TMP_ROOT="${TMP_ROOT}"
QUERY_MANIFEST="${QUERY_MANIFEST}"

mkdir -p "\$SEARCH_ROOT" "\$TABLE_ROOT" "\$QC_ROOT" "\$TMP_ROOT"

echo
echo "===== CLEAN OLD LEGACY OUTPUTS ====="
rm -f "\$TABLE_ROOT"/*.tsv "\$QC_ROOT"/*.tsv
rm -rf "\$SEARCH_ROOT"/* "\$TMP_ROOT"/*
rm -f "\$BATCH_ROOT"/*_query_db*

echo
echo "===== RUN 4 BATCHES ====="

for b in batch01 batch02 batch03 batch04; do
  echo
  echo "===== LEGACY \$b ====="

  PDB_INPUT_DIR="\$BATCH_ROOT/\$b"
  QUERY_DB="\$BATCH_ROOT/\${b}_query_db"
  RESULT_DB="\$SEARCH_ROOT/\${b}_vs_pdb_result_db"
  TMP_DIR="\$TMP_ROOT/\${b}_tmp"
  OUT_TSV="\$TABLE_ROOT/\${b}_vs_pdb_foldseek_hits.tsv"

  mkdir -p "\$TMP_DIR"

  echo -n "PDB count for \$b: "
  find "\$PDB_INPUT_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l

  "\$FOLDSEEK_BIN" createdb "\$PDB_INPUT_DIR" "\$QUERY_DB"

  "\$FOLDSEEK_BIN" search "\$QUERY_DB" "\$PDB_DB" "\$RESULT_DB" "\$TMP_DIR" --threads 20 --max-seqs 50 -a

  "\$FOLDSEEK_BIN" convertalis "\$QUERY_DB" "\$PDB_DB" "\$RESULT_DB" "\$OUT_TSV.tmp" --format-output query,target,evalue,bits,prob,alntmscore,qtmscore,ttmscore,lddt,qcov,tcov,qlen,tlen

  echo -e "query\ttarget\tevalue\tbits\tprob\talntmscore\tqtmscore\tttmscore\tlddt\tqcov\ttcov\tqlen\ttlen\tbatch" > "\$OUT_TSV"
  awk -v OFS='\\t' -v batch="\$b" '{print \$0, batch}' "\$OUT_TSV.tmp" >> "\$OUT_TSV"
  rm -f "\$OUT_TSV.tmp"

  echo -n "hit rows for \$b: "
  tail -n +2 "\$OUT_TSV" | wc -l
done

echo
echo "===== MERGE LEGACY BATCH TABLES ====="

ALL_HITS="\$TABLE_ROOT/regression_legacy_vs_pdb_foldseek_all_hits.tsv"
BEST_FIRST="\$TABLE_ROOT/regression_legacy_vs_pdb_foldseek_best_hit_first_rank.tsv"
NOHIT="\$QC_ROOT/regression_legacy_vs_pdb_foldseek_nohit.tsv"
SUMMARY="\$QC_ROOT/regression_legacy_vs_pdb_foldseek_summary.tsv"

head -n 1 "\$TABLE_ROOT/batch01_vs_pdb_foldseek_hits.tsv" > "\$ALL_HITS"
for b in batch01 batch02 batch03 batch04; do
  tail -n +2 "\$TABLE_ROOT/\${b}_vs_pdb_foldseek_hits.tsv" >> "\$ALL_HITS"
done

"${PYTHON_BIN:-python3}" - "\$ALL_HITS" "\$QUERY_MANIFEST" "\$BEST_FIRST" "\$NOHIT" "\$SUMMARY" <<'PY'
import csv
import sys
from pathlib import Path

all_hits = Path(sys.argv[1])
query_manifest = Path(sys.argv[2])
best_first = Path(sys.argv[3])
nohit = Path(sys.argv[4])
summary = Path(sys.argv[5])

with query_manifest.open() as f:
    qrows = list(csv.DictReader(f, delimiter="\t"))
query_ids = [r["run_id"] for r in qrows]

with all_hits.open() as f:
    hits = list(csv.DictReader(f, delimiter="\t"))

first = {}
for h in hits:
    q = h["query"]
    if q not in first:
        first[q] = h

fields = ["query","target","evalue","bits","prob","alntmscore","qtmscore","ttmscore","lddt","qcov","tcov","qlen","tlen","batch"]

with best_first.open("w") as f:
    w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for q in query_ids:
        if q in first:
            w.writerow(first[q])

with nohit.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["query"])
    for q in query_ids:
        if q not in first:
            w.writerow([q])

with summary.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    w.writerow(["query_records", len(query_ids)])
    w.writerow(["all_hit_rows", len(hits)])
    w.writerow(["best_first_rows", sum(1 for q in query_ids if q in first)])
    w.writerow(["nohit_rows", sum(1 for q in query_ids if q not in first)])

print("all_hit_rows", len(hits))
print("best_first_rows", sum(1 for q in query_ids if q in first))
print("nohit_rows", sum(1 for q in query_ids if q not in first))
PY

echo
echo "===== LEGACY OUTPUT QC ====="
ls -lh "\$ALL_HITS" "\$BEST_FIRST" "\$NOHIT" "\$SUMMARY"
cat "\$SUMMARY"

echo
echo "FOLDSEEK_PDB_LEGACY_BATCH_SEARCH: DONE"
echo "DATE: \$(date)"
SBATCH

chmod +x "$SBATCH_SCRIPT"

echo
echo "===== 3) SBATCH KONTROL ====="
grep -E '^#SBATCH -J|^#SBATCH -A|^#SBATCH -p|^#SBATCH -c|^#SBATCH --mem|^#SBATCH --time' "$SBATCH_SCRIPT"

echo
echo "MODULE06_LEGACY_BATCH_PREP: OK"
