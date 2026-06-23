#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from collections import defaultdict, Counter

def read_tsv(path):
    path = Path(path)
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))

def write_tsv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def fnum(x, default=None):
    try:
        if x is None or x == "" or x == "NA":
            return default
        return float(x)
    except Exception:
        return default

def yesno(v):
    return "YES" if str(v).upper() == "YES" else "NO"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--decision", required=True)
    ap.add_argument("--visual-contract", required=True)
    ap.add_argument("--query-top1", required=True)
    ap.add_argument("--reference-top1", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    panel = read_tsv(args.panel)
    decision = read_tsv(args.decision)
    visual = read_tsv(args.visual_contract)
    query_top1 = read_tsv(args.query_top1)
    ref_top1 = read_tsv(args.reference_top1)

    decision_by_query = {r["query"]: r for r in decision}
    visual_by_key = {(r["query"], r["reference_layer"], r["target"], str(r["panel_order"])): r for r in visual}
    query_top1_by_query = {r["query"]: r for r in query_top1}

    # The visual contract already carries resolved reference P2Rank status and reference top1 pocket details.
    supporting_rows = []
    for r in panel:
        po = str(r.get("panel_order", ""))
        if po in ("1", "1.0") or r.get("panel_role") == "PRIMARY":
            continue

        q = r["query"]
        layer = r["reference_layer"]
        target = r["target"]
        key = (q, layer, target, po)
        v = visual_by_key.get(key, {})
        d = decision_by_query.get(q, {})
        qt = query_top1_by_query.get(q, {})

        support_class = r.get("support_class", "")
        visual_status = v.get("visual_status", "NO_VISUAL_CONTRACT_MATCH")

        reference_file_exists = v.get("reference_file_exists", "NO")
        reference_p2rank_status = v.get("reference_p2rank_status", "")
        reference_zero_pocket_flag = v.get("reference_zero_pocket_flag", "")
        reference_top1_probability = v.get("reference_top1_probability", "")
        reference_top1_score = v.get("reference_top1_score", "")

        qtmscore = fnum(r.get("qtmscore"))
        qcov = fnum(r.get("qcov"))
        tcov = fnum(r.get("tcov"))
        prob = fnum(r.get("prob"))
        ref_prob = fnum(reference_top1_probability)

        is_resolved = reference_file_exists == "YES"
        is_zero_pocket = reference_zero_pocket_flag == "YES"
        is_ref_pocket_ready = is_resolved and reference_p2rank_status == "OK" and not is_zero_pocket

        strong_struct = "YES" if "STRONG" in support_class else "NO"
        moderate_struct = "YES" if "MODERATE" in support_class else "NO"
        weak_struct = "YES" if "WEAK" in support_class or "PARTIAL" in support_class else "NO"

        cache_missing_flag = "YES" if "CACHE_MISSING" in visual_status or reference_file_exists != "YES" else "NO"
        zero_pocket_flag = "YES" if is_zero_pocket else "NO"
        ready_ref_flag = "YES" if is_ref_pocket_ready else "NO"

        interpretation_flags = []
        if cache_missing_flag == "YES":
            interpretation_flags.append("REFERENCE_CACHE_MISSING")
        if zero_pocket_flag == "YES":
            interpretation_flags.append("REFERENCE_ZERO_POCKET")
        if ready_ref_flag == "YES":
            interpretation_flags.append("REFERENCE_POCKET_READY")
        if strong_struct == "YES":
            interpretation_flags.append("SUPPORTING_STRONG_STRUCT_MATCH")
        if moderate_struct == "YES":
            interpretation_flags.append("SUPPORTING_MODERATE_STRUCT_MATCH")
        if qtmscore is not None and qcov is not None and qtmscore >= 0.7 and qcov >= 0.7:
            interpretation_flags.append("BROAD_SUPPORTING_FOLD_MATCH")
        if ref_prob is not None and ref_prob >= 0.5:
            interpretation_flags.append("SUPPORTING_REFERENCE_HIGH_POCKET_PROB")
        if layer == "AFSP":
            interpretation_flags.append("AFSP_CONTEXT")
        if layer == "PDB":
            interpretation_flags.append("PDB_CONTEXT")

        if not interpretation_flags:
            interpretation_flags.append("SUPPORTING_CONTEXT_ONLY")

        supporting_rows.append({
            "mode": mode,
            "query": q,
            "protein_id": r.get("protein_id", ""),
            "family": r.get("family", ""),
            "primary_reference_layer": d.get("primary_reference_layer", ""),
            "primary_reference_target": d.get("primary_reference_target", ""),
            "primary_reference_class": d.get("primary_reference_class", ""),
            "primary_interpretation_policy": d.get("interpretation_policy", ""),
            "manual_review_level": d.get("manual_review_level", ""),
            "manual_review_flags": d.get("manual_review_flags", ""),
            "panel_order": po,
            "panel_role": r.get("panel_role", ""),
            "reference_layer": layer,
            "target": target,
            "source_rank": r.get("source_rank", ""),
            "support_class": support_class,
            "selection_reason": r.get("selection_reason", ""),
            "foldseek_prob": r.get("prob", ""),
            "foldseek_qtmscore": r.get("qtmscore", ""),
            "foldseek_qcov": r.get("qcov", ""),
            "foldseek_tcov": r.get("tcov", ""),
            "query_top1_pocket_probability": qt.get("top1_probability", ""),
            "query_top1_pocket_score": qt.get("top1_score", ""),
            "query_top1_residue_ids": qt.get("top1_residue_ids", ""),
            "visual_status": visual_status,
            "reference_file_exists": reference_file_exists,
            "reference_file_resolution_status": v.get("reference_file_resolution_status", ""),
            "unique_reference_id": v.get("unique_reference_id", ""),
            "reference_p2rank_status": reference_p2rank_status,
            "reference_zero_pocket_flag": reference_zero_pocket_flag,
            "reference_top1_pocket_probability": reference_top1_probability,
            "reference_top1_pocket_score": reference_top1_score,
            "reference_top1_residue_ids": v.get("reference_top1_residue_ids", ""),
            "supporting_reference_resolved": "YES" if is_resolved else "NO",
            "supporting_reference_pocket_ready": ready_ref_flag,
            "supporting_reference_cache_missing": cache_missing_flag,
            "supporting_reference_zero_pocket": zero_pocket_flag,
            "supporting_strong_struct_match": strong_struct,
            "supporting_moderate_struct_match": moderate_struct,
            "supporting_weak_or_partial_struct_match": weak_struct,
            "interpretation_flags": ";".join(interpretation_flags),
        })

    audit_fields = [
        "mode","query","protein_id","family",
        "primary_reference_layer","primary_reference_target","primary_reference_class","primary_interpretation_policy",
        "manual_review_level","manual_review_flags",
        "panel_order","panel_role","reference_layer","target","source_rank","support_class","selection_reason",
        "foldseek_prob","foldseek_qtmscore","foldseek_qcov","foldseek_tcov",
        "query_top1_pocket_probability","query_top1_pocket_score","query_top1_residue_ids",
        "visual_status","reference_file_exists","reference_file_resolution_status","unique_reference_id",
        "reference_p2rank_status","reference_zero_pocket_flag","reference_top1_pocket_probability","reference_top1_pocket_score","reference_top1_residue_ids",
        "supporting_reference_resolved","supporting_reference_pocket_ready","supporting_reference_cache_missing","supporting_reference_zero_pocket",
        "supporting_strong_struct_match","supporting_moderate_struct_match","supporting_weak_or_partial_struct_match",
        "interpretation_flags",
    ]

    audit_path = outdir / f"{mode}_supporting_reference_audit.tsv"
    write_tsv(audit_path, supporting_rows, audit_fields)

    # Per-query conflict/context flags
    by_query = defaultdict(list)
    for r in supporting_rows:
        by_query[r["query"]].append(r)

    conflict_rows = []
    for q, rows in sorted(by_query.items()):
        d = decision_by_query.get(q, {})
        n = len(rows)
        n_resolved = sum(r["supporting_reference_resolved"] == "YES" for r in rows)
        n_ready = sum(r["supporting_reference_pocket_ready"] == "YES" for r in rows)
        n_cache_missing = sum(r["supporting_reference_cache_missing"] == "YES" for r in rows)
        n_zero = sum(r["supporting_reference_zero_pocket"] == "YES" for r in rows)
        n_strong = sum(r["supporting_strong_struct_match"] == "YES" for r in rows)
        n_moderate = sum(r["supporting_moderate_struct_match"] == "YES" for r in rows)
        n_pdb = sum(r["reference_layer"] == "PDB" for r in rows)
        n_afsp = sum(r["reference_layer"] == "AFSP" for r in rows)
        n_high_ref_pocket = sum("SUPPORTING_REFERENCE_HIGH_POCKET_PROB" in r["interpretation_flags"] for r in rows)

        flags = []
        if n_cache_missing > 0:
            flags.append("SOME_SUPPORTING_REFERENCES_CACHE_MISSING")
        if n_ready > 0:
            flags.append("SUPPORTING_POCKET_CONTEXT_AVAILABLE")
        if n_strong > 0:
            flags.append("SUPPORTING_STRONG_STRUCTURAL_CONTEXT")
        if n_zero > 0:
            flags.append("SOME_SUPPORTING_REFERENCES_ZERO_POCKET")
        if n_high_ref_pocket > 0:
            flags.append("SUPPORTING_HIGH_REFERENCE_POCKET_PROB")
        if n_ready == 0:
            flags.append("NO_SUPPORTING_REFERENCE_POCKET_READY")
        if n_afsp > 0 and n_pdb > 0:
            flags.append("PDB_AND_AFSP_SUPPORTING_CONTEXT")

        if n_strong > 0 and n_ready > 0:
            supporting_context_class = "SUPPORTING_STRUCTURAL_AND_POCKET_CONTEXT"
        elif n_strong > 0:
            supporting_context_class = "SUPPORTING_STRUCTURAL_CONTEXT_ONLY"
        elif n_ready > 0:
            supporting_context_class = "SUPPORTING_POCKET_CONTEXT_ONLY"
        elif n_cache_missing == n:
            supporting_context_class = "SUPPORTING_REFERENCES_UNRESOLVED"
        else:
            supporting_context_class = "LIMITED_SUPPORTING_CONTEXT"

        conflict_rows.append({
            "mode": mode,
            "query": q,
            "protein_id": rows[0]["protein_id"],
            "family": rows[0]["family"],
            "primary_reference_layer": d.get("primary_reference_layer", ""),
            "primary_reference_target": d.get("primary_reference_target", ""),
            "primary_reference_class": d.get("primary_reference_class", ""),
            "manual_review_level": d.get("manual_review_level", ""),
            "supporting_reference_n": n,
            "supporting_resolved_n": n_resolved,
            "supporting_pocket_ready_n": n_ready,
            "supporting_cache_missing_n": n_cache_missing,
            "supporting_zero_pocket_n": n_zero,
            "supporting_strong_struct_n": n_strong,
            "supporting_moderate_struct_n": n_moderate,
            "supporting_pdb_n": n_pdb,
            "supporting_afsp_n": n_afsp,
            "supporting_high_reference_pocket_prob_n": n_high_ref_pocket,
            "supporting_context_class": supporting_context_class,
            "supporting_interpretation_flags": ";".join(flags) if flags else "NO_MAJOR_SUPPORTING_FLAG",
        })

    conflict_fields = [
        "mode","query","protein_id","family",
        "primary_reference_layer","primary_reference_target","primary_reference_class","manual_review_level",
        "supporting_reference_n","supporting_resolved_n","supporting_pocket_ready_n","supporting_cache_missing_n",
        "supporting_zero_pocket_n","supporting_strong_struct_n","supporting_moderate_struct_n",
        "supporting_pdb_n","supporting_afsp_n","supporting_high_reference_pocket_prob_n",
        "supporting_context_class","supporting_interpretation_flags",
    ]

    conflict_path = outdir / f"{mode}_supporting_reference_conflict_flags.tsv"
    write_tsv(conflict_path, conflict_rows, conflict_fields)

    # Family summary
    fam = defaultdict(list)
    for r in conflict_rows:
        fam[r["family"]].append(r)

    family_rows = []
    for family, rows in sorted(fam.items()):
        family_rows.append({
            "mode": mode,
            "family": family,
            "n_queries": len(rows),
            "supporting_reference_total": sum(int(r["supporting_reference_n"]) for r in rows),
            "supporting_resolved_total": sum(int(r["supporting_resolved_n"]) for r in rows),
            "supporting_pocket_ready_total": sum(int(r["supporting_pocket_ready_n"]) for r in rows),
            "supporting_cache_missing_total": sum(int(r["supporting_cache_missing_n"]) for r in rows),
            "supporting_strong_struct_total": sum(int(r["supporting_strong_struct_n"]) for r in rows),
            "queries_with_structural_and_pocket_context": sum(r["supporting_context_class"]=="SUPPORTING_STRUCTURAL_AND_POCKET_CONTEXT" for r in rows),
            "queries_with_unresolved_supporting_references": sum(r["supporting_context_class"]=="SUPPORTING_REFERENCES_UNRESOLVED" for r in rows),
        })

    family_fields = [
        "mode","family","n_queries","supporting_reference_total","supporting_resolved_total",
        "supporting_pocket_ready_total","supporting_cache_missing_total","supporting_strong_struct_total",
        "queries_with_structural_and_pocket_context","queries_with_unresolved_supporting_references",
    ]

    family_path = outdir / f"{mode}_supporting_reference_family_summary.tsv"
    write_tsv(family_path, family_rows, family_fields)

    # QC
    visual_n = len(visual)
    panel_n = len(panel)
    supporting_expected = sum(1 for r in panel if str(r.get("panel_order","")) not in ("1","1.0") and r.get("panel_role") != "PRIMARY")
    qc_rows = [
        {"metric": "module", "value": "M11_supporting_reference_audit"},
        {"metric": "status", "value": "OK"},
        {"metric": "mode", "value": mode},
        {"metric": "panel_rows", "value": str(panel_n)},
        {"metric": "visual_contract_rows", "value": str(visual_n)},
        {"metric": "supporting_expected_rows", "value": str(supporting_expected)},
        {"metric": "supporting_audit_rows", "value": str(len(supporting_rows))},
        {"metric": "conflict_flag_rows", "value": str(len(conflict_rows))},
        {"metric": "family_summary_rows", "value": str(len(family_rows))},
        {"metric": "supporting_resolved_rows", "value": str(sum(r["supporting_reference_resolved"]=="YES" for r in supporting_rows))},
        {"metric": "supporting_pocket_ready_rows", "value": str(sum(r["supporting_reference_pocket_ready"]=="YES" for r in supporting_rows))},
        {"metric": "supporting_cache_missing_rows", "value": str(sum(r["supporting_reference_cache_missing"]=="YES" for r in supporting_rows))},
        {"metric": "supporting_zero_pocket_rows", "value": str(sum(r["supporting_reference_zero_pocket"]=="YES" for r in supporting_rows))},
        {"metric": "png_generated", "value": "NO"},
        {"metric": "audit_path", "value": str(audit_path)},
        {"metric": "conflict_path", "value": str(conflict_path)},
        {"metric": "family_summary_path", "value": str(family_path)},
    ]

    qc_path = outdir / f"{mode}_supporting_reference_audit_qc.tsv"
    write_tsv(qc_path, qc_rows, ["metric","value"])

    # Pointer
    ptr_rows = [
        {"artifact_key":"supporting_reference_audit","path":str(audit_path),"role":"Rank-2 to rank-5 supporting reference audit; no PNG generation"},
        {"artifact_key":"supporting_reference_conflict_flags","path":str(conflict_path),"role":"Per-query supporting reference context/conflict flags for decision matrix"},
        {"artifact_key":"supporting_reference_family_summary","path":str(family_path),"role":"Family-level supporting reference audit summary"},
        {"artifact_key":"supporting_reference_audit_qc","path":str(qc_path),"role":"M11 QC report"},
    ]
    ptr_path = Path("pipeline_state/artifacts/m11_supporting_reference_audit_pointer.tsv")
    write_tsv(ptr_path, ptr_rows, ["artifact_key","path","role"])

    print("M11_SUPPORTING_REFERENCE_AUDIT_OK")
    print("audit_path", audit_path)
    print("conflict_path", conflict_path)
    print("family_summary_path", family_path)
    print("qc_path", qc_path)
    print("pointer_path", ptr_path)
    print("supporting_audit_rows", len(supporting_rows))
    print("conflict_flag_rows", len(conflict_rows))
    print("family_summary_rows", len(family_rows))

if __name__ == "__main__":
    main()
