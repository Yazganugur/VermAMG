#!/usr/bin/env python3
"""VermAMG launcher for guarded run planning, execution, and legacy preparation."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import math


ROOT = Path(__file__).resolve().parents[1]

from vermamg_lib.config import load_run_config
from vermamg_lib.executor import (
    follow_latest_log,
    initialize_plan,
    print_plan,
    print_status,
    run_guarded_plan_only,
)
from vermamg_lib.run_context import RunContext
from vermamg_lib.stage_contracts import format_stage_info, validate_stage_inputs


def load_config(path: Path) -> dict:
    return load_run_config(path)


def cfg_value(cfg: dict, key: str, default: str = "") -> str:
    value = cfg.get(key, default)
    return "" if value is None else str(value)


def nested_value(cfg: dict, *keys: str, default: str = "") -> str:
    cur = cfg
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return "" if cur is None else str(cur)


def output_root(cfg: dict, key: str, run_label: str, fallback: str) -> str:
    outputs = cfg.get("outputs") or {}
    raw = str(outputs.get(key) or fallback)
    return raw.replace("{run_label}", run_label)


def resolve_config_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def count_fasta_records(path: Path) -> int | None:
    if not path.is_file():
        return None
    n = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith(">"):
                n += 1
    return n


def input_fasta_for_mode(cfg: dict, mode: str) -> str:
    if mode == "regression":
        regression_fasta = nested_value(cfg, "inputs", "regression_fasta")
        if regression_fasta:
            return regression_fasta
    return nested_value(cfg, "inputs", "candidate_fasta")


def run_command(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print("COMMAND:", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT, env=env)
    return completed.returncode


def command_plan(mode: str, profile: str) -> list[list[str]]:
    common = [
        ["bash", "scripts/modules/00_input_qc.sh", mode],
        ["bash", "scripts/modules/01_prepare_run_set.sh", mode],
        ["bash", "scripts/modules/02_prepare_colabfold_batches.sh", mode],
    ]
    if profile == "truba":
        return common + [["bash", "scripts/modules/03_prepare_colabfold_sbatch.sh", mode]]
    return common + [["bash", "scripts/modules/03_prepare_colabfold_local_runner.sh", mode]]


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def mode_target_batches(cfg: dict, mode: str) -> str:
    colabfold = cfg.get("colabfold") or {}
    target_batches = colabfold.get("target_batches")
    if target_batches not in (None, ""):
        return str(target_batches)
    by_mode = {
        "test": colabfold.get("test_target_batches"),
        "regression": colabfold.get("regression_target_batches"),
        "full": colabfold.get("full_target_batches"),
    }
    if by_mode.get(mode) not in (None, ""):
        return str(by_mode[mode])
    return {"test": "1", "regression": "4", "full": "8"}[mode]


def configure_truba_env(cfg: dict, env: dict[str, str]) -> None:
    execution = cfg.get("execution") or {}
    submit_jobs = bool_value(execution.get("submit_jobs", cfg.get("submit_jobs", False)))
    concurrency_fields = [
        ("execution.max_concurrent_jobs", nested_value(cfg, "execution", "max_concurrent_jobs")),
        ("execution.max_concurrent_gpu_jobs", nested_value(cfg, "execution", "max_concurrent_gpu_jobs")),
        ("execution.max_concurrent_cpu_jobs", nested_value(cfg, "execution", "max_concurrent_cpu_jobs")),
        ("execution.max_total_submitted_jobs", nested_value(cfg, "execution", "max_total_submitted_jobs")),
        ("execution.max_total_requested_cores", nested_value(cfg, "execution", "max_total_requested_cores")),
        ("foldseek.max_concurrent_jobs", nested_value(cfg, "foldseek", "max_concurrent_jobs")),
        ("p2rank.max_concurrent_jobs", nested_value(cfg, "p2rank", "max_concurrent_jobs")),
        ("visual.max_concurrent_jobs", nested_value(cfg, "visual", "max_concurrent_jobs")),
    ]
    missing_concurrency = [name for name, value in concurrency_fields if value == ""]
    if submit_jobs:
        if missing_concurrency:
            raise SystemExit(
                "CONFIG_ERROR: submit_jobs=true requires concurrency fields: "
                + ", ".join(missing_concurrency)
            )
        raise SystemExit("CONFIG_ERROR: submit_jobs=true requested, but submit not implemented in launcher v1")

    required = [
        ("slurm.account", nested_value(cfg, "slurm", "account")),
        ("slurm.partition_cpu", nested_value(cfg, "slurm", "partition_cpu")),
        ("slurm.partition_gpu", nested_value(cfg, "slurm", "partition_gpu")),
    ]
    missing = [name for name, value in required if not value]
    if missing:
        raise SystemExit("CONFIG_ERROR: missing required TRUBA SLURM fields: " + ", ".join(missing))

    slurm = cfg.get("slurm") or {}
    account = str(slurm.get("account"))
    partition_cpu = str(slurm.get("partition_cpu"))
    partition_gpu = str(slurm.get("partition_gpu"))
    partition_debug = str(slurm.get("partition_debug") or partition_cpu)
    cpus_cpu = str(slurm.get("cpus_cpu") or slurm.get("cpus_per_task") or 8)
    mem_cpu = str(slurm.get("mem_cpu") or "16G")
    time_cpu = str(slurm.get("time_cpu") or "12:00:00")
    cpus_gpu = str(slurm.get("cpus_gpu") or 10)
    mem_gpu = str(slurm.get("mem_gpu") or "32G")
    time_gpu = str(slurm.get("time_gpu") or "12:00:00")
    colabfold = cfg.get("colabfold") or {}
    colabfold_batch_size = str(colabfold.get("batch_size") or "")
    mode = cfg_value(cfg, "mode")
    colabfold_target_batches = mode_target_batches(cfg, mode)
    fasta_raw = input_fasta_for_mode(cfg, mode)
    fasta_records = count_fasta_records(resolve_config_path(fasta_raw)) if fasta_raw else None
    batch_size_estimate = "UNKNOWN"
    if fasta_records is not None:
        try:
            target_n = max(1, int(colabfold_target_batches))
            batch_size_estimate = str(math.ceil(fasta_records / target_n))
        except ValueError:
            batch_size_estimate = "UNKNOWN_TARGET_BATCHES_NOT_INTEGER"

    env.update({
        "SLURM_ACCOUNT": account,
        "SLURM_PARTITION_CPU": partition_cpu,
        "SLURM_PARTITION_GPU": partition_gpu,
        "SLURM_PARTITION_DEBUG": partition_debug,
        "SLURM_CPUS": cpus_cpu,
        "SLURM_CPUS_GPU": cpus_gpu,
        "SLURM_MEM": mem_cpu,
        "SLURM_MEM_GPU": mem_gpu,
        "SLURM_TIME_CPU": time_cpu,
        "SLURM_TIME_GPU": time_gpu,
        "COLABFOLD_GPU_ACCOUNT": account,
        "COLABFOLD_GPU_PARTITION": partition_gpu,
        "COLABFOLD_GPU_CPUS": cpus_gpu,
        "COLABFOLD_GPU_MEM": mem_gpu,
        "COLABFOLD_GPU_TIME": time_gpu,
        "FOLDSEEK_PDB_SLURM_ACCOUNT": account,
        "FOLDSEEK_PDB_SLURM_PARTITION": partition_cpu,
        "FOLDSEEK_PDB_SLURM_CPUS": cpus_cpu,
        "FOLDSEEK_PDB_SLURM_MEM": mem_cpu,
        "FOLDSEEK_PDB_SLURM_TIME": time_cpu,
        "FOLDSEEK_PDB_THREADS": cpus_cpu,
        "FOLDSEEK_AFSP_SLURM_ACCOUNT": account,
        "FOLDSEEK_AFSP_SLURM_PARTITION": partition_cpu,
        "FOLDSEEK_AFSP_SLURM_CPUS": cpus_cpu,
        "FOLDSEEK_AFSP_SLURM_MEM": mem_cpu,
        "FOLDSEEK_AFSP_SLURM_TIME": time_cpu,
        "FOLDSEEK_AFSP_THREADS": cpus_cpu,
        "P2RANK_SLURM_ACCOUNT": account,
        "P2RANK_SLURM_PARTITION": partition_cpu,
        "P2RANK_SLURM_CPUS": cpus_cpu,
        "P2RANK_SLURM_MEM": mem_cpu,
        "P2RANK_SLURM_TIME": time_cpu,
    })

    print(f"TRUBA_SLURM_ACCOUNT={account}")
    print(f"TRUBA_SLURM_PARTITION_CPU={partition_cpu}")
    print(f"TRUBA_SLURM_PARTITION_GPU={partition_gpu}")
    print(f"TRUBA_SLURM_PARTITION_DEBUG={partition_debug}")
    print(f"TRUBA_SLURM_CPU_RESOURCES=cpus:{cpus_cpu} mem:{mem_cpu} time:{time_cpu}")
    print(f"TRUBA_SLURM_GPU_RESOURCES=cpus:{cpus_gpu} mem:{mem_gpu} time:{time_gpu}")
    print(f"SUBMIT_JOBS={str(submit_jobs).upper()}")
    print(
        "CONCURRENCY_POLICY="
        + " ".join(f"{name.split('.')[-1]}:{value or 'MISSING'}" for name, value in concurrency_fields)
    )
    if missing_concurrency:
        print("CONCURRENCY_POLICY_STATUS=WARN_MISSING_FIELDS_FOR_FUTURE_SUBMIT")
    else:
        print("CONCURRENCY_POLICY_STATUS=CONFIGURED_FOR_FUTURE_SUBMIT_GUARD")
    print(f"COLABFOLD_TEMPLATE_BATCH_SIZE={colabfold_batch_size or 'UNSET'}")
    print(f"COLABFOLD_TARGET_BATCHES_FOR_MODE={colabfold_target_batches}")
    print(f"COLABFOLD_FASTA_FOR_MODE={fasta_raw or 'UNSET'}")
    print(f"COLABFOLD_FASTA_RECORDS={fasta_records if fasta_records is not None else 'UNKNOWN'}")
    print(f"COLABFOLD_ESTIMATED_BATCH_SIZE={batch_size_estimate}")
    print(f"PLANNED_GPU_JOBS_COLABFOLD={colabfold_target_batches}")
    print("PLANNED_CPU_JOBS=UNKNOWN_UNTIL_FOLDSEEK_P2RANK_MANIFESTS_EXIST")
    print("BATCH_LOGIC_NOTE=M02 currently uses target_batches, not colabfold.batch_size.")


def cmd_check(args: argparse.Namespace) -> int:
    config = Path(args.config)
    cfg = load_config(config)
    run_label = cfg_value(cfg, "run_label", "UNKNOWN")
    outdir = Path(output_root(cfg, "results", run_label, f"results/{run_label}")) / "preflight"

    print("STAGE=CHECK")
    print(f"STATUS=START run_label={run_label}")
    rc = run_command([
        sys.executable,
        "scripts/modules/00_preflight_check.py",
        "--config",
        str(config),
        "--outdir",
        str(outdir),
    ])
    print(f"STATUS={'PASS' if rc == 0 else 'FAIL'} exit_code={rc}")
    return rc


def cmd_prepare(args: argparse.Namespace) -> int:
    config = Path(args.config)
    cfg = load_config(config)
    mode = cfg_value(cfg, "mode")
    profile = cfg_value(cfg, "profile")
    run_label = cfg_value(cfg, "run_label", "UNKNOWN")
    allow_compute = bool(cfg.get("allow_compute", False))

    if mode not in {"test", "regression", "full"}:
        raise SystemExit(f"CONFIG_ERROR: unsupported mode for prepare: {mode!r}")
    if not profile:
        raise SystemExit("CONFIG_ERROR: profile is required for prepare")

    env = os.environ.copy()
    env["VERMAMG_PROFILE"] = profile

    print("STAGE=PREPARE")
    print(f"STATUS=START run_label={run_label} mode={mode} profile={profile}")
    print("COMPUTE_GUARD=ENABLED")
    print(f"ALLOW_COMPUTE={str(allow_compute).upper()}")
    print("NOTE=prepare only runs M00/M01/M02/M03; generated runners are not executed.")
    if profile == "truba":
        configure_truba_env(cfg, env)
        print("NOTE_TRUBA=M03 uses scripts/modules/03_prepare_colabfold_sbatch.sh and does not submit jobs.")

    plan = command_plan(mode, profile)
    if args.dry_run:
        for cmd in plan:
            print("PLAN:", f"VERMAMG_PROFILE={profile}", " ".join(cmd))
        print("STATUS=DRY_RUN_OK")
        return 0

    for idx, cmd in enumerate(plan, start=1):
        print(f"STAGE=PREPARE_STEP_{idx}")
        rc = run_command(cmd, env=env)
        if rc != 0:
            print(f"STATUS=FAIL step={idx} exit_code={rc}")
            return rc

    print("STATUS=PASS")
    print("COMPUTE_STARTED=NO")
    return 0


def _run_context_from_args(args: argparse.Namespace) -> RunContext:
    config = Path(args.config)
    cfg = load_run_config(config)
    return RunContext.from_config(config, cfg)


def cmd_plan(args: argparse.Namespace) -> int:
    ctx = _run_context_from_args(args)
    rows, errors, plan_path = initialize_plan(ctx, start_at=args.start_at, stop_after=args.stop_after)
    return print_plan(ctx, rows, errors, plan_path, start_at=args.start_at, stop_after=args.stop_after)


def cmd_status(args: argparse.Namespace) -> int:
    ctx = _run_context_from_args(args)
    return print_status(ctx)


def cmd_follow(args: argparse.Namespace) -> int:
    ctx = _run_context_from_args(args)
    return follow_latest_log(ctx, lines=args.lines)


def cmd_run(args: argparse.Namespace) -> int:
    ctx = _run_context_from_args(args)
    return run_guarded_plan_only(
        ctx,
        resume=args.resume,
        follow=args.follow,
        start_at=args.start_at,
        stop_after=args.stop_after,
    )


def cmd_stage_info(args: argparse.Namespace) -> int:
    text = format_stage_info(args.stage)
    print(text)
    return 0 if "UNKNOWN_STAGE_CONTRACT" not in text else 2


def cmd_validate_stage(args: argparse.Namespace) -> int:
    ctx = _run_context_from_args(args)
    validation = validate_stage_inputs(ctx, args.stage)
    print("VERMAMG_STAGE_VALIDATE_V1")
    print(f"run_label\t{ctx.run_label}")
    print(f"run_root\t{ctx.rel_to_project(ctx.run_root)}")
    print(f"stage_id\t{args.stage}")
    print(f"validation_status\t{'PASS' if not validation.errors else 'FAIL'}")
    print(f"error_count\t{len(validation.errors)}")
    print("inputs")
    print("path\tresolved_path\tstatus\tdetail")
    for check in validation.checks:
        print("\t".join([check.path, check.resolved_path, check.status, check.detail]))
    return 0 if not validation.errors else 8


def main() -> int:
    parser = argparse.ArgumentParser(description="VermAMG guarded pipeline launcher")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Run preflight check for a YAML config.")
    check.add_argument("config")
    check.set_defaults(func=cmd_check)

    prepare = sub.add_parser("prepare", help="Run safe preparation stages only.")
    prepare.add_argument("config")
    prepare.add_argument("--dry-run", action="store_true")
    prepare.set_defaults(func=cmd_prepare)

    plan = sub.add_parser("plan", help="Create/review a run-config execution plan.")
    plan.add_argument("--config", required=True)
    plan.add_argument("--start-at", default=None)
    plan.add_argument("--stop-after", default=None)
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="Run a YAML-configured VermAMG pipeline.")
    run.add_argument("--config", required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--follow", action="store_true")
    run.add_argument("--start-at", default=None)
    run.add_argument("--stop-after", default=None)
    run.set_defaults(func=cmd_run)

    stage_info = sub.add_parser("stage-info", help="Show the input/output contract for one stage.")
    stage_info.add_argument("--stage", required=True)
    stage_info.set_defaults(func=cmd_stage_info)

    validate_stage = sub.add_parser("validate-stage", help="Validate required inputs for one stage without running it.")
    validate_stage.add_argument("--config", required=True)
    validate_stage.add_argument("--stage", required=True)
    validate_stage.set_defaults(func=cmd_validate_stage)

    status = sub.add_parser("status", help="Show run status from state/status.json.")
    status.add_argument("--config", required=True)
    status.set_defaults(func=cmd_status)

    follow = sub.add_parser("follow", help="Show the latest run log tail.")
    follow.add_argument("--config", required=True)
    follow.add_argument("--lines", type=int, default=40)
    follow.set_defaults(func=cmd_follow)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
