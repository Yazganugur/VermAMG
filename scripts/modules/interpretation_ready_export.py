#!/usr/bin/env python3
"""
interpretation_ready_export.py

Builds interpretation-ready export from M14 full export by joining M12A
scientific_caution (CA-only reference warning + viral context note).
These columns are computed in M12A-lite but are not propagated through
M13/M14; this module adds them back for scientific interpretation.
"""
from __future__ import annotations

import argparse
import csv
import datetime
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=fields, delimiter="\t",
            extrasaction="ignore", lineterminator="\n",
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Interpretation-ready export: M14 + M12A scientific_caution join."
    )
    ap.add_argument("--m14-full", required=True, help="M14 full export TSV")
    ap.add_argument("--m12a-primary", required=True, help="M12A primary decision matrix TSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--mode", default="full")
    ap.add_argument("--run-label", default="")
    args = ap.parse_args()

    m14_path = Path(args.m14_full)
    m12a_path = Path(args.m12a_primary)
    outdir = Path(args.outdir)

    if not m14_path.is_file():
        raise SystemExit(f"ERROR: M14 full export not found: {m14_path}")
    if not m12a_path.is_file():
        raise SystemExit(f"ERROR: M12A primary matrix not found: {m12a_path}")

    m14_rows = read_tsv(m14_path)
    m12a_rows = read_tsv(m12a_path)

    # Build M12A lookup by protein_id (primary key) and query (fallback)
    m12a_by_pid: dict[str, dict[str, str]] = {}
    m12a_by_query: dict[str, dict[str, str]] = {}
    for row in m12a_rows:
        pid = row.get("protein_id", "").strip()
        q = row.get("query", "").strip()
        if pid and pid not in m12a_by_pid:
            m12a_by_pid[pid] = row
        if q and q not in m12a_by_query:
            m12a_by_query[q] = row

    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    out_rows: list[dict[str, str]] = []
    caution_joined = 0
    caution_missing = 0
    viral_note_present = 0

    for r in m14_rows:
        pid = r.get("protein_id", "").strip()
        query = r.get("query", "").strip()
        m12a_row = m12a_by_pid.get(pid) or m12a_by_query.get(query) or {}
        scientific_caution = m12a_row.get("scientific_caution", "").strip()

        if scientific_caution:
            caution_joined += 1
        else:
            caution_missing += 1

        if "viral contig" in scientific_caution:
            viral_note_present += 1

        out = dict(r)
        out["scientific_caution"] = scientific_caution
        out["interpretation_ready_timestamp"] = timestamp
        out_rows.append(out)

    # Output fields: all M14 full columns + new columns (if not already present)
    base_fields = list(m14_rows[0].keys()) if m14_rows else []
    extra_fields = [f for f in ("scientific_caution", "interpretation_ready_timestamp")
                    if f not in base_fields]
    full_fields = base_fields + extra_fields

    full_path = outdir / f"{args.mode}_final_export_full_interpretation_ready.tsv"
    write_tsv(full_path, out_rows, full_fields)

    qc_status = "OK" if caution_missing == 0 else "WARN"
    qc_rows = [
        {"metric": "module",                    "value": "interpretation_ready_export"},
        {"metric": "status",                    "value": qc_status},
        {"metric": "mode",                      "value": args.mode},
        {"metric": "run_label",                 "value": args.run_label},
        {"metric": "total_rows",                "value": str(len(out_rows))},
        {"metric": "scientific_caution_joined", "value": str(caution_joined)},
        {"metric": "scientific_caution_missing","value": str(caution_missing)},
        {"metric": "viral_context_note_present","value": str(viral_note_present)},
        {"metric": "m14_full_path",             "value": args.m14_full},
        {"metric": "m12a_primary_path",         "value": args.m12a_primary},
        {"metric": "output_path",               "value": str(full_path)},
        {"metric": "interpretation_ready_timestamp", "value": timestamp},
    ]
    qc_path = outdir / f"{args.mode}_interpretation_ready_export_qc.tsv"
    write_tsv(qc_path, qc_rows, ["metric", "value"])

    print("INTERPRETATION_READY_EXPORT_OK")
    print(f"output_path\t{full_path}")
    print(f"total_rows\t{len(out_rows)}")
    print(f"scientific_caution_joined\t{caution_joined}")
    print(f"scientific_caution_missing\t{caution_missing}")
    print(f"viral_context_note_present\t{viral_note_present}")
    print(f"qc_status\t{qc_status}")
    print(f"qc\t{qc_path}")
    return 0 if qc_status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
