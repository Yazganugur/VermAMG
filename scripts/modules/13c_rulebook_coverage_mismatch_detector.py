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

def uniq(xs):
    out, seen = [], set()
    for x in xs:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out

def build_supporting_note(row, support_rows):
    flags = row.get("m13_context_flags", "")
    notes = []
    support_classes = []

    cache_missing_n = sum(r.get("supporting_reference_cache_missing") == "YES" for r in support_rows)
    resolved_n = sum(r.get("supporting_reference_resolved") == "YES" for r in support_rows)
    pocket_ready_n = sum(r.get("supporting_reference_pocket_ready") == "YES" for r in support_rows)
    high_context_n = sum(r.get("supporting_priority") == "HIGH_CONTEXT" for r in support_rows)

    if "SUPPORTING_HIGH_CONTEXT_AVAILABLE" in flags or high_context_n > 0:
        support_classes.append("SUPPORTING_HIGH_CONTEXT_AVAILABLE")
        notes.append("Supporting reference(s) provide useful structural/pocket context; this is audit/supporting evidence only.")
    if cache_missing_n > 0:
        support_classes.append("REFERENCE_CACHE_MISSING_FOR_SUPPORTING_HIT")
        notes.append(f"{cache_missing_n} supporting reference(s) are cache-missing/unresolved; keep as Foldseek audit-only unless structures are fetched later.")
    if "PDB_AND_AFSP_SUPPORTING_CONTEXT" in flags:
        support_classes.append("PDB_AND_AFSP_SUPPORTING_CONTEXT")
        notes.append("Both PDB and AFSP layers contribute to supporting context.")
    if not support_classes:
        support_classes.append("NO_MAJOR_SUPPORTING_CONTEXT_NOTE")
        notes.append("No major supporting-reference context note.")

    return {
        "supporting_context_classes": ";".join(uniq(support_classes)),
        "supporting_context_note": " | ".join(uniq(notes)),
        "supporting_resolved_n": str(resolved_n),
        "supporting_pocket_ready_n": str(pocket_ready_n),
        "supporting_cache_missing_n": str(cache_missing_n),
        "supporting_high_context_n": str(high_context_n),
    }

