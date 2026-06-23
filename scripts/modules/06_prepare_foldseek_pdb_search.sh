#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-regression}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="truba"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"
cd "$PROJECT_ROOT"

case "$MODE_RAW" in
  smoke) MODE="test" ;;
  pilot32) MODE="regression" ;;
  tier1_full) MODE="full" ;;
  test|regression|full) MODE="$MODE_RAW" ;;
  *)
    echo "HATA: MODE test, regression veya full olmalı."
    exit 1
    ;;
esac

echo "===== MODULE 06: PREPARE FOLDSEEK PDB SEARCH ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "DATE=$(date)"
echo

if [[ "${EXECUTION_BACKEND:-}" != "slurm" ]]; then
  echo "M06 Foldseek PDB sbatch generator supports EXECUTION_BACKEND=slurm only; for local backend use scripts/modules/06_prepare_foldseek_pdb_local_runner.sh"
  exit 0
fi

: "${FOLDSEEK_PDB_SLURM_ACCOUNT:?HATA: FOLDSEEK_PDB_SLURM_ACCOUNT unset}"
: "${FOLDSEEK_PDB_SLURM_PARTITION:?HATA: FOLDSEEK_PDB_SLURM_PARTITION unset}"
: "${FOLDSEEK_PDB_SLURM_CPUS:?HATA: FOLDSEEK_PDB_SLURM_CPUS unset}"
: "${FOLDSEEK_PDB_SLURM_MEM:?HATA: FOLDSEEK_PDB_SLURM_MEM unset}"
: "${FOLDSEEK_PDB_SLURM_TIME:?HATA: FOLDSEEK_PDB_SLURM_TIME unset}"
FOLDSEEK_PDB_THREADS="${FOLDSEEK_PDB_THREADS:-${FOLDSEEK_PDB_SLURM_CPUS}}"

FOLDSEEK_BIN="${FOLDSEEK_BIN}"
PDB_DB="${PDB_FOLDSEEK_DB}"

QUERY_MANIFEST="02_foldseek/query_pdb_manifest/${MODE}_query_pdb_manifest.tsv"

PDB_INPUT_DIR="02_foldseek/querydb/${MODE}/pdb_inputs"
QUERY_DB="02_foldseek/querydb/${MODE}/${MODE}_query_db"
RESULT_DB="02_foldseek/pdb_search/${MODE}/${MODE}_vs_pdb_result_db"
TMP_DIR="02_foldseek/tmp/${MODE}/pdb_search_tmp"

ALL_HITS="02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_all_hits.tsv"
BEST_HITS="02_foldseek/tables/${MODE}/${MODE}_vs_pdb_foldseek_best_hit_per_query.tsv"
NOHIT_TABLE="02_foldseek/qc/${MODE}/${MODE}_vs_pdb_foldseek_nohit.tsv"
RUN_SUMMARY="02_foldseek/qc/${MODE}/${MODE}_vs_pdb_foldseek_run_summary.tsv"

SBATCH_DIR="02_foldseek/sbatch/${MODE}"
SBATCH_SCRIPT="${SBATCH_DIR}/run_${MODE}_foldseek_pdb_search.sbatch"

mkdir -p "$PDB_INPUT_DIR" "$(dirname "$RESULT_DB")" "$TMP_DIR" "$(dirname "$ALL_HITS")" "$(dirname "$NOHIT_TABLE")" "$SBATCH_DIR" "02_foldseek/logs/${MODE}"

test -x "$FOLDSEEK_BIN"
test -s "$QUERY_MANIFEST"
test -s "${PDB_DB}.dbtype"

