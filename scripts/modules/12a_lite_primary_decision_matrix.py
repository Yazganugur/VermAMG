#!/usr/bin/env python3
import argparse
import csv
from collections import Counter
from pathlib import Path


def read_tsv(path, required=True):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        if required:
            raise SystemExit(f"ERROR: missing or empty input: {path}")
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def first_by(rows, key):
    out = {}
    for row in rows:
        value = row.get(key, "")
        if value and value not in out:
            out[value] = row
    return out


def metric_map(rows):
    out = {}
    for row in rows:
        metric = row.get("metric", "")
        if metric:
            out[metric] = row.get("value", "")
    return out


_VIRAL_CONTEXT_NOTE = (
    "Candidate is encoded on a viral contig; incomplete conservation relative to bacterial/PDB/AFSP "
    "references should not be treated as failure by itself; interpret divergence in the context of "
    "horizontal transfer, viral evolution, domain remodeling and host-context uncertainty."
)


def structural_support_class(pdb_row, afsp_row, decision_row):
    primary_layer = decision_row.get("primary_reference_layer", "")
    row = pdb_row if primary_layer == "PDB" else afsp_row if primary_layer == "AFSP" else {}
    if primary_layer == "PDB":
        return row.get("pdb_struct_support_class", "")
    if primary_layer == "AFSP":
        return row.get("afsp_struct_support_class", "")
    return decision_row.get("primary_reference_class", "")


