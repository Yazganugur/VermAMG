#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

old_pkg = Path(sys.argv[1])
new_summary = Path(sys.argv[2])
old_new_cf = Path(sys.argv[3])
out_table = Path(sys.argv[4])
out_summary = Path(sys.argv[5])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def fnum(x):
    try:
        return float(x)
    except Exception:
        return None

def count_pdb(path):
    atom = 0
    ca = 0
    residues = []
    if not path or not Path(path).exists():
        return atom, ca, residues
    with open(path) as f:
        for line in f:
            if line.startswith("ATOM"):
                atom += 1
                parts = line.split()
                if len(parts) > 3 and parts[2] == "CA":
                    ca += 1
                    residues.append(parts[3])
    return atom, ca, residues

def old_key_from_name(name):
    m = re.search(r"(T1P\d{3})", name)
    return m.group(1) if m else ""

cf_rows = read_tsv(old_new_cf)

rows = []
for r in cf_rows:
    key = r["old_key"]
    old_pdb = Path(r["old_pdb"]) if r.get("old_pdb") else None
    new_pdb = Path(r["new_pdb"]) if r.get("new_pdb") else None

    old_atom, old_ca, old_res = count_pdb(old_pdb)
    new_atom, new_ca, new_res = count_pdb(new_pdb)

    old_size = old_pdb.stat().st_size if old_pdb and old_pdb.exists() else 0
    new_size = new_pdb.stat().st_size if new_pdb and new_pdb.exists() else 0

    old_plddt = r.get("old_plddt_mean", "")
    new_plddt = r.get("new_plddt_mean", "")
    old_ptm = r.get("old_ptm", "")
    new_ptm = r.get("new_ptm", "")

    dp = ""
    if fnum(old_plddt) is not None and fnum(new_plddt) is not None:
        dp = round(fnum(new_plddt) - fnum(old_plddt), 4)

    dtm = ""
    if fnum(old_ptm) is not None and fnum(new_ptm) is not None:
        dtm = round(fnum(new_ptm) - fnum(old_ptm), 4)

    problems = []
    if not old_pdb or not old_pdb.exists():
        problems.append("old_pdb_missing")
    if not new_pdb or not new_pdb.exists():
        problems.append("new_pdb_missing")
    if old_ca != new_ca:
        problems.append("ca_count_changed")
    if old_res and new_res and old_res != new_res:
        problems.append("ca_residue_sequence_changed")
    if isinstance(dp, float) and abs(dp) > 1.0:
        problems.append("plddt_delta_gt_1")
    if isinstance(dtm, float) and abs(dtm) > 0.05:
        problems.append("ptm_delta_gt_0.05")

    status = "OK" if not problems else ",".join(problems)

    rows.append({
        "old_key": key,
        "new_run_id": r.get("new_run_id", ""),
        "protein_id": r.get("protein_id", ""),
        "family_label": r.get("family_label", ""),
        "old_pdb": str(old_pdb) if old_pdb else "",
        "new_pdb": str(new_pdb) if new_pdb else "",
        "old_file_size": old_size,
        "new_file_size": new_size,
        "delta_file_size": new_size - old_size,
        "old_atom_lines": old_atom,
        "new_atom_lines": new_atom,
        "delta_atom_lines": new_atom - old_atom,
        "old_ca_atoms": old_ca,
        "new_ca_atoms": new_ca,
        "delta_ca_atoms": new_ca - old_ca,
        "old_plddt_mean": old_plddt,
        "new_plddt_mean": new_plddt,
        "delta_plddt_mean": dp,
        "old_ptm": old_ptm,
        "new_ptm": new_ptm,
        "delta_ptm": dtm,
        "model_content_status": status,
    })

fields = [
    "old_key","new_run_id","protein_id","family_label",
    "old_pdb","new_pdb",
    "old_file_size","new_file_size","delta_file_size",
    "old_atom_lines","new_atom_lines","delta_atom_lines",
    "old_ca_atoms","new_ca_atoms","delta_ca_atoms",
    "old_plddt_mean","new_plddt_mean","delta_plddt_mean",
    "old_ptm","new_ptm","delta_ptm",
    "model_content_status"
]

with out_table.open("w") as f:
    w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

n = len(rows)
ok_n = sum(1 for r in rows if r["model_content_status"] == "OK")
changed_ca_n = sum(1 for r in rows if "ca_count_changed" in r["model_content_status"])
seq_changed_n = sum(1 for r in rows if "ca_residue_sequence_changed" in r["model_content_status"])
plddt_big_n = sum(1 for r in rows if "plddt_delta_gt_1" in r["model_content_status"])
ptm_big_n = sum(1 for r in rows if "ptm_delta_gt_0.05" in r["model_content_status"])

with out_summary.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    w.writerow(["comparison_rows", n])
    w.writerow(["ok_n", ok_n])
    w.writerow(["non_ok_n", n - ok_n])
    w.writerow(["ca_count_changed_n", changed_ca_n])
    w.writerow(["ca_residue_sequence_changed_n", seq_changed_n])
    w.writerow(["plddt_delta_gt_1_n", plddt_big_n])
    w.writerow(["ptm_delta_gt_0.05_n", ptm_big_n])

print("out_table:", out_table)
print("out_summary:", out_summary)
print("comparison_rows:", n)
print("ok_n:", ok_n)
print("non_ok_n:", n-ok_n)
