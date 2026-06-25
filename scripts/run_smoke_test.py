#!/usr/bin/env python3
"""Run and verify the bundled DB-free VermAMG smoke test."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "examples/smoke_precomputed/config.yaml"


def run(cmd: list[str]) -> int:
    print("COMMAND", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def count_rows(path: Path) -> int:
    if not path.is_file():
        return -1
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in csv.DictReader(handle, delimiter="\t"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the bundled VermAMG smoke test and verify outputs.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG.relative_to(ROOT)))
    ap.add_argument("--skip-doctor", action="store_true")
    ap.add_argument("--expected-rows", type=int, default=3)
    args = ap.parse_args()

    config = Path(args.config)
    if not config.is_absolute():
        config = ROOT / config

    if not args.skip_doctor:
        rc = run([sys.executable, "scripts/vermamg_doctor.py", "--mode", "smoke"])
        if rc != 0:
            print("SMOKE_STATUS\tFAIL\tdoctor_failed")
            return rc

    for cmd in [
        [sys.executable, "scripts/vermamg.py", "plan", "--config", str(config.relative_to(ROOT))],
        [sys.executable, "scripts/vermamg.py", "run", "--config", str(config.relative_to(ROOT)), "--resume", "--follow"],
    ]:
        rc = run(cmd)
        if rc != 0:
            print(f"SMOKE_STATUS\tFAIL\tcommand_failed:{rc}")
            return rc

    run_root = ROOT / "runs/smoke_precomputed/smoke_3prot_v1"
    checks = [
        ("full_export", run_root / "exports/full/full_final_export_full.tsv"),
        ("compact_export", run_root / "exports/full/full_final_export_compact.tsv"),
        ("interpretation_ready", run_root / "exports/full/interpretation_ready/full_final_export_full_interpretation_ready.tsv"),
        ("primary_decision", run_root / "results/full/07_decision_matrix/full_primary_decision_matrix.tsv"),
    ]

    failed = False
    print("SMOKE_OUTPUT_CHECKS")
    print("artifact\tstatus\trows\tpath")
    for name, path in checks:
        rows = count_rows(path)
        ok = rows == args.expected_rows
        failed = failed or not ok
        print(f"{name}\t{'PASS' if ok else 'FAIL'}\t{rows}\t{path.relative_to(ROOT)}")

    print(f"SMOKE_STATUS\t{'FAIL' if failed else 'PASS'}")
    return 3 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
