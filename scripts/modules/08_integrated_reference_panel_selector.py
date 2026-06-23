#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
from collections import defaultdict, Counter

if len(sys.argv) != 16:
    raise SystemExit(
        "Usage: 08_integrated_reference_panel_selector.py "
        "PDB_PRIMARY PDB_TOP5 PDB_QTMMAX PDB_RANK_AUDIT PDB_NEARTIE "
        "AFSP_PRIMARY AFSP_TOP5 AFSP_QTMMAX AFSP_RANK_AUDIT AFSP_NEARTIE "
        "DECISION PANEL MANUAL SUMMARY POINTER"
    )

(
    pdb_primary_path,
    pdb_top5_path,
    pdb_qtmmax_path,
    pdb_rank_audit_path,
    pdb_neartie_path,
    afsp_primary_path,
    afsp_top5_path,
    afsp_qtmmax_path,
    afsp_rank_audit_path,
    afsp_neartie_path,
    decision_path,
    panel_path,
    manual_path,
    summary_path,
    pointer_path,
) = map(Path, sys.argv[1:])

def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))

def write_tsv(path, rows, fields):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def fnum(x):
    try:
        return float(x)
    except Exception:
        return -999999.0

def support_level(cls):
    cls = cls or ""
    if "STRONG" in cls:
        return 4
    if "MODERATE" in cls:
        return 3
    if "DOMAIN_LEVEL" in cls or "PARTIAL" in cls:
        return 2
    return 1

def is_meaningful(cls):
    return support_level(cls) >= 2

def key_by_query(rows):
    return {r["query"]: r for r in rows}

def group_by_query(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["query"]].append(r)
    return d

def pick_qtmmax_by_query(rows, class_col):
    d = {}
    for r in rows:
        q = r["query"]
        if q not in d:
            d[q] = r
        else:
            old = d[q]
            if (fnum(r.get("qtmscore","")), fnum(r.get("prob","")), fnum(r.get("qcov","")), fnum(r.get("bits",""))) > (
                fnum(old.get("qtmscore","")), fnum(old.get("prob","")), fnum(old.get("qcov","")), fnum(old.get("bits",""))
            ):
                d[q] = r
    return d

pdb_primary = read_tsv(pdb_primary_path)
pdb_top5 = read_tsv(pdb_top5_path)
pdb_qtmmax = read_tsv(pdb_qtmmax_path)
pdb_rank_audit = read_tsv(pdb_rank_audit_path)
pdb_neartie = read_tsv(pdb_neartie_path)

afsp_primary = read_tsv(afsp_primary_path)
afsp_top5 = read_tsv(afsp_top5_path)
afsp_qtmmax = read_tsv(afsp_qtmmax_path)
afsp_rank_audit = read_tsv(afsp_rank_audit_path)
afsp_neartie = read_tsv(afsp_neartie_path)

pdb_by_q = key_by_query(pdb_primary)
afsp_by_q = key_by_query(afsp_primary)
pdb_qtm_by_q = key_by_query(pdb_qtmmax)
afsp_qtm_by_q = key_by_query(afsp_qtmmax)
pdb_top5_by_q = group_by_query(pdb_top5)
afsp_top5_by_q = group_by_query(afsp_top5)
pdb_rank_audit_by_q = key_by_query(pdb_rank_audit)
afsp_rank_audit_by_q = key_by_query(afsp_rank_audit)

queries = sorted(set(pdb_by_q) | set(afsp_by_q))

decision_rows = []
panel_rows = []
manual_rows = []

def add_panel(panel, seen, query, protein_id, family, layer, role, source_rank, row, support_class, reason):
    target = row.get("target", "")
    if not target:
        return
    unique_key = (layer, target)
    if unique_key in seen:
        return
    seen.add(unique_key)
    panel.append({
        "query": query,
        "protein_id": protein_id,
        "family": family,
        "reference_layer": layer,
        "panel_role": role,
        "source_rank": source_rank,
        "target": target,
        "evalue": row.get("evalue", ""),
        "bits": row.get("bits", ""),
        "prob": row.get("prob", ""),
        "alntmscore": row.get("alntmscore", ""),
        "qtmscore": row.get("qtmscore", ""),
        "ttmscore": row.get("ttmscore", ""),
        "lddt": row.get("lddt", ""),
        "qcov": row.get("qcov", ""),
        "tcov": row.get("tcov", ""),
        "qlen": row.get("qlen", ""),
        "tlen": row.get("tlen", ""),
        "support_class": support_class,
        "selection_reason": reason,
    })

