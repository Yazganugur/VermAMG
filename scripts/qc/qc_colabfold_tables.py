#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

project = Path("/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full")

paths = {
    "id_map": project / "run_sets/regression/regression_id_map.tsv",
    "batch_manifest": project / "01_colabfold/batches/regression/regression_colabfold_batch_manifest.tsv",
    "model_summary": project / "01_colabfold/qc_tables/regression/regression_colabfold_model_summary.tsv",
    "missing_outputs": project / "01_colabfold/qc_tables/regression/regression_colabfold_missing_outputs.tsv",
    "old_vs_new": project / "09_regression_pilot32/new_run_comparison/colabfold/regression_colabfold_old_vs_new_comparison.tsv",
}

required_columns = {
    "id_map": [
        "run_id", "original_fasta_header", "protein_id", "family_label",
        "mode", "raw_aa_length", "clean_aa_length", "sequence_sanitized", "source_note"
    ],
    "batch_manifest": [
        "mode", "batch_id", "batch_fasta", "run_id", "protein_id", "family_label", "aa_length"
    ],
    "model_summary": [
        "mode", "batch_id", "run_id", "protein_id", "family_label",
        "pdb_file", "score_json", "pae_json", "coverage_png", "pae_png", "plddt_png",
        "atom_lines", "ca_atoms", "plddt_mean", "plddt_min", "plddt_max", "ptm",
        "struct_conf_class", "model_status"
    ],
    "old_vs_new": [
        "old_key", "new_run_id", "protein_id", "family_label",
        "new_model_status", "new_struct_conf_class",
        "old_pdb_present", "old_score_present", "old_pae_present",
        "new_pdb_present", "new_score_present", "new_pae_present",
        "old_plddt_mean", "new_plddt_mean", "delta_plddt_mean_new_minus_old",
        "old_ptm", "new_ptm", "delta_ptm_new_minus_old"
    ],
}

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

errors = []
warnings = []

tables = {}
for name, path in paths.items():
    if not path.exists():
        errors.append(f"{name}: missing file {path}")
        continue
    tables[name] = read_tsv(path)

for name, cols in required_columns.items():
    if name not in tables:
        continue
    header = set(tables[name][0].keys()) if tables[name] else set()
    missing = [c for c in cols if c not in header]
    if missing:
        errors.append(f"{name}: missing required columns: {','.join(missing)}")

id_runs = {r["run_id"] for r in tables.get("id_map", [])}
batch_runs = {r["run_id"] for r in tables.get("batch_manifest", [])}
summary_runs = {r["run_id"] for r in tables.get("model_summary", [])}
compare_runs = {r["new_run_id"] for r in tables.get("old_vs_new", [])}

if id_runs != batch_runs:
    errors.append(f"run_id mismatch id_map vs batch_manifest: id_only={len(id_runs-batch_runs)}, batch_only={len(batch_runs-id_runs)}")

if id_runs != summary_runs:
    errors.append(f"run_id mismatch id_map vs model_summary: id_only={len(id_runs-summary_runs)}, summary_only={len(summary_runs-id_runs)}")

if compare_runs and id_runs != compare_runs:
    errors.append(f"run_id mismatch id_map vs old_vs_new: id_only={len(id_runs-compare_runs)}, compare_only={len(compare_runs-id_runs)}")

if "model_summary" in tables:
    rows = tables["model_summary"]
    if len(rows) != 32:
        errors.append(f"model_summary expected 32 rows, observed {len(rows)}")
    bad_status = [r["run_id"] for r in rows if r.get("model_status") != "OK"]
    if bad_status:
        errors.append(f"model_summary non-OK rows: {','.join(bad_status[:10])}")
    bad_conf = [r["run_id"] for r in rows if r.get("struct_conf_class") != "HIGH_STRUCT_CONF"]
    if bad_conf:
        warnings.append(f"model_summary non-HIGH_STRUCT_CONF rows: {','.join(bad_conf[:10])}")
    for r in rows:
        for field in ["pdb_file", "score_json", "pae_json", "coverage_png", "pae_png", "plddt_png"]:
            p = Path(r.get(field, ""))
            if not p.exists():
                errors.append(f"{r.get('run_id')}: missing path in model_summary field {field}: {p}")

if "missing_outputs" in tables and len(tables["missing_outputs"]) != 0:
    errors.append(f"missing_outputs table has {len(tables['missing_outputs'])} data rows")

if "old_vs_new" in tables:
    rows = tables["old_vs_new"]
    if len(rows) != 32:
        errors.append(f"old_vs_new expected 32 rows, observed {len(rows)}")
    for col in ["old_pdb_present", "old_score_present", "old_pae_present", "new_pdb_present", "new_score_present", "new_pae_present"]:
        bad = [r["new_run_id"] for r in rows if r.get(col) != "YES"]
        if bad:
            errors.append(f"old_vs_new {col} not YES for {len(bad)} rows; examples={','.join(bad[:5])}")
    # Numeric drift: not exact equality required, but should be tiny for same pipeline.
    big_plddt = []
    big_ptm = []
    for r in rows:
        try:
            if abs(float(r["delta_plddt_mean_new_minus_old"])) > 1.0:
                big_plddt.append(r["new_run_id"])
        except Exception:
            pass
        try:
            if abs(float(r["delta_ptm_new_minus_old"])) > 0.05:
                big_ptm.append(r["new_run_id"])
        except Exception:
            pass
    if big_plddt:
        warnings.append(f"old_vs_new pLDDT delta > 1.0 for {len(big_plddt)} rows")
    if big_ptm:
        warnings.append(f"old_vs_new pTM delta > 0.05 for {len(big_ptm)} rows")

print("===== COLABFOLD TABLE QC REPORT =====")
for name, rows in tables.items():
    print(f"{name}_rows={len(rows)}")

if warnings:
    print("WARNINGS:")
    for w in warnings:
        print("WARNING:", w)

if errors:
    print("ERRORS:")
    for e in errors:
        print("ERROR:", e)
    print("COLABFOLD_TABLE_QC: FAIL")
    sys.exit(1)

print("COLABFOLD_TABLE_QC: PASS")
