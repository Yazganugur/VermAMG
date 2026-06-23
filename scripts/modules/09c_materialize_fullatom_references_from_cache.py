#!/usr/bin/env python3
"""Materialize full-atom reference structures from a trusted local cache.

This helper is for project-scoped V2 runs that should not depend on Foldseek's
CA-only-like structural export for reference P2Rank. It copies already
materialized full-atom PDB-chain and AFSP structures from a previous verified
run/cache into the current isolated run directory.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import Counter
from pathlib import Path

try:
    from Bio.PDB import MMCIFParser
except ImportError:  # pragma: no cover - runtime dependency check
    MMCIFParser = None


PDB_RE = re.compile(r"^([0-9][A-Za-z0-9]{3})-assembly([0-9]+)_([A-Za-z0-9-]+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--source-run-root", type=Path, required=True)
    parser.add_argument("--pdb-out", type=Path, required=True)
    parser.add_argument("--afsp-out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def require_under(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def rel(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def read_unique_targets(panel: Path) -> list[dict[str, str]]:
    with panel.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = [col for col in ("reference_layer", "target") if col not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"ERROR: panel missing required columns: {missing}")
        by_key: dict[tuple[str, str], dict[str, str]] = {}
        counts: Counter = Counter()
        for row in reader:
            layer = (row.get("reference_layer") or "").strip().upper()
            target = (row.get("target") or "").strip()
            if layer not in {"PDB", "AFSP"} or not target:
                continue
            key = (layer, target)
            counts[key] += 1
            if key not in by_key:
                by_key[key] = {
                    "reference_layer": layer,
                    "target": target,
                    "example_query": row.get("query", ""),
                    "example_family": row.get("family", ""),
                    "example_panel_order": row.get("panel_order", ""),
                    "example_panel_role": row.get("panel_role", ""),
                    "example_source_rank": row.get("source_rank", ""),
                    "example_support_class": row.get("support_class", ""),
                }
        rows: list[dict[str, str]] = []
        for key in sorted(by_key):
            row = dict(by_key[key])
            row["panel_row_count"] = str(counts[key])
            rows.append(row)
        return rows


def atom_stats(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {
            "source_file_exists": "NO",
            "atom_lines": "0",
            "hetatm_lines": "0",
            "ca_atoms": "0",
            "non_ca_atoms": "0",
            "ca_only_like": "UNKNOWN",
            "atom_audit_status": "FAIL_MISSING_SOURCE",
        }
    if path.suffix.lower() in {".cif", ".mmcif"}:
        return cif_atom_stats(path)
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            atom_lines += 1
            if line.startswith("HETATM"):
                hetatm_lines += 1
            atom_name = line[12:16].strip() if len(line) >= 16 else ""
            if atom_name == "CA":
                ca_atoms += 1
    non_ca_atoms = atom_lines - ca_atoms
    ca_only_like = "YES" if atom_lines > 0 and non_ca_atoms == 0 else "NO"
    if atom_lines == 0:
        status = "FAIL_NO_ATOM_RECORDS"
    elif ca_only_like == "YES":
        status = "FAIL_CA_ONLY_SOURCE"
    else:
        status = "PASS_FULL_ATOM_SOURCE"
    return {
        "source_file_exists": "YES",
        "atom_lines": str(atom_lines),
        "hetatm_lines": str(hetatm_lines),
        "ca_atoms": str(ca_atoms),
        "non_ca_atoms": str(non_ca_atoms),
        "ca_only_like": ca_only_like,
        "atom_audit_status": status,
    }


def cif_atom_stats(path: Path) -> dict[str, str]:
    if MMCIFParser is None:
        return cif_text_atom_stats(path)
    parser = MMCIFParser(QUIET=True)
    try:
        structure = parser.get_structure(path.stem, str(path))
    except Exception:
        return cif_text_atom_stats(path)
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    for atom in structure.get_atoms():
        atom_lines += 1
        atom_name = atom.get_name().strip()
        if atom_name == "CA":
            ca_atoms += 1
        residue = atom.get_parent()
        if residue.id[0] != " ":
            hetatm_lines += 1
    non_ca_atoms = atom_lines - ca_atoms
    ca_only_like = "YES" if atom_lines > 0 and non_ca_atoms == 0 else "NO"
    if atom_lines == 0:
        status = "FAIL_NO_ATOM_RECORDS"
    elif ca_only_like == "YES":
        status = "FAIL_CA_ONLY_SOURCE"
    else:
        status = "PASS_FULL_ATOM_SOURCE"
    return {
        "source_file_exists": "YES",
        "atom_lines": str(atom_lines),
        "hetatm_lines": str(hetatm_lines),
        "ca_atoms": str(ca_atoms),
        "non_ca_atoms": str(non_ca_atoms),
        "ca_only_like": ca_only_like,
        "atom_audit_status": status,
    }


def cif_text_atom_stats(path: Path) -> dict[str, str]:
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            parts = line.split()
            atom_lines += 1
            if parts and parts[0] == "HETATM":
                hetatm_lines += 1
            atom_name = parts[3] if len(parts) > 3 else ""
            if atom_name == "CA":
                ca_atoms += 1
    non_ca_atoms = atom_lines - ca_atoms
    ca_only_like = "YES" if atom_lines > 0 and non_ca_atoms == 0 else "NO"
    if atom_lines == 0:
        status = "FAIL_NO_ATOM_RECORDS"
    elif ca_only_like == "YES":
        status = "FAIL_CA_ONLY_SOURCE"
    else:
        status = "PASS_FULL_ATOM_SOURCE"
    return {
        "source_file_exists": "YES",
        "atom_lines": str(atom_lines),
        "hetatm_lines": str(hetatm_lines),
        "ca_atoms": str(ca_atoms),
        "non_ca_atoms": str(non_ca_atoms),
        "ca_only_like": ca_only_like,
        "atom_audit_status": status,
    }


def pdb_source_and_output(target: str, source_root: Path, pdb_out: Path) -> tuple[Path | None, Path, str, str]:
    match = PDB_RE.match(target)
    if not match:
        return None, pdb_out / f"{safe_name(target)}.pdb", "", "ERROR_UNSUPPORTED_PDB_TARGET_FORMAT"
    _pdbid, _assembly, chain_label = match.groups()
    atom_chain = chain_label.split("-", 1)[0]
    stem = f"{safe_name(target)}.chain_{safe_name(atom_chain)}"
    source_dir = source_root / "04_p2rank/full/reference_structures/materialized/pdb_chains"
    for suffix in (".pdb", ".cif", ".mmcif"):
        candidate = source_dir / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate, pdb_out / f"{stem}{suffix}", atom_chain, ""
    filename = f"{stem}.pdb"
    return (
        source_dir / filename,
        pdb_out / filename,
        atom_chain,
        "",
    )


def afsp_source_and_output(target: str, source_root: Path, afsp_out: Path) -> tuple[Path, Path]:
    filename = f"{safe_name(target)}.pdb"
    return (
        source_root / "04_p2rank/full/reference_structures/materialized/afsp" / filename,
        afsp_out / filename,
    )


def copy_reference(source: Path | None, output: Path, overwrite: bool) -> tuple[str, str]:
    if source is None:
        return "FAILED", "unsupported target format"
    if not source.is_file() or source.stat().st_size == 0:
        return "FAILED", f"source file missing or empty: {source}"
    if output.exists() and not overwrite:
        if output.is_file() and output.stat().st_size == source.stat().st_size:
            return "REUSED_EXISTING_OUTPUT", ""
        return "BLOCKED_EXISTING_OUTPUT", f"existing output differs or overwrite disabled: {output}"
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return "COPIED", ""


MANIFEST_FIELDS = [
    "unique_reference_id",
    "reference_layer",
    "target",
    "source_url",
    "source_cache_path",
    "reference_file_path",
    "reference_file_source_class",
    "requested_chain",
    "download_status",
    "materialization_status",
    "materialization_error",
    "atom_lines_extracted",
    "hetatm_lines_extracted",
    "ter_lines_extracted",
    "expected_output_exists",
]

REPORT_FIELDS = [
    "reference_layer",
    "target",
    "panel_row_count",
    "source_file_path",
    "output_file_path",
    "requested_chain",
    "copy_status",
    "copy_error",
    "source_file_exists",
    "atom_lines",
    "hetatm_lines",
    "ca_atoms",
    "non_ca_atoms",
    "ca_only_like",
    "atom_audit_status",
]


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_summary(path: Path, rows: list[dict[str, str]]) -> Counter:
    summary: Counter = Counter()
    summary["unique_targets"] = len(rows)
    for row in rows:
        layer = row.get("reference_layer", "")
        summary[f"layer_{layer}_targets"] += 1
        summary[f"copy_status_{row.get('copy_status', '')}"] += 1
        summary[f"atom_audit_status_{row.get('atom_audit_status', '')}"] += 1
        summary[f"ca_only_like_{row.get('ca_only_like', '')}"] += 1
        if row.get("expected_output_exists") == "YES":
            summary["materialized_files_exist"] += 1
    summary["failed_targets"] = sum(
        1 for row in rows
        if row.get("copy_status") not in {"COPIED", "REUSED_EXISTING_OUTPUT"}
        or row.get("atom_audit_status") != "PASS_FULL_ATOM_SOURCE"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key in sorted(summary):
            writer.writerow([key, summary[key]])
    return summary


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    source_root = args.source_run_root.resolve()
    allowed_root = args.allowed_root.resolve()
    for path in (args.pdb_out, args.afsp_out, args.manifest, args.report, args.summary):
        require_under(path, allowed_root)
    require_under(source_root, project_root)
    if not args.panel.is_file():
        raise SystemExit(f"ERROR: panel missing: {args.panel}")

    targets = read_unique_targets(args.panel)
    report_rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []
    for index, row in enumerate(targets, start=1):
        layer = row["reference_layer"]
        target = row["target"]
        if layer == "PDB":
            source, output, requested_chain, target_error = pdb_source_and_output(target, source_root, args.pdb_out)
            source_url = ""
        else:
            source, output = afsp_source_and_output(target, source_root, args.afsp_out)
            requested_chain = ""
            target_error = ""
            source_url = f"https://alphafold.ebi.ac.uk/files/{target}.pdb"
        if target_error:
            copy_status, copy_error = "FAILED", target_error
            audit = atom_stats(Path("__missing__"))
        else:
            audit = atom_stats(source)
            copy_status, copy_error = copy_reference(source, output, args.overwrite)
        expected_output_exists = "YES" if output.is_file() and output.stat().st_size > 0 else "NO"
        source_path = rel(source, project_root) if source is not None else ""
        output_path = rel(output, project_root)
        report_row = {
            "reference_layer": layer,
            "target": target,
            "panel_row_count": row.get("panel_row_count", ""),
            "source_file_path": source_path,
            "output_file_path": output_path,
            "requested_chain": requested_chain,
            "copy_status": copy_status,
            "copy_error": copy_error,
            "expected_output_exists": expected_output_exists,
            **audit,
        }
        report_rows.append(report_row)
        manifest_rows.append({
            "unique_reference_id": f"REFCACHE{index:05d}",
            "reference_layer": layer,
            "target": target,
            "source_url": source_url,
            "source_cache_path": source_path,
            "reference_file_path": output_path,
            "reference_file_source_class": (
                "full_atom_cache_pdb_chain"
                if layer == "PDB" else "full_atom_cache_afsp_model"
            ),
            "requested_chain": requested_chain,
            "download_status": "NOT_ATTEMPTED_CACHE_ONLY",
            "materialization_status": copy_status,
            "materialization_error": copy_error,
            "atom_lines_extracted": audit.get("atom_lines", "0"),
            "hetatm_lines_extracted": audit.get("hetatm_lines", "0"),
            "ter_lines_extracted": "0",
            "expected_output_exists": expected_output_exists,
        })

    write_tsv(args.report, report_rows, REPORT_FIELDS)
    write_tsv(args.manifest, manifest_rows, MANIFEST_FIELDS)
    summary = write_summary(args.summary, report_rows)
    print("VERMAMG_M09C_FULLATOM_CACHE_MATERIALIZATION")
    print(f"source_run_root\t{rel(source_root, project_root)}")
    print(f"unique_targets\t{summary['unique_targets']}")
    print(f"PDB_targets\t{summary.get('layer_PDB_targets', 0)}")
    print(f"AFSP_targets\t{summary.get('layer_AFSP_targets', 0)}")
    print(f"materialized_files_exist\t{summary['materialized_files_exist']}")
    print(f"failed_targets\t{summary['failed_targets']}")
    print(f"manifest\t{rel(args.manifest, project_root)}")
    print(f"report\t{rel(args.report, project_root)}")
    print(f"summary\t{rel(args.summary, project_root)}")
    return 2 if int(summary["failed_targets"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
