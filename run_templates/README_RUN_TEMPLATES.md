# VermAMG Run Templates

This directory contains fill-in-the-blanks YAML config templates for starting
a VermAMG project run.

| Template | Use when |
|---|---|
| `local_run.yaml.template` | Running on a local workstation or WSL |
| `hpc_slurm_run_v2.yaml.template` | Running on an HPC cluster via SLURM |

Both templates use **schema version 2** and work with `python scripts/vermamg.py`.

---

## How to use a template

```bash
# Copy the right template for your environment:
cp run_templates/local_run.yaml.template        run_configs/my_project.yaml   # local
cp run_templates/hpc_slurm_run_v2.yaml.template run_configs/my_hpc.yaml       # HPC

# Edit — fill every [FILL] field (see below)
# Then validate and run:
python scripts/vermamg.py plan --config run_configs/my_project.yaml
python scripts/vermamg.py run  --config run_configs/my_project.yaml --resume --follow
```

---

## Field reference

### `project.name` — REQUIRED

Human-readable name for your project. Drives the slug used in the run directory path.

```yaml
project:
  name: "Lake X Viral AMG Screen 2025"
```

### `run.label` — REQUIRED

Short identifier for this specific run. Combined with the project slug to form
the unique run path: `runs/{project_slug}/{run_label}/`.

```yaml
run:
  label: "lake_x_precomputed_v1"
```

### `inputs.fasta` — REQUIRED

Path to your input FASTA file, relative to the project root. The pipeline is
count-agnostic: any number of sequences flows through unchanged.

```yaml
inputs:
  fasta: "inputs/my_proteins.faa"
```

### `inputs.metadata_tsv` — OPTIONAL

TSV file with at least a `protein_id` column. Enables metadata annotations on
outputs. Set to `""` if not available.

---

## Execution mode — `colabfold.mode` + `foldseek.mode`

This is the most important choice. Pick one row:

| Scenario | `colabfold.mode` | `foldseek.mode` | What you need |
|---|---|---|---|
| You already have structure PDBs and hit tables | `precomputed` | `precomputed_all_hits` | PDB dir + Foldseek TSVs |
| You want the pipeline to predict structures | `live` | `live` | GPU + Foldseek DBs |

### Precomputed mode fields

```yaml
colabfold:
  mode: precomputed
  query_pdb_dir:       # directory containing one .pdb per protein (named by run_id)
  collector_manifest:  # TSV: tier | batch | model_id | pdb_source | pdb_dest
  score_json_dir: ""   # optional: per-protein ColabFold JSON files
  pae_json_dir: ""     # optional: PAE JSON files

foldseek:
  mode: precomputed_all_hits
  pdb_all_hits:   # Foldseek all-hits TSV vs PDB (columns: query target evalue bits prob ...)
  afsp_all_hits:  # Foldseek all-hits TSV vs AlphaFold/Swiss-Prot
  id_map:         # TSV: run_id | protein_id | family_label | habitat_broad
```

### Live mode fields

```yaml
colabfold:
  mode: live
  cmd: "colabfold_batch"         # ColabFold executable on PATH
  msa_mode: "mmseqs2_uniref_env"
  model_type: "alphafold2_ptm"
  num_recycle: "3"
  num_models: "1"
  dry_run: true                  # set false to actually run on GPU

foldseek:
  mode: live
  threads: 4
  dry_run: true                  # set false where foldseek_bin + DBs are available
```

---

## Resources section — tool paths

After running `bash setup.sh`, copy the printed paths here:

```yaml
resources:
  java_bin: "java"
  p2rank_cmd: "resources/tools/p2rank/prank"           # symlink created by setup.sh
  p2rank_jar: "resources/tools/p2rank/bin/p2rank.jar"  # symlink created by setup.sh
  # Live Foldseek mode only:
  foldseek_bin: "resources/tools/foldseek/bin/foldseek"
  pdb_foldseek_db:  "resources/databases/foldseek/pdb"
  afsp_foldseek_db: "resources/databases/foldseek/alphafold_swissprot"
```

See [docs/INSTALL.md](../docs/INSTALL.md) for full installation instructions.

---

## Reference materialization — `reference_materialization`

The pipeline needs full-atom PDB files for each protein's selected references
(used by P2Rank for pocket prediction). These come from a prior completed run.

For your **first run** on a new protein set, do a partial run to M08 first,
then re-run with `source_run_root` pointing to that run directory. The pipeline
caches and reuses the materialized PDB files automatically.

For the **smoke demo**, reference PDB files are bundled directly in
`examples/smoke_precomputed/data/reference_run_cache/`, so no prior run is needed.

```yaml
reference_materialization:
  method: full_atom_cache
  source_run_root: "runs/my_prior_project/my_prior_run"
  overwrite: false
  guard_reference_atom_names: true
  allow_ca_only_diagnostic: false
```

---

## Local vs HPC — differences at a glance

| Setting | Local template | HPC template |
|---|---|---|
| `environment.backend` | `local` | `slurm` |
| `backend_jobs.submit_jobs` | `false` | `true` (to auto-submit) |
| `backend_jobs.emit_slurm_bundle` | `false` | `true` |
| `slurm.*` fields | ignored | must be filled |
| `p2rank.threads` | 4 | match `slurm.cpus_cpu` |

---

## Stage toggles

All stages default to `true`. Disable a stage by setting it to `false`:

```yaml
stages:
  m10f_render: false      # visual rendering (needs PyMOL/ChimeraX container)
  foldseek_search: false  # only needed in live Foldseek mode
```

Stages run in order; disabling a stage also skips all stages that depend on it.
