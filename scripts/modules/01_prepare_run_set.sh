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

echo "===== MODULE 01: PREPARE RUN SET ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "DATE: $(date)"
echo

RUN_SET_ROOT="${RUN_SET_ROOT:-${PROJECT_ROOT}/run_sets}"
RUN_DIR="${RUN_SET_ROOT}/${MODE}"
mkdir -p "$RUN_DIR"

RAW_FASTA="${RUN_DIR}/${MODE}.raw.faa"
OUT_FASTA="${RUN_DIR}/${MODE}.colabfold.faa"
OUT_IDMAP="${RUN_DIR}/${MODE}_id_map.tsv"
OUT_MANIFEST="${RUN_DIR}/${MODE}_manifest.txt"

rm -f "$RAW_FASTA" "$OUT_FASTA" "$OUT_IDMAP" "$OUT_MANIFEST"

if [ "$MODE" = "test" ]; then
  echo "--- Test mode: single protein selected for fast pipeline validation ---"

  SOURCE_FASTA="$REGRESSION_FASTA"
  TEST_MODE="${TEST_SELECTION_MODE:-first}"
  TEST_ID="${TEST_PROTEIN_ID:-}"

  echo "TEST_SELECTION_MODE=$TEST_MODE"
  echo "TEST_PROTEIN_ID=$TEST_ID"
  echo "SOURCE_FASTA=$SOURCE_FASTA"

  if [ "$TEST_MODE" = "first" ] || [ -z "$TEST_ID" ]; then
    echo "--- Selecting first sequence from regression/control FASTA ---"
    awk '
      BEGIN {keep=0; seen=0}
      /^>/ {
        if (seen==0) {keep=1; seen=1}
        else {keep=0}
      }
      keep {print}
    ' "$SOURCE_FASTA" > "$RAW_FASTA"
  else
    echo "--- Selecting exact/prefix-matched test protein ID ---"
    awk -v id="$TEST_ID" '
      BEGIN {keep=0; found=0}
      /^>/ {
        header=$0
        clean=header
        sub(/^>/,"",clean)
        split(clean,a," ")
        sid=a[1]
        core=sid
        sub(/\|.*/,"",core)
        keep=(sid==id || core==id || sid ~ ("^" id "(_|\\||$)"))
        if (keep) found=1
      }
      keep {print}
      END {
        if (found==0) exit 42
      }
    ' "$SOURCE_FASTA" > "$RAW_FASTA" || {
      echo "HATA: Test protein ID bulunamadı: $TEST_ID"
      echo "İlk 10 header:"
      grep -m10 '^>' "$SOURCE_FASTA"
      exit 1
    }
  fi

elif [ "$MODE" = "regression" ]; then
  echo "--- Regression mode: known control set selected ---"
  cp "$REGRESSION_FASTA" "$RAW_FASTA"

elif [ "$MODE" = "full" ]; then
  echo "--- Full mode: complete candidate set selected ---"
  cp "$FULL_CANDIDATE_FASTA" "$RAW_FASTA"
fi

echo
echo "--- Stable run ID FASTA and ID map are being generated ---"

"${PYTHON_BIN:-python3}" - "$MODE" "$RAW_FASTA" "$OUT_FASTA" "$OUT_IDMAP" "$FULL_CANDIDATE_TABLE" "$REGRESSION_CANDIDATES" <<'PY'
import csv
import re
import sys
from pathlib import Path

mode = sys.argv[1]
raw_fasta = Path(sys.argv[2])
out_fasta = Path(sys.argv[3])
out_idmap = Path(sys.argv[4])
full_table = Path(sys.argv[5])
reg_table = Path(sys.argv[6])

def sanitize(x: str) -> str:
    x = str(x) if x is not None else ""
    x = x.strip()
    x = re.sub(r"[^A-Za-z0-9_.-]+", "_", x)
    x = re.sub(r"_+", "_", x)
    x = x.strip("_")
    return x or "unknown"

def load_metadata_table(path: Path):
    meta = {}
    if not path.exists() or path.stat().st_size == 0:
        return meta
    with path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            pid = row.get("protein_id", "")
            if pid:
                meta[pid] = row
    return meta

meta = {}
meta.update(load_metadata_table(full_table))
meta.update(load_metadata_table(reg_table))

records = []
current_header = None
current_seq = []

with raw_fasta.open() as f:
    for line in f:
        line = line.rstrip("\n")
        if line.startswith(">"):
            if current_header is not None:
                records.append((current_header, "".join(current_seq)))
            current_header = line[1:].strip()
            current_seq = []
        else:
            current_seq.append(line.strip())
    if current_header is not None:
        records.append((current_header, "".join(current_seq)))

if not records:
    raise SystemExit("No FASTA records found.")