echo "--- query PDB input dir temizleniyor ---"
rm -f "$PDB_INPUT_DIR"/*.pdb

echo "--- query PDB dosyaları manifestten kopyalanıyor ---"
"${PYTHON_BIN:-python3}" - "$QUERY_MANIFEST" "$PDB_INPUT_DIR" <<'PY'
import csv
import shutil
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

with manifest.open() as f:
    rows = list(csv.DictReader(f, delimiter="\t"))

copied = 0
for r in rows:
    run_id = r["run_id"]
    src = Path(r["query_pdb_file"])
    if not src.exists():
        raise SystemExit(f"Missing source PDB for {run_id}: {src}")
    dst = out_dir / f"{run_id}.pdb"
    shutil.copy2(src, dst)
    copied += 1

print(f"copied_pdb={copied}")
PY

echo
echo "--- copied PDB count ---"
find "$PDB_INPUT_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l

echo
echo "--- sbatch script yazılıyor ---"
cat > "$SBATCH_SCRIPT" <<SBATCH
#!/bin/bash
#SBATCH -J fs_${MODE}_pdb
#SBATCH -A ${FOLDSEEK_PDB_SLURM_ACCOUNT}
#SBATCH -p ${FOLDSEEK_PDB_SLURM_PARTITION}
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c ${FOLDSEEK_PDB_SLURM_CPUS}
#SBATCH --mem=${FOLDSEEK_PDB_SLURM_MEM}
#SBATCH --time=${FOLDSEEK_PDB_SLURM_TIME}
#SBATCH -o ${PROJECT_ROOT}/02_foldseek/logs/${MODE}/${MODE}_foldseek_pdb.%j.out
#SBATCH -e ${PROJECT_ROOT}/02_foldseek/logs/${MODE}/${MODE}_foldseek_pdb.%j.err

set -euo pipefail

cd ${PROJECT_ROOT}

echo "===== FOLDSEEK PDB SEARCH START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "PWD: \$(pwd)"
echo "MODE: ${MODE}"

FOLDSEEK_BIN="${FOLDSEEK_BIN}"
FOLDSEEK_PDB_THREADS="${FOLDSEEK_PDB_THREADS}"
PDB_DB="${PDB_DB}"
PDB_INPUT_DIR="${PDB_INPUT_DIR}"
QUERY_DB="${QUERY_DB}"
RESULT_DB="${RESULT_DB}"
TMP_DIR="${TMP_DIR}"
ALL_HITS="${ALL_HITS}"
BEST_HITS="${BEST_HITS}"
NOHIT_TABLE="${NOHIT_TABLE}"
RUN_SUMMARY="${RUN_SUMMARY}"

echo
echo "===== INPUT QC ====="
ls -lh "\$FOLDSEEK_BIN"
ls -lh "\${PDB_DB}.dbtype"
echo -n "query PDB count: "
find "\$PDB_INPUT_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l

echo
echo "===== CLEAN OLD DB/RESULTS ====="
rm -rf "\$TMP_DIR"
mkdir -p "\$TMP_DIR"
rm -f "\$QUERY_DB"* "\$RESULT_DB"* "\$ALL_HITS" "\$BEST_HITS" "\$NOHIT_TABLE" "\$RUN_SUMMARY"

echo
echo "===== FOLDSEEK CREATEDB ====="
"\$FOLDSEEK_BIN" createdb "\$PDB_INPUT_DIR" "\$QUERY_DB"

echo
echo "===== FOLDSEEK SEARCH VS PDB ====="
"\$FOLDSEEK_BIN" search "\$QUERY_DB" "\$PDB_DB" "\$RESULT_DB" "\$TMP_DIR" --threads "\$FOLDSEEK_PDB_THREADS" --max-seqs 50 -a

echo
echo "===== FOLDSEEK CONVERTALIS ====="
"\$FOLDSEEK_BIN" convertalis "\$QUERY_DB" "\$PDB_DB" "\$RESULT_DB" "\$ALL_HITS.tmp" --format-output query,target,evalue,bits,prob,alntmscore,qtmscore,ttmscore,lddt,qcov,tcov,qlen,tlen

echo -e "query\ttarget\tevalue\tbits\tprob\talntmscore\tqtmscore\tttmscore\tlddt\tqcov\ttcov\tqlen\ttlen\tbatch" > "\$ALL_HITS"
awk -v OFS='\\t' '{print \$0, "pdb_search"}' "\$ALL_HITS.tmp" >> "\$ALL_HITS"
rm -f "\$ALL_HITS.tmp"

echo
echo "===== BEST HIT PER QUERY ====="
"${PYTHON_BIN:-python3}" - "\$ALL_HITS" "\$BEST_HITS" "\$NOHIT_TABLE" "${QUERY_MANIFEST}" <<'PY'
import csv
import sys
from pathlib import Path

all_hits = Path(sys.argv[1])
best_hits = Path(sys.argv[2])
nohit_table = Path(sys.argv[3])
query_manifest = Path(sys.argv[4])

with query_manifest.open() as f:
    qrows = list(csv.DictReader(f, delimiter="\t"))

all_queries = [r["run_id"] for r in qrows]

with all_hits.open() as f:
    hits = list(csv.DictReader(f, delimiter="\t"))

best = {}
for h in hits:
    q = h["query"]
    try:
        score = float(h["bits"])
    except Exception:
        score = -1
    if q not in best or score > best[q][0]:
        best[q] = (score, h)

fields = ["query","target","evalue","bits","prob","alntmscore","qtmscore","ttmscore","lddt","qcov","tcov","qlen","tlen","batch"]
with best_hits.open("w") as f:
    writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for q in all_queries:
        if q in best:
            writer.writerow(best[q][1])

with nohit_table.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["query"])
    for q in all_queries:
        if q not in best:
            writer.writerow([q])
PY

echo
echo "===== RUN SUMMARY ====="
{
  echo -e "metric\tvalue"
  echo -e "mode\t${MODE}"
  echo -e "query_pdb_count\t\$(find "\$PDB_INPUT_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l)"
  echo -e "all_hit_rows\t\$(( \$(wc -l < "\$ALL_HITS") - 1 ))"
  echo -e "best_hit_rows\t\$(( \$(wc -l < "\$BEST_HITS") - 1 ))"
  echo -e "nohit_rows\t\$(( \$(wc -l < "\$NOHIT_TABLE") - 1 ))"
} > "\$RUN_SUMMARY"

cat "\$RUN_SUMMARY"

echo
echo "===== OUTPUT QC ====="
ls -lh "\$ALL_HITS" "\$BEST_HITS" "\$NOHIT_TABLE" "\$RUN_SUMMARY"

echo "FOLDSEEK_PDB_SEARCH: DONE"
echo "DATE: \$(date)"
SBATCH

chmod +x "$SBATCH_SCRIPT"

echo
echo "--- sbatch preview ---"
sed -n '1,120p' "$SBATCH_SCRIPT"

echo
echo "MODULE06_PREPARE_FOLDSEEK_PDB_SEARCH: OK"
