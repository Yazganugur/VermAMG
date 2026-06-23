from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import get_nested
from .run_context import RunContext


@dataclass(frozen=True)
class InputSpec:
    path: str
    kind: str = "file"
    required_columns: tuple[str, ...] = ()
    description: str = ""
    relationship: str = ""


@dataclass(frozen=True)
class StageContract:
    stage_id: str
    does: str
    required_inputs: tuple[InputSpec, ...] = ()
    outputs: tuple[str, ...] = ()
    validation_checks: tuple[str, ...] = ()
    example_start: str = ""
    example_stop: str = ""


@dataclass(frozen=True)
class InputCheck:
    stage_id: str
    path: str
    resolved_path: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class StageValidation:
    stage_id: str
    checks: tuple[InputCheck, ...]

    @property
    def errors(self) -> tuple[InputCheck, ...]:
        return tuple(check for check in self.checks if check.status.startswith("FAIL"))


def _cmd(stage_id: str, flag: str) -> str:
    return (
        "python3 scripts/vermamg.py run --config run_configs/<run>.yaml "
        f"--{flag} {stage_id} --resume --follow"
    )


CONTRACTS: dict[str, StageContract] = {
    "012_fasta_intake": StageContract(
        stage_id="012_fasta_intake",
        does="Parses the user FASTA, validates sequence identifiers and residues, joins optional metadata, and writes canonical V2 input manifests.",
        required_inputs=(
            InputSpec("config:inputs.fasta", "file", description="User-provided candidate protein FASTA."),
        ),
        outputs=(
            "00_inputs/fasta/canonical_sequences.faa",
            "00_inputs/manifests/sample_manifest.tsv",
            "00_inputs/metadata/sample_metadata_joined.tsv",
            "00_inputs/qc/input_intake_summary.tsv",
            "00_inputs/qc/metadata_qc.tsv",
        ),
        validation_checks=(
            "FASTA has at least one record",
            "sequence identifiers are unique",
            "sequence characters pass the configured protein alphabet policy",
            "metadata joins by the configured or auto-detected metadata ID column when provided",
        ),
        example_start=_cmd("012_fasta_intake", "start-at"),
        example_stop=_cmd("012_fasta_intake", "stop-after"),
    ),
    "014_fasta_batch_plan": StageContract(
        stage_id="014_fasta_batch_plan",
        does="Creates the optional FASTA batch plan consumed by future local/HPC live ColabFold adapters.",
        required_inputs=(
            InputSpec("00_inputs/fasta/canonical_sequences.faa", "file"),
            InputSpec("00_inputs/manifests/sample_manifest.tsv", "file", ("record_index", "sequence_id", "sequence_length")),
        ),
        outputs=(
            "00_inputs/batches/batch_manifest.tsv",
            "00_inputs/batches/batch_membership.tsv",
            "00_inputs/batches/fasta/",
            "00_inputs/manifests/sample_manifest_with_batches.tsv",
            "00_inputs/qc/batch_plan_summary.tsv",
        ),
        validation_checks=(
            "every manifest sequence_id exists in the canonical FASTA",
            "batching.enabled=false still produces one explicit batch",
            "batch FASTA paths stay under the run directory",
        ),
        example_start=_cmd("014_fasta_batch_plan", "start-at"),
        example_stop=_cmd("014_fasta_batch_plan", "stop-after"),
    ),
    "016_backend_job_plan": StageContract(
        stage_id="016_backend_job_plan",
        does="Creates a backend-neutral dry-run job plan plus local and SLURM dry-run script bundles from the FASTA batch manifest.",
        required_inputs=(
            InputSpec("00_inputs/batches/batch_manifest.tsv", "file", ("batch_id", "batch_fasta", "record_count")),
        ),
        outputs=(
            "00_inputs/job_plan/backend_job_plan.tsv",
            "00_inputs/job_plan/backend_job_dependencies.tsv",
            "00_inputs/job_plan/backend_plan_summary.tsv",
            "00_inputs/job_plan/backend_dry_run_manifest.tsv",
            "submit/local/run_backend_dry_run.sh",
            "submit/slurm/submit_backend_dry_run.sh",
        ),
        validation_checks=(
            "submit_jobs=true is blocked; Paket2 emits dry-run plans only",
            "active backend is local or slurm",
            "job dependency rows are explicit and stable",
            "local and SLURM bundles are generated without starting compute",
        ),
        example_start=_cmd("016_backend_job_plan", "start-at"),
        example_stop=_cmd("016_backend_job_plan", "stop-after"),
    ),
    "020_import_colabfold": StageContract(
        stage_id="020_import_colabfold",
        does="Mode-aware: colabfold.mode=precomputed imports query PDBs; colabfold.mode=live runs ColabFold (00d_run_colabfold.py). Both build the canonical query PDB manifest.",
        required_inputs=(
            InputSpec("config:colabfold.query_pdb_dir", "dir", description="Directory containing one query PDB per run_id."),
            InputSpec("config:colabfold.collector_manifest", "file", description="Collector manifest for the imported query PDB set."),
            InputSpec(
                "config:foldseek.id_map",
                "file",
                ("run_id", "protein_id", "family_label", "habitat_broad"),
                "Canonical run_id/protein_id metadata map.",
            ),
        ),
        outputs=(
            "01_colabfold/query_pdbs/",
            "02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv",
            "02_foldseek/qc/full_query_pdb_manifest_summary.tsv",
        ),
        validation_checks=(
            "query_pdb_dir exists and contains PDB files",
            "id_map has unique run_id values",
            "manifest run_id set matches imported query PDB basenames",
        ),
        example_start=_cmd("020_import_colabfold", "start-at"),
        example_stop=_cmd("020_import_colabfold", "stop-after"),
    ),
    "030_import_foldseek": StageContract(
        stage_id="030_import_foldseek",
        does="Mode-aware: foldseek.mode=precomputed_all_hits imports the all-hit TSVs; foldseek.mode=live runs Foldseek (00e_run_foldseek.py). Both write the canonical run-local tables.",
        required_inputs=(
            InputSpec(
                "config:foldseek.pdb_all_hits",
                "file",
                ("query", "target", "evalue", "bits", "prob", "alntmscore", "qtmscore", "ttmscore", "lddt", "qcov", "tcov", "qlen", "tlen", "batch"),
                "PDB all-hit table in VermAMG canonical narrow schema.",
            ),
            InputSpec(
                "config:foldseek.afsp_all_hits",
                "file",
                ("query", "target", "evalue", "bits", "prob", "alntmscore", "qtmscore", "ttmscore", "lddt", "qcov", "tcov", "qlen", "tlen", "batch"),
                "AFSP all-hit table in VermAMG canonical narrow schema.",
            ),
            InputSpec(
                "config:foldseek.id_map",
                "file",
                ("run_id", "protein_id", "family_label", "habitat_broad"),
                "Canonical run_id/protein_id metadata map.",
            ),
        ),
        outputs=(
            "02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv",
            "02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv",
            "02_foldseek/tables/full/full_manual_id_map.tsv",
            "02_foldseek/qc/full/full_precomputed_foldseek_import_qc.tsv",
        ),
        validation_checks=(
            "PDB and AFSP all-hit query sets match id_map run_id set",
            "all-hit tables have the canonical 14-column schema",
        ),
        example_start=_cmd("030_import_foldseek", "start-at"),
        example_stop=_cmd("030_import_foldseek", "stop-after"),
    ),
    "040_m06b_pdb": StageContract(
        stage_id="040_m06b_pdb",
        does="M06B derives canonical PDB rank1, top5, qTMmax, near-tie, and classified best-hit outputs.",
        required_inputs=(
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv", "file", ("query", "target", "evalue", "bits", "prob", "alntmscore", "qtmscore", "ttmscore", "lddt", "qcov", "tcov", "qlen", "tlen", "batch")),
            InputSpec("02_foldseek/tables/full/full_manual_id_map.tsv", "file", ("run_id", "protein_id", "family_label", "habitat_broad")),
        ),
        outputs=(
            "02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1_classified.tsv",
            "02_foldseek/tables/full/full_vs_pdb_foldseek_top5_hits.tsv",
            "02_foldseek/qc/full/full_vs_pdb_foldseek_canonical_summary.tsv",
        ),
        validation_checks=("all-hit query set equals id_map run_id set", "rank1 output should contain one row per query"),
        example_start=_cmd("040_m06b_pdb", "start-at"),
        example_stop=_cmd("040_m06b_pdb", "stop-after"),
    ),
    "060_m08_reference_panel": StageContract(
        stage_id="060_m08_reference_panel",
        does="M08 selects the integrated primary/supporting reference panel from canonical PDB and AFSP Foldseek outputs.",
        required_inputs=(
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1_classified.tsv", "file", ("query", "target", "pdb_struct_support_class")),
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_top5_hits.tsv", "file", ("query", "target", "qtmscore")),
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_qtmmax_audit.tsv", "file", ("query",)),
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_rank1_vs_qtmmax_audit.tsv", "file", ("query",)),
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_neartie_top5_audit.tsv", "file", ("query",)),
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_best_hit_rank1_classified.tsv", "file", ("query", "target", "afsp_struct_support_class")),
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_top5_hits.tsv", "file", ("query", "target", "qtmscore")),
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_qtmmax_audit.tsv", "file", ("query",)),
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_rank1_vs_qtmmax_audit.tsv", "file", ("query",)),
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_neartie_top5_audit.tsv", "file", ("query",)),
        ),
        outputs=(
            "05_reference_panel/full/full_integrated_reference_decision.tsv",
            "05_reference_panel/full/full_reference_panel_targets.tsv",
            "05_reference_panel/full/full_reference_panel_manual_review.tsv",
        ),
        validation_checks=("decision table has one row per query", "panel table has five rows per query in full665 V1"),
        example_start=_cmd("060_m08_reference_panel", "start-at"),
        example_stop=_cmd("060_m08_reference_panel", "stop-after"),
    ),
    "050_m07b_afsp": StageContract(
        stage_id="050_m07b_afsp",
        does="M07B derives canonical AFSP rank1, top5, qTMmax, near-tie, and classified best-hit outputs.",
        required_inputs=(
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv", "file", ("query", "target", "evalue", "bits", "prob", "alntmscore", "qtmscore", "ttmscore", "lddt", "qcov", "tcov", "qlen", "tlen", "batch")),
            InputSpec("02_foldseek/tables/full/full_manual_id_map.tsv", "file", ("run_id", "protein_id", "family_label", "habitat_broad")),
        ),
        outputs=(
            "02_foldseek/tables/full/full_vs_afsp_foldseek_best_hit_rank1_classified.tsv",
            "02_foldseek/tables/full/full_vs_afsp_foldseek_top5_hits.tsv",
            "02_foldseek/qc/full/full_vs_afsp_foldseek_canonical_summary.tsv",
        ),
        validation_checks=("all-hit query set equals id_map run_id set", "rank1 output should contain one row per query"),
        example_start=_cmd("050_m07b_afsp", "start-at"),
        example_stop=_cmd("050_m07b_afsp", "stop-after"),
    ),
    "070_m09a_p2rank_manifests": StageContract(
        stage_id="070_m09a_p2rank_manifests",
        does="M09A prepares query and unresolved reference manifests for P2Rank.",
        required_inputs=(
            InputSpec(
                "02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv",
                "file",
                ("mode", "batch_id", "run_id", "protein_id", "family_label", "query_pdb_file", "query_pdb_basename", "colabfold_plddt_mean", "colabfold_ptm", "colabfold_struct_conf_class", "colabfold_model_status", "atom_lines", "ca_atoms"),
            ),
            InputSpec(
                "05_reference_panel/full/full_integrated_reference_decision.tsv",
                "file",
                ("query", "protein_id", "family", "primary_reference_layer", "primary_reference_target", "manual_review_level"),
            ),
            InputSpec(
                "05_reference_panel/full/full_reference_panel_targets.tsv",
                "file",
                ("query", "protein_id", "family", "panel_order", "reference_layer", "panel_role", "target", "support_class"),
            ),
        ),
        outputs=(
            "04_p2rank/full/input_manifests/full_p2rank_query_model_manifest.tsv",
            "04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest.tsv",
            "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_pending.tsv",
            "04_p2rank/full/qc/full_p2rank_input_manifest_summary.tsv",
        ),
        validation_checks=(
            "query manifest run_id set equals M08 decision query set",
            "reference panel query set equals M08 decision query set",
            "query_model_pdb paths exist",
        ),
        example_start=_cmd("070_m09a_p2rank_manifests", "start-at"),
        example_stop=_cmd("070_m09a_p2rank_manifests", "stop-after"),
    ),
    "080_m09c_materialize_references": StageContract(
        stage_id="080_m09c_materialize_references",
        does="M09C materializes unique PDB and AFSP reference structures from either trusted full-atom cache inputs or legacy local Foldseek database resources.",
        required_inputs=(
            InputSpec("05_reference_panel/full/full_reference_panel_targets.tsv", "file", ("query", "reference_layer", "target")),
            InputSpec(
                "config:reference_materialization.source_run_root",
                "dir",
                description="Required when reference_materialization.method=full_atom_cache; trusted full-atom reference cache/run root.",
            ),
            InputSpec(
                "config:resources.foldseek_bin",
                "file",
                description="Required only when reference_materialization.method=foldseek_export; Foldseek executable.",
            ),
            InputSpec(
                "config:resources.pdb_foldseek_db",
                "db_prefix",
                description="Required only when reference_materialization.method=foldseek_export; local PDB Foldseek DB prefix.",
            ),
            InputSpec(
                "config:resources.afsp_foldseek_db",
                "db_prefix",
                description="Required only when reference_materialization.method=foldseek_export; local AFSP Foldseek DB prefix.",
            ),
        ),
        outputs=(
            "04_p2rank/full/reference_resolution/full_reference_materialization_report.tsv",
            "04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv",
        ),
        validation_checks=("unique reference targets can be extracted", "materialized files stay under the run directory"),
        example_start=_cmd("080_m09c_materialize_references", "start-at"),
        example_stop=_cmd("080_m09c_materialize_references", "stop-after"),
    ),
    "090_m09b_resolve_references": StageContract(
        stage_id="090_m09b_resolve_references",
        does="M09B resolves materialized reference files back onto panel rows and unique reference structures.",
        required_inputs=(
            InputSpec("04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest.tsv", "file", ("query", "reference_layer", "target")),
            InputSpec("04_p2rank/full/reference_resolution/full_reference_materialization_report.tsv", "file"),
            InputSpec("04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv", "file", ("target", "status", "recovered_file")),
        ),
        outputs=(
            "04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv",
            "04_p2rank/full/input_manifests/full_p2rank_reference_unique_structure_manifest.tsv",
            "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_report.tsv",
            "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_summary.tsv",
        ),
        validation_checks=("primary references should be resolved before P2Rank runner generation", "review-grade fallback statuses must remain visible"),
        example_start=_cmd("090_m09b_resolve_references", "start-at"),
        example_stop=_cmd("090_m09b_resolve_references", "stop-after"),
    ),
    "100_m09d_generate_p2rank_runners": StageContract(
        stage_id="100_m09d_generate_p2rank_runners",
        does="M09D creates local P2Rank runner scripts and audits them before execution.",
        required_inputs=(
            InputSpec("04_p2rank/full/input_manifests/full_p2rank_query_model_manifest.tsv", "file", ("query", "query_model_pdb")),
            InputSpec("04_p2rank/full/input_manifests/full_p2rank_reference_unique_structure_manifest.tsv", "file", ("unique_reference_id", "reference_file_path")),
            InputSpec("config:resources.p2rank_jar", "file", description="P2Rank jar. Java must also be available on PATH or in the execution environment."),
        ),
        outputs=(
            "04_p2rank/full/local_runs/runfull_p2rank_query_models_local.sh",
            "04_p2rank/full/local_runs/runfull_p2rank_reference_resolved_unique_local.sh",
            "04_p2rank/full/full_p2rank_local_run_manifest.tsv",
            "04_p2rank/full/qc/full_p2rank_runner_audit.tsv",
        ),
        validation_checks=("runner audit contains no scratch, sbatch, or unsafe output roots", "expected query/reference manifest row counts are present"),
        example_start=_cmd("100_m09d_generate_p2rank_runners", "start-at"),
        example_stop=_cmd("100_m09d_generate_p2rank_runners", "stop-after"),
    ),
    "110_p2rank_query": StageContract(
        stage_id="110_p2rank_query",
        does="Runs P2Rank for all query structures using the generated local runner.",
        required_inputs=(InputSpec("04_p2rank/full/local_runs/runfull_p2rank_query_models_local.sh", "file"),),
        outputs=(
            "04_p2rank/full/query_models/all/query_p2rank_run_manifest.tsv",
            "04_p2rank/full/query_models/all/query_p2rank_failed.tsv",
        ),
        validation_checks=("all query PDB paths in the runner dataset exist", "failed manifest is empty or explicitly reviewed"),
        example_start=_cmd("110_p2rank_query", "start-at"),
        example_stop=_cmd("110_p2rank_query", "stop-after"),
    ),
    "120_p2rank_reference": StageContract(
        stage_id="120_p2rank_reference",
        does="Runs P2Rank for all resolved unique reference structures.",
        required_inputs=(InputSpec("04_p2rank/full/local_runs/runfull_p2rank_reference_resolved_unique_local.sh", "file"),),
        outputs=(
            "04_p2rank/full/reference_models/resolved_unique/reference_p2rank_run_manifest.tsv",
            "04_p2rank/full/reference_models/resolved_unique/reference_p2rank_failed.tsv",
        ),
        validation_checks=("all reference PDB paths in the runner dataset exist", "failed reference manifest is empty or explicitly reviewed"),
        example_start=_cmd("120_p2rank_reference", "start-at"),
        example_stop=_cmd("120_p2rank_reference", "stop-after"),
    ),
    "130_m09e_query_merge": StageContract(
        stage_id="130_m09e_query_merge",
        does="M09E merges query P2Rank prediction tables and extracts top1 pockets.",
        required_inputs=(InputSpec("04_p2rank/full/query_models/all/query_p2rank_run_manifest.tsv", "file", ("query", "status")),),
        outputs=(
            "04_p2rank/full/query_models/merged_tables/full_query_p2rank_predictions_merged.tsv",
            "04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv",
            "04_p2rank/full/qc/full_query_p2rank_merge_qc_report.tsv",
        ),
        validation_checks=("completed query count matches expected query manifest count", "zero-pocket queries are represented in QC"),
        example_start=_cmd("130_m09e_query_merge", "start-at"),
        example_stop=_cmd("130_m09e_query_merge", "stop-after"),
    ),
    "140_m09f_reference_counts": StageContract(
        stage_id="140_m09f_reference_counts",
        does="M09F summarizes reference P2Rank pocket counts, including CA-only unreliable reference status.",
        required_inputs=(InputSpec("04_p2rank/full/reference_models/resolved_unique/reference_p2rank_run_manifest.tsv", "file", ("unique_reference_id", "status", "pocket_rows")),),
        outputs=(
            "04_p2rank/full/qc/full_p2rank_reference_resolved_unique_pocket_counts.tsv",
            "04_p2rank/full/qc/full_p2rank_reference_zero_pocket_report.tsv",
            "04_p2rank/full/qc/full_p2rank_reference_resolved_unique_qc_report.tsv",
        ),
        validation_checks=("reference P2Rank completion count matches unique reference manifest count",),
        example_start=_cmd("140_m09f_reference_counts", "start-at"),
        example_stop=_cmd("140_m09f_reference_counts", "stop-after"),
    ),
    "150_m09g_reference_merge": StageContract(
        stage_id="150_m09g_reference_merge",
        does="M09G merges reference P2Rank prediction tables and extracts top1/zero-pocket rows.",
        required_inputs=(InputSpec("04_p2rank/full/reference_models/resolved_unique/reference_p2rank_run_manifest.tsv", "file", ("unique_reference_id", "status", "pocket_rows")),),
        outputs=(
            "04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_predictions_merged.tsv",
            "04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv",
            "04_p2rank/full/qc/full_reference_p2rank_merge_qc_report.tsv",
        ),
        validation_checks=("zero-pocket references should be represented in top1 output with zero_pocket_flag",),
        example_start=_cmd("150_m09g_reference_merge", "start-at"),
        example_stop=_cmd("150_m09g_reference_merge", "stop-after"),
    ),
    "160_m10a_visual_contract": StageContract(
        stage_id="160_m10a_visual_contract",
        does="M10A builds the visual overlay input contract linking each query/reference panel row to structures and P2Rank pockets.",
        required_inputs=(
            InputSpec("05_reference_panel/full/full_reference_panel_targets.tsv", "file", ("query", "panel_order", "reference_layer", "target")),
            InputSpec("05_reference_panel/full/full_integrated_reference_decision.tsv", "file", ("query", "primary_reference_layer", "primary_reference_target")),
            InputSpec("04_p2rank/full/input_manifests/full_p2rank_query_model_manifest.tsv", "file", ("query", "query_model_pdb")),
            InputSpec("04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv", "file", ("query", "pocket_rank")),
            InputSpec("04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv", "file", ("query", "target", "reference_file_path")),
            InputSpec("04_p2rank/full/qc/full_p2rank_reference_resolved_unique_pocket_counts.tsv", "file", ("unique_reference_id",)),
            InputSpec("04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv", "file", ("unique_reference_id", "zero_pocket_flag")),
        ),
        outputs=(
            "06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv",
            "06_visual_qc_v6/full/input_manifests/full_visual_overlay_query_summary.tsv",
            "06_visual_qc_v6/full/input_manifests/full_visual_overlay_reference_status_summary.tsv",
            "06_visual_qc_v6/full/qc/full_visual_overlay_input_contract_qc_report.tsv",
        ),
        validation_checks=("visual contract keeps one row per panel row", "CA-only reference status is carried as unreliable evidence"),
        example_start=_cmd("160_m10a_visual_contract", "start-at"),
        example_stop=_cmd("160_m10a_visual_contract", "stop-after"),
    ),
    "170_m10b_smoke_package": StageContract(
        stage_id="170_m10b_smoke_package",
        does="M10B creates a visual smoke package from the M10A visual contract without rendering images.",
        required_inputs=(InputSpec("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv", "file", ("query", "reference_layer", "target", "visual_status")),),
        outputs=(
            "06_visual_qc_v6/full/smoke_package/full_visual_overlay_smoke_manifest.tsv",
            "06_visual_qc_v6/full/smoke_package/full_visual_overlay_smoke.pml",
            "06_visual_qc_v6/full/smoke_package/full_visual_overlay_smoke.cxc",
            "06_visual_qc_v6/full/qc/full_visual_overlay_smoke_qc_report.tsv",
        ),
        validation_checks=("smoke scripts reference existing query/reference structure paths",),
        example_start=_cmd("170_m10b_smoke_package", "start-at"),
        example_stop=_cmd("170_m10b_smoke_package", "stop-after"),
    ),
    "180_m10c_all_query_scripts": StageContract(
        stage_id="180_m10c_all_query_scripts",
        does="M10C creates the all-query PML/CXC script package without rendering images.",
        required_inputs=(InputSpec("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv", "file", ("query", "reference_layer", "target", "visual_status")),),
        outputs=(
            "06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_manifest.tsv",
            "06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_query_summary.tsv",
            "06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_skipped_reference_report.tsv",
            "06_visual_qc_v6/full/qc/full_all_query_visual_script_package_qc_report.tsv",
        ),
        validation_checks=("all generated script paths stay under the run directory",),
        example_start=_cmd("180_m10c_all_query_scripts", "start-at"),
        example_stop=_cmd("180_m10c_all_query_scripts", "stop-after"),
    ),
    "190_m10d_visual_qc": StageContract(
        stage_id="190_m10d_visual_qc",
        does="M10D validates the visual script package paths and per-row readiness flags.",
        required_inputs=(InputSpec("06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_manifest.tsv", "file", ("query", "unique_reference_id", "pymol_script", "chimerax_script")),),
        outputs=(
            "06_visual_qc_v6/full/qc/full_visual_script_package_lite_row_qc.tsv",
            "06_visual_qc_v6/full/qc/full_visual_script_package_lite_qc_report.tsv",
            "06_visual_qc_v6/full/qc/full_visual_script_package_lite_pointer.tsv",
        ),
        validation_checks=("missing PML/CXC/query/reference paths should be zero before downstream use",),
        example_start=_cmd("190_m10d_visual_qc", "start-at"),
        example_stop=_cmd("190_m10d_visual_qc", "stop-after"),
    ),
    "210_m11_supporting_audit": StageContract(
        stage_id="210_m11_supporting_audit",
        does="M11 audits supporting reference agreement/conflict patterns against the selected panel and visual contract.",
        required_inputs=(
            InputSpec("05_reference_panel/full/full_reference_panel_targets.tsv", "file", ("query", "reference_layer", "target")),
            InputSpec("05_reference_panel/full/full_integrated_reference_decision.tsv", "file", ("query", "primary_reference_layer", "primary_reference_target")),
            InputSpec("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv", "file", ("query", "reference_layer", "target", "visual_status")),
            InputSpec("04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv", "file", ("query",)),
            InputSpec("04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv", "file", ("unique_reference_id",)),
        ),
        outputs=("results/full/06_supporting_reference_audit/full_supporting_reference_audit.tsv",),
        validation_checks=("supporting audit query set is a subset of M08 decision queries",),
        example_start=_cmd("210_m11_supporting_audit", "start-at"),
        example_stop=_cmd("210_m11_supporting_audit", "stop-after"),
    ),
    "220_m12a_primary_decision": StageContract(
        stage_id="220_m12a_primary_decision",
        does="M12A creates the primary decision matrix without changing M12 decision logic.",
        required_inputs=(
            InputSpec("05_reference_panel/full/full_integrated_reference_decision.tsv", "file", ("query", "primary_reference_layer", "primary_reference_target")),
            InputSpec("02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1_classified.tsv", "file", ("query", "target")),
            InputSpec("02_foldseek/tables/full/full_vs_afsp_foldseek_best_hit_rank1_classified.tsv", "file", ("query", "target")),
            InputSpec("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv", "file", ("query", "visual_status")),
            InputSpec("06_visual_qc_v6/full/qc/full_visual_script_package_lite_row_qc.tsv", "file", ("query_id",)),
        ),
        outputs=("results/full/07_decision_matrix/full_primary_decision_matrix.tsv",),
        validation_checks=("one primary decision row is expected per M08 decision query",),
        example_start=_cmd("220_m12a_primary_decision", "start-at"),
        example_stop=_cmd("220_m12a_primary_decision", "stop-after"),
    ),
    "250_m13a_context": StageContract(
        stage_id="250_m13a_context",
        does="M13A collects rulebook evidence context from M12/M11/M10 outputs.",
        required_inputs=(
            InputSpec("results/full/07_decision_matrix/full_combined_decision_summary.tsv", "file", ("query",)),
            InputSpec("results/full/06_supporting_reference_audit/full_supporting_reference_audit.tsv", "file", ("query",)),
            InputSpec("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv", "file", ("query",)),
        ),
        outputs=("results/full/08_rulebook_evidence/full_rulebook_context_collector.tsv",),
        validation_checks=("context rows retain query identifiers for downstream M13 modules",),
        example_start=_cmd("250_m13a_context", "start-at"),
        example_stop=_cmd("250_m13a_context", "stop-after"),
    ),
    "310_m14_export": StageContract(
        stage_id="310_m14_export",
        does="M14 builds final full and compact exports from the final decision/rulebook matrices.",
        required_inputs=(
            InputSpec("results/full/08_rulebook_evidence/full_final_rulebook_evidence_matrix.tsv", "file", ("query",)),
            InputSpec("results/full/07_decision_matrix/full_combined_decision_summary.tsv", "file", ("query",)),
        ),
        outputs=("exports/full/full_final_export_full.tsv", "exports/full/full_final_export_compact.tsv"),
        validation_checks=("export query set matches the final rulebook evidence query set",),
        example_start=_cmd("310_m14_export", "start-at"),
        example_stop=_cmd("310_m14_export", "stop-after"),
    ),
    "320_interpretation_ready_export": StageContract(
        stage_id="320_interpretation_ready_export",
        does="Creates the interpretation-ready export layer from M14 outputs.",
        required_inputs=(InputSpec("exports/full/full_final_export_full.tsv", "file", ("query",)),),
        outputs=("exports/full/interpretation_ready/full_final_export_full_interpretation_ready.tsv",),
        validation_checks=("interpretation-ready rows preserve final export query identifiers",),
        example_start=_cmd("320_interpretation_ready_export", "start-at"),
        example_stop=_cmd("320_interpretation_ready_export", "stop-after"),
    ),
    "151_m09h_deeptmhmm_topology": StageContract(
        stage_id="151_m09h_deeptmhmm_topology",
        does="Phase 1 scaffold for DeepTMHMM topology parsing and header normalization. Future logic must handle bracketed genera such as [Eubacterium].",
        required_inputs=(
            InputSpec("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv", "file", ("run_id", "protein_id", "family_label")),
            InputSpec("config:catalytic.deeptmhmm_results_dir", "dir", description="DeepTMHMM raw output directory."),
        ),
        outputs=(
            "results/full/09_topology/full_deeptmhmm_query_topology.tsv",
            "results/full/09_topology/full_deeptmhmm_query_topology_qc.tsv",
        ),
        validation_checks=("query-level topology output must retain every query",),
        example_start=_cmd("151_m09h_deeptmhmm_topology", "start-at"),
        example_stop=_cmd("151_m09h_deeptmhmm_topology", "stop-after"),
    ),
    "152_m09i_topology_pocket_context": StageContract(
        stage_id="152_m09i_topology_pocket_context",
        does="Phase 1 scaffold for topology/pocket context after query P2Rank is merged.",
        required_inputs=(
            InputSpec("results/full/09_topology/full_deeptmhmm_query_topology.tsv", "file", ("query", "topology_class")),
            InputSpec("04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv", "file", ("query",)),
        ),
        outputs=(
            "results/full/09_topology/full_query_pocket_topology_context.tsv",
            "results/full/09_topology/full_query_pocket_topology_context_qc.tsv",
        ),
        validation_checks=("topology context rows must left-join back to all queries",),
        example_start=_cmd("152_m09i_topology_pocket_context", "start-at"),
        example_stop=_cmd("152_m09i_topology_pocket_context", "stop-after"),
    ),
    "153_m09j_catalytic_stack_manifest": StageContract(
        stage_id="153_m09j_catalytic_stack_manifest",
        does="Phase 1 scaffold for the A00-equivalent complete catalytic stack manifest generated from VermAMG inputs.",
        required_inputs=(
            InputSpec("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv", "file", ("run_id", "protein_id")),
            InputSpec("05_reference_panel/full/full_reference_panel_targets.tsv", "file", ("query", "reference_layer", "target")),
            InputSpec("04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv", "file", ("query", "reference_layer", "target", "reference_file_resolution_status")),
            InputSpec("results/full/09_topology/full_query_pocket_topology_context.tsv", "file", ("query",)),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_catalytic_stack_manifest.tsv",
            "results/full/10_catalytic_layer/full_catalytic_stack_manifest_qc.tsv",
        ),
        validation_checks=("query retention and reference alias statuses must remain explicit",),
        example_start=_cmd("153_m09j_catalytic_stack_manifest", "start-at"),
        example_stop=_cmd("153_m09j_catalytic_stack_manifest", "stop-after"),
    ),
    "154_m09k_mcsa_resource_cache": StageContract(
        stage_id="154_m09k_mcsa_resource_cache",
        does="Phase 1 scaffold for M-CSA cache/resource auditing only. No downloads are performed in Phase 1.",
        required_inputs=(
            InputSpec("config:catalytic.mcsa_resource_root", "dir", description="M-CSA local cache root."),
            InputSpec("pipeline_contracts/mcsa_resource_contract.tsv", "file", ("resource_key", "default_filename")),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_mcsa_resource_audit.tsv",
            "results/full/10_catalytic_layer/full_mcsa_resource_audit_qc.tsv",
        ),
        validation_checks=("GOLD M-CSA evidence requires official literature-resource rows in later phases",),
        example_start=_cmd("154_m09k_mcsa_resource_cache", "start-at"),
        example_stop=_cmd("154_m09k_mcsa_resource_cache", "stop-after"),
    ),
    "155_m09l_uniprot_residue_evidence": StageContract(
        stage_id="155_m09l_uniprot_residue_evidence",
        does="Phase 1 scaffold for UniProt residue evidence parsing and ECO tiering.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_catalytic_stack_manifest.tsv", "file", ("query",)),
            InputSpec("config:catalytic.uniprot_resource_root", "dir", description="UniProt residue evidence cache/root."),
            InputSpec("pipeline_contracts/uniprot_residue_evidence_policy.tsv", "file", ("evidence_tier", "interpretation_policy")),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_uniprot_residue_evidence.tsv",
            "results/full/10_catalytic_layer/full_uniprot_residue_evidence_qc.tsv",
        ),
        validation_checks=("experimental/high-confidence evidence must be distinguished from predicted/similarity ECO evidence",),
        example_start=_cmd("155_m09l_uniprot_residue_evidence", "start-at"),
        example_stop=_cmd("155_m09l_uniprot_residue_evidence", "stop-after"),
    ),
    "156_m09m_catalytic_candidate_evidence": StageContract(
        stage_id="156_m09m_catalytic_candidate_evidence",
        does="Phase 1 scaffold for A04-equivalent catalytic candidate evidence generation.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_catalytic_stack_manifest.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_mcsa_resource_audit.tsv", "file", ("resource_key",)),
            InputSpec("results/full/10_catalytic_layer/full_uniprot_residue_evidence.tsv", "file", ("query",)),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long.tsv",
            "results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long_qc.tsv",
        ),
        validation_checks=("transfer-ready filtering must not remove proteins from query-level summaries",),
        example_start=_cmd("156_m09m_catalytic_candidate_evidence", "start-at"),
        example_stop=_cmd("156_m09m_catalytic_candidate_evidence", "stop-after"),
    ),
    "157_m09n_pairwise_foldseek_job_plan": StageContract(
        stage_id="157_m09n_pairwise_foldseek_job_plan",
        does="Phase 1 scaffold for safe pairwise Foldseek easy-search job planning. No jobs are generated or run in Phase 1.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long.tsv", "file", ("query", "target")),
            InputSpec("results/full/10_catalytic_layer/full_catalytic_stack_manifest.tsv", "file", ("query",)),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_pairwise_alignment_job_plan.tsv",
            "results/full/10_catalytic_layer/full_pairwise_alignment_job_plan_qc.tsv",
        ),
        validation_checks=("future implementation must use pairwise easy-search, not failed full convertalis DB conversion",),
        example_start=_cmd("157_m09n_pairwise_foldseek_job_plan", "start-at"),
        example_stop=_cmd("157_m09n_pairwise_foldseek_job_plan", "stop-after"),
    ),
    "158_m09o_pairwise_alignment_inventory": StageContract(
        stage_id="158_m09o_pairwise_alignment_inventory",
        does="Phase 1 scaffold for A07-equivalent pairwise alignment inventory with qstart/qend/tstart/tend/qaln/taln contract.",
        required_inputs=(InputSpec("results/full/10_catalytic_layer/full_pairwise_alignment_job_plan.tsv", "file", ("alignment_pair_id",)),),
        outputs=(
            "results/full/10_catalytic_layer/full_pairwise_alignment_inventory.tsv",
            "results/full/10_catalytic_layer/full_pairwise_alignment_inventory_qc.tsv",
        ),
        validation_checks=("NO_ALIGNMENT_RETURNED_BY_FOLDSEEK must be a flag, not silent row loss",),
        example_start=_cmd("158_m09o_pairwise_alignment_inventory", "start-at"),
        example_stop=_cmd("158_m09o_pairwise_alignment_inventory", "stop-after"),
    ),
    "159_m09p_mcsa_coordinate_rescue": StageContract(
        stage_id="159_m09p_mcsa_coordinate_rescue",
        does="Phase 1 scaffold for required M-CSA original RCSB PDB coordinate validation/rescue.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long.tsv", "file", ("query", "evidence_source")),
            InputSpec("config:catalytic.rcsb_original_pdb_cache", "dir", description="Original RCSB PDB/mmCIF cache."),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_mcsa_original_pdb_coordinate_rescue.tsv",
            "results/full/10_catalytic_layer/full_mcsa_original_pdb_coordinate_rescue_qc.tsv",
        ),
        validation_checks=("future GOLD M-CSA interpretation must require rescue PASS",),
        example_start=_cmd("159_m09p_mcsa_coordinate_rescue", "start-at"),
        example_stop=_cmd("159_m09p_mcsa_coordinate_rescue", "stop-after"),
    ),
    "159q_m09q_catalytic_residue_transfer": StageContract(
        stage_id="159q_m09q_catalytic_residue_transfer",
        does="Phase 1 scaffold for final rescued residue transfer, query summaries, and final catalytic classes.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_pairwise_alignment_inventory.tsv", "file", ("alignment_pair_id",)),
            InputSpec("results/full/10_catalytic_layer/full_mcsa_original_pdb_coordinate_rescue.tsv", "file", ("rescue_status",)),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_candidate_residue_transfer_mapping_mcsa_rescued.tsv",
            "results/full/10_catalytic_layer/full_query_level_catalytic_residue_summary.tsv",
            "results/full/10_catalytic_layer/full_catalytic_residue_class_summary.tsv",
            "results/full/10_catalytic_layer/full_final_catalytic_layer_integration.tsv",
            "results/full/10_catalytic_layer/full_catalytic_residue_transfer_qc.tsv",
        ),
        validation_checks=("all query-level summaries must left-join back to the complete query manifest",),
        example_start=_cmd("159q_m09q_catalytic_residue_transfer", "start-at"),
        example_stop=_cmd("159q_m09q_catalytic_residue_transfer", "stop-after"),
    ),
    "159r_m09r_catalytic_visual_annotation": StageContract(
        stage_id="159r_m09r_catalytic_visual_annotation",
        does="Phase 1 scaffold for render-ready catalytic visual query/residue manifests consumed by M10H.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_catalytic_stack_manifest.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_candidate_residue_transfer_mapping_mcsa_rescued.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_final_catalytic_layer_integration.tsv", "file", ("query",)),
        ),
        outputs=(
            "results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv",
            "results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv",
            "results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest_qc.tsv",
        ),
        validation_checks=("M10H must consume this manifest without recomputing catalytic evidence",),
        example_start=_cmd("159r_m09r_catalytic_visual_annotation", "start-at"),
        example_stop=_cmd("159r_m09r_catalytic_visual_annotation", "stop-after"),
    ),
    "159s_m09r_validate_catalytic_previsual_outputs": StageContract(
        stage_id="159s_m09r_validate_catalytic_previsual_outputs",
        does="Phase 1B read-only validator for precomputed canonical A10G-FIX2 catalytic previsual TSVs.",
        required_inputs=(
            InputSpec("results/full/10_catalytic_layer/full_candidate_residue_transfer_mapping_mcsa_rescued.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_query_level_catalytic_residue_summary.tsv", "file", ("query",)),
            InputSpec(
                "results/full/10_catalytic_layer/full_final_catalytic_layer_integration.tsv",
                "file",
                (
                    "query",
                    "A10G_FIX2_final_catalytic_layer_class",
                    "A10G_FIX2_final_catalytic_layer_interpretation",
                    "A10G_FIX2_visual_display_policy",
                    "complete_retention_status",
                ),
            ),
            InputSpec("results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv", "file", ("query",)),
            InputSpec(
                "results/full/10_catalytic_layer/full_2fua_Tyr_manual_override_audit.tsv",
                "file",
                (
                    "query",
                    "tier",
                    "query_short_id",
                    "reference_id",
                    "reference_chain",
                    "residue_type",
                    "source_residue_oneletter",
                    "transfer_status",
                    "identity_status",
                    "old_A10E_role_class",
                    "new_A10G_role_class",
                    "new_A10G_outcome",
                    "manual_override_reason",
                ),
            ),
            InputSpec(
                "results/full/10_catalytic_layer/full_catalytic_layer_class_transition_to_current.tsv",
                "file",
                (
                    "A10E_strict_final_catalytic_layer_class",
                    "A10G_FIX2_final_catalytic_layer_class",
                    "n",
                ),
            ),
            InputSpec("results/full/10_catalytic_layer/full_current_catalytic_layer_version.tsv", "file", ("key", "value")),
            InputSpec("pipeline_contracts/catalytic_previsual_output_headers.tsv", "file", ("artifact_key", "output_file", "required_columns")),
            InputSpec("pipeline_contracts/catalytic_layer_class_policy.tsv", "file", ("class_key", "canonical_expected_count")),
        ),
        outputs=("results/full/10_catalytic_layer/full_previsual_catalytic_validation_qc.tsv",),
        validation_checks=(
            "read-only validation only: no Foldseek, PyMOL, downloads, coordinate rescue, or biological generation",
            "canonical_catalytic_layer_version must be A10G_FIX2",
            "query, residue-transfer, visual, 2fua override, and final class counts must match canonical expectations",
        ),
        example_start=_cmd("159s_m09r_validate_catalytic_previsual_outputs", "start-at"),
        example_stop=_cmd("159s_m09r_validate_catalytic_previsual_outputs", "stop-after"),
    ),
    "165_m10h_catalytic_two_panel_png": StageContract(
        stage_id="165_m10h_catalytic_two_panel_png",
        does="Phase 1 prototype for catalytic two-panel PNG generation from precomputed visual annotations.",
        required_inputs=(
            InputSpec(
                "results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv",
                "file",
                (
                    "query",
                    "A10G_FIX2_final_catalytic_layer_class",
                    "A10G_FIX2_visual_display_policy",
                    "A10G_FIX2_identity_level_pre_geometry_note",
                ),
            ),
            InputSpec(
                "results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv",
                "file",
                (
                    "query",
                    "query_position_for_visual",
                    "query_residue_for_visual",
                    "visual_show_policy",
                    "default_png_layer",
                    "render_residue_on_query",
                ),
            ),
        ),
        outputs=(
            "06_visual_qc_v6/full/catalytic_two_panel_png/full_catalytic_two_panel_png_manifest.tsv",
            "06_visual_qc_v6/full/catalytic_two_panel_png/full_catalytic_two_panel_png_qc.tsv",
        ),
        validation_checks=("M10H must not parse M-CSA, UniProt, raw alignments, or run coordinate rescue",),
        example_start=_cmd("165_m10h_catalytic_two_panel_png", "start-at"),
        example_stop=_cmd("165_m10h_catalytic_two_panel_png", "stop-after"),
    ),
    "330_m15b_parallel_integrated_export": StageContract(
        stage_id="330_m15b_parallel_integrated_export",
        does="Phase 1 scaffold for parallel integrated structural/topology/catalytic export and report tables.",
        required_inputs=(
            InputSpec("exports/full/full_final_export_full.tsv", "file", ("query",)),
            InputSpec("results/full/09_topology/full_query_pocket_topology_context.tsv", "file", ("query",)),
            InputSpec("results/full/10_catalytic_layer/full_final_catalytic_layer_integration.tsv", "file", ("query",)),
            InputSpec("06_visual_qc_v6/full/catalytic_two_panel_png/full_catalytic_two_panel_png_manifest.tsv", "file", ("query",)),
        ),
        outputs=(
            "results/full/11_integrated_exports/full_parallel_integrated_primary_summary.tsv",
            "results/full/11_integrated_exports/full_parallel_integrated_export_qc.tsv",
        ),
        validation_checks=("M15B must not overwrite existing M14/M15 outputs",),
        example_start=_cmd("330_m15b_parallel_integrated_export", "start-at"),
        example_stop=_cmd("330_m15b_parallel_integrated_export", "stop-after"),
    ),
}


