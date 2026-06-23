from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, expand_template, first_text, get_nested, require_text, slugify


RUN_LAYOUT_DIRS = [
    "logs",
    "metadata",
    "state/checkpoints",
    "work",
    "tmp",
    "00_inputs/fasta",
    "00_inputs/metadata",
    "00_inputs/manifests",
    "00_inputs/batches/fasta",
    "00_inputs/job_plan",
    "00_inputs/qc",
    "inputs/fasta",
    "inputs/metadata",
    "01_colabfold",
    "02_foldseek/query_pdb_manifest",
    "02_foldseek/qc",
    "02_foldseek/tables/full",
    "02_foldseek/qc/full",
    "04_p2rank/full/input_manifests",
    "04_p2rank/full/reference_resolution",
    "04_p2rank/full/reference_structures/materialized/pdb",
    "04_p2rank/full/reference_structures/materialized/afsp",
    "04_p2rank/full/local_runs",
    "04_p2rank/full/query_models/all",
    "04_p2rank/full/query_models/merged_tables",
    "04_p2rank/full/reference_models/resolved_unique",
    "04_p2rank/full/reference_models/merged_tables",
    "04_p2rank/full/qc",
    "05_reference_panel/full",
    "06_visual_qc_v6/full/input_manifests",
    "06_visual_qc_v6/full/smoke_package",
    "06_visual_qc_v6/full/all_query_visual_scripts",
    "06_visual_qc_v6/full/catalytic_two_panel_png",
    "06_visual_qc_v6/full/qc",
    "results/full/preflight",
    "results/full/06_supporting_reference_audit",
    "results/full/07_decision_matrix",
    "results/full/08_rulebook_evidence/discovery",
    "results/full/09_topology",
    "results/full/10_catalytic_layer",
    "results/full/11_integrated_exports",
    "resources/mcsa",
    "resources/rcsb_original",
    "submit/local",
    "submit/local/jobs",
    "submit/slurm",
    "submit/slurm/sbatch",
    "submit/logs",
    "exports/full",
    "exports/full/interpretation_ready",
    "pipeline_state/artifacts",
]

WORK_TOP_LEVEL_DIRS = {
    "tmp",
    "00_inputs",
    "01_colabfold",
    "02_foldseek",
    "04_p2rank",
    "05_reference_panel",
    "06_visual_qc_v6",
    "resources",
    "submit",
    "pipeline_state",
}


@dataclass(frozen=True)
class RunContext:
    config_path: Path
    cfg: dict[str, Any]
    project_root: Path
    schema_version: int
    project_name: str
    project_slug: str
    sample_name: str
    sample_slug: str
    run_label: str
    mode: str
    profile: str
    run_root: Path
    layout_version: int

    @classmethod
    def from_config(cls, config_path: str | Path, cfg: dict[str, Any]) -> "RunContext":
        schema_version = int(get_nested(cfg, "schema_version", default=1))
        project_name = first_text(
            get_nested(cfg, "project", "name"),
            cfg.get("project_name"),
            default="VermAMG Project",
        )
        project_slug = first_text(
            get_nested(cfg, "project", "slug"),
            cfg.get("project_slug"),
            default=slugify(project_name),
        )
        project_slug = slugify(project_slug, fallback=slugify(project_name))
        sample_name = first_text(
            get_nested(cfg, "sample", "name"),
            cfg.get("sample_name"),
            default="",
        )
        sample_slug = first_text(
            get_nested(cfg, "sample", "slug"),
            cfg.get("sample_slug"),
            default=slugify(sample_name, fallback="sample") if sample_name else "",
        )
        sample_slug = slugify(sample_slug, fallback="sample") if sample_slug else ""

        mode = first_text(get_nested(cfg, "analysis", "mode"), cfg.get("mode"), default="full")
        profile = first_text(get_nested(cfg, "environment", "profile"), cfg.get("profile"), default="local_wsl")
        explicit_run_label = first_text(get_nested(cfg, "run", "label"), cfg.get("run_label"), default="")
        if schema_version >= 2 and explicit_run_label:
            run_label = slugify(explicit_run_label, fallback=project_slug)
        elif schema_version >= 2:
            today = datetime.now().strftime("%Y%m%d")
            backend = first_text(get_nested(cfg, "environment", "backend"), cfg.get("execution_backend"), default=profile)
            run_label = slugify(f"{today}_{project_slug}_{backend}_{mode}", fallback=project_slug)
        else:
            run_label = require_text(cfg, "run_label")

        default_root = "runs/{project_slug}/{run_label}" if schema_version >= 2 else "runs/{run_label}"
        raw_root = str(get_nested(cfg, "run", "root", default=default_root))
        run_root = Path(expand_template(
            raw_root,
            run_label=run_label,
            mode=mode,
            project_slug=project_slug,
            sample_slug=sample_slug,
            project_name=project_name,
            sample_name=sample_name,
        ))
        if not run_root.is_absolute():
            run_root = PROJECT_ROOT / run_root
        config = Path(config_path)
        if not config.is_absolute():
            config = PROJECT_ROOT / config
        layout_version = int(get_nested(cfg, "run", "layout_version", default=2 if schema_version >= 2 else 1))
        return cls(
            config_path=config,
            cfg=cfg,
            project_root=PROJECT_ROOT,
            schema_version=schema_version,
            project_name=project_name,
            project_slug=project_slug,
            sample_name=sample_name,
            sample_slug=sample_slug,
            run_label=run_label,
            mode=mode,
            profile=profile,
            run_root=run_root,
            layout_version=layout_version,
        )

    def rel_to_project(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return str(path)

    def run_path(self, relative: str | Path) -> Path:
        rel = Path(relative)
        if self.layout_version >= 2 and rel.parts and rel.parts[0] in WORK_TOP_LEVEL_DIRS:
            return self.run_root / "work" / rel
        return self.run_root / rel

    def project_path(self, raw: str | Path) -> Path:
        path = Path(str(raw))
        if not path.is_absolute():
            path = self.project_root / path
        return path

    def ensure_layout(self) -> None:
        self.run_root.mkdir(parents=True, exist_ok=True)
        for rel in RUN_LAYOUT_DIRS:
            self.run_path(rel).mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.config_path, self.run_path("metadata/run_config.yaml"))
        self.run_path("metadata/run_identity.tsv").write_text(
            "\n".join([
                "key\tvalue",
                f"schema_version\t{self.schema_version}",
                f"project_name\t{self.project_name}",
                f"project_slug\t{self.project_slug}",
                f"sample_name\t{self.sample_name}",
                f"sample_slug\t{self.sample_slug}",
                f"run_label\t{self.run_label}",
                f"mode\t{self.mode}",
                f"profile\t{self.profile}",
                f"layout_version\t{self.layout_version}",
                f"run_root\t{self.rel_to_project(self.run_root)}",
                f"work_root\t{self.rel_to_project(self.run_path('work'))}",
                f"results_root\t{self.rel_to_project(self.run_path('results'))}",
                f"exports_root\t{self.rel_to_project(self.run_path('exports'))}",
                "",
            ]),
            encoding="utf-8",
        )
