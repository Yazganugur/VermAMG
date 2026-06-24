#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter

if len(sys.argv) != 9:
    raise SystemExit(
        "Usage: 10c_prepare_all_query_visual_script_package.py "
        "CONTRACT OUT_ROOT PACKAGE_MANIFEST QUERY_SUMMARY SKIPPED_REPORT README QC_REPORT POINTER"
    )

contract_path = Path(sys.argv[1])
out_root = Path(sys.argv[2])
package_manifest_path = Path(sys.argv[3])
query_summary_path = Path(sys.argv[4])
skipped_report_path = Path(sys.argv[5])
readme_path = Path(sys.argv[6])
qc_report_path = Path(sys.argv[7])
pointer_path = Path(sys.argv[8])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

def safe_name(s):
    s = s or "NA"
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return s[:180]

def file_exists(path):
    return bool(path) and Path(path).exists()

def parse_residue_ids(residue_string, max_n=40):
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
    return " ".join([f"/{c}:{r}" for c, r in residues])

def write_visual_scripts(row, query_dir, script_base):
    query_pdb = row.get("query_model_pdb", "")
    ref_pdb = row.get("reference_file_path", "")

    query_res = parse_residue_ids(row.get("query_top1_residue_ids", ""), max_n=40)
    is_zero_pocket_reference = (
        row.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"
        or row.get("reference_zero_pocket_flag") == "YES"
    )
    is_unreliable_ca_only_reference = (
        row.get("visual_status") == "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"
        or row.get("reference_pocket_signal") == "UNRELIABLE_CA_ONLY_INPUT"
    )
    suppress_reference_pocket = is_zero_pocket_reference or is_unreliable_ca_only_reference
    ref_res = [] if suppress_reference_pocket else parse_residue_ids(row.get("reference_top1_residue_ids", ""), max_n=40)

    pml = query_dir / f"{script_base}.pml"
    cxc = query_dir / f"{script_base}.cxc"

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
    if not suppress_reference_pocket:
        pymol_text.append(pymol_selection("reference_top1_pocket_residues", ref_res, "reference_model"))
        pymol_text.append("show spheres, reference_top1_pocket_residues\n")
        pymol_text.append("color orange, reference_top1_pocket_residues\n")
    else:
        pymol_text.append("# Reference pocket marker is not drawn: zero-pocket or CA-only-like unreliable input.\n")
    pymol_text.append("set sphere_scale, 0.45\n")
    pymol_text.append("set transparency, 0.35, reference_model\n")
    pymol_text.append("bg_color white\n")
    pymol_text.append("orient\n")
    pymol_text.append("# Optional local rendering commands:\n")
    pymol_text.append(f'# ray 1800, 1400\n')
    pymol_text.append(f'# png "{pml.with_suffix(".png")}", dpi=200\n')
    pymol_text.append(f'save "{pml.with_suffix(".pse")}"\n')
    pml.write_text("".join(pymol_text))

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
    chimerax_text.append("# Optional local rendering command:\n")
    chimerax_text.append(f'# save "{cxc.with_suffix(".png")}" width 1800 height 1400 supersample 3\n')
    cxc.write_text("".join(chimerax_text))

    return pml, cxc, len(query_res), len(ref_res)

rows = read_tsv(contract_path)
out_root.mkdir(parents=True, exist_ok=True)

by_query = defaultdict(list)
for r in rows:
    by_query[r["query"]].append(r)

script_rows = []
query_summary_rows = []
skipped_rows = []

