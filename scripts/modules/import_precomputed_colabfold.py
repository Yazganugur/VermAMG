#!/usr/bin/env python3
"""Import precomputed ColabFold query PDBs into a VermAMG run directory."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


MANIFEST_FIELDS = [
    "mode", "batch_id", "run_id", "protein_id", "family_label",
    "query_pdb_file", "query_pdb_basename", "colabfold_plddt_mean",
    "colabfold_ptm", "colabfold_struct_conf_class", "colabfold_model_status",
    "atom_lines", "ca_atoms",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="full")
    parser.add_argument("--query-pdb-dir", type=Path, required=True)
    parser.add_argument("--collector-manifest", type=Path, required=True)
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--out-pdb-dir", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--copy-mode", choices=["copy", "symlink", "reference"], default="copy")
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


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(errors="replace", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def pdb_stats(path: Path) -> tuple[int, int]:
    atom_lines = 0
    ca_atoms = 0
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            atom_lines += 1
            if line[12:16].strip() == "CA":
                ca_atoms += 1
    return atom_lines, ca_atoms


def link_or_copy(src: Path, dst: Path, mode: str, overwrite: bool) -> None:
    if dst.exists() and not overwrite:
        raise SystemExit(f"ERROR: output exists; refusing overwrite: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        dst.symlink_to(src.resolve())


def main() -> int:
    args = parse_args()
    for path in (args.query_pdb_dir, args.collector_manifest, args.id_map):
        if not path.exists():
            raise SystemExit(f"ERROR: required input missing: {path}")
    for path in (args.out_pdb_dir, args.out_manifest, args.out_summary):
        require_under(path, args.allowed_root)

    id_rows = read_tsv(args.id_map)
    collector_rows = read_tsv(args.collector_manifest)
    id_by_run = {row["run_id"]: row for row in id_rows}
    batch_by_stem = {}
    for row in collector_rows:
        dest = Path((row.get("pdb_dest") or "").replace("\\", "/")).stem
        if dest:
            batch_by_stem[dest] = row.get("batch", "")

    pdb_by_run = {path.stem: path for path in args.query_pdb_dir.glob("*.pdb")}
    missing_pdb = sorted(set(id_by_run) - set(pdb_by_run))
    extra_pdb = sorted(set(pdb_by_run) - set(id_by_run))
    if missing_pdb:
        raise SystemExit(f"ERROR: id_map run_ids missing query PDBs: {len(missing_pdb)}")

    rows = []
    for run_id in sorted(id_by_run):
        src = pdb_by_run[run_id]
        dst = args.out_pdb_dir / src.name
        out_path = src if args.copy_mode == "reference" else dst
        atom_lines, ca_atoms = pdb_stats(src)
        meta = id_by_run[run_id]
        rows.append({
            "mode": args.mode,
            "batch_id": batch_by_stem.get(run_id, ""),
            "run_id": run_id,
            "protein_id": meta.get("protein_id", ""),
            "family_label": meta.get("family_label", ""),
            "query_pdb_file": str(out_path),
            "query_pdb_basename": src.name,
            "colabfold_plddt_mean": "NA_PRECOMPUTED_NO_SCORE_JSON",
            "colabfold_ptm": "NA_PRECOMPUTED_NO_SCORE_JSON",
            "colabfold_struct_conf_class": "UNKNOWN_PRECOMPUTED_NO_SCORE_JSON",
            "colabfold_model_status": "PRECOMPUTED_IMPORTED",
            "atom_lines": str(atom_lines),
            "ca_atoms": str(ca_atoms),
        })

    print("VERMAMG_IMPORT_PRECOMPUTED_COLABFOLD")
    print(f"id_map_rows\t{len(id_rows)}")
    print(f"collector_rows\t{len(collector_rows)}")
    print(f"query_pdbs\t{len(pdb_by_run)}")
    print(f"missing_pdb\t{len(missing_pdb)}")
    print(f"extra_pdb\t{len(extra_pdb)}")
    print(f"copy_mode\t{args.copy_mode}")
    print(f"write\t{'YES' if args.write else 'NO'}")

    if not args.write:
        print("validation_status\tDRY_RUN_OK")
        return 0

    args.out_pdb_dir.mkdir(parents=True, exist_ok=True)
    if args.copy_mode != "reference":
        for run_id in sorted(id_by_run):
            link_or_copy(pdb_by_run[run_id], args.out_pdb_dir / pdb_by_run[run_id].name, args.copy_mode, args.overwrite)

    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.out_manifest.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.out_summary.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerow(["status", "PASS"])
        writer.writerow(["query_manifest_rows", len(rows)])
        writer.writerow(["query_pdbs", len(pdb_by_run)])
        writer.writerow(["missing_pdb", len(missing_pdb)])
        writer.writerow(["extra_pdb", len(extra_pdb)])
        writer.writerow(["confidence_policy", "NA_PRECOMPUTED_NO_SCORE_JSON"])
    print("validation_status\tPASS_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
