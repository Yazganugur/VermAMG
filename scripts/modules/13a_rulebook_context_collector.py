#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from collections import defaultdict, Counter

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

def yesno(v):
    return "YES" if str(v).upper() == "YES" else "NO"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--m12a", required=True)
    ap.add_argument("--m12b", required=True)
    ap.add_argument("--m12c", required=True)
    ap.add_argument("--family-coverage", required=True)
    ap.add_argument("--known-rules", required=True)
    ap.add_argument("--ligand-classes", required=True)
    ap.add_argument("--case-definitions", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    m12a = read_tsv(args.m12a)
    m12b = read_tsv(args.m12b)
    m12c = read_tsv(args.m12c)
    famcov = read_tsv(args.family_coverage)
    known = read_tsv(args.known_rules)
    ligcls = read_tsv(args.ligand_classes)
    cases = read_tsv(args.case_definitions)

    m12b_by_pid = defaultdict(list)
    for r in m12b:
        m12b_by_pid[r["protein_id"]].append(r)

    m12c_by_pid = {r["protein_id"]: r for r in m12c}
    famcov_by_family = {r["family"]: r for r in famcov}

    known_by_family = defaultdict(list)
    for r in known:
        known_by_family[r["family"]].append(r)

    known_rule_families = set(known_by_family.keys())
    old_rule_families = set(famcov_by_family.keys())

    ligand_class_count = Counter(r.get("biological_class", "") for r in ligcls)
    case_final_class_count = Counter(r.get("final_class", "") for r in cases)

    rows = []
    for p in m12a:
        pid = p["protein_id"]
        family = p["family"]
        q = p.get("query", "")
        supp = m12b_by_pid.get(pid, [])
        c = m12c_by_pid.get(pid, {})
        fc = famcov_by_family.get(family, {})
        krules = known_by_family.get(family, [])

        if family in known_rule_families:
            rulebook_family_status = "EXISTING_KNOWN_RESIDUE_RULE"
        elif family in old_rule_families:
            rulebook_family_status = "EXISTING_CASE_RULE_ONLY_NO_KNOWN_RESIDUE_RULE"
        else:
            rulebook_family_status = "NO_EXISTING_FAMILY_RULE"

        supporting_resolved_n = sum(r.get("supporting_reference_resolved") == "YES" for r in supp)
        supporting_pocket_ready_n = sum(r.get("supporting_reference_pocket_ready") == "YES" for r in supp)
        supporting_cache_missing_n = sum(r.get("supporting_reference_cache_missing") == "YES" for r in supp)
        supporting_pdb_n = sum(r.get("supporting_reference_layer") == "PDB" for r in supp)
        supporting_afsp_n = sum(r.get("supporting_reference_layer") == "AFSP" for r in supp)
        supporting_high_context_n = sum(r.get("supporting_priority") == "HIGH_CONTEXT" for r in supp)
        supporting_unresolved_n = sum(r.get("supporting_decision_class") == "SUPPORTING_REFERENCE_UNRESOLVED" for r in supp)

        # M13 preliminary routing. This does NOT classify final evidence.
        flags = []
        if rulebook_family_status == "NO_EXISTING_FAMILY_RULE":
            flags.append("NO_EXISTING_FAMILY_RULE")
        if rulebook_family_status == "EXISTING_CASE_RULE_ONLY_NO_KNOWN_RESIDUE_RULE":
            flags.append("NO_KNOWN_RESIDUE_RULE_FOR_FAMILY")
        if (p.get("primary_reference_type") or p.get("primary_reference_layer", "")) == "AFSP":
            flags.append("AFSP_PRIMARY_NO_DIRECT_PDB_LIGAND_CONTEXT")
        if supporting_high_context_n > 0:
            flags.append("SUPPORTING_HIGH_CONTEXT_AVAILABLE")
        if supporting_cache_missing_n > 0:
            flags.append("SUPPORTING_CACHE_MISSING_PRESENT")
        if supporting_pdb_n > 0 and supporting_afsp_n > 0:
            flags.append("PDB_AND_AFSP_SUPPORTING_CONTEXT")
        if p.get("final_decision_class") in {"DOMAIN_PARTIAL_REANALYZE", "SPECIAL_CASE_MANUAL"}:
            flags.append("DOMAIN_OR_SPECIAL_CASE_REVIEW")
        if p.get("final_decision_class") == "WEAK_OR_NEGATIVE_POCKET_SUPPORT":
            flags.append("WEAK_PRIMARY_REQUIRES_CAUTION")

        if not flags:
            flags.append("READY_FOR_EXISTING_RULEBOOK_EVALUATION")

        if "NO_EXISTING_FAMILY_RULE" in flags:
            preliminary_route = "M13C_UNMATCHED_FAMILY"
        elif "DOMAIN_OR_SPECIAL_CASE_REVIEW" in flags:
            preliminary_route = "M13C_MISMATCH_OR_MANUAL_REVIEW"
        elif rulebook_family_status == "EXISTING_KNOWN_RESIDUE_RULE":
            preliminary_route = "M13B_EXISTING_KNOWN_RESIDUE_RULE"
        else:
            preliminary_route = "M13B_EXISTING_CASE_RULE_CHECK"

        row = {
            "mode": mode,
            "protein_id": pid,
            "query": q,
            "family": family,
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
            "combined_structural_recommendation": c.get("combined_structural_recommendation", ""),
            "supporting_reference_n": str(len(supp)),
            "supporting_resolved_n": str(supporting_resolved_n),
            "supporting_pocket_ready_n": str(supporting_pocket_ready_n),
            "supporting_cache_missing_n": str(supporting_cache_missing_n),
            "supporting_unresolved_n": str(supporting_unresolved_n),
            "supporting_pdb_n": str(supporting_pdb_n),
            "supporting_afsp_n": str(supporting_afsp_n),
            "supporting_high_context_n": str(supporting_high_context_n),
            "best_supporting_target": c.get("best_supporting_target", ""),
            "best_supporting_reference_layer": c.get("best_supporting_reference_layer", ""),
            "best_supporting_decision_class": c.get("best_supporting_decision_class", ""),
            "rulebook_family_status": rulebook_family_status,
            "old_section8_candidate_n_for_family": fc.get("old_section8_candidate_n", "0"),
            "known_residue_rule_n_for_family": str(len(krules)),
            "known_residue_rule_ids": ";".join(r.get("rule_id","") for r in krules),
            "known_residue_expected_query_classification": ";".join(r.get("expected_query_classification","") for r in krules),
            "known_residue_expected_reference_classification": ";".join(r.get("expected_reference_classification","") for r in krules),
            "known_residue_refined_class": ";".join(r.get("refined_class","") for r in krules),
            "m13_preliminary_route": preliminary_route,
            "m13_context_flags": ";".join(flags),
            "one_plus_four_policy": "PRIMARY_RULEBOOK_PLUS_SUPPORTING_CONTEXT_NO_OVERRIDE",
            "m13_context_note": "Context collector only; no final ligand/cofactor/motif classification is assigned here.",
        }
        rows.append(row)

    fields = [
        "mode","protein_id","query","family",
        "primary_final_decision_class","primary_final_priority","primary_reference","primary_reference_type",
        "primary_qtm_score","primary_rmsd","primary_query_conserved_fraction","primary_reference_conserved_fraction",
        "combined_structural_recommendation",
        "supporting_reference_n","supporting_resolved_n","supporting_pocket_ready_n","supporting_cache_missing_n",
        "supporting_unresolved_n","supporting_pdb_n","supporting_afsp_n","supporting_high_context_n",
        "best_supporting_target","best_supporting_reference_layer","best_supporting_decision_class",
        "rulebook_family_status","old_section8_candidate_n_for_family","known_residue_rule_n_for_family",
        "known_residue_rule_ids","known_residue_expected_query_classification","known_residue_expected_reference_classification",
        "known_residue_refined_class",
        "m13_preliminary_route","m13_context_flags","one_plus_four_policy","m13_context_note",
    ]

    context = outdir / f"{mode}_rulebook_context_collector.tsv"
    write_tsv(context, rows, fields)

    fam_counts = Counter((r["family"], r["rulebook_family_status"], r["m13_preliminary_route"]) for r in rows)
    fam_rows = []
    for (fam, status, route), n in sorted(fam_counts.items()):
        fam_rows.append({
            "mode": mode,
            "family": fam,
            "rulebook_family_status": status,
            "m13_preliminary_route": route,
            "n": n,
        })
    fam_summary = outdir / f"{mode}_rulebook_context_family_summary.tsv"
    write_tsv(fam_summary, fam_rows, ["mode","family","rulebook_family_status","m13_preliminary_route","n"])

    route_counts = Counter(r["m13_preliminary_route"] for r in rows)
    status_counts = Counter(r["rulebook_family_status"] for r in rows)
    cov_rows = []
    for k, v in sorted(route_counts.items()):
        cov_rows.append({"summary_type":"m13_preliminary_route", "class":k, "n":v})
    for k, v in sorted(status_counts.items()):
        cov_rows.append({"summary_type":"rulebook_family_status", "class":k, "n":v})
    cov_summary = outdir / f"{mode}_rulebook_context_coverage_summary.tsv"
    write_tsv(cov_summary, cov_rows, ["summary_type","class","n"])

    qc_rows = [
        {"metric":"module","value":"M13A_rulebook_context_collector"},
        {"metric":"status","value":"OK"},
        {"metric":"mode","value":mode},
        {"metric":"m12a_primary_rows","value":str(len(m12a))},
        {"metric":"m12b_supporting_rows","value":str(len(m12b))},
        {"metric":"m12c_combined_rows","value":str(len(m12c))},
        {"metric":"context_rows","value":str(len(rows))},
        {"metric":"families_in_context","value":str(len(set(r["family"] for r in rows)))},
        {"metric":"known_residue_rule_rows","value":str(len(known))},
        {"metric":"ligand_class_rows","value":str(len(ligcls))},
        {"metric":"case_definition_rows","value":str(len(cases))},
        {"metric":"one_plus_four_policy","value":"PRIMARY_RULEBOOK_PLUS_SUPPORTING_CONTEXT_NO_OVERRIDE"},
        {"metric":"context_path","value":str(context)},
        {"metric":"family_summary_path","value":str(fam_summary)},
        {"metric":"coverage_summary_path","value":str(cov_summary)},
    ]
    for k, v in sorted(route_counts.items()):
        qc_rows.append({"metric":f"route_count_{k}", "value":str(v)})
    for k, v in sorted(status_counts.items()):
        qc_rows.append({"metric":f"family_status_count_{k}", "value":str(v)})

    qc = outdir / f"{mode}_rulebook_context_collector_qc.tsv"
    write_tsv(qc, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"rulebook_context_collector","path":str(context),"role":"M13A context collector for rulebook classification"},
        {"artifact_key":"rulebook_context_family_summary","path":str(fam_summary),"role":"M13A family-level context summary"},
        {"artifact_key":"rulebook_context_coverage_summary","path":str(cov_summary),"role":"M13A rulebook coverage/route summary"},
        {"artifact_key":"rulebook_context_collector_qc","path":str(qc),"role":"M13A QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m13a_rulebook_context_collector_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M13A_RULEBOOK_CONTEXT_COLLECTOR_OK")
    print("context", context)
    print("rows", len(rows))
    print("family_summary", fam_summary)
    print("coverage_summary", cov_summary)
    print("qc", qc)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
