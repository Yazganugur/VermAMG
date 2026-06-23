# BAPS Structural Validation Pipeline — Directory Contract

## Core principle

The user provides candidate protein FASTA and optional metadata.

The pipeline owns the downstream directory structure.

Each module writes outputs into a predefined location. Later modules do not search randomly for files; they consume standardized tables/manifests produced by previous modules.

## Top-level layout

    structural_validation_tier1_full/
    ├── 00_inputs/
    ├── 01_colabfold/
    ├── 02_foldseek/
    ├── 03_references/
    ├── 04_p2rank/
    ├── 05_overlay_manifest/
    ├── 06_visual_qc_v6/
    ├── 07_decision_matrix/
    ├── 08_rulebook_evidence/
    ├── 09_regression_pilot32/
    ├── 10_results_package/
    ├── config/
    ├── docs/
    ├── logs/
    ├── pipeline_state/
    ├── run_sets/
    ├── scripts/
    └── tmp/

## Data-flow rule

Every major module must produce at least one machine-readable TSV manifest or summary table.

The next module should use that TSV as input.

## Current full665 run-root note

The current interpretation-grade full665 run root is:

    runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1/

The older run below is diagnostic/broken for reference-pocket interpretation,
because reference structures were CA-only Foldseek exports:

    runs/tier1_tier2_colabfold_postrun_fresh_v1/

Inside the corrected run, the important current interpretation layers are:

    01_colabfold/query_pdbs/
    02_foldseek/
    04_p2rank/full/reference_structures/materialized/
    04_p2rank/full/query_models/merged_tables/
    04_p2rank/full/reference_models/merged_tables/
    06_visual_qc_v6/full/input_manifests/
    06_visual_qc_v6/full/composite_png/final_pngs/
    results/full/06_supporting_reference_audit/
    results/full/07_decision_matrix/
    results/full/08_user_facing_exports/

`results/full/08_user_facing_exports/` is the main user-facing summary layer.
It contains the rank-1 primary TSV, all-reference long TSV, pocket-residue
detail TSV, multi-reference pocket-overlap metrics, a data dictionary, and QC.

Generated run-root artifacts are outputs, not source. Patch the producing
module/config and regenerate rather than editing generated TSV/PNG/PML files by
hand.

## Artifact registry

The registry records the official output path of every module.

Registry path:

    pipeline_state/artifacts/pipeline_artifact_registry.tsv

Registry columns:

    section
    module
    mode
    artifact_key
    path
    required_for_next_step
    status
    n_records
    n_files
    notes

## Regression principle

Pilot32 is the benchmark/regression set.

For each major module, the pipeline must compare new outputs against old Pilot32 outputs when available.

Regression comparison must include both:

1. file-level checks;
2. table/schema/content checks.

File counts alone are not sufficient.