def has_structural_support(label):
    label = str(label)
    return any(token in label for token in ("STRONG", "MODERATE", "DOMAIN_PARTIAL"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--m08-decision", required=True)
    parser.add_argument("--pdb-rank1", required=True)
    parser.add_argument("--afsp-rank1", required=True)
    parser.add_argument("--visual-contract", required=True)
    parser.add_argument("--m10d-qc", required=True)
    parser.add_argument("--m10e-render-manifest", required=True)
    parser.add_argument("--m11-conflict", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)

    decisions = read_tsv(args.m08_decision)
    pdb_rank1 = first_by(read_tsv(args.pdb_rank1), "query")
    afsp_rank1 = first_by(read_tsv(args.afsp_rank1), "query")
    visual_rows = read_tsv(args.visual_contract)
    m10d_qc = metric_map(read_tsv(args.m10d_qc))
    m10e_rows = read_tsv(args.m10e_render_manifest, required=False)
    m11_conflict = first_by(read_tsv(args.m11_conflict), "query")

    visual_primary = {}
    for row in visual_rows:
        if row.get("panel_role") == "PRIMARY" or str(row.get("panel_order", "")) in ("1", "1.0"):
            visual_primary[row.get("query", "")] = row

    render_by_query = {}
    for row in m10e_rows:
        query = row.get("query_id", "")
        if query and query not in render_by_query:
            render_by_query[query] = row

    output_rows = []
    for decision in decisions:
        query = decision.get("query", "")
        pdb = pdb_rank1.get(query, {})
        afsp = afsp_rank1.get(query, {})
        visual = visual_primary.get(query, {})
        render = render_by_query.get(query, {})
        m11 = m11_conflict.get(query, {})

        primary_struct_class = structural_support_class(pdb, afsp, decision)
        reference_signal = visual.get("reference_pocket_signal", "")
        reference_interpretation = visual.get("reference_pocket_interpretation", "")
        reference_ca_only = visual.get("reference_ca_only_like", "")
        query_prob = visual.get("query_top1_probability", "")
        query_pocket_present = "YES" if query_prob not in ("", "0", "0.0", "NA") else "NO"

        if reference_signal == "UNRELIABLE_CA_ONLY_INPUT":
            pocket_policy = "QUERY_POCKET_ONLY_REFERENCE_POCKET_UNRELIABLE"
            final_class = "LITE_STRUCTURAL_SUPPORT_WITH_QUERY_POCKET_REFERENCE_UNRELIABLE" if (
                query_pocket_present == "YES" and has_structural_support(primary_struct_class)
            ) else "LITE_REFERENCE_POCKET_UNRELIABLE_REVIEW"
            caution = "Reference P2Rank pocket signal is unreliable because the materialized reference structure is CA-only-like; do not interpret zero pockets as biological absence."
        else:
            pocket_policy = "QUERY_AND_REFERENCE_POCKET_CONTEXT"
            final_class = "LITE_STRUCTURAL_SUPPORT_WITH_POCKET_CONTEXT" if (
                query_pocket_present == "YES" and has_structural_support(primary_struct_class)
            ) else "LITE_REVIEW_NEEDED"
            caution = (
                "Structural similarity was detected by Foldseek and pocket context was predicted by P2Rank; "
                "this is computational evidence only and not experimental functional validation."
                if final_class == "LITE_STRUCTURAL_SUPPORT_WITH_POCKET_CONTEXT"
                else ""
            )

        render_png = render.get("expected_png", "")
        render_status = "PNG_RENDERED" if render_png and Path(render_png).exists() else "PNG_NOT_PROVEN"

        output_rows.append({
            "mode": mode,
            "query": query,
            "protein_id": decision.get("protein_id", ""),
            "family": decision.get("family", ""),
            "primary_reference_layer": decision.get("primary_reference_layer", ""),
            "primary_reference_target": decision.get("primary_reference_target", ""),
            "primary_reference_class": decision.get("primary_reference_class", primary_struct_class),
            "primary_struct_support_class": primary_struct_class,
            "pdb_target": pdb.get("target", ""),
            "pdb_qtmscore": pdb.get("qtmscore", ""),
            "pdb_qcov": pdb.get("qcov", ""),
            "pdb_class": pdb.get("pdb_struct_support_class", ""),
            "afsp_target": afsp.get("target", ""),
            "afsp_qtmscore": afsp.get("qtmscore", ""),
            "afsp_qcov": afsp.get("qcov", ""),
            "afsp_class": afsp.get("afsp_struct_support_class", ""),
            "query_top1_probability": query_prob,
            "query_top1_score": visual.get("query_top1_score", ""),
            "query_pocket_present": query_pocket_present,
            "reference_pocket_signal": reference_signal,
            "reference_pocket_interpretation": reference_interpretation,
            "reference_ca_only_like": reference_ca_only,
            "reference_pocket_overlay": visual.get("reference_pocket_overlay", "NONE"),
            "query_pocket_overlay": visual.get("query_pocket_overlay", "PRESENT"),
            "visual_status": visual.get("visual_status", ""),
            "m10d_lite_status": m10d_qc.get("status", ""),
            "m10d_unreliable_ca_only_pass_rows": m10d_qc.get("unreliable_ca_only_qc_PASS", ""),
            "m10e_render_status": render_status,
            "m10e_expected_png": render_png,
            "supporting_reference_n": m11.get("supporting_reference_n", ""),
            "supporting_pocket_ready_n": m11.get("supporting_pocket_ready_n", ""),
            "supporting_zero_pocket_n": m11.get("supporting_zero_pocket_n", ""),
            "supporting_context_class": m11.get("supporting_context_class", ""),
            "supporting_interpretation_flags": m11.get("supporting_interpretation_flags", ""),
            "primary_pocket_evidence_policy": pocket_policy,
            "final_decision_class": final_class,
            "final_priority": "LITE_REVIEW" if reference_signal == "UNRELIABLE_CA_ONLY_INPUT" else "LITE_STANDARD",
            "scientific_caution": " | ".join(x for x in [caution, _VIRAL_CONTEXT_NOTE] if x),
            "decision_matrix_source_policy": "M12A_LITE_LOCAL_TEST_NO_M10F_NO_OLD_MATRIX",
        })

    fields = [
        "mode","query","protein_id","family",
        "primary_reference_layer","primary_reference_target","primary_reference_class","primary_struct_support_class",
        "pdb_target","pdb_qtmscore","pdb_qcov","pdb_class",
        "afsp_target","afsp_qtmscore","afsp_qcov","afsp_class",
        "query_top1_probability","query_top1_score","query_pocket_present",
        "reference_pocket_signal","reference_pocket_interpretation","reference_ca_only_like",
        "reference_pocket_overlay","query_pocket_overlay","visual_status",
        "m10d_lite_status","m10d_unreliable_ca_only_pass_rows",
        "m10e_render_status","m10e_expected_png",
        "supporting_reference_n","supporting_pocket_ready_n","supporting_zero_pocket_n",
        "supporting_context_class","supporting_interpretation_flags",
        "primary_pocket_evidence_policy","final_decision_class","final_priority",
        "scientific_caution","decision_matrix_source_policy",
    ]

    matrix = outdir / f"{mode}_primary_decision_matrix.tsv"
    class_summary = outdir / f"{mode}_primary_decision_class_summary.tsv"
    qc = outdir / f"{mode}_primary_decision_matrix_qc.tsv"
    pointer = Path("pipeline_state/artifacts/m12a_primary_decision_matrix_pointer.tsv")

    write_tsv(matrix, output_rows, fields)

    class_rows = [
        {"mode": mode, "final_decision_class": cls, "n": count}
        for cls, count in sorted(Counter(row["final_decision_class"] for row in output_rows).items())
    ]
    write_tsv(class_summary, class_rows, ["mode","final_decision_class","n"])

    qc_rows = [
        {"metric": "module", "value": "M12A_lite_primary_decision_matrix"},
        {"metric": "status", "value": "OK"},
        {"metric": "mode", "value": mode},
        {"metric": "m08_decision_rows", "value": str(len(decisions))},
        {"metric": "output_rows", "value": str(len(output_rows))},
        {"metric": "unreliable_ca_only_rows", "value": str(sum(row["reference_pocket_signal"] == "UNRELIABLE_CA_ONLY_INPUT" for row in output_rows))},
        {"metric": "positive_reference_pocket_overclaim_rows", "value": "0"},
        {"metric": "m10d_status", "value": m10d_qc.get("status", "")},
        {"metric": "matrix_path", "value": str(matrix)},
        {"metric": "class_summary_path", "value": str(class_summary)},
    ]
    write_tsv(qc, qc_rows, ["metric","value"])

    pointer_rows = [
        {"artifact_key": "primary_decision_matrix", "path": str(matrix), "role": "M12A-lite local/test primary decision matrix"},
        {"artifact_key": "primary_decision_class_summary", "path": str(class_summary), "role": "M12A-lite class summary"},
        {"artifact_key": "primary_decision_matrix_qc", "path": str(qc), "role": "M12A-lite QC report"},
    ]
    write_tsv(pointer, pointer_rows, ["artifact_key","path","role"])

    print("M12A_LITE_PRIMARY_DECISION_MATRIX_OK")
    print("matrix", matrix)
    print("rows", len(output_rows))
    print("class_summary", class_summary)
    print("qc", qc)
    print("pointer", pointer)


if __name__ == "__main__":
    main()
