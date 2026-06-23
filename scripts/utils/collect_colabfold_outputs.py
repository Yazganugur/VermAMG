#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

if len(sys.argv) != 8:
    raise SystemExit(
        "Usage: collect_colabfold_outputs.py MODE IDMAP BATCH_MANIFEST OUT_ROOT MODEL_SUMMARY MISSING_TABLE CLASS_SUMMARY"
    )

mode = sys.argv[1]
idmap_path = Path(sys.argv[2])
batch_manifest_path = Path(sys.argv[3])
out_root = Path(sys.argv[4])
model_summary_path = Path(sys.argv[5])
missing_table_path = Path(sys.argv[6])
class_summary_path = Path(sys.argv[7])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def first_or_empty(paths):
    paths = sorted(paths)
    return str(paths[0]) if paths else ""

def count_atom_ca(pdb_file):
    if not pdb_file:
        return 0, 0
    atom_n = 0
    ca_n = 0
    with open(pdb_file) as f:
        for line in f:
            if line.startswith("ATOM"):
                atom_n += 1
                parts = line.split()
                if len(parts) > 2 and parts[2] == "CA":
                    ca_n += 1
    return atom_n, ca_n

def parse_score(score_file):
    result = {
        "ptm": "",
        "iptm": "",
        "ranking_confidence": "",
        "plddt_n": "",
        "plddt_mean": "",
        "plddt_min": "",
        "plddt_max": "",
    }
    if not score_file:
        return result
    try:
        data = json.loads(Path(score_file).read_text())
    except Exception:
        return result

    for key in ["ptm", "iptm", "ranking_confidence"]:
        if key in data:
            result[key] = data[key]

    plddt = data.get("plddt")
    if isinstance(plddt, list) and plddt:
        result["plddt_n"] = len(plddt)
        result["plddt_mean"] = round(sum(plddt) / len(plddt), 3)
        result["plddt_min"] = round(min(plddt), 3)
        result["plddt_max"] = round(max(plddt), 3)

    return result

def confidence_class(plddt_mean, ptm):
    try:
        plddt = float(plddt_mean)
    except Exception:
        plddt = -1
    try:
        ptm_v = float(ptm)
    except Exception:
        ptm_v = -1

    if plddt >= 90 and ptm_v >= 0.80:
        return "HIGH_STRUCT_CONF"
    if plddt >= 70 and ptm_v >= 0.60:
        return "MODERATE_STRUCT_CONF"
    if plddt >= 50:
        return "LOW_STRUCT_CONF"
    return "VERY_LOW_OR_MISSING_STRUCT_CONF"

idmap_rows = read_tsv(idmap_path)
batch_rows = read_tsv(batch_manifest_path)

idmap = {r["run_id"]: r for r in idmap_rows}
batch_by_run = {r["run_id"]: r for r in batch_rows}

summary_rows = []
missing_rows = []

for run_id, meta in idmap.items():
    batch = batch_by_run.get(run_id, {})
    batch_id = batch.get("batch_id", "")
    batch_dir = out_root / f"{batch_id}_colabfold_msa" if batch_id else out_root

    pdb_file = first_or_empty(batch_dir.glob(f"{run_id}*.pdb"))
    score_file = first_or_empty(batch_dir.glob(f"{run_id}*scores*.json"))
    pae_json = first_or_empty(batch_dir.glob(f"{run_id}*predicted_aligned_error*.json"))
    coverage_png = first_or_empty(batch_dir.glob(f"{run_id}*coverage.png"))
    pae_png = first_or_empty(batch_dir.glob(f"{run_id}*pae.png"))
    plddt_png = first_or_empty(batch_dir.glob(f"{run_id}*plddt.png"))
    a3m_file = first_or_empty(batch_dir.glob(f"{run_id}*.a3m"))

    atom_n, ca_n = count_atom_ca(pdb_file)
    score = parse_score(score_file)

    missing = []
    if not pdb_file:
        missing.append("pdb")
    if not score_file:
        missing.append("score_json")
    if not pae_json:
        missing.append("pae_json")
    if not coverage_png:
        missing.append("coverage_png")
    if not pae_png:
        missing.append("pae_png")
    if not plddt_png:
        missing.append("plddt_png")
    if atom_n == 0:
        missing.append("atom_lines")

    model_status = "OK" if not missing else "MISSING_OR_INCOMPLETE"
    conf_class = confidence_class(score["plddt_mean"], score["ptm"])

    row = {
        "mode": mode,
        "batch_id": batch_id,
        "run_id": run_id,
        "protein_id": meta.get("protein_id", ""),
        "original_fasta_header": meta.get("original_fasta_header", ""),
        "family_label": meta.get("family_label", ""),
        "raw_aa_length": meta.get("raw_aa_length", ""),
        "clean_aa_length": meta.get("clean_aa_length", meta.get("aa_length", "")),
        "sequence_sanitized": meta.get("sequence_sanitized", ""),
        "pdb_file": pdb_file,
        "score_json": score_file,
        "pae_json": pae_json,
        "coverage_png": coverage_png,
        "pae_png": pae_png,
        "plddt_png": plddt_png,
        "a3m_file": a3m_file,
        "atom_lines": atom_n,
        "ca_atoms": ca_n,
        "plddt_n": score["plddt_n"],
        "plddt_mean": score["plddt_mean"],
        "plddt_min": score["plddt_min"],
        "plddt_max": score["plddt_max"],
        "ptm": score["ptm"],
        "iptm": score["iptm"],
        "ranking_confidence": score["ranking_confidence"],
        "struct_conf_class": conf_class,
        "model_status": model_status,
    }
    summary_rows.append(row)

    if missing:
        missing_rows.append({
            "mode": mode,
            "batch_id": batch_id,
            "run_id": run_id,
            "protein_id": meta.get("protein_id", ""),
            "family_label": meta.get("family_label", ""),
            "missing_items": ",".join(missing),
        })

summary_fields = [
    "mode", "batch_id", "run_id", "protein_id", "original_fasta_header",
    "family_label", "raw_aa_length", "clean_aa_length", "sequence_sanitized",
    "pdb_file", "score_json", "pae_json", "coverage_png", "pae_png", "plddt_png",
    "a3m_file", "atom_lines", "ca_atoms", "plddt_n", "plddt_mean", "plddt_min",
    "plddt_max", "ptm", "iptm", "ranking_confidence", "struct_conf_class",
    "model_status",
]

with model_summary_path.open("w") as f:
    writer = csv.DictWriter(f, fieldnames=summary_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(summary_rows)

missing_fields = ["mode", "batch_id", "run_id", "protein_id", "family_label", "missing_items"]
with missing_table_path.open("w") as f:
    writer = csv.DictWriter(f, fieldnames=missing_fields, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(missing_rows)

class_counts = {}
for r in summary_rows:
    key = (r["struct_conf_class"], r["model_status"])
    class_counts[key] = class_counts.get(key, 0) + 1

with class_summary_path.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["mode", "struct_conf_class", "model_status", "n"])
    for (conf, status), n in sorted(class_counts.items()):
        writer.writerow([mode, conf, status, n])

print("model_summary:", model_summary_path)
print("missing_table:", missing_table_path)
print("class_summary:", class_summary_path)
print("n_models:", len(summary_rows))
print("n_missing_rows:", len(missing_rows))
