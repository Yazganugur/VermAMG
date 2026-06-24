#!/usr/bin/env python3
# LEGACY: regression calibration only. Not for production.
# Use 12a_lite_primary_decision_matrix.py for dynamic production runs.
# Requires --old-matrix (calibration QBENCH IDs) and --m10f-metrics/--m10f-alignment
# (canonical_v6_engine_regression tables). These are not available for
# new cohort proteins. Do not call from master pipeline.
import argparse
import csv
from pathlib import Path
from collections import Counter, defaultdict

VIRAL_CONTEXT_NOTE = (
    "Candidate is encoded on a viral contig; incomplete conservation relative to bacterial/PDB/AFSP "
    "references should not be treated as failure by itself. Interpret divergence in the context of "
    "horizontal transfer, viral evolution, domain remodeling and host-context uncertainty."
)

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

def safe_float(x, default=None):
    try:
        if x is None or x == "" or x == "NA":
            return default
        return float(x)
    except Exception:
        return default

def safe_int(x, default=0):
    try:
        if x is None or x == "" or x == "NA":
            return default
        return int(float(x))
    except Exception:
        return default

def frac(n, d):
    n = safe_float(n, 0.0)
    d = safe_float(d, 0.0)
    if d == 0:
        return ""
    return str(n / d)

