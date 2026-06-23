#!/usr/bin/env python3
"""Validate precomputed canonical catalytic previsual outputs.

This module is intentionally read-only with respect to biological inputs. It
does not run Foldseek, PyMOL, downloads, coordinate rescue, or residue transfer.
It validates already-produced golden TSVs and writes a small QC TSV.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


CANONICAL_FILES = {
    "candidate_residue_transfer_mapping_mcsa_rescued": "full_candidate_residue_transfer_mapping_mcsa_rescued.tsv",
    "query_level_catalytic_residue_summary": "full_query_level_catalytic_residue_summary.tsv",
    "final_catalytic_layer_integration": "full_final_catalytic_layer_integration.tsv",
    "catalytic_visual_query_manifest": "full_catalytic_visual_query_manifest.tsv",
    "catalytic_visual_annotation_manifest": "full_catalytic_visual_annotation_manifest.tsv",
    "2fua_Tyr_manual_override_audit": "full_2fua_Tyr_manual_override_audit.tsv",
    "catalytic_layer_class_transition_to_current": "full_catalytic_layer_class_transition_to_current.tsv",
    "current_catalytic_layer_version": "full_current_catalytic_layer_version.tsv",
}

DEFAULT_CLASS_COUNTS = {
    "CATALYTIC_LAYER_MCSA_CORE_CONSERVED_IDENTITY": 17,
    "CATALYTIC_LAYER_MCSA_CORE_PARTIAL_IDENTITY": 5,
    "CATALYTIC_LAYER_MCSA_CORE_CHANGED_IDENTITY": 2,
    "CATALYTIC_LAYER_MCSA_CORE_NOT_FULLY_MAPPABLE": 1,
    "CATALYTIC_LAYER_MCSA_NONCORE_ONLY": 8,
    "CATALYTIC_LAYER_UNIPROT_RESIDUE_MAPPED_NO_MCSA_CORE": 152,
    "CATALYTIC_LAYER_SUPPORT_CAUTION_ONLY": 336,
    "CATALYTIC_LAYER_CANDIDATE_NO_FULL_SUPPORT": 27,
    "CATALYTIC_LAYER_NO_RESIDUE_EVIDENCE": 117,
}

FINAL_CLASS_COLUMN = "A10G_FIX2_final_catalytic_layer_class"

QC_FIELDS = [
    "check_name",
    "status",
    "artifact_key",
    "observed",
    "expected",
    "message",
]


def resolve(base: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path


def read_header_contract(path: Path) -> dict[str, list[str]]:
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


def read_class_counts(path: Path) -> dict[str, int]:
    if not path.is_file():
        return dict(DEFAULT_CLASS_COUNTS)
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if "class_key" not in (reader.fieldnames or []) or "canonical_expected_count" not in (reader.fieldnames or []):
            return dict(DEFAULT_CLASS_COUNTS)
        out: dict[str, int] = {}
        for row in reader:
            key = row.get("class_key", "").strip()
            raw = row.get("canonical_expected_count", "").strip()
            if not key or raw == "":
                continue
            try:
                out[key] = int(raw)
            except ValueError:
                continue
        return out or dict(DEFAULT_CLASS_COUNTS)


def tsv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        line = handle.readline().rstrip("\r\n")
    return line.split("\t") if line else []


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        next(handle, None)
        return sum(1 for _ in handle)


def qc_row(check: str, status: str, artifact: str, observed: object, expected: object, message: str) -> dict[str, str]:
    return {
        "check_name": check,
        "status": status,
        "artifact_key": artifact,
        "observed": str(observed),
        "expected": str(expected),
        "message": message,
    }


def write_qc(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QC_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def find_version(rows: list[dict[str, str]], expected_key: str = "canonical_catalytic_layer_version") -> str:
    for row in rows:
        if row.get(expected_key, "").strip():
            return row[expected_key].strip()
        metric = row.get("metric", row.get("key", row.get("name", ""))).strip()
        value = row.get("value", "").strip()
        if metric == expected_key and value:
            return value
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canonical catalytic previsual golden TSVs.")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--contract-headers", default="pipeline_contracts/catalytic_previsual_output_headers.tsv")
    parser.add_argument("--class-policy", default="pipeline_contracts/catalytic_layer_class_policy.tsv")
    parser.add_argument("--validation-mode", choices=("precomputed", "golden"), default="precomputed")
    parser.add_argument("--expected-version", default="A10G_FIX2")
    parser.add_argument("--expected-query-count", type=int, default=665)
    parser.add_argument("--expected-residue-rows", type=int, default=17659)
    parser.add_argument("--expected-manual-override-rows", type=int, default=12)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path.cwd()
    run_root = resolve(project_root, args.run_root)
    catalytic_dir = run_root / "results/full/10_catalytic_layer"
    out_path = resolve(project_root, args.out)
    contract_path = resolve(project_root, args.contract_headers)
    class_policy_path = resolve(project_root, args.class_policy)

    qc: list[dict[str, str]] = [
        qc_row("validation_mode", "PASS", "ALL", args.validation_mode, "precomputed/golden", "Read-only validation mode."),
    ]

    if not contract_path.is_file():
        qc.append(qc_row("contract_headers_exist", "FAIL", "ALL", contract_path, "file exists", "Header contract TSV is missing."))
        qc.insert(0, qc_row(
            "overall_status",
            "FAIL",
            "ALL",
            "missing header contract",
            "PASS",
            "Canonical previsual catalytic validation failed before golden TSV checks.",
        ))
        write_qc(out_path, qc)
        print(f"CATALYTIC_PREVISUAL_VALIDATION_FAIL\tmissing header contract\t{out_path}")
        return 2

    headers = read_header_contract(contract_path)
    expected_classes = read_class_counts(class_policy_path)
    paths = {key: catalytic_dir / filename for key, filename in CANONICAL_FILES.items()}

    missing_artifacts: list[str] = []
    for key, path in paths.items():
        if path.is_file():
            qc.append(qc_row("file_exists", "PASS", key, path, "file exists", "Canonical TSV found."))
        else:
            missing_artifacts.append(key)
            qc.append(qc_row("file_exists", "FAIL", key, path, "file exists", "MISSING_GOLDEN_OUTPUT"))

    for key in CANONICAL_FILES:
        if key in headers:
            qc.append(qc_row("header_contract_present", "PASS", key, len(headers[key]), ">0", "Required-column contract found."))
        else:
            qc.append(qc_row("header_contract_present", "FAIL", key, "missing", "present", "Header contract row missing."))

    if missing_artifacts:
        qc.insert(0, qc_row(
            "overall_status",
            "FAIL",
            "ALL",
            f"{len(missing_artifacts)} missing golden outputs",
            "PASS",
            "Canonical previsual catalytic validation failed because required golden TSVs are missing.",
        ))
        write_qc(out_path, qc)
        print(f"CATALYTIC_PREVISUAL_VALIDATION_FAIL\tmissing golden outputs\t{out_path}")
        for key in missing_artifacts:
            print(f"MISSING_GOLDEN_OUTPUT\t{key}\t{paths[key]}")
        return 2

    for key, path in paths.items():
        expected_header = headers.get(key, [])
        observed_header = tsv_header(path)
        missing_cols = [column for column in expected_header if column not in observed_header]
        status = "PASS" if not missing_cols else "FAIL"
        message = "Header contains required columns." if not missing_cols else "Missing required columns: " + ",".join(missing_cols)
        qc.append(qc_row("required_columns", status, key, len(observed_header), len(expected_header), message))

    expected_rows = {
        "candidate_residue_transfer_mapping_mcsa_rescued": args.expected_residue_rows,
        "query_level_catalytic_residue_summary": args.expected_query_count,
        "final_catalytic_layer_integration": args.expected_query_count,
        "catalytic_visual_query_manifest": args.expected_query_count,
        "catalytic_visual_annotation_manifest": args.expected_residue_rows,
        "2fua_Tyr_manual_override_audit": args.expected_manual_override_rows,
    }
    for key, expected in expected_rows.items():
        observed = row_count(paths[key])
        qc.append(qc_row(
            "row_count",
            "PASS" if observed == expected else "FAIL",
            key,
            observed,
            expected,
            "Row count matches canonical A10G-FIX2 expectation." if observed == expected else "Row count differs from canonical A10G-FIX2 expectation.",
        ))

    final_header, final_rows = read_rows(paths["final_catalytic_layer_integration"])
    if FINAL_CLASS_COLUMN not in final_header:
        qc.append(qc_row(
            "final_class_column",
            "FAIL",
            "final_catalytic_layer_integration",
            ",".join(final_header),
            FINAL_CLASS_COLUMN,
            "Cannot validate class counts without final class column.",
        ))
    else:
        observed_classes = Counter(row.get(FINAL_CLASS_COLUMN, "") for row in final_rows)
        for class_key, expected in expected_classes.items():
            observed = observed_classes.get(class_key, 0)
            qc.append(qc_row(
                "final_class_count",
                "PASS" if observed == expected else "FAIL",
                class_key,
                observed,
                expected,
                "Final class count matches canonical A10G-FIX2 expectation." if observed == expected else "Final class count differs from canonical A10G-FIX2 expectation.",
            ))
        unexpected = sorted(key for key in observed_classes if key and key not in expected_classes)
        qc.append(qc_row(
            "unexpected_final_classes",
            "PASS" if not unexpected else "FAIL",
            "final_catalytic_layer_integration",
            ";".join(unexpected),
            "none",
            "No unexpected final catalytic classes." if not unexpected else "Unexpected final catalytic classes present.",
        ))

    version_header, version_rows = read_rows(paths["current_catalytic_layer_version"])
    observed_version = find_version(version_rows)
    qc.append(qc_row(
        "canonical_version",
        "PASS" if observed_version == args.expected_version else "FAIL",
        "current_catalytic_layer_version",
        observed_version or "missing",
        args.expected_version,
        "canonical_catalytic_layer_version matches." if observed_version == args.expected_version else "canonical_catalytic_layer_version mismatch or missing.",
    ))

    failed = [row for row in qc if row["status"] == "FAIL"]
    qc.insert(0, qc_row(
        "overall_status",
        "PASS" if not failed else "FAIL",
        "ALL",
        "PASS" if not failed else f"{len(failed)} failing checks",
        "PASS",
        "Canonical previsual catalytic outputs validated." if not failed else "Canonical previsual catalytic validation failed; see rows below.",
    ))
    write_qc(out_path, qc)

    if failed:
        print(f"CATALYTIC_PREVISUAL_VALIDATION_FAIL\t{len(failed)} failing checks\t{out_path}")
        return 2
    print(f"CATALYTIC_PREVISUAL_VALIDATION_PASS\t{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
