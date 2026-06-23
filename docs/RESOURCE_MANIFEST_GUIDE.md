# Resource Manifest Guide

Main manifest:

    config/resource_manifest.tsv

This file records external tools, databases, containers, and render dependencies.

## Important resource classes

- tool_binary
- tool_p2rank
- tool_pymol_render_env
- large_structure_database
- container

## Current major resources

- Foldseek binary
- P2Rank home and jar
- PDB Foldseek DB prefix and sidecars
- AlphaFold SwissProt Foldseek DB prefix and sidecars
- Full-atom PDB/mmCIF source/cache for reference materialization
- Full-atom AlphaFold/AFSP PDB source/cache for reference materialization
- ColabFold Apptainer/SIF container
- PyMOL Apptainer/SIF container
- PyMOL wrapper
- PyMOL Python dependencies / Pillow site-packages

## Rules

1. Manifest is the source of truth for managed external resources.
2. Large structure databases are multi-file prefix resources.
3. Do not copy DB prefixes blindly; include sidecar files.
4. Containers can be pointer/checksum-managed before optional copying.
5. Resource QC must pass before master proceeds.
6. Local profile should eventually point to local mirror paths, not TRUBA paths.

## Foldseek DB vs full-atom reference sources

Foldseek database exports can be CA-only-like and are acceptable for structural
search/matching context. They are not acceptable as reference inputs for:

- reference P2Rank
- reference-pocket interpretation
- ligand/contact context
- residue-level pocket comparison
- visual residue QC

Reference materialization must use full-atom sources:

- PDB targets: full-atom PDB/mmCIF source/cache, followed by chain-specific
  full-atom extraction when needed.
- AFSP targets: full-atom AlphaFold/AFSP PDB source/cache.

The reference atom-name guard should fail before reference P2Rank if a
materialized reference is CA-only-like, unless an explicit diagnostic CA-only
mode is requested.
