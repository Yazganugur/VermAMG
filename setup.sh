#!/usr/bin/env bash
# ============================================================================
# VermAMG setup.sh — install external tools and reference databases.
#
# Databases/tools are NOT shipped in git (tens of GB). This script fetches them
# from their official sources into resources/ and creates version-agnostic
# symlinks so run configs do not need to encode version numbers.
# It is idempotent: anything already present is skipped.
#
# Usage:
#   bash setup.sh                       # tools + Foldseek reference DBs (PDB + AFSP)
#   bash setup.sh --tools-only          # only Foldseek + P2Rank binaries (no DBs)
#   bash setup.sh --with-colabfold-db   # also fetch the large ColabFold MSA DB
#   bash setup.sh --foldseek-sse2       # use SSE2 Foldseek build (for older CPUs)
#   bash setup.sh --foldseek-arm64      # use ARM64 Foldseek build
#   bash setup.sh --help
#
# Linux/WSL only. On Windows, open WSL and run:
#   cd /mnt/d/VermAMG && bash setup.sh
# ============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RES="${PROJECT_ROOT}/resources"
TOOLS="${RES}/tools"
DBS="${RES}/databases"

TOOLS_ONLY=0
WITH_COLABFOLD_DB=0
FOLDSEEK_VER="avx2"   # avx2 (default) | sse2 | arm64

for arg in "$@"; do
  case "$arg" in
    --tools-only)        TOOLS_ONLY=1 ;;
    --with-colabfold-db) WITH_COLABFOLD_DB=1 ;;
    --foldseek-sse2)     FOLDSEEK_VER="sse2" ;;
    --foldseek-arm64)    FOLDSEEK_VER="arm64" ;;
    --help|-h)
      sed -n 's/^# \{0,1\}//p' "${BASH_SOURCE[0]}" | head -25
      exit 0 ;;
    *) echo "Unknown option: $arg (use --help)"; exit 2 ;;
  esac
done

say()  { echo -e "\n==== $* ===="; }
ok()   { echo "  OK : $*"; }
skip() { echo "SKIP : $*"; }
warn() { echo "WARN : $*"; }
have() { command -v "$1" >/dev/null 2>&1; }

dl() {  # dl <url> <output>
  if have wget; then wget -q --show-progress -O "$2" "$1";
  elif have curl; then curl -fL# -o "$2" "$1";
  else echo "ERROR: need wget or curl"; exit 1; fi
}

say "VermAMG setup"
echo "project_root = ${PROJECT_ROOT}"
mkdir -p "${TOOLS}" "${DBS}/foldseek"

# ---------------------------------------------------------------------------
# 1) Foldseek binary
# ---------------------------------------------------------------------------
FOLDSEEK_BIN="${TOOLS}/foldseek/bin/foldseek"
if [[ -x "${FOLDSEEK_BIN}" ]]; then
  skip "Foldseek already installed: ${FOLDSEEK_BIN}"
else
  say "Installing Foldseek (${FOLDSEEK_VER})"
  tmp="$(mktemp -d)"
  dl "https://mmseqs.com/foldseek/foldseek-linux-${FOLDSEEK_VER}.tar.gz" "${tmp}/foldseek.tar.gz"
  tar -xzf "${tmp}/foldseek.tar.gz" -C "${TOOLS}"
  rm -rf "${tmp}"
  ok "Installed: ${FOLDSEEK_BIN}"
fi
"${FOLDSEEK_BIN}" version 2>/dev/null | head -1 | sed 's/^/  foldseek version: /' || true

# ---------------------------------------------------------------------------
# 2) P2Rank binary + Java check + version-agnostic symlink
# ---------------------------------------------------------------------------
P2RANK_DIR="${TOOLS}/p2rank"
P2RANK_VER="2.5.1"
P2RANK_RELEASE_URL="https://github.com/rdk/p2rank/releases/download/${P2RANK_VER}/p2rank_${P2RANK_VER}.tar.gz"
P2RANK_VERSIONED="${P2RANK_DIR}/p2rank_${P2RANK_VER}"
# Version-agnostic directory symlink: configs point to resources/tools/p2rank/current/prank.
# P2Rank's launcher resolves its libraries relative to the script's directory, so a whole-
# directory symlink (not a bare file symlink) is required for the classpath to resolve.
P2RANK_CURRENT="${P2RANK_DIR}/current"
P2RANK_SYMLINK_CMD="${P2RANK_CURRENT}/prank"
P2RANK_SYMLINK_JAR="${P2RANK_CURRENT}/bin/p2rank.jar"

say "Java runtime check (required for P2Rank)"
if have java; then
  java -version 2>&1 | head -1 | sed 's/^/  /'
else
  warn "Java not found on PATH. P2Rank will not run without Java."
  warn "Install Java 11+: https://adoptium.net  or  sudo apt install default-jre"
fi

if [[ -x "${P2RANK_VERSIONED}/prank" ]]; then
  skip "P2Rank ${P2RANK_VER} already installed: ${P2RANK_VERSIONED}"
