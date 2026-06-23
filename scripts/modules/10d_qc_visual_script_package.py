#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
from collections import Counter


if len(sys.argv) != 5:
    raise SystemExit(
        "Usage: 10d_qc_visual_script_package.py "
        "MANIFEST ROW_QC SUMMARY_QC POINTER"
    )


manifest_path = Path(sys.argv[1])
row_qc_path = Path(sys.argv[2])
summary_qc_path = Path(sys.argv[3])
pointer_path = Path(sys.argv[4])


def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path, rows, fields):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def exists_file(value):
    return "YES" if value and Path(value).is_file() else "NO"


def read_text(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def is_zero(value):
    try:
        return int(str(value or "0").strip() or "0") == 0
    except ValueError:
        return False


def unreliable_ca_only_qc(row, pml_text, cxc_text):
    if row.get("reference_pocket_signal", "") != "UNRELIABLE_CA_ONLY_INPUT":
        return "NOT_APPLICABLE"

    failures = []
    if row.get("reference_pocket_overlay", "") != "NONE":
        failures.append("REFERENCE_OVERLAY_NOT_NONE")
    if not is_zero(row.get("reference_residue_count_used", "0")):
        failures.append("REFERENCE_RESIDUE_COUNT_NOT_ZERO")

    if is_zero(row.get("query_residue_count_used", "0")):
        if row.get("query_pocket_overlay", "") != "NONE":
            failures.append("QUERY_OVERLAY_PRESENT_WITH_ZERO_RESIDUES")
    elif row.get("query_pocket_overlay", "") != "PRESENT":
        failures.append("QUERY_OVERLAY_NOT_PRESENT")

    forbidden_pml = (
        "show spheres, reference_top1_pocket_residues",
        "color orange, reference_top1_pocket_residues",
        "select reference_top1_pocket_residues, (",
    )
    if any(token in pml_text for token in forbidden_pml):
        failures.append("PML_REFERENCE_POCKET_OVERLAY_PRESENT")

    cxc_lines = cxc_text.splitlines()
    reference_selection_active = False
    for line in cxc_lines:
        clean = line.strip()
        lower = clean.lower()
        if lower.startswith("select "):
            reference_selection_active = "#2" in clean
            if reference_selection_active:
                failures.append("CXC_REFERENCE_SELECTION_PRESENT")
        elif lower.startswith("color sel orange"):
            failures.append("CXC_REFERENCE_COLOR_PRESENT")
        elif reference_selection_active and (
            lower.startswith("style sel sphere")
            or lower.startswith("style sel surface")
            or lower.startswith("surface sel")
        ):
            failures.append("CXC_REFERENCE_POCKET_STYLE_PRESENT")

    if any(f.startswith("CXC_REFERENCE") for f in failures):
        failures.append("CXC_REFERENCE_POCKET_OVERLAY_PRESENT")

    return "PASS" if not failures else "FAIL:" + ",".join(failures)


if not manifest_path.is_file() or manifest_path.stat().st_size == 0:
    raise SystemExit(f"Manifest missing or empty: {manifest_path}")

manifest_rows = read_tsv(manifest_path)
if not manifest_rows:
    raise SystemExit(f"Manifest has no data rows: {manifest_path}")

row_qc_rows = []
for i, row in enumerate(manifest_rows, start=1):
    pml = row.get("pymol_script", "")
    cxc = row.get("chimerax_script", "")
    pml_ok = exists_file(pml)
    cxc_ok = exists_file(cxc)
    query_pdb_ok = exists_file(row.get("query_model_pdb", ""))
    ref_pdb_ok = exists_file(row.get("reference_file_path", ""))
    pml_text = read_text(pml) if pml_ok == "YES" else ""
    cxc_text = read_text(cxc) if cxc_ok == "YES" else ""
    unreliable_qc = unreliable_ca_only_qc(row, pml_text, cxc_text)

    row_status = "PASS"
    if "NO" in (pml_ok, cxc_ok, query_pdb_ok, ref_pdb_ok):
        row_status = "FAIL_MISSING_FILE"
    if unreliable_qc.startswith("FAIL"):
        row_status = "FAIL_UNRELIABLE_CA_ONLY_QC"

    row_qc_rows.append({
        "visual_id": f"VISUAL{ i:05d}",
        "query_id": row.get("query", ""),
        "unique_reference_id": row.get("unique_reference_id", ""),
        "status": row_status,
        "pml_ok": pml_ok,
        "cxc_ok": cxc_ok,
        "query_pdb_ok": query_pdb_ok,
        "ref_pdb_ok": ref_pdb_ok,
        "visual_status": row.get("visual_status", ""),
        "reference_pocket_signal": row.get("reference_pocket_signal", ""),
        "reference_pocket_overlay": row.get("reference_pocket_overlay", ""),
        "query_pocket_overlay": row.get("query_pocket_overlay", ""),
        "unreliable_ca_only_qc": unreliable_qc,
    })

row_fields = [
    "visual_id",
    "query_id",
    "unique_reference_id",
    "status",
    "pml_ok",
    "cxc_ok",
    "query_pdb_ok",
    "ref_pdb_ok",
    "visual_status",
    "reference_pocket_signal",
    "reference_pocket_overlay",
    "query_pocket_overlay",
    "unreliable_ca_only_qc",
]
write_tsv(row_qc_path, row_qc_rows, row_fields)

visual_status_counts = Counter(row.get("visual_status", "") for row in manifest_rows)
signal_counts = Counter(row.get("reference_pocket_signal", "") for row in manifest_rows)
ref_overlay_counts = Counter(row.get("reference_pocket_overlay", "") for row in manifest_rows)
query_overlay_counts = Counter(row.get("query_pocket_overlay", "") for row in manifest_rows)
row_status_counts = Counter(row.get("status", "") for row in row_qc_rows)
unreliable_qc_counts = Counter(row.get("unreliable_ca_only_qc", "") for row in row_qc_rows)

summary_rows = [
    {"metric": "manifest_rows", "value": str(len(manifest_rows))},
    {"metric": "row_qc_rows", "value": str(len(row_qc_rows))},
    {"metric": "pml_missing_rows", "value": str(sum(r["pml_ok"] == "NO" for r in row_qc_rows))},
    {"metric": "cxc_missing_rows", "value": str(sum(r["cxc_ok"] == "NO" for r in row_qc_rows))},
    {"metric": "query_pdb_missing_rows", "value": str(sum(r["query_pdb_ok"] == "NO" for r in row_qc_rows))},
    {"metric": "ref_pdb_missing_rows", "value": str(sum(r["ref_pdb_ok"] == "NO" for r in row_qc_rows))},
]

for key, value in sorted(row_status_counts.items()):
    summary_rows.append({"metric": f"row_status_{key}", "value": str(value)})
for key, value in sorted(visual_status_counts.items()):
    summary_rows.append({"metric": f"visual_status_{key}", "value": str(value)})
for key, value in sorted(signal_counts.items()):
    summary_rows.append({"metric": f"reference_pocket_signal_{key}", "value": str(value)})
for key, value in sorted(ref_overlay_counts.items()):
    summary_rows.append({"metric": f"reference_pocket_overlay_{key}", "value": str(value)})
for key, value in sorted(query_overlay_counts.items()):
    summary_rows.append({"metric": f"query_pocket_overlay_{key}", "value": str(value)})
for key, value in sorted(unreliable_qc_counts.items()):
    summary_rows.append({"metric": f"unreliable_ca_only_qc_{key}", "value": str(value)})

write_tsv(summary_qc_path, summary_rows, ["metric", "value"])

with pointer_path.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["artifact_key", "path", "role"])
    writer.writerow(["visual_script_package_row_qc", str(row_qc_path), "Per-row M10D-lite visual script package QC"])
    writer.writerow(["visual_script_package_summary_qc", str(summary_qc_path), "Summary M10D-lite visual script package QC"])

print("row_qc:", row_qc_path)
print("summary_qc:", summary_qc_path)
print("pointer:", pointer_path)
print("manifest_rows:", len(manifest_rows))
print("row_qc_rows:", len(row_qc_rows))
print("row_status_PASS:", row_status_counts.get("PASS", 0))
