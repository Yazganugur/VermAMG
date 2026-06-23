#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

old_all = Path(sys.argv[1])
old_classified = Path(sys.argv[2])
new_all = Path(sys.argv[3])
idmap_path = Path(sys.argv[4])
audit_table = Path(sys.argv[5])
audit_summary = Path(sys.argv[6])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def fnum(x):
    try:
        return float(x)
    except Exception:
        return -999999.0

def old_key_from_query(q):
    m = re.search(r"(T1P\d{3})", q or "")
    return m.group(1) if m else ""

def new_key_from_query(q):
    m = re.search(r"QBENCH0*(\d+)", q or "")
    if not m:
        return ""
    return f"T1P{int(m.group(1)):03d}"

def pdb_class(row):
    qtm = fnum(row.get("qtmscore", ""))
    prob = fnum(row.get("prob", ""))
    qcov = fnum(row.get("qcov", ""))

    if qtm >= 0.8 and prob >= 0.9 and qcov >= 0.7:
        return "STRONG_PDB_STRUCT_MATCH", 4
    if qtm >= 0.5 and prob >= 0.9 and qcov >= 0.5:
        return "MODERATE_PDB_STRUCT_MATCH", 3
    if qtm >= 0.4 and prob >= 0.9:
        return "DOMAIN_LEVEL_OR_PARTIAL_PDB_MATCH", 2
    return "WEAK_OR_NO_PDB_STRUCT_MATCH", 1

def choose_first(rows):
    return rows[0] if rows else {}

def choose_bits(rows):
    return max(rows, key=lambda r: fnum(r.get("bits", ""))) if rows else {}

def choose_qtm(rows):
    return max(rows, key=lambda r: (fnum(r.get("qtmscore", "")), fnum(r.get("prob", "")), fnum(r.get("qcov", "")), fnum(r.get("bits", "")))) if rows else {}

def choose_canonical(rows):
    if not rows:
        return {}
    def key(r):
        cls, rank = pdb_class(r)
        return (
            rank,
            fnum(r.get("qtmscore", "")),
            fnum(r.get("prob", "")),
            fnum(r.get("qcov", "")),
            fnum(r.get("bits", "")),
        )
    return max(rows, key=key)

def group_rows(rows, keyfunc):
    d = {}
    for r in rows:
        k = keyfunc(r.get("query", ""))
        if k:
            d.setdefault(k, []).append(r)
    return d

old_all_rows = read_tsv(old_all)
new_all_rows = read_tsv(new_all)
old_class_rows = read_tsv(old_classified)

old_class_by_key = {}
for r in old_class_rows:
    k = old_key_from_query(r.get("query", ""))
    if k:
        old_class_by_key[k] = r

old_groups = group_rows(old_all_rows, old_key_from_query)
new_groups = group_rows(new_all_rows, new_key_from_query)

methods = {
    "first": choose_first,
    "bits_max": choose_bits,
    "qtm_max": choose_qtm,
    "canonical_structural": choose_canonical,
}

audit_rows = []

for key in sorted(set(old_class_by_key) | set(old_groups) | set(new_groups)):
    old_expected = old_class_by_key.get(key, {})
    old_expected_target = old_expected.get("target", "")
    old_expected_class = old_expected.get("pdb_struct_support_class", "")

    old_method_targets = {}
    new_method_targets = {}
    old_method_classes = {}
    new_method_classes = {}

    for mname, func in methods.items():
        o = func(old_groups.get(key, []))
        n = func(new_groups.get(key, []))

        old_method_targets[mname] = o.get("target", "")
        new_method_targets[mname] = n.get("target", "")

        old_method_classes[mname] = pdb_class(o)[0] if o else ""
        new_method_classes[mname] = pdb_class(n)[0] if n else ""

    audit_rows.append({
        "old_key": key,
        "old_reported_target": old_expected_target,
        "old_reported_class": old_expected_class,

        "old_first_target": old_method_targets["first"],
        "old_bits_target": old_method_targets["bits_max"],
        "old_qtm_target": old_method_targets["qtm_max"],
        "old_canonical_target": old_method_targets["canonical_structural"],

        "new_first_target": new_method_targets["first"],
        "new_bits_target": new_method_targets["bits_max"],
        "new_qtm_target": new_method_targets["qtm_max"],
        "new_canonical_target": new_method_targets["canonical_structural"],

        "old_reported_equals_old_first": "YES" if old_expected_target == old_method_targets["first"] else "NO",
        "old_reported_equals_old_bits": "YES" if old_expected_target == old_method_targets["bits_max"] else "NO",
        "old_reported_equals_old_qtm": "YES" if old_expected_target == old_method_targets["qtm_max"] else "NO",
        "old_reported_equals_old_canonical": "YES" if old_expected_target == old_method_targets["canonical_structural"] else "NO",

        "new_bits_equals_old_reported": "YES" if new_method_targets["bits_max"] == old_expected_target else "NO",
        "new_qtm_equals_old_reported": "YES" if new_method_targets["qtm_max"] == old_expected_target else "NO",
        "new_canonical_equals_old_reported": "YES" if new_method_targets["canonical_structural"] == old_expected_target else "NO",

        "old_canonical_class": old_method_classes["canonical_structural"],
        "new_canonical_class": new_method_classes["canonical_structural"],
        "canonical_class_same_old_vs_new": "YES" if old_method_classes["canonical_structural"] == new_method_classes["canonical_structural"] else "NO",
    })

fields = [
    "old_key",
    "old_reported_target",
    "old_reported_class",
    "old_first_target",
    "old_bits_target",
    "old_qtm_target",
    "old_canonical_target",
    "new_first_target",
    "new_bits_target",
    "new_qtm_target",
    "new_canonical_target",
    "old_reported_equals_old_first",
    "old_reported_equals_old_bits",
    "old_reported_equals_old_qtm",
    "old_reported_equals_old_canonical",
    "new_bits_equals_old_reported",
    "new_qtm_equals_old_reported",
    "new_canonical_equals_old_reported",
    "old_canonical_class",
    "new_canonical_class",
    "canonical_class_same_old_vs_new",
]

with audit_table.open("w") as f:
    w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    w.writerows(audit_rows)

def count_yes(col):
    return sum(1 for r in audit_rows if r[col] == "YES")

with audit_summary.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric", "value"])
    w.writerow(["n", len(audit_rows)])
    w.writerow(["old_reported_equals_old_first", count_yes("old_reported_equals_old_first")])
    w.writerow(["old_reported_equals_old_bits", count_yes("old_reported_equals_old_bits")])
    w.writerow(["old_reported_equals_old_qtm", count_yes("old_reported_equals_old_qtm")])
    w.writerow(["old_reported_equals_old_canonical", count_yes("old_reported_equals_old_canonical")])
    w.writerow(["new_bits_equals_old_reported", count_yes("new_bits_equals_old_reported")])
    w.writerow(["new_qtm_equals_old_reported", count_yes("new_qtm_equals_old_reported")])
    w.writerow(["new_canonical_equals_old_reported", count_yes("new_canonical_equals_old_reported")])
    w.writerow(["canonical_class_same_old_vs_new", count_yes("canonical_class_same_old_vs_new")])

print("audit_table:", audit_table)
print("audit_summary:", audit_summary)
print("n:", len(audit_rows))
