#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

if len(sys.argv) != 8:
    raise SystemExit("Usage: compare_pdb_foldseek_regression.py OLD_CLASSIFIED OLD_ALL NEW_BEST NEW_ALL IDMAP COMPARISON SUMMARY")

old_classified = Path(sys.argv[1])
old_all = Path(sys.argv[2])
new_best = Path(sys.argv[3])
new_all = Path(sys.argv[4])
idmap_path = Path(sys.argv[5])
comparison_path = Path(sys.argv[6])
summary_path = Path(sys.argv[7])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def fnum(x):
    try:
        return float(x)
    except Exception:
        return None

def fdiff(a, b):
    aa = fnum(a)
    bb = fnum(b)
    if aa is None or bb is None:
        return ""
    return round(bb - aa, 6)

def old_key_from_old_query(q):
    m = re.search(r"(T1P\d{3})", q or "")
    return m.group(1) if m else ""

def new_key_from_run_id(run_id):
    m = re.search(r"QBENCH0*(\d+)", run_id or "")
    if not m:
        return ""
    return f"T1P{int(m.group(1)):03d}"

idmap = read_tsv(idmap_path)
new_to_protein = {r["run_id"]: r.get("protein_id", "") for r in idmap}
new_to_family = {r["run_id"]: r.get("family_label", "") for r in idmap}

old_rows = read_tsv(old_classified)
new_rows = read_tsv(new_best)

old_by_key = {}
for r in old_rows:
    key = old_key_from_old_query(r.get("query", "")) or old_key_from_old_query(r.get("protein_id", ""))
    if key:
        old_by_key[key] = r

new_by_key = {}
for r in new_rows:
    key = new_key_from_run_id(r.get("query", ""))
    if key:
        new_by_key[key] = r

comparison_rows = []

all_keys = sorted(set(old_by_key) | set(new_by_key))

for key in all_keys:
    old = old_by_key.get(key, {})
    new = new_by_key.get(key, {})

    new_run = new.get("query", "")
    protein_id = new_to_protein.get(new_run, old.get("protein_id", ""))
    family = new_to_family.get(new_run, old.get("family", ""))

    old_target = old.get("target", "")
    new_target = new.get("target", "")

    old_qtm = old.get("qtmscore", "")
    new_qtm = new.get("qtmscore", "")
    old_prob = old.get("prob", "")
    new_prob = new.get("prob", "")
    old_qcov = old.get("qcov", "")
    new_qcov = new.get("qcov", "")
    old_tcov = old.get("tcov", "")
    new_tcov = new.get("tcov", "")

    target_same = "YES" if old_target and new_target and old_target == new_target else "NO"

    old_class = old.get("pdb_struct_support_class", "")
    old_note = old.get("pdb_struct_support_note", "")

    # New class not yet officially produced by M06; infer only for regression diagnostics.
    qtm = fnum(new_qtm)
    prob = fnum(new_prob)
    qcov = fnum(new_qcov)
    tcov = fnum(new_tcov)

    if qtm is None or prob is None:
        new_diag_class = "NO_NUMERIC_SCORE"
    elif qtm >= 0.70 and prob >= 0.90 and (qcov is None or qcov >= 0.70):
        new_diag_class = "STRONG_STRUCTURAL_SUPPORT_DIAG"
    elif qtm >= 0.45 and prob >= 0.70:
        new_diag_class = "MODERATE_STRUCTURAL_SUPPORT_DIAG"
    elif qtm >= 0.30 or (qcov is not None and qcov >= 0.70 and tcov is not None and tcov < 0.70):
        new_diag_class = "DOMAIN_PARTIAL_OR_WEAK_DIAG"
    else:
        new_diag_class = "WEAK_STRUCTURAL_SUPPORT_DIAG"

    comparison_rows.append({
        "old_key": key,
        "protein_id": protein_id,
        "family": family,
        "old_query": old.get("query", ""),
        "new_query": new_run,
        "old_target": old_target,
        "new_target": new_target,
        "target_same": target_same,
        "old_qtmscore": old_qtm,
        "new_qtmscore": new_qtm,
        "delta_qtmscore_new_minus_old": fdiff(old_qtm, new_qtm),
        "old_prob": old_prob,
        "new_prob": new_prob,
        "delta_prob_new_minus_old": fdiff(old_prob, new_prob),
        "old_qcov": old_qcov,
        "new_qcov": new_qcov,
        "delta_qcov_new_minus_old": fdiff(old_qcov, new_qcov),
        "old_tcov": old_tcov,
        "new_tcov": new_tcov,
        "delta_tcov_new_minus_old": fdiff(old_tcov, new_tcov),
        "old_pdb_struct_support_class": old_class,
        "new_pdb_diag_class": new_diag_class,
        "old_pdb_struct_support_note": old_note,
        "comparison_status": "",
    })

