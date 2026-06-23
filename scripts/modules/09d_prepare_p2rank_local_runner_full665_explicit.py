#!/usr/bin/env python3
"""Generate explicit full665 local P2Rank runners.

The generic shell runner normalizes ``full`` to ``tier1_full``. This helper is
therefore intentionally full-path explicit and writes only under
``04_p2rank/full``.
"""

from __future__ import annotations

import argparse
import csv
import os
import stat
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODE_ROOT = PROJECT_ROOT / "04_p2rank/full"
LOCAL_RUN_DIR = MODE_ROOT / "local_runs"
QUERY_MANIFEST = MODE_ROOT / "input_manifests/full_p2rank_query_model_manifest.tsv"
REFERENCE_MANIFEST = MODE_ROOT / "input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"
QUERY_RUNNER = LOCAL_RUN_DIR / "runfull_p2rank_query_models_local.sh"
REFERENCE_RUNNER = LOCAL_RUN_DIR / "runfull_p2rank_reference_resolved_unique_local.sh"
RUN_MANIFEST = MODE_ROOT / "full_p2rank_local_run_manifest.tsv"
QUERY_OUT_ROOT = MODE_ROOT / "query_models/all"
REFERENCE_OUT_ROOT = MODE_ROOT / "reference_models/resolved_unique"
P2RANK_CMD = PROJECT_ROOT / "resources/tools/p2rank/p2rank_2.5.1/prank"
P2RANK_JAR = PROJECT_ROOT / "resources/tools/p2rank/p2rank_2.5.1/bin/p2rank.jar"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate explicit full665 P2Rank local runners.")
    parser.add_argument("--write", action="store_true", help="Write runner scripts. Default is audit-only.")
    parser.add_argument("--chunk-size", type=int, default=64)
    parser.add_argument("--threads", type=int, default=4)
    return parser.parse_args()


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def require_under(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def existing_outputs() -> list[Path]:
    targets = [
        QUERY_RUNNER,
        REFERENCE_RUNNER,
        RUN_MANIFEST,
        QUERY_OUT_ROOT / "query_p2rank_run_manifest.tsv",
        QUERY_OUT_ROOT / "query_p2rank_failed.tsv",
        REFERENCE_OUT_ROOT / "reference_p2rank_run_manifest.tsv",
        REFERENCE_OUT_ROOT / "reference_p2rank_failed.tsv",
    ]
    return [path for path in targets if path.exists()]


def validate_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    for path in (QUERY_MANIFEST, REFERENCE_MANIFEST, P2RANK_CMD, P2RANK_JAR):
        if not path.exists():
            raise SystemExit(f"ERROR: required input missing: {path}")

    query_rows = read_tsv(QUERY_MANIFEST)
    ref_rows = read_tsv(REFERENCE_MANIFEST)

    query_missing = [r for r in query_rows if not (PROJECT_ROOT / r["query_model_pdb"]).is_file()]
    ref_missing = [r for r in ref_rows if not (PROJECT_ROOT / r["reference_file_path"]).is_file()]
    if query_missing:
        raise SystemExit(f"ERROR: missing query PDB paths: {len(query_missing)}")
    if ref_missing:
        raise SystemExit(f"ERROR: missing reference PDB paths: {len(ref_missing)}")

    return query_rows, ref_rows


def runner_template(role: str, threads: int, chunk_size: int) -> str:
    if role == "query":
        manifest = rel(QUERY_MANIFEST)
        out_root = rel(QUERY_OUT_ROOT)
        allowed_root = "04_p2rank/full/query_models"
        run_log = "query_p2rank_run_manifest.tsv"
        fail_log = "query_p2rank_failed.tsv"
        dataset_subdir = "datasets/query"
        expected_file = "query_expected.tsv"
        chunk_prefix = "query_chunk"
        extract_python = r'''
import csv
import math
import os
import sys
from pathlib import Path

project = Path(os.environ["PROJECT_ROOT"])
manifest = project / os.environ["INPUT_MANIFEST"]
dataset_dir = project / os.environ["DATASET_DIR"]
expected = project / os.environ["EXPECTED_TSV"]
chunk_size = int(os.environ["CHUNK_SIZE"])
dataset_dir.mkdir(parents=True, exist_ok=True)

with manifest.open(newline="", errors="replace") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

fields = ["query","family","query_model_pdb","abs_pdb","stem","out_dir"]
with expected.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        pdb_rel = row["query_model_pdb"]
        pdb_abs = project / pdb_rel
        writer.writerow({
            "query": row["query"],
            "family": row["family"],
            "query_model_pdb": pdb_rel,
            "abs_pdb": str(pdb_abs),
            "stem": pdb_abs.stem,
            "out_dir": os.environ["OUT_ROOT"],
        })

for old in dataset_dir.glob("query_chunk_*.ds"):
    old.unlink()

for idx in range(0, len(rows), chunk_size):
    chunk = rows[idx:idx + chunk_size]
    ds = dataset_dir / f"query_chunk_{idx // chunk_size + 1:04d}.ds"
    with ds.open("w") as handle:
        for row in chunk:
            handle.write(str(project / row["query_model_pdb"]) + "\n")

print(f"dataset_chunks\t{math.ceil(len(rows) / chunk_size)}")
print(f"dataset_rows\t{len(rows)}")
'''
        finalize_python = r'''
import csv
import os
from pathlib import Path

project = Path(os.environ["PROJECT_ROOT"])
expected = project / os.environ["EXPECTED_TSV"]
out_root = project / os.environ["OUT_ROOT"]
run_log = project / os.environ["RUN_LOG"]
fail_log = project / os.environ["FAIL_LOG"]

def rel(path):
    return str(path.relative_to(project))

def find_csv(stem, suffix):
    candidates = []
    candidates.extend(out_root.rglob(f"{stem}_{suffix}.csv"))
    candidates.extend(out_root.rglob(f"{stem}.pdb_{suffix}.csv"))
    if not candidates:
        candidates = [p for p in out_root.rglob(f"*_{suffix}.csv") if stem in p.name]
    candidates = sorted(set(candidates))
    return candidates[0] if candidates else None

with expected.open(newline="", errors="replace") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

run_fields = ["query","family","query_model_pdb","out_dir","status","prediction_csv","residue_csv","pocket_rows"]
fail_fields = ["query","family","query_model_pdb","error"]
run_rows = []
fail_rows = []

for row in rows:
    pred = find_csv(row["stem"], "predictions")
    res = find_csv(row["stem"], "residues")
    status = "OK"
    error = ""
    if not pred or not pred.is_file():
        status = "MISSING_PREDICTION_CSV"
        error = status
    elif not res or not res.is_file():
        status = "MISSING_RESIDUE_CSV"
        error = status

    pocket_rows = "0"
    if pred and pred.is_file():
        with pred.open(errors="replace") as handle:
            pocket_rows = str(max(0, sum(1 for _ in handle) - 1))

    run_rows.append({
        "query": row["query"],
        "family": row["family"],
        "query_model_pdb": row["query_model_pdb"],
        "out_dir": row["out_dir"],
        "status": status,
        "prediction_csv": rel(pred) if pred else "",
        "residue_csv": rel(res) if res else "",
        "pocket_rows": pocket_rows,
    })
    if error:
        fail_rows.append({
            "query": row["query"],
            "family": row["family"],
            "query_model_pdb": row["query_model_pdb"],
            "error": error,
        })

with run_log.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=run_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(run_rows)

with fail_log.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fail_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(fail_rows)

print(f"query run log rows: {len(run_rows)}")
print(f"query failed rows: {len(fail_rows)}")
if fail_rows:
    raise SystemExit(2)
'''
    else:
        manifest = rel(REFERENCE_MANIFEST)
        out_root = rel(REFERENCE_OUT_ROOT)
        allowed_root = "04_p2rank/full/reference_models"
        run_log = "reference_p2rank_run_manifest.tsv"
        fail_log = "reference_p2rank_failed.tsv"
        dataset_subdir = "datasets/reference"
        expected_file = "reference_expected.tsv"
        chunk_prefix = "reference_chunk"
        extract_python = r'''
import csv
import math
import os
from pathlib import Path

project = Path(os.environ["PROJECT_ROOT"])
manifest = project / os.environ["INPUT_MANIFEST"]
dataset_dir = project / os.environ["DATASET_DIR"]
expected = project / os.environ["EXPECTED_TSV"]
chunk_size = int(os.environ["CHUNK_SIZE"])
dataset_dir.mkdir(parents=True, exist_ok=True)

with manifest.open(newline="", errors="replace") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

fields = ["unique_reference_id","reference_layer","target","reference_file_path","abs_pdb","stem","out_dir"]
with expected.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        pdb_rel = row["reference_file_path"]
        pdb_abs = project / pdb_rel
        writer.writerow({
            "unique_reference_id": row["unique_reference_id"],
            "reference_layer": row["reference_layer"],
            "target": row["target"],
            "reference_file_path": pdb_rel,
            "abs_pdb": str(pdb_abs),
            "stem": pdb_abs.stem,
            "out_dir": os.environ["OUT_ROOT"],
        })

for old in dataset_dir.glob("reference_chunk_*.ds"):
    old.unlink()

for idx in range(0, len(rows), chunk_size):
    chunk = rows[idx:idx + chunk_size]
    ds = dataset_dir / f"reference_chunk_{idx // chunk_size + 1:04d}.ds"
    with ds.open("w") as handle:
        for row in chunk:
            handle.write(str(project / row["reference_file_path"]) + "\n")

print(f"dataset_chunks\t{math.ceil(len(rows) / chunk_size)}")
print(f"dataset_rows\t{len(rows)}")
'''
        finalize_python = r'''
import csv
import os
from pathlib import Path

project = Path(os.environ["PROJECT_ROOT"])
expected = project / os.environ["EXPECTED_TSV"]
out_root = project / os.environ["OUT_ROOT"]
run_log = project / os.environ["RUN_LOG"]
fail_log = project / os.environ["FAIL_LOG"]

def rel(path):
    return str(path.relative_to(project))

def find_csv(stem, suffix):
    candidates = []
    candidates.extend(out_root.rglob(f"{stem}_{suffix}.csv"))
    candidates.extend(out_root.rglob(f"{stem}.pdb_{suffix}.csv"))
    if not candidates:
        candidates = [p for p in out_root.rglob(f"*_{suffix}.csv") if stem in p.name]
    candidates = sorted(set(candidates))
    return candidates[0] if candidates else None

with expected.open(newline="", errors="replace") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

run_fields = ["unique_reference_id","reference_layer","target","reference_file_path","out_dir","status","prediction_csv","residue_csv","pocket_rows"]
fail_fields = ["unique_reference_id","reference_layer","target","reference_file_path","error"]
run_rows = []
fail_rows = []

for row in rows:
    pred = find_csv(row["stem"], "predictions")
    res = find_csv(row["stem"], "residues")
    status = "OK"
    error = ""
    if not pred or not pred.is_file():
        status = "MISSING_PREDICTION_CSV"
        error = status
    elif not res or not res.is_file():
        status = "MISSING_RESIDUE_CSV"
        error = status

    pocket_rows = "0"
    if pred and pred.is_file():
        with pred.open(errors="replace") as handle:
            pocket_rows = str(max(0, sum(1 for _ in handle) - 1))

    run_rows.append({
        "unique_reference_id": row["unique_reference_id"],
        "reference_layer": row["reference_layer"],
        "target": row["target"],
        "reference_file_path": row["reference_file_path"],
        "out_dir": row["out_dir"],
        "status": status,
        "prediction_csv": rel(pred) if pred else "",
        "residue_csv": rel(res) if res else "",
        "pocket_rows": pocket_rows,
    })
    if error:
        fail_rows.append({
            "unique_reference_id": row["unique_reference_id"],
            "reference_layer": row["reference_layer"],
            "target": row["target"],
            "reference_file_path": row["reference_file_path"],
            "error": error,
        })

with run_log.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=run_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(run_rows)

with fail_log.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fail_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(fail_rows)

print(f"reference run log rows: {len(run_rows)}")
print(f"reference failed rows: {len(fail_rows)}")
if fail_rows:
    raise SystemExit(2)
'''

    return f'''#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/../../.." && pwd)"
ROLE="{role}"
P2RANK_CMD="${{PROJECT_ROOT}}/resources/tools/p2rank/p2rank_2.5.1/prank"
P2RANK_JAR="${{PROJECT_ROOT}}/resources/tools/p2rank/p2rank_2.5.1/bin/p2rank.jar"
JAVA_BIN="${{JAVA_BIN:-java}}"
P2RANK_THREADS="${{P2RANK_THREADS:-{threads}}}"
CHUNK_SIZE="${{P2RANK_CHUNK_SIZE:-{chunk_size}}}"
INPUT_MANIFEST="{manifest}"
OUT_ROOT="{out_root}"
ALLOWED_ROOT="{allowed_root}"
LOCAL_RUN_DIR="04_p2rank/full/local_runs"
DATASET_DIR="${{LOCAL_RUN_DIR}}/{dataset_subdir}"
EXPECTED_TSV="${{LOCAL_RUN_DIR}}/{expected_file}"
RUN_LOG="${{OUT_ROOT}}/{run_log}"
FAIL_LOG="${{OUT_ROOT}}/{fail_log}"

require_under() {{
  local path="$1"
  local base="$2"
  local abs_path
  local abs_base
  abs_path="$(realpath -m "${{PROJECT_ROOT}}/${{path}}")"
  abs_base="$(realpath -m "${{PROJECT_ROOT}}/${{base}}")"
  case "$abs_path" in
    "$abs_base"|"$abs_base"/*) ;;
    *)
      echo "FATAL: refusing path outside allowed root: path=$path base=$base"
      exit 1
      ;;
  esac
}}

cd "$PROJECT_ROOT"
command -v "$JAVA_BIN" >/dev/null 2>&1 || {{ echo "FATAL: JAVA_BIN command not found: $JAVA_BIN"; exit 1; }}
test -x "$P2RANK_CMD" || {{ echo "FATAL: P2RANK_CMD missing or not executable: $P2RANK_CMD"; exit 1; }}
test -s "$P2RANK_JAR" || {{ echo "FATAL: P2RANK_JAR missing or empty: $P2RANK_JAR"; exit 1; }}
test -s "$INPUT_MANIFEST" || {{ echo "FATAL: input manifest missing or empty: $INPUT_MANIFEST"; exit 1; }}
require_under "$OUT_ROOT" "$ALLOWED_ROOT"
require_under "$LOCAL_RUN_DIR" "04_p2rank/full"
require_under "$DATASET_DIR" "$LOCAL_RUN_DIR"

mkdir -p "$OUT_ROOT" "$DATASET_DIR"

if [ "${{VERMAMG_P2RANK_ALLOW_EXISTING:-0}}" != "1" ]; then
  if find "$OUT_ROOT" -type f \\( -name '*_predictions.csv' -o -name '*_residues.csv' \\) | grep -q .; then
    echo "FATAL: existing P2Rank CSV outputs found under $OUT_ROOT; refusing to overwrite/reuse."
    exit 1
  fi
  if [ -e "$RUN_LOG" ] || [ -e "$FAIL_LOG" ]; then
    echo "FATAL: existing run/failed manifest found under $OUT_ROOT; refusing to overwrite."
    exit 1
  fi
fi

export PROJECT_ROOT INPUT_MANIFEST DATASET_DIR EXPECTED_TSV CHUNK_SIZE OUT_ROOT RUN_LOG FAIL_LOG

echo "===== P2RANK {role.upper()} LOCAL RUN START ====="
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "P2RANK_CMD=$P2RANK_CMD"
echo "P2RANK_JAR=$P2RANK_JAR"
echo "JAVA_BIN=$(command -v "$JAVA_BIN")"
echo "P2RANK_THREADS=$P2RANK_THREADS"
echo "CHUNK_SIZE=$CHUNK_SIZE"
echo "INPUT_MANIFEST=$INPUT_MANIFEST"
echo "OUT_ROOT=$OUT_ROOT"

python3 - <<'PY'
{extract_python}
PY

for ds in "$DATASET_DIR"/{chunk_prefix}_*.ds; do
  echo "P2Rank chunk: $ds"
  "$P2RANK_CMD" predict -threads "$P2RANK_THREADS" -o "$OUT_ROOT" "$ds"
done

python3 - <<'PY'
{finalize_python}
PY

echo "===== P2RANK {role.upper()} LOCAL RUN DONE ====="
'''


def write_runner(path: Path, content: str) -> None:
    path.write_text(content, newline="\n")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    args = parse_args()
    if args.chunk_size <= 0:
        raise SystemExit("ERROR: --chunk-size must be positive")
    if args.threads <= 0:
        raise SystemExit("ERROR: --threads must be positive")

    require_under(LOCAL_RUN_DIR, MODE_ROOT)
    require_under(QUERY_OUT_ROOT, MODE_ROOT / "query_models")
    require_under(REFERENCE_OUT_ROOT, MODE_ROOT / "reference_models")
    query_rows, ref_rows = validate_inputs()
    existing = existing_outputs()

    print("===== M09D FULL665 EXPLICIT RUNNER GENERATOR =====")
    print(f"project_root\t{PROJECT_ROOT}")
    print(f"query_manifest\t{QUERY_MANIFEST}")
    print(f"reference_manifest\t{REFERENCE_MANIFEST}")
    print(f"query_rows\t{len(query_rows)}")
    print(f"reference_rows\t{len(ref_rows)}")
    print(f"query_paths_exist\t{sum(1 for r in query_rows if (PROJECT_ROOT / r['query_model_pdb']).is_file())}")
    print(f"reference_paths_exist\t{sum(1 for r in ref_rows if (PROJECT_ROOT / r['reference_file_path']).is_file())}")
    print(f"p2rank_cmd\t{P2RANK_CMD}")
    print(f"p2rank_jar\t{P2RANK_JAR}")
    print(f"chunk_size\t{args.chunk_size}")
    print(f"threads\t{args.threads}")
    print(f"existing_target_outputs\t{len(existing)}")
    for path in existing:
        print(f"EXISTING\t{path.relative_to(PROJECT_ROOT)}")

    if existing:
        print("validation_status\tBLOCKED_EXISTING_OUTPUTS")
        return 2
    if len(query_rows) != 665 or len(ref_rows) != 1417:
        print("validation_status\tBLOCKED_UNEXPECTED_COUNTS")
        return 2

    if not args.write:
        print("validation_status\tDRY_RUN_OK")
        print("note\tNo files written. Re-run with --write to create runners.")
        return 0

    LOCAL_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_runner(QUERY_RUNNER, runner_template("query", args.threads, args.chunk_size))
    write_runner(REFERENCE_RUNNER, runner_template("reference", args.threads, args.chunk_size))

    with RUN_MANIFEST.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["mode", "runner_role", "runner_path", "input_manifest", "output_root", "input_rows", "status", "note"])
        writer.writerow(["full", "query", rel(QUERY_RUNNER), rel(QUERY_MANIFEST), rel(QUERY_OUT_ROOT), len(query_rows), "READY", "explicit_full665_dataset_chunk_runner"])
        writer.writerow(["full", "reference", rel(REFERENCE_RUNNER), rel(REFERENCE_MANIFEST), rel(REFERENCE_OUT_ROOT), len(ref_rows), "READY", "explicit_full665_dataset_chunk_runner"])

    print(f"query_runner\t{QUERY_RUNNER.relative_to(PROJECT_ROOT)}")
    print(f"reference_runner\t{REFERENCE_RUNNER.relative_to(PROJECT_ROOT)}")
    print(f"run_manifest\t{RUN_MANIFEST.relative_to(PROJECT_ROOT)}")
    print("validation_status\tPASS_RUNNERS_WRITTEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
