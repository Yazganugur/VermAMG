#!/usr/bin/env python3
"""VermAMG V2 Paket3 live Foldseek adapter.

Consumes the live (or precomputed) ColabFold query PDB manifest and produces
the exact Foldseek all-hit contract that downstream M06B/M07B expect:

    work/02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv   (EXPECTED_HIT_COLUMNS)
    work/02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv  (EXPECTED_HIT_COLUMNS)
    work/02_foldseek/tables/full/full_manual_id_map.tsv              (id_map contract)

The proven command sequence (Foldseek easy-search / createdb -> search -> convertalis workflow):

    foldseek createdb   <query_pdb_dir> <query_db>
    foldseek search     <query_db> <target_db> <result_db> <tmp> --threads N --max-seqs 50 -a
    foldseek convertalis <query_db> <target_db> <result_db> <out.tmp> \
        --format-output query,target,evalue,bits,prob,alntmscore,qtmscore,ttmscore,lddt,qcov,tcov,qlen,tlen

then prepend the header row and append a constant `batch` tag column.

Count/data-agnostic: every query in the manifest flows through. No protein
count is hardcoded. dry_run=true validates inputs and writes the command plan
without running Foldseek, so the contract can be verified without DBs.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
from pathlib import Path
from typing import Any


# Must match import_precomputed_foldseek_hits.EXPECTED_HIT_COLUMNS exactly.
HIT_COLUMNS = [
    "query", "target", "evalue", "bits", "prob", "alntmscore", "qtmscore",
    "ttmscore", "lddt", "qcov", "tcov", "qlen", "tlen", "batch",
]
CONVERTALIS_FORMAT = "query,target,evalue,bits,prob,alntmscore,qtmscore,ttmscore,lddt,qcov,tcov,qlen,tlen"
ID_MAP_FIELDS = ["run_id", "protein_id", "family_label", "habitat_broad"]
RUN_PLAN_FIELDS = ["search", "target_db", "step", "command", "status", "note"]


def bool_value(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        rows = [{k: (v if v is not None else "") for k, v in row.items()} for row in reader]
    return fields, rows


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, metrics: list[tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows((k, str(v)) for k, v in metrics)


def require_under(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"ERROR: refusing output outside allowed root: path={path} root={root}") from exc


def stage_query_pdbs(manifest_rows: list[dict[str, str]], pdb_input_dir: Path) -> tuple[int, list[str]]:
    """Copy each query PDB to <pdb_input_dir>/<run_id>.pdb. Returns (copied, errors)."""
    errors: list[str] = []
    if pdb_input_dir.exists():
        for old in pdb_input_dir.glob("*.pdb"):
            old.unlink()
    pdb_input_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for row in manifest_rows:
        run_id = row.get("run_id", "")
        src = Path(row.get("query_pdb_file", ""))
        if not run_id:
            continue
        if not src.is_file():
            errors.append(f"missing_query_pdb:{run_id}:{src}")
            continue
        shutil.copy2(src, pdb_input_dir / f"{run_id}.pdb")
        copied += 1
    return copied, errors


def foldseek_commands(
    foldseek_bin: str,
    query_pdb_dir: Path,
    query_db: Path,
    target_db: str,
    result_db: Path,
    tmp_dir: Path,
    hits_tmp: Path,
    threads: int,
) -> list[tuple[str, list[str]]]:
    return [
        ("createdb", [foldseek_bin, "createdb", str(query_pdb_dir), str(query_db)]),
        ("search", [foldseek_bin, "search", str(query_db), target_db, str(result_db), str(tmp_dir),
                    "--threads", str(threads), "--max-seqs", "50", "-a"]),
        ("convertalis", [foldseek_bin, "convertalis", str(query_db), target_db, str(result_db), str(hits_tmp),
                         "--format-output", CONVERTALIS_FORMAT]),
    ]


def finalize_all_hits(hits_tmp: Path, out_hits: Path, batch_tag: str) -> int:
    """Prepend header, append constant batch column. Returns data row count."""
    out_hits.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with out_hits.open("w", encoding="utf-8", newline="") as out_handle:
        out_handle.write("\t".join(HIT_COLUMNS) + "\n")
        if hits_tmp.is_file():
            with hits_tmp.open("r", encoding="utf-8", errors="replace") as in_handle:
                for line in in_handle:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    out_handle.write(line + "\t" + batch_tag + "\n")
                    rows += 1
    return rows


def run_search(
    *,
    label: str,
    foldseek_bin: str,
    query_pdb_dir: Path,
    target_db: str,
    work_dir: Path,
    out_hits: Path,
    threads: int,
    batch_tag: str,
    project_root: Path,
) -> tuple[int, list[str]]:
    errors: list[str] = []
    query_db = work_dir / f"{label}_query_db"
    result_db = work_dir / f"{label}_result_db"
    tmp_dir = work_dir / f"{label}_tmp"
    hits_tmp = work_dir / f"{label}_all_hits.tmp"
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    if not Path(f"{target_db}.dbtype").is_file():
        errors.append(f"target_db_missing:{label}:{target_db}.dbtype")
        return 0, errors
    for step, cmd in foldseek_commands(foldseek_bin, query_pdb_dir, query_db, target_db, result_db, tmp_dir, hits_tmp, threads):
        print(f"FOLDSEEK_RUN\tsearch={label}\tstep={step}\tcommand={subprocess.list2cmdline(cmd)}", flush=True)
        proc = subprocess.run(cmd, cwd=project_root)
        if proc.returncode != 0:
            errors.append(f"foldseek_{step}_failed:{label}:rc={proc.returncode}")
            return 0, errors
    rows = finalize_all_hits(hits_tmp, out_hits, batch_tag)
    return rows, errors


def build_id_map(manifest_rows: list[dict[str, str]], metadata_joined: Path | None) -> list[dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    if metadata_joined and metadata_joined.is_file():
        _, rows = read_tsv(metadata_joined)
        for row in rows:
            key = row.get("sequence_id") or row.get("protein_id") or ""
            if key:
                meta[key] = row
    id_rows: list[dict[str, str]] = []
    for row in manifest_rows:
        run_id = row.get("run_id", "")
        protein_id = row.get("protein_id") or run_id
        mrow = meta.get(run_id) or meta.get(protein_id) or {}
        id_rows.append({
            "run_id": run_id,
            "protein_id": protein_id,
            "family_label": row.get("family_label") or mrow.get("family_label") or mrow.get("family") or "",
            "habitat_broad": mrow.get("habitat_broad") or mrow.get("habitat") or "",
        })
    return id_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VermAMG live Foldseek adapter (Paket3).")
    parser.add_argument("--query-manifest", required=True)
    parser.add_argument("--metadata-joined", default="")
    parser.add_argument("--backend", choices=("local", "slurm"), default="local")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--work-dir", required=True, help="work/02_foldseek/live_search")
    parser.add_argument("--out-pdb-all-hits", required=True)
    parser.add_argument("--out-afsp-all-hits", required=True)
    parser.add_argument("--out-id-map", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--out-run-plan", required=True)
    parser.add_argument("--foldseek-bin", default="")
    parser.add_argument("--pdb-foldseek-db", default="")
    parser.add_argument("--afsp-foldseek-db", default="")
    parser.add_argument("--threads", default="4")
    parser.add_argument("--dry-run", default="true")
    args = parser.parse_args(argv)

    dry_run = bool_value(args.dry_run, True)
    project_root = Path(args.project_root)
    run_root = Path(args.run_root)
    work_dir = Path(args.work_dir)
    out_pdb_all_hits = Path(args.out_pdb_all_hits)
    out_afsp_all_hits = Path(args.out_afsp_all_hits)
    out_id_map = Path(args.out_id_map)
    out_summary = Path(args.out_summary)
    out_run_plan = Path(args.out_run_plan)
    try:
        threads = int(args.threads)
    except ValueError:
        threads = 4

    for path in (out_pdb_all_hits, out_afsp_all_hits, out_id_map, out_summary, out_run_plan, work_dir):
        require_under(path, run_root)

    errors: list[str] = []
    manifest_path = Path(args.query_manifest)
    if not manifest_path.is_file():
        errors.append(f"query_manifest_not_found:{manifest_path}")
        manifest_rows: list[dict[str, str]] = []
    else:
        _, manifest_rows = read_tsv(manifest_path)
    if not manifest_rows:
        errors.append("query_manifest_has_no_rows")

    pdb_input_dir = work_dir / "query_pdb_inputs"
    foldseek_bin = args.foldseek_bin or "foldseek"

    searches = [
        ("pdb", args.pdb_foldseek_db, out_pdb_all_hits, "pdb_search"),
        ("afsp", args.afsp_foldseek_db, out_afsp_all_hits, "afsp_search"),
    ]

    # Always emit the command plan so the contract is inspectable in dry-run.
    plan_rows: list[dict[str, str]] = []
    for label, target_db, _out, _tag in searches:
        query_db = work_dir / f"{label}_query_db"
        result_db = work_dir / f"{label}_result_db"
        tmp_dir = work_dir / f"{label}_tmp"
        hits_tmp = work_dir / f"{label}_all_hits.tmp"
        for step, cmd in foldseek_commands(foldseek_bin, pdb_input_dir, query_db, target_db or f"<{label}_db>",
                                           result_db, tmp_dir, hits_tmp, threads):
            plan_rows.append({
                "search": label,
                "target_db": target_db or f"<{label}_db_not_configured>",
                "step": step,
                "command": subprocess.list2cmdline(cmd),
                "status": "PLANNED_DRY_RUN" if dry_run else "RUN",
                "note": "Paket3 live Foldseek adapter.",
            })
    write_tsv(out_run_plan, RUN_PLAN_FIELDS, plan_rows)

    pdb_rows = 0
    afsp_rows = 0
    compute_started = "NO"

    if not dry_run and not errors:
        if not args.pdb_foldseek_db:
            errors.append("pdb_foldseek_db_not_configured")
        if not args.afsp_foldseek_db:
            errors.append("afsp_foldseek_db_not_configured")
        copied, stage_errs = stage_query_pdbs(manifest_rows, pdb_input_dir)
        errors.extend(stage_errs)
        if not errors:
            compute_started = "YES"
            pdb_rows, errs = run_search(
                label="pdb", foldseek_bin=foldseek_bin, query_pdb_dir=pdb_input_dir,
                target_db=args.pdb_foldseek_db, work_dir=work_dir, out_hits=out_pdb_all_hits,
                threads=threads, batch_tag="pdb_search", project_root=project_root,
            )
            errors.extend(errs)
            afsp_rows, errs = run_search(
                label="afsp", foldseek_bin=foldseek_bin, query_pdb_dir=pdb_input_dir,
                target_db=args.afsp_foldseek_db, work_dir=work_dir, out_hits=out_afsp_all_hits,
                threads=threads, batch_tag="afsp_search", project_root=project_root,
            )
            errors.extend(errs)
            if not errors:
                write_tsv(out_id_map, ID_MAP_FIELDS, build_id_map(manifest_rows, Path(args.metadata_joined) if args.metadata_joined else None))

    status = "FAIL" if errors else ("PASS_DRY_RUN" if dry_run else "PASS")
    metrics: list[tuple[str, Any]] = [
        ("status", status),
        ("backend", args.backend),
        ("dry_run", "YES" if dry_run else "NO"),
        ("compute_started", compute_started),
        ("query_manifest_rows", len(manifest_rows)),
        ("pdb_all_hit_rows", pdb_rows),
        ("afsp_all_hit_rows", afsp_rows),
        ("foldseek_bin", foldseek_bin),
        ("pdb_db_configured", "YES" if args.pdb_foldseek_db else "NO"),
        ("afsp_db_configured", "YES" if args.afsp_foldseek_db else "NO"),
        ("out_pdb_all_hits", out_pdb_all_hits),
        ("out_afsp_all_hits", out_afsp_all_hits),
        ("out_id_map", out_id_map),
        ("out_run_plan", out_run_plan),
        ("error_count", len(errors)),
    ]
    for error in errors:
        metrics.append(("error", error))
    write_summary(out_summary, metrics)
    for key, value in metrics:
        print(f"{key}\t{value}")
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
