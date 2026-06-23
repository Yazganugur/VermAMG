#!/usr/bin/env python3
"""Explicit-path M09C helper for materializing reference panel structures."""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--foldseek-bin", type=Path, required=True)
    parser.add_argument("--pdb-db", type=Path, required=True)
    parser.add_argument("--afsp-db", type=Path, required=True)
    parser.add_argument("--pdb-out", type=Path, required=True)
    parser.add_argument("--afsp-out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
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
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def check_db_prefix(prefix: Path) -> None:
    for suffix in (".dbtype", ".lookup"):
        sidecar = Path(str(prefix) + suffix)
        if not sidecar.is_file():
            raise SystemExit(f"ERROR: Foldseek DB sidecar missing: {sidecar}")


def safe_name(target: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in target)


def final_path(out_dir: Path, target: str) -> Path:
    return out_dir / f"{safe_name(target)}.pdb"


def read_unique_targets(panel: Path) -> dict[str, list[str]]:
    with panel.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = [col for col in ("reference_layer", "target") if col not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"ERROR: panel missing required columns: {missing}")
        by_layer = {"PDB": set(), "AFSP": set()}
        for row in reader:
            layer = (row.get("reference_layer") or "").strip().upper()
            target = (row.get("target") or "").strip()
            if layer in by_layer and target:
                by_layer[layer].add(target)
    return {layer: sorted(values) for layer, values in by_layer.items()}


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def tail(text: str, limit: int = 3000) -> str:
    return text if len(text) <= limit else text[-limit:]


def find_match(exported_files: list[Path], target: str, target_count: int) -> Path | None:
    target_lc = target.lower()
    for path in exported_files:
        if path.stem.lower() == target_lc or path.name.lower() == f"{target_lc}.pdb":
            return path
    for path in exported_files:
        if target_lc in path.name.lower():
            return path
    if target_count == 1 and len(exported_files) == 1:
        return exported_files[0]
    return None


def materialize_group(layer: str, targets: list[str], db_prefix: Path, out_dir: Path, foldseek_bin: Path, overwrite: bool) -> dict[str, object]:
    if not targets:
        return {"targets": 0, "exported_files": 0, "materialized": 0, "missing": []}
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = [final_path(out_dir, target) for target in targets if final_path(out_dir, target).exists()]
    if existing and not overwrite:
        raise SystemExit(f"ERROR: {layer} existing materialized files found: {len(existing)}")

    with tempfile.TemporaryDirectory(prefix=f".foldseek_{layer.lower()}_", dir=out_dir) as tmp_name:
        tmp = Path(tmp_name)
        target_file = tmp / f"{layer.lower()}_target_ids.txt"
        subset_db = tmp / f"{layer.lower()}_subset_db"
        export_dir = tmp / "exported_pdb"
        export_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text("\n".join(targets) + "\n", encoding="utf-8")

        create_result = run_command([
            str(foldseek_bin), "createsubdb", "--id-mode", "1",
            str(target_file), str(db_prefix), str(subset_db),
        ])
        if create_result.returncode != 0:
            print("STDOUT_TAIL:")
            print(tail(create_result.stdout))
            print("STDERR_TAIL:")
            print(tail(create_result.stderr))
            raise SystemExit(create_result.returncode)

        convert_result = run_command([
            str(foldseek_bin), "convert2pdb", str(subset_db), str(export_dir),
            "--pdb-output-mode", "1",
        ])
        if convert_result.returncode != 0:
            print("STDOUT_TAIL:")
            print(tail(convert_result.stdout))
            print("STDERR_TAIL:")
            print(tail(convert_result.stderr))
            raise SystemExit(convert_result.returncode)

        exported_files = sorted(export_dir.rglob("*.pdb"))
        missing: list[str] = []
        materialized = 0
        for target in targets:
            match = find_match(exported_files, target, len(targets))
            if not match or not match.is_file() or match.stat().st_size == 0:
                missing.append(target)
                continue
            shutil.copyfile(match, final_path(out_dir, target))
            materialized += 1
    return {
        "targets": len(targets),
        "exported_files": len(exported_files),
        "materialized": materialized,
        "missing": missing,
    }


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["layer", "metric", "value"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    for path in (args.pdb_out, args.afsp_out, args.report):
        require_under(path, args.allowed_root)
    for path in (args.panel, args.foldseek_bin):
        if not path.exists():
            raise SystemExit(f"ERROR: required path missing: {path}")
    check_db_prefix(args.pdb_db)
    check_db_prefix(args.afsp_db)

    targets = read_unique_targets(args.panel)
    existing = list(args.pdb_out.glob("*.pdb")) + list(args.afsp_out.glob("*.pdb"))
    print("VERMAMG_M09C_EXPLICIT_MATERIALIZATION")
    print(f"PDB_unique_targets\t{len(targets['PDB'])}")
    print(f"AFSP_unique_targets\t{len(targets['AFSP'])}")
    print(f"existing_materialized_files\t{len(existing)}")
    print(f"write\t{'YES' if args.write else 'NO'}")
    if existing and not args.overwrite:
        print("validation_status\tBLOCKED_EXISTING_OUTPUTS")
        return 2
    if not args.write:
        print("validation_status\tDRY_RUN_OK")
        return 0

    pdb_result = materialize_group("PDB", targets["PDB"], args.pdb_db, args.pdb_out, args.foldseek_bin, args.overwrite)
    afsp_result = materialize_group("AFSP", targets["AFSP"], args.afsp_db, args.afsp_out, args.foldseek_bin, args.overwrite)
    rows = []
    for layer, result in (("PDB", pdb_result), ("AFSP", afsp_result)):
        for metric in ("targets", "exported_files", "materialized"):
            rows.append({"layer": layer, "metric": metric, "value": str(result[metric])})
        rows.append({"layer": layer, "metric": "missing", "value": str(len(result["missing"]))})
    write_report(args.report, rows)
    print(f"PDB_materialized\t{pdb_result['materialized']}")
    print(f"AFSP_materialized\t{afsp_result['materialized']}")
    print(f"PDB_missing\t{len(pdb_result['missing'])}")
    print(f"AFSP_missing\t{len(afsp_result['missing'])}")
    print("validation_status\tPASS_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

