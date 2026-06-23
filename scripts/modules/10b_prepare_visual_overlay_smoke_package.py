#!/usr/bin/env python3
import csv
import sys
import os
from pathlib import Path

# VermAMG visual path resolver.
# Prefer portable contract columns and resolve them through profile roots.
# Fall back to legacy absolute columns for backward compatibility.
def resolve_vermamg_visual_path(portable_value, legacy_value, root_kind):
    portable_value = str(portable_value or "")
    legacy_value = str(legacy_value or "")

    if portable_value:
        if portable_value.startswith("/"):
            return portable_value

        if Path(portable_value).exists():
            return portable_value

        if root_kind == "db":
            root = os.environ.get("VERMAMG_DB_ROOT", "/arf/scratch/yugur/baps_faz_c_v2/structural_validation")
        else:
            root = os.environ.get("VERMAMG_ROOT", "/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full")

        return str(Path(root) / portable_value)

    return legacy_value


if len(sys.argv) != 7:
    raise SystemExit(
        "Usage: 10b_prepare_visual_overlay_smoke_package.py "
        "CONTRACT SMOKE_MANIFEST SMOKE_PYMOL SMOKE_CHIMERAX SMOKE_README QC_REPORT"
    )

contract_path = Path(sys.argv[1])
smoke_manifest_path = Path(sys.argv[2])
pymol_path = Path(sys.argv[3])
chimerax_path = Path(sys.argv[4])
readme_path = Path(sys.argv[5])
qc_report_path = Path(sys.argv[6])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def safe_exists(path):
    return bool(path) and Path(path).exists()

def parse_residue_ids(residue_string, max_n=30):
    out = []
    for token in (residue_string or "").split():
        if "_" not in token:
            continue
        chain, resi = token.split("_", 1)
        chain = chain.strip()
        resi = resi.strip()
        if chain and resi:
            out.append((chain, resi))
    return out[:max_n]

def pymol_selection(name, residues, obj):
    if not residues:
        return f"select {name}, none\n"
    parts = [f"({obj} and chain {c} and resi {r})" for c, r in residues]
    return f"select {name}, " + " or ".join(parts) + "\n"

def chimerax_selection(residues):
    if not residues:
        return ""
    # ChimeraX chain/residue selector fragments, e.g. /A:54
    return " ".join([f"/{c}:{r}" for c, r in residues])

rows = read_tsv(contract_path)

# Prefer primary/reference-ready rows. If none, use any ready query+reference row.
candidates = [
    r for r in rows
    if r.get("visual_status") == "READY_QUERY_AND_REFERENCE"
    and r.get("panel_role") == "PRIMARY"
]
if not candidates:
    candidates = [r for r in rows if r.get("visual_status") == "READY_QUERY_AND_REFERENCE"]

if not candidates:
    candidates = [
        r for r in rows
        if r.get("visual_status") == "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"
        and r.get("panel_role") == "PRIMARY"
    ]

if not candidates:
    candidates = [r for r in rows if r.get("visual_status") == "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"]

if not candidates:
    candidates = [
        r for r in rows
        if r.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"
        and r.get("panel_role") == "PRIMARY"
    ]

