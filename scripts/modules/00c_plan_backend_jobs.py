#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import shlex
import stat
from pathlib import Path
from typing import Any


JOB_PLAN_FIELDS = [
    "job_id",
    "job_type",
    "backend",
    "scheduler",
    "execution_mode",
    "depends_on",
    "input_path",
    "output_path",
    "script_path",
    "log_stdout",
    "log_stderr",
    "cpus",
    "mem",
    "time",
    "partition",
    "command_preview",
    "status",
    "note",
]


DEPENDENCY_FIELDS = ["job_id", "depends_on", "dependency_type", "status"]


def bool_value(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def slugify(value: str, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or fallback


def q(value: str | Path) -> str:
    return shlex.quote(str(value))


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), [{key: (value if value is not None else "") for key, value in row.items()} for row in reader]


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
        writer.writerows((key, str(value)) for key, value in metrics)


def make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def script_status(script_path: Path, active_backend: str, backend: str) -> str:
    if active_backend == backend:
        return "ACTIVE_BACKEND_DRY_RUN"
    return "INACTIVE_BACKEND_DRY_RUN"


def build_command_preview(job_type: str, input_path: str, output_path: str, args: argparse.Namespace) -> str:
    if job_type == "colabfold_batch":
        return " ".join([
            str(args.colabfold_cmd),
            "--msa-mode", str(args.colabfold_msa_mode),
            "--model-type", str(args.colabfold_model_type),
            "--num-recycle", str(args.colabfold_num_recycle),
            "--num-models", str(args.colabfold_num_models),
            q(input_path),
            q(output_path),
        ])
    if job_type == "collect_colabfold":
        return "# ColabFold output collection is handled by the run pipeline (import_precomputed_colabfold.py / 00d_run_colabfold.py)"
    if job_type == "foldseek_pdb_search":
        return " ".join([q(args.foldseek_bin or "foldseek"), "easy-search", "<query_db>", q(args.pdb_foldseek_db or "<pdb_db>"), q(output_path), "<tmp>"])
    if job_type == "foldseek_afsp_search":
        return " ".join([q(args.foldseek_bin or "foldseek"), "easy-search", "<query_db>", q(args.afsp_foldseek_db or "<afsp_db>"), q(output_path), "<tmp>"])
    return "echo DRY_RUN_ONLY"


def add_job(
    jobs: list[dict[str, str]],
    *,
    job_id: str,
    job_type: str,
    backend: str,
    scheduler: str,
    execution_mode: str,
    depends_on: str,
    input_path: str,
    output_path: str,
    script_path: str,
    log_stdout: str,
    log_stderr: str,
    cpus: str,
    mem: str,
    time: str,
    partition: str,
    command_preview: str,
    status: str,
    note: str,
) -> None:
    jobs.append({
        "job_id": job_id,
        "job_type": job_type,
        "backend": backend,
        "scheduler": scheduler,
        "execution_mode": execution_mode,
        "depends_on": depends_on,
        "input_path": input_path,
        "output_path": output_path,
        "script_path": script_path,
        "log_stdout": log_stdout,
        "log_stderr": log_stderr,
        "cpus": cpus,
        "mem": mem,
        "time": time,
        "partition": partition,
        "command_preview": command_preview,
        "status": status,
        "note": note,
    })


def build_jobs(batch_rows: list[dict[str, str]], args: argparse.Namespace, backend: str, scheduler: str) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    dry_run = bool_value(args.dry_run, True)
    execution_mode = "dry_run_only" if dry_run else "planned_submit_disabled"
    live_status = "PLANNED_DRY_RUN_ONLY"
    if str(args.colabfold_mode).startswith("precomputed") and str(args.foldseek_mode).startswith("precomputed"):
        live_status = "PLANNED_FOR_FUTURE_LIVE_BACKEND"
    note = "Generated by Paket2 backend abstraction; no compute or submit is started."

    colabfold_job_ids: list[str] = []
    if bool_value(args.plan_colabfold, True):
        for index, row in enumerate(batch_rows, start=1):
            batch_id = row.get("batch_id") or f"batch_{index:04d}"
            job_id = slugify(f"cf_{batch_id}", f"cf_{index:04d}")
            colabfold_job_ids.append(job_id)
            input_path = row.get("batch_fasta", "")
            output_path = str(Path(args.run_root) / "work/01_colabfold/live_outputs" / batch_id)
            script_path = str(Path(args.submit_root) / backend / "jobs" / f"{job_id}.sh")
            if backend == "slurm":
                script_path = str(Path(args.slurm_sbatch_dir) / f"{job_id}.sbatch")
            log_stdout = str(Path(args.submit_root) / "logs" / f"{job_id}.out")
            log_stderr = str(Path(args.submit_root) / "logs" / f"{job_id}.err")
            add_job(
                jobs,
                job_id=job_id,
                job_type="colabfold_batch",
                backend=backend,
                scheduler=scheduler,
                execution_mode=execution_mode,
                depends_on="",
                input_path=input_path,
                output_path=output_path,
                script_path=script_path,
                log_stdout=log_stdout,
                log_stderr=log_stderr,
                cpus=str(args.cpus_gpu if backend == "slurm" else args.local_threads),
                mem=str(args.mem_gpu if backend == "slurm" else ""),
                time=str(args.time_gpu if backend == "slurm" else ""),
                partition=str(args.partition_gpu if backend == "slurm" else ""),
                command_preview=build_command_preview("colabfold_batch", input_path, output_path, args),
                status=live_status,
                note=note,
            )

    collect_id = "collect_colabfold"
    if bool_value(args.plan_colabfold, True):
        output_path = str(Path(args.run_root) / "work/01_colabfold/collector_manifest.tsv")
        script_path = str(Path(args.submit_root) / backend / "jobs" / f"{collect_id}.sh")
        if backend == "slurm":
            script_path = str(Path(args.slurm_sbatch_dir) / f"{collect_id}.sbatch")
        add_job(
            jobs,
            job_id=collect_id,
            job_type="collect_colabfold",
            backend=backend,
            scheduler=scheduler,
            execution_mode=execution_mode,
            depends_on=",".join(colabfold_job_ids),
            input_path=str(Path(args.run_root) / "work/01_colabfold/live_outputs"),
            output_path=output_path,
            script_path=script_path,
            log_stdout=str(Path(args.submit_root) / "logs" / f"{collect_id}.out"),
            log_stderr=str(Path(args.submit_root) / "logs" / f"{collect_id}.err"),
            cpus=str(args.cpus_cpu if backend == "slurm" else args.local_threads),
            mem=str(args.mem_cpu if backend == "slurm" else ""),
            time=str(args.time_cpu if backend == "slurm" else ""),
            partition=str(args.partition_cpu if backend == "slurm" else ""),
            command_preview=build_command_preview("collect_colabfold", "", output_path, args),
            status=live_status,
            note=note,
        )

    if bool_value(args.plan_foldseek, True):
        for job_type, db_label, db_path in [
            ("foldseek_pdb_search", "pdb", args.pdb_foldseek_db),
            ("foldseek_afsp_search", "afsp", args.afsp_foldseek_db),
        ]:
            job_id = f"foldseek_{db_label}"
            output_path = str(Path(args.run_root) / "work/02_foldseek/live_tables" / f"{args.mode}_vs_{db_label}_foldseek_all_hits.tsv")
            script_path = str(Path(args.submit_root) / backend / "jobs" / f"{job_id}.sh")
            if backend == "slurm":
                script_path = str(Path(args.slurm_sbatch_dir) / f"{job_id}.sbatch")
            add_job(
                jobs,
                job_id=job_id,
                job_type=job_type,
                backend=backend,
                scheduler=scheduler,
                execution_mode=execution_mode,
                depends_on=collect_id if bool_value(args.plan_colabfold, True) else "",
                input_path=str(Path(args.run_root) / "work/02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv"),
                output_path=output_path,
                script_path=script_path,
                log_stdout=str(Path(args.submit_root) / "logs" / f"{job_id}.out"),
                log_stderr=str(Path(args.submit_root) / "logs" / f"{job_id}.err"),
                cpus=str(args.cpus_cpu if backend == "slurm" else args.local_threads),
                mem=str(args.mem_cpu if backend == "slurm" else ""),
                time=str(args.time_cpu if backend == "slurm" else ""),
                partition=str(args.partition_cpu if backend == "slurm" else ""),
                command_preview=build_command_preview(job_type, "", output_path, args),
                status=live_status,
                note=note if db_path else note + " Foldseek DB path is not configured yet.",
            )
    return jobs


def dependency_rows(jobs: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for job in jobs:
        deps = [dep for dep in job.get("depends_on", "").split(",") if dep]
        if not deps:
            rows.append({"job_id": job["job_id"], "depends_on": "", "dependency_type": "none", "status": "ROOT_JOB"})
            continue
        for dep in deps:
            rows.append({"job_id": job["job_id"], "depends_on": dep, "dependency_type": "afterok", "status": "PLANNED"})
    return rows


def write_local_dry_run(path: Path, job_plan: Path, active_backend: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'JOB_PLAN="${SCRIPT_DIR}/../../00_inputs/job_plan/backend_job_plan.tsv"',
            "",
            "echo '===== VermAMG local backend dry-run ====='",
            f"echo 'active_backend={active_backend}'",
            "echo \"job_plan=${JOB_PLAN}\"",
            "echo 'compute_started=NO'",
            "echo 'submit_started=NO'",
            "echo",
            "awk -F '\\t' 'NR==1 {next} {printf \"DRY_RUN job_id=%s job_type=%s backend=%s depends_on=%s\\n  command=%s\\n\", $1, $2, $3, $6, $16}' \"${JOB_PLAN}\"",
            "",
        ]),
        encoding="utf-8",
    )
    make_executable(path)