for r in comparison_rows:
    problems = []
    if not r["old_query"]:
        problems.append("missing_old")
    if not r["new_query"]:
        problems.append("missing_new")
    if r["target_same"] != "YES":
        problems.append("target_changed")

    dq = fnum(r["delta_qtmscore_new_minus_old"])
    dp = fnum(r["delta_prob_new_minus_old"])

    if dq is not None and abs(dq) > 0.05:
        problems.append("qtmscore_delta_gt_0.05")
    if dp is not None and abs(dp) > 0.10:
        problems.append("prob_delta_gt_0.10")

    r["comparison_status"] = "OK" if not problems else ",".join(problems)

fields = [
    "old_key", "protein_id", "family",
    "old_query", "new_query",
    "old_target", "new_target", "target_same",
    "old_qtmscore", "new_qtmscore", "delta_qtmscore_new_minus_old",
    "old_prob", "new_prob", "delta_prob_new_minus_old",
    "old_qcov", "new_qcov", "delta_qcov_new_minus_old",
    "old_tcov", "new_tcov", "delta_tcov_new_minus_old",
    "old_pdb_struct_support_class", "new_pdb_diag_class",
    "old_pdb_struct_support_note",
    "comparison_status",
]

write_tsv(comparison_path, comparison_rows, fields)

old_all_n = sum(1 for _ in old_all.open()) - 1
new_all_n = sum(1 for _ in new_all.open()) - 1

n = len(comparison_rows)
target_same_n = sum(1 for r in comparison_rows if r["target_same"] == "YES")
ok_n = sum(1 for r in comparison_rows if r["comparison_status"] == "OK")
missing_old_n = sum(1 for r in comparison_rows if "missing_old" in r["comparison_status"])
missing_new_n = sum(1 for r in comparison_rows if "missing_new" in r["comparison_status"])
target_changed_n = sum(1 for r in comparison_rows if "target_changed" in r["comparison_status"])

with summary_path.open("w") as f:
    writer = csv.writer(f, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerow(["old_all_hit_rows", old_all_n])
    writer.writerow(["new_all_hit_rows", new_all_n])
    writer.writerow(["delta_all_hit_rows_new_minus_old", new_all_n - old_all_n])
    writer.writerow(["comparison_rows", n])
    writer.writerow(["target_same_n", target_same_n])
    writer.writerow(["target_changed_n", target_changed_n])
    writer.writerow(["ok_n", ok_n])
    writer.writerow(["missing_old_n", missing_old_n])
    writer.writerow(["missing_new_n", missing_new_n])

print("comparison:", comparison_path)
print("summary:", summary_path)
print("old_all_hit_rows:", old_all_n)
print("new_all_hit_rows:", new_all_n)
print("delta_all_hit_rows_new_minus_old:", new_all_n - old_all_n)
print("comparison_rows:", n)
print("target_same_n:", target_same_n)
print("target_changed_n:", target_changed_n)
print("ok_n:", ok_n)
