#!/usr/bin/env python3
"""Plan and audit full-atom reference materialization for VermAMG M09C.

This helper is intentionally dry-run first. It derives the expected unique
PDB/AFSP targets from the selected reference panel, maps each target to the
full-atom source URL/cache path and the future materialized output path, and
audits any source files already present. It does not run Foldseek, P2Rank, or
download anything.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path


PDB_RE = re.compile(r"^([0-9][A-Za-z0-9]{3})-assembly([0-9]+)_([A-Za-z0-9-]+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--corrected-run-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--out-missing", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--allow-existing-outputs", action="store_true")
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


def read_panel_targets(path: Path) -> tuple[list[dict[str, str]], Counter]:
    with path.open(newline="", errors="replace") as handle:
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
    rows = []
    for key in sorted(by_key):
        row = dict(by_key[key])
        row["panel_row_count"] = str(counts[key])
        rows.append(row)
    return rows, counts


def atom_audit(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {
            "audit_file_exists": "NO",
            "atom_lines": "0",
            "hetatm_lines": "0",
            "ca_atoms": "0",
            "non_ca_atoms": "0",
            "residue_count_est": "0",
            "ca_ratio": "",
            "distinct_atom_names": "",
            "top_atom_names": "",
            "ca_only_like": "UNKNOWN",
            "atom_audit_status": "MISSING_SOURCE_CACHE",
        }
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    atom_names: Counter = Counter()
    residues = set()
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            if line.startswith("HETATM"):
                hetatm_lines += 1
            atom_lines += 1
            atom_name = line[12:16].strip() if len(line) >= 16 else ""
            chain = line[21:22].strip() if len(line) >= 22 else ""
            resseq = line[22:26].strip() if len(line) >= 26 else ""
            icode = line[26:27].strip() if len(line) >= 27 else ""
            if atom_name:
                atom_names[atom_name] += 1
            if atom_name == "CA":
                ca_atoms += 1
            if chain or resseq:
                residues.add((chain, resseq, icode))
    non_ca_atoms = atom_lines - ca_atoms
    residue_count = len(residues)
    ca_ratio = (ca_atoms / atom_lines) if atom_lines else 0.0
    ca_only_like = "YES" if atom_lines > 0 and non_ca_atoms == 0 else "NO"
    if atom_lines == 0:
        status = "NO_ATOM_RECORDS"
    elif ca_only_like == "YES":
        status = "FAIL_CA_ONLY_SOURCE"
    else:
        status = "PASS_FULL_ATOM_SOURCE"
    return {
        "audit_file_exists": "YES",
        "atom_lines": str(atom_lines),
        "hetatm_lines": str(hetatm_lines),
        "ca_atoms": str(ca_atoms),
        "non_ca_atoms": str(non_ca_atoms),
        "residue_count_est": str(residue_count),
        "ca_ratio": f"{ca_ratio:.3f}",
        "distinct_atom_names": ",".join(sorted(atom_names)),
        "top_atom_names": ",".join(f"{name}:{count}" for name, count in atom_names.most_common(8)),
        "ca_only_like": ca_only_like,
        "atom_audit_status": status,
    }


def pdb_plan(row: dict[str, str], run_root: Path, project_root: Path) -> dict[str, str]:
    target = row["target"]
    match = PDB_RE.match(target)
    if not match:
        return {
            **row,
            "pdb_id": "",
            "assembly_label": "",
            "chain_label": "",
            "atom_chain": "",
            "source_url": "",
            "alternate_source_url": "",
            "source_cache_path": "",
            "expected_output_path": "",
            "materialization_plan": "ERROR_UNSUPPORTED_PDB_TARGET_FORMAT",
            "plan_status": "FAIL_UNSUPPORTED_TARGET",
        }
    pdb_id, assembly_label, chain_label = match.groups()
    pdb_id_upper = pdb_id.upper()
    pdb_id_lower = pdb_id.lower()
    atom_chain = chain_label.split("-", 1)[0]
    source_cache = run_root / "04_p2rank/full/reference_structures/full_atom_sources/pdb_entries" / f"{pdb_id_lower}.cif"
    output = run_root / "04_p2rank/full/reference_structures/materialized/pdb_chains" / f"{safe_name(target)}.chain_{safe_name(atom_chain)}.pdb"
    audit = atom_audit(source_cache)
    plan_status = "READY_SOURCE_CACHE" if audit["atom_audit_status"] == "PASS_FULL_ATOM_SOURCE" else audit["atom_audit_status"]
    return {
        **row,
        "pdb_id": pdb_id_lower,
        "assembly_label": f"assembly{assembly_label}",
        "chain_label": chain_label,
        "atom_chain": atom_chain,
        "source_url": f"https://files.rcsb.org/download/{pdb_id_upper}.cif",
        "alternate_source_url": f"https://files.rcsb.org/download/{pdb_id_upper}.pdb",
        "source_cache_path": rel(source_cache, project_root),
        "expected_output_path": rel(output, project_root),
        "materialization_plan": "CACHE_RCSB_FULL_ENTRY_CIF_THEN_EXTRACT_REQUESTED_CHAIN_FULL_ATOM_PDB",
        "plan_status": plan_status,
        **audit,
    }


def afsp_plan(row: dict[str, str], run_root: Path, project_root: Path) -> dict[str, str]:
    target = row["target"]
    source_cache = run_root / "04_p2rank/full/reference_structures/full_atom_sources/afsp_models" / f"{safe_name(target)}.pdb"
    output = run_root / "04_p2rank/full/reference_structures/materialized/afsp" / f"{safe_name(target)}.pdb"
    audit = atom_audit(source_cache)
    plan_status = "READY_SOURCE_CACHE" if audit["atom_audit_status"] == "PASS_FULL_ATOM_SOURCE" else audit["atom_audit_status"]
    return {
        **row,
        "pdb_id": "",
        "assembly_label": "",
        "chain_label": "",
        "atom_chain": "",
        "source_url": f"https://alphafold.ebi.ac.uk/files/{target}.pdb",
        "alternate_source_url": f"https://alphafold.ebi.ac.uk/files/{target}.cif",
        "source_cache_path": rel(source_cache, project_root),
        "expected_output_path": rel(output, project_root),
        "materialization_plan": "CACHE_AFSP_FULL_ATOM_MODEL_THEN_COPY_TO_MATERIALIZED_AFSP",
        "plan_status": plan_status,
        **audit,
    }


PLAN_FIELDS = [
    "target_index",
    "reference_layer",
    "target",
    "panel_row_count",
    "example_query",
    "example_family",
    "example_panel_order",
    "example_panel_role",
    "example_source_rank",
    "example_support_class",
    "pdb_id",
    "assembly_label",
    "chain_label",
    "atom_chain",
    "source_url",
    "alternate_source_url",
    "source_cache_path",
    "expected_output_path",
    "materialization_plan",
    "plan_status",
    "audit_file_exists",
    "atom_lines",
    "hetatm_lines",
    "ca_atoms",
    "non_ca_atoms",
    "residue_count_est",
    "ca_ratio",
    "distinct_atom_names",
    "top_atom_names",
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


def write_summary(path: Path, rows: list[dict[str, str]]) -> None:
    summary: Counter = Counter()
    summary["unique_targets"] = len(rows)
    for row in rows:
        layer = row["reference_layer"]
        summary[f"{layer.lower()}_target_count"] += 1
        summary[f"plan_status_{row.get('plan_status', '')}"] += 1
        summary[f"atom_audit_status_{row.get('atom_audit_status', '')}"] += 1
        summary[f"layer_{layer}_source_cache_found"] += 1 if row.get("audit_file_exists") == "YES" else 0
        summary[f"layer_{layer}_source_cache_missing"] += 1 if row.get("audit_file_exists") != "YES" else 0
    summary["download_attempted_targets"] = 0
    summary["download_failed_targets"] = 0
    summary["dry_run_materialized_targets"] = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key in sorted(summary):
            writer.writerow([key, summary[key]])


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    run_root = args.corrected_run_root
    allowed_root = args.allowed_root
    for path in (run_root, args.out_plan, args.out_summary, args.out_missing):
        require_under(path, allowed_root)
    if not args.panel.is_file():
        raise SystemExit(f"ERROR: panel missing: {args.panel}")

    targets, _counts = read_panel_targets(args.panel)
    plan_rows: list[dict[str, str]] = []
    for row in targets:
        if row["reference_layer"] == "PDB":
            planned = pdb_plan(row, run_root, project_root)
        else:
            planned = afsp_plan(row, run_root, project_root)
        planned["target_index"] = str(len(plan_rows) + 1)
        output_path = project_root / planned["expected_output_path"]
        if output_path.exists() and not args.allow_existing_outputs:
            planned["plan_status"] = "BLOCKED_EXISTING_OUTPUT"
        plan_rows.append(planned)

    missing_rows = [
        row for row in plan_rows
        if row.get("atom_audit_status") in {"MISSING_SOURCE_CACHE", "NO_ATOM_RECORDS", "FAIL_CA_ONLY_SOURCE"}
        or row.get("plan_status", "").startswith("FAIL")
        or row.get("plan_status") == "BLOCKED_EXISTING_OUTPUT"
    ]

    write_tsv(args.out_plan, plan_rows, PLAN_FIELDS)
    write_tsv(args.out_missing, missing_rows, PLAN_FIELDS)
    write_summary(args.out_summary, plan_rows)

    counts = Counter(row["reference_layer"] for row in plan_rows)
    print("VERMAMG_FULLATOM_REFERENCE_MATERIALIZATION_DRY_RUN")
    print(f"corrected_run_root\t{rel(run_root, project_root)}")
    print(f"expected_unique_targets\t{len(plan_rows)}")
    print(f"PDB_target_count\t{counts.get('PDB', 0)}")
    print(f"AFSP_target_count\t{counts.get('AFSP', 0)}")
    print(f"source_cache_missing_targets\t{sum(1 for row in plan_rows if row.get('audit_file_exists') != 'YES')}")
    print(f"ca_only_source_targets\t{sum(1 for row in plan_rows if row.get('atom_audit_status') == 'FAIL_CA_ONLY_SOURCE')}")
    print(f"download_attempted_targets\t0")
    print(f"download_failed_targets\t0")
    print(f"plan_path\t{rel(args.out_plan, project_root)}")
    print(f"summary_path\t{rel(args.out_summary, project_root)}")
    print(f"missing_path\t{rel(args.out_missing, project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
