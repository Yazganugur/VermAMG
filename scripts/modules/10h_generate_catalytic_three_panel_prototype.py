"""M10H catalytic three-panel prototype.

This isolated prototype keeps the existing M10H two-panel script unchanged.
It reuses M10G PML generation and M10H catalytic row-selection helpers, then
adds a prototype catalytic-site zoom row before composing a 3 x 3 figure:

Panel A: fold overview
Panel B: catalytic-site zoom
Panel C: P2Rank pocket context
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


FINAL_VERSION_TAG = "catalytic_three_panel_prototype_v1"


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_m10h():
    return load_module(Path(__file__).with_name("10h_generate_catalytic_two_panel_figures.py"), "m10h_two_panel")


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_tsv(path: Path, row: dict[str, str], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def upsert_tsv(path: Path, row: dict[str, str], fields: list[str], key: str = "query") -> None:
    rows: list[dict[str, str]] = []
    if path.exists() and path.stat().st_size > 0:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
    rows = [old for old in rows if old.get(key, "") != row.get(key, "")]
    rows.append(row)
    write_tsv(path, rows, fields)


def write_design_audit(out_root: Path) -> Path:
    path = out_root / "three_panel_prototype_design_audit.tsv"
    fields = [
        "audit_section",
        "panel_id",
        "panel_name",
        "layout_role",
        "existing_panel_pngs_reused",
        "new_render_required",
        "prototype_panel_pngs",
        "minimum_change_location",
        "backward_compatibility_note",
        "notes",
    ]
    rows = [
        {
            "audit_section": "current_m10h_flow",
            "panel_id": "NA",
            "panel_name": "Existing two-panel flow",
            "layout_role": "M10G renders a_* overview and b_* pocket-context panel PNGs; M10H injects catalytic marker pseudoatoms and composes with M10G compose_figure.",
            "existing_panel_pngs_reused": "a_left_query.png;a_mid_reference.png;a_right_overlay.png;b_left_query_pocket.png;b_mid_reference_pocket.png;b_right_overlay_pocket.png",
            "new_render_required": "NO_FOR_EXISTING_TWO_PANEL",
            "prototype_panel_pngs": "NA",
            "minimum_change_location": "Separate prototype script; no edit to M10H/M10G/M10A.",
            "backward_compatibility_note": "Existing two-panel behavior remains untouched.",
            "notes": "Prototype calls M10G write_pml and M10H reference-selection helpers.",
        },
        {
            "audit_section": "mock_layout_plan",
            "panel_id": "A",
            "panel_name": "Fold overview",
            "layout_role": "Row A: query, reference, overlay overview.",
            "existing_panel_pngs_reused": "YES",
            "new_render_required": "NO",
            "prototype_panel_pngs": "a_left_query.png;a_mid_reference.png;a_right_overlay.png",
            "minimum_change_location": "Reuse current M10G overview snapshots after M10H catalytic marker injection.",
            "backward_compatibility_note": "No change to existing M10H two-panel compose.",
            "notes": "Closest to current general-view logic.",
        },
        {
            "audit_section": "mock_layout_plan",
            "panel_id": "B",
            "panel_name": "Catalytic-site zoom",
            "layout_role": "Row B: query, reference, overlay focused on catalytic residues.",
            "existing_panel_pngs_reused": "NO",
            "new_render_required": "YES",
            "prototype_panel_pngs": "c_left_catalytic_zoom.png;c_mid_catalytic_zoom.png;c_right_catalytic_zoom.png",
            "minimum_change_location": "Inject three extra PyMOL png snapshots into the M10G-generated PML.",
            "backward_compatibility_note": "New snapshots are written only under the prototype out-root.",
            "notes": "Pocket residue spheres are not shown; red catalytic markers are the main emphasis.",
        },
        {
            "audit_section": "mock_layout_plan",
            "panel_id": "C",
            "panel_name": "Pocket context",
            "layout_role": "Row C: query, reference, overlay pocket context.",
            "existing_panel_pngs_reused": "YES",
            "new_render_required": "NO",
            "prototype_panel_pngs": "b_left_query_pocket.png;b_mid_reference_pocket.png;b_right_overlay_pocket.png",
            "minimum_change_location": "Reuse existing M10G pocket-context snapshots with catalytic markers overlaid.",
            "backward_compatibility_note": "No change to existing M10H two-panel compose.",
            "notes": "Muted pocket region and P2Rank spheres remain visible as supporting context.",
        },
        {
            "audit_section": "implementation_choice",
            "panel_id": "NA",
            "panel_name": "Isolated prototype",
            "layout_role": "Small backward-compatible application.",
            "existing_panel_pngs_reused": "YES",
            "new_render_required": "YES_FOR_PANEL_B",
            "prototype_panel_pngs": "final_pngs/*_catalytic_three_panel_prototype_v1_600dpi.png",
            "minimum_change_location": "scripts/modules/10h_generate_catalytic_three_panel_prototype.py",
            "backward_compatibility_note": "M10H two-panel default and previous outputs are not overwritten.",
            "notes": "This is a prototype for T2P278 and T2P054 only.",
        },
    ]
    write_tsv(path, rows, fields)
    return path


def marker_block(scale: str, marker_objects: list[str]) -> str:
    lines: list[str] = []
    for marker_object in marker_objects:
        lines.extend(
            [
                f"show spheres, {marker_object}",
                f"color catalytic_red, {marker_object}",
                f"set sphere_scale, {scale}, {marker_object}",
                f"set sphere_transparency, 0.02, {marker_object}",
            ]
        )
    return "\n".join(lines) + "\n"


def catalytic_zoom_panels_block(panel_subdir: Path, include_reference_markers: bool) -> str:
    reference_marker_lines = ""
    overlay_reference_marker_lines = ""
    if include_reference_markers:
        reference_marker_lines = marker_block("1.46", ["catalytic_reference_core_markers"])
        overlay_reference_marker_lines = marker_block("1.36", ["catalytic_reference_core_markers"])
    return f"""
