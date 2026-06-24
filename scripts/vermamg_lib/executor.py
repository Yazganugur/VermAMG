from __future__ import annotations

import csv
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, TextIO

from .config import bool_value, get_nested
from .run_context import RunContext
from .stage_contracts import StageValidation, validate_stage_window_inputs
from .stage_registry import Stage, build_stages, stage_plan_rows, stage_window_errors
from .state import read_checkpoint, read_status, write_checkpoint, write_status
from .validators import validate_config_for_plan


PLAN_FIELDS = [
    "order",
    "stage_id",
    "enabled",
    "heavy",
    "checkpoint_status",
    "expected_outputs_present",
    "resume_action",
    "title",
    "notes",
]

LOCAL_WSL_POSIX_ONLY_STAGE_IDS = {
    "110_p2rank_query",
    "120_p2rank_reference",
    "200_m10f_render",
}


def write_plan_tsv(ctx: RunContext, rows: list[dict[str, str]]) -> Path:
    path = ctx.run_path("state/run_plan.tsv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _latest_pass_stage_from_rows(rows: list[dict[str, str]]) -> str:
    latest = "000_initialize_run"
    for row in rows:
        if row.get("checkpoint_status") == "PASS":
            latest = row.get("stage_id", latest)
    return latest


def initialize_plan(
    ctx: RunContext,
    *,
    start_at: str | None = None,
    stop_after: str | None = None,
) -> tuple[list[dict[str, str]], list[str], Path]:
    ctx.ensure_layout()
    errors = validate_config_for_plan(ctx)
    errors.extend(stage_window_errors(ctx, start_at=start_at, stop_after=stop_after))
    status = "PLAN_READY" if not errors else "PLAN_BLOCKED"
    write_status(ctx.run_root, {
        "schema_version": ctx.schema_version,
        "project_name": ctx.project_name,
        "project_slug": ctx.project_slug,
        "sample_name": ctx.sample_name,
        "sample_slug": ctx.sample_slug,
        "run_label": ctx.run_label,
        "mode": ctx.mode,
        "profile": ctx.profile,
        "layout_version": ctx.layout_version,
        "status": status,
        "current_stage": "000_initialize_run",
        "last_pass_stage": "",
        "next_stage": "",
        "latest_log": "",
        "plan_path": "",
        "config_path": ctx.rel_to_project(ctx.config_path),
        "start_at": start_at or "",
        "stop_after": stop_after or "",
        "validation_errors": errors,
    })
    write_checkpoint(ctx.run_root, "000_initialize_run", {
        "status": "PASS" if not errors else "FAIL",
        "run_root": ctx.rel_to_project(ctx.run_root),
        "validation_errors": errors,
    })

    rows = stage_plan_rows(ctx, start_at=start_at, stop_after=stop_after)
    plan_path = write_plan_tsv(ctx, rows)
    latest_pass_stage = _latest_pass_stage_from_rows(rows) if not errors else ""
    next_row = next((row for row in rows if row["enabled"] == "YES" and row["resume_action"] == "RUN_PENDING"), None)
    next_expected = ""
    if next_row:
        next_expected = next_row["stage_id"]
    write_status(ctx.run_root, {
        "schema_version": ctx.schema_version,
        "project_name": ctx.project_name,
        "project_slug": ctx.project_slug,
        "sample_name": ctx.sample_name,
        "sample_slug": ctx.sample_slug,
        "run_label": ctx.run_label,
        "mode": ctx.mode,
        "profile": ctx.profile,
        "layout_version": ctx.layout_version,
        "status": status,
        "current_stage": "",
        "last_pass_stage": latest_pass_stage,
        "next_stage": next_expected,
        "latest_log": "",
        "plan_path": ctx.rel_to_project(plan_path),
        "config_path": ctx.rel_to_project(ctx.config_path),
        "start_at": start_at or "",
        "stop_after": stop_after or "",
        "validation_errors": errors,
    })
    write_checkpoint(ctx.run_root, "000_initialize_run", {
        "status": "PASS" if not errors else "FAIL",
        "run_root": ctx.rel_to_project(ctx.run_root),
        "plan_path": ctx.rel_to_project(plan_path),
        "validation_errors": errors,
    })
    return rows, errors, plan_path


def print_plan(
    ctx: RunContext,
    rows: list[dict[str, str]],
    errors: list[str],
    plan_path: Path,
    *,
    start_at: str | None = None,
    stop_after: str | None = None,
) -> int:
    print("VERMAMG_ORCHESTRATOR_PLAN_V1")
    print(f"schema_version\t{ctx.schema_version}")
    print(f"project_name\t{ctx.project_name}")
    print(f"project_slug\t{ctx.project_slug}")
    print(f"sample_name\t{ctx.sample_name}")
    print(f"sample_slug\t{ctx.sample_slug}")
    print(f"run_label\t{ctx.run_label}")
    print(f"mode\t{ctx.mode}")
    print(f"profile\t{ctx.profile}")
    print(f"layout_version\t{ctx.layout_version}")
    print(f"run_root\t{ctx.rel_to_project(ctx.run_root)}")
    print(f"work_root\t{ctx.rel_to_project(ctx.run_path('work'))}")
    print(f"results_root\t{ctx.rel_to_project(ctx.run_path('results'))}")
    print(f"exports_root\t{ctx.rel_to_project(ctx.run_path('exports'))}")
    print(f"plan_path\t{ctx.rel_to_project(plan_path)}")
    print(f"start_at\t{start_at or ''}")
    print(f"stop_after\t{stop_after or ''}")
    print(f"validation_status\t{'PASS' if not errors else 'FAIL'}")
    for err in errors:
        print(f"VALIDATION_ERROR\t{err}")
    print("stages")
    print("\t".join(PLAN_FIELDS))
    for row in rows:
        print("\t".join(row.get(field, "") for field in PLAN_FIELDS))
    return 0 if not errors else 2


def print_status(ctx: RunContext) -> int:
    status = read_status(ctx.run_root)
    if status is None:
        print("VERMAMG_ORCHESTRATOR_STATUS_V1")
        print(f"run_label\t{ctx.run_label}")
        print(f"run_root\t{ctx.rel_to_project(ctx.run_root)}")
        print("status\tNOT_INITIALIZED")
        print("hint\tRun plan first: python3 scripts/vermamg.py plan --config <config>")
        return 1
    print("VERMAMG_ORCHESTRATOR_STATUS_V1")
    for key in [
        "schema_version",
        "project_name",
        "project_slug",
        "sample_name",
        "sample_slug",
        "run_label",
        "mode",
        "profile",
        "layout_version",
        "status",
        "current_stage",
        "last_pass_stage",
        "next_stage",
        "latest_log",
        "plan_path",
        "start_at",
        "stop_after",
        "updated_at",
    ]:
        print(f"{key}\t{status.get(key, '')}")
    errors = status.get("validation_errors") or []
    print(f"validation_error_count\t{len(errors)}")
    for err in errors:
        print(f"VALIDATION_ERROR\t{err}")
    return 0 if status.get("status") != "PLAN_BLOCKED" else 2


def follow_latest_log(ctx: RunContext, lines: int = 40) -> int:
    status = read_status(ctx.run_root)
    print("VERMAMG_ORCHESTRATOR_FOLLOW_V1")
    if not status:
        print("status\tNOT_INITIALIZED")
        return 1
    latest = status.get("latest_log") or ""
    print(f"status\t{status.get('status', '')}")
    print(f"current_stage\t{status.get('current_stage', '')}")
    print(f"latest_log\t{latest}")
    if not latest:
        print("log_tail\tNO_LOG_YET")
        return 0
    log_path = Path(str(latest))
    if not log_path.is_absolute():
        log_path = ctx.project_root / log_path
    if not log_path.is_file():
        print("log_tail\tLOG_FILE_NOT_FOUND")
        return 1
    data = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in data[-lines:]:
        print(line)
    return 0


def _rel(ctx: RunContext, path: Path) -> str:
    return ctx.rel_to_project(path)


def _stage_log_path(ctx: RunContext, stage_id: str) -> Path:
    return ctx.run_path("logs") / f"{stage_id}.log"


def _stage_outputs(ctx: RunContext, stage: Stage) -> list[Path]:
    return [ctx.run_path(rel) for rel in stage.expected_outputs]


def _all_outputs_exist(paths: list[Path]) -> bool:
    return all(path.exists() for path in paths)


def _any_outputs_exist(paths: list[Path]) -> bool:
    return any(path.exists() for path in paths)


def _write_status_update(
    ctx: RunContext,
    *,
    status: str,
    current_stage: str = "",
    last_pass_stage: str = "",
    next_stage: str = "",
    latest_log: Path | None = None,
    errors: list[str] | None = None,
) -> None:
    old = read_status(ctx.run_root) or {}
    write_status(ctx.run_root, {
        "schema_version": ctx.schema_version,
        "project_name": ctx.project_name,
        "project_slug": ctx.project_slug,
        "sample_name": ctx.sample_name,
        "sample_slug": ctx.sample_slug,
        "run_label": ctx.run_label,
        "mode": ctx.mode,
        "profile": ctx.profile,
        "layout_version": ctx.layout_version,
        "status": status,
        "current_stage": current_stage,
        "last_pass_stage": last_pass_stage or old.get("last_pass_stage", ""),
        "next_stage": next_stage,
        "latest_log": _rel(ctx, latest_log) if latest_log else old.get("latest_log", ""),
        "plan_path": old.get("plan_path", ""),
        "config_path": _rel(ctx, ctx.config_path),
        "validation_errors": errors if errors is not None else old.get("validation_errors", []),
    })


def _next_enabled_stage_id(stages: list[Stage], index: int, stop_after: str | None, ctx: RunContext) -> str:
    stage_ids = [stage.stage_id for stage in stages]
    stop_idx = stage_ids.index(stop_after) if stop_after in stage_ids else len(stages) - 1
    for next_index, stage in enumerate(stages[index + 1:], start=index + 1):
        if next_index > stop_idx:
            return ""
        if stage.enabled(ctx):
            return stage.stage_id
    return ""


def _runtime_environment_errors(
    ctx: RunContext,
    stages: list[Stage],
    rows: list[dict[str, str]],
    *,
    start_at: str | None = None,
    stop_after: str | None = None,
) -> list[str]:
    if os.name != "nt" or ctx.profile != "local_wsl":
        return []
    resume_action_by_stage = {row.get("stage_id", ""): row.get("resume_action", "") for row in rows}
    stage_ids = [stage.stage_id for stage in stages]
    start_idx = stage_ids.index(start_at) if start_at in stage_ids else 0
    stop_idx = stage_ids.index(stop_after) if stop_after in stage_ids else len(stages) - 1

    def requires_wsl_posix(stage_id: str) -> bool:
        if stage_id == "080_m09c_materialize_references":
            return _reference_materialization_method(ctx) in {"foldseek_export", "foldseek", "legacy_foldseek_export"}
        return stage_id in LOCAL_WSL_POSIX_ONLY_STAGE_IDS

    selected = [
        stage.stage_id
        for index, stage in enumerate(stages)
        if start_idx <= index <= stop_idx
        and stage.enabled(ctx)
        and requires_wsl_posix(stage.stage_id)
        and resume_action_by_stage.get(stage.stage_id) == "RUN_PENDING"
    ]
    if not selected:
        return []
    return [
        "profile=local_wsl requires WSL/Linux Python for stages "
        + ",".join(selected)
        + ". Run from WSL, for example: cd /path/to/VermAMG && "
        + "python3 scripts/vermamg.py run --config run_configs/<run>.yaml --resume"
    ]


def _log(log: TextIO, follow: bool, message: str = "") -> None:
    log.write(message + "\n")
    log.flush()
    if follow:
        print(message, flush=True)


def _run_command(ctx: RunContext, cmd: list[str], log: TextIO, follow: bool) -> int:
    _log(log, follow, "COMMAND\t" + subprocess.list2cmdline([str(x) for x in cmd]))
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.Popen(
        [str(x) for x in cmd],
        cwd=ctx.project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log.write(line)
        log.flush()
        if follow:
            print(line, end="", flush=True)
    return proc.wait()


def _resolve_input(ctx: RunContext, *keys: str) -> Path:
    raw = get_nested(ctx.cfg, *keys)
    if raw in (None, ""):
        raise SystemExit("CONFIG_ERROR: missing required path: " + ".".join(keys))
    return ctx.project_path(str(raw))


def _resolve_optional_input(ctx: RunContext, *keys: str) -> Path | None:
    raw = get_nested(ctx.cfg, *keys)
    if raw in (None, ""):
        return None
    return ctx.project_path(str(raw))


def _copy_mode(ctx: RunContext) -> str:
    mode = str(get_nested(ctx.cfg, "run", "import_policy", default="copy"))
    return mode if mode in {"copy", "symlink", "reference"} else "copy"


def _cfg_bool_text(ctx: RunContext, *keys: str, default: bool = False) -> str:
    return "true" if bool_value(get_nested(ctx.cfg, *keys, default=default), default=default) else "false"


def _cfg_int_text(ctx: RunContext, *keys: str, default: int = 0) -> str:
    raw = get_nested(ctx.cfg, *keys, default=default)
    if raw in (None, ""):
        return str(default)
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return str(default)


def _cfg_text(ctx: RunContext, *keys: str, default: str = "") -> str:
    raw = get_nested(ctx.cfg, *keys, default=default)
    return str(default if raw in (None, "") else raw)


def _batch_prefix(ctx: RunContext) -> str:
    raw = str(get_nested(ctx.cfg, "batching", "batch_prefix", default="") or "").strip()
    if not raw:
        raw = ctx.sample_slug or ctx.project_slug or "batch"
    return (
        raw.replace("{project_slug}", ctx.project_slug)
        .replace("{sample_slug}", ctx.sample_slug)
        .replace("{run_label}", ctx.run_label)
    )


def _run_preflight(ctx: RunContext, log: TextIO, follow: bool) -> dict[str, Any]:
    errors = validate_config_for_plan(ctx)
    if errors:
        for err in errors:
            _log(log, follow, "VALIDATION_ERROR\t" + err)
        return {"status": "FAIL", "validation_errors": errors}

    metrics: list[tuple[str, Any]] = [
        ("status", "PASS"),
        ("run_label", ctx.run_label),
        ("mode", ctx.mode),
        ("profile", ctx.profile),
        ("run_root", _rel(ctx, ctx.run_root)),
    ]
    required_path_specs = [
        ("inputs_fasta", ("inputs", "fasta")),
        ("query_pdb_dir", ("colabfold", "query_pdb_dir")),
        ("collector_manifest", ("colabfold", "collector_manifest")),
        ("pdb_all_hits", ("foldseek", "pdb_all_hits")),
        ("afsp_all_hits", ("foldseek", "afsp_all_hits")),
        ("id_map", ("foldseek", "id_map")),
    ]
    for label, keys in required_path_specs:
        path = _resolve_input(ctx, *keys)
        metrics.append((f"{label}_exists", "YES" if path.exists() else "NO"))
        metrics.append((f"{label}_path", path))
    metadata_path = _resolve_optional_input(ctx, "inputs", "metadata_tsv")
    metrics.append(("metadata_tsv_provided", "YES" if metadata_path else "NO"))
    if metadata_path:
        metrics.append(("metadata_tsv_exists", "YES" if metadata_path.exists() else "NO"))
        metrics.append(("metadata_tsv_path", metadata_path))
    query_dir = _resolve_input(ctx, "colabfold", "query_pdb_dir")
    if query_dir.is_dir():
        metrics.append(("query_pdb_count", len(list(query_dir.glob("*.pdb")))))

    out = ctx.run_path("results/full/preflight/preflight_summary.tsv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key, value in metrics:
            writer.writerow([key, str(value)])
    for key, value in metrics:
        _log(log, follow, f"{key}\t{value}")
    return {"status": "PASS", "summary": _rel(ctx, out)}


def _run_fasta_intake(ctx: RunContext, log: TextIO, follow: bool) -> int:
    cmd: list[Any] = [
        sys.executable,
        ctx.project_path("scripts/modules/00a_fasta_intake.py"),
        "--fasta", _resolve_input(ctx, "inputs", "fasta"),
        "--metadata-id-column", str(get_nested(ctx.cfg, "metadata", "id_column", default="") or ""),
        "--metadata-required", _cfg_bool_text(ctx, "metadata", "required", default=False),
        "--metadata-strict-extra-rows", _cfg_bool_text(ctx, "metadata", "strict_extra_rows", default=False),
        "--id-policy", str(get_nested(ctx.cfg, "input_intake", "id_policy", default="preserve_first_token") or "preserve_first_token"),
        "--duplicate-policy", str(get_nested(ctx.cfg, "input_intake", "duplicate_policy", default="fail") or "fail"),
        "--min-length", _cfg_int_text(ctx, "input_intake", "min_sequence_length", default=1),
        "--invalid-sequence-policy", str(get_nested(ctx.cfg, "input_intake", "invalid_sequence_policy", default="fail") or "fail"),
        "--project-name", ctx.project_name,
        "--project-slug", ctx.project_slug,
        "--sample-name", ctx.sample_name,
        "--sample-slug", ctx.sample_slug,
        "--run-label", ctx.run_label,
        "--canonical-fasta", ctx.run_path("00_inputs/fasta/canonical_sequences.faa"),
        "--sample-manifest", ctx.run_path("00_inputs/manifests/sample_manifest.tsv"),
        "--metadata-joined", ctx.run_path("00_inputs/metadata/sample_metadata_joined.tsv"),
        "--qc-summary", ctx.run_path("00_inputs/qc/input_intake_summary.tsv"),
        "--metadata-qc", ctx.run_path("00_inputs/qc/metadata_qc.tsv"),
    ]
    metadata_path = _resolve_optional_input(ctx, "inputs", "metadata_tsv")
    if metadata_path:
        cmd.extend(["--metadata", metadata_path])
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_fasta_batch_plan(ctx: RunContext, log: TextIO, follow: bool) -> int:
    cmd: list[Any] = [
        sys.executable,
        ctx.project_path("scripts/modules/00b_plan_fasta_batches.py"),
        "--canonical-fasta", ctx.run_path("00_inputs/fasta/canonical_sequences.faa"),
        "--sample-manifest", ctx.run_path("00_inputs/manifests/sample_manifest.tsv"),
        "--batch-dir", ctx.run_path("00_inputs/batches/fasta"),
        "--batch-manifest", ctx.run_path("00_inputs/batches/batch_manifest.tsv"),
        "--batch-membership", ctx.run_path("00_inputs/batches/batch_membership.tsv"),
        "--sample-manifest-with-batches", ctx.run_path("00_inputs/manifests/sample_manifest_with_batches.tsv"),
        "--qc-summary", ctx.run_path("00_inputs/qc/batch_plan_summary.tsv"),
        "--batching-enabled", _cfg_bool_text(ctx, "batching", "enabled", default=True),
        "--strategy", str(get_nested(ctx.cfg, "batching", "strategy", default="fixed_size") or "fixed_size"),
        "--batch-size", _cfg_int_text(ctx, "batching", "batch_size", default=128),
        "--target-batches", _cfg_int_text(ctx, "batching", "target_batches", default=0),
        "--max-sequences", _cfg_int_text(ctx, "batching", "max_sequences", default=0),
        "--batch-prefix", _batch_prefix(ctx),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_backend_job_plan(ctx: RunContext, log: TextIO, follow: bool) -> int:
    backend = _cfg_text(ctx, "environment", "backend", default="local").strip().lower()
    if backend not in {"local", "slurm"}:
        backend = "local"
    submit_root = ctx.run_path("submit")
    slurm = get_nested(ctx.cfg, "slurm", default={}) or {}
    local_threads_default = int(get_nested(ctx.cfg, "p2rank", "threads", default=4) or 4)
    cmd: list[Any] = [
        sys.executable,
        ctx.project_path("scripts/modules/00c_plan_backend_jobs.py"),
        "--batch-manifest", ctx.run_path("00_inputs/batches/batch_manifest.tsv"),
        "--backend", backend,
        "--profile", ctx.profile,
        "--mode", ctx.mode,
        "--run-root", ctx.run_root,
        "--submit-root", submit_root,
        "--out-plan", ctx.run_path("00_inputs/job_plan/backend_job_plan.tsv"),
        "--out-dependencies", ctx.run_path("00_inputs/job_plan/backend_job_dependencies.tsv"),
        "--out-summary", ctx.run_path("00_inputs/job_plan/backend_plan_summary.tsv"),
        "--dry-run-manifest", ctx.run_path("00_inputs/job_plan/backend_dry_run_manifest.tsv"),
        "--local-script", ctx.run_path("submit/local/run_backend_dry_run.sh"),
        "--slurm-script", ctx.run_path("submit/slurm/submit_backend_dry_run.sh"),
        "--slurm-sbatch-dir", ctx.run_path("submit/slurm/sbatch"),
        "--dry-run", _cfg_bool_text(ctx, "backend_jobs", "dry_run", default=True),
        "--submit-jobs", _cfg_bool_text(ctx, "backend_jobs", "submit_jobs", default=False),
        "--emit-local-bundle", _cfg_bool_text(ctx, "backend_jobs", "emit_local_bundle", default=True),
        "--emit-slurm-bundle", _cfg_bool_text(ctx, "backend_jobs", "emit_slurm_bundle", default=True),
        "--plan-colabfold", _cfg_bool_text(ctx, "backend_jobs", "plan_colabfold", default=True),
        "--plan-foldseek", _cfg_bool_text(ctx, "backend_jobs", "plan_foldseek", default=True),
        "--local-threads", _cfg_int_text(ctx, "backend_jobs", "local_threads", default=local_threads_default),
        "--colabfold-mode", _cfg_text(ctx, "colabfold", "mode", default="precomputed"),
        "--colabfold-cmd", _cfg_text(ctx, "colabfold", "cmd", default="colabfold_batch"),
        "--colabfold-msa-mode", _cfg_text(ctx, "colabfold", "msa_mode", default="mmseqs2_uniref_env"),
        "--colabfold-model-type", _cfg_text(ctx, "colabfold", "model_type", default="alphafold2_ptm"),
        "--colabfold-num-recycle", _cfg_text(ctx, "colabfold", "num_recycle", default="3"),
        "--colabfold-num-models", _cfg_text(ctx, "colabfold", "num_models", default="1"),
        "--foldseek-mode", _cfg_text(ctx, "foldseek", "mode", default="precomputed_all_hits"),
        "--foldseek-bin", _cfg_text(ctx, "resources", "foldseek_bin", default=""),
        "--pdb-foldseek-db", _cfg_text(ctx, "resources", "pdb_foldseek_db", default=""),
        "--afsp-foldseek-db", _cfg_text(ctx, "resources", "afsp_foldseek_db", default=""),
        "--slurm-account", str(slurm.get("account") or ""),
        "--partition-cpu", str(slurm.get("partition_cpu") or ""),
        "--partition-gpu", str(slurm.get("partition_gpu") or ""),
        "--cpus-cpu", str(slurm.get("cpus_cpu") or slurm.get("cpus_per_task") or 8),
        "--cpus-gpu", str(slurm.get("cpus_gpu") or 10),
        "--mem-cpu", str(slurm.get("mem_cpu") or "16G"),
        "--mem-gpu", str(slurm.get("mem_gpu") or "32G"),
        "--time-cpu", str(slurm.get("time_cpu") or "12:00:00"),
        "--time-gpu", str(slurm.get("time_gpu") or "12:00:00"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _colabfold_mode(ctx: RunContext) -> str:
    return str(get_nested(ctx.cfg, "colabfold", "mode", default="precomputed") or "precomputed").strip().lower()


def _foldseek_mode(ctx: RunContext) -> str:
    return str(get_nested(ctx.cfg, "foldseek", "mode", default="precomputed_all_hits") or "precomputed_all_hits").strip().lower()


def _run_live_colabfold(ctx: RunContext, log: TextIO, follow: bool) -> int:
    backend = _cfg_text(ctx, "environment", "backend", default="local").strip().lower()
    if backend not in {"local", "slurm"}:
        backend = "local"
    slurm = get_nested(ctx.cfg, "slurm", default={}) or {}
    cmd: list[Any] = [
        sys.executable,
        ctx.project_path("scripts/modules/00d_run_colabfold.py"),
        "--batch-manifest", ctx.run_path("00_inputs/batches/batch_manifest.tsv"),
        "--sample-manifest", ctx.run_path("00_inputs/manifests/sample_manifest.tsv"),
        "--metadata-joined", ctx.run_path("00_inputs/metadata/sample_metadata_joined.tsv"),
        "--backend", backend,
        "--mode", ctx.mode,
        "--project-root", ctx.project_root,
        "--run-root", ctx.run_root,
        "--submit-root", ctx.run_path("submit"),
        "--live-output-root", ctx.run_path("01_colabfold/live_outputs"),
        "--out-pdb-dir", ctx.run_path("01_colabfold/query_pdbs"),
        "--out-manifest", ctx.run_path("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv"),
        "--out-summary", ctx.run_path("02_foldseek/qc/full_query_pdb_manifest_summary.tsv"),
        "--out-collector", ctx.run_path("01_colabfold/collector_manifest.tsv"),
        "--out-id-map", ctx.run_path("01_colabfold/live_colabfold_id_map.tsv"),
        "--out-run-plan", ctx.run_path("01_colabfold/live_plan/colabfold_run_plan.tsv"),
        "--slurm-sbatch-dir", ctx.run_path("submit/slurm/sbatch"),
        "--dry-run", _cfg_bool_text(ctx, "colabfold", "dry_run", default=False),
        "--colabfold-cmd", _cfg_text(ctx, "colabfold", "cmd", default="colabfold_batch"),
        "--colabfold-msa-mode", _cfg_text(ctx, "colabfold", "msa_mode", default="mmseqs2_uniref_env"),
        "--colabfold-model-type", _cfg_text(ctx, "colabfold", "model_type", default="alphafold2_ptm"),
        "--colabfold-num-recycle", _cfg_text(ctx, "colabfold", "num_recycle", default="3"),
        "--colabfold-num-models", _cfg_text(ctx, "colabfold", "num_models", default="1"),
        "--slurm-account", str(slurm.get("account") or ""),
        "--partition-gpu", str(slurm.get("partition_gpu") or ""),
        "--cpus-gpu", str(slurm.get("cpus_gpu") or 10),
        "--mem-gpu", str(slurm.get("mem_gpu") or "32G"),
        "--time-gpu", str(slurm.get("time_gpu") or "12:00:00"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_live_foldseek(ctx: RunContext, log: TextIO, follow: bool) -> int:
    backend = _cfg_text(ctx, "environment", "backend", default="local").strip().lower()
    if backend not in {"local", "slurm"}:
        backend = "local"
    threads = _cfg_int_text(ctx, "foldseek", "threads", default=int(get_nested(ctx.cfg, "p2rank", "threads", default=4) or 4))
    cmd: list[Any] = [
        sys.executable,
        ctx.project_path("scripts/modules/00e_run_foldseek.py"),
        "--query-manifest", ctx.run_path("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv"),
        "--metadata-joined", ctx.run_path("00_inputs/metadata/sample_metadata_joined.tsv"),
        "--backend", backend,
        "--project-root", ctx.project_root,
        "--run-root", ctx.run_root,
        "--work-dir", ctx.run_path("02_foldseek/live_search"),
        "--out-pdb-all-hits", ctx.run_path("02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv"),
        "--out-afsp-all-hits", ctx.run_path("02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv"),
        "--out-id-map", ctx.run_path("02_foldseek/tables/full/full_manual_id_map.tsv"),
        "--out-summary", ctx.run_path("02_foldseek/qc/full/full_precomputed_foldseek_import_qc.tsv"),
        "--out-run-plan", ctx.run_path("02_foldseek/live_plan/foldseek_run_plan.tsv"),
        "--foldseek-bin", _cfg_text(ctx, "resources", "foldseek_bin", default=""),
        "--pdb-foldseek-db", _cfg_text(ctx, "resources", "pdb_foldseek_db", default=""),
        "--afsp-foldseek-db", _cfg_text(ctx, "resources", "afsp_foldseek_db", default=""),
        "--threads", threads,
        "--dry-run", _cfg_bool_text(ctx, "foldseek", "dry_run", default=False),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_import_colabfold(ctx: RunContext, log: TextIO, follow: bool) -> int:
    if _colabfold_mode(ctx) == "live":
        return _run_live_colabfold(ctx, log, follow)
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/import_precomputed_colabfold.py"),
        "--mode", "full",
        "--query-pdb-dir", _resolve_input(ctx, "colabfold", "query_pdb_dir"),
        "--collector-manifest", _resolve_input(ctx, "colabfold", "collector_manifest"),
        "--id-map", _resolve_input(ctx, "foldseek", "id_map"),
        "--out-pdb-dir", ctx.run_path("01_colabfold/query_pdbs"),
        "--out-manifest", ctx.run_path("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv"),
        "--out-summary", ctx.run_path("02_foldseek/qc/full_query_pdb_manifest_summary.tsv"),
        "--allowed-root", ctx.run_root,
        "--copy-mode", _copy_mode(ctx),
        "--write",
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_import_foldseek(ctx: RunContext, log: TextIO, follow: bool) -> int:
    if _foldseek_mode(ctx) == "live":
        return _run_live_foldseek(ctx, log, follow)
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/import_precomputed_foldseek_hits.py"),
        "--pdb-all-hits", _resolve_input(ctx, "foldseek", "pdb_all_hits"),
        "--afsp-all-hits", _resolve_input(ctx, "foldseek", "afsp_all_hits"),
        "--id-map", _resolve_input(ctx, "foldseek", "id_map"),
        "--out-pdb-all-hits", ctx.run_path("02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv"),
        "--out-afsp-all-hits", ctx.run_path("02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv"),
        "--out-id-map", ctx.run_path("02_foldseek/tables/full/full_manual_id_map.tsv"),
        "--qc-report", ctx.run_path("02_foldseek/qc/full/full_precomputed_foldseek_import_qc.tsv"),
        "--allowed-root", ctx.run_root,
        "--write",
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _m06b_paths(ctx: RunContext) -> list[Path]:
    table = ctx.run_path("02_foldseek/tables/full")
    qc = ctx.run_path("02_foldseek/qc/full")
    return [
        table / "full_vs_pdb_foldseek_all_hits.tsv",
        table / "full_manual_id_map.tsv",
        table / "full_vs_pdb_foldseek_best_hit_rank1.tsv",
        table / "full_vs_pdb_foldseek_best_hit_rank1_classified.tsv",
        table / "full_vs_pdb_foldseek_top5_hits.tsv",
        table / "full_vs_pdb_foldseek_qtmmax_audit.tsv",
        table / "full_vs_pdb_foldseek_rank1_vs_qtmmax_audit.tsv",
        table / "full_vs_pdb_foldseek_neartie_top5_audit.tsv",
        qc / "full_vs_pdb_foldseek_canonical_summary.tsv",
        qc / "full_vs_pdb_foldseek_canonical_pointer.tsv",
    ]


def _m07b_paths(ctx: RunContext) -> list[Path]:
    table = ctx.run_path("02_foldseek/tables/full")
    qc = ctx.run_path("02_foldseek/qc/full")
    return [
        table / "full_vs_afsp_foldseek_all_hits.tsv",
        table / "full_manual_id_map.tsv",
        table / "full_vs_afsp_foldseek_best_hit_rank1.tsv",
        table / "full_vs_afsp_foldseek_best_hit_rank1_classified.tsv",
        table / "full_vs_afsp_foldseek_top5_hits.tsv",
        table / "full_vs_afsp_foldseek_qtmmax_audit.tsv",
        table / "full_vs_afsp_foldseek_rank1_vs_qtmmax_audit.tsv",
        table / "full_vs_afsp_foldseek_neartie_top5_audit.tsv",
        qc / "full_vs_afsp_foldseek_canonical_summary.tsv",
        qc / "full_vs_afsp_foldseek_canonical_pointer.tsv",
    ]


def _run_m06b(ctx: RunContext, log: TextIO, follow: bool) -> int:
    cmd = [sys.executable, ctx.project_path("scripts/modules/06b_make_pdb_canonical_besthit_outputs.py")]
    cmd.extend(_m06b_paths(ctx))
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m07b(ctx: RunContext, log: TextIO, follow: bool) -> int:
    cmd = [sys.executable, ctx.project_path("scripts/modules/07b_make_afsp_canonical_besthit_outputs.py")]
    cmd.extend(_m07b_paths(ctx))
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m08(ctx: RunContext, log: TextIO, follow: bool) -> int:
    table = ctx.run_path("02_foldseek/tables/full")
    out = ctx.run_path("05_reference_panel/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/08_integrated_reference_panel_selector.py"),
        table / "full_vs_pdb_foldseek_best_hit_rank1_classified.tsv",
        table / "full_vs_pdb_foldseek_top5_hits.tsv",
        table / "full_vs_pdb_foldseek_qtmmax_audit.tsv",
        table / "full_vs_pdb_foldseek_rank1_vs_qtmmax_audit.tsv",
        table / "full_vs_pdb_foldseek_neartie_top5_audit.tsv",
        table / "full_vs_afsp_foldseek_best_hit_rank1_classified.tsv",
        table / "full_vs_afsp_foldseek_top5_hits.tsv",
        table / "full_vs_afsp_foldseek_qtmmax_audit.tsv",
        table / "full_vs_afsp_foldseek_rank1_vs_qtmmax_audit.tsv",
        table / "full_vs_afsp_foldseek_neartie_top5_audit.tsv",
        out / "full_integrated_reference_decision.tsv",
        out / "full_reference_panel_targets.tsv",
        out / "full_reference_panel_manual_review.tsv",
        out / "full_reference_panel_summary.tsv",
        out / "full_reference_panel_pointer.tsv",
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _portable_project_path(ctx: RunContext, value: str) -> str:
    text = str(value or "").replace("\\", "/")
    known_roots = [
        str(ctx.project_root).replace("\\", "/").rstrip("/") + "/",
    ]
    for root in known_roots:
        if text.startswith(root):
            return text[len(root):]
    return text


def _write_platform_query_manifest(ctx: RunContext) -> Path:
    src = ctx.run_path("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv")
    dst = ctx.run_path("tmp/m09a_full_query_pdb_manifest_platform.tsv")
    with src.open(errors="replace", newline="") as in_handle:
        reader = csv.DictReader(in_handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        rows = []
        for row in reader:
            row["query_pdb_file"] = _portable_project_path(ctx, row.get("query_pdb_file", ""))
            rows.append(row)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as out_handle:
        writer = csv.DictWriter(out_handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return dst


def _run_m09a(ctx: RunContext, log: TextIO, follow: bool) -> int:
    query_manifest = _write_platform_query_manifest(ctx)
    out = ctx.run_path("04_p2rank/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09_prepare_p2rank_input_manifests.py"),
        _rel(ctx, query_manifest),
        _rel(ctx, ctx.run_path("05_reference_panel/full/full_integrated_reference_decision.tsv")),
        _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        _rel(ctx, out / "input_manifests/full_p2rank_query_model_manifest.tsv"),
        _rel(ctx, out / "input_manifests/full_p2rank_reference_panel_manifest.tsv"),
        _rel(ctx, out / "reference_resolution/full_reference_panel_file_resolution_pending.tsv"),
        _rel(ctx, out / "qc/full_p2rank_input_manifest_summary.tsv"),
        _rel(ctx, out / "qc/full_p2rank_input_manifest_pointer.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _resource_path(ctx: RunContext, *keys: str) -> Path:
    raw = get_nested(ctx.cfg, *keys)
    if raw in (None, ""):
        raise SystemExit("CONFIG_ERROR: missing required resource path: " + ".".join(keys))
    return ctx.project_path(str(raw))


def _reference_materialization_method(ctx: RunContext) -> str:
    raw = get_nested(ctx.cfg, "reference_materialization", "method", default="foldseek_export")
    return str(raw or "foldseek_export").strip().lower()


def _write_fullatom_recovery_not_applicable(ctx: RunContext) -> None:
    report = ctx.run_path("04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv")
    fields = [
        "target", "status", "candidate_count", "candidate_file", "recovered_file",
        "same_pdb_id", "same_assembly", "requested_chain_label", "requested_atom_chain",
        "requested_chain_present", "atom_lines", "ca_atoms",
        "requested_chain_atom_lines", "requested_chain_ca_atoms", "note",
    ]
    rows = []
    for target in RECOVERY_TARGETS:
        try:
            pdbid, assembly, chain_label, atom_chain = _parse_reference_target(target)
        except ValueError:
            pdbid, assembly, chain_label, atom_chain = "", "", "", ""
        expected = (
            ctx.run_path("04_p2rank/full/reference_structures/materialized/pdb_chains")
            / f"{target}.chain_{atom_chain}.pdb"
        )
        rows.append({
            "target": target,
            "status": "NOT_APPLICABLE_FULL_ATOM_CACHE_EXACT_CHAIN_FILE_EXPECTED",
            "candidate_count": "0",
            "candidate_file": "",
            "recovered_file": _rel(ctx, expected),
            "same_pdb_id": "YES" if pdbid else "",
            "same_assembly": "YES" if assembly else "",
            "requested_chain_label": chain_label,
            "requested_atom_chain": atom_chain,
            "requested_chain_present": "",
            "atom_lines": "",
            "ca_atoms": "",
            "requested_chain_atom_lines": "",
            "requested_chain_ca_atoms": "",
            "note": "Full-atom cache mode uses exact pdb_chains files; legacy Foldseek alias recovery is bypassed.",
        })
    _write_tsv(report, rows, fields)


def _run_m09c_foldseek_export(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("04_p2rank/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09c_materialize_reference_structures_explicit.py"),
        "--panel", _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        "--foldseek-bin", _rel(ctx, _resource_path(ctx, "resources", "foldseek_bin")),
        "--pdb-db", _rel(ctx, _resource_path(ctx, "resources", "pdb_foldseek_db")),
        "--afsp-db", _rel(ctx, _resource_path(ctx, "resources", "afsp_foldseek_db")),
        "--pdb-out", _rel(ctx, out / "reference_structures/materialized/pdb"),
        "--afsp-out", _rel(ctx, out / "reference_structures/materialized/afsp"),
        "--report", _rel(ctx, out / "reference_resolution/full_reference_materialization_report.tsv"),
        "--allowed-root", _rel(ctx, ctx.run_root),
        "--write",
    ]
    rc = _run_command(ctx, [str(x) for x in cmd], log, follow)
    if rc != 0:
        return rc
    try:
        rows = _recover_reviewed_pdb_aliases(ctx, log, follow)
    except SystemExit as exc:
        return int(exc.code or 1)
    _log(log, follow, f"review_recovered_aliases\t{sum(1 for r in rows if r['status'] == RECOVERY_STATUS)}")
    return 0


def _run_m09c_fullatom_cache(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("04_p2rank/full")
    source_root_raw = get_nested(ctx.cfg, "reference_materialization", "source_run_root", default="")
    if source_root_raw in (None, ""):
        raise SystemExit("CONFIG_ERROR: reference_materialization.source_run_root is required for method=full_atom_cache")
    overwrite = bool_value(get_nested(ctx.cfg, "reference_materialization", "overwrite", default=False), default=False)
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09c_materialize_fullatom_references_from_cache.py"),
        "--panel", _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        "--source-run-root", _rel(ctx, ctx.project_path(str(source_root_raw))),
        "--pdb-out", _rel(ctx, out / "reference_structures/materialized/pdb_chains"),
        "--afsp-out", _rel(ctx, out / "reference_structures/materialized/afsp"),
        "--manifest", _rel(ctx, out / "input_manifests/fullatom_reference_full_materialized_manifest.tsv"),
        "--report", _rel(ctx, out / "reference_resolution/full_reference_materialization_report.tsv"),
        "--summary", _rel(ctx, out / "reference_resolution/full_reference_materialization_summary.tsv"),
        "--project-root", _rel(ctx, ctx.project_root),
        "--allowed-root", _rel(ctx, ctx.run_root),
    ]
    if overwrite:
        cmd.append("--overwrite")
    rc = _run_command(ctx, [str(x) for x in cmd], log, follow)
    if rc != 0:
        return rc
    _write_fullatom_recovery_not_applicable(ctx)
    return 0


def _run_m09c_materialize(ctx: RunContext, log: TextIO, follow: bool) -> int:
    method = _reference_materialization_method(ctx)
    _log(log, follow, f"reference_materialization_method\t{method}")
    if method in {"full_atom_cache", "fullatom_cache", "cache_full_atom"}:
        return _run_m09c_fullatom_cache(ctx, log, follow)
    if method in {"foldseek_export", "foldseek", "legacy_foldseek_export"}:
        return _run_m09c_foldseek_export(ctx, log, follow)
    raise SystemExit(f"CONFIG_ERROR: unsupported reference_materialization.method: {method}")


RECOVERY_STATUS = "REVIEW_RECOVERED_SAME_ASSEMBLY_REQUESTED_CHAIN_PRESENT"
PDBID_ONLY_STATUS = "REVIEW_FALLBACK_PDBID_ONLY"
RECOVERY_TARGETS = ("6vlx-assembly1_B-2", "7d7o-assembly1_B-2")


def _parse_reference_target(target: str) -> tuple[str, str, str, str]:
    match = re.match(r"^([0-9][A-Za-z0-9]{3})-assembly([0-9]+)_([A-Za-z0-9-]+)$", target)
    if not match:
        raise ValueError(f"unsupported PDB target format: {target}")
    pdbid, assembly, chain_label = match.groups()
    atom_chain = chain_label.split("-", 1)[0]
    return pdbid.lower(), assembly, chain_label, atom_chain


def _pdb_chain_stats(path: Path, atom_chain: str) -> dict[str, int]:
    stats = {
        "atom_lines": 0,
        "ca_atoms": 0,
        "requested_chain_atom_lines": 0,
        "requested_chain_ca_atoms": 0,
    }
    with path.open(errors="replace") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            stats["atom_lines"] += 1
            atom_name = line[12:16].strip()
            chain = line[21].strip()
            if atom_name == "CA":
                stats["ca_atoms"] += 1
            if chain == atom_chain:
                stats["requested_chain_atom_lines"] += 1
                if atom_name == "CA":
                    stats["requested_chain_ca_atoms"] += 1
    return stats


def _recover_reviewed_pdb_aliases(ctx: RunContext, log: TextIO, follow: bool) -> list[dict[str, str]]:
    pdb_dir = ctx.run_path("04_p2rank/full/reference_structures/materialized/pdb")
    report = ctx.run_path("04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv")
    rows: list[dict[str, str]] = []
    fields = [
        "target", "status", "candidate_count", "candidate_file", "recovered_file",
        "same_pdb_id", "same_assembly", "requested_chain_label", "requested_atom_chain",
        "requested_chain_present", "atom_lines", "ca_atoms",
        "requested_chain_atom_lines", "requested_chain_ca_atoms", "note",
    ]
    for target in RECOVERY_TARGETS:
        pdbid, assembly, chain_label, atom_chain = _parse_reference_target(target)
        requested = pdb_dir / f"{target}.pdb"
        candidates = []
        for path in sorted(pdb_dir.glob(f"{pdbid}-assembly{assembly}_*.pdb")):
            if path.name == requested.name:
                continue
            stats = _pdb_chain_stats(path, atom_chain)
            if stats["requested_chain_atom_lines"] > 0 and stats["requested_chain_ca_atoms"] > 0:
                candidates.append((path, stats))

        if len(candidates) != 1:
            row = {
                "target": target,
                "status": "INVALID_AMBIGUOUS_OR_MISSING_CANDIDATE",
                "candidate_count": str(len(candidates)),
                "candidate_file": "",
                "recovered_file": _rel(ctx, requested),
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
            rows.append(row)
            continue

        candidate, stats = candidates[0]
        if requested.exists():
            raise SystemExit(f"ERROR: refusing to overwrite recovered reference file: {requested}")
        requested.write_bytes(candidate.read_bytes())
        row = {
            "target": target,
            "status": RECOVERY_STATUS,
            "candidate_count": "1",
            "candidate_file": _rel(ctx, candidate),
            "recovered_file": _rel(ctx, requested),
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
        rows.append(row)
        _log(log, follow, "RECOVERED_REFERENCE\t" + "\t".join([target, row["candidate_file"], row["recovered_file"]]))

    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if any(row["status"] != RECOVERY_STATUS for row in rows):
        for row in rows:
            _log(log, follow, "RECOVERY_ROW\t" + "\t".join(row.get(field, "") for field in fields))
        raise SystemExit("ERROR: reviewed PDB alias recovery validation failed")
    return rows


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(errors="replace", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _rewrite_resolution_summary(summary_path: Path, resolved_rows: list[dict[str, str]], unique_rows: list[dict[str, str]]) -> None:
    summary = Counter()
    summary["panel_rows"] = len(resolved_rows)
    summary["resolved_rows"] = sum(1 for row in resolved_rows if row.get("reference_file_exists") == "YES")
    summary["missing_rows"] = sum(1 for row in resolved_rows if row.get("reference_file_exists") != "YES")
    summary["unique_resolved_reference_files"] = len(unique_rows)
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
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key in sorted(summary):
            writer.writerow([key, summary[key]])


def _annotate_m09b_resolution(ctx: RunContext, log: TextIO, follow: bool) -> None:
    base = ctx.run_path("04_p2rank/full")
    resolved_path = base / "input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv"
    unique_path = base / "input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"
    report_path = base / "reference_resolution/full_reference_panel_file_resolution_report.tsv"
    summary_path = base / "reference_resolution/full_reference_panel_file_resolution_summary.tsv"

    resolved_rows = _read_tsv(resolved_path)
    unique_rows = _read_tsv(unique_path)
    report_rows = _read_tsv(report_path)
    recovery_targets = set(RECOVERY_TARGETS)

    fallback_rows = 0
    recovery_rows = 0
    for row in resolved_rows:
        if row.get("reference_layer") == "PDB" and row.get("target") in recovery_targets:
            row["reference_file_resolution_status"] = RECOVERY_STATUS
            row["resolution_method"] = RECOVERY_STATUS
            row["resolution_n_matches"] = "1"
            row["reference_file_source_class"] = "review_recovered_same_assembly_requested_chain_present"
            recovery_rows += 1
        elif row.get("resolution_method") == "PDBID_ONLY_SUBSTRING":
            row["reference_file_resolution_status"] = PDBID_ONLY_STATUS
            row["resolution_method"] = PDBID_ONLY_STATUS
            row["reference_file_source_class"] = "review_fallback_pdbid_only"
            fallback_rows += 1

    for row in report_rows:
        if row.get("reference_layer") == "PDB" and row.get("target") in recovery_targets:
            row["resolution_status"] = RECOVERY_STATUS
            row["resolution_method"] = RECOVERY_STATUS
            row["resolution_n_matches"] = "1"
            row["comment"] = "Reviewed same-PDB/same-assembly recovery with requested chain present."
        elif row.get("resolution_method") == "PDBID_ONLY_SUBSTRING":
            row["resolution_status"] = PDBID_ONLY_STATUS
            row["resolution_method"] = PDBID_ONLY_STATUS
            row["comment"] = "Review-grade PDBID-only fallback; not a clean exact target match."

    for row in unique_rows:
        if row.get("reference_layer") == "PDB" and row.get("target") in recovery_targets:
            row["reference_file_source_class"] = "review_recovered_same_assembly_requested_chain_present"
        elif row.get("target") and any(
            rr.get("reference_layer") == row.get("reference_layer")
            and rr.get("target") == row.get("target")
            and rr.get("resolution_method") == PDBID_ONLY_STATUS
            for rr in resolved_rows
        ):
            row["reference_file_source_class"] = "review_fallback_pdbid_only"

    _write_tsv(resolved_path, resolved_rows, list(resolved_rows[0].keys()))
    _write_tsv(unique_path, unique_rows, list(unique_rows[0].keys()))
    _write_tsv(report_path, report_rows, list(report_rows[0].keys()))
    _rewrite_resolution_summary(summary_path, resolved_rows, unique_rows)
    _log(log, follow, f"annotated_recovery_rows\t{recovery_rows}")
    _log(log, follow, f"annotated_pdbid_only_fallback_rows\t{fallback_rows}")


def _reference_materialized_roots(ctx: RunContext, out: Path) -> list[Path]:
    method = _reference_materialization_method(ctx)
    if method in {"full_atom_cache", "fullatom_cache", "cache_full_atom"}:
        return [
            out / "reference_structures/materialized/pdb_chains",
            out / "reference_structures/materialized/afsp",
        ]
    return [
        out / "reference_structures/materialized/pdb",
        out / "reference_structures/materialized/afsp",
    ]


def _reference_atom_guard_enabled(ctx: RunContext) -> bool:
    raw = get_nested(ctx.cfg, "reference_materialization", "guard_reference_atom_names", default=None)
    if raw is None:
        return _reference_materialization_method(ctx) in {"full_atom_cache", "fullatom_cache", "cache_full_atom"}
    return bool_value(raw, default=True)


def _run_reference_atom_guard(ctx: RunContext, log: TextIO, follow: bool) -> int:
    base = ctx.run_path("04_p2rank/full")
    allow_ca_only = bool_value(
        get_nested(ctx.cfg, "reference_materialization", "allow_ca_only_diagnostic", default=False),
        default=False,
    )
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09d_guard_reference_atom_names.py"),
        "--manifest", _rel(ctx, base / "input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"),
        "--out-audit", _rel(ctx, base / "qc/full_reference_atom_name_guard_audit.tsv"),
        "--out-summary", _rel(ctx, base / "qc/full_reference_atom_name_guard_summary.tsv"),
        "--project-root", _rel(ctx, ctx.project_root),
        "--allowed-root", _rel(ctx, ctx.run_root),
    ]
    if allow_ca_only:
        cmd.append("--allow-ca-only-diagnostic")
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m09b_resolve(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("04_p2rank/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09b_resolve_reference_panel_files.py"),
        _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        _rel(ctx, out / "input_manifests/full_p2rank_reference_panel_manifest.tsv"),
        _rel(ctx, out / "input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv"),
        _rel(ctx, out / "input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"),
        _rel(ctx, out / "reference_resolution/full_reference_panel_file_resolution_report.tsv"),
        _rel(ctx, out / "reference_resolution/full_reference_panel_file_resolution_summary.tsv"),
        _rel(ctx, out / "reference_resolution/full_reference_panel_file_resolution_pointer.tsv"),
    ]
    cmd.extend(_rel(ctx, root) for root in _reference_materialized_roots(ctx, out))
    rc = _run_command(ctx, [str(x) for x in cmd], log, follow)
    if rc != 0:
        return rc
    if _reference_materialization_method(ctx) in {"foldseek_export", "foldseek", "legacy_foldseek_export"}:
        _annotate_m09b_resolution(ctx, log, follow)
    if _reference_atom_guard_enabled(ctx):
        return _run_reference_atom_guard(ctx, log, follow)
    return 0


def _metric(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    with path.open(errors="replace", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("metric") == key:
                return row.get("value", "")
    return ""


def _write_p2rank_runner(
    ctx: RunContext,
    *,
    role: str,
    manifest: Path,
    out_root: Path,
    run_manifest: Path,
    failed: Path,
    dataset_dir: Path,
    runner: Path,
    threads: int,
    chunk_size: int,
) -> None:
    helper = ctx.project_path("scripts/modules/run_p2rank_manifest_explicit.py")
    java_bin = str(get_nested(ctx.cfg, "resources", "java_bin", default="java"))
    p2rank_jar = _rel(ctx, _resource_path(ctx, "resources", "p2rank_jar"))
    text = "\n".join([
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f'PROJECT_ROOT="{ctx.project_root.as_posix()}"',
        'cd "$PROJECT_ROOT"',
        f'python3 "{_rel(ctx, helper)}" \\',
        f'  --role "{role}" \\',
        f'  --manifest "{_rel(ctx, manifest)}" \\',
        f'  --out-root "{_rel(ctx, out_root)}" \\',
        f'  --run-manifest "{_rel(ctx, run_manifest)}" \\',
        f'  --failed "{_rel(ctx, failed)}" \\',
        f'  --dataset-dir "{_rel(ctx, dataset_dir)}" \\',
        f'  --p2rank-jar "{p2rank_jar}" \\',
        f'  --java-bin "{java_bin}" \\',
        f'  --project-root "$PROJECT_ROOT" \\',
        f'  --allowed-root "{_rel(ctx, ctx.run_root)}" \\',
        f'  --threads "{threads}" \\',
        f'  --chunk-size "{chunk_size}"',
        "",
    ])
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text(text, encoding="utf-8", newline="\n")
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _audit_p2rank_runners(ctx: RunContext, log: TextIO, follow: bool) -> bool:
    base = ctx.run_path("04_p2rank/full")
    audit_path = base / "qc/full_p2rank_runner_audit.tsv"
    query_runner = base / "local_runs/runfull_p2rank_query_models_local.sh"
    ref_runner = base / "local_runs/runfull_p2rank_reference_resolved_unique_local.sh"
    query_manifest = base / "input_manifests/full_p2rank_query_model_manifest.tsv"
    ref_manifest = base / "input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"
    rows = []

    def add(check: str, status: str, detail: str) -> None:
        rows.append({"check": check, "status": status, "detail": detail})

    for label, path in (("query_runner", query_runner), ("reference_runner", ref_runner)):
        text = path.read_text(errors="replace") if path.exists() else ""
        add(f"{label}_exists", "PASS" if path.is_file() else "FAIL", _rel(ctx, path))
        add(f"{label}_no_arf_scratch", "PASS" if "/arf/scratch" not in text else "FAIL", "")
        add(f"{label}_no_sbatch", "PASS" if "sbatch" not in text.lower() and "#SBATCH" not in text else "FAIL", "")
        add(f"{label}_no_rm_rf", "PASS" if "rm -rf" not in text else "FAIL", "")
        add(f"{label}_allowed_output_root", "PASS" if _rel(ctx, ctx.run_root) in text else "FAIL", _rel(ctx, ctx.run_root))

    query_rows = _read_tsv(query_manifest)
    ref_rows = _read_tsv(ref_manifest)
    add("query_manifest_rows", "PASS" if len(query_rows) > 0 else "FAIL", str(len(query_rows)))
    add("reference_manifest_rows", "PASS" if len(ref_rows) > 0 else "FAIL", str(len(ref_rows)))
    add("p2rank_jar_exists", "PASS" if _resource_path(ctx, "resources", "p2rank_jar").is_file() else "FAIL", str(_resource_path(ctx, "resources", "p2rank_jar")))
    add("query_pdb_paths_exist", "PASS" if all(ctx.project_path(r["query_model_pdb"]).is_file() for r in query_rows) else "FAIL", "")
    add("reference_pdb_paths_exist", "PASS" if all(ctx.project_path(r["reference_file_path"]).is_file() for r in ref_rows) else "FAIL", "")

    _write_tsv(audit_path, rows, ["check", "status", "detail"])
    for row in rows:
        _log(log, follow, f"RUNNER_AUDIT\t{row['check']}\t{row['status']}\t{row['detail']}")
    return all(row["status"] == "PASS" for row in rows)


def _run_m09d_generate_runners(ctx: RunContext, log: TextIO, follow: bool) -> int:
    base = ctx.run_path("04_p2rank/full")
    threads = int(get_nested(ctx.cfg, "p2rank", "threads", default=4))
    chunk_size = int(get_nested(ctx.cfg, "p2rank", "chunk_size", default=64))
    query_runner = base / "local_runs/runfull_p2rank_query_models_local.sh"
    ref_runner = base / "local_runs/runfull_p2rank_reference_resolved_unique_local.sh"
    query_manifest = base / "input_manifests/full_p2rank_query_model_manifest.tsv"
    ref_manifest = base / "input_manifests/full_p2rank_reference_unique_structure_manifest.tsv"
    _write_p2rank_runner(
        ctx,
        role="query",
        manifest=query_manifest,
        out_root=base / "query_models/all",
        run_manifest=base / "query_models/all/query_p2rank_run_manifest.tsv",
        failed=base / "query_models/all/query_p2rank_failed.tsv",
        dataset_dir=base / "local_runs/datasets/query",
        runner=query_runner,
        threads=threads,
        chunk_size=chunk_size,
    )
    _write_p2rank_runner(
        ctx,
        role="reference",
        manifest=ref_manifest,
        out_root=base / "reference_models/resolved_unique",
        run_manifest=base / "reference_models/resolved_unique/reference_p2rank_run_manifest.tsv",
        failed=base / "reference_models/resolved_unique/reference_p2rank_failed.tsv",
        dataset_dir=base / "local_runs/datasets/reference",
        runner=ref_runner,
        threads=threads,
        chunk_size=chunk_size,
    )
    run_manifest = base / "full_p2rank_local_run_manifest.tsv"
    with run_manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["mode", "runner_role", "runner_path", "input_manifest", "output_root", "input_rows", "status", "note"])
        writer.writerow(["full", "query", _rel(ctx, query_runner), _rel(ctx, query_manifest), _rel(ctx, base / "query_models/all"), len(_read_tsv(query_manifest)), "READY", "orchestrator_explicit_runner"])
        writer.writerow(["full", "reference", _rel(ctx, ref_runner), _rel(ctx, ref_manifest), _rel(ctx, base / "reference_models/resolved_unique"), len(_read_tsv(ref_manifest)), "READY", "orchestrator_explicit_runner"])
    if not _audit_p2rank_runners(ctx, log, follow):
        return 2
    return 0


def _run_p2rank_role(ctx: RunContext, role: str, log: TextIO, follow: bool) -> int:
    base = ctx.run_path("04_p2rank/full")
    runner = (
        base / "local_runs/runfull_p2rank_query_models_local.sh"
        if role == "query"
        else base / "local_runs/runfull_p2rank_reference_resolved_unique_local.sh"
    )
    return _run_command(ctx, ["bash", _rel(ctx, runner)], log, follow)


def _run_m09e_query_merge(ctx: RunContext, log: TextIO, follow: bool) -> int:
    base = ctx.run_path("04_p2rank/full")
    merged = base / "query_models/merged_tables"
    qc = base / "qc"
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09e_merge_query_p2rank_outputs.py"),
        _rel(ctx, base / "query_models/all/query_p2rank_run_manifest.tsv"),
        _rel(ctx, merged / "full_query_p2rank_predictions_merged.tsv"),
        _rel(ctx, merged / "full_query_p2rank_residues_merged.tsv"),
        _rel(ctx, merged / "full_query_p2rank_top1_pockets.tsv"),
        _rel(ctx, merged / "full_query_p2rank_family_summary.tsv"),
        _rel(ctx, qc / "full_query_p2rank_merge_qc_report.tsv"),
        _rel(ctx, qc / "full_query_p2rank_merge_pointer.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m09f_reference_counts(ctx: RunContext, log: TextIO, follow: bool) -> int:
    base = ctx.run_path("04_p2rank/full")
    qc = base / "qc"
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09f_make_reference_pocket_counts.py"),
        _rel(ctx, base / "reference_models/resolved_unique/reference_p2rank_run_manifest.tsv"),
        _rel(ctx, qc / "full_p2rank_reference_resolved_unique_pocket_counts.tsv"),
        _rel(ctx, qc / "full_p2rank_reference_zero_pocket_report.tsv"),
        _rel(ctx, qc / "full_p2rank_reference_resolved_unique_qc_report.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m09g_reference_merge(ctx: RunContext, log: TextIO, follow: bool) -> int:
    base = ctx.run_path("04_p2rank/full")
    merged = base / "reference_models/merged_tables"
    qc = base / "qc"
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09g_merge_reference_p2rank_outputs.py"),
        _rel(ctx, base / "reference_models/resolved_unique/reference_p2rank_run_manifest.tsv"),
        _rel(ctx, merged / "full_reference_p2rank_predictions_merged.tsv"),
        _rel(ctx, merged / "full_reference_p2rank_residues_merged.tsv"),
        _rel(ctx, merged / "full_reference_p2rank_top1_pockets.tsv"),
        _rel(ctx, merged / "full_reference_p2rank_layer_summary.tsv"),
        _rel(ctx, qc / "full_reference_p2rank_merge_qc_report.tsv"),
        _rel(ctx, qc / "full_reference_p2rank_merge_pointer.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _cfg_path(ctx: RunContext, *keys: str) -> str:
    raw = get_nested(ctx.cfg, *keys, default="")
    if raw in (None, ""):
        return "__MISSING_CONFIG_" + ".".join(keys) + "__"
    return str(raw)


def _run_phase1_scaffold(
    ctx: RunContext,
    log: TextIO,
    follow: bool,
    *,
    stage_id: str,
    script_name: str,
    inputs: list[tuple[str, str | Path]],
    outputs: list[tuple[str, Path]],
    headers: list[tuple[str, str]] | None = None,
) -> int:
    cmd: list[str | Path] = [
        sys.executable,
        ctx.project_path(f"scripts/modules/{script_name}"),
        "--stage-id",
        stage_id,
        "--mode",
        "full",
        "--workspace",
        ctx.project_root,
        "--contract-headers",
        "pipeline_contracts/catalytic_previsual_output_headers.tsv",
    ]
    for label, value in inputs:
        text = _rel(ctx, value) if isinstance(value, Path) else value
        cmd.extend(["--input", label, text])
    for artifact, path in outputs:
        cmd.extend(["--output", artifact, _rel(ctx, path)])
    for artifact, header in headers or []:
        cmd.extend(["--header", artifact, header])
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m09h_topology(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/09_topology")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="151_m09h_deeptmhmm_topology",
        script_name="09h_parse_deeptmhmm_topology.py",
        inputs=[
            ("query_manifest", ctx.run_path("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv")),
            ("deeptmhmm_results_dir", _cfg_path(ctx, "catalytic", "deeptmhmm_results_dir")),
        ],
        outputs=[
            ("deeptmhmm_query_topology", out / "full_deeptmhmm_query_topology.tsv"),
            ("deeptmhmm_query_topology_qc", out / "full_deeptmhmm_query_topology_qc.tsv"),
        ],
        headers=[
            ("deeptmhmm_query_topology", "mode\tquery\tprotein_id\ttier\tfamily\toriginal_header\tnormalized_header\ttopology_class\tsignal_peptide_flag\ttm_segment_n\ttm_ranges\tparse_status\tqc_flag"),
        ],
    )


def _run_m09i_topology_context(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/09_topology")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="152_m09i_topology_pocket_context",
        script_name="09i_query_pocket_topology_context.py",
        inputs=[
            ("deeptmhmm_query_topology", out / "full_deeptmhmm_query_topology.tsv"),
            ("query_top1_pockets", ctx.run_path("04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv")),
        ],
        outputs=[
            ("query_pocket_topology_context", out / "full_query_pocket_topology_context.tsv"),
            ("query_pocket_topology_context_qc", out / "full_query_pocket_topology_context_qc.tsv"),
        ],
        headers=[
            ("query_pocket_topology_context", "mode\tquery\tprotein_id\tfamily\ttopology_class\tquery_top1_pocket_status\tquery_top1_residue_ids\ttm_overlap_residue_n\tsignal_peptide_overlap_flag\ttopology_pocket_context_class\ttopology_pocket_context_note"),
        ],
    )


def _run_m09j_catalytic_stack_manifest(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    p2 = ctx.run_path("04_p2rank/full")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="153_m09j_catalytic_stack_manifest",
        script_name="09j_build_catalytic_stack_manifest.py",
        inputs=[
            ("query_manifest", ctx.run_path("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv")),
            ("reference_panel", ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
            ("reference_resolved", p2 / "input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv"),
            ("topology_context", ctx.run_path("results/full/09_topology/full_query_pocket_topology_context.tsv")),
        ],
        outputs=[
            ("catalytic_stack_manifest", out / "full_catalytic_stack_manifest.tsv"),
            ("catalytic_stack_manifest_qc", out / "full_catalytic_stack_manifest_qc.tsv"),
        ],
    )


def _run_m09k_mcsa_cache(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="154_m09k_mcsa_resource_cache",
        script_name="09k_cache_parse_mcsa_resources.py",
        inputs=[
            ("mcsa_resource_root", _cfg_path(ctx, "catalytic", "mcsa_resource_root")),
            ("mcsa_resource_contract", "pipeline_contracts/mcsa_resource_contract.tsv"),
        ],
        outputs=[
            ("mcsa_resource_audit", out / "full_mcsa_resource_audit.tsv"),
            ("mcsa_resource_audit_qc", out / "full_mcsa_resource_audit_qc.tsv"),
        ],
        headers=[
            ("mcsa_resource_audit", "mode\tresource_key\tresource_path\tresource_exists\tresource_kind\tchecksum_sha256\tschema_status\trow_count\tcache_status\taudit_note"),
        ],
    )


def _run_m09l_uniprot_evidence(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="155_m09l_uniprot_residue_evidence",
        script_name="09l_cache_parse_uniprot_residue_evidence.py",
        inputs=[
            ("catalytic_stack_manifest", out / "full_catalytic_stack_manifest.tsv"),
            ("uniprot_resource_root", _cfg_path(ctx, "catalytic", "uniprot_resource_root")),
            ("uniprot_evidence_policy", "pipeline_contracts/uniprot_residue_evidence_policy.tsv"),
        ],
        outputs=[
            ("uniprot_residue_evidence", out / "full_uniprot_residue_evidence.tsv"),
            ("uniprot_residue_evidence_qc", out / "full_uniprot_residue_evidence_qc.tsv"),
        ],
        headers=[
            ("uniprot_residue_evidence", "mode\tquery\tprotein_id\tfamily\treference_layer\ttarget\tuniprot_accession\tfeature_type\tfeature_position\tresidue_type\tevidence_code\tevidence_tier\tparse_status\tevidence_note"),
        ],
    )


def _run_m09m_candidate_evidence(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="156_m09m_catalytic_candidate_evidence",
        script_name="09m_generate_catalytic_candidate_evidence.py",
        inputs=[
            ("catalytic_stack_manifest", out / "full_catalytic_stack_manifest.tsv"),
            ("mcsa_resource_audit", out / "full_mcsa_resource_audit.tsv"),
            ("uniprot_residue_evidence", out / "full_uniprot_residue_evidence.tsv"),
        ],
        outputs=[
            ("candidate_catalytic_reference_evidence_long", out / "full_candidate_catalytic_reference_evidence_long.tsv"),
            ("candidate_catalytic_reference_evidence_long_qc", out / "full_candidate_catalytic_reference_evidence_long_qc.tsv"),
        ],
    )


def _run_m09n_pairwise_job_plan(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="157_m09n_pairwise_foldseek_job_plan",
        script_name="09n_prepare_pairwise_foldseek_alignment_jobs.py",
        inputs=[
            ("candidate_evidence", out / "full_candidate_catalytic_reference_evidence_long.tsv"),
            ("catalytic_stack_manifest", out / "full_catalytic_stack_manifest.tsv"),
        ],
        outputs=[
            ("pairwise_alignment_job_plan", out / "full_pairwise_alignment_job_plan.tsv"),
            ("pairwise_alignment_job_plan_qc", out / "full_pairwise_alignment_job_plan_qc.tsv"),
        ],
        headers=[
            ("pairwise_alignment_job_plan", "mode\talignment_pair_id\tquery\tpanel_order\treference_layer\ttarget\tunique_reference_id\tquery_pdb_path_portable\treference_file_path_portable\tplanned_command\tplanned_partition\tjob_script_path\tplan_status\tplan_note"),
        ],
    )


def _run_m09o_alignment_inventory(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="158_m09o_pairwise_alignment_inventory",
        script_name="09o_merge_pairwise_foldseek_alignments.py",
        inputs=[("pairwise_alignment_job_plan", out / "full_pairwise_alignment_job_plan.tsv")],
        outputs=[
            ("pairwise_alignment_inventory", out / "full_pairwise_alignment_inventory.tsv"),
            ("pairwise_alignment_inventory_qc", out / "full_pairwise_alignment_inventory_qc.tsv"),
        ],
    )


def _run_m09p_coordinate_rescue(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="159_m09p_mcsa_coordinate_rescue",
        script_name="09p_mcsa_original_pdb_coordinate_rescue.py",
        inputs=[
            ("candidate_evidence", out / "full_candidate_catalytic_reference_evidence_long.tsv"),
            ("rcsb_original_pdb_cache", _cfg_path(ctx, "catalytic", "rcsb_original_pdb_cache")),
        ],
        outputs=[
            ("mcsa_original_pdb_coordinate_rescue", out / "full_mcsa_original_pdb_coordinate_rescue.tsv"),
            ("mcsa_original_pdb_coordinate_rescue_qc", out / "full_mcsa_original_pdb_coordinate_rescue_qc.tsv"),
        ],
    )


def _run_m09q_residue_transfer(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="159q_m09q_catalytic_residue_transfer",
        script_name="09q_final_catalytic_residue_transfer.py",
        inputs=[
            ("candidate_evidence", out / "full_candidate_catalytic_reference_evidence_long.tsv"),
            ("pairwise_alignment_inventory", out / "full_pairwise_alignment_inventory.tsv"),
            ("mcsa_coordinate_rescue", out / "full_mcsa_original_pdb_coordinate_rescue.tsv"),
        ],
        outputs=[
            ("candidate_residue_transfer_mapping_mcsa_rescued", out / "full_candidate_residue_transfer_mapping_mcsa_rescued.tsv"),
            ("query_level_catalytic_residue_summary", out / "full_query_level_catalytic_residue_summary.tsv"),
            ("catalytic_residue_class_summary", out / "full_catalytic_residue_class_summary.tsv"),
            ("final_catalytic_layer_integration", out / "full_final_catalytic_layer_integration.tsv"),
            ("catalytic_residue_transfer_qc", out / "full_catalytic_residue_transfer_qc.tsv"),
        ],
        headers=[
            ("catalytic_residue_class_summary", "mode\tcatalytic_residue_class\tn"),
        ],
    )


def _run_m09r_visual_annotation(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="159r_m09r_catalytic_visual_annotation",
        script_name="09r_prepare_catalytic_visual_annotation_manifest.py",
        inputs=[
            ("catalytic_stack_manifest", out / "full_catalytic_stack_manifest.tsv"),
            ("residue_transfer_mapping", out / "full_candidate_residue_transfer_mapping_mcsa_rescued.tsv"),
            ("final_catalytic_layer_integration", out / "full_final_catalytic_layer_integration.tsv"),
        ],
        outputs=[
            ("catalytic_visual_query_manifest", out / "full_catalytic_visual_query_manifest.tsv"),
            ("catalytic_visual_annotation_manifest", out / "full_catalytic_visual_annotation_manifest.tsv"),
            ("catalytic_visual_annotation_manifest_qc", out / "full_catalytic_visual_annotation_manifest_qc.tsv"),
        ],
    )


def _run_m09r_validate_catalytic_outputs(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/10_catalytic_layer/full_previsual_catalytic_validation_qc.tsv")
    validation_mode = str(get_nested(ctx.cfg, "catalytic", "validation_mode", default="precomputed"))
    expected_version = str(get_nested(ctx.cfg, "catalytic", "expected_version", default="A10G_FIX2"))
    # Golden row-count expectations are opt-in (0 = count-agnostic / not enforced).
    expected_query_count = str(get_nested(ctx.cfg, "catalytic", "expected_query_count", default=0))
    expected_residue_rows = str(get_nested(ctx.cfg, "catalytic", "expected_residue_rows", default=0))
    expected_manual_override_rows = str(get_nested(ctx.cfg, "catalytic", "expected_manual_override_rows", default=0))
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/09r_validate_previsual_catalytic_outputs.py"),
        "--mode",
        "full",
        "--run-root",
        _rel(ctx, ctx.run_root),
        "--contract-headers",
        "pipeline_contracts/catalytic_previsual_output_headers.tsv",
        "--class-policy",
        "pipeline_contracts/catalytic_layer_class_policy.tsv",
        "--validation-mode",
        validation_mode,
        "--expected-version",
        expected_version,
        "--expected-query-count",
        expected_query_count,
        "--expected-residue-rows",
        expected_residue_rows,
        "--expected-manual-override-rows",
        expected_manual_override_rows,
        "--out",
        _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m10a(ctx: RunContext, log: TextIO, follow: bool) -> int:
    p2 = ctx.run_path("04_p2rank/full")
    v = ctx.run_path("06_visual_qc_v6/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/10a_prepare_visual_overlay_input_contract.py"),
        _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        _rel(ctx, ctx.run_path("05_reference_panel/full/full_integrated_reference_decision.tsv")),
        _rel(ctx, p2 / "input_manifests/full_p2rank_query_model_manifest.tsv"),
        _rel(ctx, p2 / "query_models/merged_tables/full_query_p2rank_top1_pockets.tsv"),
        _rel(ctx, p2 / "input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv"),
        _rel(ctx, p2 / "qc/full_p2rank_reference_resolved_unique_pocket_counts.tsv"),
        _rel(ctx, p2 / "reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv"),
        _rel(ctx, v / "input_manifests/full_visual_overlay_input_contract.tsv"),
        _rel(ctx, v / "input_manifests/full_visual_overlay_query_summary.tsv"),
        _rel(ctx, v / "input_manifests/full_visual_overlay_reference_status_summary.tsv"),
        _rel(ctx, v / "qc/full_visual_overlay_input_contract_qc_report.tsv"),
        _rel(ctx, v / "qc/full_visual_overlay_input_contract_pointer.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m10h_catalytic_png(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("06_visual_qc_v6/full/catalytic_two_panel_png")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="165_m10h_catalytic_two_panel_png",
        script_name="10h_generate_catalytic_two_panel_figures.py",
        inputs=[
            ("catalytic_visual_query_manifest", ctx.run_path("results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv")),
            ("catalytic_visual_annotation_manifest", ctx.run_path("results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv")),
        ],
        outputs=[
            ("catalytic_two_panel_png_manifest", out / "full_catalytic_two_panel_png_manifest.tsv"),
            ("catalytic_two_panel_png_qc", out / "full_catalytic_two_panel_png_qc.tsv"),
        ],
        headers=[
            ("catalytic_two_panel_png_manifest", "mode\tquery\tprotein_id\tfamily\tpng_path\tvisual_annotation_status\trender_status\trender_note"),
        ],
    )


def _run_m10b(ctx: RunContext, log: TextIO, follow: bool) -> int:
    v = ctx.run_path("06_visual_qc_v6/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/10b_prepare_visual_overlay_smoke_package.py"),
        _rel(ctx, v / "input_manifests/full_visual_overlay_input_contract.tsv"),
        _rel(ctx, v / "smoke_package/full_visual_overlay_smoke_manifest.tsv"),
        _rel(ctx, v / "smoke_package/full_visual_overlay_smoke.pml"),
        _rel(ctx, v / "smoke_package/full_visual_overlay_smoke.cxc"),
        _rel(ctx, v / "smoke_package/README_smoke_visual_overlay.txt"),
        _rel(ctx, v / "qc/full_visual_overlay_smoke_qc_report.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m10c(ctx: RunContext, log: TextIO, follow: bool) -> int:
    v = ctx.run_path("06_visual_qc_v6/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/10c_prepare_all_query_visual_script_package.py"),
        _rel(ctx, v / "input_manifests/full_visual_overlay_input_contract.tsv"),
        _rel(ctx, v / "all_query_visual_scripts"),
        _rel(ctx, v / "all_query_visual_scripts/full_all_query_visual_script_manifest.tsv"),
        _rel(ctx, v / "all_query_visual_scripts/full_all_query_visual_script_query_summary.tsv"),
        _rel(ctx, v / "all_query_visual_scripts/full_all_query_visual_script_skipped_reference_report.tsv"),
        _rel(ctx, v / "all_query_visual_scripts/README_all_query_visual_scripts.txt"),
        _rel(ctx, v / "qc/full_all_query_visual_script_package_qc_report.tsv"),
        _rel(ctx, v / "qc/full_all_query_visual_script_package_pointer.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m10d(ctx: RunContext, log: TextIO, follow: bool) -> int:
    v = ctx.run_path("06_visual_qc_v6/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/10d_qc_visual_script_package.py"),
        _rel(ctx, v / "all_query_visual_scripts/full_all_query_visual_script_manifest.tsv"),
        _rel(ctx, v / "qc/full_visual_script_package_lite_row_qc.tsv"),
        _rel(ctx, v / "qc/full_visual_script_package_lite_qc_report.tsv"),
        _rel(ctx, v / "qc/full_visual_script_package_lite_pointer.tsv"),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m10f_render(ctx: RunContext, log: TextIO, follow: bool) -> int:
    v = ctx.run_path("06_visual_qc_v6/full")
    png_dir = v / "rendered_png"
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/m10f_render_all_query_pngs.py"),
        "--manifest",        _rel(ctx, v / "all_query_visual_scripts/full_all_query_visual_script_manifest.tsv"),
        "--out-png-dir",     _rel(ctx, png_dir),
        "--out-manifest",    _rel(ctx, png_dir / "full_rendered_png_manifest.tsv"),
        "--out-qc",          _rel(ctx, png_dir / "full_rendered_png_qc.tsv"),
        "--pymol-container", _rel(ctx, ctx.project_path("resources/containers/pymol_deb12_2.5.0_sc.sif")),
        "--project-root",    str(ctx.project_root),
        "--allowed-root",    _rel(ctx, ctx.run_root),
        "--panel-orders",    "1",
        "--dpi",             "150",
        "--mode",            "full",
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m11(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/06_supporting_reference_audit")
    p2 = ctx.run_path("04_p2rank/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/11_supporting_reference_audit.py"),
        "--mode", "full",
        "--panel",          _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        "--decision",       _rel(ctx, ctx.run_path("05_reference_panel/full/full_integrated_reference_decision.tsv")),
        "--visual-contract",_rel(ctx, ctx.run_path("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv")),
        "--query-top1",     _rel(ctx, p2 / "query_models/merged_tables/full_query_p2rank_top1_pockets.tsv"),
        "--reference-top1", _rel(ctx, p2 / "reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv"),
        "--outdir",         _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m12a(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/07_decision_matrix")
    v = ctx.run_path("06_visual_qc_v6/full")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/12a_lite_primary_decision_matrix.py"),
        "--mode", "full",
        "--m08-decision",       _rel(ctx, ctx.run_path("05_reference_panel/full/full_integrated_reference_decision.tsv")),
        "--pdb-rank1",          _rel(ctx, ctx.run_path("02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1_classified.tsv")),
        "--afsp-rank1",         _rel(ctx, ctx.run_path("02_foldseek/tables/full/full_vs_afsp_foldseek_best_hit_rank1_classified.tsv")),
        "--visual-contract",    _rel(ctx, v / "input_manifests/full_visual_overlay_input_contract.tsv"),
        "--m10d-qc",            _rel(ctx, v / "qc/full_visual_script_package_lite_qc_report.tsv"),
        "--m10e-render-manifest",_rel(ctx, v / "full_pymol_render_local_run_manifest.tsv"),
        "--m11-conflict",       _rel(ctx, ctx.run_path("results/full/06_supporting_reference_audit/full_supporting_reference_conflict_flags.tsv")),
        "--outdir",             _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m12b(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/07_decision_matrix")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/12b_supporting_reference_decision_matrix.py"),
        "--mode", "full",
        "--primary",        _rel(ctx, out / "full_primary_decision_matrix.tsv"),
        "--m11-audit",      _rel(ctx, ctx.run_path("results/full/06_supporting_reference_audit/full_supporting_reference_audit.tsv")),
        "--m11-conflict",   _rel(ctx, ctx.run_path("results/full/06_supporting_reference_audit/full_supporting_reference_conflict_flags.tsv")),
        "--visual-contract",_rel(ctx, ctx.run_path("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv")),
        "--panel",          _rel(ctx, ctx.run_path("05_reference_panel/full/full_reference_panel_targets.tsv")),
        "--outdir",         _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m12c(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/07_decision_matrix")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/12c_combined_decision_summary.py"),
        "--mode", "full",
        "--primary",    _rel(ctx, out / "full_primary_decision_matrix.tsv"),
        "--supporting", _rel(ctx, out / "full_supporting_reference_decision_matrix.tsv"),
        "--m11-conflict",_rel(ctx, ctx.run_path("results/full/06_supporting_reference_audit/full_supporting_reference_conflict_flags.tsv")),
        "--outdir",     _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m13a(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/08_rulebook_evidence")
    dec = ctx.run_path("results/full/07_decision_matrix")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/13a_rulebook_context_collector.py"),
        "--mode", "full",
        "--m12a",            _rel(ctx, dec / "full_primary_decision_matrix.tsv"),
        "--m12b",            _rel(ctx, dec / "full_supporting_reference_decision_matrix.tsv"),
        "--m12c",            _rel(ctx, dec / "full_combined_decision_summary.tsv"),
        "--family-coverage", "pipeline_data/rulebook/m13_existing_rulebook_family_coverage.tsv",
        "--known-rules",     "pipeline_data/rulebook/known_residue_rules.tsv",
        "--ligand-classes",  "pipeline_data/rulebook/ligand_biological_classes.tsv",
        "--case-definitions","pipeline_data/rulebook/section8_case_definitions.tsv",
        "--outdir",          _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m13b(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/08_rulebook_evidence")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/13b_existing_rulebook_classifier.py"),
        "--mode", "full",
        "--context",          _rel(ctx, out / "full_rulebook_context_collector.tsv"),
        "--m12a",             _rel(ctx, ctx.run_path("results/full/07_decision_matrix/full_primary_decision_matrix.tsv")),
        "--known-rules",      "pipeline_data/rulebook/known_residue_rules.tsv",
        "--case-definitions", "pipeline_data/rulebook/section8_case_definitions.tsv",
        "--old-auto",         "pipeline_data/rulebook/section8_final_auto_evidence_classification_refined_known_residue.tsv",
        "--outdir",           _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m13c(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/08_rulebook_evidence")
    dec = ctx.run_path("results/full/07_decision_matrix")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/13c_rulebook_coverage_mismatch_detector.py"),
        "--mode", "full",
        "--context",          _rel(ctx, out / "full_rulebook_context_collector.tsv"),
        "--classified",       _rel(ctx, out / "full_existing_rulebook_classified.tsv"),
        "--supporting",       _rel(ctx, dec / "full_supporting_reference_decision_matrix.tsv"),
        "--combined",         _rel(ctx, dec / "full_combined_decision_summary.tsv"),
        "--mismatch-taxonomy","pipeline_contracts/b9_m13_rulebook_mismatch_taxonomy.tsv",
        "--outdir",           _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m13d_lite(ctx: RunContext, log: TextIO, follow: bool) -> int:
    discovery = ctx.run_path("results/full/08_rulebook_evidence/discovery")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/13d_prepare_ligand_scan_inputs_lite.py"),
        "--mode", "full",
        "--visual-contract",_rel(ctx, ctx.run_path("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv")),
        "--outdir",         _rel(ctx, discovery),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m13d_scan(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/08_rulebook_evidence")
    discovery = out / "discovery"
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/13d_ligand_cofactor_context_scan.py"),
        "--mode", "full",
        "--scan-map",          _rel(ctx, discovery / "full_m13d_primary_supporting_reference_ligand_scan_map.tsv"),
        "--hetatm-inventory",  _rel(ctx, discovery / "full_m13d_reference_pdb_hetatm_inventory.tsv"),
        "--ligand-dictionary", "pipeline_data/rulebook/ligand_biological_classes.tsv",
        "--fallback",          "pipeline_contracts/b9_m13d_ligand_fallback_classes.tsv",
        "--m13b",              _rel(ctx, out / "full_existing_rulebook_classified.tsv"),
        "--m13c-notes",        _rel(ctx, out / "full_rulebook_supporting_context_notes.tsv"),
        "--outdir",            _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m13e(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/08_rulebook_evidence")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/13e_final_rulebook_evidence_matrix.py"),
        "--mode", "full",
        "--m13b",          _rel(ctx, out / "full_existing_rulebook_classified.tsv"),
        "--m13c-mismatch", _rel(ctx, out / "full_rulebook_mismatch_reasons.tsv"),
        "--m13c-suggest",  _rel(ctx, out / "full_rulebook_new_class_suggestions.tsv"),
        "--m13c-notes",    _rel(ctx, out / "full_rulebook_supporting_context_notes.tsv"),
        "--m13d-primary",  _rel(ctx, out / "full_ligand_cofactor_primary_context.tsv"),
        "--m13d-support",  _rel(ctx, out / "full_ligand_cofactor_supporting_context.tsv"),
        "--m12c",          _rel(ctx, ctx.run_path("results/full/07_decision_matrix/full_combined_decision_summary.tsv")),
        "--outdir",        _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m14(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("exports/full")
    evidence = ctx.run_path("results/full/08_rulebook_evidence")
    metadata_raw = get_nested(ctx.cfg, "inputs", "metadata_tsv", default="")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/14_final_export.py"),
        "--mode", "full",
        "--m13e-final",   _rel(ctx, evidence / "full_final_rulebook_evidence_matrix.tsv"),
        "--m13e-compact", _rel(ctx, evidence / "full_final_rulebook_evidence_compact.tsv"),
        "--run-label",    ctx.run_label,
        "--outdir",       _rel(ctx, out),
    ]
    if metadata_raw:
        cmd.extend(["--metadata", metadata_raw])
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_interpretation_ready_export(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("exports/full/interpretation_ready")
    cmd = [
        sys.executable,
        ctx.project_path("scripts/modules/interpretation_ready_export.py"),
        "--mode", "full",
        "--run-label",    ctx.run_label,
        "--m14-full",     _rel(ctx, ctx.run_path("exports/full/full_final_export_full.tsv")),
        "--m12a-primary", _rel(ctx, ctx.run_path("results/full/07_decision_matrix/full_primary_decision_matrix.tsv")),
        "--outdir",       _rel(ctx, out),
    ]
    return _run_command(ctx, [str(x) for x in cmd], log, follow)


def _run_m15b_parallel_integrated_export(ctx: RunContext, log: TextIO, follow: bool) -> int:
    out = ctx.run_path("results/full/11_integrated_exports")
    return _run_phase1_scaffold(
        ctx,
        log,
        follow,
        stage_id="330_m15b_parallel_integrated_export",
        script_name="15b_parallel_integrated_topology_catalytic_exports.py",
        inputs=[
            ("m14_full_export", ctx.run_path("exports/full/full_final_export_full.tsv")),
            ("topology_context", ctx.run_path("results/full/09_topology/full_query_pocket_topology_context.tsv")),
            ("final_catalytic_layer", ctx.run_path("results/full/10_catalytic_layer/full_final_catalytic_layer_integration.tsv")),
            ("catalytic_png_manifest", ctx.run_path("06_visual_qc_v6/full/catalytic_two_panel_png/full_catalytic_two_panel_png_manifest.tsv")),
        ],
        outputs=[
            ("parallel_integrated_primary_summary", out / "full_parallel_integrated_primary_summary.tsv"),
            ("parallel_integrated_export_qc", out / "full_parallel_integrated_export_qc.tsv"),
        ],
        headers=[
            ("parallel_integrated_primary_summary", "run_label\tmode\tquery\tprotein_id\tfamily\tfinal_decision_class\ttopology_class\tfinal_catalytic_layer_class\tcatalytic_png_path\tintegrated_export_status\tintegrated_export_note"),
        ],
    )


def _execute_stage(ctx: RunContext, stage: Stage, log: TextIO, follow: bool) -> dict[str, Any]:
    if stage.stage_id == "010_preflight":
        return _run_preflight(ctx, log, follow)
    if stage.stage_id == "012_fasta_intake":
        return {"status": "PASS" if _run_fasta_intake(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "014_fasta_batch_plan":
        return {"status": "PASS" if _run_fasta_batch_plan(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "016_backend_job_plan":
        return {"status": "PASS" if _run_backend_job_plan(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "020_import_colabfold":
        return {"status": "PASS" if _run_import_colabfold(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "030_import_foldseek":
        return {"status": "PASS" if _run_import_foldseek(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "040_m06b_pdb":
        return {"status": "PASS" if _run_m06b(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "050_m07b_afsp":
        return {"status": "PASS" if _run_m07b(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "060_m08_reference_panel":
        return {"status": "PASS" if _run_m08(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "070_m09a_p2rank_manifests":
        return {"status": "PASS" if _run_m09a(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "080_m09c_materialize_references":
        return {"status": "PASS" if _run_m09c_materialize(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "090_m09b_resolve_references":
        return {"status": "PASS" if _run_m09b_resolve(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "100_m09d_generate_p2rank_runners":
        return {"status": "PASS" if _run_m09d_generate_runners(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "110_p2rank_query":
        return {"status": "PASS" if _run_p2rank_role(ctx, "query", log, follow) == 0 else "FAIL"}
    if stage.stage_id == "120_p2rank_reference":
        return {"status": "PASS" if _run_p2rank_role(ctx, "reference", log, follow) == 0 else "FAIL"}
    if stage.stage_id == "130_m09e_query_merge":
        return {"status": "PASS" if _run_m09e_query_merge(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "140_m09f_reference_counts":
        return {"status": "PASS" if _run_m09f_reference_counts(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "150_m09g_reference_merge":
        return {"status": "PASS" if _run_m09g_reference_merge(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "151_m09h_deeptmhmm_topology":
        return {"status": "PASS" if _run_m09h_topology(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "152_m09i_topology_pocket_context":
        return {"status": "PASS" if _run_m09i_topology_context(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "153_m09j_catalytic_stack_manifest":
        return {"status": "PASS" if _run_m09j_catalytic_stack_manifest(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "154_m09k_mcsa_resource_cache":
        return {"status": "PASS" if _run_m09k_mcsa_cache(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "155_m09l_uniprot_residue_evidence":
        return {"status": "PASS" if _run_m09l_uniprot_evidence(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "156_m09m_catalytic_candidate_evidence":
        return {"status": "PASS" if _run_m09m_candidate_evidence(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "157_m09n_pairwise_foldseek_job_plan":
        return {"status": "PASS" if _run_m09n_pairwise_job_plan(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "158_m09o_pairwise_alignment_inventory":
        return {"status": "PASS" if _run_m09o_alignment_inventory(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "159_m09p_mcsa_coordinate_rescue":
        return {"status": "PASS" if _run_m09p_coordinate_rescue(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "159q_m09q_catalytic_residue_transfer":
        return {"status": "PASS" if _run_m09q_residue_transfer(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "159r_m09r_catalytic_visual_annotation":
        return {"status": "PASS" if _run_m09r_visual_annotation(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "159s_m09r_validate_catalytic_previsual_outputs":
        return {"status": "PASS" if _run_m09r_validate_catalytic_outputs(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "160_m10a_visual_contract":
        return {"status": "PASS" if _run_m10a(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "165_m10h_catalytic_two_panel_png":
        return {"status": "PASS" if _run_m10h_catalytic_png(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "170_m10b_smoke_package":
        return {"status": "PASS" if _run_m10b(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "180_m10c_all_query_scripts":
        return {"status": "PASS" if _run_m10c(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "190_m10d_visual_qc":
        return {"status": "PASS" if _run_m10d(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "200_m10f_render":
        return {"status": "PASS" if _run_m10f_render(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "210_m11_supporting_audit":
        return {"status": "PASS" if _run_m11(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "220_m12a_primary_decision":
        return {"status": "PASS" if _run_m12a(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "230_m12b_supporting_decision":
        return {"status": "PASS" if _run_m12b(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "240_m12c_combined_summary":
        return {"status": "PASS" if _run_m12c(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "250_m13a_context":
        return {"status": "PASS" if _run_m13a(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "260_m13b_classifier":
        return {"status": "PASS" if _run_m13b(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "270_m13c_mismatch":
        return {"status": "PASS" if _run_m13c(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "280_m13d_ligand_inputs":
        return {"status": "PASS" if _run_m13d_lite(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "290_m13d_ligand_scan":
        return {"status": "PASS" if _run_m13d_scan(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "300_m13e_final_rulebook":
        return {"status": "PASS" if _run_m13e(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "310_m14_export":
        return {"status": "PASS" if _run_m14(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "320_interpretation_ready_export":
        return {"status": "PASS" if _run_interpretation_ready_export(ctx, log, follow) == 0 else "FAIL"}
    if stage.stage_id == "330_m15b_parallel_integrated_export":
        return {"status": "PASS" if _run_m15b_parallel_integrated_export(ctx, log, follow) == 0 else "FAIL"}
    return {"status": "FAIL", "error": f"STAGE_NOT_IMPLEMENTED: {stage.stage_id}"}


def _print_stage_table(results: list[dict[str, str]]) -> None:
    print("RUN_STAGE_TABLE")
    fields = ["stage_id", "status", "detail"]
    print("\t".join(fields))
    for row in results:
        print("\t".join(row.get(field, "") for field in fields))


def _print_stage_input_validations(validations: list[StageValidation]) -> None:
    print("RUN_STAGE_INPUT_VALIDATION")
    fields = ["stage_id", "path", "status", "detail"]
    print("\t".join(fields))
    for validation in validations:
        for check in validation.checks:
            print("\t".join([
                check.stage_id,
                check.path,
                check.status,
                check.detail,
            ]))


def run_guarded_plan_only(
    ctx: RunContext,
    *,
    resume: bool,
    follow: bool,
    start_at: str | None = None,
    stop_after: str | None = None,
) -> int:
    rows, errors, plan_path = initialize_plan(ctx, start_at=start_at, stop_after=stop_after)
    rc = print_plan(ctx, rows, errors, plan_path, start_at=start_at, stop_after=stop_after)
    if rc != 0:
        return rc

    stages = build_stages(ctx)
    stage_ids = [stage.stage_id for stage in stages]
    runtime_errors = _runtime_environment_errors(ctx, stages, rows, start_at=start_at, stop_after=stop_after)
    if runtime_errors:
        _write_status_update(
            ctx,
            status="FAIL",
            current_stage=start_at or "",
            last_pass_stage="",
            next_stage=start_at or "",
            errors=runtime_errors,
        )
        print("RUN_EXECUTION_STATUS\tFAIL")
        print("RUN_EXECUTION_ERROR\tRUNTIME_ENVIRONMENT")
        for err in runtime_errors:
            print(f"RUNTIME_ENVIRONMENT_ERROR\t{err}")
        return 9

    validations, input_errors = validate_stage_window_inputs(ctx, stages, start_at=start_at, stop_after=stop_after)
    _print_stage_input_validations(validations)
    if input_errors:
        _write_status_update(
            ctx,
            status="FAIL",
            current_stage=start_at or "",
            last_pass_stage="",
            next_stage=start_at or "",
            errors=input_errors,
        )
        print("RUN_EXECUTION_STATUS\tFAIL")
        print("RUN_EXECUTION_ERROR\tMISSING_STAGE_INPUTS")
        for err in input_errors:
            print(f"MISSING_STAGE_INPUT\t{err}")
        return 8

    start_idx = stage_ids.index(start_at) if start_at else 0
    stop_idx = stage_ids.index(stop_after) if stop_after else len(stages) - 1

    results: list[dict[str, str]] = []
    last_pass_stage = "000_initialize_run"
    stop_reached = False

    for index, stage in enumerate(stages):
        if index < start_idx:
            results.append({"stage_id": stage.stage_id, "status": "SKIP_BEFORE_START", "detail": ""})
            continue
        if index > stop_idx:
            break
        if stage.stage_id == "000_initialize_run":
            results.append({"stage_id": stage.stage_id, "status": "PASS", "detail": "initialized"})
            if stop_after == stage.stage_id:
                stop_reached = True
                break
            continue
        if not stage.enabled(ctx):
            results.append({"stage_id": stage.stage_id, "status": "SKIP_DISABLED", "detail": ""})
            if stop_after == stage.stage_id:
                stop_reached = True
                break
            continue

        outputs = _stage_outputs(ctx, stage)
        checkpoint = read_checkpoint(ctx.run_root, stage.stage_id)
        checkpoint_pass = (checkpoint or {}).get("status") == "PASS"
        log_path = _stage_log_path(ctx, stage.stage_id)
        next_stage = _next_enabled_stage_id(stages, index, stop_after, ctx)

        if checkpoint_pass and _all_outputs_exist(outputs):
            if resume:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as log:
                    _log(log, follow, f"SKIP_PASS\t{stage.stage_id}")
                _write_status_update(
                    ctx,
                    status="RUNNING",
                    current_stage=stage.stage_id,
                    last_pass_stage=stage.stage_id,
                    next_stage=next_stage,
                    latest_log=log_path,
                )
                last_pass_stage = stage.stage_id
                results.append({"stage_id": stage.stage_id, "status": "SKIP_PASS", "detail": "checkpoint_pass_outputs_exist"})
                if stop_after == stage.stage_id:
                    stop_reached = True
                    break
                continue
            results.append({"stage_id": stage.stage_id, "status": "FAIL", "detail": "OUTPUTS_EXIST_WITHOUT_RESUME"})
            _print_stage_table(results)
            return 4

        if checkpoint_pass and outputs and not _all_outputs_exist(outputs):
            missing = [_rel(ctx, p) for p in outputs if not p.exists()]
            detail = "PASS_CHECKPOINT_MISSING_OUTPUT:" + ",".join(missing)
            write_checkpoint(ctx.run_root, stage.stage_id, {"status": "FAIL", "error": detail})
            results.append({"stage_id": stage.stage_id, "status": "FAIL", "detail": detail})
            _write_status_update(ctx, status="FAIL", current_stage=stage.stage_id, last_pass_stage=last_pass_stage, next_stage=stage.stage_id)
            _print_stage_table(results)
            return 5

        if outputs and _any_outputs_exist(outputs):
            existing = [_rel(ctx, p) for p in outputs if p.exists()]
            detail = "DIRTY_PARTIAL_OUTPUT:" + ",".join(existing)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                _log(log, follow, detail)
            write_checkpoint(ctx.run_root, stage.stage_id, {"status": "FAIL", "error": detail})
            results.append({"stage_id": stage.stage_id, "status": "FAIL", "detail": detail})
            _write_status_update(ctx, status="FAIL", current_stage=stage.stage_id, last_pass_stage=last_pass_stage, next_stage=stage.stage_id, latest_log=log_path)
            _print_stage_table(results)
            return 6

        log_path.parent.mkdir(parents=True, exist_ok=True)
        _write_status_update(ctx, status="RUNNING", current_stage=stage.stage_id, last_pass_stage=last_pass_stage, next_stage=next_stage, latest_log=log_path)
        with log_path.open("w", encoding="utf-8") as log:
            _log(log, follow, f"STAGE_START\t{stage.stage_id}\t{stage.title}")
            try:
                result = _execute_stage(ctx, stage, log, follow)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
                _log(log, follow, "EXCEPTION\t" + result["error"])
            status = str(result.get("status", "FAIL"))
            if status == "PASS" and outputs and not _all_outputs_exist(outputs):
                missing = [_rel(ctx, p) for p in outputs if not p.exists()]
                status = "FAIL"
                result["error"] = "EXPECTED_OUTPUTS_MISSING_AFTER_STAGE:" + ",".join(missing)
            _log(log, follow, f"STAGE_FINISH\t{stage.stage_id}\t{status}")

        checkpoint_payload = {
            "status": status,
            "log": _rel(ctx, log_path),
            "expected_outputs": [_rel(ctx, p) for p in outputs],
        }
        checkpoint_payload.update({k: v for k, v in result.items() if k != "status"})
        write_checkpoint(ctx.run_root, stage.stage_id, checkpoint_payload)

        if status != "PASS":
            detail = str(result.get("error", "stage_failed"))
            results.append({"stage_id": stage.stage_id, "status": "FAIL", "detail": detail})
            _write_status_update(ctx, status="FAIL", current_stage=stage.stage_id, last_pass_stage=last_pass_stage, next_stage=stage.stage_id, latest_log=log_path)
            _print_stage_table(results)
            return 7

        last_pass_stage = stage.stage_id
        results.append({"stage_id": stage.stage_id, "status": "PASS", "detail": "outputs_verified"})
        _write_status_update(ctx, status="RUNNING", current_stage="", last_pass_stage=last_pass_stage, next_stage=next_stage, latest_log=log_path)

        if stop_after == stage.stage_id:
            stop_reached = True
            break

    final_status = "PASS_STOP_AFTER" if stop_after and stop_reached else "PASS"
    _write_status_update(ctx, status=final_status, current_stage="", last_pass_stage=last_pass_stage, next_stage="", latest_log=None)
    _print_stage_table(results)
    print(f"RUN_EXECUTION_STATUS\t{final_status}")
    print(f"RUN_ROOT\t{_rel(ctx, ctx.run_root)}")
    if stop_after:
        print(f"STOP_AFTER\t{stop_after}")
    return 0
