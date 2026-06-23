#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter

if len(sys.argv) < 6:
    raise SystemExit(
        "Usage: 09b_resolve_reference_panel_files.py "
        "M08_PANEL REF_PANEL_MANIFEST RESOLVED_MANIFEST UNIQUE_REF_MANIFEST RESOLUTION_REPORT RESOLUTION_SUMMARY POINTER ROOT1 [ROOT2 ...]"
    )

m08_panel_path = Path(sys.argv[1])
ref_panel_manifest_path = Path(sys.argv[2])
resolved_manifest_path = Path(sys.argv[3])
unique_ref_manifest_path = Path(sys.argv[4])
resolution_report_path = Path(sys.argv[5])
resolution_summary_path = Path(sys.argv[6])
pointer_path = Path(sys.argv[7])
roots = [Path(x) for x in sys.argv[8:]]

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def target_candidates(target, layer):
    t = target or ""
    out = []
    out.append(t)
    out.append(t + ".pdb")
    out.append(t + ".cif")
    out.append(t + ".mmcif")

    if layer == "PDB":
        m = re.match(r"^([0-9][A-Za-z0-9]{3})-assembly([0-9]+)_([A-Za-z0-9-]+)$", t)
        if m:
            pdbid, assembly, chain = m.groups()
            pdbid_l = pdbid.lower()
            chain_l = chain.lower()
            atom_chain = chain.split("-", 1)[0]
            atom_chain_l = atom_chain.lower()
            out += [
                pdbid,
                pdbid_l,
                f"{pdbid}.pdb",
                f"{pdbid_l}.pdb",
                f"{pdbid}_{chain}.pdb",
                f"{pdbid_l}_{chain_l}.pdb",
                f"{pdbid}-assembly{assembly}_{chain}.pdb",
                f"{pdbid_l}-assembly{assembly}_{chain_l}.pdb",
                f"{pdbid}-assembly{assembly}_{chain}.chain_{atom_chain}.pdb",
                f"{pdbid_l}-assembly{assembly}_{chain_l}.chain_{atom_chain_l}.pdb",
                f"{pdbid}-assembly{assembly}_{chain}.chain_{atom_chain}.cif",
                f"{pdbid_l}-assembly{assembly}_{chain_l}.chain_{atom_chain_l}.cif",
                f"{pdbid}_assembly{assembly}_{chain}.pdb",
                f"{pdbid_l}_assembly{assembly}_{chain_l}.pdb",
                f"{pdbid}_{assembly}_{chain}.pdb",
                f"{pdbid_l}_{assembly}_{chain_l}.pdb",
            ]

    if layer == "AFSP":
        out.append(t.replace("-model_v6", ""))
        out.append(t.replace("-model_v6", "") + ".pdb")
        out.append(t.replace("-model_v6", "") + ".cif")
        out.append(t.replace("-model_v6", "") + ".mmcif")

    # unique preserve order
    seen = set()
    uniq = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq

def classify_file(path):
    p = str(path).replace("\\", "/")
    if "/reference_structures/materialized/pdb_chains/" in p:
        return "reference_structures_materialized_pdb_chains"
    if "/reference_structures/materialized/pdb/" in p:
        return "reference_structures_materialized_pdb"
    if "/reference_structures/materialized/afsp/" in p:
        return "reference_structures_materialized_afsp"
    if "/reference_structures/pdb_chains/" in p:
        return "reference_structures_pdb_chains"
    if "/reference_structures/pdb/" in p:
        return "reference_structures_pdb"
    if "/reference_structures/afsp/" in p:
        return "reference_structures_afsp"
    if "/pilot32_visual_qc_package/reference_pdb/" in p:
        return "visual_qc_reference_pdb"
    if "/pilot32_visual_qc_package/query_pdb/" in p:
        return "visual_qc_query_pdb"
    if "/foldseek_tm_align/querydb/" in p:
        return "foldseek_querydb_pdb_inputs"
    return "other"

# Build file index
all_files = []
for root in roots:
    if not root.exists():
        continue
    for ext in ("*.pdb", "*.cif", "*.mmcif"):
        all_files.extend(root.rglob(ext))

by_basename = defaultdict(list)
by_norm_basename = defaultdict(list)

for p in all_files:
    by_basename[p.name].append(p)
    by_basename[p.name.lower()].append(p)
    by_norm_basename[norm(p.stem)].append(p)
    by_norm_basename[norm(p.name)].append(p)

def resolve_target(target, layer):
    cands = target_candidates(target, layer)

    # 1) exact basename
    for c in cands:
        for key in (c, c.lower()):
            hits = by_basename.get(key, [])
            if hits:
                return hits[0], "EXACT_BASENAME", len(hits)

    # 2) normalized exact basename/stem
    for c in cands:
        hits = by_norm_basename.get(norm(c), [])
        if hits:
            return hits[0], "NORMALIZED_BASENAME", len(hits)

    # 3) PDB id + chain substring
    if layer == "PDB":
        m = re.match(r"^([0-9][A-Za-z0-9]{3})-assembly([0-9]+)_([A-Za-z0-9-]+)$", target or "")
        if m:
            pdbid, assembly, chain = m.groups()
            pdbid_n = norm(pdbid)
            chain_n = norm(chain.split("-", 1)[0])
            soft = []
            for p in all_files:
                s = norm(p.name)
                if pdbid_n in s and chain_n in s:
                    soft.append(p)
            if soft:
                return soft[0], "PDBID_CHAIN_SUBSTRING", len(soft)

            soft = []
            for p in all_files:
                s = norm(p.name)
                if pdbid_n in s:
                    soft.append(p)
            if soft:
                return soft[0], "PDBID_ONLY_SUBSTRING", len(soft)

    # 4) AF accession substring
    if layer == "AFSP":
        t = target or ""
        core = t.replace("-model_v6", "")
        soft = []
        for p in all_files:
            s = p.name
            if core in s or core.lower() in s.lower():
                soft.append(p)
        if soft:
            return soft[0], "AF_ACCESSION_SUBSTRING", len(soft)

    return None, "NOT_FOUND", 0

