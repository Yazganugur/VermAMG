#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
from collections import Counter

if len(sys.argv) != 9:
    raise SystemExit(
        "Usage: 09_prepare_p2rank_input_manifests.py "
        "QUERY_MANIFEST M08_DECISION M08_PANEL QUERY_OUT REF_OUT RESOLUTION_REPORT SUMMARY POINTER"
    )

query_manifest_path = Path(sys.argv[1])
m08_decision_path = Path(sys.argv[2])
m08_panel_path = Path(sys.argv[3])
query_out_path = Path(sys.argv[4])
ref_out_path = Path(sys.argv[5])
resolution_report_path = Path(sys.argv[6])
summary_path = Path(sys.argv[7])
pointer_path = Path(sys.argv[8])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def safe_exists(p):
    try:
        return Path(p).exists()
    except Exception:
        return False

query_rows = read_tsv(query_manifest_path)
decision_rows = read_tsv(m08_decision_path)
panel_rows = read_tsv(m08_panel_path)

decision_by_query = {r["query"]: r for r in decision_rows}

query_out_rows = []
for r in query_rows:
    q = r["run_id"]
    d = decision_by_query.get(q, {})
    pdb_path = r.get("query_pdb_file", "")
    query_out_rows.append({
        "mode": r.get("mode", ""),
        "query": q,
        "protein_id": r.get("protein_id", ""),
        "family": r.get("family_label", ""),
        "query_model_pdb": pdb_path,
        "query_model_pdb_exists": "YES" if safe_exists(pdb_path) else "NO",
        "colabfold_plddt_mean": r.get("colabfold_plddt_mean", ""),
        "colabfold_ptm": r.get("colabfold_ptm", ""),
        "colabfold_struct_conf_class": r.get("colabfold_struct_conf_class", ""),
        "primary_reference_layer": d.get("primary_reference_layer", ""),
        "primary_reference_target": d.get("primary_reference_target", ""),
        "primary_reference_class": d.get("primary_reference_class", ""),
        "manual_review_level": d.get("manual_review_level", ""),
        "manual_review_flags": d.get("manual_review_flags", ""),
        "p2rank_role": "QUERY_MODEL",
    })

# Reference panel file resolution:
# At this stage target IDs are Foldseek database IDs, not guaranteed local file paths.
# We preserve target IDs and explicitly mark file resolution as pending.
ref_out_rows = []
resolution_rows = []

for r in panel_rows:
    layer = r.get("reference_layer", "")
    target = r.get("target", "")
    query = r.get("query", "")

    ref_row = {
        "query": query,
        "protein_id": r.get("protein_id", ""),
        "family": r.get("family", ""),
        "panel_order": r.get("panel_order", ""),
        "reference_layer": layer,
        "panel_role": r.get("panel_role", ""),
        "source_rank": r.get("source_rank", ""),
        "target": target,
        "support_class": r.get("support_class", ""),
        "selection_reason": r.get("selection_reason", ""),
        "reference_file_path": "",
        "reference_file_exists": "NO",
        "reference_file_resolution_status": "PENDING_REFERENCE_EXTRACTION",
        "p2rank_role": "REFERENCE_PANEL_TARGET",
    }
    ref_out_rows.append(ref_row)

    resolution_rows.append({
        "query": query,
        "reference_layer": layer,
        "target": target,
        "resolution_status": "PENDING_REFERENCE_EXTRACTION",
        "comment": "Foldseek target ID recorded; local PDB/mmCIF source file must be resolved/extracted before reference P2Rank/overlay.",
    })

query_fields = [
    "mode","query","protein_id","family",
    "query_model_pdb","query_model_pdb_exists",
    "colabfold_plddt_mean","colabfold_ptm","colabfold_struct_conf_class",
    "primary_reference_layer","primary_reference_target","primary_reference_class",
    "manual_review_level","manual_review_flags","p2rank_role",
]

ref_fields = [
    "query","protein_id","family","panel_order",
    "reference_layer","panel_role","source_rank","target",
    "support_class","selection_reason",
    "reference_file_path","reference_file_exists","reference_file_resolution_status",
    "p2rank_role",
]

resolution_fields = ["query","reference_layer","target","resolution_status","comment"]

write_tsv(query_out_path, query_out_rows, query_fields)
write_tsv(ref_out_path, ref_out_rows, ref_fields)
write_tsv(resolution_report_path, resolution_rows, resolution_fields)

summary = Counter()
summary["query_records"] = len(query_out_rows)
summary["query_model_pdb_exists_yes"] = sum(1 for r in query_out_rows if r["query_model_pdb_exists"] == "YES")
summary["query_model_pdb_exists_no"] = sum(1 for r in query_out_rows if r["query_model_pdb_exists"] != "YES")
summary["reference_panel_records"] = len(ref_out_rows)
summary["reference_file_resolved_yes"] = sum(1 for r in ref_out_rows if r["reference_file_exists"] == "YES")
summary["reference_file_resolution_pending"] = sum(1 for r in ref_out_rows if r["reference_file_resolution_status"] == "PENDING_REFERENCE_EXTRACTION")

for r in query_out_rows:
    summary[f"primary_reference_layer_{r['primary_reference_layer']}"] += 1
    summary[f"manual_review_{r['manual_review_level']}"] += 1

with summary_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    for k in sorted(summary):
        w.writerow([k, summary[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["p2rank_query_model_manifest", str(query_out_path), "Query ColabFold PDB models to be processed by P2Rank"])
    w.writerow(["p2rank_reference_panel_manifest", str(ref_out_path), "M08-selected reference panel targets; file resolution pending"])
    w.writerow(["reference_panel_file_resolution_report", str(resolution_report_path), "Reference target ID to local structure file resolution status"])
    w.writerow(["p2rank_input_manifest_summary", str(summary_path), "M09 P2Rank input preparation summary"])

print("query_manifest_out:", query_out_path)
print("reference_panel_manifest_out:", ref_out_path)
print("resolution_report:", resolution_report_path)
print("summary:", summary_path)
print("pointer:", pointer_path)
print("query_records:", len(query_out_rows))
print("reference_panel_records:", len(ref_out_rows))
print("query_model_pdb_exists_yes:", summary["query_model_pdb_exists_yes"])
print("reference_file_resolution_pending:", summary["reference_file_resolution_pending"])
