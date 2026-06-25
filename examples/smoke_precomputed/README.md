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

# 2. Verify the smoke-test dependencies:
python scripts/vermamg_doctor.py --mode smoke

# 3. Run the full pipeline on the 3 demo proteins and validate outputs:
python scripts/run_smoke_test.py
```

Outputs land in `runs/smoke_precomputed/smoke_3prot_v1/exports/`.

## Proteins in this demo

| Demo row | Family | Habitat |
|---|---|---|
| demo protein 1 | MTTB | aquatic |
| demo protein 2 | ECH\_1 | aquatic |
| demo protein 3 | Aldedh | unknown |

These three proteins were selected to cover diverse functional families
(methylthioribose transferase, enoyl-CoA hydratase, and aldehyde dehydrogenase)
from a small precomputed viral AMG demonstration set.
