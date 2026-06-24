#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from collections import Counter

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

def fnum(x, default=None):
    try:
        if x is None or x == "" or x == "NA":
            return default
        return float(x)
    except Exception:
        return default

def calibrated_priority(refined_class, old):
    priority = old.get("section8_refined_priority", "")
    if priority:
        return priority

    if refined_class in {
        "QUERY_SUPPORTED_PLUS_CATALYTIC_RESIDUE_CONSERVED",
        "PDB_LIGAND_SUPPORTED_STRUCTURAL_POCKET",
        "PDB_COFACTOR_METAL_SUPPORTED_STRUCTURAL_POCKET",
        "PDB_PLP_SUPPORTED_STRUCTURAL_POCKET",
        "STRONG_STRUCTURAL_POCKET_SUPPORT_NO_CURATED_RESIDUE",
    }:
        return "HIGH"
    if refined_class in {
        "DOMAIN_PARTIAL_REANALYZE",
        "SPECIAL_CASE_NO_QUERY_POCKET_REFERENCE_ONLY",
        "MODERATE_REVIEW_NO_LIGAND_CONTACT",
    }:
        return "REVIEW"
    if refined_class in {
        "WEAK_OR_NEGATIVE_POCKET_SUPPORT",
        "NONBIOLOGICAL_HETATM_NO_UPGRADE",
    }:
        return "LOW_CONTEXT"
    return "REVIEW"

def build_old_auto_lookup(mode, old_auto):
    bridge_rows = []
    if mode != "regression":
        return {}, bridge_rows

    old_by_pid = {r["protein_id"]: r for r in old_auto}
    lookup = dict(old_by_pid)

    bridge_path = Path("09_regression_pilot32/new_run_comparison/colabfold_model_content/regression_colabfold_old_vs_new_pdb_content_qc.tsv")
    if bridge_path.is_file():
        bridge_rows = read_tsv(bridge_path)
        for row in bridge_rows:
            old = old_by_pid.get(row.get("old_key", ""))
            if not old:
                continue
            for key in (row.get("new_run_id", ""), row.get("protein_id", "")):
                if key:
                    lookup[key] = old

    return lookup, bridge_rows

def old_auto_for_row(row, old_lookup):
    for key in (row.get("query", ""), row.get("protein_id", "")):
        if key and key in old_lookup:
            return old_lookup[key]
    return old_lookup.get(row.get("protein_id", ""), {})

