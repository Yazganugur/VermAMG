#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from collections import Counter, defaultdict

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

def classify_supporting(row):
    qtmscore = fnum(row.get("foldseek_qtmscore"))
    qcov = fnum(row.get("foldseek_qcov"))
    tcov = fnum(row.get("foldseek_tcov"))
    ref_prob = fnum(row.get("reference_top1_pocket_probability"))
    query_prob = fnum(row.get("query_top1_pocket_probability"))

    support_class = row.get("support_class", "")
    resolved = row.get("supporting_reference_resolved") == "YES"
    pocket_ready = row.get("supporting_reference_pocket_ready") == "YES"
    cache_missing = row.get("supporting_reference_cache_missing") == "YES"
    zero_pocket = row.get("supporting_reference_zero_pocket") == "YES"
    reference_pocket_signal = row.get("reference_pocket_signal", "")
    reference_ca_only_like = row.get("reference_ca_only_like", "")
    unreliable_ca_only = (
        reference_pocket_signal == "UNRELIABLE_CA_ONLY_INPUT"
        or (zero_pocket and reference_ca_only_like == "YES")
    )

    flags = []

    if cache_missing:
        flags.append("REFERENCE_CACHE_MISSING")
    if zero_pocket:
        flags.append("REFERENCE_ZERO_POCKET")
    if unreliable_ca_only:
        flags.append("REFERENCE_POCKET_UNRELIABLE_CA_ONLY_INPUT")
    if resolved:
        flags.append("REFERENCE_FILE_RESOLVED")
    if pocket_ready:
        flags.append("REFERENCE_POCKET_READY")

    if "STRONG" in support_class:
        flags.append("STRONG_STRUCTURAL_SUPPORT")
    elif "MODERATE" in support_class:
        flags.append("MODERATE_STRUCTURAL_SUPPORT")
    elif "PARTIAL" in support_class or "DOMAIN" in support_class:
        flags.append("DOMAIN_OR_PARTIAL_SUPPORT")
    elif "WEAK" in support_class or "NO" in support_class:
        flags.append("WEAK_OR_NO_STRUCTURAL_SUPPORT")

    if qtmscore is not None and qcov is not None:
        if qtmscore >= 0.85 and qcov >= 0.8:
            flags.append("HIGH_QTM_AND_QCOV")
        elif qtmscore >= 0.7 and qcov >= 0.6:
            flags.append("MODERATE_QTM_OR_QCOV")
        elif qcov < 0.6:
            flags.append("LOW_QUERY_COVERAGE_WARNING")

    if ref_prob is not None:
        if ref_prob >= 0.5:
            flags.append("HIGH_REFERENCE_POCKET_PROB")
        elif ref_prob >= 0.1:
            flags.append("LOW_TO_MODERATE_REFERENCE_POCKET_PROB")
        else:
            flags.append("VERY_LOW_REFERENCE_POCKET_PROB")

    # Class is intentionally supporting-only; it must not override primary decision.
    if cache_missing:
        decision_class = "SUPPORTING_REFERENCE_UNRESOLVED"
        priority = "AUDIT_ONLY_CACHE_MISSING"
        note = "Supporting reference was selected by Foldseek/reference panel but local structure/P2Rank evidence is unavailable."
    elif unreliable_ca_only:
        decision_class = "SUPPORTING_STRUCTURAL_CONTEXT_REFERENCE_POCKET_UNRELIABLE_CA_ONLY"
        priority = "LOW_CONTEXT"
        note = "CA-only reference input; zero pockets are not biological absence."
    elif zero_pocket:
        decision_class = "SUPPORTING_STRUCTURAL_CONTEXT_ZERO_POCKET"
        priority = "LOW_CONTEXT"
        note = "Supporting reference is structurally available but P2Rank found no usable pocket."
    elif "STRONG" in support_class and pocket_ready:
        decision_class = "SUPPORTING_STRONG_STRUCTURAL_AND_POCKET_CONTEXT"
        priority = "HIGH_CONTEXT"
        note = "Supporting reference has strong structural support and usable pocket context; it may inform manual review but does not override primary."
    elif "STRONG" in support_class:
        decision_class = "SUPPORTING_STRONG_STRUCTURAL_CONTEXT_ONLY"
        priority = "MEDIUM_HIGH_CONTEXT"
        note = "Supporting reference has strong structural support but limited pocket evidence."
    elif "MODERATE" in support_class and pocket_ready:
        decision_class = "SUPPORTING_MODERATE_STRUCTURAL_AND_POCKET_CONTEXT"
        priority = "MEDIUM_CONTEXT"
        note = "Supporting reference has moderate structural support and usable pocket context."
    elif "MODERATE" in support_class:
        decision_class = "SUPPORTING_MODERATE_STRUCTURAL_CONTEXT_ONLY"
        priority = "MEDIUM_LOW_CONTEXT"
        note = "Supporting reference has moderate structural support but limited pocket evidence."
    elif "PARTIAL" in support_class or "DOMAIN" in support_class:
        decision_class = "SUPPORTING_DOMAIN_PARTIAL_CONTEXT"
        priority = "MANUAL_DOMAIN_REVIEW"
        note = "Supporting reference suggests domain-level or partial structural context; manual domain interpretation is needed."
    else:
        decision_class = "SUPPORTING_WEAK_OR_AUDIT_ONLY_CONTEXT"
        priority = "LOW_CONTEXT"
        note = "Supporting reference is retained as audit/context evidence only."

    return decision_class, priority, ";".join(flags), note

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--primary", required=True)
    ap.add_argument("--m11-audit", required=True)
    ap.add_argument("--m11-conflict", required=True)
    ap.add_argument("--visual-contract", required=True)
    ap.add_argument("--panel", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    primary = read_tsv(args.primary)
    audit = read_tsv(args.m11_audit)
    conflict = read_tsv(args.m11_conflict)
    visual = read_tsv(args.visual_contract)
    panel = read_tsv(args.panel)

    primary_by_query = {r["query"]: r for r in primary}
    conflict_by_query = {r["query"]: r for r in conflict}
    visual_by_key = {(r["query"], r["reference_layer"], r["target"], str(r["panel_order"])): r for r in visual}

    rows = []
    for a in audit:
        q = a["query"]
        p = primary_by_query.get(q, {})
        c = conflict_by_query.get(q, {})

        key = (q, a["reference_layer"], a["target"], str(a["panel_order"]))
        v = visual_by_key.get(key, {})
        av = dict(a)
        for col in ("reference_pocket_signal", "reference_pocket_interpretation", "reference_ca_only_like"):
            av[col] = v.get(col, a.get(col, ""))

        decision_class, priority, flags, note = classify_supporting(av)

        row = {
            "mode": mode,
            "query": q,
            "protein_id": p.get("protein_id", a.get("protein_id", "")),
            "original_protein_id": a.get("protein_id", ""),
            "family": a.get("family", ""),
            "primary_final_decision_class": p.get("final_decision_class", ""),
            "primary_final_priority": p.get("final_priority", ""),
            "primary_reference": p.get("primary_reference") or p.get("primary_reference_target", ""),
            "primary_reference_type": p.get("primary_reference_type") or p.get("primary_reference_layer", ""),
            "primary_qtm_score": p.get("qtm_score") or (
                p.get("pdb_qtmscore", "") if p.get("primary_reference_layer", "") == "PDB"
                else p.get("afsp_qtmscore", "") if p.get("primary_reference_layer", "") == "AFSP"
                else ""
            ),
            "primary_rmsd": p.get("rmsd", ""),
            "primary_query_conserved_fraction": p.get("query_conserved_fraction", ""),
            "primary_reference_conserved_fraction": p.get("reference_conserved_fraction", ""),
            "supporting_panel_order": a.get("panel_order", ""),
            "supporting_panel_role": a.get("panel_role", ""),
            "supporting_reference_layer": a.get("reference_layer", ""),
            "supporting_target": a.get("target", ""),
            "supporting_source_rank": a.get("source_rank", ""),
            "supporting_support_class": a.get("support_class", ""),
            "supporting_selection_reason": a.get("selection_reason", ""),
            "supporting_foldseek_prob": a.get("foldseek_prob", ""),
            "supporting_foldseek_qtmscore": a.get("foldseek_qtmscore", ""),
            "supporting_foldseek_qcov": a.get("foldseek_qcov", ""),
            "supporting_foldseek_tcov": a.get("foldseek_tcov", ""),
            "query_top1_pocket_probability": a.get("query_top1_pocket_probability", ""),
            "query_top1_pocket_score": a.get("query_top1_pocket_score", ""),
            "reference_file_exists": a.get("reference_file_exists", ""),
            "reference_file_resolution_status": a.get("reference_file_resolution_status", ""),
            "unique_reference_id": a.get("unique_reference_id", ""),
            "reference_p2rank_status": a.get("reference_p2rank_status", ""),
            "reference_zero_pocket_flag": a.get("reference_zero_pocket_flag", ""),
            "reference_pocket_signal": av.get("reference_pocket_signal", ""),
            "reference_pocket_interpretation": av.get("reference_pocket_interpretation", ""),
            "reference_ca_only_like": av.get("reference_ca_only_like", ""),
            "reference_top1_pocket_probability": a.get("reference_top1_pocket_probability", ""),
            "reference_top1_pocket_score": a.get("reference_top1_pocket_score", ""),
            "supporting_reference_resolved": a.get("supporting_reference_resolved", ""),
            "supporting_reference_pocket_ready": a.get("supporting_reference_pocket_ready", ""),
            "supporting_reference_cache_missing": a.get("supporting_reference_cache_missing", ""),
            "supporting_reference_zero_pocket": a.get("supporting_reference_zero_pocket", ""),
            "supporting_structural_context_class": c.get("supporting_context_class", ""),
            "supporting_query_level_flags": c.get("supporting_interpretation_flags", ""),
            "supporting_row_interpretation_flags": a.get("interpretation_flags", ""),
            "supporting_decision_class": decision_class,
            "supporting_priority": priority,
            "supporting_decision_flags": flags,
            "supporting_decision_note": note,
            "can_affect_manual_review": "YES" if decision_class not in {"SUPPORTING_REFERENCE_UNRESOLVED", "SUPPORTING_WEAK_OR_AUDIT_ONLY_CONTEXT"} else "LIMITED",
            "does_not_override_primary": "YES",
            "recommended_use": "Use as contextual/audit evidence if primary rank-1 evidence is ambiguous or biologically unsatisfactory.",
            "m12b_policy": "SUPPORTING_REFERENCES_AUDIT_ONLY_NO_PRIMARY_OVERRIDE",
        }

        rows.append(row)

    fields = [
        "mode","query","protein_id","original_protein_id","family",
        "primary_final_decision_class","primary_final_priority","primary_reference","primary_reference_type",
        "primary_qtm_score","primary_rmsd","primary_query_conserved_fraction","primary_reference_conserved_fraction",
        "supporting_panel_order","supporting_panel_role","supporting_reference_layer","supporting_target","supporting_source_rank",
        "supporting_support_class","supporting_selection_reason",
        "supporting_foldseek_prob","supporting_foldseek_qtmscore","supporting_foldseek_qcov","supporting_foldseek_tcov",
        "query_top1_pocket_probability","query_top1_pocket_score",
        "reference_file_exists","reference_file_resolution_status","unique_reference_id",
        "reference_p2rank_status","reference_zero_pocket_flag",
        "reference_pocket_signal","reference_pocket_interpretation","reference_ca_only_like",
        "reference_top1_pocket_probability","reference_top1_pocket_score",
        "supporting_reference_resolved","supporting_reference_pocket_ready",
        "supporting_reference_cache_missing","supporting_reference_zero_pocket",
        "supporting_structural_context_class","supporting_query_level_flags","supporting_row_interpretation_flags",
        "supporting_decision_class","supporting_priority","supporting_decision_flags","supporting_decision_note",
        "can_affect_manual_review","does_not_override_primary","recommended_use","m12b_policy",
    ]

    matrix = outdir / f"{mode}_supporting_reference_decision_matrix.tsv"
    write_tsv(matrix, rows, fields)

    class_counts = Counter(r["supporting_decision_class"] for r in rows)
    class_rows = [{"mode": mode, "supporting_decision_class": k, "n": v} for k, v in sorted(class_counts.items())]
    class_summary = outdir / f"{mode}_supporting_reference_decision_class_summary.tsv"
    write_tsv(class_summary, class_rows, ["mode","supporting_decision_class","n"])

    fam_counts = Counter((r["family"], r["supporting_decision_class"], r["supporting_priority"]) for r in rows)
    fam_rows = []
    for (fam, cls, pri), n in sorted(fam_counts.items()):
        fam_rows.append({
            "mode": mode,
            "family": fam,
            "supporting_decision_class": cls,
            "supporting_priority": pri,
            "n": n,
        })
    fam_summary = outdir / f"{mode}_supporting_reference_decision_family_summary.tsv"
    write_tsv(fam_summary, fam_rows, ["mode","family","supporting_decision_class","supporting_priority","n"])

    query_counts = Counter(r["query"] for r in rows)
    expected_4 = sum(1 for q, n in query_counts.items() if n == 4)

    qc_rows = [
        {"metric":"module","value":"M12B_supporting_reference_decision_matrix"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"primary_rows","value":str(len(primary))},
        {"metric":"m11_audit_rows","value":str(len(audit))},
        {"metric":"output_rows","value":str(len(rows))},
        {"metric":"queries_with_four_supporting_rows","value":str(expected_4)},
        {"metric":"unique_queries","value":str(len(query_counts))},
        {"metric":"class_summary_rows","value":str(len(class_rows))},
        {"metric":"family_summary_rows","value":str(len(fam_rows))},
        {"metric":"png_generated","value":"NO"},
        {"metric":"primary_override_allowed","value":"NO"},
        {"metric":"matrix_path","value":str(matrix)},
        {"metric":"class_summary_path","value":str(class_summary)},
        {"metric":"family_summary_path","value":str(fam_summary)},
    ]
    for cls, n in sorted(class_counts.items()):
        qc_rows.append({"metric":f"class_count_{cls}","value":str(n)})

    qc = outdir / f"{mode}_supporting_reference_decision_matrix_qc.tsv"
    write_tsv(qc, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"supporting_reference_decision_matrix","path":str(matrix),"role":"M12B supporting/rank-2-to-rank-5 decision matrix; four rows per protein"},
        {"artifact_key":"supporting_reference_decision_class_summary","path":str(class_summary),"role":"M12B supporting decision class summary"},
        {"artifact_key":"supporting_reference_decision_family_summary","path":str(fam_summary),"role":"M12B family-level supporting decision summary"},
        {"artifact_key":"supporting_reference_decision_matrix_qc","path":str(qc),"role":"M12B QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m12b_supporting_reference_decision_matrix_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M12B_SUPPORTING_REFERENCE_DECISION_MATRIX_OK")
    print("matrix", matrix)
    print("rows", len(rows))
    print("class_summary", class_summary)
    print("family_summary", fam_summary)
    print("qc", qc)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
