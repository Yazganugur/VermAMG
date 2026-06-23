#!/usr/bin/env python3
"""Shared Phase 1 scaffold runner for the catalytic previsual layer.

This helper is intentionally non-biological. It validates declared inputs,
prints intended outputs, and writes empty header/QC scaffold files only after
all required inputs exist.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def read_header_contract(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}
    out: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            key = row.get("artifact_key", "").strip()
            raw = row.get("required_columns", "")
            header = [field.strip() for field in raw.split(",") if field.strip()]
            if key and header:
                out[key] = header
    return out


def resolve(workspace: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else workspace / path


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_pairs(values: list[list[str]] | None) -> list[tuple[str, str]]:
    if not values:
        return []
    return [(item[0], item[1]) for item in values]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 catalytic previsual scaffold runner.")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--stage-id", default=Path(sys.argv[0]).stem)
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--contract-headers", default="pipeline_contracts/catalytic_previsual_output_headers.tsv")
    parser.add_argument("--input", nargs=2, action="append", metavar=("LABEL", "PATH"), default=[])
    parser.add_argument("--output", nargs=2, action="append", metavar=("ARTIFACT_KEY", "PATH"), default=[])
    parser.add_argument("--header", nargs=2, action="append", metavar=("ARTIFACT_KEY", "TAB_SEPARATED_HEADER"), default=[])
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    contract_headers = read_header_contract(resolve(workspace, args.contract_headers))
    explicit_headers = {key: value.split("\t") for key, value in parse_pairs(args.header)}

    print("CATALYTIC_PREVISUAL_PHASE1_SCAFFOLD")
    print(f"stage_id\t{args.stage_id}")
    print(f"mode\t{args.mode}")
    print(f"workspace\t{workspace}")

    missing: list[tuple[str, Path]] = []
    for label, raw in parse_pairs(args.input):
        path = resolve(workspace, raw)
        exists = path.exists()
        print(f"input\t{label}\t{path}\t{'OK' if exists else 'MISSING'}")
        if not exists:
            missing.append((label, path))

    for artifact, raw in parse_pairs(args.output):
        path = resolve(workspace, raw)
        print(f"output\t{artifact}\t{path}")

    if missing:
        print("status\tFAIL_MISSING_REQUIRED_INPUTS")
        for label, path in missing:
            print(f"missing_input\t{label}\t{path}")
        return 2

    for artifact, raw in parse_pairs(args.output):
        path = resolve(workspace, raw)
        header = explicit_headers.get(artifact) or contract_headers.get(artifact)
        if header is None:
            if artifact.endswith("_qc") or path.name.endswith("_qc.tsv"):
                header = ["metric", "value"]
            else:
                header = ["mode", "scaffold_status", "stage_id", "note"]

        if header == ["metric", "value"]:
            rows = [
                {"metric": "module", "value": args.stage_id},
                {"metric": "status", "value": "SCAFFOLD_ONLY"},
                {"metric": "mode", "value": args.mode},
                {"metric": "biological_logic_implemented", "value": "NO"},
            ]
        else:
            rows = []
        write_tsv(path, rows, header)

    print("status\tPASS_SCAFFOLD_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
