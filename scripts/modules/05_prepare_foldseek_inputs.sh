#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-regression}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="local_wsl"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"

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

echo "===== MODULE 05: PREPARE FOLDSEEK INPUTS ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "DATE=$(date)"
echo

COLABFOLD_QC_TABLE_ROOT="${COLABFOLD_QC_TABLE_ROOT:-${PROJECT_ROOT}/01_colabfold/qc_tables}"
FOLDSEEK_ROOT="${FOLDSEEK_ROOT:-${PROJECT_ROOT}/02_foldseek}"

MODEL_SUMMARY="${COLABFOLD_QC_TABLE_ROOT}/${MODE}/${MODE}_colabfold_model_summary.tsv"
OUT_DIR="${FOLDSEEK_ROOT}/query_pdb_manifest"
QC_DIR="${FOLDSEEK_ROOT}/qc"

QUERY_MANIFEST="${OUT_DIR}/${MODE}_query_pdb_manifest.tsv"
MISSING_TABLE="${QC_DIR}/${MODE}_query_pdb_missing_or_invalid.tsv"
SUMMARY_TABLE="${QC_DIR}/${MODE}_query_pdb_manifest_summary.tsv"

mkdir -p "$OUT_DIR" "$QC_DIR"

if [ ! -s "$MODEL_SUMMARY" ]; then
  echo "HATA: ColabFold model summary yok veya boş: $MODEL_SUMMARY"
  exit 1
fi

"${PYTHON_BIN:-python3}" - "$MODE" "$MODEL_SUMMARY" "$QUERY_MANIFEST" "$MISSING_TABLE" "$SUMMARY_TABLE" "$PROJECT_ROOT" <<'PY'
import csv
import sys
from pathlib import Path

mode = sys.argv[1]
model_summary = Path(sys.argv[2])
query_manifest = Path(sys.argv[3])
missing_table = Path(sys.argv[4])
summary_table = Path(sys.argv[5])
project_root = Path(sys.argv[6])


def resolve_profile_path(raw_path):
    path_text = (raw_path or "").strip()
    path = Path(path_text)
    if path.exists():
        return path

    normalized = path_text.replace("\\", "/")
    marker = "/01_colabfold/outputs/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        candidate = project_root / "01_colabfold" / "outputs" / Path(suffix)
        if candidate.exists():
            return candidate

    return path

with model_summary.open() as f:
    rows = list(csv.DictReader(f, delimiter="\t"))

required = [
    "mode", "batch_id", "run_id", "protein_id", "family_label",
    "pdb_file", "ca_atoms", "plddt_mean", "ptm",
    "struct_conf_class", "model_status"
]

header = rows[0].keys() if rows else []
missing_cols = [c for c in required if c not in header]
if missing_cols:
    raise SystemExit("Eksik model_summary sütunları: " + ",".join(missing_cols))

out_rows = []
bad_rows = []

for r in rows:
    pdb = resolve_profile_path(r.get("pdb_file", ""))
    problems = []

    if r.get("model_status") != "OK":
        problems.append("model_status_not_OK")

    if not pdb.exists():
        problems.append("pdb_path_missing")
        atom_lines = 0
        ca_atoms_recount = 0
    else:
        atom_lines = 0
        ca_atoms_recount = 0
        with pdb.open() as pf:
            for line in pf:
                if line.startswith("ATOM"):
                    atom_lines += 1
                    parts = line.split()
                    if len(parts) > 2 and parts[2] == "CA":
                        ca_atoms_recount += 1

        if atom_lines == 0:
            problems.append("no_ATOM_lines")
        if ca_atoms_recount == 0:
            problems.append("no_CA_atoms")

    row = {
        "mode": mode,
        "batch_id": r.get("batch_id", ""),
        "run_id": r.get("run_id", ""),
        "protein_id": r.get("protein_id", ""),
        "family_label": r.get("family_label", ""),
        "query_pdb_file": str(pdb),
        "query_pdb_basename": pdb.name,
        "colabfold_plddt_mean": r.get("plddt_mean", ""),
        "colabfold_ptm": r.get("ptm", ""),
        "colabfold_struct_conf_class": r.get("struct_conf_class", ""),
        "colabfold_model_status": r.get("model_status", ""),
        "atom_lines": atom_lines,
        "ca_atoms": ca_atoms_recount,
    }
    out_rows.append(row)

    if problems:
        bad = dict(row)
        bad["problems"] = ",".join(problems)
        bad_rows.append(bad)

fields = [
    "mode", "batch_id", "run_id", "protein_id", "family_label",
    "query_pdb_file", "query_pdb_basename",
    "colabfold_plddt_mean", "colabfold_ptm",
    "colabfold_struct_conf_class", "colabfold_model_status",
    "atom_lines", "ca_atoms"
]

with query_manifest.open("w") as f:
    writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(out_rows)

bad_fields = fields + ["problems"]
with missing_table.open("w") as f:
    writer = csv.DictWriter(f, fieldnames=bad_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(bad_rows)

with summary_table.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerow(["mode", mode])
    writer.writerow(["input_model_summary_rows", len(rows)])
    writer.writerow(["query_pdb_manifest_rows", len(out_rows)])
    writer.writerow(["missing_or_invalid_rows", len(bad_rows)])
    writer.writerow(["unique_run_ids", len({r["run_id"] for r in out_rows})])
    writer.writerow(["unique_families", len({r["family_label"] for r in out_rows})])

print("query_manifest:", query_manifest)
print("missing_table:", missing_table)
print("summary_table:", summary_table)
print("query_pdb_manifest_rows:", len(out_rows))
print("missing_or_invalid_rows:", len(bad_rows))
PY

echo
echo "--- output files ---"
ls -lh "$QUERY_MANIFEST" "$MISSING_TABLE" "$SUMMARY_TABLE"

echo
echo "--- query manifest preview ---"
head -8 "$QUERY_MANIFEST"

echo
echo "--- missing/invalid table ---"
cat "$MISSING_TABLE"

echo
echo "--- summary ---"
cat "$SUMMARY_TABLE"

N_QUERY=$(tail -n +2 "$QUERY_MANIFEST" | wc -l)
N_BAD=$(tail -n +2 "$MISSING_TABLE" | wc -l)

echo
echo "query_manifest_records=$N_QUERY"
echo "missing_or_invalid_records=$N_BAD"

if [ "$MODE" = "regression" ]; then
  if [ "$N_QUERY" -eq 32 ] && [ "$N_BAD" -eq 0 ]; then
    echo "MODULE05_FOLDSEEK_INPUT_PREP_QC: PASS"
  else
    echo "MODULE05_FOLDSEEK_INPUT_PREP_QC: CHECK_NEEDED"
    exit 1
  fi
else
  if [ "$N_BAD" -eq 0 ]; then
    echo "MODULE05_FOLDSEEK_INPUT_PREP_QC: PASS"
  else
    echo "MODULE05_FOLDSEEK_INPUT_PREP_QC: CHECK_NEEDED"
    exit 1
  fi
fi