else
  say "Installing P2Rank ${P2RANK_VER}"
  mkdir -p "${P2RANK_DIR}"
  tmp="$(mktemp -d)"
  dl "${P2RANK_RELEASE_URL}" "${tmp}/p2rank.tar.gz"
  tar -xzf "${tmp}/p2rank.tar.gz" -C "${P2RANK_DIR}"
  rm -rf "${tmp}"
  ok "Installed: ${P2RANK_VERSIONED}"
fi

# Version-agnostic directory symlink: resources/tools/p2rank/current -> p2rank_<ver>
# Configs then reference resources/tools/p2rank/current/prank regardless of installed version.
ln -sfn "p2rank_${P2RANK_VER}" "${P2RANK_CURRENT}"
ok "Symlink: ${P2RANK_CURRENT} -> p2rank_${P2RANK_VER}"
if [[ -x "${P2RANK_SYMLINK_CMD}" ]]; then
  ok "P2Rank ready: ${P2RANK_SYMLINK_CMD}"
fi

if [[ "${TOOLS_ONLY}" -eq 1 ]]; then
  say "Done (--tools-only)"
  echo
  echo "Add these to your run config under 'resources:':"
  echo "  p2rank_cmd: \"${P2RANK_SYMLINK_CMD##${PROJECT_ROOT}/}\""
  echo "  p2rank_jar: \"${P2RANK_SYMLINK_JAR##${PROJECT_ROOT}/}\""
  exit 0
fi

# ---------------------------------------------------------------------------
# 3) Foldseek reference databases (PDB + AlphaFold/Swiss-Prot)
# ---------------------------------------------------------------------------
fs_db() {  # fs_db <foldseek-db-name> <out-prefix>
  local name="$1" prefix="$2"
  if [[ -f "${prefix}.dbtype" ]]; then
    skip "DB already present: ${prefix}"
  else
    say "Downloading Foldseek DB: ${name}"
    local tmp; tmp="$(mktemp -d)"
    "${FOLDSEEK_BIN}" databases "${name}" "${prefix}" "${tmp}"
    rm -rf "${tmp}"
    ok "DB ready: ${prefix}"
  fi
}
fs_db "PDB"                  "${DBS}/foldseek/pdb"
fs_db "Alphafold/Swiss-Prot" "${DBS}/foldseek/alphafold_swissprot"

# ---------------------------------------------------------------------------
# 4) Optional: ColabFold MSA DB (large; live mode only)
# ---------------------------------------------------------------------------
if [[ "${WITH_COLABFOLD_DB}" -eq 1 ]]; then
  say "ColabFold MSA database (large, live-mode only)"
  echo "  Follow the official setup instructions at:"
  echo "  https://github.com/sokrypton/ColabFold#generating-msas-for-large-scale-structurecomplex-predictions"
  echo "  Target directory: ${DBS}/colabfold/"
  echo "  Set config key: resources.colabfold_db -> ${DBS}/colabfold/colabfold_data"
else
  echo
  echo "  ColabFold MSA DB skipped (precomputed mode does not need it)."
  echo "  Add --with-colabfold-db to install for live structure prediction."
fi

# ---------------------------------------------------------------------------
# 5) Python dependencies
# ---------------------------------------------------------------------------
say "Python dependencies"
if have python3; then
  python3 -m pip install -q -r "${PROJECT_ROOT}/requirements.txt" && ok "requirements.txt installed"
elif have python; then
  python  -m pip install -q -r "${PROJECT_ROOT}/requirements.txt" && ok "requirements.txt installed"
else
  warn "python3 not found — install manually: pip install -r requirements.txt"
fi

# ---------------------------------------------------------------------------
# 6) Summary: paste these paths into your run config
# ---------------------------------------------------------------------------
say "Setup complete — copy these paths into your run config"
echo
echo "  resources:"
echo "    java_bin     : java"
echo "    p2rank_cmd   : ${P2RANK_SYMLINK_CMD##${PROJECT_ROOT}/}"
echo "    p2rank_jar   : ${P2RANK_SYMLINK_JAR##${PROJECT_ROOT}/}"
echo "    foldseek_bin : ${FOLDSEEK_BIN##${PROJECT_ROOT}/}"
echo "    pdb_foldseek_db  : ${DBS##${PROJECT_ROOT}/}/foldseek/pdb"
echo "    afsp_foldseek_db : ${DBS##${PROJECT_ROOT}/}/foldseek/alphafold_swissprot"
echo
echo "Next steps:"
echo "  1. Run smoke demo (no DBs needed, just P2Rank):"
echo "       python scripts/vermamg.py run --config examples/smoke_precomputed/config.yaml --resume --follow"
echo "  2. Start your own project:"
echo "       cp run_templates/local_run.yaml.template run_configs/my_project.yaml"
echo "       # fill [FILL] fields, then:"
echo "       python scripts/vermamg.py plan --config run_configs/my_project.yaml"
echo "       python scripts/vermamg.py run  --config run_configs/my_project.yaml --resume --follow"