for q in queries:
    pdb = pdb_by_q.get(q, {})
    afsp = afsp_by_q.get(q, {})

    protein_id = pdb.get("protein_id") or afsp.get("protein_id") or ""
    family = pdb.get("family") or afsp.get("family") or ""

    pdb_cls = pdb.get("pdb_struct_support_class", "NO_PDB_RESULT")
    afsp_cls = afsp.get("afsp_struct_support_class", "NO_AFSP_RESULT")

    pdb_level = support_level(pdb_cls)
    afsp_level = support_level(afsp_cls)

    pdb_target = pdb.get("target", "")
    afsp_target = afsp.get("target", "")

    pdb_qtm = pdb.get("qtmscore", "")
    afsp_qtm = afsp.get("qtmscore", "")

    primary_layer = ""
    primary_target = ""
    primary_class = ""
    primary_reason = ""

    interpretation_policy = ""

    if pdb and pdb_level >= 3:
        primary_layer = "PDB"
        primary_target = pdb_target
        primary_class = pdb_cls
        primary_reason = "PDB experimental reference has strong/moderate structural support"
        interpretation_policy = "PDB_PRIMARY_AFSP_COMPLEMENTARY"
    elif pdb and pdb_level == 2:
        primary_layer = "PDB"
        primary_target = pdb_target
        primary_class = pdb_cls
        primary_reason = "PDB experimental reference is domain/partial; keep PDB primary but require AFSP/top5 context"
        interpretation_policy = "PDB_PARTIAL_PRIMARY_WITH_AFSP_CONTEXT"
    elif afsp and afsp_level >= 2:
        primary_layer = "AFSP"
        primary_target = afsp_target
        primary_class = afsp_cls
        primary_reason = "PDB is weak/absent; AFSP provides stronger complementary predicted-structure support"
        interpretation_policy = "AFSP_FALLBACK_BECAUSE_PDB_WEAK"
    elif pdb:
        primary_layer = "PDB"
        primary_target = pdb_target
        primary_class = pdb_cls
        primary_reason = "Only weak PDB/AFSP support available; retain PDB rank-1 as experimental anchor with manual review"
        interpretation_policy = "WEAK_REFERENCE_MANUAL_REVIEW"
    else:
        primary_layer = "NONE"
        primary_target = ""
        primary_class = "NO_REFERENCE"
        primary_reason = "No reference hit found"
        interpretation_policy = "NO_REFERENCE"

    flags = []

    pdb_audit = pdb_rank_audit_by_q.get(q, {})
    afsp_audit = afsp_rank_audit_by_q.get(q, {})

    if pdb_audit.get("manual_review_flag") == "YES":
        flags.append("PDB_RANK1_QTMMAX_DIFF")
    if afsp_audit.get("manual_review_flag") == "YES":
        flags.append("AFSP_RANK1_QTMMAX_DIFF")
    if pdb_level <= 1:
        flags.append("PDB_WEAK")
    if pdb_level == 2:
        flags.append("PDB_DOMAIN_OR_PARTIAL")
    if afsp_level > pdb_level:
        flags.append("AFSP_STRONGER_THAN_PDB")
    if pdb_level <= 1 and afsp_level >= 3:
        flags.append("PDB_WEAK_AFSP_STRONG")
    if family in {"3HCDH_N", "CobD_Cbib", "Arginase"}:
        flags.append("FAMILY_REVIEW_SUGGESTED")

    review_level = "LOW"
    if "PDB_WEAK_AFSP_STRONG" in flags or "PDB_DOMAIN_OR_PARTIAL" in flags:
        review_level = "HIGH"
    elif any(x.endswith("QTMMAX_DIFF") for x in flags) or "AFSP_STRONGER_THAN_PDB" in flags:
        review_level = "MODERATE"

    decision_rows.append({
        "query": q,
        "protein_id": protein_id,
        "family": family,
        "primary_reference_layer": primary_layer,
        "primary_reference_target": primary_target,
        "primary_reference_class": primary_class,
        "primary_reason": primary_reason,
        "interpretation_policy": interpretation_policy,
        "pdb_rank1_target": pdb_target,
        "pdb_rank1_class": pdb_cls,
        "pdb_rank1_qtmscore": pdb_qtm,
        "afsp_rank1_target": afsp_target,
        "afsp_rank1_class": afsp_cls,
        "afsp_rank1_qtmscore": afsp_qtm,
        "manual_review_level": review_level,
        "manual_review_flags": ";".join(flags),
        "recommended_visual_panel_size": "5",
    })

    if flags:
        manual_rows.append({
            "query": q,
            "protein_id": protein_id,
            "family": family,
            "manual_review_level": review_level,
            "manual_review_flags": ";".join(flags),
            "pdb_rank1_target": pdb_target,
            "pdb_rank1_class": pdb_cls,
            "afsp_rank1_target": afsp_target,
            "afsp_rank1_class": afsp_cls,
            "comment": primary_reason,
        })

    selected = []
    seen = set()

    if primary_layer == "PDB" and pdb:
        add_panel(selected, seen, q, protein_id, family, "PDB", "PRIMARY", "rank1", pdb, pdb_cls, primary_reason)
    elif primary_layer == "AFSP" and afsp:
        add_panel(selected, seen, q, protein_id, family, "AFSP", "PRIMARY", "rank1", afsp, afsp_cls, primary_reason)

    if pdb:
        add_panel(selected, seen, q, protein_id, family, "PDB", "PDB_RANK1_EXPERIMENTAL_ANCHOR", "rank1", pdb, pdb_cls, "Experimental PDB rank-1 anchor")
    if afsp:
        add_panel(selected, seen, q, protein_id, family, "AFSP", "AFSP_RANK1_COMPLEMENT", "rank1", afsp, afsp_cls, "AFSP predicted-structure complementary rank-1")

    pdb_qm = pdb_qtm_by_q.get(q, {})
    if pdb_qm and pdb_qm.get("target") != pdb_target:
        add_panel(
            selected, seen, q, protein_id, family, "PDB", "PDB_QTMMAX_AUDIT",
            "qtmmax", pdb_qm, pdb_qm.get("pdb_struct_support_class", ""),
            "PDB qTM-max differs from rank-1; audit/alternative reference"
        )

    afsp_qm = afsp_qtm_by_q.get(q, {})
    if afsp_qm and afsp_qm.get("target") != afsp_target:
        add_panel(
            selected, seen, q, protein_id, family, "AFSP", "AFSP_QTMMAX_AUDIT",
            "qtmmax", afsp_qm, afsp_qm.get("afsp_struct_support_class", ""),
            "AFSP qTM-max differs from rank-1; audit/alternative reference"
        )

    # Fill remaining panel slots from top-5, prioritizing PDB experimental then AFSP,
    # while avoiding duplicate targets already selected.
    for source_name, rows, class_col in [
        ("PDB", pdb_top5_by_q.get(q, []), "pdb_struct_support_class"),
        ("AFSP", afsp_top5_by_q.get(q, []), "afsp_struct_support_class"),
    ]:
        for r in rows:
            if len(selected) >= 5:
                break
            role = f"{source_name}_TOP5_CONTEXT"
            add_panel(
                selected, seen, q, protein_id, family, source_name, role,
                r.get("rank", ""), r, r.get(class_col, ""),
                f"{source_name} top-5 contextual/near-tie evidence"
            )
        if len(selected) >= 5:
            break

    # Re-number final panel order per query.
    for idx, r in enumerate(selected[:5], start=1):
        r["panel_order"] = idx
        panel_rows.append(r)

