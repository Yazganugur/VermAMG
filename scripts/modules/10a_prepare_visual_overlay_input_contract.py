#!/usr/bin/env python3
import csv
import os
import sys
from pathlib import Path
from collections import Counter, defaultdict

# VermAMG portable path helper for visual/render manifests.
# Keeps existing absolute columns unchanged and adds relative/profile-resolvable companion columns.
def vermamg_portable_path(value):
    value = str(value or "")
    if not value:
        return ""

    # Profile-resolvable roots; no hardcoded site-specific absolute paths.
    known_roots = tuple(
        r.rstrip("/") + "/"
        for r in (
            os.environ.get("VERMAMG_ROOT", ""),
            os.environ.get("VERMAMG_DB_ROOT", ""),
        )
        if r
    )

    for root in known_roots:
        if value.startswith(root):
            return value[len(root):]

    return value


if len(sys.argv) != 13:
    raise SystemExit(
        "Usage: 10a_prepare_visual_overlay_input_contract.py "
        "M08_PANEL M08_DECISION QUERY_MANIFEST QUERY_TOP1 REF_RESOLVED REF_UNIQUE REF_TOP1 "
        "VISUAL_CONTRACT VISUAL_QUERY_SUMMARY VISUAL_REF_STATUS QC_REPORT POINTER"
    )

m08_panel_path = Path(sys.argv[1])
m08_decision_path = Path(sys.argv[2])
query_manifest_path = Path(sys.argv[3])
query_top1_path = Path(sys.argv[4])
ref_resolved_path = Path(sys.argv[5])
ref_unique_path = Path(sys.argv[6])
ref_top1_path = Path(sys.argv[7])
visual_contract_path = Path(sys.argv[8])
visual_query_summary_path = Path(sys.argv[9])
visual_ref_status_path = Path(sys.argv[10])
qc_report_path = Path(sys.argv[11])
pointer_path = Path(sys.argv[12])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def local_reference_file_path(rr, rt):
    raw_path = rr.get("reference_file_path", "")
    if raw_path and Path(raw_path).exists():
        return raw_path, "YES"

    source_prediction = rt.get("source_prediction_csv", "")
    if source_prediction and raw_path:
        prediction_path = Path(source_prediction)
        candidate = prediction_path.parent / "visualizations" / "data" / Path(raw_path).name
        if candidate.exists():
            return str(candidate), "YES"

    if raw_path:
        data_root = ref_top1_path.parents[1] / "resolved_unique"
        matches = sorted(data_root.glob(f"*/visualizations/data/{Path(raw_path).name}"))
        matches = [m for m in matches if m.is_file()]
        if len(matches) == 1:
            return str(matches[0]), "YES"

    return raw_path, "NO" if raw_path else rr.get("reference_file_exists", "NO")


def local_query_model_path(qm):
    raw_path = qm.get("query_model_pdb", "")
    if raw_path and Path(raw_path).exists():
        return raw_path, "YES"

    normalized = raw_path.replace("\\", "/")
    marker = "/01_colabfold/outputs/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        candidate = Path("01_colabfold") / "outputs" / Path(suffix)
        if candidate.exists():
            return str(candidate), "YES"

    return raw_path, "NO" if raw_path else qm.get("query_model_pdb_exists", "NO")

m08_panel = read_tsv(m08_panel_path)
m08_decision = read_tsv(m08_decision_path)
query_manifest = read_tsv(query_manifest_path)
query_top1 = read_tsv(query_top1_path)
ref_resolved = read_tsv(ref_resolved_path)
ref_unique = read_tsv(ref_unique_path)
ref_top1 = read_tsv(ref_top1_path)

decision_by_query = {r["query"]: r for r in m08_decision}
query_manifest_by_query = {r["query"]: r for r in query_manifest}
query_top1_by_query = {r["query"]: r for r in query_top1}

# map panel target -> resolved file info at query+layer+target level
ref_resolved_by_key = {
    (r["query"], r["reference_layer"], r["target"]): r for r in ref_resolved
}

# map layer+target -> unique_reference_id/path
unique_by_layer_target = {
    (r["reference_layer"], r["target"]): r for r in ref_unique
}

unique_by_reference_file_path = {
    r.get("reference_file_path", ""): r for r in ref_unique if r.get("reference_file_path", "")
}

ref_top1_by_uid = {r["unique_reference_id"]: r for r in ref_top1}

contract_rows = []
reference_path_fallback_rows = 0
missing_unique_reference_rows = 0

