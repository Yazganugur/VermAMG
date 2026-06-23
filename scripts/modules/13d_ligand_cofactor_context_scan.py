#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from collections import Counter, defaultdict

def read_tsv(path):
    path = Path(path)
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))

def write_tsv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def split_codes(x):
    if not x:
        return []
    return [c.strip() for c in x.split(";") if c.strip()]

def unique_join(xs):
    out, seen = [], set()
    for x in xs:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return ";".join(out)

def load_ligand_dictionary(raw_path, fallback_path):
    raw = read_tsv(raw_path)
    fallback = read_tsv(fallback_path)

    d = {}

    # IMPORTANT: official code column is ligand_resn from 6AH policy.
    for r in raw:
        code = (r.get("ligand_resn") or r.get("ligand_code") or "").strip()
        if not code:
            continue
        d[code] = {
            "source": "CURATED_DICTIONARY",
            "ligand_code": code,
            "class": r.get("biological_class", ""),
            "support_level": r.get("support_level", ""),
            "interpretation_policy": (
                "BIOLOGICAL_SUPPORT" if r.get("support_level") == "YES"
                else "MANUAL_OR_RULE_DEPENDENT" if "DEPENDENT" in r.get("support_level","")
                else "MANUAL_ONLY" if r.get("support_level") == "MANUAL"
                else "NO_UPGRADE" if r.get("support_level") == "NO"
                else "REVIEW"
            ),
            "note": r.get("note", ""),
        }

    for r in fallback:
        code = r.get("ligand_code", "").strip()
        if not code:
            continue
        if code not in d:
            d[code] = {
                "source": "CONSERVATIVE_FALLBACK",
                "ligand_code": code,
                "class": r.get("fallback_class", ""),
                "support_level": r.get("support_level", ""),
                "interpretation_policy": r.get("interpretation_policy", ""),
                "note": r.get("note", ""),
            }

    return d

