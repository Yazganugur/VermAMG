#!/usr/bin/env python3
import csv
from pathlib import Path
import sys

project = Path("/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full")
table = project / "00_inputs" / "tier1_amg_with_habitat.tsv"
fasta = project / "00_inputs" / "tier1_amg.faa"

required_columns = ["protein_id"]
annotation_columns = [
    "family_label",
    "custom_annotation",
    "pfam_name",
    "pfam_acc",
    "kofam_ko_id",
    "dram_ko_id",
    "vibrant_ko_id",
    "eggnog_cog",
    "eggnog_kegg_ko",
]

with table.open() as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader)
    rows = list(reader)

cols = set(header)

print("table:", table)
print("n_rows:", len(rows))
print("n_columns:", len(header))
print("columns:")
for i, c in enumerate(header, 1):
    print(f"{i}\t{c}")

errors = []
warnings = []

for c in required_columns:
    if c not in cols:
        errors.append(f"Missing required column: {c}")

if not any(c in cols for c in annotation_columns):
    warnings.append(
        "No annotation/family columns found. Core structural workflow can run, "
        "but family-level summaries will use unknown_family/unannotated labels."
    )

protein_ids = [r[header.index("protein_id")] for r in rows] if "protein_id" in cols else []
unique_ids = set(protein_ids)

print("n_protein_ids:", len(protein_ids))
print("n_unique_protein_ids:", len(unique_ids))

fasta_headers = []
with fasta.open() as f:
    for line in f:
        if line.startswith(">"):
            h = line[1:].strip().split()[0]
            h_core = h.split("|")[0]
            fasta_headers.append(h_core)

fasta_ids = set(fasta_headers)

print("fasta_proteins:", len(fasta_headers))
print("fasta_unique_ids:", len(fasta_ids))

missing_in_fasta = sorted(unique_ids - fasta_ids)
extra_in_fasta = sorted(fasta_ids - unique_ids)

print("missing_table_ids_in_fasta:", len(missing_in_fasta))
print("extra_fasta_ids_not_in_table:", len(extra_in_fasta))

if missing_in_fasta:
    errors.append("Some table protein_id values are missing from FASTA.")

if extra_in_fasta:
    errors.append("Some FASTA IDs are not present in table protein_id.")

if warnings:
    print("SCHEMA_WARNINGS:")
    for w in warnings:
        print("WARNING:", w)

if errors:
    print("SCHEMA_CHECK: FAIL")
    for e in errors:
        print("ERROR:", e)
    sys.exit(1)

print("SCHEMA_CHECK: OK")
