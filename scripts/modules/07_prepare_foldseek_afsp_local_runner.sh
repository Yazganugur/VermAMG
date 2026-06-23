#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-test}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="local_wsl"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"
CONFIG="${PROJECT_ROOT}/config/tier1_master_config.env"
source "$CONFIG"

case "$MODE_RAW" in
  smoke) MODE="test" ;;
  pilot32) MODE="regression" ;;
  tier1_full) MODE="full" ;;
  test|regression|full) MODE="$MODE_RAW" ;;
  *)
    echo "HATA: MODE test, regression veya full olmali. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

echo "===== MODULE 07 LOCAL: PREPARE FOLDSEEK AFSP LOCAL RUNNER ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "VERMAMG_PROFILE: $VERMAMG_PROFILE"
echo "EXECUTION_BACKEND: ${EXECUTION_BACKEND:-NA}"
echo "DATE: $(date)"
echo

: "${FOLDSEEK_BIN:?HATA: FOLDSEEK_BIN unset}"
: "${AFSP_FOLDSEEK_DB:?HATA: AFSP_FOLDSEEK_DB unset}"

FOLDSEEK_AFSP_THREADS="${FOLDSEEK_AFSP_THREADS:-${FOLDSEEK_THREADS:-4}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

FOLDSEEK_ROOT="${PROJECT_ROOT}/02_foldseek"
QUERY_MANIFEST="${FOLDSEEK_ROOT}/query_pdb_manifest/${MODE}_query_pdb_manifest.tsv"
LOCAL_RUN_ROOT="${FOLDSEEK_ROOT}/local_runs/${MODE}"
LOCAL_RUNNER="${LOCAL_RUN_ROOT}/run${MODE}_foldseek_afsp_local.sh"
RUN_MANIFEST="${FOLDSEEK_ROOT}/${MODE}_foldseek_afsp_local_run_manifest.tsv"

