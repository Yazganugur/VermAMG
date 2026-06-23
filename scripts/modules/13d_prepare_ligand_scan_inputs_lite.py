#!/usr/bin/env python3
import argparse
import csv
from collections import Counter
from pathlib import Path


def read_tsv(path):
    with Path(path).open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def scan_hetatm(pdb_path):
    path = Path(pdb_path)
    if not path.exists():
        return {
            "atom_lines": "0", "hetatm_lines": "0",
            "unique_ligand_codes": "", "ligand_code_counts": "",
            "hetatm_chain_counts": "", "example_hetatm_lines": "",
            "hetatm_status": "REFERENCE_FILE_MISSING",
        }
    atom_n = 0
    het_lines = []
    code_ctr = Counter()
    chain_ctr = Counter()
    try:
        with path.open(errors="replace") as fh:
            for line in fh:
                rec = line[:6]
                if rec in ("ATOM  ", "ATOM  "):
                    atom_n += 1
                elif rec == "HETATM":
                    het_lines.append(line.rstrip())
                    resn = line[17:20].strip()
                    chain = line[21:22].strip()
                    if resn:
                        code_ctr[resn] += 1
                    if chain:
                        chain_ctr[chain] += 1
    except Exception:
        return {
            "atom_lines": "0", "hetatm_lines": "0",
            "unique_ligand_codes": "", "ligand_code_counts": "",
            "hetatm_chain_counts": "", "example_hetatm_lines": "",
            "hetatm_status": "HETATM_SCAN_ERROR",
        }
    if not het_lines:
        return {
            "atom_lines": str(atom_n), "hetatm_lines": "0",
            "unique_ligand_codes": "", "ligand_code_counts": "",
            "hetatm_chain_counts": "", "example_hetatm_lines": "",
            "hetatm_status": "NO_HETATM_APO_OR_CLEAN_PDB",
        }
    return {
        "atom_lines": str(atom_n),
        "hetatm_lines": str(len(het_lines)),
        "unique_ligand_codes": ";".join(sorted(code_ctr.keys())),
        "ligand_code_counts": ";".join(f"{k}:{v}" for k, v in sorted(code_ctr.items())),
        "hetatm_chain_counts": ";".join(f"{k}:{v}" for k, v in sorted(chain_ctr.items())),
        "example_hetatm_lines": " || ".join(het_lines[:3]),
        "hetatm_status": "HAS_HETATM",
    }


