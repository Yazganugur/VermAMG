#!/usr/bin/env python3
"""
15_user_facing_final_exports.py

Build user-facing final TSVs from the corrected full-atom run:
  1. final_primary_rank1_summary.tsv       - one row per query
  2. final_reference_panel_long.tsv        - one row per query/reference panel row
  3. pocket_residue_details_long.tsv       - residue-level overlap detail

These are intentionally compact interpretation outputs. Raw module outputs remain
available under M05/M09/M10/M11/M12 for audit/debug.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import re
from pathlib import Path
from typing import Iterable


PRIMARY_FIELDS = [
    "mode",
    "query",
    "protein_id",
    "family",
    "primary_reference_layer",
    "primary_reference_target",
    "primary_reference_panel_order",
    "primary_reference_source_rank",
    "primary_reference_support_class",
    "primary_reference_selection_reason",
    "foldseek_qtmscore",
    "foldseek_qcov",
    "foldseek_tcov",
    "foldseek_lddt",
    "foldseek_evalue",
    "foldseek_bits",
    "alignment_rmsd",
    "alignment_atom_pairs",
    "query_p2rank_probability",
    "query_p2rank_score",
    "reference_p2rank_probability",
    "reference_p2rank_score",
    "query_pocket_residue_n",
    "reference_pocket_residue_n",
    "query_conserved_n",
    "query_unique_n",
    "reference_conserved_n",
    "reference_unique_n",
    "query_overlap_fraction",
    "reference_overlap_fraction",
    "pocket_overlap_balanced_fraction",
    "pocket_overlap_jaccard_aligned_ca",
    "query_pocket_mean_plddt",
    "reference_confidence_semantics",
    "reference_pocket_mean_plddt",
    "reference_pocket_mean_bfactor",
    "reference_pocket_signal",
    "reference_zero_pocket_flag",
    "reference_ca_only_like",
    "primary_overlap_metric_status",
    "primary_overlap_metric_note",
    "supporting_reference_n",
    "supporting_pocket_ready_n",
    "supporting_zero_pocket_n",
    "best_supporting_by_overlap_panel_order",
    "best_supporting_by_overlap_layer",
    "best_supporting_by_overlap_target",
    "best_supporting_by_overlap_balanced_fraction",
    "best_supporting_by_overlap_qtmscore",
    "supporting_reference_has_better_pocket_overlap",
    "supporting_reference_has_higher_qtm",
    "manual_inspection_priority",
    "manual_inspection_reason",
    "final_decision_class",
    "final_priority",
    "combined_structural_recommendation",
    "combined_structural_recommendation_note",
    "scientific_caution",
    "final_composite_png_path",
    "primary_policy",
    "export_timestamp",
]

REFERENCE_FIELDS = [
    "mode",
    "query",
    "protein_id",
    "family",
    "panel_order",
    "panel_role",
    "reference_layer",
    "target",
    "source_rank",
    "support_class",
    "selection_reason",
    "foldseek_qtmscore",
    "foldseek_qcov",
    "foldseek_tcov",
    "foldseek_lddt",
    "foldseek_evalue",
    "foldseek_bits",
    "reference_file_resolution_status",
    "reference_p2rank_status",
    "reference_pocket_signal",
    "reference_pocket_interpretation",
    "reference_zero_pocket_flag",
    "reference_ca_only_like",
    "reference_top1_probability",
    "reference_top1_score",
    "alignment_rmsd",
    "alignment_atom_pairs",
    "query_pocket_n",
    "reference_pocket_n",
    "query_conserved_n",
    "query_unique_n",
    "reference_conserved_n",
    "reference_unique_n",
    "query_overlap_fraction",
    "reference_overlap_fraction",
    "pocket_overlap_balanced_fraction",
    "pocket_overlap_jaccard_aligned_ca",
    "query_pocket_mean_plddt",
    "reference_confidence_semantics",
    "reference_pocket_mean_plddt",
    "reference_pocket_mean_bfactor",
    "overlap_metric_status",
    "overlap_metric_note",
    "supporting_decision_class",
    "supporting_priority",
    "recommended_use",
    "can_override_primary",
    "manual_inspection_flag",
    "query_model_pdb_portable",
    "reference_file_path_portable",
    "unique_reference_id",
]

RESIDUE_FIELDS = [
    "mode",
    "query",
    "protein_id",
    "family",
    "panel_order",
    "panel_role",
    "reference_layer",
    "target",
    "residue_source",
    "pocket_overlap_class",
    "residue_id",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fields,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def clean_label(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_")


def portable(workspace: Path, path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(workspace.resolve()))
    except Exception:
        return str(path)


def as_float(value: str | None) -> float | None:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if text in {"", "NA", "nan", "None"}:
            return None
        return float(text)
    except Exception:
        return None


def as_int(value: str | None) -> int:
    try:
        if value is None or str(value).strip() in {"", "NA"}:
            return 0
        return int(float(str(value)))
    except Exception:
        return 0


def fmt(value: float | None, nd: int = 4) -> str:
    if value is None:
        return "NA"
    return f"{value:.{nd}f}"


def key3(row: dict[str, str]) -> tuple[str, str, str]:
    return (row.get("query", ""), row.get("panel_order", ""), row.get("target", ""))


def by_query(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        out.setdefault(row.get("query", ""), []).append(row)
    return out


def index_pngs(final_png_dir: Path, workspace: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not final_png_dir.is_dir():
        return mapping
    for png in final_png_dir.glob("*_v6_standard_600dpi.png"):
        name = png.name
        if "_v6_standard_600dpi.png" not in name:
            continue
        stem = name.replace("_v6_standard_600dpi.png", "")
        # Query ids may themselves contain underscores; match later by clean query prefix.
        mapping[stem] = portable(workspace, png)
    return mapping


def find_png(png_map: dict[str, str], query: str, family: str) -> str:
    exact = f"{clean_label(query)}_{clean_label(family)}"
    if exact in png_map:
        return png_map[exact]
    prefix = f"{clean_label(query)}_"
    for stem, path in png_map.items():
        if stem.startswith(prefix):
            return path
    return ""


def choose_best_supporting_by_overlap(rows: list[dict[str, str]]) -> dict[str, str]:
    candidates = [
        r for r in rows
        if r.get("panel_role") != "PRIMARY"
        and as_float(r.get("pocket_overlap_balanced_fraction")) is not None
        and r.get("overlap_metric_status") in {"OK", "REFERENCE_ZERO_POCKET", "QUERY_ZERO_POCKET"}
    ]
    if not candidates:
        return {}

    def sort_key(row: dict[str, str]) -> tuple[float, float, float, float]:
        balanced = as_float(row.get("pocket_overlap_balanced_fraction")) or -1.0
        jaccard = as_float(row.get("pocket_overlap_jaccard_aligned_ca")) or -1.0
        qtm = as_float(row.get("foldseek_qtmscore")) or -1.0
        p2 = as_float(row.get("reference_top1_probability")) or -1.0
        return (balanced, jaccard, qtm, p2)

    return sorted(candidates, key=sort_key, reverse=True)[0]


def primary_manual_flag(primary_overlap: dict[str, str], best_support: dict[str, str], supporting_rows: list[dict[str, str]]) -> tuple[str, str, str, str]:
    primary_bal = as_float(primary_overlap.get("pocket_overlap_balanced_fraction"))
    best_bal = as_float(best_support.get("pocket_overlap_balanced_fraction"))
    primary_qtm = as_float(primary_overlap.get("foldseek_qtmscore"))
    best_qtm = max((as_float(r.get("foldseek_qtmscore")) or -1.0 for r in supporting_rows), default=-1.0)
    status = primary_overlap.get("overlap_metric_status", "")

    better_overlap = "NO"
    higher_qtm = "NO"
    priority = "STANDARD"
    reason = "Primary/rank-1 path is retained; no stronger supporting-pocket flag was detected."

    if status == "REFERENCE_ZERO_POCKET":
        priority = "INSPECT_PRIMARY_REFERENCE_ZERO_POCKET"
        reason = "Primary reference has no P2Rank top-1 pocket residues; inspect supporting references before pocket-level interpretation."
        if best_bal is not None:
            better_overlap = "YES"
    elif status == "QUERY_ZERO_POCKET":
        priority = "INSPECT_QUERY_ZERO_POCKET"
        reason = "Query has no P2Rank top-1 pocket residues; pocket-overlap interpretation is not available for the primary row."
    elif status in {"MISSING_OVERLAP_METRIC", "PYMOL_ROW_ERROR", "MISSING_QUERY_PDB", "MISSING_REFERENCE_PDB"}:
        priority = "REVIEW_METRICS_MISSING"
        reason = "Primary pocket-overlap metric failed or is missing; inspect M10/M12 inputs before interpretation."
    elif primary_bal is None:
        priority = "REVIEW"
        reason = "Primary pocket-overlap metric is missing; inspect M10/M12 inputs before interpretation."
    elif best_bal is not None and best_bal > primary_bal + 0.05:
        better_overlap = "YES"
        priority = "INSPECT_SUPPORTING_REFERENCE"
        reason = "A supporting reference has a higher pocket-overlap score than the primary reference; do not auto-override primary, but inspect it."
    elif primary_bal < 0.35:
        priority = "INSPECT_PRIMARY_LOW_POCKET_OVERLAP"
        reason = "Primary query/reference top-1 pockets overlap weakly; inspect the primary figure and supporting references."

    if primary_qtm is not None and best_qtm > primary_qtm + 0.03:
        higher_qtm = "YES"
        if priority == "STANDARD":
            priority = "INSPECT_SUPPORTING_REFERENCE"
            reason = "A supporting reference has meaningfully higher qTM than the primary; inspect as contextual evidence."

    return better_overlap, higher_qtm, priority, reason


def enrich_panel_rows(
    contract_rows: list[dict[str, str]],
    panel_rows: list[dict[str, str]],
    overlap_rows: list[dict[str, str]],
    supporting_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    panel_by_key = {key3(r): r for r in panel_rows}
    overlap_by_key = {key3(r): r for r in overlap_rows}
    support_by_key = {
        (
            r.get("query", ""),
            r.get("supporting_panel_order", ""),
            r.get("supporting_target", ""),
        ): r
        for r in supporting_rows
    }

    out = []
    for row in contract_rows:
        key = key3(row)
        panel = panel_by_key.get(key, {})
        overlap = overlap_by_key.get(key, {})
        supp = support_by_key.get(key, {})
        panel_role = row.get("panel_role", "")
        manual_flag = ""
        if panel_role != "PRIMARY":
            bal = as_float(overlap.get("pocket_overlap_balanced_fraction"))
            if bal is None:
                manual_flag = "SUPPORTING_OVERLAP_NOT_AVAILABLE"
            elif bal >= 0.50:
                manual_flag = "SUPPORTING_HIGH_POCKET_OVERLAP_CONTEXT"
            elif bal >= 0.35:
                manual_flag = "SUPPORTING_MODERATE_POCKET_OVERLAP_CONTEXT"
            else:
                manual_flag = "SUPPORTING_LOW_POCKET_OVERLAP_CONTEXT"

        out.append({
            "mode": overlap.get("mode", ""),
            "query": row.get("query", ""),
            "protein_id": row.get("protein_id", ""),
            "family": row.get("family", ""),
            "panel_order": row.get("panel_order", ""),
            "panel_role": panel_role,
            "reference_layer": row.get("reference_layer", ""),
            "target": row.get("target", ""),
            "source_rank": row.get("source_rank", ""),
            "support_class": row.get("support_class", ""),
            "selection_reason": row.get("selection_reason", ""),
            "foldseek_qtmscore": panel.get("qtmscore", ""),
            "foldseek_qcov": panel.get("qcov", ""),
            "foldseek_tcov": panel.get("tcov", ""),
            "foldseek_lddt": panel.get("lddt", ""),
            "foldseek_evalue": panel.get("evalue", ""),
            "foldseek_bits": panel.get("bits", ""),
            "reference_file_resolution_status": row.get("reference_file_resolution_status", ""),
            "reference_p2rank_status": row.get("reference_p2rank_status", ""),
            "reference_pocket_signal": row.get("reference_pocket_signal", ""),
            "reference_pocket_interpretation": row.get("reference_pocket_interpretation", ""),
            "reference_zero_pocket_flag": row.get("reference_zero_pocket_flag", ""),
            "reference_ca_only_like": row.get("reference_ca_only_like", ""),
            "reference_top1_probability": row.get("reference_top1_probability", ""),
            "reference_top1_score": row.get("reference_top1_score", ""),
            "alignment_rmsd": overlap.get("alignment_rmsd", ""),
            "alignment_atom_pairs": overlap.get("alignment_atom_pairs", ""),
            "query_pocket_n": overlap.get("query_pocket_n", ""),
            "reference_pocket_n": overlap.get("reference_pocket_n", ""),
            "query_conserved_n": overlap.get("query_conserved_n", ""),
            "query_unique_n": overlap.get("query_unique_n", ""),
            "reference_conserved_n": overlap.get("reference_conserved_n", ""),
            "reference_unique_n": overlap.get("reference_unique_n", ""),
            "query_overlap_fraction": overlap.get("query_overlap_fraction", ""),
            "reference_overlap_fraction": overlap.get("reference_overlap_fraction", ""),
            "pocket_overlap_balanced_fraction": overlap.get("pocket_overlap_balanced_fraction", ""),
            "pocket_overlap_jaccard_aligned_ca": overlap.get("pocket_overlap_jaccard_aligned_ca", ""),
            "query_pocket_mean_plddt": overlap.get("query_pocket_mean_plddt", ""),
            "reference_confidence_semantics": overlap.get("reference_confidence_semantics", ""),
            "reference_pocket_mean_plddt": overlap.get("reference_pocket_mean_plddt", ""),
            "reference_pocket_mean_bfactor": overlap.get("reference_pocket_mean_bfactor", ""),
            "overlap_metric_status": overlap.get("overlap_metric_status", "MISSING_OVERLAP_METRIC"),
            "overlap_metric_note": overlap.get("overlap_metric_note", ""),
            "supporting_decision_class": supp.get("supporting_decision_class", ""),
            "supporting_priority": supp.get("supporting_priority", ""),
            "recommended_use": supp.get("recommended_use", ""),
            "can_override_primary": "NO",
            "manual_inspection_flag": manual_flag,
            "query_model_pdb_portable": row.get("query_model_pdb_portable", ""),
            "reference_file_path_portable": row.get("reference_file_path_portable", ""),
            "unique_reference_id": row.get("unique_reference_id", ""),
            "_query_conserved_residue_ids": overlap.get("query_conserved_residue_ids", ""),
            "_query_unique_residue_ids": overlap.get("query_unique_residue_ids", ""),
            "_reference_conserved_residue_ids": overlap.get("reference_conserved_residue_ids", ""),
            "_reference_unique_residue_ids": overlap.get("reference_unique_residue_ids", ""),
        })
    return out


def residue_detail_rows(reference_long_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    specs = [
        ("QUERY", "OVERLAPPING", "_query_conserved_residue_ids"),
        ("QUERY", "QUERY_UNIQUE", "_query_unique_residue_ids"),
        ("REFERENCE", "OVERLAPPING", "_reference_conserved_residue_ids"),
        ("REFERENCE", "REFERENCE_UNIQUE", "_reference_unique_residue_ids"),
    ]
    for row in reference_long_rows:
        base = {k: row.get(k, "") for k in [
            "mode", "query", "protein_id", "family", "panel_order",
            "panel_role", "reference_layer", "target",
        ]}
        for source, cls, field in specs:
            for residue_id in row.get(field, "").split():
                rows.append({
                    **base,
                    "residue_source": source,
                    "pocket_overlap_class": cls,
                    "residue_id": residue_id,
                })
    return rows


def build_primary_rows(
    contract_rows: list[dict[str, str]],
    panel_long_rows: list[dict[str, str]],
    primary_decision_rows: list[dict[str, str]],
    combined_rows: list[dict[str, str]],
    png_map: dict[str, str],
    timestamp: str,
) -> list[dict[str, str]]:
    contract_primary = [r for r in contract_rows if r.get("panel_role") == "PRIMARY"]
    panel_by_key = {key3(r): r for r in panel_long_rows}
    all_by_query = by_query(panel_long_rows)
    m12a_by_query = {r.get("query", ""): r for r in primary_decision_rows}
    combined_by_query = {r.get("query", ""): r for r in combined_rows}

    out = []
    for row in sorted(contract_primary, key=lambda r: r.get("query", "")):
        query = row.get("query", "")
        family = row.get("family", "")
        primary = panel_by_key.get(key3(row), {})
        all_ref_rows = all_by_query.get(query, [])
        supporting = [r for r in all_ref_rows if r.get("panel_role") != "PRIMARY"]
        best_support = choose_best_supporting_by_overlap(supporting)
        better_overlap, higher_qtm, priority, reason = primary_manual_flag(primary, best_support, supporting)
        m12a = m12a_by_query.get(query, {})
        combined = combined_by_query.get(query, {})

        out.append({
            "mode": primary.get("mode", m12a.get("mode", "")),
            "query": query,
            "protein_id": row.get("protein_id", ""),
            "family": family,
            "primary_reference_layer": row.get("reference_layer", ""),
            "primary_reference_target": row.get("target", ""),
            "primary_reference_panel_order": row.get("panel_order", ""),
            "primary_reference_source_rank": row.get("source_rank", ""),
            "primary_reference_support_class": row.get("support_class", ""),
            "primary_reference_selection_reason": row.get("selection_reason", ""),
            "foldseek_qtmscore": primary.get("foldseek_qtmscore", ""),
            "foldseek_qcov": primary.get("foldseek_qcov", ""),
            "foldseek_tcov": primary.get("foldseek_tcov", ""),
            "foldseek_lddt": primary.get("foldseek_lddt", ""),
            "foldseek_evalue": primary.get("foldseek_evalue", ""),
            "foldseek_bits": primary.get("foldseek_bits", ""),
            "alignment_rmsd": primary.get("alignment_rmsd", ""),
            "alignment_atom_pairs": primary.get("alignment_atom_pairs", ""),
            "query_p2rank_probability": row.get("query_top1_probability", ""),
            "query_p2rank_score": row.get("query_top1_score", ""),
            "reference_p2rank_probability": row.get("reference_top1_probability", ""),
            "reference_p2rank_score": row.get("reference_top1_score", ""),
            "query_pocket_residue_n": primary.get("query_pocket_n", ""),
            "reference_pocket_residue_n": primary.get("reference_pocket_n", ""),
            "query_conserved_n": primary.get("query_conserved_n", ""),
            "query_unique_n": primary.get("query_unique_n", ""),
            "reference_conserved_n": primary.get("reference_conserved_n", ""),
            "reference_unique_n": primary.get("reference_unique_n", ""),
            "query_overlap_fraction": primary.get("query_overlap_fraction", ""),
            "reference_overlap_fraction": primary.get("reference_overlap_fraction", ""),
            "pocket_overlap_balanced_fraction": primary.get("pocket_overlap_balanced_fraction", ""),
            "pocket_overlap_jaccard_aligned_ca": primary.get("pocket_overlap_jaccard_aligned_ca", ""),
            "query_pocket_mean_plddt": primary.get("query_pocket_mean_plddt", ""),
            "reference_confidence_semantics": primary.get("reference_confidence_semantics", ""),
            "reference_pocket_mean_plddt": primary.get("reference_pocket_mean_plddt", ""),
            "reference_pocket_mean_bfactor": primary.get("reference_pocket_mean_bfactor", ""),
            "reference_pocket_signal": row.get("reference_pocket_signal", ""),
            "reference_zero_pocket_flag": row.get("reference_zero_pocket_flag", ""),
            "reference_ca_only_like": row.get("reference_ca_only_like", ""),
            "primary_overlap_metric_status": primary.get("overlap_metric_status", ""),
            "primary_overlap_metric_note": primary.get("overlap_metric_note", ""),
            "supporting_reference_n": m12a.get("supporting_reference_n", combined.get("supporting_reference_n", "")),
            "supporting_pocket_ready_n": m12a.get("supporting_pocket_ready_n", combined.get("supporting_pocket_ready_n", "")),
            "supporting_zero_pocket_n": m12a.get("supporting_zero_pocket_n", combined.get("supporting_zero_pocket_n", "")),
            "best_supporting_by_overlap_panel_order": best_support.get("panel_order", ""),
            "best_supporting_by_overlap_layer": best_support.get("reference_layer", ""),
            "best_supporting_by_overlap_target": best_support.get("target", ""),
            "best_supporting_by_overlap_balanced_fraction": best_support.get("pocket_overlap_balanced_fraction", ""),
            "best_supporting_by_overlap_qtmscore": best_support.get("foldseek_qtmscore", ""),
            "supporting_reference_has_better_pocket_overlap": better_overlap,
            "supporting_reference_has_higher_qtm": higher_qtm,
            "manual_inspection_priority": priority,
            "manual_inspection_reason": reason,
            "final_decision_class": m12a.get("final_decision_class", combined.get("primary_final_decision_class", "")),
            "final_priority": m12a.get("final_priority", combined.get("primary_final_priority", "")),
            "combined_structural_recommendation": combined.get("combined_structural_recommendation", ""),
            "combined_structural_recommendation_note": combined.get("combined_structural_recommendation_note", ""),
            "scientific_caution": m12a.get("scientific_caution", ""),
            "final_composite_png_path": find_png(png_map, query, family),
            "primary_policy": "PRIMARY_RANK1_DECISION_PRESERVED__SUPPORTING_REFERENCES_CONTEXT_ONLY_NO_AUTO_OVERRIDE",
            "export_timestamp": timestamp,
        })
    return out


def write_dictionary(path: Path) -> None:
    rows = [
        {"file": "final_primary_rank1_summary", "field": "pocket_overlap_balanced_fraction", "meaning": "Mean of query_overlap_fraction and reference_overlap_fraction for the primary/rank-1 reference."},
        {"file": "final_primary_rank1_summary", "field": "supporting_reference_has_better_pocket_overlap", "meaning": "YES when a supporting reference has balanced pocket overlap more than 0.05 above primary; it is an inspection flag, not an automatic override."},
        {"file": "final_primary_rank1_summary", "field": "reference_confidence_semantics", "meaning": "REFERENCE_BFACTOR for experimental PDB references; REFERENCE_PLDDT for AFSP predicted references."},
        {"file": "final_reference_panel_long", "field": "can_override_primary", "meaning": "Always NO in this export. Supporting references provide context only."},
        {"file": "pocket_residue_details_long", "field": "pocket_overlap_class", "meaning": "OVERLAPPING, QUERY_UNIQUE, or REFERENCE_UNIQUE after aligned CA pocket comparison."},
    ]
    write_tsv(path, rows, ["file", "field", "meaning"])


def write_readme(path: Path, mode: str) -> None:
    text = f"""# User-facing VermAMG exports ({mode})

