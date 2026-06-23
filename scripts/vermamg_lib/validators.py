from __future__ import annotations

from pathlib import Path

from .config import bool_value, get_nested
from .run_context import RunContext


def validate_config_for_plan(ctx: RunContext) -> list[str]:
    errors: list[str] = []
    if ctx.mode != "full":
        errors.append("V2 orchestrator currently supports analysis.mode=full only.")
    colabfold_mode = str(get_nested(ctx.cfg, "colabfold", "mode", default="") or "").strip().lower()
    foldseek_mode = str(get_nested(ctx.cfg, "foldseek", "mode", default="") or "").strip().lower()
    if colabfold_mode not in {"precomputed", "live"}:
        errors.append("colabfold.mode must be 'precomputed' or 'live'.")
    if foldseek_mode not in {"precomputed_all_hits", "live"}:
        errors.append("foldseek.mode must be 'precomputed_all_hits' or 'live'.")
    backend = str(get_nested(ctx.cfg, "environment", "backend", default="local") or "local").strip().lower()
    if backend not in {"local", "slurm"}:
        errors.append(f"Invalid environment.backend: {backend}")
    backend_submit = bool_value(get_nested(ctx.cfg, "backend_jobs", "submit_jobs", default=False), default=False)
    execution_submit = bool_value(get_nested(ctx.cfg, "execution", "submit_jobs", default=False), default=False)
    if backend_submit or execution_submit:
        errors.append("submit_jobs=true is blocked in Paket2; only dry-run job planning is implemented.")

    # inputs.fasta is always required; FASTA intake/batching drive every mode.
    required_paths = [
        ("inputs.fasta", get_nested(ctx.cfg, "inputs", "fasta")),
    ]
    # Precomputed import paths are only required when importing precomputed data.
    # Live modes generate these tables from compute, so they are not required at
    # plan time (the live adapters validate tools/DBs at run time, allowing
    # plan-on-laptop / run-on-HPC). This keeps the pipeline data/count-agnostic.
    if colabfold_mode == "precomputed":
        required_paths += [
            ("colabfold.query_pdb_dir", get_nested(ctx.cfg, "colabfold", "query_pdb_dir")),
            ("colabfold.collector_manifest", get_nested(ctx.cfg, "colabfold", "collector_manifest")),
            # The precomputed ColabFold importer maps run_ids via foldseek.id_map.
            ("foldseek.id_map", get_nested(ctx.cfg, "foldseek", "id_map")),
        ]
    if foldseek_mode == "precomputed_all_hits":
        required_paths += [
            ("foldseek.pdb_all_hits", get_nested(ctx.cfg, "foldseek", "pdb_all_hits")),
            ("foldseek.afsp_all_hits", get_nested(ctx.cfg, "foldseek", "afsp_all_hits")),
            ("foldseek.id_map", get_nested(ctx.cfg, "foldseek", "id_map")),
        ]
    seen_labels: set[str] = set()
    for label, raw in required_paths:
        if label in seen_labels:
            continue
        seen_labels.add(label)
        if not raw:
            errors.append(f"Missing required path: {label}")
            continue
        path = Path(str(raw))
        if not path.is_absolute():
            path = ctx.project_root / path
        if not path.exists():
            errors.append(f"Required path not found: {label}={path}")
    metadata_raw = get_nested(ctx.cfg, "inputs", "metadata_tsv")
    metadata_required = bool_value(get_nested(ctx.cfg, "metadata", "required", default=False), default=False)
    if metadata_raw:
        metadata_path = Path(str(metadata_raw))
        if not metadata_path.is_absolute():
            metadata_path = ctx.project_root / metadata_path
        if not metadata_path.exists():
            errors.append(f"Optional metadata path not found: inputs.metadata_tsv={metadata_path}")
    elif metadata_required:
        errors.append("Missing required path: inputs.metadata_tsv because metadata.required=true")

    id_policy = str(get_nested(ctx.cfg, "input_intake", "id_policy", default="preserve_first_token") or "")
    if id_policy not in {"preserve_first_token", "slug_first_token"}:
        errors.append(f"Invalid input_intake.id_policy: {id_policy}")
    duplicate_policy = str(get_nested(ctx.cfg, "input_intake", "duplicate_policy", default="fail") or "")
    if duplicate_policy not in {"fail"}:
        errors.append(f"Invalid input_intake.duplicate_policy: {duplicate_policy}")
    invalid_policy = str(get_nested(ctx.cfg, "input_intake", "invalid_sequence_policy", default="fail") or "")
    if invalid_policy not in {"fail", "warn"}:
        errors.append(f"Invalid input_intake.invalid_sequence_policy: {invalid_policy}")
    try:
        min_length = int(get_nested(ctx.cfg, "input_intake", "min_sequence_length", default=1) or 1)
        if min_length < 1:
            errors.append("input_intake.min_sequence_length must be >= 1")
    except (TypeError, ValueError):
        errors.append("input_intake.min_sequence_length must be an integer")

    strategy = str(get_nested(ctx.cfg, "batching", "strategy", default="fixed_size") or "")
    if strategy not in {"fixed_size", "target_batches", "single"}:
        errors.append(f"Invalid batching.strategy: {strategy}")
    try:
        batch_size = int(get_nested(ctx.cfg, "batching", "batch_size", default=128) or 128)
        if batch_size < 1:
            errors.append("batching.batch_size must be >= 1")
    except (TypeError, ValueError):
        errors.append("batching.batch_size must be an integer")
    try:
        target_batches = int(get_nested(ctx.cfg, "batching", "target_batches", default=0) or 0)
        if target_batches < 0:
            errors.append("batching.target_batches must be >= 0")
    except (TypeError, ValueError):
        errors.append("batching.target_batches must be an integer")
    try:
        max_sequences = int(get_nested(ctx.cfg, "batching", "max_sequences", default=0) or 0)
        if max_sequences < 0:
            errors.append("batching.max_sequences must be >= 0")
    except (TypeError, ValueError):
        errors.append("batching.max_sequences must be an integer")
    for label in ["local_threads"]:
        try:
            value = int(get_nested(ctx.cfg, "backend_jobs", label, default=4) or 4)
            if value < 1:
                errors.append(f"backend_jobs.{label} must be >= 1")
        except (TypeError, ValueError):
            errors.append(f"backend_jobs.{label} must be an integer")
    return errors
