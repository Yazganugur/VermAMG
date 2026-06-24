#!/usr/bin/env python3
"""
VermAMG preflight checker (R01-R07 + O01-O03).
Bir run YAML config dosyasını okur ve koşunun başlayıp başlayamayacağını
raporlar. Exit: 0=PASS/WARN, 1=FAIL, 2=CONFIG_ERROR.
"""
import argparse
import csv
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# YAML loader
# ──────────────────────────────────────────────────────────────
_YAML_AVAILABLE = False
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
    def load_yaml(path):
        with open(path, encoding="utf-8") as fh:
            return _yaml.safe_load(fh) or {}
except ImportError:
    def load_yaml(_path):  # type: ignore[misc]
        return None

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
PASS  = "PASS"
WARN  = "WARN"
FAIL  = "FAIL"

def _get(cfg, *keys, default=None):
    node = cfg
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
        if node is None:
            return default
    return node


def result(check_id, name, status, detail=""):
    return {"check_id": check_id, "check_name": name,
            "status": status, "detail": detail}


def write_tsv(path, rows, fields):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

# ──────────────────────────────────────────────────────────────
# Checks R01-R07
# ──────────────────────────────────────────────────────────────
def check_r01_required_fields(cfg):
    missing = []
    for path, keys in [
        ("run.run_label",      ("run_label",)),
        ("run.project_name",   ("project_name",)),
        ("run.mode",           ("mode",)),
        ("run.profile",        ("profile",)),
        ("inputs.candidate_fasta", ("inputs", "candidate_fasta")),
    ]:
        v = _get(cfg, *keys)
        if not v or (isinstance(v, str) and not v.strip()):
            missing.append(path)
    if missing:
        return result("R01", "required_fields", FAIL,
                      "Eksik veya boş zorunlu alanlar: " + ", ".join(missing))
    return result("R01", "required_fields", PASS)


def check_r02_run_label(cfg):
    rl = (_get(cfg, "run_label") or "").strip()
    if not rl:
        return result("R02", "run_label_format", FAIL, "run_label boş.")
    if len(rl) < 3 or len(rl) > 80:
        return result("R02", "run_label_format", FAIL,
                      f"run_label uzunluğu 3-80 karakter olmalı. Mevcut: {len(rl)}")
    for bad in ("/", "\\"):
        if bad in rl:
            return result("R02", "run_label_format", FAIL,
                          f"run_label slash/backslash içeremez: {rl!r}")
    if not rl.strip():
        return result("R02", "run_label_format", FAIL,
                      "run_label yalnızca boşluk içeremez.")
    return result("R02", "run_label_format", PASS, f"run_label: {rl!r}")


def check_r03_mode(cfg):
    mode = (_get(cfg, "mode") or "").strip()
    valid = {"test", "regression", "full"}
    if mode not in valid:
        return result("R03", "mode_valid", FAIL,
                      f"mode={mode!r}. Geçerli değerler: {sorted(valid)}")
    return result("R03", "mode_valid", PASS, f"mode: {mode}")


def check_r04_profile(cfg):
    profile = (_get(cfg, "profile") or "").strip()
    valid = {"local_wsl", "slurm"}
    if profile not in valid:
        return result("R04", "profile_valid", FAIL,
                      f"profile={profile!r}. Geçerli değerler: {sorted(valid)}")
    return result("R04", "profile_valid", PASS, f"profile: {profile}")


def check_r05_candidate_fasta(cfg, project_root):
    raw = (_get(cfg, "inputs", "candidate_fasta") or "").strip()
    if not raw:
        return result("R05", "candidate_fasta", FAIL, "inputs.candidate_fasta boş.")
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    if not p.exists():
        return result("R05", "candidate_fasta", FAIL,
                      f"Dosya bulunamadı: {p}")
    if p.stat().st_size == 0:
        return result("R05", "candidate_fasta", FAIL,
                      f"Dosya boş (0 byte): {p}")
    has_header = False
    try:
        with p.open(errors="replace") as fh:
            for line in fh:
                if line.startswith(">"):
                    has_header = True
                    break
    except OSError as exc:
        return result("R05", "candidate_fasta", FAIL, f"Okunamadı: {exc}")
    if not has_header:
        return result("R05", "candidate_fasta", FAIL,
                      f"FASTA header satırı ('>') bulunamadı: {p}")
    return result("R05", "candidate_fasta", PASS, f"{p}")