for p in m08_panel:
    q = p["query"]
    layer = p["reference_layer"]
    target = p["target"]

    d = decision_by_query.get(q, {})
    qm = query_manifest_by_query.get(q, {})
    qt = query_top1_by_query.get(q, {})
    resolved_query_model_pdb, resolved_query_model_exists = local_query_model_path(qm)

    rr = ref_resolved_by_key.get((q, layer, target), {})
    unique = unique_by_layer_target.get((layer, target), {})
    if not unique and rr.get("reference_file_path", ""):
        unique = unique_by_reference_file_path.get(rr.get("reference_file_path", ""), {})
        if unique:
            reference_path_fallback_rows += 1
    if not unique:
        missing_unique_reference_rows += 1

    uid = unique.get("unique_reference_id", "")
    rt = ref_top1_by_uid.get(uid, {}) if uid else {}
    reference_pocket_signal = unique.get("reference_pocket_signal", "")
    reference_pocket_interpretation = unique.get("reference_pocket_interpretation", "")
    resolved_reference_file_path, resolved_reference_file_exists = local_reference_file_path(rr, rt)

    ref_status = "CACHE_MISSING"
    if rr.get("reference_file_exists") == "YES":
        ref_status = rt.get("reference_status", "RESOLVED_NO_P2RANK_TOP1")
    elif rr.get("reference_file_resolution_status"):
        ref_status = rr.get("reference_file_resolution_status", "CACHE_MISSING")

    zero_flag = rt.get("zero_pocket_flag", "")
    if ref_status == "NO_POCKETS_OR_EMPTY_OUTPUT":
        zero_flag = "YES"

    contract_rows.append({
        "query": q,
        "protein_id": p.get("protein_id", ""),
        "family": p.get("family", ""),
        "panel_order": p.get("panel_order", ""),
        "panel_role": p.get("panel_role", ""),
        "reference_layer": layer,
        "target": target,
        "source_rank": p.get("source_rank", ""),
        "support_class": p.get("support_class", ""),
        "selection_reason": p.get("selection_reason", ""),

        "primary_reference_layer": d.get("primary_reference_layer", ""),
        "primary_reference_target": d.get("primary_reference_target", ""),
        "manual_review_level": d.get("manual_review_level", ""),
        "manual_review_flags": d.get("manual_review_flags", ""),

        "query_model_pdb": resolved_query_model_pdb,

        "query_model_pdb_portable": vermamg_portable_path(resolved_query_model_pdb),
        "query_model_pdb_exists": resolved_query_model_exists,
        "query_top1_pocket_name": qt.get("pocket_name", ""),
        "query_top1_score": qt.get("top1_score", ""),
        "query_top1_probability": qt.get("top1_probability", ""),
        "query_top1_residue_ids": qt.get("top1_residue_ids", ""),
        "query_prediction_csv": qt.get("source_prediction_csv", ""),
        "query_prediction_csv_portable": vermamg_portable_path(qt.get("source_prediction_csv", "")),
        "query_residue_csv": qt.get("source_residue_csv", ""),

        "query_residue_csv_portable": vermamg_portable_path(qt.get("source_residue_csv", "")),
        "reference_file_path": resolved_reference_file_path,
        "reference_file_path_portable": vermamg_portable_path(resolved_reference_file_path),
        "reference_file_exists": resolved_reference_file_exists,
        "reference_file_resolution_status": rr.get("reference_file_resolution_status", "CACHE_MISSING"),
        "unique_reference_id": uid,
        "reference_p2rank_status": rt.get("reference_status", ref_status),
        "reference_zero_pocket_flag": zero_flag,
        "reference_atom_count": unique.get("atom_count", ""),
        "reference_residue_count_est": unique.get("residue_count_est", ""),
        "reference_ca_only_like": unique.get("ca_only_like", ""),
        "reference_pocket_signal": reference_pocket_signal,
        "reference_pocket_interpretation": reference_pocket_interpretation,
        "reference_top1_pocket_name": rt.get("pocket_name", ""),
        "reference_top1_score": rt.get("top1_score", ""),
        "reference_top1_probability": rt.get("top1_probability", ""),
        "reference_top1_residue_ids": rt.get("top1_residue_ids", ""),
        "reference_prediction_csv": rt.get("source_prediction_csv", ""),
        "reference_prediction_csv_portable": vermamg_portable_path(rt.get("source_prediction_csv", "")),
        "reference_residue_csv": rt.get("source_residue_csv", ""),

        "reference_residue_csv_portable": vermamg_portable_path(rt.get("source_residue_csv", "")),
        "visual_status": (
            "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"
            if resolved_query_model_exists == "YES" and resolved_reference_file_exists == "YES" and reference_pocket_signal == "UNRELIABLE_CA_ONLY_INPUT"
            else
            "READY_QUERY_AND_REFERENCE"
            if resolved_query_model_exists == "YES" and resolved_reference_file_exists == "YES" and zero_flag != "YES"
            else "READY_QUERY_REFERENCE_ZERO_POCKET"
            if resolved_query_model_exists == "YES" and resolved_reference_file_exists == "YES" and zero_flag == "YES"
            else "READY_QUERY_ONLY_REFERENCE_CACHE_MISSING"
            if resolved_query_model_exists == "YES"
            else "BLOCKED_QUERY_MODEL_MISSING"
        )
    })