def write_slurm_bundle(
    *,
    submit_script: Path,
    sbatch_dir: Path,
    jobs: list[dict[str, str]],
    active_backend: str,
    args: argparse.Namespace,
) -> None:
    submit_script.parent.mkdir(parents=True, exist_ok=True)
    sbatch_dir.mkdir(parents=True, exist_ok=True)
    for job in jobs:
        script = Path(job["script_path"])
        script.parent.mkdir(parents=True, exist_ok=True)
        gres = "#SBATCH --gres=gpu:1" if job["job_type"] == "colabfold_batch" else ""
        partition = job["partition"] or "CHANGE_ME_PARTITION"
        account = args.slurm_account or "CHANGE_ME_ACCOUNT"
        script.write_text(
            "\n".join([
                "#!/bin/bash",
                f"#SBATCH -J {job['job_id']}",
                f"#SBATCH -A {account}",
                f"#SBATCH -p {partition}",
                "#SBATCH -N 1",
                "#SBATCH -n 1",
                f"#SBATCH -c {job['cpus'] or 1}",
                gres,
                f"#SBATCH --mem={job['mem'] or 'CHANGE_ME_MEM'}",
                f"#SBATCH --time={job['time'] or 'CHANGE_ME_TIME'}",
                f"#SBATCH -o {job['log_stdout']}",
                f"#SBATCH -e {job['log_stderr']}",
                "",
                "set -euo pipefail",
                "echo '===== VermAMG SLURM dry-run job ====='",
                f"echo 'job_id={job['job_id']}'",
                f"echo 'job_type={job['job_type']}'",
                f"echo 'depends_on={job['depends_on']}'",
                "echo 'compute_started=NO'",
                "echo 'This generated sbatch is a dry-run scaffold. Paket3 wires real execution.'",
                f"echo 'command_preview={job['command_preview'].replace(chr(39), chr(39) + chr(34) + chr(39) + chr(34) + chr(39))}'",
                "",
            ]),
            encoding="utf-8",
        )
        make_executable(script)
    submit_script.write_text(
        "\n".join([
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'SBATCH_DIR="${SCRIPT_DIR}/sbatch"',
            "",
            "echo '===== VermAMG SLURM backend dry-run ====='",
            f"echo 'active_backend={active_backend}'",
            "echo 'submit_started=NO'",
            "echo 'The commands below are previews only:'",
            "find \"${SBATCH_DIR}\" -maxdepth 1 -type f -name '*.sbatch' | sort | while read -r script; do",
            "  echo \"DRY_RUN sbatch ${script}\"",
            "done",
            "",
        ]),
        encoding="utf-8",
    )
    make_executable(submit_script)


