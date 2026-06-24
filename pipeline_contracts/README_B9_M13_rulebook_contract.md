# VermAMG — Section 9 / M13 Rulebook Contract

M13 is the ligand/cofactor/motif/known-residue rulebook layer.

The old Section 8 rulebook was calibrated on Pilot32 / 11 families. In the Tier1 full setting, new families and new evidence patterns are expected.

## Core rule

Do not force new families or incompatible evidence patterns into old Pilot32 classes.

## Required behavior

M13 must:

1. classify candidates that match existing Section 8 rules;
2. separate families absent from the existing rulebook;
3. separate cases where a family rule exists but the required evidence is missing;
4. record primary apo/no-ligand cases without penalizing automatically;
5. record supporting holo/ligand/cofactor context as supporting evidence only;
6. suggest where new family-specific, ligand-specific, metal/cofactor-specific, or domain-partial rules may be needed;
7. preserve viral-contig evolutionary caution language.

## Important policy

Supporting references can inform manual review but must not automatically override primary/rank-1 structural decisions.

## Planned outputs

- rulebook_context_collector.tsv
- existing_rulebook_classified.tsv
- rulebook_unmatched_families.tsv
- rulebook_mismatch_reasons.tsv
- rulebook_new_class_suggestions.tsv
- final_rulebook_evidence_matrix.tsv
- rulebook_coverage_qc.tsv
