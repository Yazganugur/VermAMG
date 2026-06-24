#!/usr/bin/env python3
"""VermAMG launcher for guarded run planning, execution, and status."""

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


def run_command(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print("COMMAND:", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT, env=env)
    return completed.returncode


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
