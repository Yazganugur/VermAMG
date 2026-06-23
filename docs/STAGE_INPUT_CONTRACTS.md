# VermAMG Stage Input Contracts

This document describes the V2 run-config stage entry points. Paths are
relative to `runs/{project_slug}/{run_label}/`; paths such as `00_inputs/...`,
`02_foldseek/...`, and `04_p2rank/...` are resolved under `work/` by the V2
run context. `config:` paths are read from the YAML config and resolved
relative to the repository.

The partial-run pattern is:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at <stage_id> --stop-after <stage_id> --resume --follow
```

Use `stage-info` for the machine-readable summary:

```bash
python3 scripts/vermamg.py stage-info --stage 070_m09a_p2rank_manifests
```

Use `validate-stage` to check one entry point without running it:

```bash
python3 scripts/vermamg.py validate-stage --config run_configs/<run>.yaml --stage 070_m09a_p2rank_manifests
```

## 012_fasta_intake

What it does: parses the user FASTA, validates sequence identifiers and
protein characters, joins optional metadata, and writes the canonical V2 sample
manifest.

Required inputs:

- `config:inputs.fasta`: user-provided candidate protein FASTA.
- `config:inputs.metadata_tsv`: optional metadata TSV. If provided, the join key
  is `metadata.id_column` or auto-detected from `protein_id`, `sequence_id`,
  `run_id`, `query`, `id`.

Expected relationships:

- FASTA records must have non-empty first-token IDs.
- Sequence IDs must be unique under the configured `input_intake.id_policy`.
- Metadata can be absent; if present, matched/missing/extra rows are reported.

Outputs:

- `00_inputs/fasta/canonical_sequences.faa`
- `00_inputs/manifests/sample_manifest.tsv`
- `00_inputs/metadata/sample_metadata_joined.tsv`
- `00_inputs/qc/input_intake_summary.tsv`
- `00_inputs/qc/metadata_qc.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 012_fasta_intake --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 012_fasta_intake --resume --follow
```

## 014_fasta_batch_plan

What it does: converts the canonical sample manifest into an explicit batch
plan. `batching.enabled=false` means "do not split", but still creates one
batch so live local/HPC adapters can consume the same contract.

Required inputs:

- `00_inputs/fasta/canonical_sequences.faa`
- `00_inputs/manifests/sample_manifest.tsv`: columns `record_index`,
  `sequence_id`, `sequence_length`.

Expected relationships:

- Every `sequence_id` in the manifest must exist in the canonical FASTA.
- Batch FASTA files stay under the run-local `work/00_inputs/batches/fasta/`
  directory.

Outputs:

- `00_inputs/batches/batch_manifest.tsv`
- `00_inputs/batches/batch_membership.tsv`
- `00_inputs/batches/fasta/*.faa`
- `00_inputs/manifests/sample_manifest_with_batches.tsv`
- `00_inputs/qc/batch_plan_summary.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 014_fasta_batch_plan --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 014_fasta_batch_plan --resume --follow
```

## 016_backend_job_plan

What it does: creates a backend-neutral dry-run job plan from the FASTA batch
manifest. It writes one active backend plan plus local and SLURM dry-run script
bundles. This stage does not execute ColabFold, does not execute Foldseek, and
does not call `sbatch`.

Required inputs:

- `00_inputs/batches/batch_manifest.tsv`: columns `batch_id`, `batch_fasta`,
  `record_count`.

Expected relationships:

- One ColabFold dry-run job is planned per FASTA batch.
- One collect job depends on all ColabFold batch jobs.
- Foldseek PDB and AFSP dry-run jobs depend on the collect job.
- `backend_jobs.submit_jobs: true` is blocked in Paket2.

Outputs:

- `00_inputs/job_plan/backend_job_plan.tsv`
- `00_inputs/job_plan/backend_job_dependencies.tsv`
- `00_inputs/job_plan/backend_plan_summary.tsv`
- `00_inputs/job_plan/backend_dry_run_manifest.tsv`
- `submit/local/run_backend_dry_run.sh`
- `submit/slurm/submit_backend_dry_run.sh`
- `submit/slurm/sbatch/*.sbatch`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 016_backend_job_plan --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 016_backend_job_plan --resume --follow
```

## 020_import_colabfold

What it does: mode-aware. `colabfold.mode=precomputed` imports precomputed query
PDB files; `colabfold.mode=live` runs ColabFold (`00d_run_colabfold.py`) over the
FASTA batches. Both build the same canonical query PDB manifest.

Required inputs (`colabfold.mode=precomputed`):

- `config:colabfold.query_pdb_dir`: directory containing query PDB files.
- `config:colabfold.collector_manifest`: collector manifest.
- `config:foldseek.id_map`: columns `run_id`, `protein_id`, `family_label`,
  `habitat_broad`.

Required inputs (`colabfold.mode=live`):

- `00_inputs/batches/batch_manifest.tsv` (from 014): columns `batch_id`,
  `batch_fasta`.
- `00_inputs/manifests/sample_manifest.tsv` (from 012): column `sequence_id`.
- `colabfold.cmd` available on the active backend (GPU recommended). Tool
  presence is validated by the adapter at run time. Live mode fills real
  `colabfold_plddt_mean`/`colabfold_ptm` from ColabFold score JSONs.

Expected relationships:

- One query PDB resolves for each `run_id` (= FASTA record id in live mode).
- `run_id` values should be unique.

Outputs:

- `01_colabfold/query_pdbs/`
- `02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv`
- `02_foldseek/qc/full_query_pdb_manifest_summary.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 020_import_colabfold --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 020_import_colabfold --resume --follow
```

## 030_import_foldseek

What it does: mode-aware. `foldseek.mode=precomputed_all_hits` imports precomputed
PDB and AFSP Foldseek all-hit tables; `foldseek.mode=live` runs Foldseek
(`00e_run_foldseek.py`: `createdb -> search -> convertalis`) to generate them.
Both write the same canonical run-local tables.

Required inputs (`foldseek.mode=precomputed_all_hits`):

- `config:foldseek.pdb_all_hits`: columns `query`, `target`, `evalue`, `bits`,
  `prob`, `alntmscore`, `qtmscore`, `ttmscore`, `lddt`, `qcov`, `tcov`, `qlen`,
  `tlen`, `batch`.
- `config:foldseek.afsp_all_hits`: same columns.
- `config:foldseek.id_map`: columns `run_id`, `protein_id`, `family_label`,
  `habitat_broad`.

Required inputs (`foldseek.mode=live`):

- `02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv` (from 020):
  columns `run_id`, `query_pdb_file`.
- `config:resources.foldseek_bin`, `config:resources.pdb_foldseek_db`,
  `config:resources.afsp_foldseek_db` — validated by the adapter at run time
  (kept out of the plan-time gate so plan-on-laptop / run-on-HPC works).

Expected relationships:

- PDB query set, AFSP query set, and id_map `run_id` set should match.

Outputs:

- `02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv`
- `02_foldseek/tables/full/full_vs_afsp_foldseek_all_hits.tsv`
- `02_foldseek/tables/full/full_manual_id_map.tsv`
- `02_foldseek/qc/full/full_precomputed_foldseek_import_qc.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 030_import_foldseek --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 030_import_foldseek --resume --follow
```

## 040_m06b_pdb

What it does: creates canonical PDB rank1, top5, qTMmax, near-tie, and
classified best-hit outputs.

Required inputs:

- `02_foldseek/tables/full/full_vs_pdb_foldseek_all_hits.tsv`: canonical
  14-column Foldseek all-hit schema.
- `02_foldseek/tables/full/full_manual_id_map.tsv`: columns `run_id`,
  `protein_id`, `family_label`, `habitat_broad`.

Expected relationships:

- All-hit query set should match id_map `run_id`.
- Rank1 output should contain one row per query.

Outputs:

- `02_foldseek/tables/full/full_vs_pdb_foldseek_best_hit_rank1_classified.tsv`
- `02_foldseek/tables/full/full_vs_pdb_foldseek_top5_hits.tsv`
- `02_foldseek/qc/full/full_vs_pdb_foldseek_canonical_summary.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 040_m06b_pdb --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 040_m06b_pdb --resume --follow
```

## 060_m08_reference_panel

What it does: selects the integrated PDB/AFSP primary and supporting reference
panel.

Required inputs:

- PDB M06B rank1 classified, top5, qTMmax, rank1-vs-qTMmax, and near-tie TSVs.
- AFSP M07B rank1 classified, top5, qTMmax, rank1-vs-qTMmax, and near-tie TSVs.
- Key columns include `query`, `target`, `qtmscore`, and support-class columns.

Expected relationships:

- PDB and AFSP canonical output query sets should match.
- Decision table should contain one row per query.
- Full665 panel should contain five rows per query.

Outputs:

- `05_reference_panel/full/full_integrated_reference_decision.tsv`
- `05_reference_panel/full/full_reference_panel_targets.tsv`
- `05_reference_panel/full/full_reference_panel_manual_review.tsv`
- `05_reference_panel/full/full_reference_panel_summary.tsv`
- `05_reference_panel/full/full_reference_panel_pointer.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 060_m08_reference_panel --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 060_m08_reference_panel --resume --follow
```

## 070_m09a_p2rank_manifests

What it does: prepares query and unresolved reference manifests for P2Rank.

Required inputs:

- `02_foldseek/query_pdb_manifest/full_query_pdb_manifest.tsv`: columns `mode`,
  `batch_id`, `run_id`, `protein_id`, `family_label`, `query_pdb_file`,
  `query_pdb_basename`, `colabfold_plddt_mean`, `colabfold_ptm`,
  `colabfold_struct_conf_class`, `colabfold_model_status`, `atom_lines`,
  `ca_atoms`.
- `05_reference_panel/full/full_integrated_reference_decision.tsv`: columns
  `query`, `protein_id`, `family`, `primary_reference_layer`,
  `primary_reference_target`, `manual_review_level`.
- `05_reference_panel/full/full_reference_panel_targets.tsv`: columns `query`,
  `protein_id`, `family`, `panel_order`, `reference_layer`, `panel_role`,
  `target`, `support_class`.

Expected relationships:

- Query manifest `run_id` set equals M08 decision `query` set.
- Panel query set equals decision query set.
- Query model PDB paths exist.

Outputs:

- `04_p2rank/full/input_manifests/full_p2rank_query_model_manifest.tsv`
- `04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest.tsv`
- `04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_pending.tsv`
- `04_p2rank/full/qc/full_p2rank_input_manifest_summary.tsv`
- `04_p2rank/full/qc/full_p2rank_input_manifest_pointer.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 070_m09a_p2rank_manifests --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 070_m09a_p2rank_manifests --resume --follow
```

## 080_m09c_materialize_references

What it does: materializes unique PDB and AFSP reference structures as
full-atom P2Rank-ready inputs. Foldseek DB CA-only exports are not valid for
reference P2Rank, reference-pocket, ligand/contact, or residue-level
interpretation.

Required inputs:

- `05_reference_panel/full/full_reference_panel_targets.tsv`: columns `query`,
  `reference_layer`, `target`.
- Full-atom PDB/mmCIF source/cache for PDB targets.
- Full-atom AFSP/AlphaFold source/cache for AFSP targets.
- Chain-specific target information embedded in PDB panel targets where needed.

Expected relationships:

- Unique `(reference_layer, target)` pairs should be materializable.
- PDB targets should be full-atom and chain-specific when the target encodes a
  chain.
- AFSP targets should be full-atom AlphaFold/AFSP PDB models.
- CA-only Foldseek DB exports must not be used as final P2Rank/reference-pocket
  input.
- Materialized structures must stay under the run directory.

Outputs:

- `04_p2rank/full/reference_resolution/full_reference_materialization_report.tsv`
- `04_p2rank/full/reference_resolution/full_reference_materialization_summary.tsv`
- `04_p2rank/full/reference_resolution/fullatom_reference_full_materialized_manifest.tsv`
- `04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv`
- `04_p2rank/full/reference_structures/materialized/pdb_chains/`
- `04_p2rank/full/reference_structures/materialized/afsp/`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 080_m09c_materialize_references --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 080_m09c_materialize_references --resume --follow
```

## 090_m09b_resolve_references and reference atom guard

What it does: resolves materialized reference files back onto every reference
panel row, writes the unique P2Rank reference manifest, and optionally runs the
reference atom-name guard before reference P2Rank. In `full_atom_cache` mode the
guard is enabled by default.

Required inputs:

- `04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest.tsv`:
  columns `query`, `reference_layer`, `target`.
- `04_p2rank/full/reference_resolution/full_reference_materialization_report.tsv`.
- `04_p2rank/full/reference_resolution/full_reviewed_recovered_reference_aliases.tsv`.
- Full-atom materialized reference structures from `080_m09c_materialize_references`.

Expected relationships:

- Every panel row should resolve to an existing materialized reference file.
- The unique reference manifest should contain one row per distinct resolved
  reference structure.
- Every reference structure should contain non-CA atoms.
- Backbone atoms `N`, `CA`, `C`, and `O` should be present for normal protein
  residues.
- CA-only-like references must fail before reference P2Rank unless an explicit
  diagnostic CA-only mode is requested.

Outputs:

- `04_p2rank/full/input_manifests/full_p2rank_reference_panel_manifest_resolved.tsv`
- `04_p2rank/full/input_manifests/full_p2rank_reference_unique_structure_manifest.tsv`
- `04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_report.tsv`
- `04_p2rank/full/reference_resolution/full_reference_panel_file_resolution_summary.tsv`
- `04_p2rank/full/qc/full_reference_atom_name_guard_audit.tsv`
- `04_p2rank/full/qc/full_reference_atom_name_guard_summary.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 090_m09b_resolve_references --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 090_m09b_resolve_references --resume --follow
```

## 100_m09d_generate_p2rank_runners

What it does: creates local P2Rank runner scripts and audits them before
execution.

Required inputs:

- `04_p2rank/full/input_manifests/full_p2rank_query_model_manifest.tsv`:
  columns `query`, `query_model_pdb`.
- `04_p2rank/full/input_manifests/full_p2rank_reference_unique_structure_manifest.tsv`:
  columns `unique_reference_id`, `reference_file_path`.
- `config:resources.p2rank_jar`

Expected relationships:

- Query manifest row count should match expected query structure count.
- Reference unique manifest row count should match resolved unique references.
- Runner audit must reject scratch paths, sbatch directives, and unsafe output
  roots.

Outputs:

- `04_p2rank/full/local_runs/runfull_p2rank_query_models_local.sh`
- `04_p2rank/full/local_runs/runfull_p2rank_reference_resolved_unique_local.sh`
- `04_p2rank/full/full_p2rank_local_run_manifest.tsv`
- `04_p2rank/full/qc/full_p2rank_runner_audit.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 100_m09d_generate_p2rank_runners --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 100_m09d_generate_p2rank_runners --resume --follow
```

## 110_p2rank_query

What it does: runs P2Rank for all query structures.

Required inputs:

- `04_p2rank/full/local_runs/runfull_p2rank_query_models_local.sh`

Expected relationships:

- Every query PDB path referenced by the runner dataset should exist.
- Failed query manifest should be empty or explicitly reviewed.

Outputs:

- `04_p2rank/full/query_models/all/query_p2rank_run_manifest.tsv`
- `04_p2rank/full/query_models/all/query_p2rank_failed.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 110_p2rank_query --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 110_p2rank_query --resume --follow
```

## 130_m09e_query_merge

What it does: merges query P2Rank predictions and extracts query top1 pockets.

Required inputs:

- `04_p2rank/full/query_models/all/query_p2rank_run_manifest.tsv`: columns
  `query`, `status`.

Expected relationships:

- Completed query count should match expected query manifest count.
- Zero-pocket queries should be represented in QC.

Outputs:

- `04_p2rank/full/query_models/merged_tables/full_query_p2rank_predictions_merged.tsv`
- `04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv`
- `04_p2rank/full/qc/full_query_p2rank_merge_qc_report.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 130_m09e_query_merge --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 130_m09e_query_merge --resume --follow
```

## 160_m10a_visual_contract

What it does: builds the visual overlay input contract linking panel rows to
query/reference structures and P2Rank pockets.

Required inputs:

- M08 decision and reference panel TSVs.
- M09A query model manifest.
- M09E query top1 pockets.
- M09B resolved reference panel manifest.
- M09F reference pocket counts.
- M09G reference top1 pockets.

Expected relationships:

- Visual contract should retain one row per reference panel row.
- CA-only reference status must remain unreliable evidence, not clean negative
  biological evidence.

Outputs:

- `06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv`
- `06_visual_qc_v6/full/input_manifests/full_visual_overlay_query_summary.tsv`
- `06_visual_qc_v6/full/input_manifests/full_visual_overlay_reference_status_summary.tsv`
- `06_visual_qc_v6/full/qc/full_visual_overlay_input_contract_qc_report.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 160_m10a_visual_contract --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 160_m10a_visual_contract --resume --follow
```

## 210_m11_supporting_audit

What it does: audits supporting reference agreement and conflict patterns.

Required inputs:

- `05_reference_panel/full/full_reference_panel_targets.tsv`
- `05_reference_panel/full/full_integrated_reference_decision.tsv`
- `06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv`
- `04_p2rank/full/query_models/merged_tables/full_query_p2rank_top1_pockets.tsv`
- `04_p2rank/full/reference_models/merged_tables/full_reference_p2rank_top1_pockets.tsv`

Expected relationships:

- Supporting audit query set should be a subset of M08 decision queries.

Outputs:

- `results/full/06_supporting_reference_audit/full_supporting_reference_audit.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 210_m11_supporting_audit --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 210_m11_supporting_audit --resume --follow
```

## 220_m12a_primary_decision

What it does: builds the primary decision matrix using existing M12 logic.

Required inputs:

- M08 decision table.
- M06B and M07B rank1 classified tables.
- M10A visual overlay contract.
- M10D row QC.

Expected relationships:

- One primary decision row is expected per M08 decision query.

Outputs:

- `results/full/07_decision_matrix/full_primary_decision_matrix.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 220_m12a_primary_decision --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 220_m12a_primary_decision --resume --follow
```

## 235_m12d_multi_reference_pocket_overlap

What it does: computes PyMOL-aligned query/reference top-1 pocket overlap
metrics for every M10A visual contract row. This includes primary and supporting
references.

Required inputs:

- `06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv`
- Query model PDBs referenced by the contract.
- Full-atom reference PDBs referenced by the contract.
- PyMOL render/alignment environment.

Expected relationships:

- One overlap metric row should be produced for every selected visual contract
  row.
- CA-only references should already have been blocked by the reference atom
  guard.
- `REFERENCE_ZERO_POCKET` and `QUERY_ZERO_POCKET` are explicit statuses, not
  silent missing metrics.

Outputs:

- `results/full/08_user_facing_exports/full_multi_reference_pocket_overlap_metrics.tsv`
- `results/full/08_user_facing_exports/full_multi_reference_pocket_overlap_metrics_qc.tsv`
- `results/full/08_user_facing_exports/full_multi_reference_pocket_overlap_metrics_input.tsv`

Examples:

```bash
python3 scripts/modules/12d_multi_reference_pocket_overlap_metrics.py \
  --workspace . \
  --contract runs/<run_label>/06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv \
  --outdir runs/<run_label>/results/full/08_user_facing_exports \
  --mode full \
  --pymol-cmd 06_visual_qc_v6/render_env/bin/pymol
```

## 240_m15_user_facing_exports

What it does: builds compact user-facing structural/pocket TSV exports. These
preserve the primary/rank-1 decision while exposing all supporting-reference
context.

Required inputs:

- M10A visual overlay input contract.
- M05 reference panel targets.
- M12A primary decision matrix.
- M12B supporting reference decision matrix.
- M12C combined decision summary.
- M12D multi-reference pocket overlap metrics.
- Optional final composite PNG directory.

Expected relationships:

- `full_final_primary_rank1_summary.tsv` should contain one row per query.
- `full_final_reference_panel_long.tsv` should contain one row per
  query/reference panel row.
- Missing overlap metrics are a QC warning/failure; zero-pocket statuses are
  explicit interpreted statuses.
- Supporting references do not automatically override the primary decision.

Outputs:

- `results/full/08_user_facing_exports/full_final_primary_rank1_summary.tsv`
- `results/full/08_user_facing_exports/full_final_reference_panel_long.tsv`
- `results/full/08_user_facing_exports/full_pocket_residue_details_long.tsv`
- `results/full/08_user_facing_exports/full_user_facing_data_dictionary.tsv`
- `results/full/08_user_facing_exports/full_user_facing_export_qc.tsv`
- `results/full/08_user_facing_exports/README_user_facing_exports.md`

Examples:

```bash
python3 scripts/modules/15_user_facing_final_exports.py \
  --workspace . \
  --mode full \
  --contract runs/<run_label>/06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv \
  --reference-panel runs/<run_label>/05_reference_panel/full/full_reference_panel_targets.tsv \
  --primary-decision runs/<run_label>/results/full/07_decision_matrix/full_primary_decision_matrix.tsv \
  --supporting-decision runs/<run_label>/results/full/07_decision_matrix/full_supporting_reference_decision_matrix.tsv \
  --combined-decision runs/<run_label>/results/full/07_decision_matrix/full_combined_decision_summary.tsv \
  --overlap-metrics runs/<run_label>/results/full/08_user_facing_exports/full_multi_reference_pocket_overlap_metrics.tsv \
  --final-png-dir runs/<run_label>/06_visual_qc_v6/full/composite_png/final_pngs \
  --outdir runs/<run_label>/results/full/08_user_facing_exports
```

## 250_m13a_context

What it does: collects M13 rulebook evidence context from M12/M11/M10 outputs.

Required inputs:

- `results/full/07_decision_matrix/full_combined_decision_summary.tsv`
- `results/full/06_supporting_reference_audit/full_supporting_reference_audit.tsv`
- `06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv`

Expected relationships:

- Context rows retain query identifiers for downstream M13 modules.

Outputs:

- `results/full/08_rulebook_evidence/full_rulebook_context_collector.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 250_m13a_context --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 250_m13a_context --resume --follow
```

## 310_m14_export

What it does: builds final full and compact exports.

Required inputs:

- `results/full/08_rulebook_evidence/full_final_rulebook_evidence_matrix.tsv`
- `results/full/07_decision_matrix/full_combined_decision_summary.tsv`

Expected relationships:

- Export query set should match the final rulebook evidence query set.

Outputs:

- `exports/full/full_final_export_full.tsv`
- `exports/full/full_final_export_compact.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 310_m14_export --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 310_m14_export --resume --follow
```

## 320_interpretation_ready_export

What it does: creates the interpretation-ready export layer from M14 outputs.

Required inputs:

- `exports/full/full_final_export_full.tsv`

Expected relationships:

- Interpretation-ready rows preserve final export query identifiers.

Outputs:

- `exports/full/interpretation_ready/full_final_export_full_interpretation_ready.tsv`

Examples:

```bash
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --start-at 320_interpretation_ready_export --resume --follow
python3 scripts/vermamg.py run --config run_configs/<run>.yaml --stop-after 320_interpretation_ready_export --resume --follow
```
