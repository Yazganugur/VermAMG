#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-test}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="truba"
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
    echo "HATA: MODE test, regression veya full olmalı."
    exit 1
    ;;
esac

echo "===== MODULE 02: PREPARE COLABFOLD BATCHES ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "DATE: $(date)"
echo

RUN_SET_ROOT="${RUN_SET_ROOT:-${PROJECT_ROOT}/run_sets}"
RUN_DIR="${RUN_SET_ROOT}/${MODE}"
INPUT_FASTA="${RUN_DIR}/${MODE}.colabfold.faa"
INPUT_IDMAP="${RUN_DIR}/${MODE}_id_map.tsv"

BATCH_ROOT="${PROJECT_ROOT}/01_colabfold/batches/${MODE}"
BATCH_MANIFEST="${BATCH_ROOT}/${MODE}_colabfold_batch_manifest.tsv"

case "$MODE" in
  test)
    TARGET_BATCHES="${TEST_TARGET_BATCHES:-1}"
    ;;
  regression)
    TARGET_BATCHES="${REGRESSION_TARGET_BATCHES:-4}"
    ;;
  full)
    TARGET_BATCHES="${FULL_TARGET_BATCHES:-8}"
    ;;
esac

echo "RUN_DIR=$RUN_DIR"
echo "INPUT_FASTA=$INPUT_FASTA"
echo "INPUT_IDMAP=$INPUT_IDMAP"
echo "BATCH_ROOT=$BATCH_ROOT"
echo "TARGET_BATCHES=$TARGET_BATCHES"

test -s "$INPUT_FASTA"
test -s "$INPUT_IDMAP"

case "$BATCH_ROOT" in
  "$PROJECT_ROOT"/01_colabfold/batches/*) ;;
  *)
    echo "HATA: Unsafe BATCH_ROOT outside PROJECT_ROOT: $BATCH_ROOT"
    exit 1
    ;;
esac

rm -rf "$BATCH_ROOT"
mkdir -p "$BATCH_ROOT"

"${PYTHON_BIN:-python3}" - "$MODE" "$INPUT_FASTA" "$INPUT_IDMAP" "$BATCH_ROOT" "$BATCH_MANIFEST" "$TARGET_BATCHES" <<'PY'
import csv
import math
import sys
from pathlib import Path

mode = sys.argv[1]
input_fasta = Path(sys.argv[2])
input_idmap = Path(sys.argv[3])
batch_root = Path(sys.argv[4])
batch_manifest = Path(sys.argv[5])
target_batches = int(sys.argv[6])

records = []
header = None
seq = []

with input_fasta.open() as f:
    for line in f:
        line = line.rstrip("\n")
        if line.startswith(">"):
            if header is not None:
                records.append((header, "".join(seq)))
            header = line[1:].strip().split()[0]
            seq = []
        else:
            seq.append(line.strip())
    if header is not None:
        records.append((header, "".join(seq)))

if not records:
    raise SystemExit("No FASTA records found.")

n_records = len(records)
target_batches = max(1, min(target_batches, n_records))
batch_size = math.ceil(n_records / target_batches)

idmap = {}
with input_idmap.open() as f:
    reader = csv.DictReader(f, delimiter="\t")
    for row in reader:
        idmap[row["run_id"]] = row

manifest_rows = []

for idx, start in enumerate(range(0, n_records, batch_size), 1):
    batch_records = records[start:start+batch_size]
    batch_id = f"batch{idx:03d}"
    batch_dir = batch_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_fasta = batch_dir / f"{mode}_{batch_id}.faa"
    with batch_fasta.open("w") as out:
        for rid, sequence in batch_records:
            out.write(f">{rid}\n")
            for j in range(0, len(sequence), 80):
                out.write(sequence[j:j+80] + "\n")

    for rid, sequence in batch_records:
        meta = idmap.get(rid, {})
        manifest_rows.append({
            "mode": mode,
            "batch_id": batch_id,
            "batch_fasta": str(batch_fasta),
            "run_id": rid,
            "protein_id": meta.get("protein_id", ""),
            "family_label": meta.get("family_label", ""),
            "aa_length": len(sequence),
        })

with batch_manifest.open("w") as out:
    fieldnames = ["mode", "batch_id", "batch_fasta", "run_id", "protein_id", "family_label", "aa_length"]
    writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(manifest_rows)

print(f"records={n_records}")
print(f"target_batches={target_batches}")
print(f"calculated_batch_size={batch_size}")
print(f"n_batches={(n_records + batch_size - 1)//batch_size}")
print(f"manifest={batch_manifest}")
PY

echo
echo "--- Batch QC ---"
N_INPUT=$(grep -c '^>' "$INPUT_FASTA")
N_BATCH_FASTA=$(find "$BATCH_ROOT" -type f -name "*.faa" | wc -l)
N_BATCH_RECORDS=$(find "$BATCH_ROOT" -type f -name "*.faa" -exec grep -h '^>' {} \; | wc -l)
N_MANIFEST_DATA=$(( $(wc -l < "$BATCH_MANIFEST") - 1 ))

echo "input_fasta_records=$N_INPUT"
echo "batch_fasta_files=$N_BATCH_FASTA"
echo "batch_fasta_records=$N_BATCH_RECORDS"
echo "manifest_records=$N_MANIFEST_DATA"

if [ "$N_INPUT" -ne "$N_BATCH_RECORDS" ]; then
  echo "HATA: Input FASTA protein sayısı ile batch FASTA protein sayısı eşleşmiyor."
  exit 1
fi

if [ "$N_INPUT" -ne "$N_MANIFEST_DATA" ]; then
  echo "HATA: Input FASTA protein sayısı ile batch manifest kayıt sayısı eşleşmiyor."
  exit 1
fi

echo
echo "--- Batch distribution ---"
cut -f2 "$BATCH_MANIFEST" | tail -n +2 | sort | uniq -c

echo
echo "--- Batch files ---"
find "$BATCH_ROOT" -type f | sort

echo
echo "--- Batch manifest preview ---"
head -20 "$BATCH_MANIFEST"

echo
echo "MODULE 02 PREPARE COLABFOLD BATCHES: OK"