for query, qrows in sorted(by_query.items()):
    family = qrows[0].get("family", "")
    query_dir = out_root / safe_name(f"{query}_{family}")
    query_dir.mkdir(parents=True, exist_ok=True)

    ready_rows = [r for r in qrows if r.get("visual_status") == "READY_QUERY_AND_REFERENCE"]
    zero_rows = [r for r in qrows if r.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"]
    unreliable_rows = [r for r in qrows if r.get("visual_status") == "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"]
    missing_rows = [r for r in qrows if r.get("visual_status") == "READY_QUERY_ONLY_REFERENCE_CACHE_MISSING"]
    blocked_rows = [r for r in qrows if r.get("visual_status") == "BLOCKED_QUERY_MODEL_MISSING"]

    # Prefer primary reference first, then lowest panel_order, then PDB before AFSP.
    def row_sort_key(r):
        panel_role_score = 0 if r.get("panel_role") == "PRIMARY" else 1
        try:
            order = int(r.get("panel_order", "999"))
        except Exception:
            order = 999
        layer_score = 0 if r.get("reference_layer") == "PDB" else 1
        return (panel_role_score, order, layer_score, r.get("target", ""))

    ready_rows = sorted(ready_rows, key=row_sort_key)

    # Script policy: create scripts for all ready rows. Zero-pocket references
    # get query pocket + reference structure only, with no reference pocket marker.
    scripts_created = 0

    scriptable_rows = sorted(ready_rows + zero_rows + unreliable_rows, key=row_sort_key)
    zero_pocket_scripts_created = 0
    unreliable_ca_only_scripts_created = 0

    for r in scriptable_rows:
        panel_order = r.get("panel_order", "")
        target = r.get("target", "")
        layer = r.get("reference_layer", "")
        role = r.get("panel_role", "")
        script_base = safe_name(f"{query}_panel{panel_order}_{role}_{layer}_{target}")

        pml, cxc, qres_n, rres_n = write_visual_scripts(r, query_dir, script_base)
        scripts_created += 1
        is_zero_pocket_reference = (
            r.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"
            or r.get("reference_zero_pocket_flag") == "YES"
        )
        is_unreliable_ca_only_reference = (
            r.get("visual_status") == "READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY"
            or r.get("reference_pocket_signal") == "UNRELIABLE_CA_ONLY_INPUT"
        )
        if is_unreliable_ca_only_reference:
            unreliable_ca_only_scripts_created += 1
        elif is_zero_pocket_reference:
            zero_pocket_scripts_created += 1

        reference_pocket_signal = (
            "UNRELIABLE_CA_ONLY_INPUT"
            if is_unreliable_ca_only_reference
            else "ABSENT"
            if is_zero_pocket_reference
            else "PRESENT"
        )
        reference_pocket_overlay = "NONE" if reference_pocket_signal != "PRESENT" else "PRESENT"
        query_pocket_overlay = "PRESENT" if qres_n else "NONE"
        reference_pocket_interpretation = (
            r.get("reference_pocket_interpretation", "")
            or ("NOT_BIOLOGICAL_ABSENCE" if is_unreliable_ca_only_reference else "")
            or ("NO_POCKET_PREDICTED_FULL_ATOM" if is_zero_pocket_reference else "POSITIVE_POCKET_SIGNAL")
        )

        script_rows.append({
            "query": query,
            "protein_id": r.get("protein_id", ""),
            "family": family,
            "panel_order": panel_order,
            "panel_role": role,
            "reference_layer": layer,
            "target": target,
            "visual_status": r.get("visual_status", ""),
            "query_model_pdb": r.get("query_model_pdb", ""),
            "query_model_pdb_portable": r.get("query_model_pdb_portable", ""),
            "reference_file_path": r.get("reference_file_path", ""),
            "reference_file_path_portable": r.get("reference_file_path_portable", ""),
            "unique_reference_id": r.get("unique_reference_id", ""),
            "query_top1_score": r.get("query_top1_score", ""),
            "query_top1_probability": r.get("query_top1_probability", ""),
            "reference_top1_score": r.get("reference_top1_score", ""),
            "reference_top1_probability": r.get("reference_top1_probability", ""),
            "query_residue_count_used": str(qres_n),
            "reference_residue_count_used": str(rres_n),
            "reference_pocket_signal": reference_pocket_signal,
            "reference_pocket_overlay": reference_pocket_overlay,
            "query_pocket_overlay": query_pocket_overlay,
            "reference_pocket_interpretation": reference_pocket_interpretation,
            "pymol_script": str(pml),
            "chimerax_script": str(cxc),
            "query_dir": str(query_dir),
        })

    for r in missing_rows + blocked_rows:
        skipped_rows.append({
            "query": query,
            "protein_id": r.get("protein_id", ""),
            "family": family,
            "panel_order": r.get("panel_order", ""),
            "panel_role": r.get("panel_role", ""),
            "reference_layer": r.get("reference_layer", ""),
            "target": r.get("target", ""),
            "visual_status": r.get("visual_status", ""),
            "skip_reason": (
                "reference_zero_pocket"
                if r.get("visual_status") == "READY_QUERY_REFERENCE_ZERO_POCKET"
                else "reference_cache_missing"
                if r.get("visual_status") == "READY_QUERY_ONLY_REFERENCE_CACHE_MISSING"
                else "query_model_missing"
            ),
            "reference_file_path": r.get("reference_file_path", ""),
            "reference_file_exists": r.get("reference_file_exists", ""),
            "reference_zero_pocket_flag": r.get("reference_zero_pocket_flag", ""),
        })

    # Query README
    q_readme = query_dir / "README.txt"
    q_readme.write_text(
        f"Visual scripts for {query}\n"
        f"Family: {family}\n\n"
        f"READY_QUERY_AND_REFERENCE scripts created: {scripts_created}\n"
        f"Zero-pocket reference scripts created: {zero_pocket_scripts_created}\n"
        f"CA-only-like unreliable reference scripts created: {unreliable_ca_only_scripts_created}\n"
        f"Cache-missing references skipped: {len(missing_rows)}\n"
        f"Blocked rows: {len(blocked_rows)}\n\n"
        "Scripts are generated for PyMOL (.pml) and ChimeraX (.cxc).\n"
        "Zero-pocket reference scripts show query pocket plus reference structure only; they are not positive reference pocket support.\n"
        "CA-only-like unreliable reference scripts are not biological no-pocket evidence.\n"
        "PNG rendering is intentionally optional/local for now.\n"
    )

    query_summary_rows.append({
        "query": query,
        "protein_id": qrows[0].get("protein_id", ""),
        "family": family,
        "panel_rows": str(len(qrows)),
        "ready_query_and_reference_rows": str(len(ready_rows)),
        "zero_pocket_reference_rows": str(len(zero_rows)),
        "zero_pocket_visual_scripts_created": str(zero_pocket_scripts_created),
        "unreliable_ca_only_reference_rows": str(len(unreliable_rows)),
        "unreliable_ca_only_visual_scripts_created": str(unreliable_ca_only_scripts_created),
        "cache_missing_reference_rows": str(len(missing_rows)),
        "blocked_rows": str(len(blocked_rows)),
        "visual_scripts_created": str(scripts_created),
        "query_dir": str(query_dir),
    })

script_fields = [
    "query","protein_id","family","panel_order","panel_role",
    "reference_layer","target","visual_status",
    "query_model_pdb","query_model_pdb_portable","reference_file_path","reference_file_path_portable","unique_reference_id",
    "query_top1_score","query_top1_probability",
    "reference_top1_score","reference_top1_probability",
    "query_residue_count_used","reference_residue_count_used",
    "reference_pocket_signal","reference_pocket_overlay","query_pocket_overlay",
    "reference_pocket_interpretation",
    "pymol_script","chimerax_script","query_dir",
]

query_summary_fields = [
    "query","protein_id","family","panel_rows",
    "ready_query_and_reference_rows","zero_pocket_reference_rows",
    "zero_pocket_visual_scripts_created",
    "unreliable_ca_only_reference_rows","unreliable_ca_only_visual_scripts_created",
    "cache_missing_reference_rows","blocked_rows",
    "visual_scripts_created","query_dir",
]

skipped_fields = [
    "query","protein_id","family","panel_order","panel_role",
    "reference_layer","target","visual_status","skip_reason",
    "reference_file_path","reference_file_exists","reference_zero_pocket_flag",
]

write_tsv(package_manifest_path, script_rows, script_fields)
write_tsv(query_summary_path, query_summary_rows, query_summary_fields)
write_tsv(skipped_report_path, skipped_rows, skipped_fields)

readme_path.write_text(
    "M10C all-query visual/overlay script package\n"
    "============================================\n\n"
    "Purpose:\n"
    "Generate PyMOL and ChimeraX overlay scripts for every query-reference panel row that is READY_QUERY_AND_REFERENCE, READY_QUERY_REFERENCE_ZERO_POCKET, or READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY.\n\n"
    "Important:\n"
    "- PNG rendering is intentionally not required on the HPC cluster.\n"
    "- Use PyMOL or ChimeraX locally to render .pml/.cxc scripts.\n"
    "- Cache-missing references are listed in the skipped report.\n"
    "- Zero-pocket references generate query-pocket + reference-structure scripts only; this is not positive reference pocket support.\n\n"
    "- CA-only-like unreliable references are not biological no-pocket evidence.\n\n"
    f"Main manifest: {package_manifest_path}\n"
    f"Query summary: {query_summary_path}\n"
    f"Skipped report: {skipped_report_path}\n"
)

status_counter = Counter()
for r in rows:
    status_counter[r.get("visual_status", "")] += 1

qc = Counter()
qc["contract_rows"] = len(rows)
qc["query_count"] = len(by_query)
qc["script_manifest_rows"] = len(script_rows)
qc["query_summary_rows"] = len(query_summary_rows)
qc["skipped_rows"] = len(skipped_rows)
qc["pymol_script_files"] = len(list(out_root.rglob("*.pml")))
qc["chimerax_script_files"] = len(list(out_root.rglob("*.cxc")))
qc["ready_query_and_reference_rows"] = status_counter.get("READY_QUERY_AND_REFERENCE", 0)
qc["zero_pocket_rows"] = status_counter.get("READY_QUERY_REFERENCE_ZERO_POCKET", 0)
qc["zero_pocket_script_rows"] = sum(1 for r in script_rows if r.get("reference_pocket_signal") == "ABSENT")
qc["unreliable_ca_only_rows"] = status_counter.get("READY_QUERY_REFERENCE_UNRELIABLE_CA_ONLY", 0)
qc["unreliable_ca_only_script_rows"] = sum(1 for r in script_rows if r.get("reference_pocket_signal") == "UNRELIABLE_CA_ONLY_INPUT")
qc["cache_missing_rows"] = status_counter.get("READY_QUERY_ONLY_REFERENCE_CACHE_MISSING", 0)
qc["blocked_query_rows"] = status_counter.get("BLOCKED_QUERY_MODEL_MISSING", 0)
qc["queries_with_no_scripts"] = sum(1 for r in query_summary_rows if int(r["visual_scripts_created"]) == 0)

with qc_report_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric", "value"])
    for k in sorted(qc):
        w.writerow([k, qc[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["all_query_visual_script_manifest", str(package_manifest_path), "One row per generated query-reference visual script pair"])
    w.writerow(["all_query_visual_script_query_summary", str(query_summary_path), "One row per query visual script summary"])
    w.writerow(["all_query_visual_script_skipped_reference_report", str(skipped_report_path), "Skipped cache-missing/zero-pocket visual rows"])
    w.writerow(["all_query_visual_script_readme", str(readme_path), "M10C package README"])
    w.writerow(["all_query_visual_script_qc_report", str(qc_report_path), "M10C QC report"])

print("package_manifest:", package_manifest_path)
print("query_summary:", query_summary_path)
print("skipped_report:", skipped_report_path)
print("readme:", readme_path)
print("qc_report:", qc_report_path)
print("pointer:", pointer_path)
print("script_rows:", len(script_rows))
print("query_summary_rows:", len(query_summary_rows))
print("skipped_rows:", len(skipped_rows))
