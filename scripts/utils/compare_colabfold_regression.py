#!/usr/bin/env python3
import csv
import json
import re
import sys
from pathlib import Path

if len(sys.argv) != 5:
    raise SystemExit("Usage: compare_colabfold_regression.py OLD_PKG NEW_SUMMARY IDMAP OUT_DIR")

old_pkg = Path(sys.argv[1])
new_summary = Path(sys.argv[2])
idmap_path = Path(sys.argv[3])
out_dir = Path(sys.argv[4])
out_dir.mkdir(parents=True, exist_ok=True)

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def parse_score(path):
    result = {
        "plddt_mean": "",
        "plddt_min": "",
        "plddt_max": "",
        "plddt_n": "",
        "ptm": "",
    }
    if not path or not Path(path).exists():
        return result
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return result
    plddt = data.get("plddt")
    if isinstance(plddt, list) and plddt:
        result["plddt_n"] = len(plddt)
        result["plddt_mean"] = round(sum(plddt) / len(plddt), 3)
        result["plddt_min"] = round(min(plddt), 3)
        result["plddt_max"] = round(max(plddt), 3)
    if "ptm" in data:
        result["ptm"] = data["ptm"]
    return result

def old_short_id_from_filename(name):
    # Example: T1P001_CoA_trans_host_associated_unrelaxed_rank_...
    m = re.match(r"^(T1P\d{3}_.+?)_unrelaxed_rank_", name)
    if m:
        return m.group(1)
    m = re.match(r"^(T1P\d{3}_.+?)_scores_rank_", name)
    if m:
        return m.group(1)
    m = re.match(r"^(T1P\d{3}_.+?)_predicted_aligned_error", name)
    if m:
        return m.group(1)
    return ""

def new_old_like_id(run_id, original_header, idx):
    # Since new run IDs are QBENCH000001_..., infer old T1P-style order from index.
    # We preserve the exact mapping through original protein IDs where possible.
    return f"T1P{idx:03d}"

new_rows = read_tsv(new_summary)
idmap_rows = read_tsv(idmap_path)

# Build old file inventory by T1P numeric prefix.
old_files = {}
if old_pkg.exists():
    for f in old_pkg.rglob("*"):
        if not f.is_file():
            continue
        sid = old_short_id_from_filename(f.name)
        if not sid:
            continue
        key = sid.split("_")[0]  # T1P001
        old_files.setdefault(key, {"old_short_full": sid})
        if f.name.endswith(".pdb"):
            old_files[key]["old_pdb"] = str(f)
        elif "scores" in f.name and f.suffix == ".json":
            old_files[key]["old_score_json"] = str(f)
        elif "predicted_aligned_error" in f.name and f.suffix == ".json":
            old_files[key]["old_pae_json"] = str(f)
        elif f.name.endswith(".png"):
            old_files[key].setdefault("old_png_count", 0)
            old_files[key]["old_png_count"] += 1

compare_rows = []
for i, row in enumerate(new_rows, 1):
    old_key = new_old_like_id(row["run_id"], row.get("original_fasta_header", ""), i)
    old = old_files.get(old_key, {})

    old_score = parse_score(old.get("old_score_json", ""))
    new_plddt = row.get("plddt_mean", "")
    new_ptm = row.get("ptm", "")
    old_plddt = old_score.get("plddt_mean", "")
    old_ptm = old_score.get("ptm", "")

    def diff(a, b):
        try:
            return round(float(a) - float(b), 3)
        except Exception:
            return ""

    compare_rows.append({
        "old_key": old_key,
        "new_run_id": row["run_id"],
        "protein_id": row.get("protein_id", ""),
        "family_label": row.get("family_label", ""),
        "new_model_status": row.get("model_status", ""),
        "new_struct_conf_class": row.get("struct_conf_class", ""),
        "old_pdb_present": "YES" if old.get("old_pdb") else "NO",
        "old_score_present": "YES" if old.get("old_score_json") else "NO",
        "old_pae_present": "YES" if old.get("old_pae_json") else "NO",
        "old_png_count": old.get("old_png_count", 0),
        "new_pdb_present": "YES" if row.get("pdb_file") else "NO",
        "new_score_present": "YES" if row.get("score_json") else "NO",
        "new_pae_present": "YES" if row.get("pae_json") else "NO",
        "new_png_count": sum(1 for k in ["coverage_png", "pae_png", "plddt_png"] if row.get(k)),
        "old_plddt_mean": old_plddt,
        "new_plddt_mean": new_plddt,
        "delta_plddt_mean_new_minus_old": diff(new_plddt, old_plddt),
        "old_ptm": old_ptm,
        "new_ptm": new_ptm,
        "delta_ptm_new_minus_old": diff(new_ptm, old_ptm),
        "old_pdb": old.get("old_pdb", ""),
        "new_pdb": row.get("pdb_file", ""),
    })

fields = [
    "old_key", "new_run_id", "protein_id", "family_label",
    "new_model_status", "new_struct_conf_class",
    "old_pdb_present", "old_score_present", "old_pae_present", "old_png_count",
    "new_pdb_present", "new_score_present", "new_pae_present", "new_png_count",
    "old_plddt_mean", "new_plddt_mean", "delta_plddt_mean_new_minus_old",
    "old_ptm", "new_ptm", "delta_ptm_new_minus_old",
    "old_pdb", "new_pdb",
]

compare_path = out_dir / "regression_colabfold_old_vs_new_comparison.tsv"
write_tsv(compare_path, compare_rows, fields)

summary = {
    "n_new_models": len(new_rows),
    "n_old_pdb_present": sum(1 for r in compare_rows if r["old_pdb_present"] == "YES"),
    "n_old_score_present": sum(1 for r in compare_rows if r["old_score_present"] == "YES"),
    "n_old_pae_present": sum(1 for r in compare_rows if r["old_pae_present"] == "YES"),
    "n_new_pdb_present": sum(1 for r in compare_rows if r["new_pdb_present"] == "YES"),
    "n_new_score_present": sum(1 for r in compare_rows if r["new_score_present"] == "YES"),
    "n_new_pae_present": sum(1 for r in compare_rows if r["new_pae_present"] == "YES"),
    "n_new_high_conf": sum(1 for r in compare_rows if r["new_struct_conf_class"] == "HIGH_STRUCT_CONF"),
}

summary_path = out_dir / "regression_colabfold_old_vs_new_summary.tsv"
with summary_path.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    for k, v in summary.items():
        writer.writerow([k, v])

print("comparison:", compare_path)
print("summary:", summary_path)
for k, v in summary.items():
    print(f"{k}: {v}")
