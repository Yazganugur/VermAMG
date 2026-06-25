#!/usr/bin/env python3
"""Check whether a VermAMG checkout is ready for a requested run mode."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def exists(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p.exists()


def is_file(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p.is_file()


def executable(path_or_cmd: str) -> bool:
    if not path_or_cmd:
        return False
    if shutil.which(path_or_cmd):
        return True
    p = Path(path_or_cmd)
    if not p.is_absolute():
        p = ROOT / p
    return p.is_file()


def command_ok(cmd: list[str], timeout: int = 15) -> bool:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def add(rows: list[dict[str, str]], check: str, status: str, detail: str, required: bool) -> None:
    rows.append({
        "check": check,
        "status": status,
        "required": "YES" if required else "NO",
        "detail": detail,
    })


def path_from_env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def main() -> int:
    ap = argparse.ArgumentParser(description="VermAMG install/resource doctor")
    ap.add_argument(
        "--mode",
        choices=("smoke", "precomputed", "live", "render", "all"),
        default="smoke",
        help="Which capability to validate.",
    )
    args = ap.parse_args()

    rows: list[dict[str, str]] = []
    want_smoke = args.mode in {"smoke", "precomputed", "all"}
    want_live = args.mode in {"live", "all"}
    want_render = args.mode in {"render", "all"}

    py_ok = sys.version_info >= (3, 10)
    add(rows, "python_version", "PASS" if py_ok else "FAIL",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", True)

    yaml_ok = importlib.util.find_spec("yaml") is not None
    pandas_ok = importlib.util.find_spec("pandas") is not None
    add(rows, "python_package_pyyaml", "PASS" if yaml_ok else "FAIL", "import yaml", True)
    add(rows, "python_package_pandas", "PASS" if pandas_ok else "FAIL", "import pandas", True)

    java_ok = command_ok([path_from_env("JAVA_BIN", "java"), "-version"])
    add(rows, "java", "PASS" if java_ok else "FAIL", "required by P2Rank", want_smoke or want_live)

    p2rank_cmd = path_from_env("P2RANK_CMD", "resources/tools/p2rank/current/prank")
    p2rank_jar = path_from_env("P2RANK_JAR", "resources/tools/p2rank/current/bin/p2rank.jar")
    add(rows, "p2rank_cmd", "PASS" if executable(p2rank_cmd) else "FAIL", p2rank_cmd, want_smoke or want_live)
    add(rows, "p2rank_jar", "PASS" if is_file(p2rank_jar) else "FAIL", p2rank_jar, want_smoke or want_live)

    demo_paths = [
        "examples/smoke_precomputed/config.yaml",
        "examples/smoke_precomputed/data/proteins.faa",
        "examples/smoke_precomputed/data/query_pdbs",
        "examples/smoke_precomputed/data/foldseek/pdb_all_hits.tsv",
        "examples/smoke_precomputed/data/foldseek/afsp_all_hits.tsv",
        "examples/smoke_precomputed/data/reference_run_cache",
    ]
    for p in demo_paths:
        add(rows, f"demo_path:{p}", "PASS" if exists(p) else "FAIL", p, want_smoke)

    foldseek_bin = path_from_env("FOLDSEEK_BIN", "resources/tools/foldseek/bin/foldseek")
    pdb_db = path_from_env("PDB_FOLDSEEK_DB", "resources/databases/foldseek/pdb/pdb")
    afsp_db = path_from_env("AFSP_FOLDSEEK_DB", "resources/databases/foldseek/alphafold_swissprot/af_swissprot")
    add(rows, "foldseek_bin", "PASS" if executable(foldseek_bin) else "FAIL", foldseek_bin, want_live)
    add(rows, "foldseek_pdb_dbtype", "PASS" if is_file(pdb_db + ".dbtype") else "FAIL", pdb_db + ".dbtype", want_live)
    add(rows, "foldseek_afsp_dbtype", "PASS" if is_file(afsp_db + ".dbtype") else "FAIL", afsp_db + ".dbtype", want_live)

    colabfold_cmd = path_from_env("COLABFOLD_CMD", "colabfold_batch")
    add(rows, "colabfold_cmd", "PASS" if executable(colabfold_cmd) else "WARN", colabfold_cmd, False)

    pymol_cmd = path_from_env("PYMOL_CMD", "scripts/utils/pymol_apptainer_wrapper.sh")
    pymol_container = path_from_env("PYMOL_CONTAINER", "resources/containers/pymol_deb12_2.5.0_sc.sif")
    apptainer_ok = executable("apptainer")
    pymol_cmd_ok = executable(pymol_cmd)
    pymol_container_ok = is_file(pymol_container)
    render_ok = pymol_cmd_ok and (Path(pymol_cmd).name != "pymol_apptainer_wrapper.sh" or (apptainer_ok and pymol_container_ok))
    add(rows, "pymol_cmd", "PASS" if pymol_cmd_ok else "WARN", pymol_cmd, want_render)
    add(rows, "apptainer", "PASS" if apptainer_ok else "WARN", "needed for Apptainer PyMOL wrapper", want_render and Path(pymol_cmd).name == "pymol_apptainer_wrapper.sh")
    add(rows, "pymol_container", "PASS" if pymol_container_ok else "WARN", pymol_container, want_render and Path(pymol_cmd).name == "pymol_apptainer_wrapper.sh")
    add(rows, "render_capability", "PASS" if render_ok else "WARN", "optional unless m10f_render/m10g figures are enabled", want_render)

    print("VERMAMG_DOCTOR_V1")
    print(f"root\t{ROOT}")
    print(f"mode\t{args.mode}")
    print("check\tstatus\trequired\tdetail")
    failed_required = False
    for row in rows:
        print(f"{row['check']}\t{row['status']}\t{row['required']}\t{row['detail']}")
        if row["required"] == "YES" and row["status"] != "PASS":
            failed_required = True

    print(f"doctor_status\t{'FAIL' if failed_required else 'PASS'}")
    return 2 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
