#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

try:
    from Bio.PDB import MMCIFParser
except ImportError:  # pragma: no cover
    MMCIFParser = None

if len(sys.argv) != 5:
    raise SystemExit(
        "Usage: 09f_make_reference_pocket_counts.py "
        "RUN_MANIFEST OUT_COUNTS OUT_ZERO_QC OUT_POINTER"
    )


run_manifest_path = Path(sys.argv[1])
out_counts_path = Path(sys.argv[2])
out_zero_qc_path = Path(sys.argv[3])
out_pointer_path = Path(sys.argv[4])


def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def clean_int(value):
    try:
        return int(str(value or "0").strip() or "0")
    except ValueError:
        return 0


def atom_residue_sanity(path):
    p = Path(path)
    if p.suffix.lower() in {".cif", ".mmcif"}:
        if MMCIFParser is None:
            return 0, 0, "UNKNOWN"
        try:
            structure = MMCIFParser(QUIET=True).get_structure(p.stem, str(p))
        except Exception:
            return 0, 0, "UNKNOWN"
        atom_count = 0
        ca_count = 0
        residue_keys = set()
        for atom in structure.get_atoms():
            residue = atom.get_parent()
            chain = residue.get_parent()
            atom_count += 1
            if atom.get_name().strip() == "CA":
                ca_count += 1
            residue_keys.add((chain.id, str(residue.id[1]), residue.id[2].strip()))
        residue_count = len(residue_keys)
        ca_only_like = (
            "YES"
            if atom_count > 0 and ca_count == atom_count
            else "NO"
        )
        return atom_count, residue_count, ca_only_like

    atom_count = 0
    ca_count = 0
    residue_keys = set()
    try:
        with p.open() as f:
            for line in f:
                if not (line.startswith("ATOM") or line.startswith("HETATM")):
                    continue
                atom_count += 1
                atom_name = line[12:16].strip() if len(line) >= 16 else ""
                if atom_name == "CA":
                    ca_count += 1
                chain = line[21:22].strip() if len(line) >= 22 else ""
                resseq = line[22:26].strip() if len(line) >= 26 else ""
                icode = line[26:27].strip() if len(line) >= 27 else ""
                if chain or resseq:
                    residue_keys.add((chain, resseq, icode))
    except OSError:
        return 0, 0, "UNKNOWN"

    residue_count = len(residue_keys)
    ca_only_like = (
        "YES"
        if atom_count > 0 and ca_count == atom_count
        else "NO"
    )
    return atom_count, residue_count, ca_only_like


def pocket_signal(status, pocket_rows, ca_only_like):
    if status != "OK":
        return "UNKNOWN", "P2RANK_FAILED_OR_INPUT_MISSING"
    if pocket_rows > 0:
        return "PRESENT", "POSITIVE_POCKET_SIGNAL"
    if ca_only_like == "YES":
        return "UNRELIABLE_CA_ONLY_INPUT", "NOT_BIOLOGICAL_ABSENCE"
    return "ABSENT", "NO_POCKET_PREDICTED_FULL_ATOM"


def write_tsv(path, rows, fields):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


manifest_rows = read_tsv(run_manifest_path)

count_fields = [
    "unique_reference_id",
    "reference_layer",
    "target",
    "reference_file_path",
    "status",
    "prediction_csv",
    "residue_csv",
    "pocket_rows",
    "atom_count",
    "residue_count_est",
    "ca_only_like",
    "reference_pocket_signal",
    "reference_pocket_interpretation",
]

count_rows = []
for row in manifest_rows:
    pocket_rows = clean_int(row.get("pocket_rows", "0"))
    atom_count, residue_count_est, ca_only_like = atom_residue_sanity(row.get("reference_file_path", ""))
    reference_pocket_signal, reference_pocket_interpretation = pocket_signal(
        row.get("status", ""),
        pocket_rows,
        ca_only_like,
    )
    count_rows.append({
        "unique_reference_id": row.get("unique_reference_id", ""),
        "reference_layer": row.get("reference_layer", ""),
        "target": row.get("target", ""),
        "reference_file_path": row.get("reference_file_path", ""),
        "status": row.get("status", ""),
        "prediction_csv": row.get("prediction_csv", ""),
        "residue_csv": row.get("residue_csv", ""),
        "pocket_rows": str(pocket_rows),
        "atom_count": str(atom_count),
        "residue_count_est": str(residue_count_est),
        "ca_only_like": ca_only_like,
        "reference_pocket_signal": reference_pocket_signal,
        "reference_pocket_interpretation": reference_pocket_interpretation,
    })

total_references = len(count_rows)
ok_references = sum(1 for row in count_rows if row["status"] == "OK")
zero_pocket_references = sum(
    1 for row in count_rows
    if row["status"] == "OK" and clean_int(row["pocket_rows"]) == 0
)
nonzero_pocket_references = sum(
    1 for row in count_rows
    if row["status"] == "OK" and clean_int(row["pocket_rows"]) > 0
)
failed_references = total_references - ok_references
ca_only_like_references = sum(1 for row in count_rows if row["ca_only_like"] == "YES")

write_tsv(out_counts_path, count_rows, count_fields)

with out_zero_qc_path.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerow(["total_references", total_references])
    writer.writerow(["ok_references", ok_references])
    writer.writerow(["zero_pocket_references", zero_pocket_references])
    writer.writerow(["nonzero_pocket_references", nonzero_pocket_references])
    writer.writerow(["failed_references", failed_references])
    writer.writerow(["ca_only_like_references", ca_only_like_references])

with out_pointer_path.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["artifact_key", "path", "role"])
    writer.writerow([
        "reference_resolved_unique_pocket_counts",
        str(out_counts_path),
        "Pocket-count table for resolved unique reference structures",
    ])
    writer.writerow([
        "reference_resolved_unique_zero_pocket_qc",
        str(out_zero_qc_path),
        "Zero-pocket QC metrics for resolved unique reference structures",
    ])

print("counts:", out_counts_path)
print("zero_qc:", out_zero_qc_path)
print("pointer:", out_pointer_path)
print("total_references:", total_references)
print("ok_references:", ok_references)
print("zero_pocket_references:", zero_pocket_references)
print("nonzero_pocket_references:", nonzero_pocket_references)
print("failed_references:", failed_references)
print("ca_only_like_references:", ca_only_like_references)