This folder contains compact interpretation tables built from the corrected
full-atom reference run.

Files:
- `{mode}_final_primary_rank1_summary.tsv`: one row per query. This is the main
  rank-1/primary interpretation table.
- `{mode}_final_reference_panel_long.tsv`: one row per query/reference panel row.
  Use this when checking whether supporting references provide better context.
- `{mode}_pocket_residue_details_long.tsv`: residue-level pocket overlap classes.
- `{mode}_user_facing_data_dictionary.tsv`: short field definitions.
- `{mode}_user_facing_export_qc.tsv`: row counts and warning flags.

Policy:
- The primary/rank-1 path is preserved.
- Supporting references are audit/context evidence and do not automatically
  override primary decisions.
- PDB reference B-column values are B-factors; AFSP reference B-column values
  are pLDDT-like confidence values.
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build user-facing final TSV exports.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--mode", default="full")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--reference-panel", required=True)
    parser.add_argument("--primary-decision", required=True)
    parser.add_argument("--supporting-decision", required=True)
    parser.add_argument("--combined-decision", required=True)
    parser.add_argument("--overlap-metrics", required=True)
    parser.add_argument("--final-png-dir", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    def wpath(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else workspace / p

    contract = read_tsv(wpath(args.contract))
    panel = read_tsv(wpath(args.reference_panel))
    primary_decision = read_tsv(wpath(args.primary_decision))
    supporting_decision = read_tsv(wpath(args.supporting_decision))
    combined_decision = read_tsv(wpath(args.combined_decision))
    overlap = read_tsv(wpath(args.overlap_metrics))
    outdir = wpath(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    png_map = index_pngs(wpath(args.final_png_dir), workspace)

    reference_long = enrich_panel_rows(contract, panel, overlap, supporting_decision)
    primary_rows = build_primary_rows(contract, reference_long, primary_decision, combined_decision, png_map, timestamp)
    residue_rows = residue_detail_rows(reference_long)

    primary_path = outdir / f"{args.mode}_final_primary_rank1_summary.tsv"
    reference_path = outdir / f"{args.mode}_final_reference_panel_long.tsv"
    residue_path = outdir / f"{args.mode}_pocket_residue_details_long.tsv"
    dictionary_path = outdir / f"{args.mode}_user_facing_data_dictionary.tsv"
    readme_path = outdir / "README_user_facing_exports.md"
    qc_path = outdir / f"{args.mode}_user_facing_export_qc.tsv"

    write_tsv(primary_path, primary_rows, PRIMARY_FIELDS)
    write_tsv(reference_path, reference_long, REFERENCE_FIELDS)
    write_tsv(residue_path, residue_rows, RESIDUE_FIELDS)
    write_dictionary(dictionary_path)
    write_readme(readme_path, args.mode)

    expected_primary = len({r.get("query", "") for r in contract if r.get("query", "")})
    bad_overlap_statuses = {"", "MISSING_OVERLAP_METRIC", "PYMOL_ROW_ERROR", "MISSING_QUERY_PDB", "MISSING_REFERENCE_PDB"}
    primary_missing_overlap = sum(1 for r in primary_rows if r.get("primary_overlap_metric_status") in bad_overlap_statuses)
    primary_reference_zero_pocket = sum(1 for r in primary_rows if r.get("primary_overlap_metric_status") == "REFERENCE_ZERO_POCKET")
    primary_query_zero_pocket = sum(1 for r in primary_rows if r.get("primary_overlap_metric_status") == "QUERY_ZERO_POCKET")
    primary_missing_png = sum(1 for r in primary_rows if not r.get("final_composite_png_path"))
    better_overlap = sum(1 for r in primary_rows if r.get("supporting_reference_has_better_pocket_overlap") == "YES")
    higher_qtm = sum(1 for r in primary_rows if r.get("supporting_reference_has_higher_qtm") == "YES")
    ref_missing_overlap = sum(1 for r in reference_long if r.get("overlap_metric_status") in bad_overlap_statuses)
    qc_status = "OK"
    if len(primary_rows) != expected_primary or primary_missing_overlap > 0 or ref_missing_overlap > 0:
        qc_status = "WARN"

    qc_rows = [
        {"metric": "module", "value": "M15_user_facing_final_exports"},
        {"metric": "status", "value": qc_status},
        {"metric": "mode", "value": args.mode},
        {"metric": "expected_primary_queries", "value": str(expected_primary)},
        {"metric": "primary_rows", "value": str(len(primary_rows))},
        {"metric": "reference_panel_rows", "value": str(len(reference_long))},
        {"metric": "pocket_residue_detail_rows", "value": str(len(residue_rows))},
        {"metric": "primary_missing_overlap_rows", "value": str(primary_missing_overlap)},
        {"metric": "primary_reference_zero_pocket_rows", "value": str(primary_reference_zero_pocket)},
        {"metric": "primary_query_zero_pocket_rows", "value": str(primary_query_zero_pocket)},
        {"metric": "reference_rows_missing_overlap_metrics", "value": str(ref_missing_overlap)},
        {"metric": "primary_missing_png_rows", "value": str(primary_missing_png)},
        {"metric": "supporting_reference_has_better_pocket_overlap_rows", "value": str(better_overlap)},
        {"metric": "supporting_reference_has_higher_qtm_rows", "value": str(higher_qtm)},
        {"metric": "primary_path", "value": str(primary_path)},
        {"metric": "reference_panel_long_path", "value": str(reference_path)},
        {"metric": "pocket_residue_details_path", "value": str(residue_path)},
        {"metric": "data_dictionary_path", "value": str(dictionary_path)},
        {"metric": "readme_path", "value": str(readme_path)},
        {"metric": "export_timestamp", "value": timestamp},
    ]
    write_tsv(qc_path, qc_rows, ["metric", "value"])

    print("M15_USER_FACING_FINAL_EXPORTS_DONE")
    print(f"status\t{qc_status}")
    print(f"primary_rows\t{len(primary_rows)}")
    print(f"reference_panel_rows\t{len(reference_long)}")
    print(f"pocket_residue_detail_rows\t{len(residue_rows)}")
    print(f"primary_missing_overlap_rows\t{primary_missing_overlap}")
    print(f"reference_rows_missing_overlap_metrics\t{ref_missing_overlap}")
    print(f"primary_missing_png_rows\t{primary_missing_png}")
    print(f"primary_path\t{primary_path}")
    print(f"reference_panel_long_path\t{reference_path}")
    print(f"pocket_residue_details_path\t{residue_path}")
    print(f"qc\t{qc_path}")
    return 0 if qc_status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