def check_r06_output_collision(cfg, project_root):
    run_label = (_get(cfg, "run_label") or "").strip()
    policy = (_get(cfg, "preflight", "overwrite_policy") or "fail_if_exists").strip()

    results_root = (_get(cfg, "outputs", "results") or "").strip()
    exports_root = (_get(cfg, "outputs", "exports") or "").strip()

    # Resolve defaults if not set
    if not results_root:
        results_root = f"results/{run_label}"
    if not exports_root:
        exports_root = f"exports/{run_label}"

    paths_to_check = []
    for raw in (results_root, exports_root):
        p = Path(raw)
        if not p.is_absolute():
            p = project_root / p
        paths_to_check.append(p)

    existing = [str(p) for p in paths_to_check if p.exists()]
    if not existing:
        return result("R06", "output_collision", PASS,
                      "Çıktı klasörleri henüz mevcut değil.")

    if policy == "warn_and_continue":
        return result("R06", "output_collision", WARN,
                      "Mevcut çıktı klasörleri bulundu (overwrite_policy=warn_and_continue): "
                      + ", ".join(existing))
    return result("R06", "output_collision", FAIL,
                  "Çıktı klasörleri zaten mevcut ve overwrite_policy=fail_if_exists: "
                  + ", ".join(existing))


def check_r07_python_version():
    vi = sys.version_info
    if (vi.major, vi.minor) < (3, 8):
        return result("R07", "python_version", FAIL,
                      f"Python >= 3.8 gerekli. Mevcut: {vi.major}.{vi.minor}.{vi.micro}")
    return result("R07", "python_version", PASS,
                  f"Python {vi.major}.{vi.minor}.{vi.micro}")

# ──────────────────────────────────────────────────────────────
# Optional checks O01-O03 — metadata
# ──────────────────────────────────────────────────────────────
REQUIRED_META_COLS = {
    "protein_id", "kofam_ko_id", "pfam_name",
    "habitat_broad", "flag_virus_specific",
}


def _resolve_metadata_path(cfg, project_root):
    raw = (
        _get(cfg, "inputs", "candidate_metadata") or
        _get(cfg, "inputs", "annotation", "metadata_tsv") or ""
    ).strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    return p


