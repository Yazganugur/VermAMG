#!/usr/bin/env python3
"""
12d_multi_reference_pocket_overlap_metrics.py

Compute query/reference top-1 pocket overlap metrics for every row in the
M10A visual overlay contract. The computation intentionally reuses the same
PyMOL alignment semantics as M10G composite figures, but writes TSV metrics
instead of rendering PNGs.

Policy:
  - Primary/rank-1 interpretation is not changed.
  - Supporting references are measured for audit/context only.
  - CA-only-like reference pocket calls remain unreliable and are flagged.
"""
from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path


METRIC_FIELDS = [
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
    "unique_reference_id",
    "visual_status",
    "reference_file_resolution_status",
    "reference_p2rank_status",
    "reference_zero_pocket_flag",
    "reference_ca_only_like",
    "reference_pocket_signal",
    "reference_pocket_interpretation",
    "query_top1_probability",
    "query_top1_score",
    "reference_top1_probability",
    "reference_top1_score",
    "query_model_pdb_portable",
    "reference_file_path_portable",
    "reference_confidence_semantics",
    "overlap_metric_status",
    "overlap_metric_note",
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
    "reference_pocket_mean_plddt",
    "reference_pocket_mean_bfactor",
    "query_conserved_residue_ids",
    "query_unique_residue_ids",
    "reference_conserved_residue_ids",
    "reference_unique_residue_ids",
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


def resolve_path(workspace: Path, row: dict[str, str], portable_key: str, full_key: str) -> Path | None:
    portable = row.get(portable_key, "").strip()
    full = row.get(full_key, "").strip()
    if portable:
        p = Path(portable)
        return p if p.is_absolute() else workspace / p
    if full:
        p = Path(full)
        return p if p.is_absolute() else workspace / p
    return None


def reference_confidence_semantics(row: dict[str, str]) -> str:
    layer = row.get("reference_layer", "")
    ref_path = row.get("reference_file_path_portable", "")
    if layer == "AFSP" or Path(ref_path).name.startswith("AF-"):
        return "REFERENCE_PLDDT"
    if layer == "PDB":
        return "REFERENCE_BFACTOR"
    return "REVIEW_REFERENCE_CONFIDENCE_SEMANTICS"


def prepare_input_rows(
    rows: list[dict[str, str]],
    workspace: Path,
    mode: str,
    only_query: set[str] | None,
    limit: int | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    prepared: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for row in rows:
        query = row.get("query", "").strip()
        if only_query and query not in only_query:
            continue

        query_pdb = resolve_path(workspace, row, "query_model_pdb_portable", "query_model_pdb")
        ref_pdb = resolve_path(workspace, row, "reference_file_path_portable", "reference_file_path")

        base = {
            "mode": mode,
            "query": query,
            "protein_id": row.get("protein_id", ""),
            "family": row.get("family", ""),
            "panel_order": row.get("panel_order", ""),
            "panel_role": row.get("panel_role", ""),
            "reference_layer": row.get("reference_layer", ""),
            "target": row.get("target", ""),
            "source_rank": row.get("source_rank", ""),
            "support_class": row.get("support_class", ""),
            "selection_reason": row.get("selection_reason", ""),
            "unique_reference_id": row.get("unique_reference_id", ""),
            "visual_status": row.get("visual_status", ""),
            "reference_file_resolution_status": row.get("reference_file_resolution_status", ""),
            "reference_p2rank_status": row.get("reference_p2rank_status", ""),
            "reference_zero_pocket_flag": row.get("reference_zero_pocket_flag", ""),
            "reference_ca_only_like": row.get("reference_ca_only_like", ""),
            "reference_pocket_signal": row.get("reference_pocket_signal", ""),
            "reference_pocket_interpretation": row.get("reference_pocket_interpretation", ""),
            "query_top1_probability": row.get("query_top1_probability", ""),
            "query_top1_score": row.get("query_top1_score", ""),
            "reference_top1_probability": row.get("reference_top1_probability", ""),
            "reference_top1_score": row.get("reference_top1_score", ""),
            "query_model_pdb_portable": row.get("query_model_pdb_portable", ""),
            "reference_file_path_portable": row.get("reference_file_path_portable", ""),
            "reference_confidence_semantics": reference_confidence_semantics(row),
            "query_pdb_abs": str(query_pdb) if query_pdb else "",
            "reference_pdb_abs": str(ref_pdb) if ref_pdb else "",
            "query_top1_residue_ids": row.get("query_top1_residue_ids", ""),
            "reference_top1_residue_ids": row.get("reference_top1_residue_ids", ""),
        }

        if not query_pdb or not query_pdb.is_file():
            skipped.append({**base, "overlap_metric_status": "MISSING_QUERY_PDB",
                            "overlap_metric_note": str(query_pdb or "")})
            continue
        if not ref_pdb or not ref_pdb.is_file():
            skipped.append({**base, "overlap_metric_status": "MISSING_REFERENCE_PDB",
                            "overlap_metric_note": str(ref_pdb or "")})
            continue

        prepared.append(base)
        if limit is not None and len(prepared) >= limit:
            break

    return prepared, skipped


def write_pymol_script(script_path: Path, input_tsv: Path, output_tsv: Path) -> None:
    script_path.parent.mkdir(parents=True, exist_ok=True)
    input_repr = repr(str(input_tsv))
    output_repr = repr(str(output_tsv))
    fields_repr = repr(METRIC_FIELDS)

    script = f"""
python
from pymol import cmd
import csv
import math
import traceback

INPUT_TSV = {input_repr}
OUTPUT_TSV = {output_repr}
FIELDS = {fields_repr}

cmd.feedback("disable", "all", "everything")

def _fmt(v, nd=3):
    if v is None:
        return "NA"
    try:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return "NA"
        return f"{{float(v):.{{nd}}f}}"
    except Exception:
        return str(v)

def _fraction(num, den):
    try:
        den = int(den)
        num = int(num)
    except Exception:
        return None
    if den <= 0:
        return None
    return num / den

def _parse_residue_ids(text):
    out = []
    for token in (text or "").replace(",", " ").split():
        if "_" not in token:
            continue
        chain, resi = token.split("_", 1)
        chain = chain.strip()
        resi = resi.strip()
        if chain and resi:
            out.append((chain, resi))
    return out

def _selection_from_residues(obj, residues, ca_only=True):
    if not residues:
        return "none"
    by_chain = {{}}
    for chain, resi in residues:
        by_chain.setdefault(chain, []).append(resi)
    pieces = []
    for chain, resis in by_chain.items():
        uniq = []
        seen = set()
        for resi in resis:
            if resi not in seen:
                seen.add(resi)
                uniq.append(resi)
        atom_part = " and name CA" if ca_only else ""
        pieces.append(f"({{obj}} and chain {{chain}}{{atom_part}} and resi {{'+'.join(uniq)}})")
    return " or ".join(pieces)

def _ca_residue_set(selection):
    model = cmd.get_model(selection)
    out = set()
    for atom in model.atom:
        if atom.name != "CA":
            continue
        try:
            resi = int(atom.resi)
        except Exception:
            continue
        out.add((atom.chain, resi))
    return out

def _residues_to_text(residues):
    return " ".join(f"{{chain}}_{{resi}}" for chain, resi in sorted(residues, key=lambda x: (x[0], x[1])))

def _mean_ca_b(selection):
    model = cmd.get_model(selection)
    vals = []
    for atom in model.atom:
        if atom.name == "CA":
            try:
                vals.append(float(atom.b))
            except Exception:
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)

def _alignment_maps(aln_object):
    info = {{}}
    for obj in ["query", "reference"]:
        model = cmd.get_model(obj)
        for atom in model.atom:
            try:
                resi_int = int(atom.resi)
            except Exception:
                continue
            info[(obj, atom.index)] = {{
                "obj": obj,
                "index": atom.index,
                "chain": atom.chain,
                "resi": resi_int,
                "name": atom.name,
            }}

    q_to_r = {{}}
    r_to_q = {{}}
    for col in cmd.get_raw_alignment(aln_object):
        atoms = [info[(model, idx)] for model, idx in col if (model, idx) in info]
        q_atoms = [a for a in atoms if a["obj"] == "query" and a["name"] == "CA"]
        r_atoms = [a for a in atoms if a["obj"] == "reference" and a["name"] == "CA"]
        if len(q_atoms) == 1 and len(r_atoms) == 1:
            q = q_atoms[0]
            r = r_atoms[0]
            q_to_r[(q["chain"], q["resi"])] = (r["chain"], r["resi"])
            r_to_q[(r["chain"], r["resi"])] = (q["chain"], q["resi"])
    return q_to_r, r_to_q

def _base_output(row):
    out = {{k: row.get(k, "") for k in FIELDS}}
    return out

def compute_row(row):
    out = _base_output(row)
    query_res = _parse_residue_ids(row.get("query_top1_residue_ids", ""))
    ref_res = _parse_residue_ids(row.get("reference_top1_residue_ids", ""))

    cmd.delete("all")
    cmd.load(row["query_pdb_abs"], "query")
    cmd.load(row["reference_pdb_abs"], "reference")

    align_result = cmd.align("reference", "query", object="aln_main")
    try:
        rmsd = float(align_result[0])
    except Exception:
        rmsd = None
    try:
        aligned_pairs = int(align_result[1])
    except Exception:
        aligned_pairs = None

    cmd.select("query_pocket_ca", _selection_from_residues("query", query_res, ca_only=True))
    cmd.select("reference_pocket_ca", _selection_from_residues("reference", ref_res, ca_only=True))

    query_pocket = _ca_residue_set("query_pocket_ca")
    reference_pocket = _ca_residue_set("reference_pocket_ca")

    q_to_r, r_to_q = _alignment_maps("aln_main")

    query_conserved = [q for q in query_pocket if q_to_r.get(q) in reference_pocket]
    query_unique = [q for q in query_pocket if q_to_r.get(q) not in reference_pocket]
    reference_conserved = [r for r in reference_pocket if r_to_q.get(r) in query_pocket]
    reference_unique = [r for r in reference_pocket if r_to_q.get(r) not in query_pocket]

    qn = len(query_pocket)
    rn = len(reference_pocket)
    qcn = len(query_conserved)
    rcn = len(reference_conserved)
    common = min(qcn, rcn)
    qfrac = _fraction(qcn, qn)
    rfrac = _fraction(rcn, rn)
    balanced = None if qfrac is None or rfrac is None else (qfrac + rfrac) / 2.0
    union = qn + rn - common
    jaccard = None if union <= 0 else common / union

    q_mean = _mean_ca_b("query_pocket_ca")
    r_mean = _mean_ca_b("reference_pocket_ca")
    ref_sem = row.get("reference_confidence_semantics", "")

    out.update({{
        "overlap_metric_status": "OK",
        "overlap_metric_note": "",
        "alignment_rmsd": _fmt(rmsd),
        "alignment_atom_pairs": "" if aligned_pairs is None else str(aligned_pairs),
        "query_pocket_n": str(qn),
        "reference_pocket_n": str(rn),
        "query_conserved_n": str(qcn),
        "query_unique_n": str(len(query_unique)),
        "reference_conserved_n": str(rcn),
        "reference_unique_n": str(len(reference_unique)),
        "query_overlap_fraction": _fmt(qfrac, 4),
        "reference_overlap_fraction": _fmt(rfrac, 4),
        "pocket_overlap_balanced_fraction": _fmt(balanced, 4),
        "pocket_overlap_jaccard_aligned_ca": _fmt(jaccard, 4),
        "query_pocket_mean_plddt": _fmt(q_mean),
        "reference_pocket_mean_plddt": _fmt(r_mean) if ref_sem == "REFERENCE_PLDDT" else "NA",
        "reference_pocket_mean_bfactor": _fmt(r_mean) if ref_sem == "REFERENCE_BFACTOR" else "NA",
        "query_conserved_residue_ids": _residues_to_text(query_conserved),
        "query_unique_residue_ids": _residues_to_text(query_unique),
        "reference_conserved_residue_ids": _residues_to_text(reference_conserved),
        "reference_unique_residue_ids": _residues_to_text(reference_unique),
    }})

    if row.get("reference_ca_only_like", "").upper() == "YES":
        out["overlap_metric_status"] = "UNRELIABLE_CA_ONLY_INPUT"
        out["overlap_metric_note"] = "Reference is CA-only-like; pocket metrics are not interpretation-grade."
    elif row.get("reference_zero_pocket_flag", "").upper() == "YES" or rn == 0:
        out["overlap_metric_status"] = "REFERENCE_ZERO_POCKET"
        out["overlap_metric_note"] = "No reference top-1 pocket residues were available."
    elif qn == 0:
        out["overlap_metric_status"] = "QUERY_ZERO_POCKET"
        out["overlap_metric_note"] = "No query top-1 pocket residues were available."

    cmd.delete("all")
    return out

with open(INPUT_TSV, newline="", encoding="utf-8", errors="replace") as inp, open(OUTPUT_TSV, "w", newline="", encoding="utf-8") as out_fh:
    reader = csv.DictReader(inp, delimiter="\\t")
    writer = csv.DictWriter(out_fh, fieldnames=FIELDS, delimiter="\\t", extrasaction="ignore", lineterminator="\\n")
    writer.writeheader()
    for idx, row in enumerate(reader, start=1):
        try:
            out = compute_row(row)
        except Exception as exc:
            out = _base_output(row)
            out["overlap_metric_status"] = "PYMOL_ROW_ERROR"
            out["overlap_metric_note"] = f"{{type(exc).__name__}}: {{exc}}"
            try:
                cmd.delete("all")
            except Exception:
                pass
        writer.writerow(out)
        if idx % 100 == 0:
            out_fh.flush()
            print(f"processed {{idx}} rows")
python end
quit
"""
    script_path.write_text(textwrap.dedent(script).lstrip(), encoding="utf-8")


def run_pymol(pymol_cmd: str, pml_path: Path) -> int:
    cmd = shlex.split(pymol_cmd) + ["-cq", str(pml_path)]
    print("RUN_PYMOL", " ".join(shlex.quote(part) for part in cmd), flush=True)
    proc = subprocess.run(cmd)
    return proc.returncode


def count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def write_qc(
    qc_path: Path,
    mode: str,
    input_rows: int,
    prepared_rows: int,
    skipped_rows: int,
    output_path: Path,
    pymol_returncode: int | None,
) -> None:
    status_counts: dict[str, int] = {}
    if output_path.exists():
        for row in read_tsv(output_path):
            key = row.get("overlap_metric_status", "")
            status_counts[key] = status_counts.get(key, 0) + 1

    error_rows = sum(n for k, n in status_counts.items() if k in {"PYMOL_ROW_ERROR", "MISSING_QUERY_PDB", "MISSING_REFERENCE_PDB"})
    qc_status = "OK" if prepared_rows > 0 and count_rows(output_path) == prepared_rows and error_rows == 0 and pymol_returncode in (0, None) else "WARN"
    rows = [
        {"metric": "module", "value": "M12D_multi_reference_pocket_overlap_metrics"},
        {"metric": "status", "value": qc_status},
        {"metric": "mode", "value": mode},
        {"metric": "contract_rows_selected", "value": str(input_rows)},
        {"metric": "prepared_rows", "value": str(prepared_rows)},
        {"metric": "skipped_missing_input_rows", "value": str(skipped_rows)},
        {"metric": "output_rows", "value": str(count_rows(output_path))},
        {"metric": "pymol_returncode", "value": "" if pymol_returncode is None else str(pymol_returncode)},
        {"metric": "output_path", "value": str(output_path)},
    ]
    for status, n in sorted(status_counts.items()):
        rows.append({"metric": f"overlap_metric_status__{status}", "value": str(n)})
    write_tsv(qc_path, rows, ["metric", "value"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute multi-reference pocket overlap metrics via PyMOL.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--mode", default="full")
    parser.add_argument("--pymol-cmd", default=os.environ.get("PYMOL_CMD", "pymol"))
    parser.add_argument("--only-query", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pml-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = workspace / contract_path
    outdir = Path(args.outdir)
    if not outdir.is_absolute():
        outdir = workspace / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    output_path = outdir / f"{args.mode}_multi_reference_pocket_overlap_metrics.tsv"
    input_path = outdir / f"{args.mode}_multi_reference_pocket_overlap_metrics_input.tsv"
    skipped_path = outdir / f"{args.mode}_multi_reference_pocket_overlap_metrics_skipped.tsv"
    pml_path = outdir / f"{args.mode}_multi_reference_pocket_overlap_metrics.pml"
    qc_path = outdir / f"{args.mode}_multi_reference_pocket_overlap_metrics_qc.tsv"

    if output_path.exists() and not args.force and not args.pml_only:
        raise SystemExit(f"ERROR: output exists; use --force to overwrite: {output_path}")

    all_rows = read_tsv(contract_path)
    only_query = set(args.only_query) if args.only_query else None
    prepared, skipped = prepare_input_rows(all_rows, workspace, args.mode, only_query, args.limit)
    write_tsv(input_path, prepared, list(prepared[0].keys()) if prepared else [
        "mode", "query", "protein_id", "family", "panel_order", "panel_role",
        "reference_layer", "target", "query_pdb_abs", "reference_pdb_abs",
        "query_top1_residue_ids", "reference_top1_residue_ids",
    ])
    write_tsv(skipped_path, skipped, list(skipped[0].keys()) if skipped else [
        "mode", "query", "protein_id", "family", "panel_order", "panel_role",
        "reference_layer", "target", "overlap_metric_status", "overlap_metric_note",
    ])
    write_pymol_script(pml_path, input_path, output_path)

    pymol_rc: int | None = None
    if not args.pml_only:
        if output_path.exists():
            output_path.unlink()
        pymol_rc = run_pymol(args.pymol_cmd, pml_path)

    write_qc(qc_path, args.mode, len(prepared) + len(skipped), len(prepared), len(skipped), output_path, pymol_rc)

    print("M12D_MULTI_REFERENCE_POCKET_OVERLAP_METRICS_DONE")
    print(f"prepared_rows\t{len(prepared)}")
    print(f"skipped_rows\t{len(skipped)}")
    print(f"output\t{output_path}")
    print(f"qc\t{qc_path}")
    print(f"pml\t{pml_path}")
    if pymol_rc not in (0, None):
        return pymol_rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