def write_dry_run_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    manifest_rows = []
    for label, script, backend, status in rows:
        manifest_rows.append({
            "bundle": label,
            "backend": backend,
            "script_path": script,
            "status": status,
            "compute_started": "NO",
            "submit_started": "NO",
        })
    write_tsv(path, ["bundle", "backend", "script_path", "status", "compute_started", "submit_started"], manifest_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create V2 local/SLURM backend dry-run job plans from FASTA batches.")
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--backend", choices=("local", "slurm"), required=True)
    parser.add_argument("--profile", default="")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--submit-root", required=True)
    parser.add_argument("--out-plan", required=True)
    parser.add_argument("--out-dependencies", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--dry-run-manifest", required=True)
    parser.add_argument("--local-script", required=True)
    parser.add_argument("--slurm-script", required=True)
    parser.add_argument("--slurm-sbatch-dir", required=True)
    parser.add_argument("--dry-run", default="true")
    parser.add_argument("--submit-jobs", default="false")
    parser.add_argument("--emit-local-bundle", default="true")
    parser.add_argument("--emit-slurm-bundle", default="true")
    parser.add_argument("--plan-colabfold", default="true")
    parser.add_argument("--plan-foldseek", default="true")
    parser.add_argument("--local-threads", default="4")
    parser.add_argument("--colabfold-mode", default="precomputed")
    parser.add_argument("--colabfold-cmd", default="colabfold_batch")
    parser.add_argument("--colabfold-msa-mode", default="mmseqs2_uniref_env")
    parser.add_argument("--colabfold-model-type", default="alphafold2_ptm")
    parser.add_argument("--colabfold-num-recycle", default="3")
    parser.add_argument("--colabfold-num-models", default="1")
    parser.add_argument("--foldseek-mode", default="precomputed_all_hits")
    parser.add_argument("--foldseek-bin", default="")
    parser.add_argument("--pdb-foldseek-db", default="")
    parser.add_argument("--afsp-foldseek-db", default="")
    parser.add_argument("--slurm-account", default="")
    parser.add_argument("--partition-cpu", default="")
    parser.add_argument("--partition-gpu", default="")
    parser.add_argument("--cpus-cpu", default="8")
    parser.add_argument("--cpus-gpu", default="10")
    parser.add_argument("--mem-cpu", default="16G")
    parser.add_argument("--mem-gpu", default="32G")
    parser.add_argument("--time-cpu", default="12:00:00")
    parser.add_argument("--time-gpu", default="12:00:00")
    args = parser.parse_args(argv)

    errors: list[str] = []
    if bool_value(args.submit_jobs, False):
        errors.append("submit_jobs_true_not_supported_in_paket2")
    batch_path = Path(args.batch_manifest)
    if not batch_path.is_file():
        errors.append(f"batch_manifest_not_found:{batch_path}")
        batch_rows: list[dict[str, str]] = []
    else:
        _, batch_rows = read_tsv(batch_path)
    if not batch_rows:
        errors.append("batch_manifest_has_no_rows")

    local_jobs = build_jobs(batch_rows, args, "local", "none")
    slurm_jobs = build_jobs(batch_rows, args, "slurm", "slurm")
    active_jobs = local_jobs if args.backend == "local" else slurm_jobs
    active_deps = dependency_rows(active_jobs)

    out_plan = Path(args.out_plan)
    out_dependencies = Path(args.out_dependencies)
    out_summary = Path(args.out_summary)
    dry_run_manifest = Path(args.dry_run_manifest)
    local_script = Path(args.local_script)
    slurm_script = Path(args.slurm_script)
    slurm_dir = Path(args.slurm_sbatch_dir)

    write_tsv(out_plan, JOB_PLAN_FIELDS, active_jobs)
    write_tsv(out_dependencies, DEPENDENCY_FIELDS, active_deps)
    dry_run_rows: list[tuple[str, str, str, str]] = []
    if bool_value(args.emit_local_bundle, True):
        write_local_dry_run(local_script, out_plan, args.backend)
        dry_run_rows.append(("local", str(local_script), "local", script_status(local_script, args.backend, "local")))
    if bool_value(args.emit_slurm_bundle, True):
        write_slurm_bundle(submit_script=slurm_script, sbatch_dir=slurm_dir, jobs=slurm_jobs, active_backend=args.backend, args=args)
        dry_run_rows.append(("slurm", str(slurm_script), "slurm", script_status(slurm_script, args.backend, "slurm")))
    write_dry_run_manifest(dry_run_manifest, dry_run_rows)

    placeholder_slurm = not args.slurm_account or not args.partition_cpu or not args.partition_gpu
    status = "FAIL" if errors else "PASS"
    metrics: list[tuple[str, Any]] = [
        ("status", status),
        ("backend", args.backend),
        ("profile", args.profile),
        ("dry_run", "YES" if bool_value(args.dry_run, True) else "NO"),
        ("submit_jobs", "YES" if bool_value(args.submit_jobs, False) else "NO"),
        ("batch_count", len(batch_rows)),
        ("active_job_count", len(active_jobs)),
        ("active_dependency_rows", len(active_deps)),
        ("local_bundle_emitted", "YES" if bool_value(args.emit_local_bundle, True) else "NO"),
        ("slurm_bundle_emitted", "YES" if bool_value(args.emit_slurm_bundle, True) else "NO"),
        ("slurm_ready_to_submit", "NO" if placeholder_slurm else "YES_DRY_RUN_ONLY"),
        ("colabfold_mode", args.colabfold_mode),
        ("foldseek_mode", args.foldseek_mode),
        ("plan_colabfold", "YES" if bool_value(args.plan_colabfold, True) else "NO"),
        ("plan_foldseek", "YES" if bool_value(args.plan_foldseek, True) else "NO"),
        ("out_plan", out_plan),
        ("out_dependencies", out_dependencies),
        ("dry_run_manifest", dry_run_manifest),
        ("local_script", local_script),
        ("slurm_script", slurm_script),
        ("error_count", len(errors)),
    ]
    for error in errors:
        metrics.append(("error", error))
    write_summary(out_summary, metrics)
    for key, value in metrics:
        print(f"{key}\t{value}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