case "$LOCAL_RUN_ROOT" in
  "$FOLDSEEK_ROOT"/local_runs/*) ;;
  *)
    echo "HATA: Unsafe LOCAL_RUN_ROOT outside FOLDSEEK_ROOT: $LOCAL_RUN_ROOT"
    exit 1
    ;;
esac

case "$RUN_MANIFEST" in
  "$FOLDSEEK_ROOT"/*_foldseek_afsp_local_run_manifest.tsv) ;;
  *)
    echo "HATA: Unsafe RUN_MANIFEST outside FOLDSEEK_ROOT: $RUN_MANIFEST"
    exit 1
    ;;
esac

test -x "$FOLDSEEK_BIN" || { echo "HATA: FOLDSEEK_BIN not executable: $FOLDSEEK_BIN"; exit 1; }
test -s "${AFSP_FOLDSEEK_DB}.dbtype" || { echo "HATA: AFSP_FOLDSEEK_DB dbtype missing: ${AFSP_FOLDSEEK_DB}.dbtype"; exit 1; }
test -s "$QUERY_MANIFEST" || { echo "HATA: query manifest missing or empty: $QUERY_MANIFEST"; exit 1; }
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "HATA: PYTHON_BIN not found: $PYTHON_BIN"; exit 1; }

"$PYTHON_BIN" - "$QUERY_MANIFEST" <<'PY'
import csv
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
with manifest.open() as f:
    rows = list(csv.DictReader(f, delimiter="\t"))

if not rows:
    raise SystemExit(f"HATA: query manifest has no data rows: {manifest}")

missing = []
for r in rows:
    src = Path(r.get("query_pdb_file", ""))
    if not src.exists():
        missing.append(f'{r.get("run_id", "NA")}:{src}')

if missing:
    raise SystemExit("HATA: missing query PDB files: " + "; ".join(missing[:10]))

print(f"query_pdb_manifest_rows={len(rows)}")
PY

mkdir -p "$LOCAL_RUN_ROOT"

cat > "$LOCAL_RUNNER" <<RUNNER
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$PROJECT_ROOT"
MODE="$MODE"
FOLDSEEK_ROOT="$FOLDSEEK_ROOT"
FOLDSEEK_BIN="$FOLDSEEK_BIN"
FOLDSEEK_AFSP_THREADS="$FOLDSEEK_AFSP_THREADS"
AFSP_DB="$AFSP_FOLDSEEK_DB"
PYTHON_BIN="$PYTHON_BIN"
QUERY_MANIFEST="$QUERY_MANIFEST"

PDB_INPUT_DIR="\$FOLDSEEK_ROOT/querydb/\$MODE/pdb_inputs"
QUERY_DB="\$FOLDSEEK_ROOT/querydb/\$MODE/\${MODE}_query_db"
RESULT_DB="\$FOLDSEEK_ROOT/afsp_search/\$MODE/\${MODE}_vs_afsp_result_db"
TMP_DIR="\$FOLDSEEK_ROOT/tmp/\$MODE/afsp_search_tmp"

ALL_HITS="\$FOLDSEEK_ROOT/tables/\$MODE/\${MODE}_vs_afsp_foldseek_all_hits.tsv"
BEST_HITS="\$FOLDSEEK_ROOT/tables/\$MODE/\${MODE}_vs_afsp_foldseek_best_hit_per_query.tsv"
NOHIT_TABLE="\$FOLDSEEK_ROOT/qc/\$MODE/\${MODE}_vs_afsp_foldseek_nohit.tsv"
RUN_SUMMARY="\$FOLDSEEK_ROOT/qc/\$MODE/\${MODE}_vs_afsp_foldseek_run_summary.tsv"

fatal() {
  echo "HATA: \$*" >&2
  exit 1
}

require_under_foldseek() {
  local label="\$1"
  local path="\$2"
  [ -n "\$path" ] || fatal "\$label is empty"
  case "\$path" in
    "\$FOLDSEEK_ROOT"/*) ;;
    *) fatal "\$label outside FOLDSEEK_ROOT: \$path" ;;
  esac
}

cd "\$PROJECT_ROOT"

echo "===== FOLDSEEK AFSP LOCAL RUNNER START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "PWD: \$(pwd)"
echo "MODE: \$MODE"
echo "FOLDSEEK_ROOT: \$FOLDSEEK_ROOT"
echo "QUERY_MANIFEST: \$QUERY_MANIFEST"
echo "AFSP_DB: \$AFSP_DB"
echo "THREADS: \$FOLDSEEK_AFSP_THREADS"

test -x "\$FOLDSEEK_BIN" || fatal "FOLDSEEK_BIN not executable: \$FOLDSEEK_BIN"
test -s "\${AFSP_DB}.dbtype" || fatal "AFSP dbtype missing: \${AFSP_DB}.dbtype"
test -s "\$QUERY_MANIFEST" || fatal "query manifest missing or empty: \$QUERY_MANIFEST"
command -v "\$PYTHON_BIN" >/dev/null 2>&1 || fatal "PYTHON_BIN not found: \$PYTHON_BIN"

require_under_foldseek "PDB_INPUT_DIR" "\$PDB_INPUT_DIR"
require_under_foldseek "QUERY_DB" "\$QUERY_DB"
require_under_foldseek "RESULT_DB" "\$RESULT_DB"
require_under_foldseek "TMP_DIR" "\$TMP_DIR"
require_under_foldseek "ALL_HITS" "\$ALL_HITS"
require_under_foldseek "BEST_HITS" "\$BEST_HITS"
require_under_foldseek "NOHIT_TABLE" "\$NOHIT_TABLE"
require_under_foldseek "RUN_SUMMARY" "\$RUN_SUMMARY"

mkdir -p "\$PDB_INPUT_DIR" "\$(dirname "\$RESULT_DB")" "\$TMP_DIR" "\$(dirname "\$ALL_HITS")" "\$(dirname "\$NOHIT_TABLE")"

echo
echo "===== CLEAN QUERY PDB INPUTS ====="
rm -f "\$PDB_INPUT_DIR"/*.pdb

echo
echo "===== COPY QUERY PDB FILES ====="
"\$PYTHON_BIN" - "\$QUERY_MANIFEST" "\$PDB_INPUT_DIR" <<'PY'
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
echo "===== QUERY PDB COUNT ====="
find "\$PDB_INPUT_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l

echo
echo "===== CLEAN OLD AFSP DB/RESULTS ====="
rm -rf "\$TMP_DIR"
mkdir -p "\$TMP_DIR"
rm -f "\$QUERY_DB"* "\$RESULT_DB"* "\$ALL_HITS" "\$BEST_HITS" "\$NOHIT_TABLE" "\$RUN_SUMMARY"

echo
echo "===== FOLDSEEK CREATEDB ====="
"\$FOLDSEEK_BIN" createdb "\$PDB_INPUT_DIR" "\$QUERY_DB"

echo
echo "===== FOLDSEEK SEARCH VS AFSP ====="
"\$FOLDSEEK_BIN" search "\$QUERY_DB" "\$AFSP_DB" "\$RESULT_DB" "\$TMP_DIR" --threads "\$FOLDSEEK_AFSP_THREADS" --max-seqs 50 -a

echo
echo "===== FOLDSEEK CONVERTALIS ====="
"\$FOLDSEEK_BIN" convertalis "\$QUERY_DB" "\$AFSP_DB" "\$RESULT_DB" "\$ALL_HITS.tmp" --format-output query,target,evalue,bits,prob,alntmscore,qtmscore,ttmscore,lddt,qcov,tcov,qlen,tlen

echo -e "query\ttarget\tevalue\tbits\tprob\talntmscore\tqtmscore\tttmscore\tlddt\tqcov\ttcov\tqlen\ttlen\tbatch" > "\$ALL_HITS"
awk -v OFS='\\t' '{print \$0, "afsp_search"}' "\$ALL_HITS.tmp" >> "\$ALL_HITS"
rm -f "\$ALL_HITS.tmp"

echo
echo "===== BEST HIT PER QUERY ====="
"\$PYTHON_BIN" - "\$ALL_HITS" "\$BEST_HITS" "\$NOHIT_TABLE" "\$QUERY_MANIFEST" <<'PY'
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
  echo -e "mode\t\$MODE"
  echo -e "query_pdb_count\t\$(find "\$PDB_INPUT_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l)"
  echo -e "threads\t\$FOLDSEEK_AFSP_THREADS"
  echo -e "afsp_all_hit_rows\t\$(( \$(wc -l < "\$ALL_HITS") - 1 ))"
  echo -e "afsp_best_hit_rows\t\$(( \$(wc -l < "\$BEST_HITS") - 1 ))"
  echo -e "afsp_nohit_rows\t\$(( \$(wc -l < "\$NOHIT_TABLE") - 1 ))"
} > "\$RUN_SUMMARY"

cat "\$RUN_SUMMARY"

echo
echo "===== OUTPUT QC ====="
ls -lh "\$ALL_HITS" "\$BEST_HITS" "\$NOHIT_TABLE" "\$RUN_SUMMARY"

echo "FOLDSEEK_AFSP_LOCAL_SEARCH: DONE"
echo "DATE: \$(date)"
RUNNER

chmod +x "$LOCAL_RUNNER"

printf "mode\tquery_manifest\tafsp_db\tlocal_runner\tfoldseek_bin\tthreads\tstatus\n" > "$RUN_MANIFEST"
printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
  "$MODE" "$QUERY_MANIFEST" "$AFSP_FOLDSEEK_DB" "$LOCAL_RUNNER" "$FOLDSEEK_BIN" "$FOLDSEEK_AFSP_THREADS" "PREPARED" >> "$RUN_MANIFEST"

echo
echo "--- Foldseek AFSP local run manifest ---"
cat "$RUN_MANIFEST"

echo
echo "--- Foldseek AFSP local runner ---"
ls -lh "$LOCAL_RUNNER"

echo
echo "MODULE07_PREPARE_FOLDSEEK_AFSP_LOCAL_RUNNER: OK"