# --- c_left: query catalytic zoom -----------------------------------------
scene full_view, recall
hide everything
show cartoon, query
color ghost_gray, query
set cartoon_transparency, 0.72, query
{marker_block("1.46", ["catalytic_query_core_markers"]).rstrip()}
python
if cmd.count_atoms("catalytic_query_core_ca") > 0:
    cmd.zoom("catalytic_query_core_ca", 5.2, complete=1)
python end
png {panel_subdir.as_posix()}/c_left_catalytic_zoom.png, width=2600, height=1900, dpi=600, ray=1

# --- c_mid: reference catalytic zoom --------------------------------------
scene full_view, recall
hide everything
show cartoon, reference
color ghost_gray, reference
set cartoon_transparency, 0.72, reference
{reference_marker_lines.rstrip()}
python
if cmd.count_atoms("catalytic_reference_core_ca") > 0:
    cmd.zoom("catalytic_reference_core_ca", 5.2, complete=1)
python end
png {panel_subdir.as_posix()}/c_mid_catalytic_zoom.png, width=2600, height=1900, dpi=600, ray=1

# --- c_right: catalytic overlay zoom --------------------------------------
scene full_view, recall
hide everything
show cartoon, query
show cartoon, reference
color query_cyan, query
color ref_gray, reference
set cartoon_transparency, 0.16, reference
set cartoon_transparency, 0.34, query
{marker_block("1.36", ["catalytic_query_core_markers"]).rstrip()}
{overlay_reference_marker_lines.rstrip()}
python
if cmd.count_atoms("catalytic_query_core_ca or catalytic_reference_core_ca") > 0:
    cmd.zoom("catalytic_query_core_ca or catalytic_reference_core_ca", 5.4, complete=1)