def _parse_fasta_ids(fasta_path):
    ids = set()
    try:
        with fasta_path.open(errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith(">"):
                    continue
                header = line[1:].split()[0] if line[1:] else ""
                if "|" in header:
                    header = header.split("|")[0]
                if header:
                    ids.add(header)
    except OSError:
        pass
    return ids


def _parse_metadata_ids(meta_path):
    ids = set()
    try:
        with meta_path.open(newline="", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                pid = (row.get("protein_id") or "").strip()
                if pid:
                    ids.add(pid)
    except OSError:
        pass
    return ids


def check_o01_metadata_file(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    meta_path = _resolve_metadata_path(cfg, project_root)

    if meta_path is None:
        return (
            result("O01", "metadata_file", WARN,
                   "inputs.candidate_metadata yapılandırılmamış. "
                   "M14 annotation sütunları boş olacak."),
            None,
        )
    if not meta_path.exists():
        status = WARN if profile == "local_wsl" else FAIL
        return (
            result("O01", "metadata_file", status,
                   f"Metadata dosyası bulunamadı: {meta_path}"),
            None,
        )
    if meta_path.stat().st_size == 0:
        return (
            result("O01", "metadata_file", FAIL,
                   f"Metadata dosyası boş (0 byte): {meta_path}"),
            None,
        )
    return result("O01", "metadata_file", PASS, f"{meta_path}"), meta_path


def check_o02_metadata_columns(cfg, meta_path):
    profile = (_get(cfg, "profile") or "").strip()
    schema_check = str(
        _get(cfg, "preflight", "check_metadata_schema") or "true"
    ).lower()

    try:
        with meta_path.open(newline="", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            actual_cols = set(reader.fieldnames or [])
    except OSError as exc:
        return result("O02", "metadata_required_columns", FAIL,
                      f"Okunamadı: {exc}")

    missing = REQUIRED_META_COLS - actual_cols
    if not missing:
        return result("O02", "metadata_required_columns", PASS,
                      f"Tüm zorunlu sütunlar mevcut. Toplam sütun: {len(actual_cols)}")

    if profile == "slurm" and schema_check != "false":
        status = FAIL
    else:
        status = WARN
    return result("O02", "metadata_required_columns", status,
                  f"Eksik zorunlu sütunlar: {sorted(missing)}")


def check_o03_fasta_metadata_join(cfg, fasta_path, meta_path):
    fasta_ids = _parse_fasta_ids(fasta_path)
    meta_ids  = _parse_metadata_ids(meta_path)

    if not fasta_ids:
        return result("O03", "fasta_metadata_join", FAIL,
                      "FASTA'dan hiç protein ID ayrıştırılamadı.")

    matched   = fasta_ids & meta_ids
    missing_n = len(fasta_ids - meta_ids)
    extra_n   = len(meta_ids - fasta_ids)
    fasta_n   = len(fasta_ids)
    meta_n    = len(meta_ids)
    matched_n = len(matched)
    coverage  = matched_n / fasta_n if fasta_n > 0 else 0.0

    detail = (
        f"fasta_n={fasta_n} meta_n={meta_n} matched_n={matched_n} "
        f"missing_metadata_n={missing_n} extra_metadata_n={extra_n} "
        f"coverage={coverage:.4f}"
    )
    if coverage == 0.0:
        return result("O03", "fasta_metadata_join", FAIL,
                      f"Eşleşme yok (coverage=0.0). {detail}")
    if coverage < 0.95:
        return result("O03", "fasta_metadata_join", WARN,
                      f"Düşük coverage (<0.95). {detail}")
    return result("O03", "fasta_metadata_join", PASS, detail)


# ──────────────────────────────────────────────────────────────
# Optional checks O04-O10 — tools / resources / disk
# ──────────────────────────────────────────────────────────────
def _tool_status(profile):
    return FAIL if profile == "slurm" else WARN


def _resolve_resource(cfg, project_root, *config_keys, default_relative=""):
    raw = (_get(cfg, *config_keys) or "").strip()
    if not raw and default_relative:
        raw = default_relative
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    return p


def check_o04_apptainer(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    for cmd in ("apptainer", "singularity"):
        if shutil.which(cmd):
            try:
                out = subprocess.run([cmd, "--version"], capture_output=True,
                                     text=True, timeout=10)
                ver = out.stdout.strip() or out.stderr.strip()
                return result("O04", "apptainer_or_singularity", PASS,
                              f"{cmd}: {ver}")
            except Exception:
                return result("O04", "apptainer_or_singularity", PASS, cmd)
    return result("O04", "apptainer_or_singularity",
                  _tool_status(profile),
                  "apptainer veya singularity PATH'te bulunamadı. "
                  "ColabFold ve PyMOL container'ları için gerekli.")


def check_o05_java(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    java_bin = (_get(cfg, "resources", "tools", "java_bin") or "java").strip()
    if shutil.which(java_bin):
        try:
            out = subprocess.run([java_bin, "-version"], capture_output=True,
                                 text=True, timeout=10)
            ver = (out.stderr or out.stdout).strip().splitlines()[0]
            return result("O05", "java", PASS, ver)
        except Exception:
            return result("O05", "java", PASS, java_bin)
    return result("O05", "java", _tool_status(profile),
                  f"java bulunamadı ({java_bin}). P2Rank için gerekli.")


def check_o06_p2rank(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    p = _resolve_resource(cfg, project_root,
                          "resources", "tools", "p2rank_cmd",
                          default_relative="resources/tools/p2rank/p2rank_2.5.1/prank")
    if p and p.exists():
        return result("O06", "p2rank", PASS, str(p))
    return result("O06", "p2rank", _tool_status(profile),
                  f"P2Rank çalıştırıcı bulunamadı: {p}")


def check_o07_foldseek(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    p = _resolve_resource(cfg, project_root,
                          "resources", "tools", "foldseek_bin",
                          default_relative="resources/tools/foldseek/bin/foldseek")
    if p and p.exists():
        return result("O07", "foldseek", PASS, str(p))
    return result("O07", "foldseek", _tool_status(profile),
                  f"Foldseek binary bulunamadı: {p}")


def check_o08_pymol_container(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    p = _resolve_resource(cfg, project_root,
                          "resources", "pymol_container",
                          default_relative="resources/containers/pymol_deb12_2.5.0_sc.sif")
    if p and p.exists():
        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb < 100:
            return result("O08", "pymol_container", _tool_status(profile),
                          f"PyMOL container çok küçük ({size_mb:.0f} MB < 100 MB): {p}")
        return result("O08", "pymol_container", PASS,
                      f"{p} ({size_mb:.0f} MB)")
    return result("O08", "pymol_container", _tool_status(profile),
                  f"PyMOL container bulunamadı: {p}")


def check_o09_foldseek_databases(cfg, project_root):
    profile = (_get(cfg, "profile") or "").strip()
    missing = []

    for config_key, default_rel, label in [
        (("resources", "pdb_foldseek_db"),
         "resources/databases/foldseek/pdb/pdb",
         "PDB Foldseek DB"),
        (("resources", "afsp_foldseek_db"),
         "resources/databases/foldseek/alphafold_swissprot/af_swissprot",
         "AFSP Foldseek DB"),
    ]:
        p = _resolve_resource(cfg, project_root, *config_key,
                              default_relative=default_rel)
        dbtype = Path(str(p) + ".dbtype") if p else None
        if not dbtype or not dbtype.exists():
            missing.append(f"{label} ({dbtype})")

    if missing:
        return result("O09", "foldseek_databases",
                      _tool_status(profile),
                      "Eksik Foldseek DB dosyaları: " + "; ".join(missing))
    return result("O09", "foldseek_databases", PASS,
                  "PDB ve AFSP Foldseek DB dosyaları mevcut.")


def check_o10_disk_space(cfg, project_root):
    mode = (_get(cfg, "mode") or "").strip()
    try:
        usage = shutil.disk_usage(project_root)
        free_gb = usage.free / (1024 ** 3)
    except OSError as exc:
        return result("O10", "disk_space", WARN,
                      f"Disk alanı ölçülemedi: {exc}")

    if free_gb < 10:
        return result("O10", "disk_space", FAIL,
                      f"Yetersiz disk alanı: {free_gb:.1f} GB boş (minimum 10 GB).")
    if mode == "full" and free_gb < 50:
        return result("O10", "disk_space", WARN,
                      f"mode=full için disk alanı düşük: {free_gb:.1f} GB boş "
                      f"(önerilen minimum 50 GB).")
    return result("O10", "disk_space", PASS,
                  f"{free_gb:.1f} GB boş disk alanı.")


# ──────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────
def run_checks(cfg, project_root):
    checks = [
        check_r01_required_fields(cfg),
        check_r02_run_label(cfg),
        check_r03_mode(cfg),
        check_r04_profile(cfg),
        check_r05_candidate_fasta(cfg, project_root),
        check_r06_output_collision(cfg, project_root),
        check_r07_python_version(),
    ]

    # Optional metadata checks — O01 her zaman çalışır
    o01_res, meta_path = check_o01_metadata_file(cfg, project_root)
    checks.append(o01_res)

    if meta_path is not None:
        checks.append(check_o02_metadata_columns(cfg, meta_path))
        fasta_raw = (_get(cfg, "inputs", "candidate_fasta") or "").strip()
        if fasta_raw:
            fp = Path(fasta_raw)
            if not fp.is_absolute():
                fp = project_root / fp
            if fp.exists():
                checks.append(check_o03_fasta_metadata_join(cfg, fp, meta_path))

    # Optional tool/resource/disk checks
    check_tools = str(_get(cfg, "preflight", "check_tools") or "false").lower() == "true"
    check_db    = str(_get(cfg, "preflight", "check_databases") or "false").lower() == "true"

    if check_tools:
        checks.append(check_o04_apptainer(cfg, project_root))
        checks.append(check_o05_java(cfg, project_root))
        checks.append(check_o06_p2rank(cfg, project_root))
        checks.append(check_o07_foldseek(cfg, project_root))
        checks.append(check_o08_pymol_container(cfg, project_root))

    if check_db:
        checks.append(check_o09_foldseek_databases(cfg, project_root))

    checks.append(check_o10_disk_space(cfg, project_root))

    return checks


def overall_status(checks, strict):
    statuses = {r["status"] for r in checks}
    if FAIL in statuses:
        return FAIL
    if WARN in statuses:
        return FAIL if strict else WARN
    return PASS


def print_summary(checks, overall, run_label, strict):
    WIDTH = 60
    colors = {PASS: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}
    reset = "\033[0m"
    print()
    print("=" * WIDTH)
    print(f"  VermAMG Preflight — run_label: {run_label!r}")
    print("=" * WIDTH)
    for r in checks:
        c = colors.get(r["status"], "")
        flag = f"[{r['status']:<4}]"
        line = f"  {c}{flag}{reset}  {r['check_id']}  {r['check_name']}"
        print(line)
        if r["detail"] and r["status"] != PASS:
            print(f"           {r['detail']}")
    print("-" * WIDTH)
    c = colors.get(overall, "")
    strict_note = " (--strict etkin)" if strict else ""
    print(f"  Sonuç: {c}{overall}{reset}{strict_note}")
    print("=" * WIDTH)
    print()


def write_reports(checks, overall, run_label, outdir, cfg, timestamp):
    od = Path(outdir)
    od.mkdir(parents=True, exist_ok=True)

    report_path = od / f"{run_label}_preflight_report.tsv"
    summary_path = od / f"{run_label}_preflight_summary.tsv"

    report_rows = [
        {
            "run_label": run_label,
            "timestamp": timestamp,
            "check_id": r["check_id"],
            "check_name": r["check_name"],
            "status": r["status"],
            "detail": r["detail"],
        }
        for r in checks
    ]
    write_tsv(report_path, report_rows,
              ["run_label", "timestamp", "check_id", "check_name", "status", "detail"])

    pass_n = sum(r["status"] == PASS for r in checks)
    warn_n = sum(r["status"] == WARN for r in checks)
    fail_n = sum(r["status"] == FAIL for r in checks)
    summary_rows = [
        {"metric": "run_label",      "value": run_label},
        {"metric": "timestamp",      "value": timestamp},
        {"metric": "overall_status", "value": overall},
        {"metric": "pass_n",         "value": str(pass_n)},
        {"metric": "warn_n",         "value": str(warn_n)},
        {"metric": "fail_n",         "value": str(fail_n)},
        {"metric": "total_checks",   "value": str(len(checks))},
        {"metric": "mode",           "value": str(_get(cfg, "mode") or "")},
        {"metric": "profile",        "value": str(_get(cfg, "profile") or "")},
    ]
    write_tsv(summary_path, summary_rows, ["metric", "value"])

    ptr_rows = [
        {"artifact_key": "preflight_report",
         "path": str(report_path),
         "role": "VermAMG preflight check report"},
        {"artifact_key": "preflight_summary",
         "path": str(summary_path),
         "role": "VermAMG preflight summary"},
    ]
    ptr = Path("pipeline_state/artifacts") / f"{run_label}_preflight_pointer.tsv"
    write_tsv(ptr, ptr_rows, ["artifact_key", "path", "role"])

    print(f"Rapor  : {report_path}")
    print(f"Özet   : {summary_path}")
    print(f"Pointer: {ptr}")

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="VermAMG preflight checker — koşu başlamadan önce config doğrular."
    )
    ap.add_argument("--config",  required=True,
                    help="Doldurulmuş run YAML config dosyası yolu.")
    ap.add_argument("--outdir",  default=None,
                    help="TSV rapor dosyalarının yazılacağı dizin (opsiyonel).")
    ap.add_argument("--strict",  action="store_true",
                    help="WARN'ları FAIL olarak değerlendirir.")
    args = ap.parse_args()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # PyYAML yoksa CONFIG_ERROR
    if not _YAML_AVAILABLE:
        print("CONFIG_ERROR: PyYAML kurulu değil. "
              "'pip install pyyaml' veya 'pip3 install pyyaml' ile kurun.",
              file=sys.stderr)
        sys.exit(2)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"CONFIG_ERROR: Config dosyası bulunamadı: {config_path}",
              file=sys.stderr)
        sys.exit(2)

    try:
        cfg = load_yaml(str(config_path))
    except Exception as exc:
        print(f"CONFIG_ERROR: YAML parse hatası: {exc}", file=sys.stderr)
        sys.exit(2)

    if cfg is None:
        print("CONFIG_ERROR: YAML dosyası boş veya okunamadı.", file=sys.stderr)
        sys.exit(2)

    project_root = Path(args.config).resolve().parent.parent
    # Eğer config run_configs/ altındaysa proje kökü bir üst dizindir.
    # Değilse yine de cwd kullan.
    if not (project_root / "00_inputs").exists():
        project_root = Path.cwd()

    checks = run_checks(cfg, project_root)
    run_label = (_get(cfg, "run_label") or "UNKNOWN").strip()
    overall = overall_status(checks, args.strict)

    print_summary(checks, overall, run_label, args.strict)

    if args.outdir:
        write_reports(checks, overall, run_label, args.outdir, cfg, timestamp)

    sys.exit(0 if overall in (PASS, WARN) else 1)


if __name__ == "__main__":
    main()
