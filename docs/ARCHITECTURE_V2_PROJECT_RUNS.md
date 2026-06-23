# VermAMG Architecture V2: Project-Scoped Runs

VermAMG V2 is organized around a user-provided project identity. A user should
describe the project, inputs, environment, and options once in a YAML run config;
the pipeline then plans, validates, runs, resumes, and exports under one isolated
project run directory.

## Canonical User Flow

```bash
cd /path/to/VermAMG
cp run_templates/precomputed_project_run_v2.yaml.template run_configs/my_project.yaml
python scripts/vermamg.py plan --config run_configs/my_project.yaml
python scripts/vermamg.py run --config run_configs/my_project.yaml --resume --follow
```

For `profile: local_wsl`, heavy stages that call Linux Foldseek, P2Rank runner
scripts, or containerized render tooling must be run from WSL/Linux:

```bash
cd /mnt/d/VermAMG
python3 scripts/vermamg.py run --config run_configs/my_project.yaml --resume --follow
```

PowerShell/Windows Python can be useful for plan/preflight checks, but it is not
the canonical executor for `local_wsl` compute stages.

The first V2 implementation targets the proven precomputed downstream path:

- precomputed ColabFold query PDBs
- precomputed Foldseek PDB and AlphaFold SwissProt all-hit tables
- M06B/M07B canonical structural search outputs
- M08 reference panel
- M09 full-atom reference materialization, atom-name guard, and P2Rank
- M10 visual contracts/scripts
- M11/M12 decision matrices
- M13/M14 interpretation exports

Live FASTA-to-ColabFold/Foldseek execution is now connected to the same V2
identity and run-root model via the Paket3 adapters (see "Live Adapters" below).

## Input Intake And Batching

Every V2 project run now starts by materializing the user FASTA into a
run-local canonical input contract:

```text
work/00_inputs/fasta/canonical_sequences.faa
work/00_inputs/manifests/sample_manifest.tsv
work/00_inputs/metadata/sample_metadata_joined.tsv
work/00_inputs/qc/input_intake_summary.tsv
work/00_inputs/qc/metadata_qc.tsv
```

The intake policy is configured under:

```yaml
input_intake:
  id_policy: preserve_first_token
  duplicate_policy: fail
  min_sequence_length: 1
  invalid_sequence_policy: fail

metadata:
  id_column: protein_id
  required: false
  strict_extra_rows: false
```

The next stage writes an explicit batch plan:

```text
work/00_inputs/batches/batch_manifest.tsv
work/00_inputs/batches/batch_membership.tsv
work/00_inputs/batches/fasta/*.faa
work/00_inputs/manifests/sample_manifest_with_batches.tsv
work/00_inputs/qc/batch_plan_summary.tsv
```

`batching.enabled: false` means "do not split the FASTA", but VermAMG still
writes a single-batch plan. This keeps future local and SLURM adapters on one
stable input contract instead of branching by environment.

## Backend Job Plan

Paket2 adds `016_backend_job_plan`, a dry-run-only backend abstraction layer.
It consumes `work/00_inputs/batches/batch_manifest.tsv` and writes:

```text
work/00_inputs/job_plan/backend_job_plan.tsv
work/00_inputs/job_plan/backend_job_dependencies.tsv
work/00_inputs/job_plan/backend_plan_summary.tsv
work/00_inputs/job_plan/backend_dry_run_manifest.tsv
work/submit/local/run_backend_dry_run.sh
work/submit/slurm/submit_backend_dry_run.sh
work/submit/slurm/sbatch/*.sbatch
```

The active backend comes from:

```yaml
environment:
  backend: local   # local | slurm

backend_jobs:
  dry_run: true
  submit_jobs: false
  emit_local_bundle: true
  emit_slurm_bundle: true
  plan_colabfold: true
  plan_foldseek: true
```

The stage plans ColabFold batch jobs, a collect job, and Foldseek PDB/AFSP jobs
with explicit dependency rows. `submit_jobs: true` is intentionally blocked in
this phase. The generated local and SLURM scripts are previews only; Paket3
wires real live adapter commands and output collection into this contract.

## Live Adapters (Paket3)

Paket3 connects live ColabFold and Foldseek execution behind the same stage
contracts the precomputed import already satisfies. There are no new stage IDs:
`020_import_colabfold` and `030_import_foldseek` became mode-aware.

```yaml
colabfold:
  mode: live          # precomputed | live
  cmd: colabfold_batch
  msa_mode: mmseqs2_uniref_env
  model_type: alphafold2_ptm
  num_recycle: "3"
  num_models: "1"
  dry_run: false      # true plans per-batch commands without compute

foldseek:
  mode: live          # precomputed_all_hits | live
  threads: 4
  dry_run: false

resources:
  foldseek_bin: ""        # required for foldseek.mode=live
  pdb_foldseek_db: ""
  afsp_foldseek_db: ""
```