# Prefer the M08 panel because it has metrics. If malformed/missing, fall back to ref manifest.
panel_rows = read_tsv(m08_panel_path)

resolved_rows = []
report_rows = []

for r in panel_rows:
    q = r.get("query", "")
    layer = r.get("reference_layer", "")
    target = r.get("target", "")
    hit, method, n_matches = resolve_target(target, layer)

    path = str(hit) if hit else ""
    exists = "YES" if hit and hit.exists() else "NO"
    status = "RESOLVED" if exists == "YES" else "MISSING"

    resolved_rows.append({
        "query": q,
        "protein_id": r.get("protein_id", ""),
        "family": r.get("family", ""),
        "panel_order": r.get("panel_order", ""),
        "reference_layer": layer,
        "panel_role": r.get("panel_role", ""),
        "source_rank": r.get("source_rank", ""),
        "target": target,
        "support_class": r.get("support_class", ""),
        "selection_reason": r.get("selection_reason", ""),
        "reference_file_path": path,
        "reference_file_exists": exists,
        "reference_file_resolution_status": status,
        "resolution_method": method,
        "resolution_n_matches": n_matches,
        "reference_file_source_class": classify_file(hit) if hit else "",
        "p2rank_role": "REFERENCE_PANEL_TARGET",
    })

    report_rows.append({
        "query": q,
        "reference_layer": layer,
        "target": target,
        "resolution_status": status,
        "resolution_method": method,
        "resolution_n_matches": n_matches,
        "reference_file_path": path,
        "comment": "Resolved local structure file" if status == "RESOLVED" else "No local structure file found under configured roots",
    })

resolved_fields = [
    "query","protein_id","family","panel_order",
    "reference_layer","panel_role","source_rank","target",
    "support_class","selection_reason",
    "reference_file_path","reference_file_exists","reference_file_resolution_status",
    "resolution_method","resolution_n_matches","reference_file_source_class",
    "p2rank_role",
]

report_fields = [
    "query","reference_layer","target","resolution_status","resolution_method",
    "resolution_n_matches","reference_file_path","comment",
]

write_tsv(resolved_manifest_path, resolved_rows, resolved_fields)
write_tsv(resolution_report_path, report_rows, report_fields)

# Unique resolved files for P2Rank reference runs.
seen = set()
unique_rows = []
for r in resolved_rows:
    if r["reference_file_exists"] != "YES":
        continue
    key = r["reference_file_path"]
    if key in seen:
        continue
    seen.add(key)
    unique_rows.append({
        "unique_reference_id": f"REF{len(unique_rows)+1:05d}",
        "reference_layer": r["reference_layer"],
        "target": r["target"],
        "reference_file_path": r["reference_file_path"],
        "reference_file_source_class": r["reference_file_source_class"],
        "support_class": r["support_class"],
        "example_query": r["query"],
        "p2rank_role": "UNIQUE_REFERENCE_STRUCTURE",
    })

unique_fields = [
    "unique_reference_id","reference_layer","target","reference_file_path",
    "reference_file_source_class","support_class","example_query","p2rank_role",
]
write_tsv(unique_ref_manifest_path, unique_rows, unique_fields)

summary = Counter()
summary["panel_rows"] = len(resolved_rows)
summary["resolved_rows"] = sum(1 for r in resolved_rows if r["reference_file_exists"] == "YES")
summary["missing_rows"] = sum(1 for r in resolved_rows if r["reference_file_exists"] != "YES")
summary["unique_resolved_reference_files"] = len(unique_rows)
summary["candidate_structure_files_indexed"] = len(all_files)

for r in resolved_rows:
    summary[f"layer_{r['reference_layer']}_rows"] += 1
    summary[f"layer_{r['reference_layer']}_resolved"] += 1 if r["reference_file_exists"] == "YES" else 0
    summary[f"status_{r['reference_file_resolution_status']}"] += 1
    summary[f"method_{r['resolution_method']}"] += 1
    if r["reference_file_source_class"]:
        summary[f"source_{r['reference_file_source_class']}"] += 1

with resolution_summary_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    for k in sorted(summary):
        w.writerow([k, summary[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["p2rank_reference_panel_manifest_resolved", str(resolved_manifest_path), "Reference panel manifest with local structure file resolution"])
    w.writerow(["p2rank_reference_unique_structure_manifest", str(unique_ref_manifest_path), "Unique resolved reference structure files for P2Rank"])
    w.writerow(["reference_file_resolution_detailed", str(resolution_report_path), "Detailed target-to-file resolution report"])
    w.writerow(["reference_file_resolution_summary", str(resolution_summary_path), "M09B reference resolution summary"])

print("candidate_structure_files_indexed:", len(all_files))
print("resolved_manifest:", resolved_manifest_path)
print("unique_ref_manifest:", unique_ref_manifest_path)
print("resolution_report:", resolution_report_path)
print("resolution_summary:", resolution_summary_path)
print("pointer:", pointer_path)
print("panel_rows:", len(resolved_rows))
print("resolved_rows:", summary["resolved_rows"])
print("missing_rows:", summary["missing_rows"])
print("unique_resolved_reference_files:", len(unique_rows))
