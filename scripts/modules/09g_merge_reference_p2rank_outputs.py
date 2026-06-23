#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
from collections import defaultdict, Counter

if len(sys.argv) != 8:
    raise SystemExit(
        "Usage: 09g_merge_reference_p2rank_outputs.py "
        "RUN_MANIFEST PRED_MERGED RES_MERGED TOP1_TABLE LAYER_SUMMARY QC_REPORT POINTER"
    )

run_manifest_path = Path(sys.argv[1])
pred_merged_path = Path(sys.argv[2])
res_merged_path = Path(sys.argv[3])
top1_path = Path(sys.argv[4])
layer_summary_path = Path(sys.argv[5])
qc_report_path = Path(sys.argv[6])
pointer_path = Path(sys.argv[7])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def clean_dict(row):
    return {(k or "").strip(): (v or "").strip() for k, v in row.items()}

def read_p2rank_csv(path):
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return []
    with p.open() as f:
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
    uid = m["unique_reference_id"]
    layer = m["reference_layer"]
    target = m["target"]
    ref_path = m["reference_file_path"]
    status = m["status"]
    pred_csv = Path(m["prediction_csv"])
    res_csv = Path(m["residue_csv"])
    pocket_rows = int(m.get("pocket_rows", "0") or 0)

    pred_data = read_p2rank_csv(pred_csv)
    for r in pred_data:
        pred_rows.append({
            "unique_reference_id": uid,
            "reference_layer": layer,
            "target": target,
            "reference_status": status,
            "reference_file_path": ref_path,
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
        })

    if pred_data:
        r = sorted(pred_data, key=lambda x: int(x.get("rank", "999") or 999))[0]
        top1_rows.append({
            "unique_reference_id": uid,
            "reference_layer": layer,
            "target": target,
            "reference_status": status,
            "reference_file_path": ref_path,
            "pocket_rows": pocket_rows,
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
            "zero_pocket_flag": "NO",
        })
    else:
        top1_rows.append({
            "unique_reference_id": uid,
            "reference_layer": layer,
            "target": target,
            "reference_status": status,
            "reference_file_path": ref_path,
            "pocket_rows": pocket_rows,
            "pocket_name": "",
            "pocket_rank": "",
            "top1_score": "",
            "top1_probability": "",
            "top1_sas_points": "",
            "top1_surf_atoms": "",
            "top1_center_x": "",
            "top1_center_y": "",
            "top1_center_z": "",
            "top1_residue_ids": "",
            "source_prediction_csv": str(pred_csv),
            "source_residue_csv": str(res_csv),
            "zero_pocket_flag": "YES",
        })

    res_data = read_p2rank_csv(res_csv)
    for r in res_data:
        res_rows.append({
            "unique_reference_id": uid,
            "reference_layer": layer,
            "target": target,
            "reference_status": status,
            "reference_file_path": ref_path,
            "source_residue_csv": str(res_csv),
            "chain": r.get("chain", ""),
            "residue_label": r.get("residue_label", ""),
            "residue_name": r.get("residue_name", ""),
            "score": r.get("score", ""),
            "zscore": r.get("zscore", ""),
            "probability": r.get("probability", ""),
            "pocket": r.get("pocket", ""),
        })

pred_fields = [
    "unique_reference_id","reference_layer","target","reference_status",
    "reference_file_path","source_prediction_csv",
    "pocket_name","pocket_rank","score","probability",
    "sas_points","surf_atoms",
    "center_x","center_y","center_z",
    "residue_ids","surf_atom_ids",
]

res_fields = [
    "unique_reference_id","reference_layer","target","reference_status",
    "reference_file_path","source_residue_csv",
    "chain","residue_label","residue_name",
    "score","zscore","probability","pocket",
]

top1_fields = [
    "unique_reference_id","reference_layer","target","reference_status",
    "reference_file_path","pocket_rows",
    "pocket_name","pocket_rank",
    "top1_score","top1_probability",
    "top1_sas_points","top1_surf_atoms",
    "top1_center_x","top1_center_y","top1_center_z",
    "top1_residue_ids",
    "source_prediction_csv","source_residue_csv",
    "zero_pocket_flag",
]

