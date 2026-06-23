#!/usr/bin/env python3
"""M10H catalytic two-panel PNG prototype.

This prototype reuses the existing M10G structural/pocket renderer without
editing M10G. It generates one T2P001-style composite in an M10H output tree and
adds only optional catalytic marker pseudoatoms from precomputed M09R catalytic
visual manifests.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


FINAL_VERSION_TAG = "catalytic_v1"
HIDDEN_POLICIES = {"HIDE", "HIDDEN", "SUPPRESS", "SUPPRESSED", "DO_NOT_SHOW", "NONE"}


def load_m10g():
    path = Path(__file__).with_name("10g_generate_full_composite_figures.py")
    spec = importlib.util.spec_from_file_location("vermamg_m10g_composite", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load M10G module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def default_full_dir_from_contract(contract_path: Path) -> Path:
    # .../06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv
    if contract_path.parent.name == "input_manifests":
        return contract_path.parent.parent
    return contract_path.parent


def existing_m10g_png_path(contract_path: Path, query: str, family: str, m10g) -> Path:
    full_dir = default_full_dir_from_contract(contract_path)
    return full_dir / "composite_png" / "final_pngs" / f"{query}_{m10g.clean_label(family)}_v6_standard_600dpi.png"


def normalize_policy(value: str) -> str:
    return str(value or "").strip().upper()


def parse_visual_positions(value: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    text = str(value or "").replace(",", " ").replace(";", " ")
    for token in text.split():
        token = token.strip()
        if not token or token.upper() == "NA":
            continue
        if "_" in token:
            token = token.split("_")[-1]
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def unique_nonempty(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        if not value or value.upper() == "NA":
            continue
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def query_top1_pocket_overlap_status(overlap_count: int, pocket_count: int) -> str:
    if pocket_count == 0:
        return "NO_QUERY_TOP1_POCKET"
    if overlap_count == 0:
        return "NO_TOP1_P2RANK_POCKET_OVERLAP"
    return "TOP1_P2RANK_POCKET_OVERLAP_PRESENT"


def select_renderable_catalytic_rows(rows: list[dict[str, str]], query: str) -> tuple[list[dict[str, str]], int, int]:
    selected: list[dict[str, str]] = []
    caution_suppressed = 0
    secondary_suppressed = 0
    for row in rows:
        if row.get("query", "") != query:
            continue
        if normalize_policy(row.get("render_residue_on_query", "")) != "YES":
            continue
        if not str(row.get("query_position_for_visual", "")).strip():
            continue
        if not str(row.get("query_residue_for_visual", "")).strip():
            continue
        policy = normalize_policy(row.get("visual_show_policy", ""))
        if policy in HIDDEN_POLICIES or "HIDDEN" in policy or "HIDE" in policy:
            continue
        if policy == "SHOW_CAUTION" or row.get("default_png_layer", "") == "CAUTION":
            caution_suppressed += 1
            continue
        layer = normalize_policy(row.get("default_png_layer", ""))
        if not (policy == "SHOW_PRIMARY" or layer == "PRIMARY_CORE"):
            secondary_suppressed += 1
            continue
        selected.append(row)
    return selected, caution_suppressed, secondary_suppressed


def classify_catalytic_positions(rows: list[dict[str, str]]) -> tuple[list[str], list[str], list[dict[str, str]]]:
    query_positions: list[str] = []
    reference_positions: list[str] = []
    rendered_rows: list[dict[str, str]] = []
    query_seen: set[str] = set()
    reference_seen: set[str] = set()
    row_seen: set[tuple[str, str]] = set()
    for row in rows:
        q_positions = parse_visual_positions(row.get("query_position_for_visual", ""))
        r_positions = parse_visual_positions(row.get("target_position_for_visual", ""))
        for pos in q_positions:
            if pos not in query_seen:
                query_seen.add(pos)
                query_positions.append(pos)
        for pos in r_positions:
            if pos not in reference_seen:
                reference_seen.add(pos)
                reference_positions.append(pos)
        row_key = (str(row.get("query_position_for_visual", "")).strip(), str(row.get("target_position_for_visual", "")).strip())
        if row_key not in row_seen:
            row_seen.add(row_key)
            rendered_rows.append({
                "query": row.get("query", ""),
                "visual_row_id": row.get("visual_row_id", ""),
                "reference_id": row.get("reference_id", ""),
                "query_position_for_visual": row.get("query_position_for_visual", ""),
                "query_residue_for_visual": row.get("query_residue_for_visual", ""),
                "target_position_for_visual": row.get("target_position_for_visual", ""),
                "target_residue_for_visual": row.get("target_residue_for_visual", ""),
                "visual_show_policy": row.get("visual_show_policy", ""),
                "default_png_layer": row.get("default_png_layer", ""),
                "A10G_FIX2_role_class": row.get("A10G_FIX2_role_class", ""),
                "A10G_FIX2_role_refined_outcome": row.get("A10G_FIX2_role_refined_outcome", ""),
            })
    return query_positions, reference_positions, rendered_rows


def m10a_reference_id(row: dict[str, str]) -> str:
    return str(row.get("target", "") or row.get("primary_reference_target", "")).strip()


def select_m10a_contract_row(
    *,
    contract_path: Path,
    query: str,
    reference_selection_mode: str,
    catalytic_rows: list[dict[str, str]],
    m10g,
    limit: int | None,
) -> tuple[dict[str, str], str, str]:
    if reference_selection_mode == "displayed":
        primary_rows = [row for row in m10g.load_contract_primary(contract_path) if row.get("query", "") == query]
        if limit is not None:
            primary_rows = primary_rows[:limit]
        if not primary_rows:
            raise SystemExit(f"FATAL: query not found as PRIMARY row in M10A contract: {query}")
        row = primary_rows[0]
        return row, m10a_reference_id(row), "DISPLAYED_PRIMARY_ROW_SELECTED"

    annotation_reference_ids = unique_nonempty([row.get("reference_id", "") for row in catalytic_rows])
    if not annotation_reference_ids:
        raise SystemExit(f"FATAL: ANNOTATION_REFERENCE_ID_MISSING: query={query}")
    if len(annotation_reference_ids) != 1:
        raise SystemExit(
            "FATAL: ANNOTATION_REFERENCE_ID_AMBIGUOUS: "
            f"query={query} reference_ids={','.join(annotation_reference_ids)}"
        )

    annotation_reference_id = annotation_reference_ids[0]
    matches = [
        row
        for row in read_tsv(contract_path)
        if row.get("query", "") == query and m10a_reference_id(row) == annotation_reference_id
    ]
    if not matches:
        raise SystemExit(
            "FATAL: ANNOTATION_REFERENCE_M10A_ROW_NOT_FOUND: "
            f"query={query} annotation_reference_id={annotation_reference_id}"
        )
    return matches[0], annotation_reference_id, "ANNOTATION_REFERENCE_M10A_ROW_SELECTED"


def pymol_resi_selection(obj: str, positions: list[str]) -> str:
    if not positions:
        return "none"
    return f"{obj} and name CA and resi " + "+".join(positions)


def catalytic_setup_block(query_positions: list[str], reference_positions: list[str]) -> str:
    query_sel = pymol_resi_selection("query", query_positions)
    reference_sel = pymol_resi_selection("reference", reference_positions)
    return f'''
cmd.select("catalytic_query_core_ca", "{query_sel}")
cmd.select("catalytic_reference_core_ca", "{reference_sel}")

def make_catalytic_marker_object(selection, object_name):
    cmd.delete(object_name)
    model = cmd.get_model(selection)
    n = 0
    for atom in model.atom:
        if atom.name != "CA":
            continue
        n += 1
        cmd.pseudoatom(object_name, pos=atom.coord, name="CAT", resn="CAT", resi=str(n), chain="Z")
    if n == 0:
        cmd.select(object_name, "none")
    return n

catalytic_query_core_marker_n = make_catalytic_marker_object("catalytic_query_core_ca", "catalytic_query_core_markers")
catalytic_reference_core_marker_n = make_catalytic_marker_object("catalytic_reference_core_ca", "catalytic_reference_core_markers")
'''


def catalytic_panel_block(scale: str, marker_objects: list[str]) -> str:
    lines: list[str] = []
    for marker_object in marker_objects:
        lines.extend([
            f"show spheres, {marker_object}",
            f"color catalytic_red, {marker_object}",
            f"set sphere_scale, {scale}, {marker_object}",
            f"set sphere_transparency, 0.02, {marker_object}",
        ])
    return "\n".join(lines) + "\n"


def patch_pml_text(
    text: str,
    *,
    query_positions: list[str],
    reference_positions: list[str],
    include_reference_markers: bool,
    old_metrics_path: Path,
    new_metrics_path: Path,
) -> str:
    text = text.replace(old_metrics_path.as_posix(), new_metrics_path.as_posix())
    text = text.replace(
        'cmd.set_color("ghost_gray",        [0.82, 0.82, 0.82])',
        'cmd.set_color("ghost_gray",        [0.82, 0.82, 0.82])\n'
        'cmd.set_color("catalytic_red",     [1.00, 0.00, 0.00])',
    )
    out_lines: list[str] = []
    setup_inserted = False
    for line in text.splitlines():
        stripped = line.strip()
        marker_objects: list[str] = []
        if stripped.startswith("png ") and any(name in stripped for name in ("/a_left_query.png", "/b_left_query_pocket.png")):
            marker_objects = ["catalytic_query_core_markers"]
        elif include_reference_markers and stripped.startswith("png ") and any(name in stripped for name in ("/a_mid_reference.png", "/b_mid_reference_pocket.png")):
            marker_objects = ["catalytic_reference_core_markers"]
        elif stripped.startswith("png ") and any(name in stripped for name in ("/a_right_overlay.png", "/b_right_overlay_pocket.png")):
            marker_objects = ["catalytic_query_core_markers"]
            if include_reference_markers:
                marker_objects.append("catalytic_reference_core_markers")
        if marker_objects:
            scale = "1.24" if "/b_" in stripped else "0.82"
            out_lines.append(catalytic_panel_block(scale, marker_objects).rstrip("\n"))
        out_lines.append(line)
        if not setup_inserted and stripped.startswith('cmd.select("reference_pocket_ca",'):
            out_lines.append(catalytic_setup_block(query_positions, reference_positions).rstrip("\n"))
            setup_inserted = True
    return "\n".join(out_lines) + "\n"


def add_catalytic_legend_if_needed(path: Path, core_n: int, secondary_n: int, m10g) -> None:
    if core_n == 0:
        return
    m10g._require_pil()
    img = m10g.Image.open(path).convert("RGB")
    draw = m10g.ImageDraw.Draw(img)
    font_legend = m10g.get_font(27, False)
    items = [("circle", (255, 0, 0), "catalytic residue")]
    # Existing legend rows are at top_m+18 and top_m+72. Add one row below them.
    m10g.draw_legend_row(draw, img.size[0], 48 + 126, items, font_legend, marker=32, gap=64, x_min=90, x_max=90 + 2 * (1240 + 40) - 28)
    img.save(path, dpi=(600, 600))


def write_outputs(
    *,
    out_root: Path,
    manifest_rows: list[dict[str, str]],
    qc_rows: list[dict[str, str]],
) -> tuple[Path, Path]:
    manifest = out_root / "full_catalytic_two_panel_png_manifest.tsv"
    qc = out_root / "full_catalytic_two_panel_png_qc.tsv"
    manifest_fields = [
        "query",
        "family",
        "pml_path",
        "png_path",
        "rendered_residue_table_path",
        "existing_m10g_png_path",
        "displayed_reference_id",
        "reference_selection_mode",
        "selected_m10a_reference_id",
        "selected_m10a_row_status",
        "catalytic_manifest_reference_ids",
        "reference_marker_mode",
        "catalytic_annotation_rows_used",
        "primary_residue_n",
        "query_primary_marker_count",
        "reference_primary_marker_count",
        "suppressed_reference_marker_count",
        "query_top1_pocket_overlap_count",
        "query_top1_pocket_overlap_status",
        "secondary_residue_n",
        "caution_rows_suppressed",
        "render_status",
        "render_note",
    ]
    write_tsv(manifest, manifest_rows, manifest_fields)
    write_tsv(qc, qc_rows, ["metric", "value"])
    return manifest, qc


def write_catalytic_metrics(path: Path, rows: list[dict[str, str]]) -> None:
    write_tsv(path, rows, ["metric", "value"])


def write_rendered_residue_table(path: Path, rows: list[dict[str, str]]) -> None:
    write_tsv(
        path,
        rows,
        [
            "query",
            "visual_row_id",
            "reference_id",
            "query_position_for_visual",
            "query_residue_for_visual",
            "target_position_for_visual",
            "target_residue_for_visual",
            "visual_show_policy",
            "default_png_layer",
            "A10G_FIX2_role_class",
            "A10G_FIX2_role_refined_outcome",
            "query_marker_rendered",
            "reference_marker_rendered",
            "reference_marker_note",
        ],
    )


def promote_composite_png(src: Path, dst: Path) -> None:
    try:
        shutil.move(str(src), str(dst))
    except PermissionError:
        if not dst.exists():
            shutil.copy2(str(src), str(dst))
        try:
            src.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="M10H prototype: T2P001 catalytic two-panel PNG.")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--contract", default=None, help="M10A full_visual_overlay_input_contract.tsv")
    parser.add_argument("--decision-matrix", default=None, dest="decision_matrix")
    parser.add_argument("--pymol", default=None)
    parser.add_argument("--query", default="T2P001")
    parser.add_argument("--reference-selection-mode", choices=["displayed", "annotation"], default="displayed")
    parser.add_argument("--catalytic-visual-query-manifest", required=True)
    parser.add_argument("--catalytic-visual-annotation-manifest", required=True)
    parser.add_argument("--out-root", default=None)
    parser.add_argument("--pml-only", action="store_true")
    parser.add_argument("--compose-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-if-exists", action="store_true")
    args = parser.parse_args()

    if args.pml_only and args.compose_only:
        raise SystemExit("FATAL: --pml-only and --compose-only are mutually exclusive.")

    m10g = load_m10g()
    workspace = Path(args.workspace or os.environ.get("VERMAMG_ROOT", "") or ".").resolve()
    contract_path = Path(args.contract).resolve() if args.contract else workspace / m10g.CONTRACT_REL
    decision_path = Path(args.decision_matrix).resolve() if args.decision_matrix else workspace / m10g.DECISION_MATRIX_REL
    catalytic_query_path = Path(args.catalytic_visual_query_manifest).resolve()
    catalytic_annotation_path = Path(args.catalytic_visual_annotation_manifest).resolve()
    full_dir = default_full_dir_from_contract(contract_path)
    out_root = Path(args.out_root).resolve() if args.out_root else full_dir / "catalytic_two_panel_png"
    pymol_cmd = args.pymol or os.environ.get("PYMOL_CMD", "") or str(workspace / m10g.PYMOL_REL)

    for path in (contract_path, decision_path, catalytic_query_path, catalytic_annotation_path):
        if not path.exists():
            raise SystemExit(f"FATAL: required input not found: {path}")

    pml_dir = out_root / "pml"
    panel_dir = out_root / "panels"
    table_dir = out_root / "tables"
    log_dir = out_root / "logs"
    final_dir = out_root / "final_pngs"
    for directory in (out_root, pml_dir, panel_dir, table_dir, log_dir, final_dir):
        directory.mkdir(parents=True, exist_ok=True)

    catalytic_annotation_rows = read_tsv(catalytic_annotation_path)
    catalytic_rows, caution_suppressed, secondary_suppressed = select_renderable_catalytic_rows(catalytic_annotation_rows, args.query)
    row, selected_m10a_reference_id, selected_m10a_row_status = select_m10a_contract_row(
        contract_path=contract_path,
        query=args.query,
        reference_selection_mode=args.reference_selection_mode,
        catalytic_rows=catalytic_rows,
        m10g=m10g,
        limit=args.limit,
    )
    query = row["query"]
    family = row.get("family", "NA")
    dm_map = m10g.load_decision_matrix(decision_path)
    catalytic_query_rows = [r for r in read_tsv(catalytic_query_path) if r.get("query", "") == query]
    query_core_positions, reference_core_positions, rendered_residue_rows = classify_catalytic_positions(catalytic_rows)
    displayed_reference_id = m10a_reference_id(row)
    catalytic_manifest_reference_ids = unique_nonempty([r.get("reference_id", "") for r in catalytic_rows])
    reference_ids_text = ",".join(catalytic_manifest_reference_ids)
    reference_marker_mode = "DIRECT"
    if reference_core_positions and (len(catalytic_manifest_reference_ids) != 1 or catalytic_manifest_reference_ids[0] != displayed_reference_id):
        reference_marker_mode = "SUPPRESSED_REFERENCE_MISMATCH"
    reference_marker_positions = reference_core_positions if reference_marker_mode == "DIRECT" else []
    suppressed_reference_marker_count = len(reference_core_positions) - len(reference_marker_positions)
    reference_marker_note = (
        "REFERENCE_CATALYTIC_MARKERS_SUPPRESSED_REFERENCE_MISMATCH"
        if reference_marker_mode == "SUPPRESSED_REFERENCE_MISMATCH"
        else ""
    )
    query_top1_positions = [resi for _chain, resi in m10g.parse_residue_ids(row.get("query_top1_residue_ids", ""))]
    query_top1_position_set = set(query_top1_positions)
    query_top1_pocket_overlap_count = len(set(query_core_positions) & query_top1_position_set)
    query_top1_pocket_overlap = query_top1_pocket_overlap_status(query_top1_pocket_overlap_count, len(query_top1_position_set))
    rendered_residue_rows = [
        {
            **residue_row,
            "query_marker_rendered": "YES",
            "reference_marker_rendered": "YES" if reference_marker_mode == "DIRECT" else "NO",
            "reference_marker_note": reference_marker_note,
        }
        for residue_row in rendered_residue_rows
    ]

    desired_pml = pml_dir / f"{query}_{m10g.clean_label(family)}_{FINAL_VERSION_TAG}.pml"
    desired_metrics = table_dir / f"{query}_catalytic_metrics.tsv"
    rendered_residue_table = table_dir / f"{query}_catalytic_residues_rendered.tsv"
    desired_png = final_dir / f"{query}_{m10g.clean_label(family)}_{FINAL_VERSION_TAG}_600dpi.png"
    old_metrics = table_dir / f"{query}_metrics.tsv"
    existing_png = existing_m10g_png_path(contract_path, query, family, m10g)

    if args.skip_if_exists and desired_png.exists() and not args.pml_only:
        render_status = "SKIP_EXISTS"
        render_note = "Existing M10H catalytic PNG already present."
    else:
        render_status = "PENDING"
        render_note = ""

    if not args.compose_only and render_status != "SKIP_EXISTS":
        generated_pml, err, _has_query_pocket = m10g.write_pml(row, dm_map, workspace, panel_dir, table_dir, pml_dir)
        if err:
            raise SystemExit(f"FATAL: M10G-equivalent PML preparation failed: {err}")
        patched = patch_pml_text(
            generated_pml.read_text(encoding="utf-8", errors="replace"),
            query_positions=query_core_positions,
            reference_positions=reference_marker_positions,
            include_reference_markers=(reference_marker_mode == "DIRECT"),
            old_metrics_path=old_metrics,
            new_metrics_path=desired_metrics,
        )
        desired_pml.write_text(patched, encoding="utf-8")
        if generated_pml != desired_pml and generated_pml.exists():
            try:
                generated_pml.unlink()
            except OSError:
                pass
        render_status = "PML_ONLY" if args.pml_only else "PML_READY"
        render_note = "PML generated; PyMOL/rendering not run." if args.pml_only else "PML generated."

    if args.compose_only and render_status != "SKIP_EXISTS":
        metrics = m10g.read_metrics(desired_metrics)
        standard_png = m10g.compose_figure(
            query,
            family,
            metrics,
            out_root,
            panel_dir,
            has_query_pocket=bool(m10g.parse_residue_ids(row.get("query_top1_residue_ids", ""))),
            has_reference_pocket=m10g.has_reliable_reference_pocket(row),
        )
        promote_composite_png(standard_png, desired_png)
        add_catalytic_legend_if_needed(desired_png, len(query_core_positions), 0, m10g)
        render_status = "COMPOSE_ONLY"
        render_note = "Composed from existing panel PNGs; PyMOL not run."

    if not args.pml_only and not args.compose_only and render_status not in {"SKIP_EXISTS", "PENDING"}:
        log_path = log_dir / f"{query}.pymol.log"
        try:
            with log_path.open("w", encoding="utf-8") as log_handle:
                subprocess.run(
                    [pymol_cmd, "-cq", str(desired_pml)],
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    check=True,
                    env={**os.environ, "VERMAMG_ROOT": str(workspace)},
                )
            metrics = m10g.read_metrics(desired_metrics)
            standard_png = m10g.compose_figure(
                query,
                family,
                metrics,
                out_root,
                panel_dir,
                has_query_pocket=bool(m10g.parse_residue_ids(row.get("query_top1_residue_ids", ""))),
                has_reference_pocket=m10g.has_reliable_reference_pocket(row),
            )
            promote_composite_png(standard_png, desired_png)
            add_catalytic_legend_if_needed(desired_png, len(query_core_positions), 0, m10g)
            render_status = "PASS"
            render_note = "PyMOL render and PIL composition completed."
        except Exception as exc:
            render_status = "FAIL"
            render_note = f"Render/compose failed: {exc}"

    if not catalytic_query_rows:
        catalytic_class = "MISSING_QUERY_MANIFEST_ROW"
    else:
        catalytic_class = catalytic_query_rows[0].get("A10G_FIX2_final_catalytic_layer_class", "")

    png_path_current_run = ""
    if render_status in {"PASS", "COMPOSE_ONLY", "SKIP_EXISTS"} and desired_png.exists():
        png_path_current_run = str(desired_png)

    manifest_rows = [{
        "query": query,
        "family": family,
        "pml_path": str(desired_pml),
        "png_path": png_path_current_run,
        "rendered_residue_table_path": str(rendered_residue_table),
        "existing_m10g_png_path": str(existing_png),
        "displayed_reference_id": displayed_reference_id,
        "reference_selection_mode": args.reference_selection_mode,
        "selected_m10a_reference_id": selected_m10a_reference_id,
        "selected_m10a_row_status": selected_m10a_row_status,
        "catalytic_manifest_reference_ids": reference_ids_text,
        "reference_marker_mode": reference_marker_mode,
        "catalytic_annotation_rows_used": str(len(catalytic_rows)),
        "primary_residue_n": str(len(query_core_positions)),
        "query_primary_marker_count": str(len(query_core_positions)),
        "reference_primary_marker_count": str(len(reference_marker_positions)),
        "suppressed_reference_marker_count": str(suppressed_reference_marker_count),
        "query_top1_pocket_overlap_count": str(query_top1_pocket_overlap_count),
        "query_top1_pocket_overlap_status": query_top1_pocket_overlap,
        "secondary_residue_n": "0",
        "caution_rows_suppressed": str(caution_suppressed),
        "render_status": render_status,
        "render_note": render_note,
    }]
    qc_rows = [
        {"metric": "module", "value": "10h_generate_catalytic_two_panel_figures"},
        {"metric": "prototype_scope", "value": "single_query"},
        {"metric": "query", "value": query},
        {"metric": "family", "value": family},
        {"metric": "catalytic_class", "value": catalytic_class},
        {"metric": "existing_m10g_png_path", "value": str(existing_png)},
        {"metric": "new_m10h_png_path", "value": str(desired_png)},
        {"metric": "displayed_reference_id", "value": displayed_reference_id},
        {"metric": "reference_selection_mode", "value": args.reference_selection_mode},
        {"metric": "selected_m10a_reference_id", "value": selected_m10a_reference_id},
        {"metric": "selected_m10a_row_status", "value": selected_m10a_row_status},
        {"metric": "catalytic_manifest_reference_ids", "value": reference_ids_text},
        {"metric": "reference_marker_mode", "value": reference_marker_mode},
        {"metric": "reference_marker_qc_note", "value": reference_marker_note},
        {"metric": "catalytic_annotation_rows_used", "value": str(len(catalytic_rows))},
        {"metric": "primary_residue_n", "value": str(len(query_core_positions))},
        {"metric": "query_primary_marker_count", "value": str(len(query_core_positions))},
        {"metric": "reference_primary_residue_n", "value": str(len(reference_marker_positions))},
        {"metric": "reference_primary_marker_count", "value": str(len(reference_marker_positions))},
        {"metric": "suppressed_reference_marker_count", "value": str(suppressed_reference_marker_count)},
        {"metric": "query_top1_pocket_overlap_count", "value": str(query_top1_pocket_overlap_count)},
        {"metric": "query_top1_pocket_overlap_status", "value": query_top1_pocket_overlap},
        {"metric": "secondary_residue_n", "value": "0"},
        {"metric": "secondary_rows_suppressed", "value": str(secondary_suppressed)},
        {"metric": "caution_rows_suppressed", "value": str(caution_suppressed)},
        {"metric": "render_status", "value": render_status},
        {"metric": "render_note", "value": render_note},
        {"metric": "biological_logic_recomputed", "value": "NO"},
        {"metric": "catalytic_overlay_note", "value": "Catalytic overlay is identity-level/pre-geometry; top1 P2Rank pocket overlap is not required or validated."},
    ]
    catalytic_metric_rows = [
        {"metric": "query", "value": query},
        {"metric": "family", "value": family},
        {"metric": "catalytic_class", "value": catalytic_class},
        {"metric": "displayed_reference_id", "value": displayed_reference_id},
        {"metric": "reference_selection_mode", "value": args.reference_selection_mode},
        {"metric": "selected_m10a_reference_id", "value": selected_m10a_reference_id},
        {"metric": "selected_m10a_row_status", "value": selected_m10a_row_status},
        {"metric": "catalytic_manifest_reference_ids", "value": reference_ids_text},
        {"metric": "reference_marker_mode", "value": reference_marker_mode},
        {"metric": "reference_marker_qc_note", "value": reference_marker_note},
        {"metric": "catalytic_annotation_rows_used", "value": str(len(catalytic_rows))},
        {"metric": "primary_residue_n", "value": str(len(query_core_positions))},
        {"metric": "query_primary_marker_count", "value": str(len(query_core_positions))},
        {"metric": "reference_primary_residue_n", "value": str(len(reference_marker_positions))},
        {"metric": "reference_primary_marker_count", "value": str(len(reference_marker_positions))},
        {"metric": "suppressed_reference_marker_count", "value": str(suppressed_reference_marker_count)},
        {"metric": "query_top1_pocket_overlap_count", "value": str(query_top1_pocket_overlap_count)},
        {"metric": "query_top1_pocket_overlap_status", "value": query_top1_pocket_overlap},
        {"metric": "secondary_residue_n", "value": "0"},
        {"metric": "secondary_rows_suppressed", "value": str(secondary_suppressed)},
        {"metric": "caution_rows_suppressed", "value": str(caution_suppressed)},
        {"metric": "render_status", "value": render_status},
        {"metric": "render_note", "value": render_note},
        {"metric": "biological_logic_recomputed", "value": "NO"},
        {"metric": "existing_m10g_png_path", "value": str(existing_png)},
        {"metric": "new_m10h_png_path", "value": str(desired_png)},
        {"metric": "rendered_residue_table_path", "value": str(rendered_residue_table)},
        {"metric": "catalytic_overlay_note", "value": "Catalytic overlay is identity-level/pre-geometry; top1 P2Rank pocket overlap is not required or validated."},
    ]
    write_catalytic_metrics(desired_metrics, catalytic_metric_rows)
    write_rendered_residue_table(rendered_residue_table, rendered_residue_rows)
    manifest_path, qc_path = write_outputs(out_root=out_root, manifest_rows=manifest_rows, qc_rows=qc_rows)

    print("M10H_CATALYTIC_TWO_PANEL_PROTOTYPE")
    print(f"query\t{query}")
    print(f"family\t{family}")
    print(f"existing_m10g_png\t{existing_png}")
    print(f"new_m10h_png\t{png_path_current_run if png_path_current_run else 'NOT_RENDERED'}")
    print(f"pml\t{desired_pml}")
    print(f"metrics\t{desired_metrics}")
    print(f"rendered_residue_table\t{rendered_residue_table}")
    print(f"displayed_reference_id\t{displayed_reference_id}")
    print(f"reference_selection_mode\t{args.reference_selection_mode}")
    print(f"selected_m10a_reference_id\t{selected_m10a_reference_id}")
    print(f"selected_m10a_row_status\t{selected_m10a_row_status}")
    print(f"catalytic_manifest_reference_ids\t{reference_ids_text}")
    print(f"reference_marker_mode\t{reference_marker_mode}")
    print(f"catalytic_annotation_rows_used\t{len(catalytic_rows)}")
    print(f"primary_residue_n\t{len(query_core_positions)}")
    print(f"query_primary_marker_count\t{len(query_core_positions)}")
    print(f"reference_primary_marker_count\t{len(reference_marker_positions)}")
    print(f"suppressed_reference_marker_count\t{suppressed_reference_marker_count}")
    print(f"query_top1_pocket_overlap_count\t{query_top1_pocket_overlap_count}")
    print(f"query_top1_pocket_overlap_status\t{query_top1_pocket_overlap}")
    print("secondary_residue_n\t0")
    print(f"secondary_rows_suppressed\t{secondary_suppressed}")
    print(f"caution_rows_suppressed\t{caution_suppressed}")
    print(f"render_status\t{render_status}")
    print(f"manifest\t{manifest_path}")
    print(f"qc\t{qc_path}")

    return 0 if render_status != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
