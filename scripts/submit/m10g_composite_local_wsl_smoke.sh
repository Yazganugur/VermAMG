#!/usr/bin/env bash
# m10g_composite_local_wsl_smoke.sh
# Smoke render — local_wsl, 3 proteins, sequential.
#
# Usage:
#   cd /path/to/VermAMG
#   bash scripts/submit/m10g_composite_local_wsl_smoke.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── load local_wsl profile ────────────────────────────────────────────────────
source "${PROJECT_ROOT}/scripts/utils/load_vermamg_profile.sh" local_wsl
export VERMAMG_ROOT="${VERMAMG_ROOT:-$PROJECT_ROOT}"
cd "$VERMAMG_ROOT"

_fail() { echo "FATAL: $*" >&2; exit 1; }

echo "===== M10G COMPOSITE SMOKE — local_wsl ====="
echo "DATE:         $(date)"
echo "HOST:         $(hostname)"
echo "VERMAMG_ROOT: $VERMAMG_ROOT"
echo ""

# ── resolve Python with PIL ───────────────────────────────────────────────────
# Try candidates in priority order; pick the first one where PIL imports cleanly.
# Never inject bundled 3.9 .so files into a non-3.9 interpreter.
_find_python_with_pil() {
  local -a candidates=(
    "${PYTHON_BIN:-}"                                   # explicit override
    "$(command -v python3 2>/dev/null || true)"         # current PATH python3
    "/home/$(whoami)/miniconda3/bin/python3"            # miniconda (current user)
    "/opt/conda/bin/python3"                            # conda base alt
    "/usr/bin/python3"                                  # system fallback
  )

  for _cand in "${candidates[@]}"; do
    [ -z "$_cand" ] && continue
    [ -x "$_cand" ] || continue

    # Try clean system PIL first (no sys.path changes)
    if "$_cand" -c "from PIL import Image" 2>/dev/null; then
      _PY_VER=$("$_cand" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      _PIL_FILE=$("$_cand" -c "import PIL; print(PIL.__file__)")
      _PIL_VER=$("$_cand"  -c "import PIL; print(PIL.__version__)")
      echo "PYTHON_BIN:   $_cand"
      echo "PYTHON_VER:   $_PY_VER"
      echo "PIL_FILE:     $_PIL_FILE"
      echo "PIL_VERSION:  $_PIL_VER"
      PYTHON_BIN="$_cand"
      export PYTHON_BIN
      return 0
    fi

    # For Python 3.9 only: try bundled PIL as fallback
    _VER=$("$_cand" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
    if [ "$_VER" = "3.9" ]; then
      _BUNDLED="${VERMAMG_PYMOL_PIL_SITE:-${VERMAMG_ROOT}/resources/tools/pymol_pydeps/lib/python3.9/site-packages}"
      if [ -d "$_BUNDLED" ] && PYMOL_PIL_SITE="$_BUNDLED" "$_cand" -c "from PIL import Image" 2>/dev/null; then
        export PYMOL_PIL_SITE="$_BUNDLED"
        _PIL_FILE=$("$_cand" -c "import sys; sys.path.insert(0,'$_BUNDLED'); import PIL; print(PIL.__file__)")
        _PIL_VER=$("$_cand"  -c "import sys; sys.path.insert(0,'$_BUNDLED'); import PIL; print(PIL.__version__)")
        echo "PYTHON_BIN:   $_cand"
        echo "PYTHON_VER:   3.9"
        echo "PIL_FILE:     $_PIL_FILE  (bundled)"
        echo "PIL_VERSION:  $_PIL_VER"
        PYTHON_BIN="$_cand"
        export PYTHON_BIN
        return 0
      fi
    fi
  done

  return 1
}

echo "--- Detecting Python with PIL ---"
if ! _find_python_with_pil; then
  echo ""
  echo "FATAL: No Python with PIL found. Tried:"
  echo "  \$PYTHON_BIN, which python3, ~/miniconda3/bin/python3,"
  echo "  /opt/conda/bin/python3, /usr/bin/python3"
  echo ""
  echo "Fix: activate your conda env first, or run:"
  echo "  pip install Pillow"
  echo "  export PYTHON_BIN=\$(which python3)"
  exit 1
fi
echo ""

# ── other preflight checks ────────────────────────────────────────────────────
echo "PYMOL_CMD:    ${PYMOL_CMD:-}"
command -v apptainer >/dev/null 2>&1 || _fail "apptainer not found in PATH"
test -s "${PYMOL_CMD:-}"             || _fail "PYMOL_CMD not executable: ${PYMOL_CMD:-unset}"
test -s "scripts/modules/10g_generate_full_composite_figures.py" || _fail "10g script missing"
PYMOL_SIF="${VERMAMG_PYMOL_SIF:-${VERMAMG_ROOT}/resources/containers/pymol_deb12_2.5.0_sc.sif}"
test -s "$PYMOL_SIF"                 || _fail "PyMOL SIF not found: $PYMOL_SIF"
echo ""

# ── clear stale smoke output ──────────────────────────────────────────────────
FRESH_RUN="${M10G_FRESH_RUN_REL:-runs/full_composite_run_v1}"
OUTDIR="${VERMAMG_ROOT}/${FRESH_RUN}/06_visual_qc_v6/full/composite_png_smoke"

if [ -d "$OUTDIR" ]; then
  echo "Clearing stale smoke output: $OUTDIR"
  rm -rf "$OUTDIR"
fi
mkdir -p "$OUTDIR"

# ── run ───────────────────────────────────────────────────────────────────────
LOGFILE="${VERMAMG_ROOT}/logs/m10g_smoke_$(date +%Y%m%d_%H%M%S).log"
SCRIPT="scripts/modules/10g_generate_full_composite_figures.py"
SMOKE_IDS="${M10G_SMOKE_IDS}"

mkdir -p "$(dirname "$LOGFILE")"

echo "OUTDIR:    $OUTDIR"
echo "LOG:       $LOGFILE"
echo "SMOKE_IDS: $SMOKE_IDS"
echo ""
echo "--- Running smoke (3 proteins, sequential) ---"

"$PYTHON_BIN" "$SCRIPT" \
  --workspace  "$VERMAMG_ROOT" \
  --outdir     "$OUTDIR" \
  --pymol      "$PYMOL_CMD" \
  --only       "$SMOKE_IDS" \
  --cleanup-panel-pngs \
  2>&1 | tee "$LOGFILE"

echo ""
echo "===== M10G SMOKE COMPLETE ====="

# ── QC ────────────────────────────────────────────────────────────────────────
MANIFEST="${OUTDIR}/composite_png_manifest.tsv"
FAILED="${OUTDIR}/composite_png_failed.tsv"
QC="${OUTDIR}/composite_png_qc.tsv"

if [ -s "$QC" ]; then
  echo "--- Smoke QC report ---"
  cat "$QC"
fi

PRODUCED_N=$(awk -F'\t' 'NR>1 && $3 != "PML_ONLY" {c++} END{print c+0}' "$MANIFEST" 2>/dev/null || echo 0)
FAILED_N=$(awk 'NR>1{c++} END{print c+0}' "$FAILED" 2>/dev/null || echo 0)

echo ""
echo "SMOKE_PRODUCED: $PRODUCED_N / 3"
echo "SMOKE_FAILED:   $FAILED_N"
echo ""

if [ "$PRODUCED_N" -ge 3 ] && [ "$FAILED_N" -eq 0 ]; then
  echo "M10G_SMOKE_QC: PASS"
  echo ""
  echo "Smoke composite PNGs:"
  find "$OUTDIR" -maxdepth 1 -name '*_v6_standard_600dpi.png' | sort
  echo ""
  echo "Open in Explorer:"
  echo "  explorer.exe \"\$(wslpath -w ${OUTDIR})\""
  echo ""
  echo "Visually confirm layout, then run full:"
  echo "  bash scripts/submit/m10g_composite_local_wsl_full.sh"
else
  echo "M10G_SMOKE_QC: FAIL — check $LOGFILE and $FAILED"
  exit 1
fi