decision_fields = [
    "query","protein_id","family",
    "primary_reference_layer","primary_reference_target","primary_reference_class",
    "primary_reason","interpretation_policy",
    "pdb_rank1_target","pdb_rank1_class","pdb_rank1_qtmscore",
    "afsp_rank1_target","afsp_rank1_class","afsp_rank1_qtmscore",
    "manual_review_level","manual_review_flags",
    "recommended_visual_panel_size",
]

panel_fields = [
    "query","protein_id","family","panel_order",
    "reference_layer","panel_role","source_rank","target",
    "evalue","bits","prob","alntmscore","qtmscore","ttmscore","lddt","qcov","tcov","qlen","tlen",
    "support_class","selection_reason",
]

manual_fields = [
    "query","protein_id","family","manual_review_level","manual_review_flags",
    "pdb_rank1_target","pdb_rank1_class",
    "afsp_rank1_target","afsp_rank1_class",
    "comment",
]

write_tsv(decision_path, decision_rows, decision_fields)
write_tsv(panel_path, panel_rows, panel_fields)
write_tsv(manual_path, manual_rows, manual_fields)

summary = Counter()
summary["n_queries"] = len(decision_rows)
summary["panel_rows"] = len(panel_rows)
for r in decision_rows:
    summary[f"primary_layer_{r['primary_reference_layer']}"] += 1
    summary[f"manual_review_{r['manual_review_level']}"] += 1
    summary[f"policy_{r['interpretation_policy']}"] += 1

with summary_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["metric","value"])
    for k in sorted(summary):
        w.writerow([k, summary[k]])

with pointer_path.open("w") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["artifact_key","path","role"])
    w.writerow(["integrated_reference_decision", str(decision_path), "One-row-per-protein PDB+AFSP primary/reference decision table"])
    w.writerow(["reference_panel_targets", str(panel_path), "Up-to-five selected reference targets per protein for downstream P2Rank/visual QC"])
    w.writerow(["reference_panel_manual_review", str(manual_path), "Manual review flags explaining weak/partial/alternative-reference cases"])
    w.writerow(["reference_panel_summary", str(summary_path), "M08 integrated reference selector summary"])

print("decision:", decision_path)
print("panel:", panel_path)
print("manual:", manual_path)
print("summary:", summary_path)
print("pointer:", pointer_path)
print("n_queries:", len(decision_rows))
print("panel_rows:", len(panel_rows))
print("manual_rows:", len(manual_rows))
