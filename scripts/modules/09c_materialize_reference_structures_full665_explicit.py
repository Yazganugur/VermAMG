#!/usr/bin/env python3
"""Explicit full665 M09C reference materialization helper.

This helper intentionally does not accept a VermAMG mode argument, because the
generic shell wrapper maps "full" to "tier1_full". It reads the canonical full
M08 panel, extracts unique reference targets, and materializes structures from
the local Foldseek databases for downstream M09B resolution.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_PANEL = PROJECT_ROOT / "05_reference_panel/full/full_reference_panel_targets.tsv"
DEFAULT_FOLDSEEK = PROJECT_ROOT / "resources/tools/foldseek/bin/foldseek"
DEFAULT_PDB_DB = PROJECT_ROOT / "resources/databases/foldseek/pdb/pdb"
DEFAULT_AFSP_DB = PROJECT_ROOT / "resources/databases/foldseek/alphafold_swissprot/af_swissprot"
DEFAULT_PDB_OUT = PROJECT_ROOT / "04_p2rank/full/reference_structures/materialized/pdb"
DEFAULT_AFSP_OUT = PROJECT_ROOT / "04_p2rank/full/reference_structures/materialized/afsp"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize unique full665 M08 reference targets from local Foldseek DBs."
    )
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--foldseek-bin", type=Path, default=DEFAULT_FOLDSEEK)
    parser.add_argument("--pdb-db", type=Path, default=DEFAULT_PDB_DB)
    parser.add_argument("--afsp-db", type=Path, default=DEFAULT_AFSP_DB)
    parser.add_argument("--pdb-out", type=Path, default=DEFAULT_PDB_OUT)
    parser.add_argument("--afsp-out", type=Path, default=DEFAULT_AFSP_OUT)
    parser.add_argument("--write", action="store_true", help="Materialize structures. Default is dry-run.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing existing final materialized PDB files. Not needed for first run.",
    )
    return parser.parse_args()


def require_under(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def check_db_prefix(prefix: Path) -> None:
    dbtype = Path(str(prefix) + ".dbtype")
    lookup = Path(str(prefix) + ".lookup")
    if not dbtype.is_file():
        raise SystemExit(f"ERROR: Foldseek DB dbtype missing: {dbtype}")
    if not lookup.is_file():
        raise SystemExit(f"ERROR: Foldseek DB lookup missing: {lookup}")


def safe_name(target: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in target)


def read_unique_targets(panel: Path) -> dict[str, list[str]]:
    with panel.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise SystemExit(f"ERROR: empty panel TSV: {panel}")
        missing = [c for c in ("reference_layer", "target") if c not in reader.fieldnames]
        if missing:
            raise SystemExit(f"ERROR: panel TSV missing required columns: {missing}")
        by_layer: dict[str, set[str]] = {"PDB": set(), "AFSP": set()}
        layer_rows = Counter()
        for row in reader:
            layer = (row.get("reference_layer") or "").strip().upper()
            target = (row.get("target") or "").strip()
            if not target:
                continue
            layer_rows[layer] += 1
            if layer in by_layer:
                by_layer[layer].add(target)

    return {layer: sorted(targets) for layer, targets in by_layer.items()}


def final_path(out_dir: Path, target: str) -> Path:
    return out_dir / f"{safe_name(target)}.pdb"


def tail_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def find_match(exported_files: list[Path], target: str, target_count: int) -> Path | None:
    target_lc = target.lower()

    for path in exported_files:
        if path.stem.lower() == target_lc:
            return path

    for path in exported_files:
        if path.name.lower() == f"{target_lc}.pdb":
            return path

    for path in exported_files:
        if target_lc in path.name.lower():
            return path

    if target_count == 1 and len(exported_files) == 1:
        return exported_files[0]

    return None


def materialize_group(
    *,
    layer: str,
    targets: list[str],
    db_prefix: Path,
    out_dir: Path,
    foldseek_bin: Path,
    overwrite: bool,
) -> dict[str, object]:
    if not targets:
        return {"targets": 0, "exported_files": 0, "materialized": 0, "missing": []}

    out_dir.mkdir(parents=True, exist_ok=True)
    existing = [final_path(out_dir, target) for target in targets if final_path(out_dir, target).exists()]
    if existing and not overwrite:
        print(f"ERROR: {layer} existing final files would be overwritten: {len(existing)}")
        for path in existing[:20]:
            print(f"EXISTING_{layer}\t{path}")
        raise SystemExit("ERROR: refusing to overwrite existing materialized files without --overwrite")

    with tempfile.TemporaryDirectory(prefix=f".foldseek_{layer.lower()}_", dir=out_dir) as tmp_name:
        tmp = Path(tmp_name)
        target_file = tmp / f"full665_{layer.lower()}_target_ids.txt"
        subset_db = tmp / f"full665_{layer.lower()}_subset_db"
        export_dir = tmp / "exported_pdb"
        export_dir.mkdir(parents=True, exist_ok=True)

        target_file.write_text("\n".join(targets) + "\n")

        create_cmd = [
            str(foldseek_bin),
            "createsubdb",
            "--id-mode",
            "1",
            str(target_file),
            str(db_prefix),
            str(subset_db),
        ]
        convert_cmd = [
            str(foldseek_bin),
            "convert2pdb",
            str(subset_db),
            str(export_dir),
            "--pdb-output-mode",
            "1",
        ]

        create_result = run_command(create_cmd)
        if create_result.returncode != 0:
            print(f"ERROR: foldseek createsubdb failed for {layer}: exit={create_result.returncode}")
            print("STDOUT_TAIL:")
            print(tail_text(create_result.stdout))
            print("STDERR_TAIL:")
            print(tail_text(create_result.stderr))
            raise SystemExit(create_result.returncode)

        convert_result = run_command(convert_cmd)
        if convert_result.returncode != 0:
            print(f"ERROR: foldseek convert2pdb failed for {layer}: exit={convert_result.returncode}")
            print("STDOUT_TAIL:")
            print(tail_text(convert_result.stdout))
            print("STDERR_TAIL:")
            print(tail_text(convert_result.stderr))
            raise SystemExit(convert_result.returncode)

        exported_files = sorted(export_dir.rglob("*.pdb"))
        missing: list[str] = []
        materialized = 0
        for target in targets:
            match = find_match(exported_files, target, len(targets))
            if not match or not match.is_file() or match.stat().st_size == 0:
                missing.append(target)
                continue
            destination = final_path(out_dir, target)
            shutil.copyfile(match, destination)
            materialized += 1

    return {
        "targets": len(targets),
        "exported_files": len(exported_files),
        "materialized": materialized,
        "missing": missing,
    }


def main() -> int:
    args = parse_args()
    allowed_root = PROJECT_ROOT / "04_p2rank/full/reference_structures/materialized"

    require_under(args.pdb_out, allowed_root)
    require_under(args.afsp_out, allowed_root)

    if not args.panel.is_file():
        raise SystemExit(f"ERROR: panel TSV missing: {args.panel}")
    if not args.foldseek_bin.is_file():
        raise SystemExit(f"ERROR: Foldseek binary missing: {args.foldseek_bin}")
    check_db_prefix(args.pdb_db)
    check_db_prefix(args.afsp_db)

    targets = read_unique_targets(args.panel)
    print("===== M09C FULL665 EXPLICIT MATERIALIZATION HELPER =====")
    print(f"project_root\t{PROJECT_ROOT}")
    print(f"panel\t{args.panel}")
    print(f"foldseek_bin\t{args.foldseek_bin}")
    print(f"pdb_db\t{args.pdb_db}")
    print(f"afsp_db\t{args.afsp_db}")
    print(f"pdb_out\t{args.pdb_out}")
    print(f"afsp_out\t{args.afsp_out}")
    print(f"dry_run\t{not args.write}")
    print(f"unique_PDB_targets\t{len(targets['PDB'])}")
    print(f"unique_AFSP_targets\t{len(targets['AFSP'])}")
    print(f"unique_total_targets\t{len(targets['PDB']) + len(targets['AFSP'])}")

    existing_pdb = [final_path(args.pdb_out, target) for target in targets["PDB"] if final_path(args.pdb_out, target).exists()]
    existing_afsp = [final_path(args.afsp_out, target) for target in targets["AFSP"] if final_path(args.afsp_out, target).exists()]
    print(f"existing_PDB_final_files\t{len(existing_pdb)}")
    print(f"existing_AFSP_final_files\t{len(existing_afsp)}")

    if not args.write:
        print("validation_status\tDRY_RUN_OK")
        print("note\tNo files were written. Re-run with --write to materialize references.")
        return 0

    if (existing_pdb or existing_afsp) and not args.overwrite:
        print("validation_status\tBLOCKED_EXISTING_OUTPUTS")
        raise SystemExit("ERROR: existing materialized outputs detected; use --overwrite only after explicit approval")

    pdb_result = materialize_group(
        layer="PDB",
        targets=targets["PDB"],
        db_prefix=args.pdb_db,
        out_dir=args.pdb_out,
        foldseek_bin=args.foldseek_bin,
        overwrite=args.overwrite,
    )
    afsp_result = materialize_group(
        layer="AFSP",
        targets=targets["AFSP"],
        db_prefix=args.afsp_db,
        out_dir=args.afsp_out,
        foldseek_bin=args.foldseek_bin,
        overwrite=args.overwrite,
    )

    missing_pdb = list(pdb_result["missing"])
    missing_afsp = list(afsp_result["missing"])
    print("===== MATERIALIZATION SUMMARY =====")
    print(f"PDB_targets\t{pdb_result['targets']}")
    print(f"PDB_exported_files\t{pdb_result['exported_files']}")
    print(f"PDB_materialized\t{pdb_result['materialized']}")
    print(f"PDB_missing\t{len(missing_pdb)}")
    print(f"AFSP_targets\t{afsp_result['targets']}")
    print(f"AFSP_exported_files\t{afsp_result['exported_files']}")
    print(f"AFSP_materialized\t{afsp_result['materialized']}")
    print(f"AFSP_missing\t{len(missing_afsp)}")
    print(f"total_materialized\t{pdb_result['materialized'] + afsp_result['materialized']}")
    print(f"total_missing\t{len(missing_pdb) + len(missing_afsp)}")

    for target in missing_pdb[:50]:
        print(f"MISSING_PDB\t{target}")
    for target in missing_afsp[:50]:
        print(f"MISSING_AFSP\t{target}")

    if missing_pdb or missing_afsp:
        print("validation_status\tCOMPLETE_WITH_MISSING_TARGETS")
    else:
        print("validation_status\tPASS_ALL_TARGETS_MATERIALIZED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
