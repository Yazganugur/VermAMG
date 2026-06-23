# Protein-centric design note

This pipeline is a structural-functional validation and prioritization workflow for candidate proteins.

It is not an upstream annotation-discovery tool.

The minimum required input is:

1. a protein FASTA file;
2. protein identifiers that can be tracked across pipeline steps.

A candidate metadata table is strongly recommended, but most annotation fields are optional.

Pfam, KOfam, DRAM-v, VIBRANT, eggNOG, PHROG, habitat, organism, and viral-neighborhood fields can improve interpretation and reporting, but they are not required for the core structural workflow.

The central biological unit is the protein.

Core workflow:

candidate protein
→ predicted structure
→ structural homolog search
→ reference selection
→ query/reference pocket prediction
→ residue-level pocket comparison
→ visual QC panels
→ decision matrix
→ optional rulebook-based ligand/cofactor/residue interpretation

For the BAPS Faz C v2 use case, the full candidate set corresponds to Tier1 viral-context-supported putative AMG/AVG candidates with rich upstream metadata.

For a general release, users may provide any candidate protein set. If family/annotation labels are absent, the pipeline should fall back to generic labels such as `unknown_family` or `unannotated`.
