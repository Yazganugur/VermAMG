# VermAMG — Developer / Internal Notes

> These are internal development notes and run-state checkpoints preserved from
> the original working README. They reference local-only runs (gitignored) and
> historical V1 details. The public-facing project README is at the repo root.

---

VermAMG is a structural-functional validation workflow for viral-context-supported putative AMG/AVG candidates from the BAPS Faz C v2 analysis.

## V2 project-run architecture

In schema v2, the user gives a project name once, and VermAMG creates an isolated run under:

```text
runs/{project_slug}/{run_label}/
  work/        # machine/intermediate artifacts
  results/     # scientific intermediate tables and decision layers
  exports/     # user-facing final package
```

V2 materializes the user FASTA before downstream execution:
`012_fasta_intake` writes `work/00_inputs/manifests/sample_manifest.tsv`, and
`014_fasta_batch_plan` writes explicit batch FASTA/manifest files under
`work/00_inputs/batches/`. `016_backend_job_plan` creates dry-run local and SLURM
job-plan bundles under `work/00_inputs/job_plan/` and `work/submit/`.

The checked V2 full-atom cache smoke run is:
`runs/hoxd_viral_amg_screen/hoxd_precomputed_project_v2_fullatom_cache_smoke/`
— completed through `320_interpretation_ready_export` with 665 final rows,
1496/1496 full-atom references, reference atom-name guard PASS.

## Current checkpoint (local-only runs)

- Corrected full665 full-atom-reference run is the current interpretation-grade checkpoint:
  `runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1/`.
- The previous full665 run `runs/tier1_tier2_colabfold_postrun_fresh_v1/` is retained
  as a broken diagnostic run because its reference structures were CA-only Foldseek
  exports. Do not use it for reference P2Rank, reference-pocket, ligand/contact, or
  residue-level interpretation.
- Current corrected run summary: 1496/1496 unique references materialized as full-atom
  inputs; reference atom-name guard PASS; CA-only count = 0; reference P2Rank completed
  and merged; M10 visual contract rows = 3325.

## User-facing outputs (corrected full-atom run)

Under `runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1/results/full/08_user_facing_exports/`:
- `full_final_primary_rank1_summary.tsv`: one row per query (primary/rank-1 interpretation).
- `full_final_reference_panel_long.tsv`: one row per query/reference panel row.
- `full_pocket_residue_details_long.tsv`: residue-level pocket overlap classes.
- `full_multi_reference_pocket_overlap_metrics.tsv`: M12D overlap metrics.

Policy:
- The primary/rank-1 path is preserved; supporting references are audit/context evidence only.
- A flag like `supporting_reference_has_better_pocket_overlap=YES` means "inspect this
  supporting reference"; it is not a silent primary replacement.
- PDB reference B-column = B-factors; AFSP reference B-column = pLDDT-like confidence.
- P2Rank pockets are computational top-1 predictions, not experimental active-site validation.

## Future evidence axes

Separate evidence axes that join into final exports without changing the primary/rank-1
structural logic:
- Topology axis: DeepTMHMM topology class, TM segments, query-pocket/TM overlap.
- Catalytic axis: M-CSA catalytic residues, UniProt annotations, PROSITE, CDD transfer,
  ConSurf conservation, AlphaFill cofactor context, HyPhy selection.

## Main rule

Do not edit generated artifacts as source. Patch source modules, regenerate artifacts,
then smoke-test.

## Legacy V1 master pipeline (retained)

`scripts/master/run_tier1_master_pipeline.sh` is the V1 shell orchestrator (modes:
`test` / `regression` / `full`). The V2 path (`scripts/vermamg.py`) supersedes it.
Legacy upstream compute/cache stayed `mode`-based (`02_foldseek/tables/{mode}/`,
`04_p2rank/{mode}/`, `06_visual_qc_v6/{mode}/`).
