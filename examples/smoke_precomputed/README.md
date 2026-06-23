# Smoke Demo — 3 proteins, precomputed mode

A minimal, self-contained demonstration of the VermAMG pipeline.  
No external databases required. P2Rank + Java must be installed (via `setup.sh`).

## What is included

| File/Directory | Contents |
|---|---|
| `data/proteins.faa` | 3 viral AMG candidate protein sequences (FASTA) |
| `data/query_pdbs/` | ColabFold-predicted structure PDB for each protein |
| `data/foldseek/pdb_all_hits.tsv` | Foldseek structural homology hits vs PDB |
| `data/foldseek/afsp_all_hits.tsv` | Foldseek hits vs AlphaFold/Swiss-Prot |
| `data/foldseek/id_map.tsv` | Protein ID mapping |
| `data/foldseek/collector_manifest.tsv` | ColabFold run manifest |
| `data/reference_run_cache/` | Materialized reference PDB structures (bundled) |
| `config.yaml` | Pipeline configuration for this demo run |

## How to run

```bash
# 1. Install P2Rank (required for pocket prediction stage):
bash setup.sh --tools-only

# 2. Validate the demo config:
python scripts/vermamg.py plan --config examples/smoke_precomputed/config.yaml

# 3. Run the full pipeline on the 3 demo proteins:
python scripts/vermamg.py run --config examples/smoke_precomputed/config.yaml --resume --follow
```

Outputs land in `runs/smoke_precomputed/smoke_3prot_v1/exports/`.

## Proteins in this demo

| Run ID | Family | Habitat |
|---|---|---|
| T1_Acidiferrobacteraceae_bacterium_...2024893_5 | MTTB | aquatic |
| T1_Acidimicrobiaceae_bacterium_...2024894_6 | ECH\_1 | aquatic |
| T1_Acidimicrobiia_bacterium_...2080302_3 | Aldedh | unknown |

These three proteins were selected to cover diverse functional families (methylthioribose
transferase, enoyl-CoA hydratase, and aldehyde dehydrogenase) from the tier-1
viral AMG candidate set.