python end
png {panel_subdir.as_posix()}/c_right_catalytic_zoom.png, width=2600, height=1900, dpi=600, ray=1
"""


def patch_three_panel_pml_text(
    text: str,
    *,
    m10h,
    query_positions: list[str],
    reference_positions: list[str],
    include_reference_markers: bool,
    old_metrics_path: Path,
    new_metrics_path: Path,
    panel_subdir: Path,
) -> str:
    text = text.replace(old_metrics_path.as_posix(), new_metrics_path.as_posix())
    text = text.replace(
        'cmd.set_color("ghost_gray",        [0.82, 0.82, 0.82])',
        'cmd.set_color("ghost_gray",        [0.82, 0.82, 0.82])\n'
        'cmd.set_color("catalytic_red",     [1.00, 0.00, 0.00])',
    )

    out_lines: list[str] = []
    setup_inserted = False
    catalytic_zoom_inserted = False
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
            out_lines.append(marker_block(scale, marker_objects).rstrip("\n"))

        out_lines.append(line)

        if not setup_inserted and stripped.startswith('cmd.select("reference_pocket_ca",'):
            out_lines.append(
                m10h.catalytic_setup_block(query_positions, reference_positions).rstrip("\n")
            )
            setup_inserted = True

        if (
            not catalytic_zoom_inserted
            and stripped.startswith("png ")
            and "/a_right_overlay.png" in stripped
        ):
            out_lines.append(
                catalytic_zoom_panels_block(panel_subdir, include_reference_markers).rstrip("\n")
            )
            catalytic_zoom_inserted = True

    return "\n".join(out_lines) + "\n"


def placeholder_panel(m10g, title: str, sub: str, panel_w: int, panel_h: int):
    return m10g.make_placeholder_panel(title, panel_w, panel_h, sub=sub)


def load_three_panel_images(m10g, panel_dir: Path, query: str, has_query_pocket: bool, has_reference_pocket: bool):
    m10g._require_pil()
    pd = panel_dir / query
    panel_w, panel_h = 1100, 780
    paths = {
        "a_left": pd / "a_left_query.png",
        "a_mid": pd / "a_mid_reference.png",
        "a_right": pd / "a_right_overlay.png",
        "c_left": pd / "c_left_catalytic_zoom.png",
        "c_mid": pd / "c_mid_catalytic_zoom.png",
        "c_right": pd / "c_right_catalytic_zoom.png",
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise RuntimeError("Missing required overview/catalytic panel files: " + "; ".join(missing))

    panels = {
        "a_left": m10g.fit_panel(m10g.Image.open(paths["a_left"]).convert("RGB"), panel_w, panel_h, crop=True),
        "a_mid": m10g.fit_panel(m10g.Image.open(paths["a_mid"]).convert("RGB"), panel_w, panel_h, crop=True),
        "a_right": m10g.fit_panel(m10g.Image.open(paths["a_right"]).convert("RGB"), panel_w, panel_h, crop=True),
    }

    c_imgs = m10g.shared_crop_white(
        [
            m10g.Image.open(paths["c_left"]).convert("RGB"),
            m10g.Image.open(paths["c_mid"]).convert("RGB"),
            m10g.Image.open(paths["c_right"]).convert("RGB"),
        ],
        pad=85,
    )
    panels["c_left"] = m10g.fit_panel(c_imgs[0], panel_w, panel_h, crop=False)
    panels["c_mid"] = m10g.fit_panel(c_imgs[1], panel_w, panel_h, crop=False)
    panels["c_right"] = m10g.fit_panel(c_imgs[2], panel_w, panel_h, crop=False)

    if has_query_pocket:
        b_paths = {
            "b_left": pd / "b_left_query_pocket.png",
            "b_mid": pd / "b_mid_reference_pocket.png",
            "b_right": pd / "b_right_overlay_pocket.png",
        }
        required_b = ["b_left", "b_mid", "b_right"] if has_reference_pocket else ["b_left"]
        missing_b = [str(b_paths[key]) for key in required_b if not b_paths[key].exists()]
        if missing_b:
            raise RuntimeError("Missing required pocket panel files: " + "; ".join(missing_b))
        b_left = m10g.Image.open(b_paths["b_left"]).convert("RGB")
        if has_reference_pocket:
            b_imgs = m10g.shared_crop_white(
                [
                    b_left,
                    m10g.Image.open(b_paths["b_mid"]).convert("RGB"),
                    m10g.Image.open(b_paths["b_right"]).convert("RGB"),
                ],
                pad=85,
            )
            panels["b_left"] = m10g.fit_panel(b_imgs[0], panel_w, panel_h, crop=False)
            panels["b_mid"] = m10g.fit_panel(b_imgs[1], panel_w, panel_h, crop=False)
            panels["b_right"] = m10g.fit_panel(b_imgs[2], panel_w, panel_h, crop=False)
        else:
            panels["b_left"] = m10g.fit_panel(m10g.crop_white(b_left, pad=85), panel_w, panel_h, crop=False)
            panels["b_mid"] = placeholder_panel(m10g, "No reliable reference pocket", "Reference P2Rank zero-pocket", panel_w, panel_h)
            panels["b_right"] = placeholder_panel(m10g, "No reliable pocket overlap", "reference pocket unavailable", panel_w, panel_h)
    else:
        panels["b_left"] = placeholder_panel(m10g, "No query pocket predicted", "P2Rank found no significant pocket", panel_w, panel_h)
        panels["b_mid"] = placeholder_panel(m10g, "No reliable reference pocket", "no query pocket to compare", panel_w, panel_h)
        panels["b_right"] = placeholder_panel(m10g, "No pocket overlap", "no query pocket to compare", panel_w, panel_h)

    return panels, panel_w, panel_h


def compose_three_panel_figure(
    *,
    m10g,
    query: str,
    family: str,
    metrics: dict[str, str],
    out_root: Path,
    panel_dir: Path,
    has_query_pocket: bool,
    has_reference_pocket: bool,
    catalytic_summary: dict[str, str],
) -> Path:
    panels, panel_w, panel_h = load_three_panel_images(m10g, panel_dir, query, has_query_pocket, has_reference_pocket)
    Image = m10g.Image
    ImageDraw = m10g.ImageDraw

    left_m, right_m = 88, 88
    top_m, bot_m = 46, 92
    col_gap, row_gap = 38, 54
    legend_band = 276
    row_label_band = 42
    header_band = 38

    fig_w = left_m + 3 * panel_w + 2 * col_gap + right_m
    fig_h = (
        top_m
        + legend_band
        + 3 * (row_label_band + header_band + panel_h)
        + 2 * row_gap
        + bot_m
    )
    canvas = Image.new("RGB", (fig_w, fig_h), "white")
    draw = ImageDraw.Draw(canvas)

    font_title = m10g.get_font(34, True)
    font_letter = m10g.get_font(38, True)
    font_header = m10g.get_font(27, True)
    font_legend = m10g.get_font(24, False)
    font_score = m10g.get_font(21, False)
    font_score_bold = m10g.get_font(21, True)
    font_small = m10g.get_font(19, False)

    x1 = left_m
    x2 = left_m + panel_w + col_gap
    x3 = left_m + 2 * (panel_w + col_gap)
    col_x = [x1, x2, x3]

    y_legend = top_m
    row_a_label = y_legend + legend_band
    row_a_header = row_a_label + row_label_band
    row_a_panel = row_a_header + header_band
    row_b_label = row_a_panel + panel_h + row_gap
    row_b_header = row_b_label + row_label_band
    row_b_panel = row_b_header + header_band
    row_c_label = row_b_panel + panel_h + row_gap
    row_c_header = row_c_label + row_label_band
    row_c_panel = row_c_header + header_band

    draw.text((left_m, y_legend + 6), f"{query} | {family} | catalytic three-panel prototype", fill="black", font=font_title)

    m10g.draw_legend_row(
        draw,
        fig_w,
        y_legend + 62,
        [
            ("rect", (0, 199, 224), "Query protein"),
            ("rect", (158, 158, 158), "Reference"),
            ("circle", (255, 0, 0), "Catalytic residue"),
        ],
        font_legend,
        marker=30,
        gap=62,
        x_min=left_m,
        x_max=x3 - 24,
    )
    m10g.draw_legend_row(
        draw,
        fig_w,
        y_legend + 112,
        [
            ("circle", (255, 219, 0), "Shared pocket position"),
            ("circle", (255, 82, 10), "Query-specific pocket position"),
            ("circle", (13, 89, 255), "Reference-specific pocket position"),
        ],
        font_legend,
        marker=30,
        gap=54,
        x_min=left_m,
        x_max=x3 - 24,
    )

    box_w = 750
    box_h = 166
    bx2 = x3 + panel_w
    bx1 = bx2 - box_w
    by1 = y_legend + 52
    draw.rounded_rectangle([bx1, by1, bx2, by1 + box_h], radius=14, fill=(255, 255, 255), outline=(130, 130, 130), width=2)
    score_lines = [
        ("qTMscore", metrics.get("qtm_score", "NA")),
        ("RMSD", metrics.get("rmsd", "NA")),
        ("P2Rank Q/R", f"{metrics.get('query_p2rank', 'NA')} / {metrics.get('reference_p2rank', 'NA')}"),
        ("Catalytic markers Q/R", f"{catalytic_summary.get('query_primary_marker_count', 'NA')} / {catalytic_summary.get('reference_primary_marker_count', 'NA')}"),
    ]
    yy = by1 + 16
    for label, value in score_lines:
        draw.text((bx1 + 16, yy), f"{label}:", fill="black", font=font_score_bold)
        draw.text((bx1 + 310, yy), str(value), fill=(30, 30, 30), font=font_score)
        yy += 34

    row_specs = [
        ("A", "Fold overview", row_a_label, row_a_header, row_a_panel, ["a_left", "a_mid", "a_right"]),
        ("B", "Catalytic-site zoom", row_b_label, row_b_header, row_b_panel, ["c_left", "c_mid", "c_right"]),
        ("C", "Pocket context", row_c_label, row_c_header, row_c_panel, ["b_left", "b_mid", "b_right"]),
    ]
    border_col = (232, 232, 232)
    for letter, label, y_label, y_header, y_panel, keys in row_specs:
        draw.text((30, y_label - 1), letter, fill="black", font=font_letter)
        draw.text((left_m, y_label + 6), label, fill=(30, 30, 30), font=font_header)
        for x, txt in zip(col_x, ["Query", "Reference", "Overlay"]):
            draw.text((x, y_header + 2), txt, fill="black", font=font_header)
        for x, key in zip(col_x, keys):
            canvas.paste(panels[key], (x, y_panel))
            draw.rectangle([x, y_panel, x + panel_w, y_panel + panel_h], outline=border_col, width=2)

    caption = (
        f"Reference selection: {catalytic_summary.get('reference_selection_mode', 'NA')} | "
        f"selected reference: {catalytic_summary.get('selected_m10a_reference_id', 'NA')} | "
        f"reference marker mode: {catalytic_summary.get('reference_marker_mode', 'NA')} | "
        f"top1 catalytic overlap: {catalytic_summary.get('query_top1_pocket_overlap_count', 'NA')}"
    )
    draw.text((left_m, fig_h - 48), caption, fill=(70, 70, 70), font=font_small)

    final_dir = out_root / "final_pngs"
    final_dir.mkdir(parents=True, exist_ok=True)
    out = final_dir / f"{query}_{m10g.clean_label(family)}_{FINAL_VERSION_TAG}_600dpi.png"
    canvas.save(out, dpi=(600, 600))
    return out


def promote_pml(generated_pml: Path, desired_pml: Path, patched_text: str) -> None:
    desired_pml.write_text(patched_text, encoding="utf-8")
    if generated_pml != desired_pml and generated_pml.exists():
        try:
            generated_pml.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="M10H catalytic three-panel prototype.")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--contract", default=None, help="M10A full_visual_overlay_input_contract.tsv")
    parser.add_argument("--decision-matrix", default=None, dest="decision_matrix")
    parser.add_argument("--pymol", default=None)
    parser.add_argument("--query", required=True)
    parser.add_argument("--reference-selection-mode", choices=["displayed", "annotation"], default="displayed")
    parser.add_argument("--catalytic-visual-query-manifest", required=True)
    parser.add_argument("--catalytic-visual-annotation-manifest", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--pml-only", action="store_true")
    parser.add_argument("--compose-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-if-exists", action="store_true")
    args = parser.parse_args()

    if args.pml_only and args.compose_only:
        raise SystemExit("FATAL: --pml-only and --compose-only are mutually exclusive.")

    m10h = load_m10h()
    m10g = m10h.load_m10g()
    workspace = Path(args.workspace or os.environ.get("VERMAMG_ROOT", "") or ".").resolve()
    contract_path = Path(args.contract).resolve() if args.contract else workspace / m10g.CONTRACT_REL
    decision_path = Path(args.decision_matrix).resolve() if args.decision_matrix else workspace / m10g.DECISION_MATRIX_REL
    catalytic_query_path = Path(args.catalytic_visual_query_manifest).resolve()
    catalytic_annotation_path = Path(args.catalytic_visual_annotation_manifest).resolve()
    out_root = Path(args.out_root).resolve()
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

    design_audit = write_design_audit(out_root)

    catalytic_annotation_rows = m10h.read_tsv(catalytic_annotation_path)
    catalytic_rows, caution_suppressed, secondary_suppressed = m10h.select_renderable_catalytic_rows(catalytic_annotation_rows, args.query)
    row, selected_m10a_reference_id, selected_m10a_row_status = m10h.select_m10a_contract_row(
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
    catalytic_query_rows = [r for r in m10h.read_tsv(catalytic_query_path) if r.get("query", "") == query]
    query_core_positions, reference_core_positions, rendered_residue_rows = m10h.classify_catalytic_positions(catalytic_rows)
    displayed_reference_id = m10h.m10a_reference_id(row)
    catalytic_manifest_reference_ids = m10h.unique_nonempty([r.get("reference_id", "") for r in catalytic_rows])
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
    query_top1_pocket_overlap = m10h.query_top1_pocket_overlap_status(query_top1_pocket_overlap_count, len(query_top1_position_set))
    has_query_pocket = bool(m10g.parse_residue_ids(row.get("query_top1_residue_ids", "")))
    has_reference_pocket = m10g.has_reliable_reference_pocket(row)

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
    standard_metrics = table_dir / f"{query}_three_panel_standard_metrics.tsv"
    catalytic_metrics = table_dir / f"{query}_three_panel_catalytic_metrics.tsv"
    rendered_residue_table = table_dir / f"{query}_three_panel_catalytic_residues_rendered.tsv"
    desired_png = final_dir / f"{query}_{m10g.clean_label(family)}_{FINAL_VERSION_TAG}_600dpi.png"
    old_metrics = table_dir / f"{query}_metrics.tsv"
    existing_png = m10h.existing_m10g_png_path(contract_path, query, family, m10g)

    if args.skip_if_exists and desired_png.exists() and not args.pml_only:
        render_status = "SKIP_EXISTS"
        render_note = "Existing M10H three-panel prototype PNG already present."
    else:
        render_status = "PENDING"
        render_note = ""

    if not args.compose_only and render_status != "SKIP_EXISTS":
        generated_pml, err, _has_query_pocket = m10g.write_pml(row, dm_map, workspace, panel_dir, table_dir, pml_dir)
        if err:
            raise SystemExit(f"FATAL: M10G-equivalent PML preparation failed: {err}")
        patched = patch_three_panel_pml_text(
            generated_pml.read_text(encoding="utf-8", errors="replace"),
            m10h=m10h,
            query_positions=query_core_positions,
            reference_positions=reference_marker_positions,
            include_reference_markers=(reference_marker_mode == "DIRECT"),
            old_metrics_path=old_metrics,
            new_metrics_path=standard_metrics,
            panel_subdir=panel_dir / query,
        )
        promote_pml(generated_pml, desired_pml, patched)
        render_status = "PML_ONLY" if args.pml_only else "PML_READY"
        render_note = "PML generated; PyMOL/rendering not run." if args.pml_only else "PML generated."

    catalytic_summary = {
        "reference_selection_mode": args.reference_selection_mode,
        "selected_m10a_reference_id": selected_m10a_reference_id,
        "selected_m10a_row_status": selected_m10a_row_status,
        "reference_marker_mode": reference_marker_mode,
        "query_primary_marker_count": str(len(query_core_positions)),
        "reference_primary_marker_count": str(len(reference_marker_positions)),
        "suppressed_reference_marker_count": str(suppressed_reference_marker_count),
        "query_top1_pocket_overlap_count": str(query_top1_pocket_overlap_count),
        "query_top1_pocket_overlap_status": query_top1_pocket_overlap,
    }

    if args.compose_only and render_status != "SKIP_EXISTS":
        metrics = m10g.read_metrics(standard_metrics)
        out_png = compose_three_panel_figure(
            m10g=m10g,
            query=query,
            family=family,
            metrics=metrics,
            out_root=out_root,
            panel_dir=panel_dir,
            has_query_pocket=has_query_pocket,
            has_reference_pocket=has_reference_pocket,
            catalytic_summary=catalytic_summary,
        )
        if out_png != desired_png:
            shutil.move(str(out_png), str(desired_png))
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
            metrics = m10g.read_metrics(standard_metrics)
            out_png = compose_three_panel_figure(
                m10g=m10g,
                query=query,
                family=family,
                metrics=metrics,
                out_root=out_root,
                panel_dir=panel_dir,
                has_query_pocket=has_query_pocket,
                has_reference_pocket=has_reference_pocket,
                catalytic_summary=catalytic_summary,
            )
            if out_png != desired_png:
                shutil.move(str(out_png), str(desired_png))
            render_status = "PASS"
            render_note = "PyMOL render and three-panel PIL composition completed."
        except Exception as exc:
            render_status = "FAIL"
            render_note = f"Render/compose failed: {exc}"

    if not catalytic_query_rows:
        catalytic_class = "MISSING_QUERY_MANIFEST_ROW"
    else:
        catalytic_class = catalytic_query_rows[0].get("A10G_FIX2_final_catalytic_layer_class", "")

    m10h.write_rendered_residue_table(rendered_residue_table, rendered_residue_rows)
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
        {"metric": "has_query_pocket", "value": "YES" if has_query_pocket else "NO"},
        {"metric": "has_reference_pocket", "value": "YES" if has_reference_pocket else "NO"},
        {"metric": "secondary_residue_n", "value": "0"},
        {"metric": "secondary_rows_suppressed", "value": str(secondary_suppressed)},
        {"metric": "caution_rows_suppressed", "value": str(caution_suppressed)},
        {"metric": "render_status", "value": render_status},
        {"metric": "render_note", "value": render_note},
        {"metric": "standard_metrics_path", "value": str(standard_metrics)},
        {"metric": "prototype_png_path", "value": str(desired_png)},
        {"metric": "rendered_residue_table_path", "value": str(rendered_residue_table)},
        {"metric": "design_audit_path", "value": str(design_audit)},
    ]
    m10h.write_catalytic_metrics(catalytic_metrics, catalytic_metric_rows)

    png_exists = desired_png.exists() and render_status in {"PASS", "COMPOSE_ONLY", "SKIP_EXISTS"}
    png_size = str(desired_png.stat().st_size) if desired_png.exists() else "0"
    manifest_row = {
        "query": query,
        "family": family,
        "pml_path": str(desired_pml),
        "png_path": str(desired_png) if png_exists else "",
        "standard_metrics_path": str(standard_metrics),
        "catalytic_metrics_path": str(catalytic_metrics),
        "rendered_residue_table_path": str(rendered_residue_table),
        "existing_m10g_png_path": str(existing_png),
        "displayed_reference_id": displayed_reference_id,
        "reference_selection_mode": args.reference_selection_mode,
        "selected_m10a_reference_id": selected_m10a_reference_id,
        "selected_m10a_row_status": selected_m10a_row_status,
        "catalytic_manifest_reference_ids": reference_ids_text,
        "reference_marker_mode": reference_marker_mode,
        "catalytic_annotation_rows_used": str(len(catalytic_rows)),
        "query_primary_marker_count": str(len(query_core_positions)),
        "reference_primary_marker_count": str(len(reference_marker_positions)),
        "suppressed_reference_marker_count": str(suppressed_reference_marker_count),
        "query_top1_pocket_overlap_count": str(query_top1_pocket_overlap_count),
        "query_top1_pocket_overlap_status": query_top1_pocket_overlap,
        "has_query_pocket": "YES" if has_query_pocket else "NO",
        "has_reference_pocket": "YES" if has_reference_pocket else "NO",
        "render_status": render_status,
        "render_note": render_note,
        "png_size_bytes": png_size,
    }
    manifest_fields = list(manifest_row.keys())
    manifest_path = out_root / "full_catalytic_three_panel_prototype_manifest.tsv"
    qc_path = out_root / "three_panel_prototype_qc_summary.tsv"
    upsert_tsv(manifest_path, manifest_row, manifest_fields)
    upsert_tsv(qc_path, manifest_row, manifest_fields)

    command_log_fields = [
        "timestamp_utc",
        "query",
        "reference_selection_mode",
        "command",
        "render_status",
        "render_note",
        "png_path",
        "png_size_bytes",
    ]
    append_tsv(
        out_root / "three_panel_prototype_render_command_log.tsv",
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "reference_selection_mode": args.reference_selection_mode,
            "command": " ".join(shlex.quote(arg) for arg in sys.argv),
            "render_status": render_status,
            "render_note": render_note,
            "png_path": str(desired_png) if png_exists else "",
            "png_size_bytes": png_size,
        },
        command_log_fields,
    )

    print("M10H_CATALYTIC_THREE_PANEL_PROTOTYPE")
    print(f"query\t{query}")
    print(f"family\t{family}")
    print(f"reference_selection_mode\t{args.reference_selection_mode}")
    print(f"selected_m10a_reference_id\t{selected_m10a_reference_id}")
    print(f"reference_marker_mode\t{reference_marker_mode}")
    print(f"query_primary_marker_count\t{len(query_core_positions)}")
    print(f"reference_primary_marker_count\t{len(reference_marker_positions)}")
    print(f"suppressed_reference_marker_count\t{suppressed_reference_marker_count}")
    print(f"query_top1_pocket_overlap_count\t{query_top1_pocket_overlap_count}")
    print(f"has_query_pocket\t{'YES' if has_query_pocket else 'NO'}")
    print(f"has_reference_pocket\t{'YES' if has_reference_pocket else 'NO'}")
    print(f"pml\t{desired_pml}")
    print(f"png\t{str(desired_png) if png_exists else 'NOT_RENDERED'}")
    print(f"design_audit\t{design_audit}")
    print(f"manifest\t{manifest_path}")
    print(f"qc\t{qc_path}")
    print(f"render_status\t{render_status}")

    return 0 if render_status != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
