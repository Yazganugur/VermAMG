#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


VALID_PROTEIN_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ*.-")
METADATA_ID_CANDIDATES = ("protein_id", "sequence_id", "run_id", "query", "id")


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


def parse_fasta(
    path: Path,
    *,
    id_policy: str,
    min_length: int,
    invalid_sequence_policy: str,
) -> tuple[list[dict[str, str]], list[str]]:
    records: list[dict[str, str]] = []
    errors: list[str] = []
    header = ""
    seq_parts: list[str] = []
    seen_sequence = False

    def finish_record() -> None:
        nonlocal header, seq_parts
        if not header:
            return
        record_index = len(records) + 1
        source_id = header.split()[0] if header.split() else ""
        sequence_id = source_id if id_policy == "preserve_first_token" else slugify(source_id, f"seq_{record_index:06d}")
        sequence = re.sub(r"\s+", "", "".join(seq_parts)).upper()
        invalid_chars = sorted(set(sequence) - VALID_PROTEIN_CHARS)
        internal_stop_count = sequence[:-1].count("*") if sequence.endswith("*") else sequence.count("*")
        if not source_id:
            errors.append(f"record_{record_index}:empty_source_id")
        if len(sequence) < min_length:
            errors.append(f"{sequence_id}:sequence_too_short:{len(sequence)}")
        if invalid_chars:
            message = f"{sequence_id}:invalid_sequence_chars:{''.join(invalid_chars)}"
            if invalid_sequence_policy == "fail":
                errors.append(message)
        records.append({
            "record_index": str(record_index),
            "sequence_id": sequence_id,
            "source_id": source_id,
            "source_header": header.replace("\t", " "),
            "sequence_slug": slugify(sequence_id, f"seq_{record_index:06d}"),
            "sequence_length": str(len(sequence)),
            "sequence_sha256": hashlib.sha256(sequence.encode("utf-8")).hexdigest(),
            "has_terminal_stop": "YES" if sequence.endswith("*") else "NO",
            "internal_stop_count": str(internal_stop_count),
            "invalid_char_count": str(len(invalid_chars)),
            "invalid_chars": "".join(invalid_chars),
            "sequence": sequence,
        })
        header = ""
        seq_parts = []

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n\r")
            if not line.strip():
                continue
            if line.startswith(">"):
                finish_record()
                header = line[1:].strip()
                if not header:
                    errors.append(f"line_{line_no}:empty_fasta_header")
                seq_parts = []
                seen_sequence = True
                continue
            if not header:
                errors.append(f"line_{line_no}:sequence_before_first_header")
                continue
            seq_parts.append(line.strip())
        finish_record()

    if not seen_sequence or not records:
        errors.append("empty_fasta:no_records")

    return records, errors


def read_metadata(path: Path, id_column: str) -> tuple[list[str], list[dict[str, str]], str, list[str]]:
    errors: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            return [], [], "", ["metadata_empty_or_missing_header"]
        header = [str(name) for name in reader.fieldnames]
        if id_column:
            detected = id_column
            if detected not in header:
                errors.append(f"metadata_id_column_not_found:{detected}")
        else:
            detected = next((name for name in METADATA_ID_CANDIDATES if name in header), "")
            if not detected:
                errors.append("metadata_id_column_auto_detect_failed")
        rows = [{key: (value if value is not None else "") for key, value in row.items()} for row in reader]
    return header, rows, detected, errors


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


