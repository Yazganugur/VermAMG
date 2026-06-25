#!/usr/bin/env python3
"""
10g_generate_full_composite_figures.py
One composite PNG per query protein for the full fresh run.
Adapted from generate_v6_standard_figures.py (M10F canonical engine).

Layout: 2-row x 3-view composite
  Row a: global structural — query | reference | superposition
  Row b: pocket-focused   — query pocket | reference pocket | pocket overlap
Includes legend, metrics box, and reference-confidence caveat label.

B-factor vs pLDDT semantics:
  query     = pLDDT  (ColabFold model, B-column stores pLDDT)
  PDB ref   = B-factor
  AFSP ref  = pLDDT

Reference caveat: references must be full-atom for pocket rendering. Experimental
PDB references use B-factor semantics, while AFSP references use pLDDT semantics.

Execution modes:
  Normal      : generate PML → run PyMOL → assemble composite
  --pml-only  : generate PML files only  (no PyMOL, no PIL needed)
  --compose-only: assemble composites from already-rendered panel PNGs (no PML/PyMOL)

WSL / local_wsl usage:
  source scripts/utils/load_vermamg_profile.sh local_wsl
  # Smoke (3 proteins, sequential):
  bash scripts/submit/m10g_composite_local_wsl_smoke.sh
  # Full (all query proteins, 3-phase parallel):
  bash scripts/submit/m10g_composite_local_wsl_full.sh
"""

import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

# PIL is only needed for --compose-only or normal (not --pml-only).
# Imported lazily so --pml-only works without PIL installed on the host.
_PIL_LOADED = False
Image = ImageDraw = ImageFont = ImageChops = None

def _require_pil():
    """Import PIL, preferring the system installation.

    Resolution order:
      1. Try a clean system import first — no sys.path changes.
      2. Only if that fails AND Python is exactly 3.9, try the bundled
         3.9 PIL from PYMOL_PIL_SITE (avoids poisoning newer interpreters).
      3. If still unavailable, exit with a clear, actionable error.

    Prints the resolved PIL path and version so failures are diagnosable.
    """
    global _PIL_LOADED, Image, ImageDraw, ImageFont, ImageChops
    if _PIL_LOADED:
        return

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"

    # ── Step 1: system PIL (no sys.path mutation) ─────────────────────────
    try:
        from PIL import Image as _Img, ImageDraw as _IDraw, \
            ImageFont as _IFont, ImageChops as _IChops
        Image, ImageDraw, ImageFont, ImageChops = _Img, _IDraw, _IFont, _IChops
        _PIL_LOADED = True
        print(f"PIL: system Pillow {_Img.__version__} | Python {py_ver} | {_Img.__file__}",
              flush=True)
        return
    except ImportError:
        pass  # fall through to bundled fallback

    # ── Step 2: bundled PIL — only valid for Python 3.9 ──────────────────
    pil_site = os.environ.get("PYMOL_PIL_SITE", "")
    if (sys.version_info.major == 3 and sys.version_info.minor == 9
            and pil_site and pil_site not in sys.path):
        sys.path.insert(0, pil_site)
        try:
            from PIL import Image as _Img, ImageDraw as _IDraw, \
                ImageFont as _IFont, ImageChops as _IChops
            Image, ImageDraw, ImageFont, ImageChops = _Img, _IDraw, _IFont, _IChops
            _PIL_LOADED = True
            print(f"PIL: bundled Pillow {_Img.__version__} | Python {py_ver} | {_Img.__file__}",
                  flush=True)
            return
        except ImportError:
            pass  # fall through to fatal error

    # ── Step 3: give up with a clear error ───────────────────────────────
    bundled_note = (
        f"  Bundled PIL site (PYMOL_PIL_SITE): {pil_site or '(not set)'}\n"
        f"  Bundled PIL is only usable with Python 3.9; you have {py_ver}.\n"
        if pil_site else ""
    )
    sys.exit(
        f"\nFATAL: PIL/Pillow not available (Python {py_ver}).\n"
        f"  Fix: pip install Pillow\n"
        + bundled_note
    )

FRESH_RUN_REL = os.environ.get(
    "M10G_FRESH_RUN_REL",
    "runs/smoke_precomputed/smoke_3prot_v1"
)
CONTRACT_REL = f"{FRESH_RUN_REL}/06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv"
DECISION_MATRIX_REL = f"{FRESH_RUN_REL}/results/full/07_decision_matrix/full_primary_decision_matrix.tsv"
PYMOL_REL = "scripts/utils/pymol_apptainer_wrapper.sh"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def read_tsv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def safe_float(x):
    try:
        if x is None or str(x).strip() in ("", "NA", "nan"):
            return None
        return float(x)
    except Exception:
        return None


def fmt(x, nd=3):
    if x is None:
        return "NA"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)


def clean_label(s):
    s = str(s)
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    return s.strip("_")


def parse_residue_ids(s):
    """Returns list of (chain, resi_string). Handles 'A_118' style."""
    if not s or str(s).strip().upper() in ("", "NA"):
        return []
    out = []
    for tok in str(s).replace(",", " ").split():
        parts = tok.strip().split("_")
        if len(parts) >= 2:
            chain, resi = parts[0], parts[1]
            if resi:
                out.append((chain, resi))
    return out


def pymol_selection_from_residues(obj, residues, ca_only=True):
    if not residues:
        return "none"
    by_chain = {}
    for chain, resi in residues:
        by_chain.setdefault(chain, []).append(resi)
    pieces = []
    for chain, resis in by_chain.items():
        seen = set()
        uniq = [r for r in resis if not (r in seen or seen.add(r))]
        resi_expr = "+".join(uniq)
        if ca_only:
            pieces.append(f"({obj} and chain {chain} and name CA and resi {resi_expr})")
        else:
            pieces.append(f"({obj} and chain {chain} and resi {resi_expr})")
    return " or ".join(pieces)


def get_font(size, bold=False):
    _require_pil()
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            pass
    return ImageFont.load_default()