- `colabfold.mode=live` runs `scripts/modules/00d_run_colabfold.py` over the
  Paket1 FASTA batches and emits the same canonical
  `full_query_pdb_manifest.tsv` (plus collector manifest and id_map). Live runs
  fill real `colabfold_plddt_mean`/`colabfold_ptm` from the ColabFold score
  JSONs, where the precomputed path wrote `NA`.
- `foldseek.mode=live` runs `scripts/modules/00e_run_foldseek.py` with the
  proven `createdb -> search --max-seqs 50 -a -> convertalis` sequence (ported
  from `scripts/modules/06_prepare_foldseek_pdb_search.sh`) and emits the
  canonical 14-column `full_vs_pdb/afsp_foldseek_all_hits.tsv` plus the id_map.

Both adapters are fully count/data-agnostic: every FASTA record and every query
PDB flows through; no cohort size is hardcoded. They honor `environment.backend`
(`local` runs the tool directly; `slurm` emits/submits one sbatch per batch).
Tool/DB availability is validated by the adapters at run time with explicit
errors, so `plan` works on a laptop and the real run executes on a GPU box or
HPC node. `colabfold.dry_run`/`foldseek.dry_run` build the command plan only;
set them false on a compute node to materialize structures and hit tables.

Downstream M06B -> M14 is unchanged: it never distinguishes live-generated from
precomputed inputs because both produce identical canonical contracts.

## Reference Materialization Policy

V2 precomputed project runs default to `reference_materialization.method:
full_atom_cache`. The run config points to a trusted full-atom reference cache
or previous corrected run:

```yaml
reference_materialization:
  method: full_atom_cache
  source_run_root: "runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1"
  guard_reference_atom_names: true
  allow_ca_only_diagnostic: false
```

This copies full-atom PDB-chain/mmCIF and AFSP structures into the current run
under `work/04_p2rank/full/reference_structures/materialized/` before reference
P2Rank. The atom-name guard then fails the run if a reference input is missing
or CA-only-like. Legacy `foldseek_export` remains available for compatibility,
but it is not the recommended interpretation-grade reference path.

Current verified V2 smoke:

```text
runs/hoxd_viral_amg_screen/hoxd_precomputed_project_v2_fullatom_cache_smoke/
```

Validation highlights:

- 1496/1496 unique references materialized from full-atom cache.
- 3325/3325 reference panel rows resolved; 0 missing.
- Reference atom-name guard PASS; CA-only-like references = 0.
- Reference P2Rank manifest rows = 1496; failed manifest is header-only.
- M14 and interpretation-ready exports contain 665 rows with QC status OK.

## Project Identity

Users provide:

```yaml
schema_version: 2

project:
  name: "HOXD Viral AMG Screen"
  slug: ""

run:
  label: ""
  root: "runs/{project_slug}/{run_label}"
```

Rules:

- `project.name` is the required human-readable project identity.
- `project.slug` is optional; if empty, VermAMG derives a filesystem-safe slug.
- `run.label` is optional; if empty, VermAMG derives
  `YYYYMMDD_{project_slug}_{backend}_{mode}`.
- V2 defaults to `runs/{project_slug}/{run_label}`.

Example resolved root:

```text
runs/hoxd_viral_amg_screen/20260621_hoxd_viral_amg_screen_local_full/
```

## Run Directory Contract

Every V2 run root contains the three user-facing strata requested for the
product architecture:

```text
runs/{project_slug}/{run_label}/
  metadata/
  inputs/
  state/
  logs/
  work/
  results/
  exports/
```

Meaning:

- `work/`: machine/intermediate artifacts needed by downstream stages.
- `results/`: scientific intermediate results and decision tables.
- `exports/`: user-facing final package.

In V2 layout, legacy intermediate directories are stored under `work/`:

```text
work/01_colabfold/
work/02_foldseek/
work/04_p2rank/
work/05_reference_panel/
work/06_visual_qc_v6/
```

This keeps the scientific stage names recognizable while preventing generated
machine artifacts from living next to `results/` and `exports/` as peers.

## Compatibility Policy

Schema V1 configs remain supported. V1 keeps the historical layout:

```text
runs/{run_label}/
  01_colabfold/
  02_foldseek/
  04_p2rank/
  results/
  exports/
```

Schema V2 uses the project-scoped layout. Existing module contracts can still
refer to paths such as `02_foldseek/...`; the V2 `RunContext` resolves those
paths under `work/02_foldseek/...`.

## Next Architecture Phases

1. Keep Python `scripts/vermamg.py` as the canonical guarded orchestrator.
2. (DONE, Paket3) Live local/SLURM ColabFold adapter wired into the backend
   contract via `00d_run_colabfold.py` and `colabfold.mode=live`.
3. (DONE, Paket3) Live Foldseek search/collect adapter via
   `00e_run_foldseek.py` and `foldseek.mode=live`, matching the precomputed
   downstream contract exactly.
4. Validate a real end-to-end live run on a GPU/HPC node (compute was out of
   scope for the contract-validate phase: no GPU/Foldseek DBs available locally).
5. Parameterize remaining internal `full` naming in user-facing exports.
6. Add cleanup/archive policy for legacy, generated, backup, and temporary files.