def write_canonical_fasta(path: Path, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(f">{record['sequence_id']}\n")
            handle.write(wrap_sequence(record["sequence"]) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse VermAMG user FASTA into canonical V2 input manifests.")
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--metadata", default="")
    parser.add_argument("--metadata-id-column", default="")
    parser.add_argument("--metadata-required", default="false")
    parser.add_argument("--metadata-strict-extra-rows", default="false")
    parser.add_argument("--id-policy", choices=("preserve_first_token", "slug_first_token"), default="preserve_first_token")
    parser.add_argument("--duplicate-policy", choices=("fail",), default="fail")
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--invalid-sequence-policy", choices=("fail", "warn"), default="fail")
    parser.add_argument("--project-name", default="")
    parser.add_argument("--project-slug", default="")
    parser.add_argument("--sample-name", default="")
    parser.add_argument("--sample-slug", default="")
    parser.add_argument("--run-label", default="")
    parser.add_argument("--canonical-fasta", required=True)
    parser.add_argument("--sample-manifest", required=True)
    parser.add_argument("--metadata-joined", required=True)
    parser.add_argument("--qc-summary", required=True)
    parser.add_argument("--metadata-qc", required=True)
    args = parser.parse_args(argv)

    fasta_path = Path(args.fasta)
    metadata_path = Path(args.metadata) if args.metadata else None
    errors: list[str] = []

    if not fasta_path.is_file():
        errors.append(f"fasta_not_found:{fasta_path}")
        records: list[dict[str, str]] = []
    else:
        records, parse_errors = parse_fasta(
            fasta_path,
            id_policy=args.id_policy,
            min_length=max(1, args.min_length),
            invalid_sequence_policy=args.invalid_sequence_policy,
        )
        errors.extend(parse_errors)

    sequence_counts = Counter(record["sequence_id"] for record in records)
    duplicate_ids = sorted(seq_id for seq_id, count in sequence_counts.items() if count > 1)
    if duplicate_ids:
        errors.append("duplicate_sequence_ids:" + ",".join(duplicate_ids[:20]))

    metadata_header: list[str] = []
    metadata_rows: list[dict[str, str]] = []
    metadata_id_column = ""
    metadata_duplicate_ids: list[str] = []
    metadata_by_id: dict[str, dict[str, str]] = {}
    metadata_provided = metadata_path is not None and str(metadata_path) != ""
    if metadata_provided:
        if not metadata_path or not metadata_path.is_file():
            errors.append(f"metadata_not_found:{metadata_path}")
        else:
            metadata_header, metadata_rows, metadata_id_column, metadata_errors = read_metadata(metadata_path, args.metadata_id_column)
            errors.extend(metadata_errors)
            if metadata_id_column:
                metadata_counts = Counter(row.get(metadata_id_column, "") for row in metadata_rows)
                metadata_duplicate_ids = sorted(key for key, count in metadata_counts.items() if key and count > 1)
                if metadata_duplicate_ids:
                    errors.append("duplicate_metadata_ids:" + ",".join(metadata_duplicate_ids[:20]))
                for row in metadata_rows:
                    key = row.get(metadata_id_column, "")
                    if key and key not in metadata_by_id:
                        metadata_by_id[key] = row
    elif bool_value(args.metadata_required):
        errors.append("metadata_required_but_not_provided")

    manifest_rows: list[dict[str, str]] = []
    joined_rows: list[dict[str, str]] = []
    fasta_ids = {record["sequence_id"] for record in records}
    metadata_ids = set(metadata_by_id)
    for record in records:
        metadata_status = "NOT_PROVIDED"
        if metadata_provided:
            metadata_status = "MATCHED" if record["sequence_id"] in metadata_by_id else "MISSING"
        manifest_row = {
            key: record[key]
            for key in [
                "record_index",
                "sequence_id",
                "source_id",
                "source_header",
                "sequence_slug",
                "sequence_length",
                "sequence_sha256",
                "has_terminal_stop",
                "internal_stop_count",
                "invalid_char_count",
                "invalid_chars",
            ]
        }
        manifest_row.update({
            "metadata_status": metadata_status,
            "project_name": args.project_name,
            "project_slug": args.project_slug,
            "sample_name": args.sample_name,
            "sample_slug": args.sample_slug,
            "run_label": args.run_label,
        })
        manifest_rows.append(manifest_row)

        joined = dict(manifest_row)
        if metadata_status == "MATCHED":
            metadata_row = metadata_by_id[record["sequence_id"]]
            for key in metadata_header:
                out_key = key if key not in joined else f"metadata_{key}"
                joined[out_key] = metadata_row.get(key, "")
        joined_rows.append(joined)

    missing_metadata = [row["sequence_id"] for row in manifest_rows if row["metadata_status"] == "MISSING"]
    extra_metadata = sorted(metadata_ids - fasta_ids)
    if bool_value(args.metadata_required) and missing_metadata:
        errors.append(f"metadata_missing_for_sequences:{len(missing_metadata)}")
    if bool_value(args.metadata_strict_extra_rows) and extra_metadata:
        errors.append(f"metadata_extra_rows:{len(extra_metadata)}")

    status = "FAIL" if errors else "PASS"

    manifest_fields = [
        "record_index",
        "sequence_id",
        "source_id",
        "source_header",
        "sequence_slug",
        "sequence_length",
        "sequence_sha256",
        "has_terminal_stop",
        "internal_stop_count",
        "invalid_char_count",
        "invalid_chars",
        "metadata_status",
        "project_name",
        "project_slug",
        "sample_name",
        "sample_slug",
        "run_label",
    ]
    joined_fields = list(manifest_fields)
    for key in metadata_header:
        out_key = key if key not in joined_fields else f"metadata_{key}"
        if out_key not in joined_fields:
            joined_fields.append(out_key)

    if records:
        write_canonical_fasta(Path(args.canonical_fasta), records)
    write_tsv(Path(args.sample_manifest), manifest_fields, manifest_rows)
    write_tsv(Path(args.metadata_joined), joined_fields, joined_rows)

    metadata_qc_rows = [
        {
            "metric": "metadata_provided",
            "value": "YES" if metadata_provided else "NO",
        },
        {"metric": "metadata_id_column", "value": metadata_id_column},
        {"metric": "metadata_rows", "value": str(len(metadata_rows))},
        {"metric": "metadata_duplicate_ids", "value": str(len(metadata_duplicate_ids))},
        {"metric": "metadata_matched_sequences", "value": str(sum(1 for row in manifest_rows if row["metadata_status"] == "MATCHED"))},
        {"metric": "metadata_missing_sequences", "value": str(len(missing_metadata))},
        {"metric": "metadata_extra_rows", "value": str(len(extra_metadata))},
    ]
    write_tsv(Path(args.metadata_qc), ["metric", "value"], metadata_qc_rows)

    lengths = [int(record["sequence_length"]) for record in records]
    summary = [
        ("status", status),
        ("fasta_path", fasta_path),
        ("record_count", len(records)),
        ("unique_sequence_ids", len(sequence_counts)),
        ("duplicate_sequence_ids", len(duplicate_ids)),
        ("invalid_sequence_records", sum(1 for record in records if int(record["invalid_char_count"]) > 0)),
        ("min_sequence_length", min(lengths) if lengths else 0),
        ("max_sequence_length", max(lengths) if lengths else 0),
        ("total_aa", sum(lengths)),
        ("metadata_provided", "YES" if metadata_provided else "NO"),
        ("metadata_id_column", metadata_id_column),
        ("metadata_rows", len(metadata_rows)),
        ("metadata_matched_sequences", sum(1 for row in manifest_rows if row["metadata_status"] == "MATCHED")),
        ("metadata_missing_sequences", len(missing_metadata)),
        ("metadata_extra_rows", len(extra_metadata)),
        ("canonical_fasta", args.canonical_fasta),
        ("sample_manifest", args.sample_manifest),
        ("metadata_joined", args.metadata_joined),
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
