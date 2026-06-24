# VermAMG — Section 9 Pipeline Contracts

This directory freezes the architecture after successful M10F integration.

## Current accepted endpoint

The accepted current endpoint is:

**M10F canonical v6 visual QC**

The old `M10R_C_v6_standard_render` / `v6_standard_portable` branch was deleted and replaced by M10F.

## Core interpretation rule

Primary reference and supporting references are separated.

### Primary reference

The primary reference is the rank-1 / panel_order=1 reference selected by the integrated reference decision layer.

It drives:

- canonical v6 PNG generation
- primary residue-level pocket overlap tables
- primary alignment-pocket classification
- main decision matrix evidence
- primary rulebook evidence

### Supporting references

Supporting references are panel_order 2–5.

They are retained for:

- apo/holo context
- partial-domain warnings
- paralog or functional-shift warnings
- alternative structural support
- ligand/cofactor/manual-review context

They do **not** trigger mass PNG generation.

## Next modules

- M11: supporting reference audit
- M12: decision matrix
- M13: Section 8 rulebook evidence bridge
- M14: results export
- M15: true one-command runner

## Long-term tool vision

The target is a DRAM-V-like self-contained tool where a user provides protein FASTA input and receives a complete `results/` directory containing intermediate outputs, final figures, decision matrix, rulebook evidence, summaries, README files, logs and provenance.