def get_stage_contract(stage_id: str) -> StageContract | None:
    return CONTRACTS.get(stage_id)


def _config_value(cfg: dict[str, Any], dotted: str) -> Any:
    return get_nested(cfg, *dotted.split("."))


def _resolve_spec_path(ctx: RunContext, spec: InputSpec) -> tuple[Path | None, str]:
    if spec.path.startswith("config:"):
        key = spec.path[len("config:"):]
        raw = _config_value(ctx.cfg, key)
        if raw in (None, ""):
            return None, f"empty config value {key}"
        return ctx.project_path(str(raw)), ""
    return ctx.run_path(spec.path), ""


def _path_exists(path: Path, kind: str) -> bool:
    if kind == "file":
        return path.is_file()
    if kind == "dir":
        return path.is_dir()
    if kind == "db_prefix":
        return path.exists() or path.with_suffix(path.suffix + ".dbtype").exists()
    return path.exists()


def _read_header(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        line = handle.readline().rstrip("\n")
    return tuple(line.split("\t")) if line else ()


def _run_relative_key(path: str) -> str:
    return Path(path).as_posix().rstrip("/")


def _reference_materialization_method(ctx: RunContext) -> str:
    raw = get_nested(ctx.cfg, "reference_materialization", "method", default="foldseek_export")
    return str(raw or "foldseek_export").strip().lower()


def _colabfold_mode(ctx: RunContext) -> str:
    return str(get_nested(ctx.cfg, "colabfold", "mode", default="precomputed") or "precomputed").strip().lower()


def _foldseek_mode(ctx: RunContext) -> str:
    return str(get_nested(ctx.cfg, "foldseek", "mode", default="precomputed_all_hits") or "precomputed_all_hits").strip().lower()


def _effective_required_inputs(ctx: RunContext, contract: StageContract) -> tuple[InputSpec, ...]:
    # Live ColabFold/Foldseek modes consume run-local FASTA-intake products
    # instead of precomputed config paths. Tool/DB presence is validated by the
    # live adapters at run time (with explicit errors), so it is not gated here;
    # this keeps plan-on-laptop / run-on-HPC and dry-run planning flows working.
    if contract.stage_id == "020_import_colabfold" and _colabfold_mode(ctx) == "live":
        return (
            InputSpec("00_inputs/batches/batch_manifest.tsv", "file", ("batch_id", "batch_fasta"),
                      "FASTA batch plan produced by 014_fasta_batch_plan."),
            InputSpec("00_inputs/manifests/sample_manifest.tsv", "file", ("sequence_id",),
                      "Canonical sample manifest produced by 012_fasta_intake."),
        )
    if contract.stage_id == "030_import_foldseek" and _foldseek_mode(ctx) == "live":
        return (
            InputSpec("02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv", "file",
                      ("run_id", "query_pdb_file"),
                      "Query PDB manifest produced by 020_import_colabfold (live or precomputed)."),
        )
    if contract.stage_id != "080_m09c_materialize_references":
        return contract.required_inputs
    method = _reference_materialization_method(ctx)
    if method in {"full_atom_cache", "fullatom_cache", "cache_full_atom"}:
        return (
            InputSpec("05_reference_panel/full/full_reference_panel_targets.tsv", "file", ("query", "reference_layer", "target")),
            InputSpec("config:reference_materialization.source_run_root", "dir", description="Trusted full-atom reference cache/run root."),
        )
    return (
        InputSpec("05_reference_panel/full/full_reference_panel_targets.tsv", "file", ("query", "reference_layer", "target")),
        InputSpec("config:resources.foldseek_bin", "file", description="Foldseek executable."),
        InputSpec("config:resources.pdb_foldseek_db", "db_prefix", description="Local PDB Foldseek DB prefix."),
        InputSpec("config:resources.afsp_foldseek_db", "db_prefix", description="Local AFSP Foldseek DB prefix."),
    )


def validate_stage_inputs(
    ctx: RunContext,
    stage_id: str,
    *,
    skip_run_rel_paths: set[str] | None = None,
) -> StageValidation:
    contract = get_stage_contract(stage_id)
    if not contract:
        return StageValidation(stage_id, ())
    skip_run_rel_paths = skip_run_rel_paths or set()
    checks: list[InputCheck] = []
    for spec in _effective_required_inputs(ctx, contract):
        if not spec.path.startswith("config:") and _run_relative_key(spec.path) in skip_run_rel_paths:
            checks.append(InputCheck(stage_id, spec.path, "", "SKIP_PRODUCED_IN_WINDOW", "input is produced by an earlier selected stage"))
            continue
        resolved, problem = _resolve_spec_path(ctx, spec)
        if resolved is None:
            checks.append(InputCheck(stage_id, spec.path, "", "FAIL_MISSING_CONFIG", problem))
            continue
        if not _path_exists(resolved, spec.kind):
            checks.append(InputCheck(stage_id, spec.path, str(resolved), "FAIL_MISSING", f"expected {spec.kind}"))
            continue
        if spec.required_columns:
            if not resolved.is_file():
                checks.append(InputCheck(stage_id, spec.path, str(resolved), "FAIL_NOT_A_FILE", "cannot check columns"))
                continue
            header = _read_header(resolved)
            missing = [name for name in spec.required_columns if name not in header]
            if missing:
                checks.append(InputCheck(stage_id, spec.path, str(resolved), "FAIL_MISSING_COLUMNS", ",".join(missing)))
                continue
        checks.append(InputCheck(stage_id, spec.path, str(resolved), "PASS", ""))
    return StageValidation(stage_id, tuple(checks))


def validate_stage_window_inputs(
    ctx: RunContext,
    stages: list[Any],
    *,
    start_at: str | None = None,
    stop_after: str | None = None,
) -> tuple[list[StageValidation], list[str]]:
    stage_ids = [stage.stage_id for stage in stages]
    start_idx = stage_ids.index(start_at) if start_at else 0
    stop_idx = stage_ids.index(stop_after) if stop_after else len(stages) - 1
    produced_in_window: set[str] = set()
    validations: list[StageValidation] = []
    errors: list[str] = []
    for index, stage in enumerate(stages):
        if index < start_idx or index > stop_idx:
            continue
        if not stage.enabled(ctx):
            continue
        validation = validate_stage_inputs(ctx, stage.stage_id, skip_run_rel_paths=produced_in_window)
        validations.append(validation)
        for check in validation.errors:
            errors.append(f"{check.stage_id}:{check.path}:{check.status}:{check.detail}")
        produced_in_window.update(_run_relative_key(path) for path in stage.expected_outputs)
    return validations, errors


def format_stage_info(stage_id: str) -> str:
    contract = get_stage_contract(stage_id)
    if not contract:
        return f"VERMAMG_STAGE_INFO_V1\nstage_id\t{stage_id}\nstatus\tUNKNOWN_STAGE_CONTRACT"
    lines = [
        "VERMAMG_STAGE_INFO_V1",
        f"stage_id\t{contract.stage_id}",
        f"does\t{contract.does}",
        "required_inputs",
        "path\tkind\trequired_columns\tdescription\trelationship",
    ]
    for spec in contract.required_inputs:
        lines.append(
            "\t".join([
                spec.path,
                spec.kind,
                ",".join(spec.required_columns) if spec.required_columns else "NONE",
                spec.description,
                spec.relationship,
            ])
        )
    lines.extend(["outputs", "path"])
    lines.extend(contract.outputs or ("NONE",))
    lines.extend(["validation_checks", "check"])
    lines.extend(contract.validation_checks or ("NONE",))
    lines.append(f"example_start\t{contract.example_start}")
    lines.append(f"example_stop\t{contract.example_stop}")
    return "\n".join(lines)
