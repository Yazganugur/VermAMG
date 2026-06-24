# Catalytic Previsual Layer Contracts

Phase 1B status: scaffold contracts plus read-only canonical-output validation.
These stages declare the automatic
topology/catalytic layer that must run before catalytic visual rendering. They
must not consume prototype A00/A04/A07/A08/A09 outputs in production; those
prototype files are contract examples only.

The current canonical biological contract is A10G-FIX2 + A10H + A10I:
function-type-aware M-CSA role classification, required original-PDB coordinate
rescue before residue transfer, the 2fua tyrosine phenol-lyase Tyr manual core
catalytic override, and identity-level pre-geometry interpretation. Active-site
geometry is not validated in this layer.

## Dependency Placement

The approved dependency rule is:

```text
reference/structure/pocket inputs
  -> M09H-M09R topology/catalytic residue layer
  -> full_catalytic_visual_query_manifest.tsv
  -> full_catalytic_visual_annotation_manifest.tsv
  -> M10H catalytic two-panel PNG rendering
  -> M15B parallel integrated exports/report tables
```

M10H consumes only `full_catalytic_visual_query_manifest.tsv` and
`full_catalytic_visual_annotation_manifest.tsv`. It must not parse M-CSA,
UniProt, raw Foldseek alignments, or perform original-PDB coordinate rescue.

M15B is a parallel integrated export surface. It must not overwrite existing
M14 or M15 exports.

## Stage Map

| Stage | Module | Status | Output Contract |
|---|---|---|---|
| 151_m09h_deeptmhmm_topology | `09h_parse_deeptmhmm_topology.py` | default disabled scaffold | `full_deeptmhmm_query_topology.tsv` |
| 152_m09i_topology_pocket_context | `09i_query_pocket_topology_context.py` | default disabled scaffold | `full_query_pocket_topology_context.tsv` |
| 153_m09j_catalytic_stack_manifest | `09j_build_catalytic_stack_manifest.py` | default disabled scaffold | `full_catalytic_stack_manifest.tsv` |
| 154_m09k_mcsa_resource_cache | `09k_cache_parse_mcsa_resources.py` | default disabled scaffold | `full_mcsa_resource_audit.tsv` |
| 155_m09l_uniprot_residue_evidence | `09l_cache_parse_uniprot_residue_evidence.py` | default disabled scaffold | `full_uniprot_residue_evidence.tsv` |
| 156_m09m_catalytic_candidate_evidence | `09m_generate_catalytic_candidate_evidence.py` | default disabled scaffold | `full_candidate_catalytic_reference_evidence_long.tsv` |
| 157_m09n_pairwise_foldseek_job_plan | `09n_prepare_pairwise_foldseek_alignment_jobs.py` | default disabled scaffold | `full_pairwise_alignment_job_plan.tsv` |
| 158_m09o_pairwise_alignment_inventory | `09o_merge_pairwise_foldseek_alignments.py` | default disabled scaffold | `full_pairwise_alignment_inventory.tsv` |
| 159_m09p_mcsa_coordinate_rescue | `09p_mcsa_original_pdb_coordinate_rescue.py` | default disabled scaffold | `full_mcsa_original_pdb_coordinate_rescue.tsv` |
| 159q_m09q_catalytic_residue_transfer | `09q_final_catalytic_residue_transfer.py` | default disabled scaffold | transfer, query summary, final class TSVs |
| 159r_m09r_catalytic_visual_annotation | `09r_prepare_catalytic_visual_annotation_manifest.py` | default disabled scaffold | visual query/residue manifests |
| 159s_m09r_validate_catalytic_previsual_outputs | `09r_validate_previsual_catalytic_outputs.py` | default disabled validator | `full_previsual_catalytic_validation_qc.tsv` |
| 165_m10h_catalytic_two_panel_png | `10h_generate_catalytic_two_panel_figures.py` | default disabled scaffold | catalytic PNG manifest/QC |
| 330_m15b_parallel_integrated_export | `15b_parallel_integrated_topology_catalytic_exports.py` | default disabled scaffold | parallel integrated export/QC |

## Evidence Policy

- M-CSA core literature evidence is GOLD identity-level support after
  original-PDB coordinate rescue.
- M-CSA non-core literature evidence is GOLD context only.
- UniProt experimental/high-confidence residue evidence is STRONG.
- UniProt similarity/predicted ECO evidence is SUPPORT_CAUTION.
- SUPPORT_CAUTION evidence can be reported, but must not be described as
  catalytic proof.
- M-CSA/PDB residue evidence must go through original RCSB PDB coordinate
  validation/rescue before final interpretation.
- The 2fua tyrosine phenol-lyase Tyr manual core catalytic override is required
  and must be auditable in `full_2fua_Tyr_manual_override_audit.tsv`.
- This is an identity-level, pre-geometry layer. `geometry_validated_flag` must
  remain false/no until a later active-site geometry module validates geometry.

## Canonical Validation Targets

A10G-FIX2 canonical outputs under `results/full/10_catalytic_layer/`:

- `full_candidate_residue_transfer_mapping_mcsa_rescued.tsv`: one row per transferred catalytic residue.
- `full_query_level_catalytic_residue_summary.tsv`: one row per query protein.
- `full_final_catalytic_layer_integration.tsv`: one row per query protein; class-count
  validation uses `A10G_FIX2_final_catalytic_layer_class` as the canonical
  class column.
- `full_catalytic_visual_query_manifest.tsv`: one row per query protein.
- `full_catalytic_visual_annotation_manifest.tsv`: one row per residue-level annotation.
- `full_2fua_Tyr_manual_override_audit.tsv`: one row per manual residue override.
- `full_catalytic_layer_class_transition_to_current.tsv`: transition audit
  with `A10E_strict_final_catalytic_layer_class`,
  `A10G_FIX2_final_catalytic_layer_class`, and `n`.
- `full_current_catalytic_layer_version.tsv`: must report
  key/value row `canonical_catalytic_layer_version=A10G_FIX2`.

## Retention Policy

Every major query-level summary must left-join back to the full query manifest.
No Tier1/Tier2 query protein or A00/reference-equivalent row may silently
disappear. Alias/symlink representation must remain visible as explicit
`alias_status` values.

## Exact Headers

The machine-readable header contracts live in:

```text
pipeline_contracts/catalytic_previsual_output_headers.tsv
```

The highest-priority downstream contracts are:

```text
results/full/10_catalytic_layer/full_catalytic_visual_query_manifest.tsv
results/full/10_catalytic_layer/full_catalytic_visual_annotation_manifest.tsv
```

Their required-column headers are declared in
`pipeline_contracts/catalytic_previsual_output_headers.tsv`.

The final class-count policy is declared in
`pipeline_contracts/catalytic_layer_class_policy.tsv`.
