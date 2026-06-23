#!/usr/bin/env python3
"""
m10f_render_all_query_pngs.py

Renders PNG overlays for all primary-panel visual scripts using PyMOL
via Apptainer. A single Apptainer+PyMOL session is used to avoid per-call
startup overhead.

B-factor / pLDDT semantic:
  query structure  = ColabFold pLDDT (confidence 0-100, not B-factor)
  PDB reference    = crystallographic B-factor (thermal displacement)
  AFSP reference   = AlphaFold pLDDT (confidence 0-100)
These semantics are encoded in the PML scripts (query b-factor / reference
b-factor are coloured differently); this module renders what the scripts
define without altering that logic.

CA-only caution:
  Reference pocket evidence is unreliable for this run (all references are
  CA-only-like). The PML scripts already note this. Zero reference pocket
  markers in PNGs is expected and does NOT indicate biological absence.
"""
from __future__ import annotations

import argparse
import hashlib
import csv
import datetime
import os
import subprocess
import tempfile
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t",
                           extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="M10F: Render PNG overlays via PyMOL/Apptainer.")
    ap.add_argument("--manifest",         required=True, help="all_query_visual_script_manifest.tsv")
    ap.add_argument("--out-png-dir",      required=True, help="Output directory for PNG files")
    ap.add_argument("--out-manifest",     required=True, help="Output PNG manifest TSV")
    ap.add_argument("--out-qc",           required=True, help="Output QC report TSV")
    ap.add_argument("--pymol-container",  required=True, help="Path to PyMOL Apptainer .sif")
    ap.add_argument("--project-root",     required=True, help="Project root for Apptainer bind mount")
    ap.add_argument("--allowed-root",     required=True, help="Run root; all outputs must be under here")
    ap.add_argument("--panel-orders",     default="1,2,3,4,5",   help="Comma-separated panel_order values to render (default: 1,2,3,4,5)")
    ap.add_argument("--dpi",              type=int, default=150, help="PNG DPI (default: 150)")
    ap.add_argument("--ray",              action="store_true", help="Use PyMOL ray tracing (slow, high quality)")
    ap.add_argument("--mode",             default="full")
    args = ap.parse_args()

    manifest_path   = Path(args.manifest)
    out_png_dir     = Path(args.out_png_dir)
    out_manifest    = Path(args.out_manifest)
    out_qc          = Path(args.out_qc)
    sif             = Path(args.pymol_container)
    project_root    = Path(args.project_root)
    allowed_root    = Path(args.allowed_root)
    target_orders   = set(args.panel_orders.split(","))
    dpi             = args.dpi
    use_ray         = args.ray

    # Safety: outputs must stay under allowed_root
    for p in (out_png_dir, out_manifest, out_qc):
        try:
            p.resolve().relative_to(allowed_root.resolve())
        except ValueError:
            raise SystemExit(f"ERROR: output path outside allowed_root: {p}")

    if not sif.is_file():
        raise SystemExit(f"ERROR: PyMOL container not found: {sif}")
    if not manifest_path.is_file():
        raise SystemExit(f"ERROR: manifest not found: {manifest_path}")

    out_png_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    rows = read_tsv(manifest_path)
    target_rows = [r for r in rows if r.get("panel_order", "") in target_orders]
    print(f"manifest_rows: {len(rows)}")
    print(f"panel_orders_selected: {args.panel_orders}")
    print(f"rows_to_render: {len(target_rows)}")
    print(f"out_png_dir: {out_png_dir}")
    print(f"ray: {use_ray}")
    print(f"dpi: {dpi}")

    if not target_rows:
        raise SystemExit("ERROR: no rows matched selected panel_orders in manifest")

    # Build per-row render instructions
    render_rows = []
    for r in target_rows:
        query = r.get("query", "")
        pml_path = r.get("pymol_script", "")
        if not pml_path:
            render_rows.append({"query": query, "pml": "", "png": "", "status": "SKIP_NO_PML"})
            continue
        # Derive SHORT stable PNG filename.
        # Long query/protein names exceed PyMOL/OS path limits during png export.
        # Keep identity in manifest; use compact filename for actual PNG.
        safe_role = (r.get("panel_role", "") or "PANEL").replace("/", "_").replace(" ", "_")[:24]
        safe_layer = (r.get("reference_layer", "") or "REF").replace("/", "_").replace(" ", "_")[:8]
        safe_target = (r.get("target", "") or "target").replace("/", "_").replace(" ", "_")[:32]
        key = "|".join([
            r.get("query", ""),
            r.get("protein_id", ""),
            r.get("panel_order", ""),
            r.get("panel_role", ""),
            r.get("reference_layer", ""),
            r.get("target", ""),
            pml_path,
        ])
        h = hashlib.md5(key.encode("utf-8", errors="replace")).hexdigest()[:12]
        png_name = f"panel{r.get('panel_order','X')}_{safe_role}_{safe_layer}_{safe_target}_{h}.png"
        png_path = out_png_dir / png_name
        render_rows.append({
            "query": query,
            "protein_id": r.get("protein_id", ""),
            "family": r.get("family", ""),
            "panel_order": r.get("panel_order", ""),
            "panel_role": r.get("panel_role", ""),
            "reference_layer": r.get("reference_layer", ""),
            "target": r.get("target", ""),
            "pml": str(pml_path),
            "png": str(png_path),
            "status": "PENDING",
        })

    print(f"render_pairs_built: {len(render_rows)}")

    # Write master PML that processes all renders in one PyMOL session
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pml", prefix="m10f_master_render_",
        dir=str(out_png_dir), delete=False, encoding="utf-8"
    ) as tmp:
        master_pml_path = tmp.name
        for rr in render_rows:
            if not rr["pml"]:
                continue
            pml_abs = project_root / rr["pml"] if not Path(rr["pml"]).is_absolute() else Path(rr["pml"])
            png_abs = project_root / rr["png"] if not Path(rr["png"]).is_absolute() else Path(rr["png"])
            tmp.write(f'@{pml_abs.as_posix()}\n')
            if use_ray:
                tmp.write(f'ray 1800, 1400\n')
            tmp.write(f'png "{png_abs.as_posix()}", dpi={dpi}, ray=0\n')
            tmp.write(f'reinitialize\n')
            tmp.write(f'\n')

    print(f"master_pml: {master_pml_path}")

    # Run Apptainer+PyMOL once for all renders
    cmd = [
        "apptainer", "exec",
        "--bind", f"{project_root.as_posix()}:{project_root.as_posix()}",
        str(sif),
        "pymol", "-cq", master_pml_path,
    ]
    print("COMMAND\t" + " ".join(cmd))

    rc = subprocess.run(cmd, cwd=str(project_root)).returncode

    # Collect results
    passed, failed, missing = 0, 0, 0
    for rr in render_rows:
        if not rr["png"]:
            rr["status"] = "SKIP_NO_PML"
            missing += 1
            continue
        png_abs = project_root / rr["png"] if not Path(rr["png"]).is_absolute() else Path(rr["png"])
        if png_abs.is_file() and png_abs.stat().st_size > 0:
            rr["status"] = "PASS"
            passed += 1
        else:
            rr["status"] = "FAIL_PNG_MISSING"
            failed += 1

    # Clean up master PML
    try:
        Path(master_pml_path).unlink()
    except OSError:
        pass

    # Write PNG manifest
    png_fields = ["query", "protein_id", "family", "panel_order", "panel_role",
                  "reference_layer", "target", "pml", "png", "status"]
    write_tsv(out_manifest, render_rows, png_fields)

    # Write QC report
    qc_status = "OK" if failed == 0 and rc == 0 else "WARN" if passed > 0 else "FAIL"
    qc_rows = [
        {"metric": "module",             "value": "m10f_render_all_query_pngs"},
        {"metric": "status",             "value": qc_status},
        {"metric": "mode",               "value": args.mode},
        {"metric": "panel_orders",       "value": args.panel_orders},
        {"metric": "rows_selected",      "value": str(len(target_rows))},
        {"metric": "rendered_pass",      "value": str(passed)},
        {"metric": "rendered_fail",      "value": str(failed)},
        {"metric": "rendered_skip",      "value": str(missing)},
        {"metric": "apptainer_exit_code","value": str(rc)},
        {"metric": "use_ray",            "value": str(use_ray)},
        {"metric": "dpi",                "value": str(dpi)},
        {"metric": "out_png_dir",        "value": str(out_png_dir)},
        {"metric": "png_manifest_path",  "value": str(out_manifest)},
        {"metric": "render_timestamp",   "value": timestamp},
        {"metric": "ca_only_note",       "value": "Reference pocket zero-marker expected; CA-only reference structures."},
        {"metric": "semantic_note",      "value": "Query = pLDDT confidence. PDB reference = B-factor. AFSP reference = pLDDT."},
    ]
    write_tsv(out_qc, qc_rows, ["metric", "value"])

    print(f"M10F_RENDER_COMPLETE")
    print(f"rendered_pass\t{passed}")
    print(f"rendered_fail\t{failed}")
    print(f"apptainer_exit_code\t{rc}")
    print(f"qc_status\t{qc_status}")
    print(f"png_manifest\t{out_manifest}")
    print(f"qc_report\t{out_qc}")

    return 0 if qc_status in ("OK", "WARN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
