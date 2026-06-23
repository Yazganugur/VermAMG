from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import bool_value, get_nested
from .run_context import RunContext
from .state import read_checkpoint


@dataclass(frozen=True)
class Stage:
    stage_id: str
    title: str
    enabled_key: str | None
    expected_outputs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    heavy: bool = False
    v1_status: str = "PLANNED"
    notes: str = ""
    default_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def enabled(self, ctx: RunContext) -> bool:
        if not self.enabled_key:
            return True
        value = get_nested(ctx.cfg, *self.enabled_key.split("."), default=self.default_enabled)
        return bool_value(value, default=self.default_enabled)


def build_stages(ctx: RunContext) -> list[Stage]:
    mode = ctx.mode
    return [
        Stage("000_initialize_run", "Create isolated run directory", None, ("metadata/run_config.yaml", "state/status.json")),
        Stage("010_preflight", "Validate config and required inputs", None, ("results/full/preflight/preflight_summary.tsv",)),
        Stage("012_fasta_intake", "Parse FASTA and metadata into canonical sample manifest", "stages.input_intake", ("00_inputs/fasta/canonical_sequences.faa", "00_inputs/manifests/sample_manifest.tsv", "00_inputs/metadata/sample_metadata_joined.tsv", "00_inputs/qc/input_intake_summary.tsv", "00_inputs/qc/metadata_qc.tsv")),
        Stage("014_fasta_batch_plan", "Create optional FASTA batch plan", "stages.batch_plan", ("00_inputs/batches/batch_manifest.tsv", "00_inputs/batches/batch_membership.tsv", "00_inputs/manifests/sample_manifest_with_batches.tsv", "00_inputs/qc/batch_plan_summary.tsv")),
        Stage("016_backend_job_plan", "Create local/SLURM backend dry-run job plan", "stages.backend_job_plan", ("00_inputs/job_plan/backend_job_plan.tsv", "00_inputs/job_plan/backend_job_dependencies.tsv", "00_inputs/job_plan/backend_plan_summary.tsv", "00_inputs/job_plan/backend_dry_run_manifest.tsv", "submit/local/run_backend_dry_run.sh", "submit/slurm/submit_backend_dry_run.sh")),
        Stage("020_import_colabfold", "Import or live-generate query PDBs (colabfold.mode)", "stages.import_colabfold", ("01_colabfold/query_pdbs", "02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv", "02_foldseek/qc/full_query_pdb_manifest_summary.tsv"), notes="colabfold.mode=precomputed imports query PDBs; colabfold.mode=live runs ColabFold (00d_run_colabfold.py)."),
        Stage("030_import_foldseek", "Import or live-generate Foldseek all-hit tables (foldseek.mode)", "stages.import_foldseek", ("02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv", "02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv", "02_foldseek/tables/full/full_manual_id_map.tsv", "02_foldseek/qc/full/full_precomputed_foldseek_import_qc.tsv"), notes="foldseek.mode=precomputed_all_hits imports tables; foldseek.mode=live runs Foldseek (00e_run_foldseek.py)."),
        Stage("040_m06b_pdb", "M06B PDB canonical best-hit outputs", "stages.m06b_m07b", ("02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1.tsv", "02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1_classified.tsv", "02_foldseek/tables/full/full_vs_pdb_foldseek_top5_hits.tsv", "02_foldseek/tables/full/full_vs_pdb_foldseek_qtmmax_audit.tsv", "02_foldseek/tables/full/full_vs_pdb_foldseek_rank1_vs_qtmmax_audit.tsv", "02_foldseek/tables/full/full_vs_pdb_foldseek_neartie_top5_audit.tsv", "02_foldseek/qc/full/full_vs_pdb_foldseek_canonical_summary.tsv", "02_foldseek/qc/full/full_vs_pdb_foldseek_canonical_pointer.tsv")),
        Stage("050_m07b_afsp", "M07B AFSP canonical best-hit outputs", "stages.m06b_m07b", ("02_foldseek/tables/full/full_vs_afsp_foldseek_best_hit_rank1.tsv", "02_foldseek/tables/full/full_vs_afsp_foldseek_best_hit_rank1_classified.tsv", "02_foldseek/tables/full/full_vs_afsp_foldseek_top5_hits.tsv", "02_foldseek/tables/full/full_vs_afsp_foldseek_qtmmax_audit.tsv", "02_foldseek/tables/full/full_vs_afsp_foldseek_rank1_vs_qtmmax_audit.tsv", "02_foldseek/tables/full/full_vs_afsp_foldseek_neartie_top5_audit.tsv", "02_foldseek/qc/full/full_vs_afsp_foldseek_canonical_summary.tsv", "02_foldseek/qc/full/full_vs_afsp_foldseek_canonical_pointer.tsv")),
        Stage("060_m08_reference_panel", "M08 integrated reference panel", "stages.m08", ("05_reference_panel/full/full_integrated_reference_decision.tsv", "05_reference_panel/full/full_reference_panel_targets.tsv", "05_reference_panel/full/full_reference_panel_manual_review.tsv", "05_reference_panel/full/full_reference_panel_summary.tsv", "05_reference_panel/full/full_reference_panel_pointer.tsv")),
        Stage("070_m09a_p2rank_manifests", "M09A P2Rank input manifests", "stages.m09", ("04_p2rank/full/input_manifests/full_p2rank_query_model_manifest.tsv", "04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest.tsv", "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_pending.tsv", "04_p2rank/full/qc/full_p2rank_input_manifest_summary.tsv", "04_p2rank/full/qc/full_p2rank_input_manifest_pointer.tsv")),
        Stage("080_m09c_materialize_references", "M09C materialize reference structures", "stages.m09", ("04_p2rank/full/reference_resolution/full_reference_materialization_report.tsv", "04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv"), heavy=True),
        Stage("090_m09b_resolve_references", "M09B resolve materialized references", "stages.m09", ("04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv", "04_p2rank/full/input_manifests/full_p2rank_reference_unique_structure_manifest.tsv", "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_report.tsv", "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_summary.tsv", "04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_pointer.tsv")),
        Stage("100_m09d_generate_p2rank_runners", "M09D generate P2Rank local runners", "stages.p2rank", ("04_p2rank/full/local_runs/runfull_p2rank_query_models_local.sh", "04_p2rank/full/local_runs/runfull_p2rank_reference_resolved_unique_local.sh", "04_p2rank/full/full_p2rank_local_run_manifest.tsv", "04_p2rank/full/qc/full_p2rank_runner_audit.tsv")),
        Stage("110_p2rank_query", "Run query P2Rank", "stages.p2rank", ("04_p2rank/full/query_models/all/query_p2rank_run_manifest.tsv", "04_p2rank/full/query_models/all/query_p2rank_failed.tsv"), heavy=True),
        Stage("120_p2rank_reference", "Run reference P2Rank", "stages.p2rank", ("04_p2rank/full/reference_models/resolved_unique/reference_p2rank_run_manifest.tsv", "04_p2rank/full/reference_models/resolved_unique/reference_p2rank_failed.tsv"), heavy=True),
        Stage("130_m09e_query_merge", "M09E merge query P2Rank", "stages.p2rank", ("04_p2rank/full/query_models/merged_tables/full_query_p2rank_predictions_merged.tsv", "04_p2rank/full/query_models/merged_tables/full_query_p2rank_residues_merged.tsv", "04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv", "04_p2rank/full/qc/full_query_p2rank_merge_qc_report.tsv")),
        Stage("140_m09f_reference_counts", "M09F reference pocket counts", "stages.p2rank", ("04_p2rank/full/qc/full_p2rank_reference_resolved_unique_pocket_counts.tsv", "04_p2rank/full/qc/full_p2rank_reference_zero_pocket_report.tsv", "04_p2rank/full/qc/full_p2rank_reference_resolved_unique_qc_report.tsv")),
        Stage("150_m09g_reference_merge", "M09G merge reference P2Rank", "stages.p2rank", ("04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_predictions_merged.tsv", "04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_residues_merged.tsv", "04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv", "04_p2rank/full/qc/full_reference_p2rank_merge_qc_report.tsv")),
        Stage("151_m09h_deeptmhmm_topology", "M09H DeepTMHMM topology table", "stages.m09h_m09r_catalytic_previsual", ("results/full/09_topology/full_deeptmhmm_query_topology.tsv", "results/full/09_topology/full_deeptmhmm_query_topology_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; no topology parsing logic yet.", default_enabled=False),
        Stage("152_m09i_topology_pocket_context", "M09I topology/pocket context", "stages.m09h_m09r_catalytic_previsual", ("results/full/09_topology/full_query_pocket_topology_context.tsv", "results/full/09_topology/full_query_pocket_topology_context_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; no topology overlap logic yet.", default_enabled=False),
        Stage("153_m09j_catalytic_stack_manifest", "M09J catalytic stack manifest", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_catalytic_stack_manifest.tsv", "results/full/10_catalytic_layer/full_catalytic_stack_manifest_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; A00-equivalent contract only.", default_enabled=False),
        Stage("154_m09k_mcsa_resource_cache", "M09K M-CSA cache/resource audit", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_mcsa_resource_audit.tsv", "results/full/10_catalytic_layer/full_mcsa_resource_audit_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; cache-check only, no downloads.", default_enabled=False),
        Stage("155_m09l_uniprot_residue_evidence", "M09L UniProt residue evidence", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_uniprot_residue_evidence.tsv", "results/full/10_catalytic_layer/full_uniprot_residue_evidence_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; no UniProt parsing logic yet.", default_enabled=False),
        Stage("156_m09m_catalytic_candidate_evidence", "M09M catalytic candidate evidence", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long.tsv", "results/full/10_catalytic_layer/full_candidate_catalytic_reference_evidence_long_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; A04-equivalent contract only.", default_enabled=False),
        Stage("157_m09n_pairwise_foldseek_job_plan", "M09N pairwise Foldseek job plan", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_pairwise_alignment_job_plan.tsv", "results/full/10_catalytic_layer/full_pairwise_alignment_job_plan_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; no real Foldseek jobs.", default_enabled=False),
        Stage("158_m09o_pairwise_alignment_inventory", "M09O pairwise alignment inventory", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_pairwise_alignment_inventory.tsv", "results/full/10_catalytic_layer/full_pairwise_alignment_inventory_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; A07-equivalent contract only.", default_enabled=False),
        Stage("159_m09p_mcsa_coordinate_rescue", "M09P M-CSA original-PDB coordinate rescue", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_mcsa_original_pdb_coordinate_rescue.tsv", "results/full/10_catalytic_layer/full_mcsa_original_pdb_coordinate_rescue_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; no coordinate rescue logic yet.", default_enabled=False),
        Stage("159q_m09q_catalytic_residue_transfer", "M09Q catalytic residue transfer and classes", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_candidate_residue_transfer_mapping_mcsa_rescued.tsv", "results/full/10_catalytic_layer/full_query_level_catalytic_residue_summary.tsv", "results/full/10_catalytic_layer/full_catalytic_residue_class_summary.tsv", "results/full/10_catalytic_layer/full_final_catalytic_layer_integration.tsv", "results/full/10_catalytic_layer/full_catalytic_residue_transfer_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; A08/A09-equivalent contracts only.", default_enabled=False),
        Stage("159r_m09r_catalytic_visual_annotation", "M09R catalytic visual annotation manifest", "stages.m09h_m09r_catalytic_previsual", ("results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv", "results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv", "results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; produces precomputed visual manifests required by M10H.", default_enabled=False),
        Stage("159s_m09r_validate_catalytic_previsual_outputs", "M09R validate previsual catalytic outputs", "stages.m09r_validate_catalytic_previsual_outputs", ("results/full/10_catalytic_layer/full_previsual_catalytic_validation_qc.tsv",), v1_status="VALIDATOR_SCAFFOLD", notes="Default-disabled Phase 1B validator for precomputed A10G-FIX2 catalytic TSVs; no biological generation.", default_enabled=False),
        Stage("160_m10a_visual_contract", "M10A visual overlay input contract", "stages.m10a_d", ("06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv", "06_visual_qc_v6/full/input_manifests/full_visual_overlay_query_summary.tsv", "06_visual_qc_v6/full/input_manifests/full_visual_overlay_reference_status_summary.tsv", "06_visual_qc_v6/full/qc/full_visual_overlay_input_contract_qc_report.tsv")),
        Stage("165_m10h_catalytic_two_panel_png", "M10H catalytic two-panel PNG prototype", "stages.m10h_catalytic_two_panel_png", ("06_visual_qc_v6/full/catalytic_two_panel_png/full_catalytic_two_panel_png_manifest.tsv", "06_visual_qc_v6/full/catalytic_two_panel_png/full_catalytic_two_panel_png_qc.tsv"), heavy=True, v1_status="PROTOTYPE", notes="Default-disabled Phase 1 prototype; consumes only M09R catalytic visual query/residue manifests.", default_enabled=False),
        Stage("170_m10b_smoke_package", "M10B smoke visual package", "stages.m10a_d", ("06_visual_qc_v6/full/smoke_package/full_visual_overlay_smoke_manifest.tsv", "06_visual_qc_v6/full/smoke_package/full_visual_overlay_smoke.pml", "06_visual_qc_v6/full/smoke_package/full_visual_overlay_smoke.cxc", "06_visual_qc_v6/full/qc/full_visual_overlay_smoke_qc_report.tsv")),
        Stage("180_m10c_all_query_scripts", "M10C all-query visual scripts", "stages.m10a_d", ("06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_manifest.tsv", "06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_query_summary.tsv", "06_visual_qc_v6/full/all_query_visual_scripts/full_all_query_visual_script_skipped_reference_report.tsv", "06_visual_qc_v6/full/qc/full_all_query_visual_script_package_qc_report.tsv")),
        Stage("190_m10d_visual_qc", "M10D visual script QC", "stages.m10a_d", ("06_visual_qc_v6/full/qc/full_visual_script_package_lite_row_qc.tsv", "06_visual_qc_v6/full/qc/full_visual_script_package_lite_qc_report.tsv", "06_visual_qc_v6/full/qc/full_visual_script_package_lite_pointer.tsv")),
        Stage("200_m10f_render", "M10F render overlays", "stages.m10f_render", ("06_visual_qc_v6/full/rendered_png/full_rendered_png_manifest.tsv", "06_visual_qc_v6/full/rendered_png/full_rendered_png_qc.tsv"), heavy=True, notes="Requires PyMOL Apptainer container."),
        Stage("210_m11_supporting_audit", "M11 supporting reference audit", "stages.m11", ("results/full/06_supporting_reference_audit/full_supporting_reference_audit.tsv",)),
        Stage("220_m12a_primary_decision", "M12A primary decision matrix", "stages.m12", ("results/full/07_decision_matrix/full_primary_decision_matrix.tsv",)),
        Stage("230_m12b_supporting_decision", "M12B supporting reference decision matrix", "stages.m12", ("results/full/07_decision_matrix/full_supporting_reference_decision_matrix.tsv",)),
        Stage("240_m12c_combined_summary", "M12C combined decision summary", "stages.m12", ("results/full/07_decision_matrix/full_combined_decision_summary.tsv",)),
        Stage("250_m13a_context", "M13A rulebook context", "stages.m13", ("results/full/08_rulebook_evidence/full_rulebook_context_collector.tsv",)),
        Stage("260_m13b_classifier", "M13B existing rulebook classifier", "stages.m13", ("results/full/08_rulebook_evidence/full_existing_rulebook_classified.tsv",)),
        Stage("270_m13c_mismatch", "M13C coverage mismatch detector", "stages.m13", ("results/full/08_rulebook_evidence/full_rulebook_mismatch_reasons.tsv",)),
        Stage("280_m13d_ligand_inputs", "M13D-lite ligand scan inputs", "stages.m13", ("results/full/08_rulebook_evidence/discovery/full_m13d_primary_supporting_reference_ligand_scan_map.tsv",)),
        Stage("290_m13d_ligand_scan", "M13D ligand/cofactor context scan", "stages.m13", ("results/full/08_rulebook_evidence/full_ligand_cofactor_primary_context.tsv",)),
        Stage("300_m13e_final_rulebook", "M13E final rulebook evidence matrix", "stages.m13", ("results/full/08_rulebook_evidence/full_final_rulebook_evidence_matrix.tsv",)),
        Stage("310_m14_export", "M14 final export", "stages.m14", ("exports/full/full_final_export_full.tsv", "exports/full/full_final_export_compact.tsv")),
        Stage("320_interpretation_ready_export", "Interpretation-ready export", "stages.interpretation_ready_export", ("exports/full/interpretation_ready/full_final_export_full_interpretation_ready.tsv",)),
        Stage("330_m15b_parallel_integrated_export", "M15B parallel integrated topology/catalytic export", "stages.m15b_parallel_integrated_export", ("results/full/11_integrated_exports/full_parallel_integrated_primary_summary.tsv", "results/full/11_integrated_exports/full_parallel_integrated_export_qc.tsv"), v1_status="SCAFFOLD", notes="Default-disabled Phase 1 scaffold; does not overwrite M14/M15.", default_enabled=False),
    ]


def stage_window_errors(ctx: RunContext, *, start_at: str | None = None, stop_after: str | None = None) -> list[str]:
    stages = build_stages(ctx)
    stage_ids = [stage.stage_id for stage in stages]
    errors: list[str] = []
    if start_at and start_at not in stage_ids:
        errors.append(f"UNKNOWN_START_AT_STAGE:{start_at}")
    if stop_after and stop_after not in stage_ids:
        errors.append(f"UNKNOWN_STOP_AFTER_STAGE:{stop_after}")
    if not errors and start_at and stop_after and stage_ids.index(start_at) > stage_ids.index(stop_after):
        errors.append(f"START_AT_AFTER_STOP_AFTER:{start_at}>{stop_after}")
    return errors


def stage_plan_rows(
    ctx: RunContext,
    *,
    start_at: str | None = None,
    stop_after: str | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    stages = build_stages(ctx)
    stage_ids = [stage.stage_id for stage in stages]
    start_idx = stage_ids.index(start_at) if start_at in stage_ids else 0
    stop_idx = stage_ids.index(stop_after) if stop_after in stage_ids else len(stages) - 1
    for idx, stage in enumerate(stages, start=1):
        zero_idx = idx - 1
        enabled = stage.enabled(ctx)
        outputs = [ctx.run_path(rel) for rel in stage.expected_outputs]
        output_state = "NO_EXPECTED_OUTPUTS"
        if outputs:
            exists_n = sum(1 for path in outputs if path.exists())
            output_state = f"{exists_n}/{len(outputs)}"
        checkpoint = read_checkpoint(ctx.run_root, stage.stage_id)
        ckpt_status = str((checkpoint or {}).get("status", "NONE"))
        resume_action = "DISABLED"
        if start_at and zero_idx < start_idx:
            resume_action = "SKIP_BEFORE_START"
        elif stop_after and zero_idx > stop_idx:
            resume_action = "SKIP_AFTER_STOP"
        elif enabled:
            if ckpt_status == "PASS" and outputs and all(path.exists() for path in outputs):
                resume_action = "SKIP_PASS"
            elif ckpt_status != "PASS" and outputs and any(path.exists() for path in outputs):
                resume_action = "DIRTY_PARTIAL_OUTPUT"
            else:
                resume_action = "RUN_PENDING"
        rows.append({
            "order": str(idx),
            "stage_id": stage.stage_id,
            "enabled": "YES" if enabled else "NO",
            "heavy": "YES" if stage.heavy else "NO",
            "checkpoint_status": ckpt_status,
            "expected_outputs_present": output_state,
            "resume_action": resume_action,
            "title": stage.title,
            "notes": stage.notes,
        })
    return rows
