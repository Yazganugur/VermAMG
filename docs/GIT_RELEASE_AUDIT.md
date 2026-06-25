# Git Release Audit

This note records the current split between the local working directory and the
files intended for git.

## Reference Policy

- `D:\VermAMG_archive` is the canonical historical pipeline snapshot.
- It is read-only for migration work.
- `D:\VermAMG` is the git-ready, project-agnostic pipeline.

## Size Split

Current local `D:\VermAMG` contains large ignored runtime assets:

| Path | Approx. size | Git policy |
|---|---:|---|
| `resources/` | 15.1 GB | ignored; installed by `setup.sh` or provided by user |
| `runs/` | 8.4 GB | ignored; per-user outputs |
| `incoming/` | 1.0 GB | ignored; local handoff/input cache |
| tracked files | 8.74 MB | intended git payload |

The large local size is expected while developing with installed databases,
containers, and run outputs. These paths are excluded by `.gitignore`.

## Required External Assets

Git ships source code, contracts, templates, docs, and a small precomputed demo.
It does not ship:

- Foldseek databases
- ColabFold databases
- Apptainer/Singularity containers
- run outputs
- local/private run configs

Use `setup.sh` for standard local installation, or point run configs at existing
shared HPC resources.

## Agnostic Cleanup Completed

- Removed hardcoded M10G smoke protein IDs from submit wrappers.
- Replaced fixed M10G full QC count with contract-derived primary row count.
- Moved the tiny PyMOL wrapper into tracked `scripts/utils/`.
- Kept heavy PyMOL/ColabFold containers outside git.
- Replaced demo `tier1` values with `demo` in the bundled collector manifest.
- Ignored private `run_configs/*.yaml` while keeping tracked example configs.

## Quick Checks

```bash
git status --short
git ls-files | wc -l
python scripts/vermamg.py plan --config examples/smoke_precomputed/config.yaml
bash -n setup.sh
```