prefix = {"test": "QTEST", "regression": "QBENCH", "full": "QFULL"}.get(mode, "Q")

with out_fasta.open("w") as fo, out_idmap.open("w") as mo:
    writer = csv.writer(mo, delimiter="\t", lineterminator="\n")
    writer.writerow([
        "run_id",
        "original_fasta_header",
        "protein_id",
        "family_label",
        "mode",
        "raw_aa_length",
        "clean_aa_length",
        "sequence_sanitized",
        "source_note",
    ])

    for i, (header, seq) in enumerate(records, 1):
        first_token = header.split()[0]
        protein_id = first_token.split("|")[0]

        row = meta.get(protein_id, {})
        family = (
            row.get("family_label")
            or row.get("pfam_name")
            or row.get("kofam_ko_id")
            or row.get("dram_ko_id")
            or row.get("vibrant_ko_id")
            or row.get("eggnog_kegg_ko")
            or "unknown_family"
        )
        family_clean = sanitize(family)

        run_id = f"{prefix}{i:06d}_{family_clean}"

        raw_seq = seq.upper()
        # ColabFold-ready protein FASTA should not contain terminal stop symbols
        # or non-amino-acid characters. Keep common ambiguous amino-acid codes.
        allowed = set("ACDEFGHIKLMNPQRSTVWYXBZUO")
        clean_seq = "".join(aa for aa in raw_seq if aa in allowed)
        sequence_sanitized = "YES" if clean_seq != raw_seq else "NO"

        if not clean_seq:
            raise SystemExit(f"Empty sequence after sanitization for {protein_id}")

        fo.write(f">{run_id}\n")
        for j in range(0, len(clean_seq), 80):
            fo.write(clean_seq[j:j+80] + "\n")

        writer.writerow([
            run_id,
            header,
            protein_id,
            family,
            mode,
            len(raw_seq),
            len(clean_seq),
            sequence_sanitized,
            "stable_run_id_generated_from_input_fasta",
        ])
PY

echo "--- Run set QC ---"
if [ ! -s "$OUT_FASTA" ]; then
  echo "HATA: OUT_FASTA boş veya yok: $OUT_FASTA"
  exit 1
fi

N_FASTA=$(grep -c '^>' "$OUT_FASTA")
N_RAW=$(grep -c '^>' "$RAW_FASTA")
N_IDMAP_DATA=$(( $(wc -l < "$OUT_IDMAP") - 1 ))

echo "raw_fasta=$RAW_FASTA"
echo "colabfold_fasta=$OUT_FASTA"
echo "idmap=$OUT_IDMAP"
echo "raw_fasta_proteins=$N_RAW"
echo "colabfold_fasta_proteins=$N_FASTA"
echo "idmap_records=$N_IDMAP_DATA"

if [ "$N_FASTA" -ne "$N_IDMAP_DATA" ]; then
  echo "HATA: ColabFold FASTA protein sayısı ile ID map kayıt sayısı eşleşmiyor."
  exit 1
fi

if [ "$N_FASTA" -ne "$N_RAW" ]; then
  echo "HATA: Raw FASTA ve ColabFold FASTA protein sayıları eşleşmiyor."
  exit 1
fi

if [ "$MODE" = "test" ] && [ "$N_FASTA" -ne 1 ]; then
  echo "HATA: Test mode tam 1 protein içermeli."
  exit 1
fi

if [ "$MODE" = "regression" ] && [ "$N_FASTA" -ne 32 ]; then
  echo "HATA: Regression mode tam 32 protein içermeli."
  exit 1
fi

if [ "$MODE" = "full" ] && [ "$N_FASTA" -ne 237 ]; then
  echo "HATA: Full mode tam 237 protein içermeli."
  exit 1
fi

{
  echo "BAPS Faz C v2 — Structural Validation Master Pipeline Run Set Manifest"
  echo "Created: $(date)"
  echo "Mode raw: $MODE_RAW"
  echo "Mode normalized: $MODE"
  echo "Run directory: $RUN_DIR"
  echo "Raw FASTA: $RAW_FASTA"
  echo "ColabFold FASTA: $OUT_FASTA"
  echo "ID map: $OUT_IDMAP"
  echo "FASTA protein count: $N_FASTA"
  echo "ID map records: $N_IDMAP_DATA"
  echo
  echo "First raw FASTA header:"
  grep -m1 '^>' "$RAW_FASTA"
  echo
  echo "First ColabFold FASTA header:"
  grep -m1 '^>' "$OUT_FASTA"
} > "$OUT_MANIFEST"

echo
echo "--- Manifest ---"
cat "$OUT_MANIFEST"

echo
echo "MODULE 01 PREPARE RUN SET: OK"
