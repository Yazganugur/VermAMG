#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

all_hits = Path(sys.argv[1])
idmap_path = Path(sys.argv[2])
primary_best = Path(sys.argv[3])
primary_classified = Path(sys.argv[4])
top5_table = Path(sys.argv[5])
qtm_max = Path(sys.argv[6])
rank_audit = Path(sys.argv[7])
neartie_audit = Path(sys.argv[8])
summary_path = Path(sys.argv[9])
pointer_path = Path(sys.argv[10])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def fnum(x):
    try:
        return float(x)
    except Exception:
        return -999999.0

def classify_afsp(row):
    qtm = fnum(row.get("qtmscore", ""))
    prob = fnum(row.get("prob", ""))
    qcov = fnum(row.get("qcov", ""))

    if qtm >= 0.8 and prob >= 0.9 and qcov >= 0.7:
        return "STRONG_AFSP_STRUCT_MATCH", "High query TM-score, high probability, and broad query coverage against AF/Swiss-Prot"
    if qtm >= 0.5 and prob >= 0.9 and qcov >= 0.5:
        return "MODERATE_AFSP_STRUCT_MATCH", "Moderate query TM-score with high probability and sufficient query coverage against AF/Swiss-Prot"
    if qtm >= 0.4 and prob >= 0.9:
        return "DOMAIN_LEVEL_OR_PARTIAL_AFSP_MATCH", "Possible partial/domain-level AF/Swiss-Prot match; inspect domain boundaries and coverage"
    return "WEAK_OR_NO_AFSP_STRUCT_MATCH", "No confident AF/Swiss-Prot structural match under current criteria"

idrows = read_tsv(idmap_path)
id_by_run = {r["run_id"]: r for r in idrows}
query_order = [r["run_id"] for r in idrows]

hits = read_tsv(all_hits)

groups = {}
for h in hits:
    groups.setdefault(h["query"], []).append(h)

hit_fields = ["query","target","evalue","bits","prob","alntmscore","qtmscore","ttmscore","lddt","qcov","tcov","qlen","tlen","batch"]
classified_fields = ["protein_id","family","habitat"] + hit_fields + ["afsp_struct_support_class","afsp_struct_support_note"]
top5_fields = ["protein_id","family","habitat","rank"] + hit_fields + ["afsp_struct_support_class","afsp_struct_support_note"]

audit_fields = [
    "query","protein_id","family",
    "rank1_target","qtmmax_target","target_same",
    "rank1_qtmscore","qtmmax_qtmscore",
    "rank1_prob","qtmmax_prob",
    "rank1_qcov","qtmmax_qcov",
    "rank1_class","qtmmax_class","class_same",
    "manual_review_flag","manual_review_reason"
]

neartie_fields = [
    "query","protein_id","family",
    "rank1_target","alternative_target",
    "alternative_rank",
    "rank1_bits","alternative_bits","delta_bits_alt_minus_rank1",
    "rank1_qtmscore","alternative_qtmscore","delta_qtmscore_alt_minus_rank1",
    "rank1_prob","alternative_prob","delta_prob_alt_minus_rank1",
    "rank1_class","alternative_class",
    "near_tie_flag","near_tie_reason"
]

rank1_rows = []
qtm_rows = []
top5_rows = []
audit_rows = []
neartie_rows = []