def classify_case_rule(row, old_lookup):
    """
    Existing Pilot32/B8 case-rule classifier.
    For regression, old Section 8 refined classes are used as calibration labels.
    For full mode later, this function must be generalized with family/evidence rules.
    """
    old = old_auto_for_row(row, old_lookup)

    route = row.get("m13_preliminary_route", "")
    family_status = row.get("rulebook_family_status", "")

    if route == "M13C_MISMATCH_OR_MANUAL_REVIEW":
        return {
            "m13b_classification_status": "NOT_CLASSIFIED_ROUTE_TO_M13C",
            "m13b_existing_rulebook_class": "",
            "m13b_priority": "",
            "m13b_rule_source": "M13A_ROUTE",
            "m13b_rule_id": "",
            "m13b_reason": "M13A flagged this candidate as domain/special/manual review; do not force existing rulebook class.",
            "m13b_next_route": "M13C_MISMATCH_OR_MANUAL_REVIEW",
        }

    if family_status == "EXISTING_KNOWN_RESIDUE_RULE":
        refined = row.get("known_residue_refined_class", "")
        if refined:
            return {
                "m13b_classification_status": "CLASSIFIED_EXISTING_KNOWN_RESIDUE_RULE",
                "m13b_existing_rulebook_class": refined,
                "m13b_priority": old.get("section8_refined_priority", "HIGH"),
                "m13b_rule_source": "known_residue_rules.tsv",
                "m13b_rule_id": row.get("known_residue_rule_ids", ""),
                "m13b_reason": "Existing curated known-residue rule applies to this family; supporting references are retained as context only.",
                "m13b_next_route": "M13E_FINAL_RULEBOOK_MATRIX",
            }

    if route == "M13B_EXISTING_CASE_RULE_CHECK":
        refined = old.get("section8_refined_evidence_class", "")
        priority = calibrated_priority(refined, old) if refined else ""
        source = old.get("section8_refinement_source", "")
        reason = old.get("section8_refinement_reason", "")
        if refined:
            return {
                "rulebook_family_status": "EXISTING_SECTION8_CALIBRATED_CASE_RULE",
                "m13b_classification_status": "CLASSIFIED_EXISTING_CASE_RULE_CALIBRATED",
                "m13b_existing_rulebook_class": refined,
                "m13b_priority": priority,
                "m13b_rule_source": source or "old_section8_calibrated_case_rule",
                "m13b_rule_id": old.get("rulebook_rule_id", ""),
                "m13b_reason": reason or "Existing Pilot32 Section 8 case-rule class transferred as regression calibration.",
                "m13b_next_route": "M13E_FINAL_RULEBOOK_MATRIX",
            }

        return {
            "m13b_classification_status": "NOT_CLASSIFIED_CASE_RULE_MISSING",
            "m13b_existing_rulebook_class": "",
            "m13b_priority": "",
            "m13b_rule_source": "old_section8_calibrated_case_rule",
            "m13b_rule_id": "",
            "m13b_reason": "Candidate family has existing case-rule context but no transferable calibrated refined class was found.",
            "m13b_next_route": "M13C_MISMATCH_OR_MANUAL_REVIEW",
        }

    if family_status == "NO_EXISTING_FAMILY_RULE":
        return {
            "m13b_classification_status": "NOT_CLASSIFIED_NO_EXISTING_FAMILY_RULE",
            "m13b_existing_rulebook_class": "",
            "m13b_priority": "",
            "m13b_rule_source": "none",
            "m13b_rule_id": "",
            "m13b_reason": "Family absent from existing Pilot32/Section 8 rulebook.",
            "m13b_next_route": "M13C_UNMATCHED_FAMILY",
        }

    return {
        "m13b_classification_status": "NOT_CLASSIFIED_UNRESOLVED_ROUTE",
        "m13b_existing_rulebook_class": "",
        "m13b_priority": "",
        "m13b_rule_source": "none",
        "m13b_rule_id": "",
        "m13b_reason": "Could not assign existing rulebook route.",
        "m13b_next_route": "M13C_MISMATCH_OR_MANUAL_REVIEW",
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--m12a", required=True)
    ap.add_argument("--known-rules", required=True)
    ap.add_argument("--case-definitions", required=True)
    ap.add_argument("--old-auto", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    context = read_tsv(args.context)
    old_auto = read_tsv(args.old_auto)
    known = read_tsv(args.known_rules)
    cases = read_tsv(args.case_definitions)

    old_lookup, bridge_rows = build_old_auto_lookup(mode, old_auto)

    rows = []
    for r in context:
        cls = classify_case_rule(r, old_lookup)

        old = old_auto_for_row(r, old_lookup)
        rulebook_family_status = cls.get("rulebook_family_status", r.get("rulebook_family_status", ""))

        out = {
            "mode": mode,
            "protein_id": r.get("protein_id", ""),
            "query": r.get("query", ""),
            "family": r.get("family", ""),
            "primary_final_decision_class": r.get("primary_final_decision_class", ""),
            "primary_final_priority": r.get("primary_final_priority", ""),
            "primary_reference": r.get("primary_reference", ""),
            "primary_reference_type": r.get("primary_reference_type", ""),
            "combined_structural_recommendation": r.get("combined_structural_recommendation", ""),
            "supporting_reference_n": r.get("supporting_reference_n", ""),
            "supporting_resolved_n": r.get("supporting_resolved_n", ""),
            "supporting_pocket_ready_n": r.get("supporting_pocket_ready_n", ""),
            "supporting_cache_missing_n": r.get("supporting_cache_missing_n", ""),
            "best_supporting_target": r.get("best_supporting_target", ""),
            "best_supporting_reference_layer": r.get("best_supporting_reference_layer", ""),
            "best_supporting_decision_class": r.get("best_supporting_decision_class", ""),
            "rulebook_family_status": rulebook_family_status,
            "known_residue_rule_n_for_family": r.get("known_residue_rule_n_for_family", ""),
            "known_residue_rule_ids": r.get("known_residue_rule_ids", ""),
            "m13_preliminary_route": r.get("m13_preliminary_route", ""),
            "m13_context_flags": r.get("m13_context_flags", ""),
            **cls,
            "old_section8_auto_class": old.get("section8_auto_evidence_class", ""),
            "old_section8_refined_class": old.get("section8_refined_evidence_class", ""),
            "old_section8_positive_ligands": old.get("section8_positive_ligands", ""),
            "old_section8_nonbiological_ligands": old.get("section8_nonbiological_ligands", ""),
            "old_section8_context_manual_ligands": old.get("section8_context_manual_ligands", ""),
            "one_plus_four_policy": "PRIMARY_RULEBOOK_PLUS_SUPPORTING_CONTEXT_NO_OVERRIDE",
            "m13b_note": "Existing rulebook classifier only; unmatched/mismatch cases are routed onward and not forced into old classes.",
        }
        rows.append(out)

    fields = [
        "mode","protein_id","query","family",
        "primary_final_decision_class","primary_final_priority","primary_reference","primary_reference_type",
        "combined_structural_recommendation",
        "supporting_reference_n","supporting_resolved_n","supporting_pocket_ready_n","supporting_cache_missing_n",
        "best_supporting_target","best_supporting_reference_layer","best_supporting_decision_class",
        "rulebook_family_status","known_residue_rule_n_for_family","known_residue_rule_ids",
        "m13_preliminary_route","m13_context_flags",
        "m13b_classification_status","m13b_existing_rulebook_class","m13b_priority",
        "m13b_rule_source","m13b_rule_id","m13b_reason","m13b_next_route",
        "old_section8_auto_class","old_section8_refined_class",
        "old_section8_positive_ligands","old_section8_nonbiological_ligands","old_section8_context_manual_ligands",
        "one_plus_four_policy","m13b_note",
    ]

    classified = outdir / f"{mode}_existing_rulebook_classified.tsv"
    write_tsv(classified, rows, fields)

    class_counts = Counter((r["m13b_classification_status"], r["m13b_existing_rulebook_class"], r["m13b_next_route"]) for r in rows)
    class_rows = []
    for (status, cls, route), n in sorted(class_counts.items()):
        class_rows.append({
            "mode": mode,
            "m13b_classification_status": status,
            "m13b_existing_rulebook_class": cls,
            "m13b_next_route": route,
            "n": n,
        })

    class_summary = outdir / f"{mode}_existing_rulebook_classified_summary.tsv"
    write_tsv(class_summary, class_rows, ["mode","m13b_classification_status","m13b_existing_rulebook_class","m13b_next_route","n"])

    fam_counts = Counter((r["family"], r["m13b_classification_status"], r["m13b_existing_rulebook_class"]) for r in rows)
    fam_rows = []
    for (fam, status, cls), n in sorted(fam_counts.items()):
        fam_rows.append({
            "mode": mode,
            "family": fam,
            "m13b_classification_status": status,
            "m13b_existing_rulebook_class": cls,
            "n": n,
        })

    fam_summary = outdir / f"{mode}_existing_rulebook_family_summary.tsv"
    write_tsv(fam_summary, fam_rows, ["mode","family","m13b_classification_status","m13b_existing_rulebook_class","n"])

    classified_n = sum(r["m13b_classification_status"].startswith("CLASSIFIED") for r in rows)
    routed_n = len(rows) - classified_n
    forced_n = 0

    qc_rows = [
        {"metric":"module","value":"M13B_existing_rulebook_classifier"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"context_rows","value":str(len(context))},
        {"metric":"classified_rows","value":str(classified_n)},
        {"metric":"routed_not_classified_rows","value":str(routed_n)},
        {"metric":"forced_classification_count","value":str(forced_n)},
        {"metric":"known_residue_rule_rows","value":str(len(known))},
        {"metric":"case_definition_rows","value":str(len(cases))},
        {"metric":"old_auto_rows","value":str(len(old_auto))},
        {"metric":"old_auto_bridge_rows","value":str(len(bridge_rows))},
        {"metric":"old_auto_bridge_joined_rows","value":str(sum(1 for r in rows if r["old_section8_refined_class"]))},
        {"metric":"one_plus_four_policy","value":"PRIMARY_RULEBOOK_PLUS_SUPPORTING_CONTEXT_NO_OVERRIDE"},
        {"metric":"classified_path","value":str(classified)},
        {"metric":"class_summary_path","value":str(class_summary)},
        {"metric":"family_summary_path","value":str(fam_summary)},
    ]
    qc = outdir / f"{mode}_existing_rulebook_classifier_qc.tsv"
    write_tsv(qc, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"existing_rulebook_classified","path":str(classified),"role":"M13B existing rulebook classifier output"},
        {"artifact_key":"existing_rulebook_classified_summary","path":str(class_summary),"role":"M13B classification summary"},
        {"artifact_key":"existing_rulebook_family_summary","path":str(fam_summary),"role":"M13B family-level classification summary"},
        {"artifact_key":"existing_rulebook_classifier_qc","path":str(qc),"role":"M13B QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m13b_existing_rulebook_classifier_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M13B_EXISTING_RULEBOOK_CLASSIFIER_OK")
    print("classified", classified)
    print("rows", len(rows))
    print("classified_rows", classified_n)
    print("routed_not_classified_rows", routed_n)
    print("class_summary", class_summary)
    print("family_summary", fam_summary)
    print("qc", qc)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
