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

def safe_int(x, default=0):
    try:
        if x is None or x == "" or x == "NA":
            return default
        return int(float(x))
    except Exception:
        return default

def summarize_supporting(rows):
    n = len(rows)
    class_counts = Counter(r.get("supporting_decision_class", "") for r in rows)
    layer_counts = Counter(r.get("supporting_reference_layer", "") for r in rows)

    n_high_context = sum(r.get("supporting_priority") == "HIGH_CONTEXT" for r in rows)
    n_medium_high_context = sum(r.get("supporting_priority") == "MEDIUM_HIGH_CONTEXT" for r in rows)
    n_medium_context = sum(r.get("supporting_priority") == "MEDIUM_CONTEXT" for r in rows)
    n_cache_missing = sum(r.get("supporting_reference_cache_missing") == "YES" for r in rows)
    n_resolved = sum(r.get("supporting_reference_resolved") == "YES" for r in rows)
    n_pocket_ready = sum(r.get("supporting_reference_pocket_ready") == "YES" for r in rows)
    n_zero_pocket = sum(r.get("supporting_reference_zero_pocket") == "YES" for r in rows)
    n_unreliable_ca_only = sum(
        r.get("reference_pocket_signal") == "UNRELIABLE_CA_ONLY_INPUT"
        or r.get("reference_ca_only_like") == "YES"
        for r in rows
    )
    n_strong_struct = sum("STRONG" in r.get("supporting_support_class", "") for r in rows)
    n_moderate_struct = sum("MODERATE" in r.get("supporting_support_class", "") for r in rows)
    n_unresolved = class_counts.get("SUPPORTING_REFERENCE_UNRESOLVED", 0)

    best_rows = []
    priority_rank = {
        "HIGH_CONTEXT": 1,
        "MEDIUM_HIGH_CONTEXT": 2,
        "MEDIUM_CONTEXT": 3,
        "MEDIUM_LOW_CONTEXT": 4,
        "MANUAL_DOMAIN_REVIEW": 5,
        "LOW_CONTEXT": 6,
        "AUDIT_ONLY_CACHE_MISSING": 7,
    }

    def sort_key(r):
        pri = priority_rank.get(r.get("supporting_priority", ""), 99)
        try:
            order = int(float(r.get("supporting_panel_order", "999")))
        except Exception:
            order = 999
        return (pri, order)

    if rows:
        best_rows = sorted(rows, key=sort_key)
        best = best_rows[0]
    else:
        best = {}

    # Structural support interpretation is deliberately contextual.
    if n_high_context > 0:
        supporting_summary_class = "SUPPORTING_HIGH_CONTEXT_AVAILABLE"
    elif n_medium_high_context > 0 or n_medium_context > 0:
        supporting_summary_class = "SUPPORTING_MODERATE_CONTEXT_AVAILABLE"
    elif n_resolved > 0:
        supporting_summary_class = "SUPPORTING_RESOLVED_LIMITED_CONTEXT"
    elif n_cache_missing == n and n > 0:
        supporting_summary_class = "SUPPORTING_REFERENCES_MOSTLY_UNRESOLVED"
    else:
        supporting_summary_class = "SUPPORTING_CONTEXT_LIMITED_OR_ABSENT"

    flags = []
    if n_high_context > 0:
        flags.append("HAS_HIGH_CONTEXT_SUPPORTING_REFERENCE")
    if n_pocket_ready > 0:
        flags.append("HAS_SUPPORTING_POCKET_READY_REFERENCE")
    if n_strong_struct > 0:
        flags.append("HAS_STRONG_SUPPORTING_STRUCTURAL_REFERENCE")
    if n_moderate_struct > 0:
        flags.append("HAS_MODERATE_SUPPORTING_STRUCTURAL_REFERENCE")
    if n_cache_missing > 0:
        flags.append("HAS_CACHE_MISSING_SUPPORTING_REFERENCES")
    if n_zero_pocket > 0:
        flags.append("HAS_ZERO_POCKET_SUPPORTING_REFERENCES")
    if n_unreliable_ca_only > 0:
        flags.append("HAS_UNRELIABLE_CA_ONLY_SUPPORTING_REFERENCE_POCKET_CALLS")
    if layer_counts.get("PDB", 0) > 0 and layer_counts.get("AFSP", 0) > 0:
        flags.append("HAS_PDB_AND_AFSP_SUPPORTING_CONTEXT")
    if not flags:
        flags.append("NO_MAJOR_SUPPORTING_CONTEXT_FLAG")

    return {
        "supporting_reference_n": str(n),
        "supporting_resolved_n": str(n_resolved),
        "supporting_pocket_ready_n": str(n_pocket_ready),
        "supporting_cache_missing_n": str(n_cache_missing),
        "supporting_zero_pocket_n": str(n_zero_pocket),
        "supporting_reference_pocket_unreliable_ca_only_n": str(n_unreliable_ca_only),
        "supporting_reference_pocket_interpretation_flags": ";".join(
            sorted({
                r.get("reference_pocket_interpretation", "")
                for r in rows
                if r.get("reference_pocket_interpretation", "")
            })
        ),
        "supporting_ca_only_caution": (
            "Supporting reference zero-pocket calls come from CA-only-like inputs; do not interpret as biological pocket absence."
            if n_unreliable_ca_only > 0 else ""
        ),
        "supporting_strong_struct_n": str(n_strong_struct),
        "supporting_moderate_struct_n": str(n_moderate_struct),
        "supporting_unresolved_n": str(n_unresolved),
        "supporting_pdb_n": str(layer_counts.get("PDB", 0)),
        "supporting_afsp_n": str(layer_counts.get("AFSP", 0)),
        "supporting_summary_class": supporting_summary_class,
        "supporting_summary_flags": ";".join(flags),
        "best_supporting_panel_order": best.get("supporting_panel_order", ""),
        "best_supporting_reference_layer": best.get("supporting_reference_layer", ""),
        "best_supporting_target": best.get("supporting_target", ""),
        "best_supporting_decision_class": best.get("supporting_decision_class", ""),
        "best_supporting_priority": best.get("supporting_priority", ""),
        "best_supporting_note": best.get("supporting_decision_note", ""),
    }

