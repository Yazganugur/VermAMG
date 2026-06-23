# VermAMG — Installation Guide

This document explains what external tools and databases VermAMG needs,
where they come from, where they land, and which run-config key to set for each.

`setup.sh` automates steps 1–4. Steps 5–6 are needed only for **live mode**
(running ColabFold + Foldseek from a raw FASTA; precomputed mode and the smoke
demo work without them).

---

## Quick install (precomputed mode + smoke demo)

```bash
git clone <repo-url> VermAMG && cd VermAMG
python3 -m pip install -r requirements.txt
bash setup.sh --tools-only        # installs Foldseek binary + P2Rank
```

Then run the bundled demo:

```bash
python scripts/vermamg.py run --config examples/smoke_precomputed/config.yaml --resume --follow
```

---

## Full install (live structure prediction mode)

```bash
bash setup.sh                     # Foldseek + P2Rank + Foldseek reference DBs
bash setup.sh --with-colabfold-db # also fetches the ColabFold MSA DB (~100 GB)
```

---

## Dependency table

| Component | Purpose | Source | Target path | Approx. size | Run-config key |
|---|---|---|---|---|---|
| **Python ≥ 3.10** | Pipeline runtime | python.org / conda | system | — | — |
| **PyYAML, pandas** | Pipeline deps | `pip install -r requirements.txt` | site-packages | <50 MB | — |
| **Java ≥ 11** | Required by P2Rank | adoptium.net or `apt install default-jre` | system | ~200 MB | `resources.java_bin` |
| **Foldseek binary** | Structural search (live mode) | mmseqs.com/foldseek | `resources/tools/foldseek/bin/foldseek` | ~50 MB | `resources.foldseek_bin` |
| **P2Rank binary** | Binding pocket prediction | github.com/rdk/p2rank/releases | `resources/tools/p2rank/current/prank` (symlink) | ~30 MB | `resources.p2rank_cmd` |
| **Foldseek PDB DB** | PDB structural homologs | `foldseek databases PDB ...` | `resources/databases/foldseek/pdb` | ~11 GB | `resources.pdb_foldseek_db` |
| **Foldseek AFSP DB** | AlphaFold/Swiss-Prot homologs | `foldseek databases Alphafold/Swiss-Prot ...` | `resources/databases/foldseek/alphafold_swissprot` | ~5 GB | `resources.afsp_foldseek_db` |
| **ColabFold MSA DB** | MSA for structure prediction (live) | ColabFold docs | `resources/databases/colabfold/` | ~100 GB | `resources.colabfold_db` |
| **ColabFold container** | Structure prediction (live, GPU) | see ColabFold docs | `resources/containers/colabfold.sif` | ~4 GB | — |

---

## Foldseek binary

`setup.sh` downloads and extracts the Linux AVX2 build automatically:

```bash
bash setup.sh --tools-only
# Binary lands at: resources/tools/foldseek/bin/foldseek
```

For older CPUs without AVX2 support:

```bash
bash setup.sh --tools-only --foldseek-sse2
```

---

## P2Rank

`setup.sh` downloads P2Rank 2.5.1 and creates a version-agnostic directory symlink
(`resources/tools/p2rank/current -> p2rank_2.5.1`) so your config never needs to
encode the version number:

```bash
bash setup.sh --tools-only
# Executable: resources/tools/p2rank/current/prank
# JAR:        resources/tools/p2rank/current/bin/p2rank.jar
```

**Java is required.** If `java -version` fails, install Java 11+:

```bash
# Debian/Ubuntu:
sudo apt install default-jre

# Or download from: https://adoptium.net
```

Run-config (already set this way in the smoke demo and templates):

```yaml
resources:
  java_bin: "java"
  p2rank_cmd: "resources/tools/p2rank/current/prank"
  p2rank_jar: "resources/tools/p2rank/current/bin/p2rank.jar"
```

---

## Foldseek reference databases (live Foldseek mode)

`setup.sh` (without `--tools-only`) downloads both databases:

```bash
bash setup.sh
# PDB DB:  resources/databases/foldseek/pdb
# AFSP DB: resources/databases/foldseek/alphafold_swissprot
```

These are large (~16 GB total) and take time to download. Download is
idempotent — interrupt and re-run safely.

Run-config:

```yaml
resources:
  foldseek_bin: "resources/tools/foldseek/bin/foldseek"
  pdb_foldseek_db:  "resources/databases/foldseek/pdb"
  afsp_foldseek_db: "resources/databases/foldseek/alphafold_swissprot"
```

---

## ColabFold MSA database (live ColabFold mode, optional)

Only needed if you want the pipeline to predict protein structures from a raw
FASTA (i.e., `colabfold.mode: live`). Requires a GPU node.

```bash
bash setup.sh --with-colabfold-db
# Follow the ColabFold DB setup instructions printed by the script.
# Target: resources/databases/colabfold/
```

---

## Disk summary

| Scenario | Approx. total disk needed |
|---|---|
| Smoke demo only (clone + P2Rank) | ~300 MB |
| Precomputed mode (no structure prediction) | ~300 MB |
| Live Foldseek mode (precomputed ColabFold) | ~17 GB |
| Full live mode (ColabFold + Foldseek) | ~120 GB |

---

## HPC / SLURM notes

- Run `setup.sh` on a login node (or dedicate a compute node) that has internet access.
- Module-based HPC environments: load Java and Python modules before running `setup.sh`.
- The `--tools-only` flag skips the large DB downloads; download DBs separately if
  they are available via a shared filesystem mount.
- Use `hpc_slurm_run_v2.yaml.template` for SLURM runs; set `slurm.*` fields for
  your cluster's partition and account.