for q in query_order:
    hs = groups.get(q, [])
    if not hs:
        continue

    meta = id_by_run.get(q, {})
    base = {
        "protein_id": meta.get("protein_id", ""),
        "family": meta.get("family_label", ""),
        "habitat": meta.get("habitat_broad", ""),
    }

    rank1 = hs[0]
    rank1_class, rank1_note = classify_afsp(rank1)

    qtmhit = max(hs, key=lambda r: (fnum(r.get("qtmscore", "")), fnum(r.get("prob", "")), fnum(r.get("qcov", "")), fnum(r.get("bits", ""))))
    qtm_class, qtm_note = classify_afsp(qtmhit)

    r1 = dict(base)
    r1.update(rank1)
    r1["afsp_struct_support_class"] = rank1_class
    r1["afsp_struct_support_note"] = rank1_note
    rank1_rows.append(r1)

    qm = dict(base)
    qm.update(qtmhit)
    qm["afsp_struct_support_class"] = qtm_class
    qm["afsp_struct_support_note"] = qtm_note
    qtm_rows.append(qm)

    for idx, h in enumerate(hs[:5], start=1):
        cls, note = classify_afsp(h)
        tr = dict(base)
        tr["rank"] = idx
        tr.update(h)
        tr["afsp_struct_support_class"] = cls
        tr["afsp_struct_support_note"] = note
        top5_rows.append(tr)

    target_same = "YES" if rank1.get("target") == qtmhit.get("target") else "NO"
    class_same = "YES" if rank1_class == qtm_class else "NO"

    reason = []
    if target_same == "NO":
        reason.append("rank1_target_differs_from_qtmmax")
    if class_same == "NO":
        reason.append("class_differs_between_rank1_and_qtmmax")

    audit_rows.append({
        "query": q,
        "protein_id": meta.get("protein_id", ""),
        "family": meta.get("family_label", ""),
        "rank1_target": rank1.get("target", ""),
        "qtmmax_target": qtmhit.get("target", ""),
        "target_same": target_same,
        "rank1_qtmscore": rank1.get("qtmscore", ""),
        "qtmmax_qtmscore": qtmhit.get("qtmscore", ""),
        "rank1_prob": rank1.get("prob", ""),
        "qtmmax_prob": qtmhit.get("prob", ""),
        "rank1_qcov": rank1.get("qcov", ""),
        "qtmmax_qcov": qtmhit.get("qcov", ""),
        "rank1_class": rank1_class,
        "qtmmax_class": qtm_class,
        "class_same": class_same,
        "manual_review_flag": "YES" if reason else "NO",
        "manual_review_reason": ";".join(reason),
    })

    r1_bits = fnum(rank1.get("bits", ""))
    r1_qtm = fnum(rank1.get("qtmscore", ""))
    r1_prob = fnum(rank1.get("prob", ""))

    for idx, h in enumerate(hs[1:5], start=2):
        alt_class, alt_note = classify_afsp(h)
        alt_bits = fnum(h.get("bits", ""))
        alt_qtm = fnum(h.get("qtmscore", ""))
        alt_prob = fnum(h.get("prob", ""))

        near_reasons = []
        if r1_bits > 0 and alt_bits >= 0.95 * r1_bits:
            near_reasons.append("bits_within_95pct_of_rank1")
        if alt_qtm >= r1_qtm + 0.03:
            near_reasons.append("alt_qtm_gt_rank1_by_0.03")
        if alt_class != rank1_class:
            near_reasons.append("alt_class_differs_from_rank1")

        neartie_rows.append({
            "query": q,
            "protein_id": meta.get("protein_id", ""),
            "family": meta.get("family_label", ""),
            "rank1_target": rank1.get("target", ""),
            "alternative_target": h.get("target", ""),
            "alternative_rank": idx,
            "rank1_bits": rank1.get("bits", ""),
            "alternative_bits": h.get("bits", ""),
            "delta_bits_alt_minus_rank1": round(alt_bits - r1_bits, 6),
            "rank1_qtmscore": rank1.get("qtmscore", ""),
            "alternative_qtmscore": h.get("qtmscore", ""),
            "delta_qtmscore_alt_minus_rank1": round(alt_qtm - r1_qtm, 6),
            "rank1_prob": rank1.get("prob", ""),
            "alternative_prob": h.get("prob", ""),
            "delta_prob_alt_minus_rank1": round(alt_prob - r1_prob, 6),
            "rank1_class": rank1_class,
            "alternative_class": alt_class,
            "near_tie_flag": "YES" if near_reasons else "NO",
            "near_tie_reason": ";".join(near_reasons),
        })

