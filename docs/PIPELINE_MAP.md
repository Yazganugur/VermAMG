# VermAMG Pipeline Map

This is the high-level map for the current VermAMG structural/pocket workflow.
It reflects the corrected full-atom-reference full665 run.

## Current Corrected Run

Interpretation-grade full665 run:

```text
runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1/
```

Broken diagnostic run retained for comparison only:

```text
runs/tier1_tier2_colabfold_postrun_fresh_v1/
```

The older run used CA-only Foldseek exports as reference structures. That is not
valid for reference P2Rank, reference-pocket, ligand/contact, or residue-level
interpretation.

## High-Level Flow

```text
Input protein FASTA / candidate set
  -> Resource manifest QC
  -> M00 input QC
  -> M01 run-set preparation
  -> M02-M04 ColabFold query model layer / model collection
  -> M05 Foldseek query PDB manifest
  -> M06 PDB Foldseek outputs
  -> M07 AFSP Foldseek outputs
  -> M08 integrated reference panel
  -> M09 full-atom reference materialization and P2Rank setup
  -> M09D reference atom-name guard and P2Rank runners
  -> M09E/M09F/M09G query/reference P2Rank merges
  -> M09H-M09R topology/catalytic residue layer
  -> M10A visual overlay input contract
  -> M10H catalytic two-panel PNG scaffold
  -> M10B smoke visual overlay package
  -> M10C all-query visual script package
  -> M10D visual script QC
  -> M10G composite PNG generation
  -> M11 supporting reference audit
  -> M12A/B/C primary, supporting, and combined decision matrices
  -> M12D multi-reference pocket overlap metrics
  -> M13 rulebook/evidence layer, when enabled
  -> M14 final export, when enabled
  -> M15 user-facing structural/pocket exports
  -> M15B parallel integrated topology/catalytic exports
```

## Primary Scientific Policy

- The primary/rank-1 structural path is preserved.
- Supporting references are retained as contextual/audit evidence.
- Supporting references do not automatically override the primary reference.
- Multi-reference outputs may flag a supporting reference for manual inspection,
  especially when it has better pocket overlap or better qTM.
- All language remains computational/cautious; outputs are not experimental
  functional validation.

## Full-Atom Reference Policy

Reference structures used for reference P2Rank and pocket/residue interpretation
must be full-atom:

- PDB targets are materialized as full-atom PDB/mmCIF-derived structures.
- PDB chain-specific targets are extracted as full-atom chain-specific PDBs.
- AFSP targets are materialized as full-atom AlphaFold/AFSP PDB structures.
- CA-only Foldseek DB exports are acceptable for structural search context, but
  not for P2Rank/reference-pocket/ligand-contact/residue-level inputs.
- The atom-name guard must fail before reference P2Rank if a reference remains
  CA-only, unless an explicit diagnostic CA-only mode is requested.

## Visual and Composite PNG Layer

M10A creates the visual overlay contract, one row per query/reference panel row.
M10C creates PyMOL/ChimeraX scripts for primary and supporting references.
M10G creates one composite PNG per query for the primary reference path.
M10H is a separate default-disabled catalytic PNG scaffold. It consumes only
the precomputed catalytic visual manifests:
`results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv` and
`results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv`.
It must not recompute M-CSA parsing, UniProt parsing, residue transfer,
Foldseek alignment parsing, or original-PDB coordinate rescue.

Current composite figure conventions:

- Query protein: cyan.
- Reference protein: gray.
- Shared/overlapping aligned pocket C-alpha positions: yellow.
- Query-unique pocket positions: orange.
- Reference-unique pocket positions: blue.
- PDB reference confidence values are B-factors.
- AFSP reference confidence values are pLDDT-like B-column values.

Final PNGs are intended under:

```text
06_visual_qc_v6/full/composite_png/final_pngs/
```

## M12D Multi-Reference Pocket Overlap

M12D computes PyMOL-aligned top-1 pocket overlap metrics for every row in the
M10A visual contract, including primary and supporting references.

Output:

```text
results/full/08_user_facing_exports/full_multi_reference_pocket_overlap_metrics.tsv
```

Key fields:

- `alignment_rmsd`
- `query_pocket_n`, `reference_pocket_n`
- `query_conserved_n`, `reference_conserved_n`
- `query_unique_n`, `reference_unique_n`
- `query_overlap_fraction`, `reference_overlap_fraction`
- `pocket_overlap_balanced_fraction`
- `pocket_overlap_jaccard_aligned_ca`
- `reference_confidence_semantics`

This layer answers whether a supporting reference has better pocket overlap than
the primary reference. It does not change the primary decision.

## M15 User-Facing Exports

M15 builds compact interpretation tables from M05, M10, M11, M12, and M12D.

Output directory:

```text
runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1/results/full/08_user_facing_exports/
```

Main files:

- `full_final_primary_rank1_summary.tsv`: one row per query. Main user-facing
  primary/rank-1 structural and pocket summary.
- `full_final_reference_panel_long.tsv`: one row per query/reference panel row.
  Use this to inspect all primary and supporting references.
- `full_pocket_residue_details_long.tsv`: residue-level pocket overlap detail.
- `full_multi_reference_pocket_overlap_metrics.tsv`: lower-level M12D metric
  table used by M15.
- `full_user_facing_export_qc.tsv`: row counts and QC.
- `README_user_facing_exports.md`: short guide for the generated export folder.

Important flags:

- `supporting_reference_has_better_pocket_overlap`
- `supporting_reference_has_higher_qtm`
- `manual_inspection_priority`
- `primary_overlap_metric_status`

## Manifests and Pointers

Manifests are TSV files that declare what a stage will consume or produce.
Examples include query PDB manifests, P2Rank manifests, visual overlay
contracts, and run manifests.

Pointers are small TSV files that tell downstream tools where the current
artifact for a stage was written. They are useful when outputs are isolated by
mode or run label.

Neither manifests nor pointers are biological evidence by themselves. They are
workflow bookkeeping and QC aids.

## Future Evidence Axes

The topology/catalytic axis is now reserved as M09H-M09R, before visual
rendering. Phase 1B adds a read-only A10G-FIX2 validator for precomputed
canonical TSVs. Future implementation must
regenerate DeepTMHMM topology parsing, M-CSA/UniProt evidence parsing, safe
pairwise Foldseek alignment inventory, M-CSA original-PDB coordinate rescue,
residue transfer, complete query summaries, and final catalytic classes from
pipeline inputs/resources.

These axes remain additive. They write their own summary/detail TSVs first,
feed M10H through the M09R visual annotation manifest, then join into M15B
without rewriting the existing structural/pocket decision logic.
