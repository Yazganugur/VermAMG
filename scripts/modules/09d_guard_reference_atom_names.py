#!/usr/bin/env python3
"""Hard atom-name QC guard for reference P2Rank inputs."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

try:
    from Bio.PDB import MMCIFParser
except ImportError:  # pragma: no cover
    MMCIFParser = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-audit", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--allow-ca-only-diagnostic", action="store_true")
    return parser.parse_args()


def require_under(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing path outside allowed root: path={path} root={root}") from exc


def resolve_path(value: str, project_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def rel(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def empty_audit(status: str, requested_chain: str = "") -> dict[str, str]:
    return {
        "reference_file_exists": "NO" if status == "FAIL_MISSING_REFERENCE_FILE" else "YES",
        "atom_lines": "0",
        "hetatm_lines": "0",
        "ca_atoms": "0",
        "non_ca_atoms": "0",
        "residue_count_est": "0",
        "ca_ratio": "",
        "distinct_atom_names": "",
        "top_atom_names": "",
        "has_N": "NO",
        "has_CA": "NO",
        "has_C": "NO",
        "has_O": "NO",
        "has_CB": "NO",
        "chain_ids": "",
        "requested_chain": requested_chain,
        "requested_chain_present": "NO" if requested_chain else "",
        "ca_only_like": "UNKNOWN",
        "guard_status": status,
    }


def finalize_audit(
    *,
    atom_lines: int,
    hetatm_lines: int,
    ca_atoms: int,
    atom_names: Counter,
    residues: set,
    chains: set,
    allow_ca_only: bool,
    requested_chain: str,
) -> dict[str, str]:
    non_ca_atoms = atom_lines - ca_atoms
    ca_ratio = (ca_atoms / atom_lines) if atom_lines else 0.0
    ca_only_like = "YES" if atom_lines > 0 and non_ca_atoms == 0 else "NO"
    requested_chain_present = "YES" if requested_chain and requested_chain in chains else ("NO" if requested_chain else "")
    has_backbone = all(atom_names.get(name, 0) > 0 for name in ("N", "CA", "C", "O"))
    if atom_lines == 0:
        status = "FAIL_NO_ATOM_RECORDS"
    elif ca_only_like == "YES" and not allow_ca_only:
        status = "FAIL_CA_ONLY_REFERENCE_INPUT"
    elif not has_backbone:
        status = "FAIL_MISSING_BACKBONE_ATOMS"
    elif requested_chain and requested_chain_present != "YES":
        status = "FAIL_REQUESTED_CHAIN_NOT_PRESENT"
    elif ca_only_like == "YES":
        status = "PASS_DIAGNOSTIC_CA_ONLY_ALLOWED"
    else:
        status = "PASS_FULL_ATOM_REFERENCE_INPUT"
    return {
        "reference_file_exists": "YES",
        "atom_lines": str(atom_lines),
        "hetatm_lines": str(hetatm_lines),
        "ca_atoms": str(ca_atoms),
        "non_ca_atoms": str(non_ca_atoms),
        "residue_count_est": str(len(residues)),
        "ca_ratio": f"{ca_ratio:.3f}",
        "distinct_atom_names": ",".join(sorted(atom_names)),
        "top_atom_names": ",".join(f"{name}:{count}" for name, count in atom_names.most_common(8)),
        "has_N": "YES" if atom_names.get("N", 0) > 0 else "NO",
        "has_CA": "YES" if atom_names.get("CA", 0) > 0 else "NO",
        "has_C": "YES" if atom_names.get("C", 0) > 0 else "NO",
        "has_O": "YES" if atom_names.get("O", 0) > 0 else "NO",
        "has_CB": "YES" if atom_names.get("CB", 0) > 0 else "NO",
        "chain_ids": ",".join(sorted(chains)),
        "requested_chain": requested_chain,
        "requested_chain_present": requested_chain_present,
        "ca_only_like": ca_only_like,
        "guard_status": status,
    }


def audit_cif(path: Path, allow_ca_only: bool, requested_chain: str = "") -> dict[str, str]:
    if MMCIFParser is None:
        return audit_cif_text(path, allow_ca_only, requested_chain)
    parser = MMCIFParser(QUIET=True)
    try:
        structure = parser.get_structure(path.stem, str(path))
    except Exception:
        return audit_cif_text(path, allow_ca_only, requested_chain)
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    atom_names: Counter = Counter()
    residues = set()
    chains = set()
    for atom in structure.get_atoms():
        residue = atom.get_parent()
        chain = residue.get_parent()
        atom_lines += 1
        atom_name = atom.get_name().strip()
        atom_names[atom_name] += 1
        if atom_name == "CA":
            ca_atoms += 1
        if residue.id[0] != " ":
            hetatm_lines += 1
        chains.add(chain.id)
        residues.add((chain.id, str(residue.id[1]), residue.id[2].strip()))
    return finalize_audit(
        atom_lines=atom_lines,
        hetatm_lines=hetatm_lines,
        ca_atoms=ca_atoms,
        atom_names=atom_names,
        residues=residues,
        chains=chains,
        allow_ca_only=allow_ca_only,
        requested_chain=requested_chain,
    )


def audit_cif_text(path: Path, allow_ca_only: bool, requested_chain: str = "") -> dict[str, str]:
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    atom_names: Counter = Counter()
    residues = set()
    chains = set()
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            parts = line.split()
            atom_lines += 1
            if parts and parts[0] == "HETATM":
                hetatm_lines += 1
            atom_name = parts[3] if len(parts) > 3 else ""
            chain = parts[16] if len(parts) > 16 else (parts[6] if len(parts) > 6 else "")
            resseq = parts[15] if len(parts) > 15 else (parts[8] if len(parts) > 8 else "")
            if atom_name:
                atom_names[atom_name] += 1
            if atom_name == "CA":
                ca_atoms += 1
            if chain:
                chains.add(chain)
            if chain or resseq:
                residues.add((chain, resseq, ""))
    return finalize_audit(
        atom_lines=atom_lines,
        hetatm_lines=hetatm_lines,
        ca_atoms=ca_atoms,
        atom_names=atom_names,
        residues=residues,
        chains=chains,
        allow_ca_only=allow_ca_only,
        requested_chain=requested_chain,
    )


def audit_structure(path: Path, allow_ca_only: bool, requested_chain: str = "") -> dict[str, str]:
    if not path.is_file():
        return empty_audit("FAIL_MISSING_REFERENCE_FILE", requested_chain)
    if path.suffix.lower() in {".cif", ".mmcif"}:
        return audit_cif(path, allow_ca_only, requested_chain)
    atom_lines = 0
    hetatm_lines = 0
    ca_atoms = 0
    atom_names: Counter = Counter()
    residues = set()
    chains = set()
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            atom_lines += 1
            if line.startswith("HETATM"):
                hetatm_lines += 1
            atom_name = line[12:16].strip() if len(line) >= 16 else ""
            chain = line[21:22].strip() if len(line) >= 22 else ""
            resseq = line[22:26].strip() if len(line) >= 26 else ""
            icode = line[26:27].strip() if len(line) >= 27 else ""
            if atom_name:
                atom_names[atom_name] += 1
            if chain:
                chains.add(chain)
            if atom_name == "CA":
                ca_atoms += 1
            if chain or resseq:
                residues.add((chain, resseq, icode))
    return finalize_audit(
        atom_lines=atom_lines,
        hetatm_lines=hetatm_lines,
        ca_atoms=ca_atoms,
        atom_names=atom_names,
        residues=residues,
        chains=chains,
        allow_ca_only=allow_ca_only,
        requested_chain=requested_chain,
    )


AUDIT_FIELDS = [
    "unique_reference_id",
    "reference_layer",
    "target",
    "reference_file_path",
    "reference_file_source_class",
    "reference_file_exists",
    "atom_lines",
    "hetatm_lines",
    "ca_atoms",
    "non_ca_atoms",
    "residue_count_est",
    "ca_ratio",
    "distinct_atom_names",
    "top_atom_names",
    "has_N",
    "has_CA",
    "has_C",
    "has_O",
    "has_CB",
    "chain_ids",
    "requested_chain",
    "requested_chain_present",
    "ca_only_like",
    "guard_status",
]


def write_audit(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in AUDIT_FIELDS})


def write_summary(path: Path, rows: list[dict[str, str]], allow_ca_only: bool) -> Counter:
    summary: Counter = Counter()
    summary["total_references"] = len(rows)
    summary["allow_ca_only_diagnostic"] = "YES" if allow_ca_only else "NO"
    for row in rows:
        summary[f"layer_{row.get('reference_layer', '')}_references"] += 1
        summary[f"guard_status_{row.get('guard_status', '')}"] += 1
        summary[f"ca_only_like_{row.get('ca_only_like', '')}"] += 1
        if row.get("reference_file_exists") == "YES":
            summary["existing_reference_files"] += 1
        else:
            summary["missing_reference_files"] += 1
    summary["failed_references"] = sum(1 for row in rows if row.get("guard_status", "").startswith("FAIL"))
    summary["pass_references"] = len(rows) - int(summary["failed_references"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key in sorted(summary):
            writer.writerow([key, summary[key]])
    return summary


def main() -> int:
    args = parse_args()
    for path in (args.out_audit, args.out_summary):
        require_under(path, args.allowed_root)
    if not args.manifest.is_file():
        raise SystemExit(f"ERROR: manifest missing: {args.manifest}")
    project_root = args.project_root.resolve()
    rows = []
    for source in read_tsv(args.manifest):
        reference_file_path = source.get("reference_file_path") or source.get("expected_output_path") or source.get("source_cache_path") or ""
        full_path = resolve_path(reference_file_path, project_root)
        requested_chain = source.get("requested_chain") or source.get("atom_chain") or ""
        audit = audit_structure(full_path, args.allow_ca_only_diagnostic, requested_chain=requested_chain)
        row = {
            "unique_reference_id": source.get("unique_reference_id", source.get("target_index", "")),
            "reference_layer": source.get("reference_layer", ""),
            "target": source.get("target", ""),
            "reference_file_path": rel(full_path, project_root),
            "reference_file_source_class": source.get("reference_file_source_class", source.get("materialization_plan", "")),
            **audit,
        }
        rows.append(row)
    write_audit(args.out_audit, rows)
    summary = write_summary(args.out_summary, rows, args.allow_ca_only_diagnostic)
    print("VERMAMG_REFERENCE_ATOM_NAME_GUARD")
    print(f"manifest\t{rel(args.manifest, project_root)}")
    print(f"total_references\t{summary['total_references']}")
    print(f"failed_references\t{summary['failed_references']}")
    print(f"ca_only_like_yes\t{summary.get('ca_only_like_YES', 0)}")
    print(f"audit_path\t{rel(args.out_audit, project_root)}")
    print(f"summary_path\t{rel(args.out_summary, project_root)}")
    return 2 if int(summary["failed_references"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