def combined_recommendation(primary, supp):
    primary_class = primary.get("final_decision_class", "")
    primary_priority = primary.get("final_priority", "")
    supp_class = supp.get("supporting_summary_class", "")

    if primary_class in {"STRONG_ADVANCE"}:
        return (
            "ADVANCE_WITH_PRIMARY_SUPPORT",
            "Primary decision is strong; supporting references may provide context but are not required for advancement."
        )

    if primary_class in {"QUERY_SUPPORTED_REVIEW", "MODERATE_REVIEW"}:
        if supp_class in {"SUPPORTING_HIGH_CONTEXT_AVAILABLE", "SUPPORTING_MODERATE_CONTEXT_AVAILABLE"}:
            return (
                "ADVANCE_TO_MANUAL_REVIEW_WITH_SUPPORTING_CONTEXT",
                "Primary evidence requires review, and supporting references provide useful additional structural/pocket context."
            )
        return (
            "ADVANCE_TO_MANUAL_REVIEW_PRIMARY_ONLY",
            "Primary evidence requires review; supporting context is limited or unresolved."
        )

    if primary_class in {"DOMAIN_PARTIAL_REANALYZE", "SPECIAL_CASE_MANUAL"}:
        return (
            "MANUAL_REVIEW_REQUIRED",
            "Primary decision indicates domain/special-case review; supporting references should be consulted manually."
        )

    if primary_class in {"WEAK_OR_NEGATIVE_POCKET_SUPPORT"}:
        if supp_class in {"SUPPORTING_HIGH_CONTEXT_AVAILABLE", "SUPPORTING_MODERATE_CONTEXT_AVAILABLE"}:
            return (
                "WEAK_PRIMARY_BUT_SUPPORTING_CONTEXT_AVAILABLE",
                "Primary evidence is weak, but supporting references provide context that may justify targeted manual inspection."
            )
        return (
            "LOW_PRIORITY_OR_HOLD",
            "Primary evidence is weak and supporting context does not provide sufficient rescue evidence."
        )

    if primary_class == "LITE_STRUCTURAL_SUPPORT_WITH_QUERY_POCKET_REFERENCE_UNRELIABLE":
        supp_flags = supp.get("supporting_summary_flags", "")
        if "HAS_UNRELIABLE_CA_ONLY_SUPPORTING_REFERENCE_POCKET_CALLS" in supp_flags:
            return (
                "LITE_REVIEW_QUERY_POCKET_WITH_UNRELIABLE_REFERENCE_POCKET",
                "Query pocket and structural context are present, but reference pocket evidence is unreliable because reference structures are CA-only-like; do not interpret zero pockets as biological absence.",
            )
        return (
            "LITE_REVIEW_QUERY_POCKET_PRIMARY_REFERENCE_UNRELIABLE",
            "Query pocket and structural support are computationally detected, but the primary reference structure is CA-only-like; pocket absence in primary reference should not be interpreted as biological absence.",
        )

    if primary_class == "LITE_STRUCTURAL_SUPPORT_WITH_POCKET_CONTEXT":
        struct_class = primary.get("primary_struct_support_class", "")
        if "DOMAIN_LEVEL" in struct_class or "PARTIAL" in struct_class:
            return (
                "LITE_REVIEW_DOMAIN_PARTIAL_CONTEXT",
                "Domain-level or partial structural similarity and computational pocket context are present, but this is not sufficient for advancement without manual review.",
            )
        if supp_class in {"SUPPORTING_HIGH_CONTEXT_AVAILABLE", "SUPPORTING_MODERATE_CONTEXT_AVAILABLE"}:
            return (
                "LITE_ADVANCE_WITH_SUPPORTING_CONTEXT",
                "Lite structural and pocket support computationally detected; supporting references provide additional context.",
            )
        return (
            "LITE_ADVANCE_PRIMARY_SUPPORTED",
            "Lite structural and pocket support computationally detected; supporting context is limited or unresolved.",
        )

    if primary_class == "LITE_REVIEW_NEEDED":
        if supp_class in {"SUPPORTING_HIGH_CONTEXT_AVAILABLE", "SUPPORTING_MODERATE_CONTEXT_AVAILABLE"}:
            return (
                "LITE_REVIEW_WITH_SUPPORTING_CONTEXT",
                "Lite review needed; supporting references provide context that may inform manual review.",
            )
        return (
            "LITE_REVIEW_PRIMARY_ONLY",
            "Lite review needed; supporting context is limited.",
        )

    if primary_class == "LITE_REFERENCE_POCKET_UNRELIABLE_REVIEW":
        return (
            "LITE_REVIEW_REFERENCE_POCKET_UNRELIABLE",
            "Lite review needed; reference pocket evidence is unreliable due to CA-only-like input.",
        )

    return (
        "REVIEW_UNCLASSIFIED",
        "Combined recommendation could not be assigned from current classes."
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--primary", required=True)
    ap.add_argument("--supporting", required=True)
    ap.add_argument("--m11-conflict", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    primary = read_tsv(args.primary)
    supporting = read_tsv(args.supporting)
    conflict = read_tsv(args.m11_conflict)

    supp_by_pid = defaultdict(list)
    for r in supporting:
        supp_by_pid[r["protein_id"]].append(r)

    conflict_by_query = {r["query"]: r for r in conflict}

    rows = []
    for p in primary:
        pid = p["protein_id"]
        q = p.get("query", "")
        supp_rows = supp_by_pid.get(pid, [])
        supp_summary = summarize_supporting(supp_rows)
        rec_class, rec_note = combined_recommendation(p, supp_summary)
        conflict_row = conflict_by_query.get(q, {})

        row = {
            "mode": mode,
            "protein_id": pid,
            "query": q,
            "family": p.get("family", ""),
            "habitat": p.get("habitat", ""),
            "primary_final_decision_class": p.get("final_decision_class", ""),
            "primary_final_priority": p.get("final_priority", ""),
            "primary_recommended_next_step": p.get("recommended_next_step", ""),
            "primary_decision_reason": p.get("decision_reason", ""),
            "primary_reference": p.get("primary_reference", ""),
            "primary_reference_type": p.get("primary_reference_type", ""),
            "primary_qtm_score": p.get("qtm_score", ""),
            "primary_rmsd": p.get("rmsd", ""),
            "primary_query_conserved_fraction": p.get("query_conserved_fraction", ""),
            "primary_reference_conserved_fraction": p.get("reference_conserved_fraction", ""),
            "primary_query_p2rank": p.get("query_p2rank", ""),
            "primary_reference_p2rank": p.get("reference_p2rank", ""),
            "primary_pocket_status": p.get("pocket_status", ""),
            "primary_overlay_status": p.get("overlay_status", ""),
            "primary_chainaware_reference_mode": p.get("chainaware_reference_mode", ""),
            "primary_entry_vs_chain_category": p.get("entry_vs_chain_category", ""),
            "supporting_reference_n": supp_summary["supporting_reference_n"],
            "supporting_resolved_n": supp_summary["supporting_resolved_n"],
            "supporting_pocket_ready_n": supp_summary["supporting_pocket_ready_n"],
            "supporting_cache_missing_n": supp_summary["supporting_cache_missing_n"],
            "supporting_zero_pocket_n": supp_summary["supporting_zero_pocket_n"],
            "supporting_reference_pocket_unreliable_ca_only_n": supp_summary["supporting_reference_pocket_unreliable_ca_only_n"],
            "supporting_reference_pocket_interpretation_flags": supp_summary["supporting_reference_pocket_interpretation_flags"],
            "supporting_ca_only_caution": supp_summary["supporting_ca_only_caution"],
            "supporting_strong_struct_n": supp_summary["supporting_strong_struct_n"],
            "supporting_moderate_struct_n": supp_summary["supporting_moderate_struct_n"],
            "supporting_unresolved_n": supp_summary["supporting_unresolved_n"],
            "supporting_pdb_n": supp_summary["supporting_pdb_n"],
            "supporting_afsp_n": supp_summary["supporting_afsp_n"],
            "supporting_summary_class": supp_summary["supporting_summary_class"],
            "supporting_summary_flags": supp_summary["supporting_summary_flags"],
            "best_supporting_panel_order": supp_summary["best_supporting_panel_order"],
            "best_supporting_reference_layer": supp_summary["best_supporting_reference_layer"],
            "best_supporting_target": supp_summary["best_supporting_target"],
            "best_supporting_decision_class": supp_summary["best_supporting_decision_class"],
            "best_supporting_priority": supp_summary["best_supporting_priority"],
            "best_supporting_note": supp_summary["best_supporting_note"],
            "m11_supporting_context_class": conflict_row.get("supporting_context_class", ""),
            "m11_supporting_interpretation_flags": conflict_row.get("supporting_interpretation_flags", ""),
            "combined_structural_recommendation": rec_class,
            "combined_structural_recommendation_note": rec_note,
            "primary_decision_is_overridden": "NO",
            "supporting_reference_policy": "SUPPORTING_REFERENCES_SUMMARIZED_BUT_DO_NOT_OVERRIDE_PRIMARY",
            "next_module_bridge": "M13_RULEBOOK_LIGAND_COFACTOR_MOTIF_EVIDENCE",
        }
        rows.append(row)

    fields = [
        "mode","protein_id","query","family","habitat",
        "primary_final_decision_class","primary_final_priority","primary_recommended_next_step","primary_decision_reason",
        "primary_reference","primary_reference_type","primary_qtm_score","primary_rmsd",
        "primary_query_conserved_fraction","primary_reference_conserved_fraction",
        "primary_query_p2rank","primary_reference_p2rank","primary_pocket_status","primary_overlay_status",
        "primary_chainaware_reference_mode","primary_entry_vs_chain_category",
        "supporting_reference_n","supporting_resolved_n","supporting_pocket_ready_n","supporting_cache_missing_n",
        "supporting_zero_pocket_n","supporting_strong_struct_n","supporting_moderate_struct_n","supporting_unresolved_n",
        "supporting_reference_pocket_unreliable_ca_only_n","supporting_reference_pocket_interpretation_flags","supporting_ca_only_caution",
        "supporting_pdb_n","supporting_afsp_n","supporting_summary_class","supporting_summary_flags",
        "best_supporting_panel_order","best_supporting_reference_layer","best_supporting_target",
        "best_supporting_decision_class","best_supporting_priority","best_supporting_note",
        "m11_supporting_context_class","m11_supporting_interpretation_flags",
        "combined_structural_recommendation","combined_structural_recommendation_note",
        "primary_decision_is_overridden","supporting_reference_policy","next_module_bridge",
    ]

    summary = outdir / f"{mode}_combined_decision_summary.tsv"
    write_tsv(summary, rows, fields)

    rec_counts = Counter(r["combined_structural_recommendation"] for r in rows)
    rec_rows = [{"mode": mode, "combined_structural_recommendation": k, "n": v} for k, v in sorted(rec_counts.items())]
    rec_summary = outdir / f"{mode}_combined_decision_recommendation_summary.tsv"
    write_tsv(rec_summary, rec_rows, ["mode","combined_structural_recommendation","n"])

    fam_counts = Counter((r["family"], r["primary_final_decision_class"], r["supporting_summary_class"], r["combined_structural_recommendation"]) for r in rows)
    fam_rows = []
    for (fam, pcls, scls, rec), n in sorted(fam_counts.items()):
        fam_rows.append({
            "mode": mode,
            "family": fam,
            "primary_final_decision_class": pcls,
            "supporting_summary_class": scls,
            "combined_structural_recommendation": rec,
            "n": n,
        })
    fam_summary = outdir / f"{mode}_combined_decision_family_summary.tsv"
    write_tsv(fam_summary, fam_rows, ["mode","family","primary_final_decision_class","supporting_summary_class","combined_structural_recommendation","n"])

    override_n = sum(r["primary_decision_is_overridden"] != "NO" for r in rows)
    support_n_ok = sum(safe_int(r["supporting_reference_n"]) == 4 for r in rows)

    qc_rows = [
        {"metric":"module","value":"M12C_combined_decision_summary"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"primary_rows","value":str(len(primary))},
        {"metric":"supporting_rows","value":str(len(supporting))},
        {"metric":"output_rows","value":str(len(rows))},
        {"metric":"queries_with_four_supporting_refs","value":str(support_n_ok)},
        {"metric":"supporting_reference_pocket_unreliable_ca_only_rows","value":str(sum(safe_int(r["supporting_reference_pocket_unreliable_ca_only_n"]) for r in rows))},
        {"metric":"primary_override_count","value":str(override_n)},
        {"metric":"recommendation_summary_rows","value":str(len(rec_rows))},
        {"metric":"family_summary_rows","value":str(len(fam_rows))},
        {"metric":"summary_path","value":str(summary)},
        {"metric":"recommendation_summary_path","value":str(rec_summary)},
        {"metric":"family_summary_path","value":str(fam_summary)},
    ]
    for rec, n in sorted(rec_counts.items()):
        qc_rows.append({"metric":f"recommendation_count_{rec}","value":str(n)})

    qc = outdir / f"{mode}_combined_decision_summary_qc.tsv"
    write_tsv(qc, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"combined_decision_summary","path":str(summary),"role":"M12C one-row-per-protein combined structural summary"},
        {"artifact_key":"combined_decision_recommendation_summary","path":str(rec_summary),"role":"M12C combined recommendation class summary"},
        {"artifact_key":"combined_decision_family_summary","path":str(fam_summary),"role":"M12C family-level combined structural summary"},
        {"artifact_key":"combined_decision_summary_qc","path":str(qc),"role":"M12C QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m12c_combined_decision_summary_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M12C_COMBINED_DECISION_SUMMARY_OK")
    print("summary", summary)
    print("rows", len(rows))
    print("recommendation_summary", rec_summary)
    print("family_summary", fam_summary)
    print("qc", qc)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