contract_fields = [
    "query","protein_id","family","panel_order","panel_role",
    "reference_layer","target","source_rank","support_class","selection_reason",
    "primary_reference_layer","primary_reference_target","manual_review_level","manual_review_flags",
    "query_model_pdb","query_model_pdb_portable","query_model_pdb_exists",
    "query_top1_pocket_name","query_top1_score","query_top1_probability","query_top1_residue_ids",
    "query_prediction_csv","query_prediction_csv_portable","query_residue_csv","query_residue_csv_portable",
    "reference_file_path","reference_file_path_portable","reference_file_exists","reference_file_resolution_status",
    "unique_reference_id","reference_p2rank_status","reference_zero_pocket_flag",
    "reference_atom_count","reference_residue_count_est","reference_ca_only_like",
    "reference_pocket_signal","reference_pocket_interpretation",
    "reference_top1_pocket_name","reference_top1_score","reference_top1_probability","reference_top1_residue_ids",
    "reference_prediction_csv","reference_prediction_csv_portable","reference_residue_csv","reference_residue_csv_portable","visual_status",
]

write_tsv(visual_contract_path, contract_rows, contract_fields)

# Query-level summary
by_query = defaultdict(list)
for r in contract_rows:
    by_query[r["query"]].append(r)

query_summary_rows = []
for q, rows in sorted(by_query.items()):
    status_counts = Counter(r["visual_status"] for r in rows)
    query_summary_rows.append({
        "query": q,
        "protein_id": rows[0]["protein_id"],
        "family": rows[0]["family"],
        "primary_reference_layer": rows[0]["primary_reference_layer"],
        "primary_reference_target": rows[0]["primary_reference_target"],
        "manual_review_level": rows[0]["manual_review_level"],
        "panel_rows": len(rows),
        "ready_query_and_reference": status_counts.get("READY_QUERY_AND_REFERENCE", 0),
        "ready_query_reference_zero_pocket": status_counts.get("READY_QUERY_REFERENCE_ZERO_POCKET", 0),
        "ready_query_reference_unreliable_ca_only": status_counts.get("READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY", 0),
        "ready_query_only_reference_cache_missing": status_counts.get("READY_QUERY_ONLY_REFERENCE_CACHE_MISSING", 0),
        "blocked_query_model_missing": status_counts.get("BLOCKED_QUERY_MODEL_MISSING", 0),
        "query_top1_score": rows[0]["query_top1_score"],
        "query_top1_probability": rows[0]["query_top1_probability"],
    })

query_summary_fields = [
    "query","protein_id","family",
    "primary_reference_layer","primary_reference_target","manual_review_level",
    "panel_rows","ready_query_and_reference","ready_query_reference_zero_pocket",
    "ready_query_reference_unreliable_ca_only",
    "ready_query_only_reference_cache_missing","blocked_query_model_missing",
    "query_top1_score","query_top1_probability",
]
write_tsv(visual_query_summary_path, query_summary_rows, query_summary_fields)

status_counts = Counter()
layer_counts = Counter()
for r in contract_rows:
    status_counts[r["visual_status"]] += 1
    layer_counts[(r["reference_layer"], r["visual_status"])] += 1

status_rows = []
for key, val in sorted(status_counts.items()):
    status_rows.append({
        "summary_type": "visual_status",
        "reference_layer": "ALL",
        "status": key,
        "n": val,
    })

for (layer, status), val in sorted(layer_counts.items()):
    status_rows.append({
        "summary_type": "layer_visual_status",
        "reference_layer": layer,
        "status": status,
        "n": val,
    })

status_fields = ["summary_type","reference_layer","status","n"]
write_tsv(visual_ref_status_path, status_rows, status_fields)

qc = Counter()
qc["contract_rows"] = len(contract_rows)
qc["query_count"] = len(by_query)
qc["query_summary_rows"] = len(query_summary_rows)
qc["visual_status_summary_rows"] = len(status_rows)
for r in contract_rows:
    qc[f"visual_status_{r['visual_status']}"] += 1
qc["duplicate_query_layer_target"] = len(contract_rows) - len(set((r["query"], r["reference_layer"], r["target"]) for r in contract_rows))
qc["query_models_missing"] = sum(1 for r in contract_rows if r["query_model_pdb_exists"] != "YES")
qc["reference_unique_path_fallback_rows"] = reference_path_fallback_rows
qc["reference_unique_missing_rows"] = missing_unique_reference_rows

with qc_report_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    for k in sorted(qc):
        w.writerow([k, qc[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["visual_overlay_input_contract", str(visual_contract_path), "One row per query-reference panel pair for M10 visual/overlay"])
    w.writerow(["visual_overlay_query_summary", str(visual_query_summary_path), "One row per query summarizing visual readiness"])
    w.writerow(["visual_overlay_reference_status_summary", str(visual_ref_status_path), "M10 visual readiness status counts"])
    w.writerow(["visual_overlay_input_contract_qc_report", str(qc_report_path), "M10A contract QC report"])

print("visual_contract:", visual_contract_path)
print("query_summary:", visual_query_summary_path)
print("ref_status_summary:", visual_ref_status_path)
print("qc_report:", qc_report_path)
print("pointer:", pointer_path)
print("contract_rows:", len(contract_rows))
print("query_summary_rows:", len(query_summary_rows))
print("duplicate_query_layer_target:", qc["duplicate_query_layer_target"])
