#!/usr/bin/env python3
"""Import precomputed Foldseek all-hit TSVs into an isolated run directory."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


EXPECTED_HIT_COLUMNS = [
    "query", "target", "evalue", "bits", "prob", "alntmscore", "qtmscore",
    "ttmscore", "lddt", "qcov", "tcov", "qlen", "tlen", "batch",
]
EXPECTED_ID_MAP_COLUMNS = ["run_id", "protein_id", "family_label", "habitat_broad"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdb-all-hits", type=Path, required=True)
    parser.add_argument("--afsp-all-hits", type=Path, required=True)
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--out-pdb-all-hits", type=Path, required=True)
    parser.add_argument("--out-afsp-all-hits", type=Path, required=True)
    parser.add_argument("--out-id-map", type=Path, required=True)
    parser.add_argument("--qc-report", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def require_under(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing output outside allowed root: path={path} root={root}") from exc


def header(path: Path) -> list[str]:
    with path.open(errors="replace", newline="") as handle:
        return handle.readline().rstrip("\n").split("\t")


def count_rows_and_queries(path: Path) -> tuple[int, int]:
    with path.open(errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        queries = set()
        rows = 0
        for row in reader:
            rows += 1
            if row.get("query"):
                queries.add(row["query"])
    return rows, len(queries)


def require_columns(label: str, observed: list[str], expected: list[str]) -> None:
    missing = [col for col in expected if col not in observed]
    if missing:
        raise SystemExit(f"ERROR: {label} missing required columns: {missing}")


def copy_one(src: Path, dst: Path, overwrite: bool) -> None:
    if dst.exists() and not overwrite:
        raise SystemExit(f"ERROR: output exists; refusing overwrite: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    args = parse_args()
    for path in (args.pdb_all_hits, args.afsp_all_hits, args.id_map):
        if not path.is_file():
            raise SystemExit(f"ERROR: required input missing: {path}")
    for path in (args.out_pdb_all_hits, args.out_afsp_all_hits, args.out_id_map, args.qc_report):
        require_under(path, args.allowed_root)

    require_columns("PDB all-hit TSV", header(args.pdb_all_hits), EXPECTED_HIT_COLUMNS)
    require_columns("AFSP all-hit TSV", header(args.afsp_all_hits), EXPECTED_HIT_COLUMNS)
    require_columns("id_map TSV", header(args.id_map), EXPECTED_ID_MAP_COLUMNS)

    pdb_rows, pdb_queries = count_rows_and_queries(args.pdb_all_hits)
    afsp_rows, afsp_queries = count_rows_and_queries(args.afsp_all_hits)
    id_rows = max(0, sum(1 for _ in args.id_map.open(errors="replace")) - 1)

    print("VERMAMG_IMPORT_PRECOMPUTED_FOLDSEEK")
    print(f"pdb_rows\t{pdb_rows}")
    print(f"pdb_unique_queries\t{pdb_queries}")
    print(f"afsp_rows\t{afsp_rows}")
    print(f"afsp_unique_queries\t{afsp_queries}")
    print(f"id_map_rows\t{id_rows}")
    print(f"write\t{'YES' if args.write else 'NO'}")

    if not args.write:
        print("validation_status\tDRY_RUN_OK")
        return 0

    copy_one(args.pdb_all_hits, args.out_pdb_all_hits, args.overwrite)
    copy_one(args.afsp_all_hits, args.out_afsp_all_hits, args.overwrite)
    copy_one(args.id_map, args.out_id_map, args.overwrite)

    args.qc_report.parent.mkdir(parents=True, exist_ok=True)
    with args.qc_report.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerow(["status", "PASS"])
        writer.writerow(["pdb_rows", pdb_rows])
        writer.writerow(["pdb_unique_queries", pdb_queries])
        writer.writerow(["afsp_rows", afsp_rows])
        writer.writerow(["afsp_unique_queries", afsp_queries])
        writer.writerow(["id_map_rows", id_rows])
    print("validation_status\tPASS_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