with primary_best.open("w") as f:
    w = csv.DictWriter(f, fieldnames=hit_fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for r in rank1_rows:
        w.writerow({k: r.get(k, "") for k in hit_fields})

with primary_classified.open("w") as f:
    w = csv.DictWriter(f, fieldnames=classified_fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for r in rank1_rows:
        w.writerow({k: r.get(k, "") for k in classified_fields})

with top5_table.open("w") as f:
    w = csv.DictWriter(f, fieldnames=top5_fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for r in top5_rows:
        w.writerow({k: r.get(k, "") for k in top5_fields})

with qtm_max.open("w") as f:
    w = csv.DictWriter(f, fieldnames=classified_fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    for r in qtm_rows:
        w.writerow({k: r.get(k, "") for k in classified_fields})

with rank_audit.open("w") as f:
    w = csv.DictWriter(f, fieldnames=audit_fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    w.writerows(audit_rows)

with neartie_audit.open("w") as f:
    w = csv.DictWriter(f, fieldnames=neartie_fields, delimiter="\t", lineterminator="\n")
    w.writeheader()
    w.writerows(neartie_rows)

class_counts = {}
for r in rank1_rows:
    cls = r.get("afsp_struct_support_class", "")
    class_counts[cls] = class_counts.get(cls, 0) + 1

with summary_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    w.writerow(["best_hit_rule", "foldseek_rank1_default_output_order"])
    w.writerow(["classification_rule", "Bölüm4_qtmscore_prob_qcov_thresholds"])
    w.writerow(["reference_layer", "AFSP_predicted_structural_reference"])
    w.writerow(["all_hit_rows", len(hits)])
    w.writerow(["query_records", len(query_order)])
    w.writerow(["rank1_besthit_rows", len(rank1_rows)])
    w.writerow(["top5_rows", len(top5_rows)])
    w.writerow(["qtmmax_audit_rows", len(qtm_rows)])
    w.writerow(["rank1_vs_qtmmax_target_diff_n", sum(1 for r in audit_rows if r["target_same"] == "NO")])
    w.writerow(["rank1_vs_qtmmax_class_diff_n", sum(1 for r in audit_rows if r["class_same"] == "NO")])
    w.writerow(["manual_review_flag_n", sum(1 for r in audit_rows if r["manual_review_flag"] == "YES")])
    w.writerow(["neartie_flag_n", sum(1 for r in neartie_rows if r["near_tie_flag"] == "YES")])
    for cls in sorted(class_counts):
        w.writerow([cls, class_counts[cls]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["afsp_primary_besthit_classified", str(primary_classified), "AFSP rank-1 classified table; complementary predicted-structure downstream input"])
    w.writerow(["afsp_primary_besthit_rank1", str(primary_best), "Raw AFSP rank-1 Foldseek best hit table"])
    w.writerow(["afsp_top5_hits", str(top5_table), "AFSP top-5 audit/evidence table"])
    w.writerow(["afsp_qtmmax_audit", str(qtm_max), "Secondary AFSP qTM-max audit table"])
    w.writerow(["afsp_rank1_vs_qtmmax_audit", str(rank_audit), "Manual review flags for AFSP rank1 vs qTM-max differences"])
    w.writerow(["afsp_neartie_top5_audit", str(neartie_audit), "AFSP top-5 near-tie and alternative-support audit"])
    w.writerow(["afsp_canonical_summary", str(summary_path), "Canonical AFSP Foldseek summary"])

print("primary_classified:", primary_classified)
print("top5_table:", top5_table)
print("qtmmax_audit:", qtm_max)
print("rank_audit:", rank_audit)
print("neartie_audit:", neartie_audit)
print("summary:", summary_path)
print("pointer:", pointer_path)
print("rank1_besthit_rows:", len(rank1_rows))
print("top5_rows:", len(top5_rows))
print("manual_review_flag_n:", sum(1 for r in audit_rows if r["manual_review_flag"] == "YES"))
print("neartie_flag_n:", sum(1 for r in neartie_rows if r["near_tie_flag"] == "YES"))
