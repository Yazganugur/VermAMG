#!/usr/bin/env python3
"""Run P2Rank from an explicit query or reference manifest."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["query", "reference"], required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--failed", type=Path, required=True)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--p2rank-jar", type=Path, required=True)
    parser.add_argument("--java-bin", default="java")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=64)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def require_under(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(errors="replace", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def resolve_project_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def rel(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def count_data_rows(path: Path) -> int:
    with path.open(errors="replace") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _csv_base(path: Path, suffix: str) -> str:
    tail = f"_{suffix}.csv"
    name = path.name
    return name[:-len(tail)] if name.endswith(tail) else path.stem


def build_p2rank_csv_index(out_root: Path, suffix: str) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in sorted(out_root.rglob(f"*_{suffix}.csv")):
        base = _csv_base(path, suffix)
        keys = {base, Path(base).stem}
        for key in keys:
            index.setdefault(key, path)
    return index


def find_p2rank_csv(index: dict[str, Path], pdb_path: Path) -> Path | None:
    return index.get(pdb_path.name) or index.get(pdb_path.stem)


def role_rows(args: argparse.Namespace, manifest_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if args.role == "query":
        required = ["query", "family", "query_model_pdb"]
        missing = [col for col in required if manifest_rows and col not in manifest_rows[0]]
        if missing:
            raise SystemExit(f"ERROR: query manifest missing columns: {missing}")
        for row in manifest_rows:
            pdb_rel = row["query_model_pdb"]
            rows.append({
                "id": row["query"],
                "family": row.get("family", ""),
                "pdb_rel": pdb_rel,
                "pdb_abs": str(resolve_project_path(args.project_root, pdb_rel)),
            })
    else:
        required = ["unique_reference_id", "reference_layer", "target", "reference_file_path"]
        missing = [col for col in required if manifest_rows and col not in manifest_rows[0]]
        if missing:
            raise SystemExit(f"ERROR: reference manifest missing columns: {missing}")
        for row in manifest_rows:
            pdb_rel = row["reference_file_path"]
            rows.append({
                "id": row["unique_reference_id"],
                "reference_layer": row.get("reference_layer", ""),
                "target": row.get("target", ""),
                "pdb_rel": pdb_rel,
                "pdb_abs": str(resolve_project_path(args.project_root, pdb_rel)),
            })
    return rows


def write_dataset_chunks(rows: list[dict[str, str]], dataset_dir: Path, prefix: str, chunk_size: int) -> list[Path]:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for old in dataset_dir.glob(f"{prefix}_*.ds"):
        old.unlink()
    chunks = []
    for idx in range(0, len(rows), chunk_size):
        chunk = rows[idx:idx + chunk_size]
        path = dataset_dir / f"{prefix}_{idx // chunk_size + 1:04d}.ds"
        with path.open("w", newline="\n") as handle:
            for row in chunk:
                handle.write(row["pdb_abs"] + "\n")
        chunks.append(path)
    return chunks


def java_classpath(jar: Path) -> str:
    sep = ";" if os.name == "nt" else ":"
    return str(jar) + sep + str(jar.parent / "lib" / "*")


def run_p2rank_chunks(args: argparse.Namespace, chunks: list[Path]) -> None:
    for ds in chunks:
        print(f"P2Rank chunk\t{ds}")
        cmd = [
            args.java_bin,
            "-Xmx2048m",
            "-cp",
            java_classpath(args.p2rank_jar),
            "cz.siret.prank.program.Main",
            "predict",
            "-threads",
            str(args.threads),
            "-o",
            str(args.out_root),
            str(ds),
        ]
        completed = subprocess.run(cmd, cwd=args.project_root)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)


def existing_p2rank_outputs(out_root: Path) -> list[Path]:
    patterns = ["*_predictions.csv", "*_residues.csv"]
    out: list[Path] = []
    for pattern in patterns:
        out.extend(out_root.rglob(pattern))
    return sorted(out)


def finalize(args: argparse.Namespace, rows: list[dict[str, str]]) -> int:
    run_rows: list[dict[str, str]] = []
    failed_rows: list[dict[str, str]] = []
    prediction_index = build_p2rank_csv_index(args.out_root, "predictions")
    residue_index = build_p2rank_csv_index(args.out_root, "residues")
    if args.role == "query":
        run_fields = ["query", "family", "query_model_pdb", "out_dir", "status", "prediction_csv", "residue_csv", "pocket_rows"]
        fail_fields = ["query", "family", "query_model_pdb", "error"]
    else:
        run_fields = [
            "unique_reference_id", "reference_layer", "target", "reference_file_path",
            "out_dir", "status", "prediction_csv", "residue_csv", "pocket_rows",
        ]
        fail_fields = ["unique_reference_id", "reference_layer", "target", "reference_file_path", "error"]

    for row in rows:
        pdb_abs = Path(row["pdb_abs"])
        pred = find_p2rank_csv(prediction_index, pdb_abs)
        residues = find_p2rank_csv(residue_index, pdb_abs)
        status = "OK"
        error = ""
        if pred is None:
            status = "MISSING_PREDICTION_CSV"
            error = status
        elif residues is None:
            status = "MISSING_RESIDUE_CSV"
            error = status
        pocket_rows = count_data_rows(pred) if pred else 0

        if args.role == "query":
            run_rows.append({
                "query": row["id"],
                "family": row.get("family", ""),
                "query_model_pdb": row["pdb_rel"],
                "out_dir": rel(args.project_root, args.out_root),
                "status": status,
                "prediction_csv": rel(args.project_root, pred) if pred else "",
                "residue_csv": rel(args.project_root, residues) if residues else "",
                "pocket_rows": str(pocket_rows),
            })
            if error:
                failed_rows.append({
                    "query": row["id"],
                    "family": row.get("family", ""),
                    "query_model_pdb": row["pdb_rel"],
                    "error": error,
                })
        else:
            run_rows.append({
                "unique_reference_id": row["id"],
                "reference_layer": row.get("reference_layer", ""),
                "target": row.get("target", ""),
                "reference_file_path": row["pdb_rel"],
                "out_dir": rel(args.project_root, args.out_root),
                "status": status,
                "prediction_csv": rel(args.project_root, pred) if pred else "",
                "residue_csv": rel(args.project_root, residues) if residues else "",
                "pocket_rows": str(pocket_rows),
            })
            if error:
                failed_rows.append({
                    "unique_reference_id": row["id"],
                    "reference_layer": row.get("reference_layer", ""),
                    "target": row.get("target", ""),
                    "reference_file_path": row["pdb_rel"],
                    "error": error,
                })

    write_tsv(args.run_manifest, run_rows, run_fields)
    write_tsv(args.failed, failed_rows, fail_fields)
    print(f"{args.role}_run_rows\t{len(run_rows)}")
    print(f"{args.role}_failed_rows\t{len(failed_rows)}")
    return 2 if failed_rows else 0


def main() -> int:
    args = parse_args()
    args.project_root = args.project_root.resolve()
    args.allowed_root = args.allowed_root.resolve()
    args.out_root = resolve_project_path(args.project_root, str(args.out_root))
    args.run_manifest = resolve_project_path(args.project_root, str(args.run_manifest))
    args.failed = resolve_project_path(args.project_root, str(args.failed))
    args.dataset_dir = resolve_project_path(args.project_root, str(args.dataset_dir))
    args.manifest = resolve_project_path(args.project_root, str(args.manifest))
    args.p2rank_jar = resolve_project_path(args.project_root, str(args.p2rank_jar))

    for path in (args.out_root, args.run_manifest, args.failed, args.dataset_dir):
        require_under(path, args.allowed_root)
    if args.threads <= 0 or args.chunk_size <= 0:
        raise SystemExit("ERROR: --threads and --chunk-size must be positive")
    if not args.manifest.is_file():
        raise SystemExit(f"ERROR: manifest missing: {args.manifest}")
    if not args.p2rank_jar.is_file():
        raise SystemExit(f"ERROR: P2Rank jar missing: {args.p2rank_jar}")
    manifest_rows = read_tsv(args.manifest)
    rows = role_rows(args, manifest_rows)
    missing = [row for row in rows if not Path(row["pdb_abs"]).is_file()]
    print("VERMAMG_RUN_P2RANK_MANIFEST_EXPLICIT")
    print(f"role\t{args.role}")
    print(f"input_rows\t{len(rows)}")
    print(f"missing_pdb\t{len(missing)}")
    print(f"out_root\t{args.out_root}")
    print(f"java_bin\t{args.java_bin}")
    print(f"threads\t{args.threads}")
    print(f"chunk_size\t{args.chunk_size}")
    if missing:
        for row in missing[:20]:
            print(f"MISSING_PDB\t{row['id']}\t{row['pdb_rel']}")
        return 2

    if not args.overwrite:
        existing_manifests = [path for path in (args.run_manifest, args.failed) if path.exists()]
        if existing_manifests:
            print(f"existing_manifest_count\t{len(existing_manifests)}")
            for path in existing_manifests:
                print(f"EXISTING_MANIFEST\t{path}")
            raise SystemExit("ERROR: refusing to overwrite existing P2Rank run manifest")
        existing = existing_p2rank_outputs(args.out_root)
        if existing:
            print(f"existing_p2rank_output_count\t{len(existing)}")
            print("existing_output_policy\tFINALIZE_EXISTING_OUTPUTS")
            for path in existing[:20]:
                print(f"EXISTING\t{path}")
            return finalize(args, rows)

    args.out_root.mkdir(parents=True, exist_ok=True)
    chunks = write_dataset_chunks(rows, args.dataset_dir, f"{args.role}_chunk", args.chunk_size)
    print(f"dataset_chunks\t{len(chunks)}")
    run_p2rank_chunks(args, chunks)
    return finalize(args, rows)


if __name__ == "__main__":
    raise SystemExit(main())
