#!/usr/bin/env python3
import argparse
import csv
import datetime
from pathlib import Path

METADATA_MAP = {
    "src_dramv":         "annotation_src_dramv",
    "src_vibrant":       "annotation_src_vibrant",
    "src_concordant":    "annotation_src_concordant",
    "dram_ko_id":        "annotation_dram_ko_id",
    "dram_amg_flags":    "annotation_dram_amg_flags",
    "vibrant_ko_id":     "annotation_vibrant_ko_id",
    "kofam_ko_id":       "annotation_kofam_ko_id",
    "kofam_trust_idx":   "annotation_kofam_trust_idx",
    "pfam_name":         "annotation_pfam_name",
    "pfam_acc":          "annotation_pfam_acc",
    "eggnog_cog":        "annotation_eggnog_cog",
    "eggnog_kegg_ko":    "annotation_eggnog_kegg_ko",
    "habitat_broad":     "annotation_habitat_broad",
    "habitat_fine":      "annotation_habitat_fine",
    "organism":          "annotation_organism",
    "flag_misannotation":   "viral_context_flag_misannotation",
    "flag_virus_specific":  "viral_context_flag_virus_specific",
    "ko_vlscore":           "viral_context_ko_vlscore",
    "pfam_vlscore":         "viral_context_pfam_vlscore",
    "left_class":           "viral_context_left_class",
    "right_class":          "viral_context_right_class",
    "context_score":        "viral_context_context_score",
    "phrog_support":        "viral_context_phrog_support",
    "confidence_final":     "viral_context_confidence_final",
}

ANNOTATION_FIELDS = list(METADATA_MAP.values())

EMPTY_ANNOTATION = {f: "" for f in ANNOTATION_FIELDS}

COMPACT_FIELDS = [
    "run_label", "mode", "protein_id", "query", "family",
    "final_rulebook_evidence_class", "final_rulebook_priority",
    "final_rulebook_recommendation", "final_rulebook_basis",
    "m12_combined_structural_recommendation",
    "m13b_classification_status", "m13b_existing_rulebook_class",
    "m13c_true_mismatch_flag",
    "primary_ligand_context_class", "ligand_evidence_tier",
    "annotation_kofam_ko_id", "annotation_pfam_name",
    "annotation_habitat_broad", "annotation_habitat_fine",
    "viral_context_confidence_final", "viral_context_flag_virus_specific",
    "png_primary_path",
    "export_timestamp",
]


def read_tsv(path):
    with Path(path).open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def load_metadata(meta_path):
    if not meta_path:
        return {}
    p = Path(meta_path)
    if not p.exists():
        return {}
    rows = read_tsv(str(p))
    result = {}
    for r in rows:
        pid = r.get("protein_id", "").strip()
        if pid:
            result[pid] = {dest: r.get(src, "") for src, dest in METADATA_MAP.items()}
    return result