def detect_true_mismatch(row, support_rows):
    flags = row.get("m13_context_flags", "")
    primary_class = row.get("primary_final_decision_class", "")
    primary_ref_type = row.get("primary_reference_type", "")
    family_status = row.get("rulebook_family_status", "")
    m13b_status = row.get("m13b_classification_status", "")

    mismatch_classes = []
    reasons = []
    suggestions = []

    if family_status == "NO_EXISTING_FAMILY_RULE":
        mismatch_classes.append("NO_EXISTING_FAMILY_RULE")
        reasons.append("Family is absent from the existing Section 8 rulebook.")
        suggestions.append("Create a new family-specific rule after checking structural, ligand/cofactor, motif and literature context.")

    if m13b_status.startswith("NOT_CLASSIFIED"):
        mismatch_classes.append("FAMILY_RULE_EXISTS_BUT_REQUIRED_EVIDENCE_MISSING")
        reasons.append("Candidate was not classified by M13B; existing rulebook should not be forced.")
        suggestions.append("Inspect whether a family-specific, domain-aware, no-query-pocket, or special-case rule is needed.")

    if "DOMAIN_OR_SPECIAL_CASE_REVIEW" in flags or primary_class in {"DOMAIN_PARTIAL_REANALYZE", "SPECIAL_CASE_MANUAL"}:
        mismatch_classes.append("POTENTIAL_NEW_DOMAIN_PARTIAL_RULE")
        reasons.append("Primary structural layer indicates domain-partial or special-case manual review.")
        suggestions.append("Use domain-aware rule logic; do not interpret full-protein pocket conservation as a simple negative.")

    if primary_ref_type == "AFSP" and m13b_status.startswith("NOT_CLASSIFIED"):
        mismatch_classes.append("AFSP_ONLY_NO_PDB_LIGAND_CONTEXT")
        reasons.append("Primary reference is AFSP/predicted in a case that already requires manual/mismatch review.")
        suggestions.append("Use structural/pocket evidence cautiously; evaluate supporting PDB references for biochemical context.")

    if primary_class == "WEAK_OR_NEGATIVE_POCKET_SUPPORT" and m13b_status.startswith("NOT_CLASSIFIED"):
        mismatch_classes.append("LOW_EVIDENCE_REVIEW_ONLY")
        reasons.append("Primary structural evidence is weak/negative and existing rulebook did not classify the case.")
        suggestions.append("Keep as review/low priority unless supporting biochemical evidence justifies targeted inspection.")

    mismatch_classes = uniq(mismatch_classes)
    reasons = uniq(reasons)
    suggestions = uniq(suggestions)

    if not mismatch_classes:
        return None

    if "NO_EXISTING_FAMILY_RULE" in mismatch_classes:
        primary_mismatch_class = "NO_EXISTING_FAMILY_RULE"
        action = "NEW_FAMILY_RULE_NEEDED"
    elif "POTENTIAL_NEW_DOMAIN_PARTIAL_RULE" in mismatch_classes:
        primary_mismatch_class = "POTENTIAL_NEW_DOMAIN_PARTIAL_RULE"
        action = "DOMAIN_AWARE_RULE_OR_MANUAL_REVIEW_NEEDED"
    elif "AFSP_ONLY_NO_PDB_LIGAND_CONTEXT" in mismatch_classes:
        primary_mismatch_class = "AFSP_ONLY_NO_PDB_LIGAND_CONTEXT"
        action = "CHECK_SUPPORTING_PDB_OR_KEEP_REVIEW"
    elif "LOW_EVIDENCE_REVIEW_ONLY" in mismatch_classes:
        primary_mismatch_class = "LOW_EVIDENCE_REVIEW_ONLY"
        action = "KEEP_REVIEW_OR_LOW_PRIORITY"
    else:
        primary_mismatch_class = mismatch_classes[0]
        action = "MANUAL_REVIEW"

    return {
        "primary_mismatch_class": primary_mismatch_class,
        "all_mismatch_classes": ";".join(mismatch_classes),
        "mismatch_reasons": " | ".join(reasons),
        "suggested_action": action,
        "new_rule_suggestion": " | ".join(suggestions),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--classified", required=True)
    ap.add_argument("--supporting", required=True)
    ap.add_argument("--combined", required=True)
    ap.add_argument("--mismatch-taxonomy", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    context = read_tsv(args.context)
    classified = read_tsv(args.classified)
    supporting = read_tsv(args.supporting)
    combined = read_tsv(args.combined)
    taxonomy = read_tsv(args.mismatch_taxonomy)

    class_by_pid = {r["protein_id"]: r for r in classified}
    combined_by_pid = {r["protein_id"]: r for r in combined}
    support_by_pid = defaultdict(list)
    for r in supporting:
        support_by_pid[r["protein_id"]].append(r)

    unmatched_rows = []
    mismatch_rows = []
    suggestion_rows = []
    support_note_rows = []

    for ctx in context:
        pid = ctx["protein_id"]
        cl = class_by_pid.get(pid, {})
        comb = combined_by_pid.get(pid, {})
        supp = support_by_pid.get(pid, [])

        merged = dict(ctx)
        merged.update({
            "m13b_classification_status": cl.get("m13b_classification_status", ""),
            "m13b_existing_rulebook_class": cl.get("m13b_existing_rulebook_class", ""),
            "m13b_next_route": cl.get("m13b_next_route", ""),
            "m13b_reason": cl.get("m13b_reason", ""),
        })

        support_note = build_supporting_note(merged, supp)
        mismatch = detect_true_mismatch(merged, supp)

        base = {
            "mode": mode,
            "protein_id": pid,
            "query": ctx.get("query", ""),
            "family": ctx.get("family", ""),
            "primary_final_decision_class": ctx.get("primary_final_decision_class", ""),
            "primary_reference": ctx.get("primary_reference", ""),
            "primary_reference_type": ctx.get("primary_reference_type", ""),
            "rulebook_family_status": ctx.get("rulebook_family_status", ""),
            "m13b_classification_status": cl.get("m13b_classification_status", ""),
            "m13b_existing_rulebook_class": cl.get("m13b_existing_rulebook_class", ""),
            "m13b_next_route": cl.get("m13b_next_route", ""),
            "supporting_reference_n": ctx.get("supporting_reference_n", ""),
            "supporting_resolved_n": support_note["supporting_resolved_n"],
            "supporting_pocket_ready_n": support_note["supporting_pocket_ready_n"],
            "supporting_cache_missing_n": support_note["supporting_cache_missing_n"],
            "supporting_high_context_n": support_note["supporting_high_context_n"],
            "best_supporting_target": ctx.get("best_supporting_target", ""),
            "best_supporting_reference_layer": ctx.get("best_supporting_reference_layer", ""),
            "m13_context_flags": ctx.get("m13_context_flags", ""),
            "does_this_override_m13b": "NO",
        }

        support_note_rows.append({
            **base,
            "supporting_context_classes": support_note["supporting_context_classes"],
            "supporting_context_note": support_note["supporting_context_note"],
            "supporting_context_policy": "SUPPORTING_CONTEXT_AUDIT_ONLY_NOT_TRUE_MISMATCH",
        })

        if mismatch is not None:
            row = {
                **base,
                **mismatch,
                "m13c_policy": "TRUE_MISMATCH_AND_NEW_RULE_SUGGESTION_ONLY_NO_FORCED_CLASSIFICATION",
            }
            mismatch_rows.append(row)

            if ctx.get("rulebook_family_status") == "NO_EXISTING_FAMILY_RULE":
                unmatched_rows.append(row)

            suggestion_rows.append({
                **row,
                "suggestion_priority": (
                    "HIGH" if mismatch["primary_mismatch_class"] in {"NO_EXISTING_FAMILY_RULE", "POTENTIAL_NEW_DOMAIN_PARTIAL_RULE"}
                    else "MEDIUM"
                )
            })

    mismatch_fields = [
        "mode","protein_id","query","family",
        "primary_final_decision_class","primary_reference","primary_reference_type",
        "rulebook_family_status","m13b_classification_status","m13b_existing_rulebook_class","m13b_next_route",
        "supporting_reference_n","supporting_resolved_n","supporting_pocket_ready_n",
        "supporting_cache_missing_n","supporting_high_context_n",
        "best_supporting_target","best_supporting_reference_layer",
        "m13_context_flags",
        "primary_mismatch_class","all_mismatch_classes","mismatch_reasons","suggested_action","new_rule_suggestion",
        "does_this_override_m13b","m13c_policy",
    ]

    supporting_fields = [
        "mode","protein_id","query","family",
        "primary_final_decision_class","primary_reference","primary_reference_type",
        "m13b_classification_status","m13b_existing_rulebook_class",
        "supporting_reference_n","supporting_resolved_n","supporting_pocket_ready_n",
        "supporting_cache_missing_n","supporting_high_context_n",
        "best_supporting_target","best_supporting_reference_layer",
        "m13_context_flags","supporting_context_classes","supporting_context_note",
        "supporting_context_policy","does_this_override_m13b",
    ]

    unmatched = outdir / f"{mode}_rulebook_unmatched_families.tsv"
    mismatch_path = outdir / f"{mode}_rulebook_mismatch_reasons.tsv"
    suggestions = outdir / f"{mode}_rulebook_new_class_suggestions.tsv"
    support_notes = outdir / f"{mode}_rulebook_supporting_context_notes.tsv"

    write_tsv(unmatched, unmatched_rows, mismatch_fields)
    write_tsv(mismatch_path, mismatch_rows, mismatch_fields)
    write_tsv(suggestions, suggestion_rows, mismatch_fields + ["suggestion_priority"])
    write_tsv(support_notes, support_note_rows, supporting_fields)

    summary_counts = Counter((r["primary_mismatch_class"], r["suggested_action"]) for r in mismatch_rows)
    summary_rows = []
    for (cls, action), n in sorted(summary_counts.items()):
        summary_rows.append({
            "mode": mode,
            "primary_mismatch_class": cls,
            "suggested_action": action,
            "n": n,
        })

    summary = outdir / f"{mode}_rulebook_coverage_mismatch_summary.tsv"
    write_tsv(summary, summary_rows, ["mode","primary_mismatch_class","suggested_action","n"])

    override_n = sum(r.get("does_this_override_m13b") != "NO" for r in mismatch_rows + support_note_rows)

    qc_rows = [
        {"metric":"module","value":"M13C_rulebook_coverage_mismatch_detector"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"context_rows","value":str(len(context))},
        {"metric":"classified_rows","value":str(len(classified))},
        {"metric":"taxonomy_rows","value":str(len(taxonomy))},
        {"metric":"unmatched_family_rows","value":str(len(unmatched_rows))},
        {"metric":"true_mismatch_rows","value":str(len(mismatch_rows))},
        {"metric":"new_rule_suggestion_rows","value":str(len(suggestion_rows))},
        {"metric":"supporting_context_note_rows","value":str(len(support_note_rows))},
        {"metric":"override_m13b_count","value":str(override_n)},
        {"metric":"unmatched_path","value":str(unmatched)},
        {"metric":"mismatch_path","value":str(mismatch_path)},
        {"metric":"suggestions_path","value":str(suggestions)},
        {"metric":"supporting_context_notes_path","value":str(support_notes)},
        {"metric":"summary_path","value":str(summary)},
        {"metric":"fix_policy","value":"SUPPORTING_CONTEXT_NOT_COUNTED_AS_TRUE_MISMATCH"},
    ]

    qc = outdir / f"{mode}_rulebook_coverage_mismatch_qc.tsv"
    write_tsv(qc, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"rulebook_unmatched_families","path":str(unmatched),"role":"M13C families absent from rulebook"},
        {"artifact_key":"rulebook_mismatch_reasons","path":str(mismatch_path),"role":"M13C true mismatch/manual-review reasons"},
        {"artifact_key":"rulebook_new_class_suggestions","path":str(suggestions),"role":"M13C true new-rule suggestions"},
        {"artifact_key":"rulebook_supporting_context_notes","path":str(support_notes),"role":"M13C supporting context notes; not counted as true mismatch"},
        {"artifact_key":"rulebook_coverage_mismatch_summary","path":str(summary),"role":"M13C true mismatch summary"},
        {"artifact_key":"rulebook_coverage_mismatch_qc","path":str(qc),"role":"M13C QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m13c_rulebook_coverage_mismatch_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M13C_TRUE_MISMATCH_DETECTOR_OK")
    print("unmatched", unmatched, "rows", len(unmatched_rows))
    print("true_mismatch", mismatch_path, "rows", len(mismatch_rows))
    print("suggestions", suggestions, "rows", len(suggestion_rows))
    print("supporting_notes", support_notes, "rows", len(support_note_rows))
    print("summary", summary)
    print("qc", qc)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