def compact_float(x):
    v = safe_float(x)
    if v is None:
        return ""
    return f"{v:.6g}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--old-matrix", required=True)
    ap.add_argument("--m10f-metrics", required=True)
    ap.add_argument("--m10f-alignment", required=True)
    ap.add_argument("--m08-decision", required=True)
    ap.add_argument("--pdb-rank1", required=True)
    ap.add_argument("--afsp-rank1", required=True)
    ap.add_argument("--m11-conflict", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    old_rows = read_tsv(args.old_matrix)
    m10 = read_tsv(args.m10f_metrics)
    m08 = read_tsv(args.m08_decision)
    pdb = read_tsv(args.pdb_rank1)
    afsp = read_tsv(args.afsp_rank1)
    m11 = read_tsv(args.m11_conflict)

    old_by_t1p = {r["protein_id"]: r for r in old_rows}
    m10_by_t1p = {r["protein_id"]: r for r in m10}

    # old T1P order <-> new QBENCH order bridge by row order.
    # Regression set has proven 32/32 ID match between old and M10F metrics.
    # M08/PDB/AFSP/M11 are keyed by QBENCH IDs, so row order bridge is safest for regression port.
    old_order = [r["protein_id"] for r in old_rows]
    m08_order = [r["query"] for r in m08]

    if len(old_order) != len(m08_order):
        raise SystemExit(f"ERROR: old matrix rows ({len(old_order)}) != M08 rows ({len(m08_order)})")

    t1p_to_query = dict(zip(old_order, m08_order))
    query_to_t1p = {v:k for k,v in t1p_to_query.items()}

    m08_by_query = {r["query"]: r for r in m08}
    pdb_by_query = {r["query"]: r for r in pdb}
    afsp_by_query = {r["query"]: r for r in afsp}
    m11_by_query = {r["query"]: r for r in m11}

    # alignment classification counts from canonical M10F combined table
    align_rows = read_tsv(args.m10f_alignment)
    align_counts = defaultdict(Counter)
    for r in align_rows:
        pid = r.get("protein_id", "")
        cls = r.get("classification", "")
        if pid:
            align_counts[pid][cls] += 1

    output_rows = []

    old_header = list(old_rows[0].keys())

    for old in old_rows:
        pid = old["protein_id"]
        query = t1p_to_query.get(pid, "")
        mm = m10_by_t1p.get(pid, {})
        d = m08_by_query.get(query, {})
        p = pdb_by_query.get(query, {})
        a = afsp_by_query.get(query, {})
        s = m11_by_query.get(query, {})

        q_cons = mm.get("query_conserved_n", old.get("query_conserved_n", ""))
        q_pocket = mm.get("query_pocket_n", old.get("query_pocket_n", ""))
        r_cons = mm.get("reference_conserved_n", old.get("reference_conserved_n", ""))
        r_pocket = mm.get("reference_pocket_n", old.get("reference_pocket_n", ""))

        # Preserve old calibrated decision labels in regression, but refresh structural values from M10F where available.
        row = dict(old)

        row["qtm_score"] = mm.get("qtm_score", old.get("qtm_score", ""))
        row["rmsd"] = mm.get("rmsd", old.get("rmsd", ""))
        row["query_conserved_n"] = q_cons
        row["query_pocket_n"] = q_pocket
        row["query_conserved_fraction"] = frac(q_cons, q_pocket)
        row["query_unique_n"] = mm.get("query_unique_n", old.get("query_unique_n", ""))
        row["reference_conserved_n"] = r_cons
        row["reference_pocket_n"] = r_pocket
        row["reference_conserved_fraction"] = frac(r_cons, r_pocket)
        row["reference_unique_n"] = mm.get("reference_unique_n", old.get("reference_unique_n", ""))
        row["query_p2rank"] = mm.get("query_p2rank", old.get("query_p2rank", ""))
        row["reference_p2rank"] = mm.get("reference_p2rank", old.get("reference_p2rank", ""))

        row["primary_reference_type_b6"] = mm.get("primary_reference_type", old.get("primary_reference_type_b6", ""))
        row["chainaware_reference_mode_b6"] = mm.get("chainaware_reference_mode", old.get("chainaware_reference_mode_b6", ""))
        row["reference_confidence_type"] = mm.get("reference_confidence_type", old.get("reference_confidence_type", ""))
        row["reference_pocket_probability_for_overlay"] = mm.get("reference_p2rank", old.get("reference_pocket_probability_for_overlay", ""))
        row["query_plddt_mean"] = mm.get("query_plddt_mean", old.get("query_plddt_mean", ""))
        row["reference_plddt_mean"] = mm.get("reference_plddt_mean", old.get("reference_plddt_mean", ""))
        row["query_pocket_mean_plddt"] = mm.get("query_pocket_mean_plddt", row["query_plddt_mean"])
        row["reference_confidence_semantics"] = mm.get("reference_confidence_semantics", "")
        row["reference_pocket_mean_plddt"] = mm.get("reference_pocket_mean_plddt", row["reference_plddt_mean"])
        row["reference_pocket_mean_bfactor"] = mm.get("reference_pocket_mean_bfactor", "")
        if row["reference_confidence_semantics"] == "REFERENCE_BFACTOR" or row["reference_confidence_type"] == "PDB_Bfactor_not_pLDDT":
            row["reference_plddt_mean"] = "NA"
            row["reference_pocket_mean_plddt"] = "NA"

        # Refresh PDB/AFSP rank-1 fields from current M06/M07/M08 where possible.
        row["pdb_target"] = p.get("target", old.get("pdb_target", ""))
        row["pdb_qtmscore"] = p.get("qtmscore", old.get("pdb_qtmscore", ""))
        row["pdb_qcov"] = p.get("qcov", old.get("pdb_qcov", ""))
        row["pdb_tcov"] = p.get("tcov", old.get("pdb_tcov", ""))
        row["pdb_class"] = p.get("pdb_struct_support_class", old.get("pdb_class", ""))

        row["afsp_target"] = a.get("target", old.get("afsp_target", ""))
        row["afsp_qtmscore"] = a.get("qtmscore", old.get("afsp_qtmscore", ""))
        row["afsp_qcov"] = a.get("qcov", old.get("afsp_qcov", ""))
        row["afsp_tcov"] = a.get("tcov", old.get("afsp_tcov", ""))
        row["afsp_class"] = a.get("afsp_struct_support_class", old.get("afsp_class", ""))

        row["primary_reference"] = d.get("primary_reference_target", old.get("primary_reference", ""))
        row["primary_reference_type"] = d.get("primary_reference_layer", old.get("primary_reference_type", ""))

        # File paths should point to canonical M10F outputs, not old local Section 6 paths.
        row["residue_detail_table"] = (
            f"06_visual_qc_v6/regression/canonical_v6_engine_regression/"
            f"rendered_png/v6_standard/tables/{pid}_pocket_residue_details.tsv"
        )
        row["alignment_detail_table"] = (
            f"06_visual_qc_v6/regression/canonical_v6_engine_regression/"
            f"rendered_png/v6_standard/tables/{pid}_alignment_pocket_classification.tsv"
        )

        # Keep viral context caution explicitly.
        row["viral_contig_context_note"] = VIRAL_CONTEXT_NOTE

        # Add bridge identifiers and M11 supporting context as new columns.
        row["query"] = query
        row["supporting_reference_n"] = s.get("supporting_reference_n", "")
        row["supporting_resolved_n"] = s.get("supporting_resolved_n", "")
        row["supporting_pocket_ready_n"] = s.get("supporting_pocket_ready_n", "")
        row["supporting_cache_missing_n"] = s.get("supporting_cache_missing_n", "")
        row["supporting_zero_pocket_n"] = s.get("supporting_zero_pocket_n", "")
        row["supporting_strong_struct_n"] = s.get("supporting_strong_struct_n", "")
        row["supporting_moderate_struct_n"] = s.get("supporting_moderate_struct_n", "")
        row["supporting_context_class"] = s.get("supporting_context_class", "")
        row["supporting_interpretation_flags"] = s.get("supporting_interpretation_flags", "")
        row["decision_matrix_source_policy"] = "B7_CALIBRATED_CLASS_WITH_M10F_REFRESH_AND_M11_SUPPORTING_CONTEXT"
        row["primary_decision_scope"] = "PRIMARY_RANK1_REFERENCE_ONLY"
        row["supporting_reference_policy"] = "SUPPORTING_REFERENCES_DO_NOT_OVERRIDE_PRIMARY_DECISION"
        row["m12a_note"] = "Primary decision matrix preserves Section 7 calibrated class while refreshing canonical M10F values and adding M11 supporting-context summary."

        output_rows.append(row)

    new_cols = [
        "query",
        "supporting_reference_n",
        "supporting_resolved_n",
        "supporting_pocket_ready_n",
        "supporting_cache_missing_n",
        "supporting_zero_pocket_n",
        "supporting_strong_struct_n",
        "supporting_moderate_struct_n",
        "supporting_context_class",
        "supporting_interpretation_flags",
        "query_pocket_mean_plddt",
        "reference_confidence_semantics",
        "reference_pocket_mean_plddt",
        "reference_pocket_mean_bfactor",
        "decision_matrix_source_policy",
        "primary_decision_scope",
        "supporting_reference_policy",
        "m12a_note",
    ]

    out_fields = old_header + [c for c in new_cols if c not in old_header]

    out_matrix = outdir / f"{mode}_primary_decision_matrix.tsv"
    write_tsv(out_matrix, output_rows, out_fields)

    # Class summary
    class_counts = Counter(r["final_decision_class"] for r in output_rows)
    priority_counts = Counter(r["final_priority"] for r in output_rows)

    class_rows = []
    for cls, n in sorted(class_counts.items()):
        class_rows.append({
            "mode": mode,
            "final_decision_class": cls,
            "n": n,
        })

    class_summary = outdir / f"{mode}_primary_decision_class_summary.tsv"
    write_tsv(class_summary, class_rows, ["mode","final_decision_class","n"])

    # Priority summary
    priority_rows = []
    for pri, n in sorted(priority_counts.items()):
        priority_rows.append({
            "mode": mode,
            "final_priority": pri,
            "n": n,
        })

    priority_summary = outdir / f"{mode}_primary_decision_priority_summary.tsv"
    write_tsv(priority_summary, priority_rows, ["mode","final_priority","n"])

    # Family summary
    fam_counts = Counter((r["family"], r["final_decision_class"], r["final_priority"]) for r in output_rows)
    fam_rows = []
    for (fam, cls, pri), n in sorted(fam_counts.items()):
        fam_rows.append({
            "mode": mode,
            "family": fam,
            "final_decision_class": cls,
            "final_priority": pri,
            "n": n,
        })

    fam_summary = outdir / f"{mode}_primary_decision_family_summary.tsv"
    write_tsv(fam_summary, fam_rows, ["mode","family","final_decision_class","final_priority","n"])

    # QC
    old_ids = set(old_by_t1p.keys())
    new_ids = set(m10_by_t1p.keys())
    id_intersection = old_ids & new_ids
    output_ids = {r["protein_id"] for r in output_rows}

    expected_class_counts = dict(class_counts)

    qc_rows = [
        {"metric": "module", "value": "M12A_primary_decision_matrix"},
        {"metric": "status", "value": "OK"},
        {"metric": "mode", "value": mode},
        {"metric": "old_matrix_rows", "value": str(len(old_rows))},
        {"metric": "m10f_metrics_rows", "value": str(len(m10))},
        {"metric": "m11_conflict_rows", "value": str(len(m11))},
        {"metric": "output_rows", "value": str(len(output_rows))},
        {"metric": "old_m10f_id_intersection", "value": str(len(id_intersection))},
        {"metric": "output_unique_ids", "value": str(len(output_ids))},
        {"metric": "class_summary_rows", "value": str(len(class_rows))},
        {"metric": "priority_summary_rows", "value": str(len(priority_rows))},
        {"metric": "family_summary_rows", "value": str(len(fam_rows))},
        {"metric": "source_policy", "value": "B7_CALIBRATED_CLASS_WITH_M10F_REFRESH_AND_M11_SUPPORTING_CONTEXT"},
        {"metric": "primary_scope", "value": "PRIMARY_RANK1_REFERENCE_ONLY"},
        {"metric": "supporting_policy", "value": "SUPPORTING_REFERENCES_DO_NOT_OVERRIDE_PRIMARY_DECISION"},
        {"metric": "matrix_path", "value": str(out_matrix)},
        {"metric": "class_summary_path", "value": str(class_summary)},
        {"metric": "priority_summary_path", "value": str(priority_summary)},
        {"metric": "family_summary_path", "value": str(fam_summary)},
    ]

    for cls, n in sorted(class_counts.items()):
        qc_rows.append({"metric": f"class_count_{cls}", "value": str(n)})

    qc = outdir / f"{mode}_primary_decision_matrix_qc.tsv"
    write_tsv(qc, qc_rows, ["metric","value"])

    ptr_rows = [
        {"artifact_key":"primary_decision_matrix","path":str(out_matrix),"role":"M12A primary/rank-1 decision matrix; one row per protein"},
        {"artifact_key":"primary_decision_class_summary","path":str(class_summary),"role":"M12A final decision class summary"},
        {"artifact_key":"primary_decision_priority_summary","path":str(priority_summary),"role":"M12A final priority summary"},
        {"artifact_key":"primary_decision_family_summary","path":str(fam_summary),"role":"M12A family-level primary decision summary"},
        {"artifact_key":"primary_decision_matrix_qc","path":str(qc),"role":"M12A QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m12a_primary_decision_matrix_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key","path","role"])

    print("M12A_PRIMARY_DECISION_MATRIX_OK")
    print("matrix", out_matrix)
    print("rows", len(output_rows))
    print("class_summary", class_summary)
    print("priority_summary", priority_summary)
    print("family_summary", fam_summary)
    print("qc", qc)
    print("pointer", ptr)

if __name__ == "__main__":
    main()