write_tsv(pred_merged_path, pred_rows, pred_fields)
write_tsv(res_merged_path, res_rows, res_fields)
write_tsv(top1_path, top1_rows, top1_fields)

# Layer/status summary
by_layer = defaultdict(list)
for r in top1_rows:
    by_layer[r["reference_layer"]].append(r)

summary_rows = []
for layer, rows in sorted(by_layer.items()):
    scored = [r for r in rows if r["zero_pocket_flag"] == "NO"]
    scores = [fnum(r["top1_score"]) for r in scored]
    probs = [fnum(r["top1_probability"]) for r in scored]
    pocket_counts = [int(r["pocket_rows"] or 0) for r in rows]

    status_counts = Counter(r["reference_status"] for r in rows)

    summary_rows.append({
        "reference_layer": layer,
        "n_references": len(rows),
        "ok_references": status_counts.get("OK", 0),
        "zero_pocket_references": status_counts.get("NO_POCKETS_OR_EMPTY_OUTPUT", 0),
        "mean_top1_score_nonzero": round(sum(scores) / len(scores), 4) if scores else "",
        "min_top1_score_nonzero": round(min(scores), 4) if scores else "",
        "max_top1_score_nonzero": round(max(scores), 4) if scores else "",
        "mean_top1_probability_nonzero": round(sum(probs) / len(probs), 4) if probs else "",
        "min_top1_probability_nonzero": round(min(probs), 4) if probs else "",
        "max_top1_probability_nonzero": round(max(probs), 4) if probs else "",
        "mean_pocket_count_all": round(sum(pocket_counts) / len(pocket_counts), 4) if pocket_counts else "",
        "min_pocket_count_all": min(pocket_counts) if pocket_counts else "",
        "max_pocket_count_all": max(pocket_counts) if pocket_counts else "",
    })

layer_fields = [
    "reference_layer","n_references","ok_references","zero_pocket_references",
    "mean_top1_score_nonzero","min_top1_score_nonzero","max_top1_score_nonzero",
    "mean_top1_probability_nonzero","min_top1_probability_nonzero","max_top1_probability_nonzero",
    "mean_pocket_count_all","min_pocket_count_all","max_pocket_count_all",
]

write_tsv(layer_summary_path, summary_rows, layer_fields)

qc = Counter()
qc["manifest_records"] = len(manifest)
qc["manifest_ok_records"] = sum(1 for m in manifest if m["status"] == "OK")
qc["manifest_zero_pocket_records"] = sum(1 for m in manifest if m["status"] == "NO_POCKETS_OR_EMPTY_OUTPUT")
qc["merged_prediction_rows"] = len(pred_rows)
qc["merged_residue_rows"] = len(res_rows)
qc["top1_rows"] = len(top1_rows)
qc["layer_summary_rows"] = len(summary_rows)
qc["references_with_prediction_rows"] = len({r["unique_reference_id"] for r in pred_rows})
qc["references_with_residue_rows"] = len({r["unique_reference_id"] for r in res_rows})
qc["zero_pocket_top1_rows"] = sum(1 for r in top1_rows if r["zero_pocket_flag"] == "YES")

with qc_report_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    for k in sorted(qc):
        w.writerow([k, qc[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["reference_p2rank_predictions_merged", str(pred_merged_path), "Merged resolved-reference P2Rank pocket predictions"])
    w.writerow(["reference_p2rank_residues_merged", str(res_merged_path), "Merged resolved-reference P2Rank residue-level scores"])
    w.writerow(["reference_p2rank_top1_pockets", str(top1_path), "Top-ranked pocket per resolved reference; zero-pocket rows retained"])
    w.writerow(["reference_p2rank_layer_summary", str(layer_summary_path), "PDB/AFSP reference-layer pocket summary"])
    w.writerow(["reference_p2rank_merge_qc_report", str(qc_report_path), "M09G reference merge QC report"])

print("pred_merged:", pred_merged_path)
print("res_merged:", res_merged_path)
print("top1:", top1_path)
print("layer_summary:", layer_summary_path)
print("qc_report:", qc_report_path)
print("pointer:", pointer_path)
print("merged_prediction_rows:", len(pred_rows))
print("merged_residue_rows:", len(res_rows))
print("top1_rows:", len(top1_rows))
print("layer_summary_rows:", len(summary_rows))