def classify_reference(row, het_by_path, ligdict):
    layer = row.get("reference_layer", "")
    ref_exists = row.get("reference_file_exists", "")
    scan_eligible = row.get("scan_eligible_for_ligand_hetatm", "")
    scan_note = row.get("scan_eligibility_note", "")
    ref_path = row.get("reference_file_path", "")

    if layer == "AFSP":
        return {
            "ligand_context_class": "AFSP_NO_CRYSTAL_LIGAND_CONTEXT",
            "positive_biological_ligands": "",
            "biological_metal_or_cluster_ligands": "",
            "manual_context_ligands": "",
            "nonbiological_ligands": "",
            "ignored_ligands": "",
            "unknown_unclassified_ligands": "",
            "all_ligand_codes": "",
            "ligand_interpretation_notes": "AFSP/predicted structure: no experimental crystallographic ligand context expected.",
            "hetatm_status": "NOT_APPLICABLE_AFSP",
            "hetatm_lines": "0",
        }

    if not ref_path or ref_exists != "YES":
        return {
            "ligand_context_class": "REFERENCE_FILE_MISSING",
            "positive_biological_ligands": "",
            "biological_metal_or_cluster_ligands": "",
            "manual_context_ligands": "",
            "nonbiological_ligands": "",
            "ignored_ligands": "",
            "unknown_unclassified_ligands": "",
            "all_ligand_codes": "",
            "ligand_interpretation_notes": "Reference file unavailable; ligand/cofactor scan not performed.",
            "hetatm_status": "REFERENCE_FILE_MISSING",
            "hetatm_lines": "0",
        }

    if scan_eligible != "YES":
        return {
            "ligand_context_class": "NOT_SCAN_ELIGIBLE",
            "positive_biological_ligands": "",
            "biological_metal_or_cluster_ligands": "",
            "manual_context_ligands": "",
            "nonbiological_ligands": "",
            "ignored_ligands": "",
            "unknown_unclassified_ligands": "",
            "all_ligand_codes": "",
            "ligand_interpretation_notes": f"Not scan eligible: {scan_note}",
            "hetatm_status": "NOT_SCAN_ELIGIBLE",
            "hetatm_lines": "0",
        }

    het = het_by_path.get(ref_path, {})
    hetatm_status = het.get("hetatm_status", "")
    hetatm_lines = het.get("hetatm_lines", "0")
    codes = split_codes(het.get("unique_ligand_codes", ""))

    if not codes or hetatm_status == "NO_HETATM_APO_OR_CLEAN_PDB":
        return {
            "ligand_context_class": "NO_HETATM_APO_OR_CLEAN_PDB",
            "positive_biological_ligands": "",
            "biological_metal_or_cluster_ligands": "",
            "manual_context_ligands": "",
            "nonbiological_ligands": "",
            "ignored_ligands": "",
            "unknown_unclassified_ligands": "",
            "all_ligand_codes": "",
            "ligand_interpretation_notes": "No HETATM records detected; apo/clean PDB context.",
            "hetatm_status": hetatm_status or "NO_HETATM_APO_OR_CLEAN_PDB",
            "hetatm_lines": hetatm_lines,
        }

    positive = []
    bio_metal = []
    manual = []
    nonbio = []
    ignored = []
    unknown = []
    notes = []

    for code in codes:
        info = ligdict.get(code)
        if not info:
            unknown.append(code)
            notes.append(f"{code}: not in curated dictionary or fallback; treat as unknown/no upgrade.")
            continue

        policy = info.get("interpretation_policy", "")
        support = info.get("support_level", "")
        cls = info.get("class", "")
        note = info.get("note", "")
        source = info.get("source", "")

        if policy == "IGNORE":
            ignored.append(code)
        elif policy == "NO_UPGRADE":
            nonbio.append(code)
        elif policy == "BIOLOGICAL_SUPPORT":
            if "METAL" in cls or "CLUSTER" in cls:
                bio_metal.append(code)
            else:
                positive.append(code)
        elif policy in {"MANUAL_ONLY", "MANUAL_OR_RULE_DEPENDENT"}:
            manual.append(code)
        else:
            manual.append(code)

        notes.append(f"{code}:{cls}:{support}:{policy}:{source}:{note}")

    if positive or bio_metal:
        ligand_context_class = "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT"
    elif manual and not positive and not bio_metal:
        # If only manual ions/metals plus water/nonbio exist, keep conservative.
        ligand_context_class = "MANUAL_CONTEXT_LIGAND_PRESENT_NO_AUTOMATIC_SUPPORT"
    elif nonbio and not manual and not positive and not bio_metal:
        ligand_context_class = "NONBIOLOGICAL_HETATM_ONLY"
    elif ignored and not nonbio and not manual and not positive and not bio_metal:
        ligand_context_class = "WATER_ONLY_OR_APO_LIKE"
    elif unknown and not positive and not bio_metal:
        ligand_context_class = "UNKNOWN_HETATM_NO_AUTOMATIC_SUPPORT"
    else:
        ligand_context_class = "NO_BIOLOGICAL_LIGAND_AFTER_FILTER"

    return {
        "ligand_context_class": ligand_context_class,
        "positive_biological_ligands": unique_join(positive),
        "biological_metal_or_cluster_ligands": unique_join(bio_metal),
        "manual_context_ligands": unique_join(manual),
        "nonbiological_ligands": unique_join(nonbio),
        "ignored_ligands": unique_join(ignored),
        "unknown_unclassified_ligands": unique_join(unknown),
        "all_ligand_codes": unique_join(codes),
        "ligand_interpretation_notes": " | ".join(notes),
        "hetatm_status": hetatm_status,
        "hetatm_lines": hetatm_lines,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--scan-map", required=True)
    ap.add_argument("--hetatm-inventory", required=True)
    ap.add_argument("--ligand-dictionary", required=True)
    ap.add_argument("--fallback", required=True)
    ap.add_argument("--m13b", required=True)
    ap.add_argument("--m13c-notes", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    scan_map = read_tsv(args.scan_map)
    hetatm = read_tsv(args.hetatm_inventory)
    m13b = read_tsv(args.m13b)
    notes = read_tsv(args.m13c_notes)
    ligdict = load_ligand_dictionary(args.ligand_dictionary, args.fallback)

    het_by_path = {r["reference_file_path"]: r for r in hetatm}
    m13b_by_query = {r["query"]: r for r in m13b}
    notes_by_query = {r["query"]: r for r in notes}

    primary_rows = []
    supporting_rows = []

    for r in scan_map:
        cls = classify_reference(r, het_by_path, ligdict)
        m13b_row = m13b_by_query.get(r.get("query",""), {})
        note_row = notes_by_query.get(r.get("query",""), {})

        out = {
            "mode": mode,
            "query": r.get("query", ""),
            "protein_id": m13b_row.get("protein_id", r.get("protein_id", "")),
            "original_protein_id": r.get("protein_id", ""),
            "family": r.get("family", ""),
            "panel_order": r.get("panel_order", ""),
            "panel_role": r.get("panel_role", ""),
            "reference_layer": r.get("reference_layer", ""),
            "target": r.get("target", ""),
            "reference_file_path": r.get("reference_file_path", ""),
            "reference_file_exists": r.get("reference_file_exists", ""),
            "scan_eligible_for_ligand_hetatm": r.get("scan_eligible_for_ligand_hetatm", ""),
            "scan_eligibility_note": r.get("scan_eligibility_note", ""),
            "reference_p2rank_status": r.get("reference_p2rank_status", ""),
            "reference_zero_pocket_flag": r.get("reference_zero_pocket_flag", ""),
            "reference_top1_pocket_probability": r.get("reference_top1_pocket_probability", ""),
            "m13b_classification_status": m13b_row.get("m13b_classification_status", ""),
            "m13b_existing_rulebook_class": m13b_row.get("m13b_existing_rulebook_class", ""),
            "m13c_supporting_context_classes": note_row.get("supporting_context_classes", ""),
            **cls,
            "does_this_override_primary_or_m13b": "NO",
            "m13d_policy": "HETATM_NOT_EQUAL_BIOLOGICAL_SUPPORT__PRIMARY_PLUS_SUPPORTING_NO_OVERRIDE",
        }

        if str(r.get("panel_order", "")) == "1" or r.get("panel_role") == "PRIMARY":
            primary_rows.append(out)
        else:
            supporting_rows.append(out)

    common_fields = [
        "mode","query","protein_id","original_protein_id","family",
        "panel_order","panel_role","reference_layer","target",
        "reference_file_path","reference_file_exists",
        "scan_eligible_for_ligand_hetatm","scan_eligibility_note",
        "reference_p2rank_status","reference_zero_pocket_flag","reference_top1_pocket_probability",
        "m13b_classification_status","m13b_existing_rulebook_class","m13c_supporting_context_classes",
        "ligand_context_class","positive_biological_ligands","biological_metal_or_cluster_ligands",
        "manual_context_ligands","nonbiological_ligands","ignored_ligands","unknown_unclassified_ligands",
        "all_ligand_codes","hetatm_status","hetatm_lines","ligand_interpretation_notes",
        "does_this_override_primary_or_m13b","m13d_policy",
    ]

    primary_path = outdir / f"{mode}_ligand_cofactor_primary_context.tsv"
    support_path = outdir / f"{mode}_ligand_cofactor_supporting_context.tsv"
    write_tsv(primary_path, primary_rows, common_fields)
    write_tsv(support_path, supporting_rows, common_fields)

    summary_counts = Counter()
    for r in primary_rows:
        summary_counts[("primary", r["ligand_context_class"])] += 1
    for r in supporting_rows:
        summary_counts[("supporting", r["ligand_context_class"])] += 1

    summary_rows = [
        {"scope": scope, "ligand_context_class": cls, "n": n}
        for (scope, cls), n in sorted(summary_counts.items())
    ]

    summary_path = outdir / f"{mode}_ligand_cofactor_context_summary.tsv"
    write_tsv(summary_path, summary_rows, ["scope","ligand_context_class","n"])

    override_n = sum(r["does_this_override_primary_or_m13b"] != "NO" for r in primary_rows + supporting_rows)

    qc_rows = [
        {"metric":"module","value":"M13D_ligand_cofactor_context_scan"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"scan_map_rows","value":str(len(scan_map))},
        {"metric":"primary_rows","value":str(len(primary_rows))},
        {"metric":"supporting_rows","value":str(len(supporting_rows))},
        {"metric":"hetatm_inventory_rows","value":str(len(hetatm))},
        {"metric":"ligand_dictionary_total_codes","value":str(len(ligdict))},
        {"metric":"primary_positive_biological_context_rows","value":str(sum(1 for r in primary_rows if r["ligand_context_class"] == "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT"))},
        {"metric":"supporting_positive_biological_context_rows","value":str(sum(1 for r in supporting_rows if r["ligand_context_class"] == "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT"))},
        {"metric":"override_primary_or_m13b_count","value":str(override_n)},
        {"metric":"primary_path","value":str(primary_path)},
        {"metric":"supporting_path","value":str(support_path)},
        {"metric":"summary_path","value":str(summary_path)},
    ]

    qc_path = outdir / f"{mode}_ligand_cofactor_context_qc.tsv"
    write_tsv(qc_path, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"ligand_cofactor_primary_context","path":str(primary_path),"role":"M13D primary/rank-1 ligand/cofactor context"},
        {"artifact_key":"ligand_cofactor_supporting_context","path":str(support_path),"role":"M13D supporting rank-2-to-rank-5 ligand/cofactor context"},
        {"artifact_key":"ligand_cofactor_context_summary","path":str(summary_path),"role":"M13D ligand/cofactor context summary"},
        {"artifact_key":"ligand_cofactor_context_qc","path":str(qc_path),"role":"M13D QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m13d_ligand_cofactor_context_scan_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M13D_LIGAND_COFACTOR_CONTEXT_SCAN_OK")
    print("primary_rows", len(primary_rows))
    print("supporting_rows", len(supporting_rows))
    print("primary_positive_biological_context_rows", sum(1 for r in primary_rows if r["ligand_context_class"] == "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT"))
    print("supporting_positive_biological_context_rows", sum(1 for r in supporting_rows if r["ligand_context_class"] == "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT"))
    print("override_primary_or_m13b_count", override_n)
    print("primary", primary_path)
    print("supporting", support_path)
    print("summary", summary_path)
    print("qc", qc_path)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
