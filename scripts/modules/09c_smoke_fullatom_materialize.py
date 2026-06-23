#!/usr/bin/env python3
"""Download and materialize a small full-atom reference smoke subset."""

from __future__ import annotations

import argparse
import csv
import shutil
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

try:
    from Bio.PDB import MMCIFIO, MMCIFParser, Select
except ImportError:  # pragma: no cover - runtime dependency check
    MMCIFIO = MMCIFParser = Select = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="Materialize every target in the plan.")
    parser.add_argument("--out-manifest", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path("."))
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


def resolve_path(value: str, project_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def download(url: str, path: Path, overwrite: bool) -> tuple[str, str]:
    if path.is_file() and path.stat().st_size > 0 and not overwrite:
        return "CACHE_HIT", ""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, path.open("wb") as out_handle:
            shutil.copyfileobj(response, out_handle)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return "DOWNLOAD_FAILED", str(exc)
    if not path.is_file() or path.stat().st_size == 0:
        return "DOWNLOAD_FAILED", "download produced empty file"
    return "DOWNLOADED", ""


def extract_chain_pdb(source: Path, output: Path, chain_id: str, overwrite: bool) -> tuple[str, str, Counter]:
    if output.exists() and not overwrite:
        return "MATERIALIZED_EXISTS", "", Counter()
    stats: Counter = Counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open(errors="replace") as in_handle, output.open("w", encoding="utf-8", newline="") as out_handle:
        for line in in_handle:
            rec = line[:6].strip()
            if rec in {"ATOM", "HETATM", "ANISOU", "TER"}:
                line_chain = line[21:22].strip() if len(line) >= 22 else ""
                if line_chain != chain_id:
                    continue
                out_handle.write(line.rstrip("\n") + "\n")
                stats[f"{rec.lower()}_lines"] += 1
                if rec in {"ATOM", "HETATM"}:
                    stats["atom_hetatm_lines"] += 1
                    atom_name = line[12:16].strip() if len(line) >= 16 else ""
                    if atom_name:
                        stats[f"atom_name_{atom_name}"] += 1
            elif rec == "END":
                continue
        out_handle.write("END\n")
    if stats["atom_hetatm_lines"] == 0:
        return "CHAIN_EXTRACTION_FAILED", f"requested chain not found or empty: {chain_id}", stats
    return "MATERIALIZED", "", stats


def extract_chain_cif(source: Path, output: Path, chain_id: str, overwrite: bool) -> tuple[str, str, Counter]:
    if output.exists() and not overwrite:
        return "MATERIALIZED_EXISTS", "", Counter()
    if MMCIFParser is None or MMCIFIO is None or Select is None:
        return "CHAIN_EXTRACTION_FAILED", "Biopython MMCIFParser/MMCIFIO unavailable", Counter()

    class ChainSelect(Select):
        def accept_chain(self, chain):  # noqa: N802 - Biopython API
            return 1 if chain.id == chain_id else 0

    parser = MMCIFParser(QUIET=True)
    try:
        structure = parser.get_structure(source.stem, str(source))
    except Exception as exc:
        return "CHAIN_EXTRACTION_FAILED", f"mmCIF parse failed: {exc}", Counter()

    stats: Counter = Counter()
    for atom in structure.get_atoms():
        residue = atom.get_parent()
        chain = residue.get_parent()
        if chain.id != chain_id:
            continue
        stats["atom_hetatm_lines"] += 1
        hetflag = residue.id[0]
        if hetflag == " ":
            stats["atom_lines"] += 1
        else:
            stats["hetatm_lines"] += 1
        stats[f"atom_name_{atom.get_name().strip()}"] += 1
    if stats["atom_hetatm_lines"] == 0:
        return "CHAIN_EXTRACTION_FAILED", f"requested chain not found or empty in mmCIF: {chain_id}", stats

    output.parent.mkdir(parents=True, exist_ok=True)
    io = MMCIFIO()
    io.set_structure(structure)
    try:
        io.save(str(output), ChainSelect())
    except Exception as exc:
        return "CHAIN_EXTRACTION_FAILED", f"mmCIF write failed: {exc}", stats
    return "MATERIALIZED", "", stats


def copy_afsp(source: Path, output: Path, overwrite: bool) -> tuple[str, str]:
    if output.exists() and not overwrite:
        return "MATERIALIZED_EXISTS", ""
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    return "MATERIALIZED", ""


FIELDS = [
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


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, str]]) -> Counter:
    summary: Counter = Counter()
    summary["smoke_targets"] = len(rows)
    for row in rows:
        summary[f"layer_{row.get('reference_layer', '')}_targets"] += 1
        summary[f"download_status_{row.get('download_status', '')}"] += 1
        summary[f"materialization_status_{row.get('materialization_status', '')}"] += 1
        if row.get("expected_output_exists") == "YES":
            summary["materialized_files_exist"] += 1
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
    allowed_root = args.allowed_root
    for path in (args.out_manifest, args.out_summary):
        require_under(path, allowed_root)
    if not args.target and not args.all:
        raise SystemExit("ERROR: provide at least one --target or --all")
    plan_rows = {row["target"]: row for row in read_tsv(args.plan)}
    selected_targets = sorted(plan_rows) if args.all else args.target
    missing = [target for target in selected_targets if target not in plan_rows]
    if missing:
        raise SystemExit(f"ERROR: targets not found in plan: {missing}")

    manifest_rows: list[dict[str, str]] = []
    for index, target in enumerate(selected_targets, start=1):
        plan = plan_rows[target]
        layer = plan["reference_layer"]
        output = resolve_path(plan["expected_output_path"], project_root)
        requested_chain = plan.get("atom_chain", "")
        if layer == "PDB":
            pdb_url = plan.get("alternate_source_url") or plan.get("source_url", "")
            cif_url = plan.get("source_url", "")
            source_url = pdb_url
            pdb_id = plan.get("pdb_id", "").lower()
            source_cache = output.parents[2] / "full_atom_sources/pdb_entries" / f"{pdb_id}.pdb"
        else:
            source_url = plan.get("source_url", "")
            source_cache = resolve_path(plan["source_cache_path"], project_root)

        for path in (source_cache, output):
            require_under(path, allowed_root)

        download_status, download_error = download(source_url, source_cache, args.overwrite)
        source_format = "PDB" if layer == "PDB" else "PDB"
        if layer == "PDB" and download_status == "DOWNLOAD_FAILED" and cif_url:
            cif_cache = source_cache.with_suffix(".cif")
            require_under(cif_cache, allowed_root)
            cif_status, cif_error = download(cif_url, cif_cache, args.overwrite)
            if cif_status in {"CACHE_HIT", "DOWNLOADED"}:
                source_url = cif_url
                source_cache = cif_cache
                output = output.with_suffix(".cif")
                download_status = cif_status
                download_error = ""
                source_format = "CIF"
            else:
                download_status = f"{download_status};CIF_{cif_status}"
                download_error = f"PDB: {download_error}; CIF: {cif_error}"
        materialization_status = "NOT_ATTEMPTED"
        materialization_error = download_error
        stats: Counter = Counter()
        if download_status in {"CACHE_HIT", "DOWNLOADED"}:
            if layer == "PDB":
                if source_format == "CIF":
                    materialization_status, materialization_error, stats = extract_chain_cif(
                        source_cache,
                        output,
                        requested_chain,
                        args.overwrite,
                    )
                else:
                    materialization_status, materialization_error, stats = extract_chain_pdb(
                        source_cache,
                        output,
                        requested_chain,
                        args.overwrite,
                    )
            else:
                materialization_status, materialization_error = copy_afsp(source_cache, output, args.overwrite)
        manifest_rows.append({
            "unique_reference_id": f"SMOKE{index:03d}",
            "reference_layer": layer,
            "target": target,
            "source_url": source_url,
            "source_cache_path": rel(source_cache, project_root),
            "reference_file_path": rel(output, project_root),
            "reference_file_source_class": (
                "smoke_full_atom_pdb_chain_extraction"
                if layer == "PDB" else "smoke_full_atom_afsp_model"
            ),
            "requested_chain": requested_chain,
            "download_status": download_status,
            "materialization_status": materialization_status,
            "materialization_error": materialization_error,
            "atom_lines_extracted": str(stats.get("atom_lines", 0)),
            "hetatm_lines_extracted": str(stats.get("hetatm_lines", 0)),
            "ter_lines_extracted": str(stats.get("ter_lines", 0)),
            "expected_output_exists": "YES" if output.is_file() and output.stat().st_size > 0 else "NO",
        })

    write_tsv(args.out_manifest, manifest_rows, FIELDS)
    summary = write_summary(args.out_summary, manifest_rows)
    failed = sum(
        1 for row in manifest_rows
        if row["materialization_status"] not in {"MATERIALIZED", "MATERIALIZED_EXISTS"}
    )
    print("VERMAMG_FULLATOM_REFERENCE_SMOKE_MATERIALIZATION")
    print(f"smoke_targets\t{len(manifest_rows)}")
    print(f"PDB_targets\t{summary.get('layer_PDB_targets', 0)}")
    print(f"AFSP_targets\t{summary.get('layer_AFSP_targets', 0)}")
    print(f"failed_targets\t{failed}")
    print(f"manifest\t{rel(args.out_manifest, project_root)}")
    print(f"summary\t{rel(args.out_summary, project_root)}")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
