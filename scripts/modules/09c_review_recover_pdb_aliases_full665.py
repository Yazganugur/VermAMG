#!/usr/bin/env python3
"""Reviewed recovery for two full665 PDB alias materialization misses.

This is deliberately narrow. It only considers the two audited targets where
Foldseek exported an alternative same-PDB/same-assembly file that contains the
requested atom-chain label.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDB_DIR = PROJECT_ROOT / "04_p2rank/full/reference_structures/materialized/pdb"
RESOLUTION_DIR = PROJECT_ROOT / "04_p2rank/full/reference_resolution"
RECOVERY_TSV = RESOLUTION_DIR / "full_reviewed_recovered_reference_aliases.tsv"
RESOLVED_MANIFEST = PROJECT_ROOT / "04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv"
UNIQUE_MANIFEST = PROJECT_ROOT / "04_p2rank/full/input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"
RESOLUTION_REPORT = RESOLUTION_DIR / "full_reference_panel_file_resolution_report.tsv"
RESOLUTION_SUMMARY = RESOLUTION_DIR / "full_reference_panel_file_resolution_summary.tsv"

RECOVERY_STATUS = "REVIEW_RECOVERED_SAME_ASSEMBLY_REQUESTED_CHAIN_PRESENT"
TARGETS = ("6vlx-assembly1_B-2", "7d7o-assembly1_B-2")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reviewed full665 PDB alias recovery.")
    parser.add_argument("--write", action="store_true", help="Create reviewed recovered copies.")
    parser.add_argument(
        "--annotate-m09b",
        action="store_true",
        help="Update M09B resolved/report/summary TSVs with reviewed recovery status.",
    )
    return parser.parse_args()


def require_under(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def parse_target(target: str) -> tuple[str, str, str, str]:
    pdbid, rest = target.split("-assembly", 1)
    assembly, chain_label = rest.split("_", 1)
    atom_chain = chain_label.split("-", 1)[0]
    return pdbid.lower(), assembly, chain_label, atom_chain


def pdb_stats(path: Path, atom_chain: str) -> dict[str, int]:
    atom_lines = 0
    ca_atoms = 0
    requested_chain_atom_lines = 0
    requested_chain_ca_atoms = 0
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            atom_lines += 1
            atom_name = line[12:16].strip()
            chain = line[21].strip()
            if atom_name == "CA":
                ca_atoms += 1
            if chain == atom_chain:
                requested_chain_atom_lines += 1
                if atom_name == "CA":
                    requested_chain_ca_atoms += 1
    return {
        "atom_lines": atom_lines,
        "ca_atoms": ca_atoms,
        "requested_chain_atom_lines": requested_chain_atom_lines,
        "requested_chain_ca_atoms": requested_chain_ca_atoms,
    }


def candidate_metadata(path: Path) -> tuple[str, str]:
    pdbid, assembly, _chain_label, _atom_chain = parse_target(path.stem)
    return pdbid, assembly


def validate_target(target: str) -> dict[str, str]:
    pdbid, assembly, chain_label, atom_chain = parse_target(target)
    requested_path = PDB_DIR / f"{target}.pdb"
    same_pdb_assembly = []

    for path in sorted(PDB_DIR.glob(f"{pdbid}-assembly{assembly}_*.pdb")):
        cand_pdbid, cand_assembly = candidate_metadata(path)
        if cand_pdbid == pdbid and cand_assembly == assembly:
            stats = pdb_stats(path, atom_chain)
            if stats["requested_chain_atom_lines"] > 0 and stats["requested_chain_ca_atoms"] > 0:
                same_pdb_assembly.append((path, stats))

    if len(same_pdb_assembly) != 1:
        return {
            "target": target,
            "status": "INVALID_AMBIGUOUS_OR_MISSING_CANDIDATE",
            "candidate_count": str(len(same_pdb_assembly)),
            "candidate_file": "",
            "recovered_file": str(requested_path),
            "same_pdb_id": "YES",
            "same_assembly": "YES",
            "requested_chain_label": chain_label,
            "requested_atom_chain": atom_chain,
            "requested_chain_present": "NO",
            "atom_lines": "0",
            "ca_atoms": "0",
            "requested_chain_atom_lines": "0",
            "requested_chain_ca_atoms": "0",
            "note": "Expected exactly one same-PDB/same-assembly candidate with requested atom-chain present.",
        }

    candidate, stats = same_pdb_assembly[0]
    return {
        "target": target,
        "status": RECOVERY_STATUS,
        "candidate_count": "1",
        "candidate_file": str(candidate.relative_to(PROJECT_ROOT)),
        "recovered_file": str(requested_path.relative_to(PROJECT_ROOT)),
        "same_pdb_id": "YES",
        "same_assembly": "YES",
        "requested_chain_label": chain_label,
        "requested_atom_chain": atom_chain,
        "requested_chain_present": "YES",
        "atom_lines": str(stats["atom_lines"]),
        "ca_atoms": str(stats["ca_atoms"]),
        "requested_chain_atom_lines": str(stats["requested_chain_atom_lines"]),
        "requested_chain_ca_atoms": str(stats["requested_chain_ca_atoms"]),
        "note": "Reviewed recovery: copy uses requested target basename; source remains same-PDB/same-assembly candidate.",
    }


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "target",
        "status",
        "candidate_count",
        "candidate_file",
        "recovered_file",
        "same_pdb_id",
        "same_assembly",
        "requested_chain_label",
        "requested_atom_chain",
        "requested_chain_present",
        "atom_lines",
        "ca_atoms",
        "requested_chain_atom_lines",
        "requested_chain_ca_atoms",
        "note",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_recovery_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def annotate_m09b(rows: list[dict[str, str]]) -> None:
    recovered = {row["target"]: row for row in rows if row["status"] == RECOVERY_STATUS}
    if not recovered:
        raise SystemExit("ERROR: no valid recovery rows available for M09B annotation")

    fields, resolved_rows = read_tsv(RESOLVED_MANIFEST)
    changed = 0
    for row in resolved_rows:
        if row.get("target") not in recovered:
            continue
        if row.get("reference_layer") != "PDB":
            continue
        rec = recovered[row["target"]]
        row["reference_file_path"] = rec["recovered_file"]
        row["reference_file_exists"] = "YES"
        row["reference_file_resolution_status"] = RECOVERY_STATUS
        row["resolution_method"] = RECOVERY_STATUS
        row["resolution_n_matches"] = rec["candidate_count"]
        row["reference_file_source_class"] = "review_recovered_same_assembly_requested_chain_present"
        changed += 1
    write_rows(RESOLVED_MANIFEST, fields, resolved_rows)

    report_fields, report_rows = read_tsv(RESOLUTION_REPORT)
    report_changed = 0
    for row in report_rows:
        if row.get("target") not in recovered:
            continue
        if row.get("reference_layer") != "PDB":
            continue
        rec = recovered[row["target"]]
        row["resolution_status"] = RECOVERY_STATUS
        row["resolution_method"] = RECOVERY_STATUS
        row["resolution_n_matches"] = rec["candidate_count"]
        row["reference_file_path"] = rec["recovered_file"]
        row["comment"] = rec["note"]
        report_changed += 1
    write_rows(RESOLUTION_REPORT, report_fields, report_rows)

    unique_changed = 0
    if UNIQUE_MANIFEST.exists():
        unique_fields, unique_rows = read_tsv(UNIQUE_MANIFEST)
        for row in unique_rows:
            if row.get("target") not in recovered:
                continue
            if row.get("reference_layer") != "PDB":
                continue
            row["reference_file_source_class"] = "review_recovered_same_assembly_requested_chain_present"
            unique_changed += 1
        write_rows(UNIQUE_MANIFEST, unique_fields, unique_rows)

    summary = Counter()
    summary["panel_rows"] = len(resolved_rows)
    summary["resolved_rows"] = sum(1 for r in resolved_rows if r.get("reference_file_exists") == "YES")
    summary["missing_rows"] = sum(1 for r in resolved_rows if r.get("reference_file_exists") != "YES")
    summary["unique_resolved_reference_files"] = len(
        {r.get("reference_file_path") for r in resolved_rows if r.get("reference_file_exists") == "YES"}
    )
    summary["candidate_structure_files_indexed"] = summary["unique_resolved_reference_files"]
    for row in resolved_rows:
        layer = row.get("reference_layer", "")
        status = row.get("reference_file_resolution_status", "")
        method = row.get("resolution_method", "")
        source = row.get("reference_file_source_class", "")
        summary[f"layer_{layer}_rows"] += 1
        if row.get("reference_file_exists") == "YES":
            summary[f"layer_{layer}_resolved"] += 1
        summary[f"status_{status}"] += 1
        summary[f"method_{method}"] += 1
        if source:
            summary[f"source_{source}"] += 1

    with RESOLUTION_SUMMARY.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key in sorted(summary):
            writer.writerow([key, summary[key]])

    print(f"annotated_resolved_rows\t{changed}")
    print(f"annotated_report_rows\t{report_changed}")
    print(f"annotated_unique_rows\t{unique_changed}")


def main() -> int:
    require_under(PDB_DIR, PROJECT_ROOT / "04_p2rank/full/reference_structures/materialized")
    require_under(RECOVERY_TSV, RESOLUTION_DIR)
    if not PDB_DIR.is_dir():
        raise SystemExit(f"ERROR: materialized PDB directory missing: {PDB_DIR}")

    if args.annotate_m09b and not args.write and RECOVERY_TSV.exists():
        rows = read_recovery_tsv(RECOVERY_TSV)
    else:
        rows = [validate_target(target) for target in TARGETS]
    print("===== REVIEWED PDB ALIAS RECOVERY =====")
    for row in rows:
        print(
            "\t".join(
                [
                    row["target"],
                    row["status"],
                    row["candidate_file"],
                    row["recovered_file"],
                    f"atom_lines={row['atom_lines']}",
                    f"ca_atoms={row['ca_atoms']}",
                    f"requested_chain_atom_lines={row['requested_chain_atom_lines']}",
                    f"requested_chain_ca_atoms={row['requested_chain_ca_atoms']}",
                ]
            )
        )

    if any(row["status"] != RECOVERY_STATUS for row in rows):
        print("validation_status\tBLOCKED_INVALID_RECOVERY")
        return 2

    if not args.write and not args.annotate_m09b:
        print("validation_status\tDRY_RUN_OK")
        print("note\tNo files written. Re-run with --write to create reviewed recovered copies.")
        return 0

    if args.write:
        RESOLUTION_DIR.mkdir(parents=True, exist_ok=True)
        for row in rows:
            src = PROJECT_ROOT / row["candidate_file"]
            dst = PROJECT_ROOT / row["recovered_file"]
            require_under(dst, PDB_DIR)
            if dst.exists():
                raise SystemExit(f"ERROR: refusing to overwrite existing recovered file: {dst}")
            shutil.copyfile(src, dst)

        write_tsv(RECOVERY_TSV, rows)
        print(f"recovery_audit_tsv\t{RECOVERY_TSV.relative_to(PROJECT_ROOT)}")

    if args.annotate_m09b:
        annotate_m09b(rows)

    print("validation_status\tPASS_REVIEW_RECOVERY_WRITTEN_OR_ANNOTATED")
    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main())
