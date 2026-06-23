#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
from collections import defaultdict, Counter

if len(sys.argv) != 8:
    raise SystemExit(
        "Usage: 09e_merge_query_p2rank_outputs.py "
        "RUN_MANIFEST PRED_MERGED RES_MERGED TOP1_TABLE FAMILY_SUMMARY QC_REPORT POINTER"
    )

run_manifest_path = Path(sys.argv[1])
pred_merged_path = Path(sys.argv[2])
res_merged_path = Path(sys.argv[3])
top1_path = Path(sys.argv[4])
family_summary_path = Path(sys.argv[5])
qc_report_path = Path(sys.argv[6])
pointer_path = Path(sys.argv[7])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def clean_dict(row):
    return {(k or "").strip(): (v or "").strip() for k, v in row.items()}

def read_p2rank_csv(path):
    with Path(path).open() as f:
        return [clean_dict(r) for r in csv.DictReader(f)]

def fnum(x):
    try:
        return float(x)
    except Exception:
        return 0.0

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

manifest = read_tsv(run_manifest_path)

pred_rows = []
res_rows = []
top1_rows = []

for m in manifest:
    query = m["query"]
    family = m["family"]
    status = m["status"]
    pred_csv = Path(m["prediction_csv"])
    res_csv = Path(m["residue_csv"])

    if status != "OK":
        continue

    pred_data = read_p2rank_csv(pred_csv)
    for r in pred_data:
        out = {
            "query": query,
            "family": family,
            "source_prediction_csv": str(pred_csv),
            "pocket_name": r.get("name", ""),
            "pocket_rank": r.get("rank", ""),
            "score": r.get("score", ""),
            "probability": r.get("probability", ""),
            "sas_points": r.get("sas_points", ""),
            "surf_atoms": r.get("surf_atoms", ""),
            "center_x": r.get("center_x", ""),
            "center_y": r.get("center_y", ""),
            "center_z": r.get("center_z", ""),
            "residue_ids": r.get("residue_ids", ""),
            "surf_atom_ids": r.get("surf_atom_ids", ""),
        }
        pred_rows.append(out)

    if pred_data:
        r = sorted(pred_data, key=lambda x: int(x.get("rank", "999") or 999))[0]
        top1_rows.append({
            "query": query,
            "family": family,
            "pocket_name": r.get("name", ""),
            "pocket_rank": r.get("rank", ""),
            "top1_score": r.get("score", ""),
            "top1_probability": r.get("probability", ""),
            "top1_sas_points": r.get("sas_points", ""),
            "top1_surf_atoms": r.get("surf_atoms", ""),
            "top1_center_x": r.get("center_x", ""),
            "top1_center_y": r.get("center_y", ""),
            "top1_center_z": r.get("center_z", ""),
            "top1_residue_ids": r.get("residue_ids", ""),
            "source_prediction_csv": str(pred_csv),
            "source_residue_csv": str(res_csv),
        })

    res_data = read_p2rank_csv(res_csv)
    for r in res_data:
        out = {
            "query": query,
            "family": family,
            "source_residue_csv": str(res_csv),
            "chain": r.get("chain", ""),
            "residue_label": r.get("residue_label", ""),
            "residue_name": r.get("residue_name", ""),
            "score": r.get("score", ""),
            "zscore": r.get("zscore", ""),
            "probability": r.get("probability", ""),
            "pocket": r.get("pocket", ""),
        }
        res_rows.append(out)

pred_fields = [
    "query","family","source_prediction_csv",
    "pocket_name","pocket_rank","score","probability",
    "sas_points","surf_atoms",
    "center_x","center_y","center_z",
    "residue_ids","surf_atom_ids",
]

res_fields = [
    "query","family","source_residue_csv",
    "chain","residue_label","residue_name",
    "score","zscore","probability","pocket",
]

top1_fields = [
    "query","family","pocket_name","pocket_rank",
    "top1_score","top1_probability",
    "top1_sas_points","top1_surf_atoms",
    "top1_center_x","top1_center_y","top1_center_z",
    "top1_residue_ids",
    "source_prediction_csv","source_residue_csv",
]

write_tsv(pred_merged_path, pred_rows, pred_fields)
write_tsv(res_merged_path, res_rows, res_fields)
write_tsv(top1_path, top1_rows, top1_fields)

# Family summary
by_family = defaultdict(list)
for r in top1_rows:
    by_family[r["family"]].append(r)

family_rows = []
for fam, rows in sorted(by_family.items()):
    scores = [fnum(r["top1_score"]) for r in rows]
    probs = [fnum(r["top1_probability"]) for r in rows]
    pocket_counts = []
    for q in {r["query"] for r in rows}:
        pocket_counts.append(sum(1 for p in pred_rows if p["query"] == q))

    family_rows.append({
        "family": fam,
        "n_queries": len(rows),
        "mean_top1_score": round(sum(scores) / len(scores), 4) if scores else "",
        "min_top1_score": round(min(scores), 4) if scores else "",
        "max_top1_score": round(max(scores), 4) if scores else "",
        "mean_top1_probability": round(sum(probs) / len(probs), 4) if probs else "",
        "min_top1_probability": round(min(probs), 4) if probs else "",
        "max_top1_probability": round(max(probs), 4) if probs else "",
        "mean_pocket_count": round(sum(pocket_counts) / len(pocket_counts), 4) if pocket_counts else "",
        "min_pocket_count": min(pocket_counts) if pocket_counts else "",
        "max_pocket_count": max(pocket_counts) if pocket_counts else "",
    })

family_fields = [
    "family","n_queries",
    "mean_top1_score","min_top1_score","max_top1_score",
    "mean_top1_probability","min_top1_probability","max_top1_probability",
    "mean_pocket_count","min_pocket_count","max_pocket_count",
]

write_tsv(family_summary_path, family_rows, family_fields)

# QC report
qc = Counter()
qc["manifest_records"] = len(manifest)
qc["manifest_ok_records"] = sum(1 for m in manifest if m["status"] == "OK")
qc["merged_prediction_rows"] = len(pred_rows)
qc["merged_residue_rows"] = len(res_rows)
qc["top1_rows"] = len(top1_rows)
qc["family_summary_rows"] = len(family_rows)
qc["queries_with_prediction_rows"] = len({r["query"] for r in pred_rows})
qc["queries_with_residue_rows"] = len({r["query"] for r in res_rows})
qc["queries_with_top1"] = len({r["query"] for r in top1_rows})
qc["zero_prediction_queries"] = len(set(m["query"] for m in manifest) - set(r["query"] for r in pred_rows))

with qc_report_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    for k in sorted(qc):
        w.writerow([k, qc[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["query_p2rank_predictions_merged", str(pred_merged_path), "Merged query-model P2Rank pocket predictions"])
    w.writerow(["query_p2rank_residues_merged", str(res_merged_path), "Merged query-model P2Rank residue-level scores"])
    w.writerow(["query_p2rank_top1_pockets", str(top1_path), "Top-ranked pocket per query model"])
    w.writerow(["query_p2rank_family_summary", str(family_summary_path), "Family-level query pocket summary"])
    w.writerow(["query_p2rank_merge_qc_report", str(qc_report_path), "M09E merge QC report"])

print("pred_merged:", pred_merged_path)
print("res_merged:", res_merged_path)
print("top1:", top1_path)
print("family_summary:", family_summary_path)
print("qc_report:", qc_report_path)
print("pointer:", pointer_path)
print("merged_prediction_rows:", len(pred_rows))
print("merged_residue_rows:", len(res_rows))
print("top1_rows:", len(top1_rows))
print("family_summary_rows:", len(family_rows))
