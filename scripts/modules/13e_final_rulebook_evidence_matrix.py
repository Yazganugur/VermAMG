#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from collections import Counter, defaultdict

def read_tsv(path):
    with Path(path).open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))

def write_tsv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

def join_unique(vals):
    out, seen = [], set()
    for v in vals:
        if v and v not in seen:
            out.append(v)
            seen.add(v)
    return ";".join(out)

def calibrated_recommendation(final_class):
    positive_classes = {
        "QUERY_SUPPORTED_PLUS_CATALYTIC_RESIDUE_CONSERVED",
        "PDB_LIGAND_SUPPORTED_STRUCTURAL_POCKET",
        "PDB_COFACTOR_METAL_SUPPORTED_STRUCTURAL_POCKET",
        "PDB_PLP_SUPPORTED_STRUCTURAL_POCKET",
        "STRONG_STRUCTURAL_POCKET_SUPPORT_NO_CURATED_RESIDUE",
    }
    if final_class in positive_classes:
        return "ADVANCE_WITH_RULEBOOK_CLASS"
    return "REVIEW_WITH_CALIBRATED_RULE"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--m13b", required=True)
    ap.add_argument("--m13c-mismatch", required=True)
    ap.add_argument("--m13c-suggest", required=True)
    ap.add_argument("--m13c-notes", required=True)
    ap.add_argument("--m13d-primary", required=True)
    ap.add_argument("--m13d-support", required=True)
    ap.add_argument("--m12c", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)

    m13b = read_tsv(args.m13b)
    mismatch = read_tsv(args.m13c_mismatch)
    suggest = read_tsv(args.m13c_suggest)
    notes = read_tsv(args.m13c_notes)
    dprim = read_tsv(args.m13d_primary)
    dsupp = read_tsv(args.m13d_support)
    m12c = read_tsv(args.m12c)

    mismatch_by_pid = {r["protein_id"]: r for r in mismatch}
    suggest_by_pid = {r["protein_id"]: r for r in suggest}
    notes_by_pid = {r["protein_id"]: r for r in notes}
    dprim_by_pid = {r["protein_id"]: r for r in dprim}
    m12c_by_pid = {r["protein_id"]: r for r in m12c}

    dsupp_by_pid = defaultdict(list)
    for r in dsupp:
        dsupp_by_pid[r["protein_id"]].append(r)

    final_rows = []

    for r in m13b:
        pid = r["protein_id"]
        mm = mismatch_by_pid.get(pid, {})
        sg = suggest_by_pid.get(pid, {})
        nt = notes_by_pid.get(pid, {})
        dp = dprim_by_pid.get(pid, {})
        dc = m12c_by_pid.get(pid, {})
        supp = dsupp_by_pid.get(pid, [])

        m13b_status = r.get("m13b_classification_status", "")
        m13b_class = r.get("m13b_existing_rulebook_class", "")
        has_true_mismatch = "YES" if pid in mismatch_by_pid else "NO"
        is_calibrated_case_rule = m13b_status == "CLASSIFIED_EXISTING_CASE_RULE_CALIBRATED"

        primary_lig_class = dp.get("ligand_context_class", "")
        primary_positive = dp.get("positive_biological_ligands", "")
        primary_biometal = dp.get("biological_metal_or_cluster_ligands", "")
        primary_manual = dp.get("manual_context_ligands", "")
        primary_all = dp.get("all_ligand_codes", "")

        supp_positive_rows = [x for x in supp if x.get("ligand_context_class") == "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT"]
        supp_manual_rows = [x for x in supp if x.get("ligand_context_class") == "MANUAL_CONTEXT_LIGAND_PRESENT_NO_AUTOMATIC_SUPPORT"]

        supporting_positive_n = len(supp_positive_rows)
        supporting_positive_targets = join_unique(x.get("target", "") for x in supp_positive_rows)
        supporting_positive_ligands = join_unique(x.get("positive_biological_ligands", "") for x in supp_positive_rows)
        supporting_biometal_ligands = join_unique(x.get("biological_metal_or_cluster_ligands", "") for x in supp_positive_rows)
        supporting_manual_ligands = join_unique(x.get("manual_context_ligands", "") for x in supp_manual_rows + supp_positive_rows)

        if is_calibrated_case_rule:
            final_class = m13b_class
            final_priority = r.get("m13b_priority", "") or "CALIBRATED"
            final_basis = "M13B_SECTION8_CALIBRATED_CASE_RULE"
            final_note = r.get("m13b_reason", "") or "Existing Section 8 calibrated case-rule class transferred for reproduction."
            if has_true_mismatch == "YES":
                mismatch_note = mm.get("mismatch_reasons", "") or mm.get("new_rule_suggestion", "")
                if mismatch_note:
                    final_note = final_note + " | M13C note retained: " + mismatch_note
        elif has_true_mismatch == "YES":
            final_class = "REVIEW_OR_NEW_RULE_NEEDED"
            final_priority = "REVIEW"
            final_basis = "M13C_TRUE_MISMATCH_OR_SPECIAL_CASE"
            final_note = mm.get("new_rule_suggestion", "") or mm.get("mismatch_reasons", "")
        elif m13b_status.startswith("CLASSIFIED"):
            final_class = m13b_class
            final_priority = r.get("m13b_priority", "") or "CLASSIFIED"
            final_basis = "M13B_EXISTING_RULEBOOK"
            final_note = r.get("m13b_reason", "")
        else:
            final_class = "UNCLASSIFIED_REVIEW"
            final_priority = "REVIEW"
            final_basis = "UNCLASSIFIED_NO_FORCED_RULE"
            final_note = r.get("m13b_reason", "")

        if primary_lig_class == "BIOLOGICAL_LIGAND_OR_COFACTOR_PRESENT":
            ligand_evidence_tier = "PRIMARY_BIOLOGICAL_LIGAND_OR_COFACTOR_CONTEXT"
        elif supporting_positive_n > 0:
            ligand_evidence_tier = "SUPPORTING_BIOLOGICAL_LIGAND_OR_COFACTOR_CONTEXT_ONLY"
        elif primary_lig_class == "MANUAL_CONTEXT_LIGAND_PRESENT_NO_AUTOMATIC_SUPPORT":
            ligand_evidence_tier = "PRIMARY_MANUAL_CONTEXT_NO_AUTOMATIC_SUPPORT"
        elif primary_lig_class in {"WATER_ONLY_OR_APO_LIKE", "NO_HETATM_APO_OR_CLEAN_PDB"}:
            ligand_evidence_tier = "PRIMARY_APO_OR_WATER_ONLY_CONTEXT"
        elif primary_lig_class == "AFSP_NO_CRYSTAL_LIGAND_CONTEXT":
            ligand_evidence_tier = "PRIMARY_AFSP_NO_CRYSTAL_LIGAND_CONTEXT"
        elif primary_lig_class == "REFERENCE_FILE_MISSING":
            ligand_evidence_tier = "PRIMARY_REFERENCE_FILE_MISSING"
        else:
            ligand_evidence_tier = "LIGAND_CONTEXT_REVIEW"

        if is_calibrated_case_rule:
            final_recommendation = calibrated_recommendation(final_class)
        elif final_class == "REVIEW_OR_NEW_RULE_NEEDED":
            final_recommendation = "MANUAL_REVIEW_BEFORE_FINAL_INTERPRETATION"
        elif ligand_evidence_tier == "PRIMARY_BIOLOGICAL_LIGAND_OR_COFACTOR_CONTEXT":
            final_recommendation = "ADVANCE_WITH_PRIMARY_RULEBOOK_AND_LIGAND_CONTEXT"
        elif ligand_evidence_tier == "SUPPORTING_BIOLOGICAL_LIGAND_OR_COFACTOR_CONTEXT_ONLY":
            final_recommendation = "ADVANCE_WITH_SUPPORTING_CONTEXT_NOTE"
        elif final_class and final_class != "UNCLASSIFIED_REVIEW":
            final_recommendation = "ADVANCE_WITH_RULEBOOK_CLASS"
        else:
            final_recommendation = "REVIEW"

        final_rows.append({
            "mode": mode,
            "protein_id": pid,
            "query": r.get("query", ""),
            "family": r.get("family", ""),
            "m12_combined_structural_recommendation": dc.get("combined_structural_recommendation", ""),
            "m13b_classification_status": m13b_status,
            "m13b_existing_rulebook_class": m13b_class,
            "m13c_true_mismatch_flag": has_true_mismatch,
            "m13c_primary_mismatch_class": mm.get("primary_mismatch_class", ""),
            "m13c_suggested_action": mm.get("suggested_action", ""),
            "m13c_new_rule_suggestion": sg.get("new_rule_suggestion", mm.get("new_rule_suggestion", "")),
            "primary_ligand_context_class": primary_lig_class,
            "primary_positive_biological_ligands": primary_positive,
            "primary_biological_metal_or_cluster_ligands": primary_biometal,
            "primary_manual_context_ligands": primary_manual,
            "primary_all_ligand_codes": primary_all,
            "supporting_biological_context_n": str(supporting_positive_n),
            "supporting_biological_context_targets": supporting_positive_targets,
            "supporting_positive_biological_ligands": supporting_positive_ligands,
            "supporting_biological_metal_or_cluster_ligands": supporting_biometal_ligands,
            "supporting_manual_context_ligands": supporting_manual_ligands,
            "m13c_supporting_context_classes": nt.get("supporting_context_classes", ""),
            "ligand_evidence_tier": ligand_evidence_tier,
            "final_rulebook_evidence_class": final_class,
            "final_rulebook_priority": final_priority,
            "final_rulebook_basis": final_basis,
            "final_rulebook_recommendation": final_recommendation,
            "final_rulebook_note": final_note,
            "does_ligand_context_override_primary_or_m13b": "NO",
            "m13e_policy": "FINAL_MATRIX_FROM_M13B_M13C_M13D__SUPPORTING_CONTEXT_NO_OVERRIDE",
        })

    fields = [
        "mode","protein_id","query","family",
        "m12_combined_structural_recommendation",
        "m13b_classification_status","m13b_existing_rulebook_class",
        "m13c_true_mismatch_flag","m13c_primary_mismatch_class","m13c_suggested_action","m13c_new_rule_suggestion",
        "primary_ligand_context_class","primary_positive_biological_ligands",
        "primary_biological_metal_or_cluster_ligands","primary_manual_context_ligands","primary_all_ligand_codes",
        "supporting_biological_context_n","supporting_biological_context_targets",
        "supporting_positive_biological_ligands","supporting_biological_metal_or_cluster_ligands",
        "supporting_manual_context_ligands","m13c_supporting_context_classes",
        "ligand_evidence_tier",
        "final_rulebook_evidence_class","final_rulebook_priority","final_rulebook_basis",
        "final_rulebook_recommendation","final_rulebook_note",
        "does_ligand_context_override_primary_or_m13b","m13e_policy",
    ]

    final_path = outdir / f"{mode}_final_rulebook_evidence_matrix.tsv"
    write_tsv(final_path, final_rows, fields)

    compact_fields = [
        "protein_id","family","final_rulebook_evidence_class","ligand_evidence_tier",
        "primary_ligand_context_class","primary_positive_biological_ligands",
        "supporting_biological_context_n","supporting_positive_biological_ligands",
        "m13c_true_mismatch_flag","m13c_primary_mismatch_class",
        "final_rulebook_recommendation"
    ]
    compact_path = outdir / f"{mode}_final_rulebook_evidence_compact.tsv"
    write_tsv(compact_path, final_rows, compact_fields)

    class_counts = Counter((r["final_rulebook_evidence_class"], r["ligand_evidence_tier"], r["final_rulebook_recommendation"]) for r in final_rows)
    class_rows = [
        {"final_rulebook_evidence_class": a, "ligand_evidence_tier": b, "final_rulebook_recommendation": c, "n": n}
        for (a,b,c), n in sorted(class_counts.items())
    ]
    class_path = outdir / f"{mode}_final_rulebook_evidence_class_summary.tsv"
    write_tsv(class_path, class_rows, ["final_rulebook_evidence_class","ligand_evidence_tier","final_rulebook_recommendation","n"])

    fam_counts = Counter((r["family"], r["final_rulebook_evidence_class"], r["ligand_evidence_tier"]) for r in final_rows)
    fam_rows = [
        {"family": a, "final_rulebook_evidence_class": b, "ligand_evidence_tier": c, "n": n}
        for (a,b,c), n in sorted(fam_counts.items())
    ]
    fam_path = outdir / f"{mode}_final_rulebook_evidence_family_summary.tsv"
    write_tsv(fam_path, fam_rows, ["family","final_rulebook_evidence_class","ligand_evidence_tier","n"])

    override_n = sum(r["does_ligand_context_override_primary_or_m13b"] != "NO" for r in final_rows)
    mismatch_n = sum(r["m13c_true_mismatch_flag"] == "YES" for r in final_rows)

    qc_rows = [
        {"metric":"module","value":"M13E_final_rulebook_evidence_matrix"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"final_rows","value":str(len(final_rows))},
        {"metric":"m13c_true_mismatch_rows","value":str(mismatch_n)},
        {"metric":"primary_biological_context_rows","value":str(sum(r["ligand_evidence_tier"]=="PRIMARY_BIOLOGICAL_LIGAND_OR_COFACTOR_CONTEXT" for r in final_rows))},
        {"metric":"supporting_biological_context_only_rows","value":str(sum(r["ligand_evidence_tier"]=="SUPPORTING_BIOLOGICAL_LIGAND_OR_COFACTOR_CONTEXT_ONLY" for r in final_rows))},
        {"metric":"override_count","value":str(override_n)},
        {"metric":"final_path","value":str(final_path)},
        {"metric":"compact_path","value":str(compact_path)},
        {"metric":"class_summary_path","value":str(class_path)},
        {"metric":"family_summary_path","value":str(fam_path)},
    ]
    qc_path = outdir / f"{mode}_final_rulebook_evidence_matrix_qc.tsv"
    write_tsv(qc_path, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"final_rulebook_evidence_matrix","path":str(final_path),"role":"M13E final one-row-per-protein rulebook evidence matrix"},
        {"artifact_key":"final_rulebook_evidence_compact","path":str(compact_path),"role":"M13E compact final view"},
        {"artifact_key":"final_rulebook_evidence_class_summary","path":str(class_path),"role":"M13E class summary"},
        {"artifact_key":"final_rulebook_evidence_family_summary","path":str(fam_path),"role":"M13E family summary"},
        {"artifact_key":"final_rulebook_evidence_matrix_qc","path":str(qc_path),"role":"M13E QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m13e_final_rulebook_evidence_matrix_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M13E_FINAL_RULEBOOK_EVIDENCE_MATRIX_OK")
    print("final_rows", len(final_rows))
    print("m13c_true_mismatch_rows", mismatch_n)
    print("override_count", override_n)
    print("final", final_path)
    print("compact", compact_path)
    print("qc", qc_path)

if __name__ == "__main__":
    main()