def load_png_manifest(png_path):
    if not png_path:
        return {}
    p = Path(png_path)
    if not p.exists():
        return {}
    rows = read_tsv(str(p))

    def _key(r):
        for col in ("query", "query_id", "visual_id", "protein_id"):
            v = r.get(col, "").strip()
            if v:
                return v
        return ""

    def _png(r):
        for col in ("png_path", "primary_png", "png_primary_path", "expected_png"):
            v = r.get(col, "").strip()
            if v:
                return v
        return ""

    def _preferred(r):
        return r.get("row_index", "") == "1" or r.get("scope", "") == "smoke"

    result = {}
    for r in rows:
        key = _key(r)
        png = _png(r)
        if not key or not png:
            continue
        if key not in result or _preferred(r):
            result[key] = png
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--m13e-final", required=True)
    ap.add_argument("--m13e-compact", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--metadata", default=None)
    ap.add_argument("--png-manifest", default=None)
    ap.add_argument("--run-label", default="")
    args = ap.parse_args()

    mode = args.mode
    run_label = args.run_label
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    export_timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    final_rows = read_tsv(args.m13e_final)
    meta_by_pid = load_metadata(args.metadata)
    png_by_query = load_png_manifest(args.png_manifest)

    metadata_rows = len(meta_by_pid)
    metadata_matched = 0
    metadata_missing = 0
    png_matched = 0

    full_rows = []
    for r in final_rows:
        pid = r.get("protein_id", "").strip()
        query = r.get("query", "").strip()

        ann = meta_by_pid.get(pid)
        if ann:
            metadata_matched += 1
        else:
            ann = dict(EMPTY_ANNOTATION)
            if metadata_rows > 0:
                metadata_missing += 1

        png = png_by_query.get(query, "") or png_by_query.get(pid, "")
        if png:
            png_matched += 1

        out = {
            "run_label": run_label,
            "export_timestamp": export_timestamp,
            **r,
            **ann,
            "png_primary_path": png,
        }
        full_rows.append(out)

    if not final_rows:
        full_fields = (
            ["run_label", "export_timestamp"]
            + ["mode", "protein_id", "query", "family"]
            + ANNOTATION_FIELDS
            + ["png_primary_path"]
        )
    else:
        sample_keys = list(final_rows[0].keys())
        full_fields = (
            ["run_label", "export_timestamp"]
            + sample_keys
            + ANNOTATION_FIELDS
            + ["png_primary_path"]
        )

    full_path = outdir / f"{mode}_final_export_full.tsv"
    compact_path = outdir / f"{mode}_final_export_compact.tsv"
    qc_path = outdir / f"{mode}_final_export_qc.tsv"

    write_tsv(full_path, full_rows, full_fields)
    write_tsv(compact_path, full_rows, COMPACT_FIELDS)

    total = len(full_rows)
    join_cov = (
        f"{metadata_matched / total:.4f}" if total > 0 else "NA"
    )
    qc_status = (
        "WARN" if (metadata_rows > 0 and metadata_missing > 0) else "OK"
    )

    qc_rows = [
        {"metric": "module",                         "value": "M14_final_export"},
        {"metric": "status",                         "value": qc_status},
        {"metric": "mode",                           "value": mode},
        {"metric": "run_label",                      "value": run_label},
        {"metric": "export_timestamp",               "value": export_timestamp},
        {"metric": "final_rows",                     "value": str(total)},
        {"metric": "metadata_provided",              "value": "YES" if args.metadata else "NO"},
        {"metric": "metadata_rows",                  "value": str(metadata_rows)},
        {"metric": "metadata_matched_rows",          "value": str(metadata_matched)},
        {"metric": "metadata_missing_rows",          "value": str(metadata_missing)},
        {"metric": "metadata_join_coverage_fraction","value": join_cov},
        {"metric": "png_manifest_provided",          "value": "YES" if args.png_manifest else "NO"},
        {"metric": "png_matched_rows",               "value": str(png_matched)},
        {"metric": "full_export_path",               "value": str(full_path)},
        {"metric": "compact_export_path",            "value": str(compact_path)},
    ]
    write_tsv(qc_path, qc_rows, ["metric", "value"])

    ptr_rows = [
        {"artifact_key": "final_export_full",
         "path": str(full_path),
         "role": "M14 full export: M13E decisions + annotation context"},
        {"artifact_key": "final_export_compact",
         "path": str(compact_path),
         "role": "M14 compact export: key decisions + annotation summary"},
        {"artifact_key": "final_export_qc",
         "path": str(qc_path),
         "role": "M14 QC report"},
    ]
    ptr = Path("pipeline_state/artifacts/m14_final_export_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key", "path", "role"])

    print("M14_FINAL_EXPORT_OK")
    print("full_export", full_path)
    print("compact_export", compact_path)
    print("final_rows", total)
    print("metadata_matched_rows", metadata_matched)
    print("metadata_missing_rows", metadata_missing)
    print("metadata_join_coverage_fraction", join_cov)
    print("png_matched_rows", png_matched)
    print("qc_status", qc_status)
    print("qc", qc_path)
    print("pointer", ptr)


if __name__ == "__main__":
    main()
