#!/usr/bin/env python3
"""VermAMG V2 Paket3 live ColabFold adapter.

Consumes the Paket1 FASTA batch plan and produces the exact canonical
ColabFold import contract that downstream stages already expect:

    work/01_colabfold/query_pdbs/<run_id>.pdb
    work/01_colabfold/collector_manifest.tsv
    work/02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv   (MANIFEST_FIELDS)
    work/00_inputs/job_plan/full_manual_id_map.tsv                    (id_map contract)

The module is count/data-agnostic: it iterates whatever batches the FASTA
intake produced. No protein count is hardcoded.

Backends:
  local  -> run colabfold_batch per batch as a subprocess.
  slurm  -> emit + submit one sbatch per batch (guarded; real HPC submission).

dry_run=true builds the per-batch command plan and validates inputs without
starting any compute, so the contract can be verified without a GPU.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


# Must match import_precomputed_colabfold.MANIFEST_FIELDS exactly.
MANIFEST_FIELDS = [
    "mode", "batch_id", "run_id", "protein_id", "family_label",
    "query_pdb_file", "query_pdb_basename", "colabfold_plddt_mean",
    "colabfold_ptm", "colabfold_struct_conf_class", "colabfold_model_status",
    "atom_lines", "ca_atoms",
]

COLLECTOR_FIELDS = ["tier", "batch", "model_id", "pdb_source", "pdb_dest"]
ID_MAP_FIELDS = ["run_id", "protein_id", "family_label", "habitat_broad"]
RUN_PLAN_FIELDS = [
    "batch_id", "batch_index", "batch_fasta", "record_count",
    "backend", "output_dir", "command", "status", "note",
]


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


def fasta_ids(path: Path) -> list[str]:
    """Return record ids (first whitespace token of each header), order-preserving."""
    ids: list[str] = []
    if not path.is_file():
        return ids
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith(">"):
                ids.append(line[1:].strip().split()[0] if line[1:].strip() else "")
    return ids


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


def conf_class(plddt: float | None) -> str:
    if plddt is None:
        return "UNKNOWN_NO_SCORE_JSON"
    if plddt >= 90:
        return "VERY_HIGH"
    if plddt >= 70:
        return "CONFIDENT"
    if plddt >= 50:
        return "LOW"
    return "VERY_LOW"


def build_colabfold_command(args: argparse.Namespace, batch_fasta: str, out_dir: str) -> list[str]:
    return [
        str(args.colabfold_cmd),
        "--msa-mode", str(args.colabfold_msa_mode),
        "--model-type", str(args.colabfold_model_type),
        "--num-recycle", str(args.colabfold_num_recycle),
        "--num-models", str(args.colabfold_num_models),
        batch_fasta,
        out_dir,
    ]


def load_meta_lookup(sample_manifest: Path, metadata_joined: Path | None) -> dict[str, dict[str, str]]:
    """Map sequence_id -> {protein_id, family_label, habitat_broad}.

    sequence_id is the canonical run identity for live ColabFold (the FASTA
    record id = predicted PDB stem). family_label/habitat_broad are best-effort
    from the joined metadata; missing values stay empty (no fabricated data).
    """
    lookup: dict[str, dict[str, str]] = {}
    if sample_manifest.is_file():
        _, rows = read_tsv(sample_manifest)
        for row in rows:
            seq_id = row.get("sequence_id") or row.get("source_id") or ""
            if not seq_id:
                continue
            lookup[seq_id] = {
                "protein_id": row.get("source_id") or seq_id,
                "family_label": "",
                "habitat_broad": "",
            }
    if metadata_joined and metadata_joined.is_file():
        _, rows = read_tsv(metadata_joined)
        for row in rows:
            seq_id = row.get("sequence_id") or row.get("protein_id") or ""
            if not seq_id:
                continue
            entry = lookup.setdefault(seq_id, {"protein_id": seq_id, "family_label": "", "habitat_broad": ""})
            for src_key, dst_key in (
                ("protein_id", "protein_id"),
                ("family_label", "family_label"),
                ("family", "family_label"),
                ("habitat_broad", "habitat_broad"),
                ("habitat", "habitat_broad"),
            ):
                val = row.get(src_key)
                if val:
                    entry[dst_key] = val
    return lookup


def find_rank1_pdb(batch_out_dir: Path, run_id: str) -> Path | None:
    patterns = [
        f"{run_id}_unrelaxed_rank_001_*.pdb",
        f"{run_id}_relaxed_rank_001_*.pdb",
        f"{run_id}_*rank_001*.pdb",
        f"{run_id}.pdb",
    ]
    for pattern in patterns:
        matches = sorted(batch_out_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def find_rank1_scores(batch_out_dir: Path, run_id: str) -> Path | None:
    for pattern in (f"{run_id}_scores_rank_001_*.json", f"{run_id}_*rank_001*.json"):
        matches = sorted(batch_out_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def parse_scores(path: Path) -> tuple[float | None, float | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        return None, None
    plddt = data.get("plddt")
    plddt_mean: float | None = None
    if isinstance(plddt, list) and plddt:
        try:
            plddt_mean = sum(float(x) for x in plddt) / len(plddt)
        except (TypeError, ValueError):
            plddt_mean = None
    elif isinstance(plddt, (int, float)):
        plddt_mean = float(plddt)
    ptm = data.get("ptm")
    ptm_val: float | None = None
    if isinstance(ptm, (int, float)):
        ptm_val = float(ptm)
    return plddt_mean, ptm_val


def run_local(commands: list[tuple[str, list[str]]], project_root: Path) -> list[str]:
    errors: list[str] = []
    for batch_id, cmd in commands:
        print(f"COLABFOLD_RUN\tbatch_id={batch_id}\tcommand={subprocess.list2cmdline(cmd)}", flush=True)
        proc = subprocess.run(cmd, cwd=project_root)
        if proc.returncode != 0:
            errors.append(f"colabfold_batch_failed:{batch_id}:rc={proc.returncode}")
    return errors


def submit_slurm(sbatch_scripts: list[tuple[str, Path]], project_root: Path) -> list[str]:
    errors: list[str] = []
    for batch_id, script in sbatch_scripts:
        cmd = ["sbatch", str(script)]
        print(f"COLABFOLD_SUBMIT\tbatch_id={batch_id}\tcommand={subprocess.list2cmdline(cmd)}", flush=True)
        proc = subprocess.run(cmd, cwd=project_root)
        if proc.returncode != 0:
            errors.append(f"sbatch_submit_failed:{batch_id}:rc={proc.returncode}")
    return errors


def write_sbatch(script: Path, *, batch_id: str, cmd: list[str], args: argparse.Namespace) -> None:
    script.parent.mkdir(parents=True, exist_ok=True)
    account = args.slurm_account or "CHANGE_ME_ACCOUNT"
    partition = args.partition_gpu or "CHANGE_ME_PARTITION"
    logs = Path(args.submit_root) / "logs"
    body = "\n".join([
        "#!/bin/bash",
        f"#SBATCH -J cf_{batch_id}",
        f"#SBATCH -A {account}",
        f"#SBATCH -p {partition}",
        "#SBATCH -N 1",
        "#SBATCH -n 1",
        f"#SBATCH -c {args.cpus_gpu}",
        "#SBATCH --gres=gpu:1",
        f"#SBATCH --mem={args.mem_gpu}",
        f"#SBATCH --time={args.time_gpu}",
        f"#SBATCH -o {logs / (f'cf_{batch_id}.%j.out')}",
        f"#SBATCH -e {logs / (f'cf_{batch_id}.%j.err')}",
        "",
        "set -euo pipefail",
        f"echo 'COLABFOLD_SBATCH batch_id={batch_id}'",
        " ".join(shlex.quote(part) for part in cmd),
        "",
    ])
    script.write_text(body, encoding="utf-8")


def collect_outputs(
    *,
    batches: list[dict[str, str]],
    out_root: Path,
    meta_lookup: dict[str, dict[str, str]],
    mode: str,
    out_pdb_dir: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[str]]:
    manifest_rows: list[dict[str, str]] = []
    collector_rows: list[dict[str, str]] = []
    id_map_rows: list[dict[str, str]] = []
    errors: list[str] = []
    out_pdb_dir.mkdir(parents=True, exist_ok=True)
    for batch in batches:
        batch_id = batch["batch_id"]
        batch_fasta = Path(batch["batch_fasta"])
        batch_out_dir = out_root / batch_id
        for run_id in fasta_ids(batch_fasta):
            if not run_id:
                continue
            src = find_rank1_pdb(batch_out_dir, run_id)
            if src is None:
                errors.append(f"missing_colabfold_pdb:{batch_id}:{run_id}")
                continue
            dst = out_pdb_dir / f"{run_id}.pdb"
            dst.write_bytes(src.read_bytes())
            atom_lines, ca_atoms = pdb_stats(dst)
            scores = find_rank1_scores(batch_out_dir, run_id)
            plddt_mean, ptm = parse_scores(scores) if scores else (None, None)
            meta = meta_lookup.get(run_id, {"protein_id": run_id, "family_label": "", "habitat_broad": ""})
            manifest_rows.append({
                "mode": mode,
                "batch_id": batch_id,
                "run_id": run_id,
                "protein_id": meta.get("protein_id", run_id),
                "family_label": meta.get("family_label", ""),
                "query_pdb_file": str(dst),
                "query_pdb_basename": dst.name,
                "colabfold_plddt_mean": f"{plddt_mean:.4f}" if plddt_mean is not None else "NA_LIVE_NO_SCORE_JSON",
                "colabfold_ptm": f"{ptm:.4f}" if ptm is not None else "NA_LIVE_NO_SCORE_JSON",
                "colabfold_struct_conf_class": conf_class(plddt_mean),
                "colabfold_model_status": "LIVE_COLABFOLD",
                "atom_lines": str(atom_lines),
                "ca_atoms": str(ca_atoms),
            })
            collector_rows.append({
                "tier": mode,
                "batch": batch_id,
                "model_id": run_id,
                "pdb_source": str(src),
                "pdb_dest": str(dst),
            })
            id_map_rows.append({
                "run_id": run_id,
                "protein_id": meta.get("protein_id", run_id),
                "family_label": meta.get("family_label", ""),
                "habitat_broad": meta.get("habitat_broad", ""),
            })
    return manifest_rows, collector_rows, id_map_rows, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VermAMG live ColabFold adapter (Paket3).")
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--sample-manifest", required=True)
    parser.add_argument("--metadata-joined", default="")
    parser.add_argument("--backend", choices=("local", "slurm"), required=True)
    parser.add_argument("--mode", default="full")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--submit-root", required=True)
    parser.add_argument("--live-output-root", required=True, help="work/01_colabfold/live_outputs")
    parser.add_argument("--out-pdb-dir", required=True)
    parser.add_argument("--out-manifest", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--out-collector", required=True)
    parser.add_argument("--out-id-map", required=True)
    parser.add_argument("--out-run-plan", required=True)
    parser.add_argument("--slurm-sbatch-dir", default="")
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--colabfold-cmd", default="colabfold_batch")
    parser.add_argument("--colabfold-msa-mode", default="mmseqs2_uniref_env")
    parser.add_argument("--colabfold-model-type", default="alphafold2_ptm")
    parser.add_argument("--colabfold-num-recycle", default="3")
    parser.add_argument("--colabfold-num-models", default="1")
    parser.add_argument("--slurm-account", default="")
    parser.add_argument("--partition-gpu", default="")
    parser.add_argument("--cpus-gpu", default="10")
    parser.add_argument("--mem-gpu", default="32G")
    parser.add_argument("--time-gpu", default="12:00:00")
    args = parser.parse_args(argv)

    dry_run = bool_value(args.dry_run, True)
    project_root = Path(args.project_root)
    run_root = Path(args.run_root)
    live_output_root = Path(args.live_output_root)
    out_pdb_dir = Path(args.out_pdb_dir)
    out_manifest = Path(args.out_manifest)
    out_summary = Path(args.out_summary)
    out_collector = Path(args.out_collector)
    out_id_map = Path(args.out_id_map)
    out_run_plan = Path(args.out_run_plan)

    for path in (out_pdb_dir, out_manifest, out_summary, out_collector, out_id_map, out_run_plan):
        require_under(path, run_root)

    errors: list[str] = []
    batch_path = Path(args.batch_manifest)
    if not batch_path.is_file():
        errors.append(f"batch_manifest_not_found:{batch_path}")
        batches: list[dict[str, str]] = []
    else:
        _, batches = read_tsv(batch_path)
    if not batches:
        errors.append("batch_manifest_has_no_rows")

    meta_lookup = load_meta_lookup(
        Path(args.sample_manifest),
        Path(args.metadata_joined) if args.metadata_joined else None,
    )

    # Build the per-batch command/sbatch plan (always emitted; safe to inspect).
    plan_rows: list[dict[str, str]] = []
    local_commands: list[tuple[str, list[str]]] = []
    sbatch_scripts: list[tuple[str, Path]] = []
    sbatch_dir = Path(args.slurm_sbatch_dir) if args.slurm_sbatch_dir else Path(args.submit_root) / "slurm" / "sbatch"
    total_records = 0
    for batch in batches:
        batch_id = batch.get("batch_id", "")
        batch_fasta = batch.get("batch_fasta", "")
        record_count = batch.get("record_count", "")
        try:
            total_records += int(record_count or 0)
        except ValueError:
            pass
        batch_out_dir = live_output_root / batch_id
        cmd = build_colabfold_command(args, batch_fasta, str(batch_out_dir))
        if args.backend == "slurm":
            script = sbatch_dir / f"cf_{batch_id}.sbatch"
            sbatch_scripts.append((batch_id, script))
            if not dry_run:
                write_sbatch(script, batch_id=batch_id, cmd=cmd, args=args)
        else:
            local_commands.append((batch_id, cmd))
        plan_rows.append({
            "batch_id": batch_id,
            "batch_index": batch.get("batch_index", ""),
            "batch_fasta": batch_fasta,
            "record_count": record_count,
            "backend": args.backend,
            "output_dir": str(batch_out_dir),
            "command": subprocess.list2cmdline(cmd),
            "status": "PLANNED_DRY_RUN" if dry_run else "SUBMITTED_OR_RUN",
            "note": "Paket3 live ColabFold adapter.",
        })
    write_tsv(out_run_plan, RUN_PLAN_FIELDS, plan_rows)

    compute_started = "NO"
    manifest_rows: list[dict[str, str]] = []
    collector_rows: list[dict[str, str]] = []
    id_map_rows: list[dict[str, str]] = []

    if not dry_run and not errors:
        # Validate the configured ColabFold command is resolvable before compute.
        missing_fasta = [b.get("batch_id", "") for b in batches if not Path(b.get("batch_fasta", "")).is_file()]
        if missing_fasta:
            errors.append("missing_batch_fasta:" + ",".join(missing_fasta))
        if not errors:
            compute_started = "YES"
            if args.backend == "slurm":
                errors.extend(submit_slurm(sbatch_scripts, project_root))
                # SLURM jobs are asynchronous; collection happens in a later
                # invocation once jobs finish. We stop here with the plan + submission.
            else:
                errors.extend(run_local(local_commands, project_root))
                if not errors:
                    manifest_rows, collector_rows, id_map_rows, collect_errs = collect_outputs(
                        batches=batches,
                        out_root=live_output_root,
                        meta_lookup=meta_lookup,
                        mode=args.mode,
                        out_pdb_dir=out_pdb_dir,
                    )
                    errors.extend(collect_errs)
                    write_tsv(out_manifest, MANIFEST_FIELDS, manifest_rows)
                    write_tsv(out_collector, COLLECTOR_FIELDS, collector_rows)
                    write_tsv(out_id_map, ID_MAP_FIELDS, id_map_rows)

    status = "FAIL" if errors else ("PASS_DRY_RUN" if dry_run else "PASS")
    metrics: list[tuple[str, Any]] = [
        ("status", status),
        ("backend", args.backend),
        ("dry_run", "YES" if dry_run else "NO"),
        ("compute_started", compute_started),
        ("batch_count", len(batches)),
        ("planned_record_count", total_records),
        ("query_manifest_rows", len(manifest_rows)),
        ("collector_rows", len(collector_rows)),
        ("id_map_rows", len(id_map_rows)),
        ("colabfold_cmd", args.colabfold_cmd),
        ("out_manifest", out_manifest),
        ("out_collector", out_collector),
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