if not candidates:
    candidates = [r for r in rows if r.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"]

if not candidates:
    raise SystemExit("No READY_QUERY_AND_REFERENCE, READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY, or READY_QUERY_REFERENCE_ZERO_POCKET row found for smoke package.")

r = candidates[0]

query_pdb = resolve_vermamg_visual_path(r.get("query_model_pdb_portable", ""), r.get("query_model_pdb", ""), "root")
ref_pdb = resolve_vermamg_visual_path(r.get("reference_file_path_portable", ""), r.get("reference_file_path", ""), "db")
query_res = parse_residue_ids(r.get("query_top1_residue_ids", ""))
is_unreliable_ca_only_reference = (
    r.get("visual_status") == "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"
    or r.get("reference_pocket_signal") == "UNRELIABLE_CA_ONLY_INPUT"
)
is_zero_pocket_reference = (
    r.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"
    or r.get("reference_zero_pocket_flag") == "YES"
    or is_unreliable_ca_only_reference
)
ref_res = [] if is_zero_pocket_reference else parse_residue_ids(r.get("reference_top1_residue_ids", ""))
smoke_mode = (
    "UNRELIABLE_CA_ONLY_REFERENCE"
    if is_unreliable_ca_only_reference
    else "ZERO_POCKET_REFERENCE"
    if is_zero_pocket_reference
    else "READY_QUERY_AND_REFERENCE"
)
reference_pocket_signal = (
    "UNRELIABLE_CA_ONLY_INPUT"
    if is_unreliable_ca_only_reference
    else "ABSENT"
    if is_zero_pocket_reference
    else "PRESENT"
)
reference_pocket_overlay = "NONE" if reference_pocket_signal != "PRESENT" else "PRESENT"
query_pocket_overlay = "PRESENT" if query_res else "NONE"
reference_pocket_interpretation = (
    r.get("reference_pocket_interpretation", "")
    or ("NOT_BIOLOGICAL_ABSENCE" if is_unreliable_ca_only_reference else "")
    or ("NO_POCKET_PREDICTED_FULL_ATOM" if is_zero_pocket_reference else "POSITIVE_POCKET_SIGNAL")
)

manifest_row = {
    "query": r.get("query", ""),
    "protein_id": r.get("protein_id", ""),
    "family": r.get("family", ""),
    "panel_order": r.get("panel_order", ""),
    "panel_role": r.get("panel_role", ""),
    "reference_layer": r.get("reference_layer", ""),
    "target": r.get("target", ""),
    "visual_status": r.get("visual_status", ""),
    "query_model_pdb": query_pdb,
    "query_model_pdb_portable": r.get("query_model_pdb_portable", ""),
    "query_model_pdb_exists": "YES" if safe_exists(query_pdb) else "NO",
    "query_top1_score": r.get("query_top1_score", ""),
    "query_top1_probability": r.get("query_top1_probability", ""),
    "query_top1_residue_count_used": str(len(query_res)),
    "reference_file_path": ref_pdb,
    "reference_file_path_portable": r.get("reference_file_path_portable", ""),
    "reference_file_exists": "YES" if safe_exists(ref_pdb) else "NO",
    "unique_reference_id": r.get("unique_reference_id", ""),
    "reference_p2rank_status": r.get("reference_p2rank_status", ""),
    "reference_zero_pocket_flag": r.get("reference_zero_pocket_flag", ""),
    "reference_top1_score": r.get("reference_top1_score", ""),
    "reference_top1_probability": r.get("reference_top1_probability", ""),
    "reference_top1_residue_count_used": str(len(ref_res)),
    "smoke_mode": smoke_mode,
    "reference_pocket_signal": reference_pocket_signal,
    "reference_pocket_overlay": reference_pocket_overlay,
    "query_pocket_overlay": query_pocket_overlay,
    "reference_pocket_interpretation": reference_pocket_interpretation,
    "pymol_script": str(pymol_path),
    "chimerax_script": str(chimerax_path),
}

fields = list(manifest_row.keys())
write_tsv(smoke_manifest_path, [manifest_row], fields)

# PyMOL script: load structures, align reference to query, color pockets.
pymol_text = []
pymol_text.append("reinitialize\n")
pymol_text.append(f'load "{query_pdb}", query_model\n')
pymol_text.append(f'load "{ref_pdb}", reference_model\n')
pymol_text.append("hide everything\n")
pymol_text.append("show cartoon, query_model\n")
pymol_text.append("show cartoon, reference_model\n")
pymol_text.append("color cyan, query_model\n")
pymol_text.append("color gray70, reference_model\n")
pymol_text.append("align reference_model, query_model\n")
pymol_text.append(pymol_selection("query_top1_pocket_residues", query_res, "query_model"))
pymol_text.append("show spheres, query_top1_pocket_residues\n")
pymol_text.append("color yellow, query_top1_pocket_residues\n")
if not is_zero_pocket_reference:
    pymol_text.append(pymol_selection("reference_top1_pocket_residues", ref_res, "reference_model"))
    pymol_text.append("show spheres, reference_top1_pocket_residues\n")
    pymol_text.append("color orange, reference_top1_pocket_residues\n")
else:
    pymol_text.append("# Reference has zero predicted pockets; no reference pocket residue marker is drawn.\n")
pymol_text.append("set sphere_scale, 0.45\n")
pymol_text.append("set transparency, 0.35, reference_model\n")
pymol_text.append("bg_color white\n")
pymol_text.append("orient\n")
pymol_text.append("ray 1800, 1400\n")
pymol_text.append(f'png "{pymol_path.with_suffix(".png")}", dpi=200\n')
pymol_text.append("save " + f'"{pymol_path.with_suffix(".pse")}"' + "\n")
pymol_path.write_text("".join(pymol_text))

# ChimeraX script
q_sel = chimerax_selection(query_res)
r_sel = chimerax_selection(ref_res)

chimerax_text = []
chimerax_text.append(f'open "{query_pdb}" name query_model\n')
chimerax_text.append(f'open "{ref_pdb}" name reference_model\n')
chimerax_text.append("match #2 to #1\n")
chimerax_text.append("style cartoon\n")
chimerax_text.append("color #1 cyan\n")
chimerax_text.append("color #2 gray\n")
if q_sel:
    chimerax_text.append(f"select #1{q_sel}\n")
    chimerax_text.append("style sel sphere\n")
    chimerax_text.append("color sel yellow\n")
if r_sel:
    chimerax_text.append(f"select #2{r_sel}\n")
    chimerax_text.append("style sel sphere\n")
    chimerax_text.append("color sel orange\n")
chimerax_text.append("view\n")
chimerax_text.append(f'save "{chimerax_path.with_suffix(".png")}" width 1800 height 1400 supersample 3\n')
chimerax_path.write_text("".join(chimerax_text))

readme_path.write_text(
    "M10B visual/overlay smoke package\n"
    "=================================\n\n"
    f"Query: {manifest_row['query']}\n"
    f"Family: {manifest_row['family']}\n"
    f"Reference: {manifest_row['reference_layer']} / {manifest_row['target']}\n"
    f"Visual status: {manifest_row['visual_status']}\n\n"
    f"Smoke mode: {manifest_row['smoke_mode']}\n"
    f"Reference pocket signal: {manifest_row['reference_pocket_signal']}\n\n"
    f"Reference pocket interpretation: {manifest_row['reference_pocket_interpretation']}\n\n"
    "Generated files:\n"
    f"- Manifest: {smoke_manifest_path}\n"
    f"- PyMOL script: {pymol_path}\n"
    f"- ChimeraX script: {chimerax_path}\n\n"
    "This smoke package checks that M10 visual inputs can be converted into viewer scripts.\n"
    "If smoke mode is ZERO_POCKET_REFERENCE, the reference has zero predicted pockets and this is not positive pocket support.\n"
    "If smoke mode is UNRELIABLE_CA_ONLY_REFERENCE, the reference structure is CA-only-like; zero pockets are not biological absence.\n"
    "Actual PNG rendering depends on PyMOL or ChimeraX availability on the execution node.\n"
)

qc = {
    "selected_query": manifest_row["query"],
    "selected_family": manifest_row["family"],
    "selected_reference_layer": manifest_row["reference_layer"],
    "selected_target": manifest_row["target"],
    "query_model_pdb_exists": manifest_row["query_model_pdb_exists"],
    "reference_file_exists": manifest_row["reference_file_exists"],
    "query_top1_residue_count_used": manifest_row["query_top1_residue_count_used"],
    "reference_top1_residue_count_used": manifest_row["reference_top1_residue_count_used"],
    "smoke_mode": manifest_row["smoke_mode"],
    "reference_pocket_signal": manifest_row["reference_pocket_signal"],
    "reference_pocket_overlay": manifest_row["reference_pocket_overlay"],
    "query_pocket_overlay": manifest_row["query_pocket_overlay"],
    "reference_pocket_interpretation": manifest_row["reference_pocket_interpretation"],
    "pymol_script_exists": "YES" if pymol_path.exists() else "NO",
    "chimerax_script_exists": "YES" if chimerax_path.exists() else "NO",
    "smoke_manifest_exists": "YES" if smoke_manifest_path.exists() else "NO",
}

with qc_report_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric", "value"])
    for k, v in qc.items():
        w.writerow([k, v])

print("smoke_manifest:", smoke_manifest_path)
print("pymol_script:", pymol_path)
print("chimerax_script:", chimerax_path)
print("readme:", readme_path)
print("qc_report:", qc_report_path)
print("selected_query:", manifest_row["query"])
print("selected_reference:", manifest_row["reference_layer"], manifest_row["target"])