def crop_white(img, pad=20):
    bg = Image.new(img.mode, img.size, "white")
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    return img.crop((max(l - pad, 0), max(t - pad, 0),
                     min(r + pad, img.size[0]), min(b + pad, img.size[1])))


def shared_crop_white(images, pad=90):
    """Crop a group of same-view panels to one shared non-white bounding box."""
    if not images:
        return images
    boxes = []
    for img in images:
        bg = Image.new(img.mode, img.size, "white")
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox:
            boxes.append(bbox)
    if not boxes:
        return images
    w, h = images[0].size
    l = max(min(b[0] for b in boxes) - pad, 0)
    t = max(min(b[1] for b in boxes) - pad, 0)
    r = min(max(b[2] for b in boxes) + pad, w)
    b = min(max(b[3] for b in boxes) + pad, h)
    return [img.crop((l, t, r, b)) for img in images]


def _lanczos():
    """Return the LANCZOS resampling filter compatible with any Pillow version.
    Pillow 10 removed the top-level Image.LANCZOS constant; use Resampling enum."""
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def fit_panel(img, target_w, target_h, crop=True):
    if crop:
        img = crop_white(img)
    img.thumbnail((target_w, target_h), _lanczos())
    canvas = Image.new("RGB", (target_w, target_h), "white")
    x = (target_w - img.size[0]) // 2
    y = (target_h - img.size[1]) // 2
    canvas.paste(img, (x, y))
    return canvas


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_legend_row(draw, fig_w, y, items, font, marker=24, gap=46, x_min=0, x_max=None):
    x_max = fig_w if x_max is None else x_max
    widths = []
    for kind, color, label in items:
        tw, _ = text_size(draw, label, font)
        widths.append(marker + 10 + tw)
    total_w = sum(widths) + gap * (len(items) - 1)
    x = max(x_min, x_min + ((x_max - x_min) - total_w) // 2)
    for (kind, color, label), item_w in zip(items, widths):
        if kind == "rect":
            draw.rectangle([x, y + 9, x + marker, y + marker - 3], fill=color)
        else:
            draw.ellipse([x, y + 2, x + marker, y + marker + 2], fill=color)
        draw.text((x + marker + 10, y), label, fill="black", font=font)
        x += item_w + gap


def read_metrics(path):
    if not path.exists():
        return {}
    rows = read_tsv(path)
    return rows[0] if rows else {}


def make_placeholder_panel(text, w, h, sub=None):
    """Gray placeholder panel for cases where no real PNG exists (e.g. no pocket)."""
    _require_pil()
    img = Image.new("RGB", (w, h), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    # light diagonal hatch to visually distinguish from a real panel
    for i in range(0, w + h, 60):
        draw.line([(max(0, i - h), min(h, i)), (min(w, i), max(0, i - w))],
                  fill=(228, 228, 228), width=1)
    font_main = get_font(28, bold=False)
    font_sub  = get_font(21, bold=False)
    cx, cy = w // 2, h // 2
    draw.text((cx, cy - (18 if sub else 0)), text,
              fill=(110, 110, 110), font=font_main, anchor="mm")
    if sub:
        draw.text((cx, cy + 26), sub,
                  fill=(150, 150, 150), font=font_sub, anchor="mm")
    return img


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def load_contract_primary(contract_path):
    """Return one row per protein: the PRIMARY panel_role row."""
    rows = read_tsv(contract_path)
    primary = [r for r in rows if r.get("panel_role", "") == "PRIMARY"]
    return primary


def load_decision_matrix(dm_path):
    """Return dict keyed by protein_id → row with pdb_qtmscore / afsp_qtmscore."""
    rows = read_tsv(dm_path)
    return {r["protein_id"]: r for r in rows}


def has_reliable_reference_pocket(row):
    """True when M10A supplied a non-empty reference top-1 pocket."""
    return bool(parse_residue_ids(row.get("reference_top1_residue_ids", "")))


def composite_pocket_status(has_query_pocket, has_reference_pocket):
    if not has_query_pocket:
        return "NO_QUERY_POCKET"
    if not has_reference_pocket:
        return "NO_RELIABLE_REFERENCE_POCKET"
    return "OK"


def choose_qtm(row, dm_map):
    pid = row["protein_id"]
    dm = dm_map.get(pid, {})
    layer = row.get("reference_layer", "")
    if layer == "AFSP":
        v = safe_float(dm.get("afsp_qtmscore"))
        return v if v is not None else safe_float(dm.get("pdb_qtmscore"))
    # PDB or unknown
    v = safe_float(dm.get("pdb_qtmscore"))
    return v if v is not None else safe_float(dm.get("afsp_qtmscore"))


# ---------------------------------------------------------------------------
# PML generation
# ---------------------------------------------------------------------------

def write_pml(row, dm_map, workspace, panel_dir, table_dir, pml_dir):
    query   = row["query"]          # canonical query identifier
    pid     = row["protein_id"]     # display-safe protein identifier
    family  = row.get("family", "NA")

    query_pdb_rel  = row.get("query_model_pdb_portable", "")
    ref_pdb_rel    = row.get("reference_file_path_portable", "")

    query_pdb  = workspace / query_pdb_rel  if query_pdb_rel  else None
    ref_pdb    = workspace / ref_pdb_rel    if ref_pdb_rel    else None

    if query_pdb is None or not query_pdb.exists():
        return None, {"query": query, "protein_id": pid, "status": "MISSING_QUERY_PDB",
                      "note": str(query_pdb)}
    if ref_pdb is None or not ref_pdb.exists():
        return None, {"query": query, "protein_id": pid, "status": "MISSING_REF_PDB",
                      "note": str(ref_pdb)}

    query_res  = parse_residue_ids(row.get("query_top1_residue_ids", ""))
    ref_res    = parse_residue_ids(row.get("reference_top1_residue_ids", ""))

    q_sel = pymol_selection_from_residues("query", query_res, ca_only=True)
    r_sel = pymol_selection_from_residues("reference", ref_res, ca_only=True)

    qtm    = choose_qtm(row, dm_map)
    qprob  = safe_float(row.get("query_top1_probability"))
    rprob  = safe_float(row.get("reference_top1_probability"))

    layer = row.get("reference_layer", "")
    ref_is_af  = layer == "AFSP" or ref_pdb.name.startswith("AF-")
    ref_is_pdb = (layer == "PDB") and not ref_is_af
    ca_only    = row.get("reference_ca_only_like", "NO").upper() == "YES"

    if ref_is_af:
        ref_conf_semantics = "REFERENCE_PLDDT"
    elif ref_is_pdb:
        ref_conf_semantics = "REFERENCE_BFACTOR"
    else:
        ref_conf_semantics = "REVIEW_REFERENCE_CONFIDENCE_SEMANTICS"

    has_query_pocket = bool(query_res)

    panel_subdir = panel_dir / query
    panel_subdir.mkdir(parents=True, exist_ok=True)
    metrics_path = table_dir / f"{query}_metrics.tsv"
    pml_path = pml_dir / f"{query}_{clean_label(family)}_v6_standard.pml"

    # b-panel render block — skipped entirely when no query pocket exists.
    # compose_figure will insert placeholder images instead.
    _b_panels = "" if not has_query_pocket else f"""
# ── b_left: query pocket ─────────────────────────────────────────────────────
scene pocket_view_same_angle_zoomed, recall
hide everything
show cartoon, query_pocket_region
color ghost_gray, query_pocket_region
set cartoon_transparency, 0.78, query_pocket_region
show spheres, query_conserved_ca
color query_yellow, query_conserved_ca
set sphere_scale, 1.08, query_conserved_ca
show spheres, query_unique_aligned_ca
color query_unique_orange, query_unique_aligned_ca
set sphere_scale, 1.28, query_unique_aligned_ca
png {panel_subdir.as_posix()}/b_left_query_pocket.png, width=2600, height=1900, dpi=600, ray=1

# ── b_mid: reference pocket ───────────────────────────────────────────────────
scene pocket_view_same_angle_zoomed, recall
hide everything
show cartoon, reference_pocket_region
color ghost_gray, reference_pocket_region
set cartoon_transparency, 0.78, reference_pocket_region
show spheres, reference_conserved_ca
color query_yellow, reference_conserved_ca
set sphere_scale, 1.08, reference_conserved_ca
show spheres, reference_unique_aligned_ca
color ref_unique_blue, reference_unique_aligned_ca
set sphere_scale, 1.28, reference_unique_aligned_ca
png {panel_subdir.as_posix()}/b_mid_reference_pocket.png, width=2600, height=1900, dpi=600, ray=1

# ── b_right: pocket overlap ───────────────────────────────────────────────────
scene pocket_view_same_angle_zoomed, recall
hide everything
show cartoon, query_pocket_region
show cartoon, reference_pocket_region
color ghost_gray, query_pocket_region
color ghost_gray, reference_pocket_region
set cartoon_transparency, 0.84, query_pocket_region
set cartoon_transparency, 0.84, reference_pocket_region
show spheres, query_conserved_ca
color query_yellow, query_conserved_ca
set sphere_scale, 1.08, query_conserved_ca
show spheres, reference_conserved_ca
color query_yellow, reference_conserved_ca
set sphere_scale, 1.08, reference_conserved_ca
show spheres, query_unique_aligned_ca
color query_unique_orange, query_unique_aligned_ca
set sphere_scale, 1.28, query_unique_aligned_ca
show spheres, reference_unique_aligned_ca
color ref_unique_blue, reference_unique_aligned_ca
set sphere_scale, 1.28, reference_unique_aligned_ca
png {panel_subdir.as_posix()}/b_right_overlay_pocket.png, width=2600, height=1900, dpi=600, ray=1
"""

    pml = f"""
reinitialize

load {query_pdb.as_posix()}, query
load {ref_pdb.as_posix()}, reference

hide everything
python
from pymol import cmd
import math
from pathlib import Path

metrics_path = Path("{metrics_path.as_posix()}")

protein_id = "{pid}"
family = "{family}"
query_label = "{query}"
qtm_score = "{fmt(qtm, 3)}"
query_p2rank = "{fmt(qprob, 3)}"
reference_p2rank = "{fmt(rprob, 3)}"
reference_confidence_semantics = "{ref_conf_semantics}"
reference_ca_only = "{str(ca_only)}"

cmd.set_color("query_cyan",        [0.00, 0.78, 0.88])
cmd.set_color("ref_gray",          [0.62, 0.62, 0.62])
cmd.set_color("query_yellow",      [1.00, 0.86, 0.00])
cmd.set_color("query_unique_orange",[1.00, 0.32, 0.04])
cmd.set_color("ref_unique_blue",   [0.05, 0.35, 1.00])
cmd.set_color("ghost_gray",        [0.82, 0.82, 0.82])

align_result = cmd.align("reference", "query", object="aln_main")
try:
    rmsd = float(align_result[0])
except Exception:
    rmsd = None

cmd.select("query_pocket_ca",     "{q_sel}")
cmd.select("reference_pocket_ca", "{r_sel}")

def ca_residue_set(selection):
    m = cmd.get_model(selection)
    return {{(a.chain, int(a.resi)) for a in m.atom if a.name == "CA"}}

query_pocket     = ca_residue_set("query_pocket_ca")
reference_pocket = ca_residue_set("reference_pocket_ca")

def atom_info_by_model_index():
    d = {{}}
    for obj in ["query", "reference"]:
        model = cmd.get_model(obj)
        for a in model.atom:
            try:
                resi_int = int(a.resi)
            except Exception:
                continue
            d[(obj, a.index)] = {{
                "obj": obj, "index": a.index, "chain": a.chain,
                "resi": resi_int, "resn": a.resn, "name": a.name, "coord": a.coord
            }}
    return d

info = atom_info_by_model_index()
raw  = cmd.get_raw_alignment("aln_main")

q_to_r = {{}}
r_to_q = {{}}
for col in raw:
    atoms   = [info[(m, i)] for m, i in col if (m, i) in info]
    q_atoms = [a for a in atoms if a["obj"] == "query"     and a["name"] == "CA"]
    r_atoms = [a for a in atoms if a["obj"] == "reference" and a["name"] == "CA"]
    if len(q_atoms) == 1 and len(r_atoms) == 1:
        q = q_atoms[0]
        r = r_atoms[0]
        q_to_r[(q["chain"], q["resi"])] = (r["chain"], r["resi"])
        r_to_q[(r["chain"], r["resi"])] = (q["chain"], q["resi"])

query_conserved = [q for q in sorted(query_pocket)
                   if q_to_r.get(q) in reference_pocket]
query_unique    = [q for q in sorted(query_pocket)
                   if q_to_r.get(q) not in reference_pocket]
reference_conserved = [r for r in sorted(reference_pocket)
                       if r_to_q.get(r) in query_pocket]
reference_unique    = [r for r in sorted(reference_pocket)
                       if r_to_q.get(r) not in query_pocket]

def select_from_tuples(selname, obj, tuples):
    if not tuples:
        cmd.select(selname, "none")
        return
    by_chain = {{}}
    for chain, resi in tuples:
        by_chain.setdefault(chain, []).append(str(resi))
    pieces = []
    for chain, resis in by_chain.items():
        resis = sorted(set(resis), key=lambda x: int(x) if x.isdigit() else x)
        pieces.append(f"({{obj}} and chain {{chain}} and name CA and resi {{'+'.join(resis)}})")
    cmd.select(selname, " or ".join(pieces))

select_from_tuples("query_conserved_ca",       "query",     query_conserved)
select_from_tuples("query_unique_aligned_ca",   "query",     query_unique)
select_from_tuples("reference_conserved_ca",    "reference", reference_conserved)
select_from_tuples("reference_unique_aligned_ca","reference", reference_unique)

cmd.select("combined_all",          "query or reference")
cmd.select("all_pocket_points",     "query_pocket_ca or reference_pocket_ca")
cmd.select("query_pocket_region",   "query     within 7.0 of query_pocket_ca")
cmd.select("reference_pocket_region","reference within 7.0 of reference_pocket_ca")

def mean_ca_b_column(selection):
    m = cmd.get_model(selection)
    vals = [float(a.b) for a in m.atom if a.name == "CA"]
    return (sum(vals) / len(vals)) if vals else None

query_pocket_mean_plddt  = mean_ca_b_column("query_pocket_ca")
reference_pocket_mean_plddt   = None
reference_pocket_mean_bfactor = None

if reference_confidence_semantics == "REFERENCE_PLDDT":
    reference_pocket_mean_plddt   = mean_ca_b_column("reference_pocket_ca")
elif reference_confidence_semantics == "REFERENCE_BFACTOR":
    reference_pocket_mean_bfactor = mean_ca_b_column("reference_pocket_ca")

with open(metrics_path, "w") as f:
    f.write("protein_id\\tquery\\tfamily\\tqtm_score\\trmsd\\tquery_p2rank\\treference_p2rank\\t"
            "query_pocket_mean_plddt\\treference_confidence_semantics\\treference_ca_only\\t"
            "reference_pocket_mean_plddt\\treference_pocket_mean_bfactor\\t"
            "query_pocket_n\\treference_pocket_n\\t"
            "query_conserved_n\\tquery_unique_n\\t"
            "reference_conserved_n\\treference_unique_n\\n")
    def _s(v): return "NA" if v is None else f"{{v:.3f}}"
    f.write(
        f"{{protein_id}}\\t{{query_label}}\\t{{family}}\\t{{qtm_score}}\\t"
        f"{{_s(rmsd)}}\\t{{query_p2rank}}\\t{{reference_p2rank}}\\t"
        f"{{_s(query_pocket_mean_plddt)}}\\t{{reference_confidence_semantics}}\\t"
        f"{{reference_ca_only}}\\t"
        f"{{_s(reference_pocket_mean_plddt)}}\\t{{_s(reference_pocket_mean_bfactor)}}\\t"
        f"{{len(query_pocket)}}\\t{{len(reference_pocket)}}\\t"
        f"{{len(query_conserved)}}\\t{{len(query_unique)}}\\t"
        f"{{len(reference_conserved)}}\\t{{len(reference_unique)}}\\n"
    )
python end

# ── visual settings ──────────────────────────────────────────────────────────
bg_color white
set ray_opaque_background, off
set orthoscopic, on
set antialias, 2
set depth_cue, 0
set ray_shadows, 1
set ambient, 0.42
set direct, 0.58
set specular, 0.20
set shininess, 18
set reflect, 0.08
set cartoon_fancy_helices, 1
set cartoon_sampling, 12
set sphere_quality, 4
set valence, 0

# ── base/pocket views ────────────────────────────────────────────────────────
hide everything
show cartoon, query
show cartoon, reference
color query_cyan, query
color ref_gray,  reference
orient combined_all
turn y, 28
turn x, -18
zoom combined_all, 2.1, complete=1
scene base_view, store

scene base_view, recall
scene full_view, store

python
if cmd.count_atoms("query_pocket_region or reference_pocket_region") > 0:
    cmd.zoom("query_pocket_region or reference_pocket_region", 4.2, complete=1)
elif cmd.count_atoms("all_pocket_points") > 0:
    cmd.zoom("all_pocket_points", 4.2, complete=1)
cmd.scene("pocket_view_same_angle_zoomed", "store")
python end

# ── a_left: query global ──────────────────────────────────────────────────────
scene full_view, recall
hide everything
show cartoon, query
color query_cyan, query
show spheres, query_conserved_ca
color query_yellow, query_conserved_ca
set sphere_scale, 0.58, query_conserved_ca
show spheres, query_unique_aligned_ca
color query_unique_orange, query_unique_aligned_ca
set sphere_scale, 0.72, query_unique_aligned_ca
png {panel_subdir.as_posix()}/a_left_query.png, width=2600, height=1900, dpi=600, ray=1

# ── a_mid: reference global ───────────────────────────────────────────────────
scene full_view, recall
hide everything
show cartoon, reference
color ref_gray, reference
show spheres, reference_conserved_ca
color query_yellow, reference_conserved_ca
set sphere_scale, 0.58, reference_conserved_ca
show spheres, reference_unique_aligned_ca
color ref_unique_blue, reference_unique_aligned_ca
set sphere_scale, 0.72, reference_unique_aligned_ca
png {panel_subdir.as_posix()}/a_mid_reference.png, width=2600, height=1900, dpi=600, ray=1

# ── a_right: superposition ────────────────────────────────────────────────────
scene full_view, recall
hide everything
show cartoon, query
show cartoon, reference
color query_cyan, query
color ref_gray,  reference
set cartoon_transparency, 0.18, reference
show spheres, query_conserved_ca
color query_yellow, query_conserved_ca
set sphere_scale, 0.58, query_conserved_ca
show spheres, reference_conserved_ca
color query_yellow, reference_conserved_ca
set sphere_scale, 0.58, reference_conserved_ca
show spheres, query_unique_aligned_ca
color query_unique_orange, query_unique_aligned_ca
set sphere_scale, 0.72, query_unique_aligned_ca
show spheres, reference_unique_aligned_ca
color ref_unique_blue, reference_unique_aligned_ca
set sphere_scale, 0.72, reference_unique_aligned_ca
png {panel_subdir.as_posix()}/a_right_overlay.png, width=2600, height=1900, dpi=600, ray=1
{_b_panels}"""
    pml_path.write_text(pml, encoding="utf-8")
    return pml_path, None, has_query_pocket


# ---------------------------------------------------------------------------
# Composite assembly
# ---------------------------------------------------------------------------

def compose_figure(query, family, metrics, outdir, panel_dir,
                   has_query_pocket=True, has_reference_pocket=True):
    """Assemble 2×3 composite PNG.

    has_query_pocket=False: b-row panels are replaced by labeled placeholders
    rather than loading from disk. This is QC-recorded as NO_QUERY_POCKET,
    not as a failure.

    has_reference_pocket=False: the reference-pocket and pocket-overlap panels
    are explicit placeholders, because a zero-pocket reference should
    not look like a silently blank render.
    """
    _require_pil()
    pd = panel_dir / query

    # a-panels must always exist — PyMOL renders them regardless of pocket status
    a_paths = {
        "a_left":  pd / "a_left_query.png",
        "a_mid":   pd / "a_mid_reference.png",
        "a_right": pd / "a_right_overlay.png",
    }
    missing_a = [str(p) for p in a_paths.values() if not p.exists()]
    if missing_a:
        raise RuntimeError("Missing a-panel files: " + "; ".join(missing_a))

    panel_w, panel_h = 1240, 880

    panels = {
        "a_left":  fit_panel(Image.open(a_paths["a_left"]).convert("RGB"),  panel_w, panel_h, crop=True),
        "a_mid":   fit_panel(Image.open(a_paths["a_mid"]).convert("RGB"),   panel_w, panel_h, crop=True),
        "a_right": fit_panel(Image.open(a_paths["a_right"]).convert("RGB"), panel_w, panel_h, crop=True),
    }

    if has_query_pocket:
        b_paths = {
            "b_left":  pd / "b_left_query_pocket.png",
            "b_mid":   pd / "b_mid_reference_pocket.png",
            "b_right": pd / "b_right_overlay_pocket.png",
        }
        required_b = ["b_left", "b_mid", "b_right"] if has_reference_pocket else ["b_left"]
        missing_b = [str(b_paths[k]) for k in required_b if not b_paths[k].exists()]
        if missing_b:
            raise RuntimeError("Missing b-panel files: " + "; ".join(missing_b))
        b_left_img = Image.open(b_paths["b_left"]).convert("RGB")
        if has_reference_pocket:
            b_imgs = shared_crop_white(
                [
                    b_left_img,
                    Image.open(b_paths["b_mid"]).convert("RGB"),
                    Image.open(b_paths["b_right"]).convert("RGB"),
                ],
                pad=85,
            )
            panels["b_left"]  = fit_panel(b_imgs[0], panel_w, panel_h, crop=False)
            panels["b_mid"]   = fit_panel(b_imgs[1], panel_w, panel_h, crop=False)
            panels["b_right"] = fit_panel(b_imgs[2], panel_w, panel_h, crop=False)
        else:
            panels["b_left"] = fit_panel(crop_white(b_left_img, pad=85), panel_w, panel_h, crop=False)
            panels["b_mid"] = make_placeholder_panel(
                "No reliable reference pocket (zero-pocket)",
                panel_w, panel_h,
                sub="Reference P2Rank produced zero usable pocket residues")
            panels["b_right"] = make_placeholder_panel(
                "No reliable pocket overlap", panel_w, panel_h,
                sub="reference pocket unavailable")
    else:
        panels["b_left"]  = make_placeholder_panel(
            "No query pocket predicted", panel_w, panel_h,
            sub="P2Rank found no significant pocket")
        panels["b_mid"]   = make_placeholder_panel(
            "No reliable reference pocket (zero-pocket)",
            panel_w, panel_h,
            sub="Reference P2Rank produced zero usable pocket residues")
        panels["b_right"] = make_placeholder_panel(
            "No pocket overlap", panel_w, panel_h,
            sub="(no query pocket to compare)")

    left_m, right_m = 90, 90
    top_m, bot_m    = 48, 130
    col_gap, row_gap = 40, 76
    legend_band      = 340
    letter_band      = 44
    header_band      = 46

    fig_w = left_m + 3 * panel_w + 2 * col_gap + right_m
    fig_h = (top_m + legend_band
             + letter_band + header_band + panel_h
             + row_gap
             + letter_band + header_band + panel_h
             + bot_m)

    canvas = Image.new("RGB", (fig_w, fig_h), "white")
    draw   = ImageDraw.Draw(canvas)

    font_letter     = get_font(40, True)
    font_header     = get_font(30, True)
    font_legend     = get_font(27, False)
    font_score      = get_font(23, False)
    font_score_bold = get_font(23, True)
    font_score_cav  = get_font(19, False)
    font_small      = get_font(20, False)
    font_caveat     = get_font(19, False)

    x1 = left_m
    x2 = left_m + panel_w + col_gap
    x3 = left_m + 2 * (panel_w + col_gap)

    y_legend   = top_m
    y_a_letter = y_legend + legend_band
    y_a_header = y_a_letter + letter_band
    y_a_panel  = y_a_header + header_band
    y_b_letter = y_a_panel + panel_h + row_gap
    y_b_header = y_b_letter + letter_band
    y_b_panel  = y_b_header + header_band

    # ── panel letters ────────────────────────────────────────────────────────
    draw.text((32, y_a_letter - 2), "a", fill="black", font=font_letter)
    draw.text((32, y_b_letter - 2), "b", fill="black", font=font_letter)

    # ── column headers ────────────────────────────────────────────────────────
    for x, txt in zip([x1, x2, x3],
                      ["Query protein", "Reference", "Overlap"]):
        draw.text((x, y_a_header + 4), txt, fill="black", font=font_header)
    for x, txt in zip([x1, x2, x3],
                      ["Query predicted pocket", "Reference predicted pocket", "Pocket overlap"]):
        draw.text((x, y_b_header + 4), txt, fill="black", font=font_header)

    # ── panels ───────────────────────────────────────────────────────────────
    border_col = (232, 232, 232)
    placements = {
        "a_left":  (x1, y_a_panel), "a_mid":  (x2, y_a_panel), "a_right": (x3, y_a_panel),
        "b_left":  (x1, y_b_panel), "b_mid":  (x2, y_b_panel), "b_right": (x3, y_b_panel),
    }
    for key, (px, py) in placements.items():
        canvas.paste(panels[key], (px, py))
        draw.rectangle([px, py, px + panel_w, py + panel_h],
                       outline=border_col, width=2)

    # ── centered legend ──────────────────────────────────────────────────────
    legend_x_min = left_m
    legend_x_max = x3 - 28
    draw_legend_row(
        draw, fig_w, y_legend + 18,
        [
            ("rect", (0, 199, 224), "Query protein"),
            ("rect", (158, 158, 158), "Reference"),
            ("circle", (255, 219, 0), "Shared/overlapping pocket position"),
        ],
        font_legend, marker=32, gap=64, x_min=legend_x_min, x_max=legend_x_max)
    draw_legend_row(
        draw, fig_w, y_legend + 72,
        [
            ("circle", (255, 82, 10), "Query-specific pocket position"),
            ("circle", (13, 89, 255), "Reference-specific pocket position"),
            ("rect", (210, 210, 210), "Faint pocket outline in panel B"),
        ],
        font_legend, marker=32, gap=64, x_min=legend_x_min, x_max=legend_x_max)

    # ── score box ────────────────────────────────────────────────────────────
    # 7 data rows + hairline + reference semantics caveat.
    box_w   = 770
    row_h   = 38
    n_rows  = 7
    box_h   = 16 + n_rows * row_h + 8 + 30 + 12
    bx2     = x3 + panel_w - 20
    by1     = y_legend + 8
    bx1     = bx2 - box_w
    val_col = bx1 + 380
    draw.rounded_rectangle([bx1, by1, bx2, by1 + box_h],
                           radius=18, fill=(255, 255, 255),
                           outline=(120, 120, 120), width=2)

    m = metrics
    qn  = m.get("query_pocket_n",        "NA")
    rn  = m.get("reference_pocket_n",    "NA")
    qc  = m.get("query_conserved_n",     "NA")
    rc  = m.get("reference_conserved_n", "NA")
    qu  = m.get("query_unique_n",        "NA")
    ru  = m.get("reference_unique_n",    "NA")

    ref_sem     = m.get("reference_confidence_semantics", "")
    q_plddt_val = m.get("query_pocket_mean_plddt", "NA") if has_query_pocket else "NA"
    if not has_reference_pocket:
        ref_conf_label = "Ref pocket value"
        ref_conf_val = "NA"
    elif ref_sem == "REFERENCE_BFACTOR":
        ref_conf_label = "Ref pocket B-factor (PDB)"
        r_conf_val = m.get("reference_pocket_mean_bfactor", "NA")
    elif ref_sem == "REFERENCE_PLDDT":
        ref_conf_label = "Ref pocket pLDDT (AFSP)"
        r_conf_val = m.get("reference_pocket_mean_plddt", "NA")
    else:
        ref_conf_label = "Ref pocket confidence"
        r_conf_val = "?"

    if not has_query_pocket:
        pocket_label, pocket_value = "Pocket status", "NONE (NO_QUERY_POCKET)"
        unique_value = "NA"
    elif not has_reference_pocket:
        pocket_label, pocket_value = "Ref pocket", "NONE (zero-pocket)"
        unique_value = f"Q {qu}  /  R NA"
    else:
        pocket_label, pocket_value = "Conserved pocket", f"Q {qc}/{qn}  /  R {rc}/{rn}"
        unique_value = f"Q {qu}  /  R {ru}"

    score_lines = [
        ("qTMscore",         m.get("qtm_score", "NA")),
        ("RMSD",             (m.get("rmsd", "NA") + " Å") if m.get("rmsd", "NA") != "NA" else "NA"),
        ("P2Rank (Q / R)",   f"{m.get('query_p2rank', 'NA')}  /  {m.get('reference_p2rank', 'NA')}"),
        ("Query pocket pLDDT",  q_plddt_val),
        (ref_conf_label,     r_conf_val),
        (pocket_label,       pocket_value),
        ("Unique pocket pos.", unique_value),
    ]

    yy = by1 + 14
    for label, value in score_lines:
        draw.text((bx1 + 16, yy), f"{label}:", fill="black",      font=font_score_bold)
        draw.text((val_col,   yy), str(value),  fill=(30, 30, 30), font=font_score)
        yy += row_h

    # ── CA-only quality caveat (small, gray, below hairline) ─────────────────
    yy += 6
    draw.line([(bx1 + 16, yy), (bx2 - 16, yy)], fill=(210, 210, 210), width=1)
    yy += 5
    ca_raw    = str(m.get("reference_ca_only", "True")).lower()
    is_ca_only = ca_raw in ("true", "yes", "1")
    if is_ca_only:
        cav_text = "Ref quality: CA-only (pocket signal unclear)"
    elif ref_sem == "REFERENCE_BFACTOR":
        cav_text = "Ref type: experimental PDB; B-factor is not pLDDT"
    elif ref_sem == "REFERENCE_PLDDT":
        cav_text = "Ref type: AFSP; reference value is pLDDT"
    else:
        cav_text = "Ref type: full-atom; confidence value should be verified"
    cav_color = (130, 90, 40) if is_ca_only else (80, 120, 70)
    draw.text((bx1 + 16, yy), cav_text, fill=cav_color, font=font_score_cav)

    # ── caption ───────────────────────────────────────────────────────────────
    pocket_note = (
        "No pocket could be predicted for the query protein (NO_QUERY_POCKET). "
        if not has_query_pocket else
        "Spheres show the Cα positions of P2Rank-predicted pocket residues. "
        "Pocket classes are defined over aligned Cα positions. "
    )
    reference_note = (
        "No reliable reference pocket (zero-pocket). "
        if not has_reference_pocket else
        "Reference pockets are computed with P2Rank from full-atom input."
    )
    caption = (f"{query}  |  Aile: {family}  |  "
               + pocket_note
               + reference_note)
    draw.text((left_m, fig_h - 54), caption, fill=(70, 70, 70), font=font_small)

    final_dir = outdir / "final_pngs"
    final_dir.mkdir(parents=True, exist_ok=True)
    out = final_dir / f"{query}_{clean_label(family)}_v6_standard_600dpi.png"
    canvas.save(out, dpi=(600, 600))
    return out


def cleanup_panel_pngs(panel_dir, query):
    pd = panel_dir / query
    if not pd.exists():
        return 0
    removed = 0
    for p in pd.glob("*.png"):
        p.unlink()
        removed += 1
    return removed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate composite figures for fresh full run.")
    ap.add_argument("--workspace", default=None,
                    help="Project root. Default: $VERMAMG_ROOT env var, then cwd.")
    ap.add_argument("--outdir",    default=None,
                    help="Output directory for composite PNGs. "
                         "Default: {workspace}/runs/.../06_visual_qc_v6/full/composite_png/")
    ap.add_argument("--contract",  default=None,
                    help="Input contract TSV. Default: auto from workspace.")
    ap.add_argument("--decision-matrix", default=None, dest="decision_matrix",
                    help="Decision matrix TSV (for qtmscore). Default: auto from workspace.")
    ap.add_argument("--pymol",     default=None,
                    help="PyMOL executable. Default: $PYMOL_CMD, then {workspace}/" + PYMOL_REL)
    ap.add_argument("--only",      default=None,
                    help="Comma-separated query IDs to process.")
    ap.add_argument("--limit",     type=int, default=None,
                    help="Process at most N proteins.")
    ap.add_argument("--pml-only",  action="store_true",
                    help="Generate PML files only; skip rendering and compositing.")
    ap.add_argument("--compose-only", action="store_true",
                    help="Assemble composites from already-rendered panel PNGs. "
                         "Skips PML generation and PyMOL. Requires panel PNGs to exist.")
    ap.add_argument("--skip-if-exists", action="store_true",
                    help="Skip a protein if its composite PNG already exists in outdir.")
    ap.add_argument("--cleanup-panel-pngs", action="store_true",
                    help="Delete per-panel PNGs after a successful final composite is written.")
    args = ap.parse_args()

    if args.pml_only and args.compose_only:
        raise SystemExit("FATAL: --pml-only and --compose-only are mutually exclusive.")

    _ws_default = os.environ.get("VERMAMG_ROOT", "") or str(Path(".").resolve())
    workspace = Path(args.workspace).resolve() if args.workspace else Path(_ws_default).resolve()

    contract_path = Path(args.contract) if args.contract else (workspace / CONTRACT_REL)
    dm_path       = Path(args.decision_matrix) if args.decision_matrix else (workspace / DECISION_MATRIX_REL)
    pymol_cmd     = (args.pymol
                     or os.environ.get("PYMOL_CMD", "")
                     or str(workspace / PYMOL_REL))
    outdir        = (Path(args.outdir).resolve() if args.outdir
                     else workspace / FRESH_RUN_REL / "06_visual_qc_v6/full/composite_png")

    panel_dir = outdir / "panels"
    pml_dir   = outdir / "pml"
    log_dir   = outdir / "logs"
    table_dir = outdir / "tables"
    for d in [outdir, panel_dir, pml_dir, log_dir, table_dir]:
        d.mkdir(parents=True, exist_ok=True)

    mode_tag = ("pml-only" if args.pml_only
                else "compose-only" if args.compose_only
                else "full")
    print(f"mode:           {mode_tag}")
    print(f"workspace:      {workspace}")
    print(f"contract:       {contract_path}")
    print(f"decision_matrix:{dm_path}")
    print(f"pymol_cmd:      {pymol_cmd}")
    print(f"outdir:         {outdir}")
    print(f"skip_if_exists: {args.skip_if_exists}")
    print()

    for p in [contract_path, dm_path]:
        if not p.exists():
            raise SystemExit(f"FATAL: required input not found: {p}")

    primary_rows = load_contract_primary(contract_path)
    dm_map       = load_decision_matrix(dm_path)

    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        primary_rows = [r for r in primary_rows if r.get("query", "") in wanted]
        if not primary_rows:
            raise SystemExit(f"FATAL: --only filter matched zero rows. Wanted: {wanted}")

    primary_rows = sorted(primary_rows, key=lambda r: r.get("query", ""))
    if args.limit:
        primary_rows = primary_rows[:args.limit]

    print(f"proteins to process: {len(primary_rows)}")
    print()

    failed         = []
    produced       = []
    skipped        = []
    all_metrics    = []
    no_pocket_list = []
    no_reference_pocket_list = []

    for row in primary_rows:
        query  = row["query"]
        family = row.get("family", "NA")
        has_query_pocket = bool(parse_residue_ids(row.get("query_top1_residue_ids", "")))
        has_reference_pocket = has_reliable_reference_pocket(row)

        # ── skip-if-exists check ──────────────────────────────────────────────
        if args.skip_if_exists and not args.pml_only:
            expected_png = outdir / "final_pngs" / f"{query}_{clean_label(family)}_v6_standard_600dpi.png"
            if expected_png.exists():
                skipped.append(query)
                print(f"SKIP (exists): {query[:60]}", flush=True)
                continue

        if not has_query_pocket:
            pocket_tag = "  [NO_QUERY_POCKET]"
        elif not has_reference_pocket:
            pocket_tag = "  [NO_RELIABLE_REFERENCE_POCKET]"
        else:
            pocket_tag = ""
        print(f"--- {query[:75]}  [{family}]{pocket_tag} ---", flush=True)
        if not has_query_pocket:
            no_pocket_list.append(query)
        if not has_reference_pocket:
            no_reference_pocket_list.append(query)

        # ── compose-only: skip PML/PyMOL ────────────────────────────────────
        if args.compose_only:
            metrics_path = table_dir / f"{query}_metrics.tsv"
            metrics = read_metrics(metrics_path)
            if metrics:
                all_metrics.append(metrics)
            try:
                out_png = compose_figure(query, family, metrics, outdir, panel_dir,
                                         has_query_pocket=has_query_pocket,
                                         has_reference_pocket=has_reference_pocket)
                if args.cleanup_panel_pngs:
                    cleanup_panel_pngs(panel_dir, query)
                pocket_status = composite_pocket_status(
                    has_query_pocket, has_reference_pocket)
                produced.append({"query": query, "family": family,
                                 "png": str(out_png), "pocket_status": pocket_status})
                print(f"  COMPOSED: {out_png.name}", flush=True)
            except Exception as exc:
                failed.append({"query": query, "protein_id": row.get("protein_id", ""),
                               "status": "FAILED_COMPOSE",
                               "note": str(exc), "log": ""})
                print(f"  FAILED_COMPOSE: {exc}", flush=True)
            continue

        # ── PML generation ───────────────────────────────────────────────────
        pml_path, err, _has_pocket = write_pml(
            row, dm_map, workspace, panel_dir, table_dir, pml_dir)
        if err:
            failed.append(err)
            print("  FAILED_PREP:", err["status"], err.get("note", ""), flush=True)
            continue

        if args.pml_only:
            print(f"  PML: {pml_path}", flush=True)
            pocket_status = composite_pocket_status(_has_pocket, has_reference_pocket)
            produced.append({"query": query, "family": family,
                             "pml": str(pml_path), "png": "PML_ONLY",
                             "pocket_status": pocket_status})
            continue

        # ── PyMOL render ─────────────────────────────────────────────────────
        log_path = log_dir / f"{query}.pymol.log"
        try:
            with open(log_path, "w") as logf:
                subprocess.run(
                    [pymol_cmd, "-cq", str(pml_path)],
                    stdout=logf, stderr=subprocess.STDOUT,
                    check=True,
                    env={**os.environ, "VERMAMG_ROOT": str(workspace)},
                )
            metrics_path = table_dir / f"{query}_metrics.tsv"
            metrics = read_metrics(metrics_path)
            if metrics:
                all_metrics.append(metrics)
            out_png = compose_figure(query, family, metrics, outdir, panel_dir,
                                     has_query_pocket=_has_pocket,
                                     has_reference_pocket=has_reference_pocket)
            if args.cleanup_panel_pngs:
                cleanup_panel_pngs(panel_dir, query)
            pocket_status = composite_pocket_status(_has_pocket, has_reference_pocket)
            produced.append({"query": query, "family": family,
                             "png": str(out_png), "pocket_status": pocket_status})
            print(f"  OK [{pocket_status}]: {out_png.name}", flush=True)
        except Exception as exc:
            failed.append({"query": query, "protein_id": row.get("protein_id", ""),
                           "status": "FAILED_RENDER_OR_COMPOSE",
                           "note": str(exc), "log": str(log_path)})
            print(f"  FAILED: {exc}", flush=True)

    # ── write outputs ────────────────────────────────────────────────────────
    manifest_path = outdir / "composite_png_manifest.tsv"
    with open(manifest_path, "w", newline="") as f:
        f.write("query\tfamily\tpng\tpocket_status\n")
        for r in produced:
            f.write(f"{r.get('query','')}\t{r.get('family','')}\t"
                    f"{r.get('png','')}\t{r.get('pocket_status','')}\n")

    failed_path = outdir / "composite_png_failed.tsv"
    with open(failed_path, "w", newline="") as f:
        f.write("query\tprotein_id\tstatus\tnote\tlog\n")
        for r in failed:
            f.write(f"{r.get('query','')}\t{r.get('protein_id','')}\t"
                    f"{r.get('status','')}\t{r.get('note','')}\t{r.get('log','')}\n")

    metrics_out = outdir / "composite_png_metrics.tsv"
    if all_metrics:
        fieldnames = list(all_metrics[0].keys())
        with open(metrics_out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            for r in all_metrics:
                w.writerow(r)

    qc_path = outdir / "composite_png_qc.tsv"
    with open(qc_path, "w") as f:
        f.write("metric\tvalue\n")
        f.write(f"mode\t{mode_tag}\n")
        f.write(f"proteins_attempted\t{len(primary_rows)}\n")
        f.write(f"produced\t{len(produced)}\n")
        f.write(f"no_query_pocket\t{len(no_pocket_list)}\n")
        f.write(f"no_reliable_reference_pocket\t{len(no_reference_pocket_list)}\n")
        f.write(f"skipped_exists\t{len(skipped)}\n")
        f.write(f"failed\t{len(failed)}\n")

    print()
    print(f"produced:                    {len(produced)}")
    print(f"no_query_pocket:             {len(no_pocket_list)}")
    print(f"no_reliable_reference_pocket: {len(no_reference_pocket_list)}")
    print(f"skipped:                     {len(skipped)}")
    print(f"failed:                      {len(failed)}")
    print(f"manifest:                    {manifest_path}")
    print(f"failed_table:                {failed_path}")
    print(f"qc_table:                    {qc_path}")


if __name__ == "__main__":
    main()
