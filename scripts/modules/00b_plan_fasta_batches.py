#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path
from typing import Any


def bool_value(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def slugify(value: str, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or fallback


def wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[i:i + width] for i in range(0, len(sequence), width))


def parse_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    header = ""
    seq_parts: list[str] = []

    def finish() -> None:
        nonlocal header, seq_parts
        if not header:
            return
        sequence_id = header.split()[0]
        records[sequence_id] = re.sub(r"\s+", "", "".join(seq_parts)).upper()
        header = ""
        seq_parts = []

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n\r")
            if not line.strip():
                continue
            if line.startswith(">"):
                finish()
                header = line[1:].strip()
                seq_parts = []
            else:
                seq_parts.append(line.strip())
        finish()
    return records


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), [{key: (value if value is not None else "") for key, value in row.items()} for row in reader]


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, metrics: list[tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows((key, str(value)) for key, value in metrics)


def chunk_rows(rows: list[dict[str, str]], *, enabled: bool, strategy: str, batch_size: int, target_batches: int) -> list[list[dict[str, str]]]:
    if not rows:
        return []
    if not enabled or strategy == "single":
        return [rows]
    if strategy == "target_batches":
        target = max(1, min(target_batches, len(rows)))
        size = max(1, math.ceil(len(rows) / target))
    else:
        size = max(1, batch_size)
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create VermAMG V2 FASTA batch plan from canonical intake outputs.")
    parser.add_argument("--canonical-fasta", required=True)
    parser.add_argument("--sample-manifest", required=True)
    parser.add_argument("--batch-dir", required=True)
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--batch-membership", required=True)
    parser.add_argument("--sample-manifest-with-batches", required=True)
    parser.add_argument("--qc-summary", required=True)
    parser.add_argument("--batching-enabled", default="true")
    parser.add_argument("--strategy", choices=("fixed_size", "target_batches", "single"), default="fixed_size")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--target-batches", type=int, default=0)
    parser.add_argument("--max-sequences", type=int, default=0)
    parser.add_argument("--batch-prefix", default="")
    args = parser.parse_args(argv)

    fasta_path = Path(args.canonical_fasta)
    manifest_path = Path(args.sample_manifest)
    errors: list[str] = []
    if not fasta_path.is_file():
        errors.append(f"canonical_fasta_not_found:{fasta_path}")
    if not manifest_path.is_file():
        errors.append(f"sample_manifest_not_found:{manifest_path}")
    if errors:
        write_summary(Path(args.qc_summary), [("status", "FAIL"), ("error_count", len(errors)), *[("error", err) for err in errors]])
        for err in errors:
            print(f"error\t{err}")
        return 1

    sequences = parse_fasta(fasta_path)
    manifest_fields, manifest_rows = read_tsv(manifest_path)
    if args.max_sequences and args.max_sequences > 0:
        manifest_rows = manifest_rows[:args.max_sequences]

    missing_sequences = [row.get("sequence_id", "") for row in manifest_rows if row.get("sequence_id", "") not in sequences]
    if missing_sequences:
        errors.append(f"manifest_sequence_missing_from_fasta:{len(missing_sequences)}")

    batch_prefix = slugify(args.batch_prefix, "batch")
    batches = chunk_rows(
        manifest_rows,
        enabled=bool_value(args.batching_enabled, True),
        strategy=args.strategy,
        batch_size=max(1, args.batch_size),
        target_batches=max(0, args.target_batches),
    )
    batch_dir = Path(args.batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_manifest_rows: list[dict[str, str]] = []
    membership_rows: list[dict[str, str]] = []
    manifest_with_batches: list[dict[str, str]] = []
    for batch_index, rows in enumerate(batches, start=1):
        batch_id = f"{batch_prefix}_{batch_index:04d}"
        batch_fasta = batch_dir / f"{batch_id}.faa"
        total_aa = 0
        with batch_fasta.open("w", encoding="utf-8", newline="\n") as handle:
            for member_index, row in enumerate(rows, start=1):
                sequence_id = row.get("sequence_id", "")
                sequence = sequences.get(sequence_id, "")
                total_aa += len(sequence)
                handle.write(f">{sequence_id}\n")
                handle.write(wrap_sequence(sequence) + "\n")
                membership_rows.append({
                    "batch_id": batch_id,
                    "batch_index": str(batch_index),
                    "member_index": str(member_index),
                    "record_index": row.get("record_index", ""),
                    "sequence_id": sequence_id,
                    "sequence_length": row.get("sequence_length", str(len(sequence))),
                    "batch_fasta": str(batch_fasta),
                })
                updated = dict(row)
                updated.update({
                    "batch_id": batch_id,
                    "batch_index": str(batch_index),
                    "member_index": str(member_index),
                    "batch_fasta": str(batch_fasta),
                })
                manifest_with_batches.append(updated)
        first_record = rows[0].get("record_index", "") if rows else ""
        last_record = rows[-1].get("record_index", "") if rows else ""
        batch_manifest_rows.append({
            "batch_id": batch_id,
            "batch_index": str(batch_index),
            "batch_fasta": str(batch_fasta),
            "record_count": str(len(rows)),
            "first_record_index": first_record,
            "last_record_index": last_record,
            "total_aa": str(total_aa),
        })

    write_tsv(Path(args.batch_manifest), ["batch_id", "batch_index", "batch_fasta", "record_count", "first_record_index", "last_record_index", "total_aa"], batch_manifest_rows)
    write_tsv(Path(args.batch_membership), ["batch_id", "batch_index", "member_index", "record_index", "sequence_id", "sequence_length", "batch_fasta"], membership_rows)
    manifest_batch_fields = list(manifest_fields)
    for field in ["batch_id", "batch_index", "member_index", "batch_fasta"]:
        if field not in manifest_batch_fields:
            manifest_batch_fields.append(field)
    write_tsv(Path(args.sample_manifest_with_batches), manifest_batch_fields, manifest_with_batches)

    status = "FAIL" if errors else "PASS"
    summary = [
        ("status", status),
        ("batching_enabled", "YES" if bool_value(args.batching_enabled, True) else "NO"),
        ("strategy", args.strategy),
        ("batch_size", max(1, args.batch_size)),
        ("target_batches", max(0, args.target_batches)),
        ("max_sequences", max(0, args.max_sequences)),
        ("input_records", len(manifest_rows)),
        ("planned_records", len(membership_rows)),
        ("batch_count", len(batch_manifest_rows)),
        ("missing_sequences", len(missing_sequences)),
        ("batch_manifest", args.batch_manifest),
        ("batch_membership", args.batch_membership),
        ("sample_manifest_with_batches", args.sample_manifest_with_batches),
        ("error_count", len(errors)),
    ]
    for error in errors:
        summary.append(("error", error))
    write_summary(Path(args.qc_summary), summary)
    for key, value in summary:
        print(f"{key}\t{value}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