def safe_het_row(status):
    return {
        "atom_lines": "0", "hetatm_lines": "0",
        "unique_ligand_codes": "", "ligand_code_counts": "",
        "hetatm_chain_counts": "", "example_hetatm_lines": "",
        "hetatm_status": status,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--visual-contract", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    mode = args.mode
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    contract = read_tsv(args.visual_contract)

    scan_map_rows = []
    hetatm_rows = []
    seen_paths = set()

    for r in contract:
        ref_path = r.get("reference_file_path_portable") or r.get("reference_file_path", "")
        ref_exists = r.get("reference_file_exists", "")
        layer = r.get("reference_layer", "")
        ca_only = r.get("reference_ca_only_like", "")
        pocket_signal = r.get("reference_pocket_signal", "")
        pocket_interp = r.get("reference_pocket_interpretation", "")

        if ca_only == "YES":
            scan_eligible = "NO"
            scan_note = "CA_ONLY_MATERIALIZED_NOT_CRYSTAL_PDB"
        elif layer != "PDB":
            scan_eligible = "NO"
            scan_note = "AFSP_OR_NON_PDB_REFERENCE_NO_CRYSTAL_LIGAND_EXPECTED"
        elif ref_exists != "YES":
            scan_eligible = "NO"
            scan_note = "REFERENCE_FILE_MISSING"
        else:
            scan_eligible = "YES"
            scan_note = "PDB_FILE_AVAILABLE_FOR_HETATM_SCAN"

        scan_map_rows.append({
            "mode": mode,
            "query": r.get("query", ""),
            "protein_id": r.get("protein_id", ""),
            "family": r.get("family", ""),
            "panel_order": r.get("panel_order", ""),
            "panel_role": r.get("panel_role", ""),
            "reference_layer": layer,
            "target": r.get("target", ""),
            "reference_file_path": ref_path,
            "reference_file_exists": ref_exists,
            "scan_eligible_for_ligand_hetatm": scan_eligible,
            "scan_eligibility_note": scan_note,
            "reference_p2rank_status": r.get("reference_p2rank_status", ""),
            "reference_zero_pocket_flag": r.get("reference_zero_pocket_flag", ""),
            "reference_top1_pocket_probability": r.get("reference_top1_pocket_probability", ""),
            "reference_ca_only_like": ca_only,
            "reference_pocket_signal": pocket_signal,
            "reference_pocket_interpretation": pocket_interp,
        })

        if ref_path and ref_path not in seen_paths:
            seen_paths.add(ref_path)
            if scan_eligible == "YES":
                het = scan_hetatm(ref_path)
            elif ca_only == "YES":
                het = safe_het_row("CA_ONLY_NOT_SCANNED")
            else:
                het = safe_het_row("NOT_SCAN_ELIGIBLE")
            hetatm_rows.append({
                "reference_file_path": ref_path,
                "reference_layer": layer,
                "target": r.get("target", ""),
                **het,
            })

    scan_map_fields = [
        "mode", "query", "protein_id", "family",
        "panel_order", "panel_role", "reference_layer", "target",
        "reference_file_path", "reference_file_exists",
        "scan_eligible_for_ligand_hetatm", "scan_eligibility_note",
        "reference_p2rank_status", "reference_zero_pocket_flag",
        "reference_top1_pocket_probability", "reference_ca_only_like",
        "reference_pocket_signal", "reference_pocket_interpretation",
    ]
    hetatm_fields = [
        "reference_file_path", "reference_layer", "target",
        "atom_lines", "hetatm_lines", "unique_ligand_codes",
        "ligand_code_counts", "hetatm_chain_counts",
        "example_hetatm_lines", "hetatm_status",
    ]

    scan_map_path = outdir / f"{mode}_m13d_primary_supporting_reference_ligand_scan_map.tsv"
    hetatm_path = outdir / f"{mode}_m13d_reference_pdb_hetatm_inventory.tsv"

    write_tsv(scan_map_path, scan_map_rows, scan_map_fields)
    write_tsv(hetatm_path, hetatm_rows, hetatm_fields)

    ptr_rows = [
        {"artifact_key": "m13d_ligand_scan_map_lite", "path": str(scan_map_path),
         "role": "M13D scan eligibility map (lite/local, CA-only safe)"},
        {"artifact_key": "m13d_reference_hetatm_inventory_lite", "path": str(hetatm_path),
         "role": "M13D HETATM inventory for available PDB reference files (lite/local)"},
    ]
    ptr = Path("pipeline_state/artifacts/m13d_ligand_scan_inputs_lite_pointer.tsv")
    write_tsv(ptr, ptr_rows, ["artifact_key", "path", "role"])

    ca_only_n = sum(
        r["scan_eligibility_note"] == "CA_ONLY_MATERIALIZED_NOT_CRYSTAL_PDB"
        for r in scan_map_rows
    )
    afsp_n = sum(
        r["scan_eligibility_note"] == "AFSP_OR_NON_PDB_REFERENCE_NO_CRYSTAL_LIGAND_EXPECTED"
        for r in scan_map_rows
    )
    eligible_n = sum(r["scan_eligible_for_ligand_hetatm"] == "YES" for r in scan_map_rows)

    print("M13D_LIGAND_SCAN_INPUTS_LITE_OK")
    print("scan_map", scan_map_path)
    print("scan_map_rows", len(scan_map_rows))
    print("scan_eligible_n", eligible_n)
    print("ca_only_not_scanned_n", ca_only_n)
    print("afsp_not_scanned_n", afsp_n)
    print("hetatm_inventory", hetatm_path)
    print("hetatm_inventory_rows", len(hetatm_rows))
    print("pointer", ptr)


if __name__ == "__main__":
    main()
