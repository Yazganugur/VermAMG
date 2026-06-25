#!/usr/bin/env bash
# m10g_composite_local_wsl_full.sh
# Full composite figure render — local_wsl, all query proteins, 3-phase parallel.
# Run ONLY after smoke PASS and visual layout confirmed.
#
# Usage:
#   cd /path/to/VermAMG
#   bash scripts/submit/m10g_composite_local_wsl_full.sh
#
# Parallelism: export M10G_N_PARALLEL=N (default 4)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── load local_wsl profile ────────────────────────────────────────────────────
source "${PROJECT_ROOT}/scripts/utils/load_vermamg_profile.sh" local_wsl
export VERMAMG_ROOT="${VERMAMG_ROOT:-$PROJECT_ROOT}"
cd "$VERMAMG_ROOT"

_fail() { echo "FATAL: $*" >&2; exit 1; }

echo "===== M10G COMPOSITE FULL RENDER — local_wsl ====="
echo "DATE:         $(date)"
echo "HOST:         $(hostname)"
echo "VERMAMG_ROOT: $VERMAMG_ROOT"
echo "N_PARALLEL:   ${M10G_N_PARALLEL:-4}"
echo ""

# ── resolve Python with PIL ───────────────────────────────────────────────────
# Same logic as smoke: pick the first candidate that can import PIL cleanly.
_find_python_with_pil() {
  local -a candidates=(
    "${PYTHON_BIN:-}"
    "$(command -v python3 2>/dev/null || true)"
    "/home/$(whoami)/miniconda3/bin/python3"
    "/opt/conda/bin/python3"
    "/usr/bin/python3"
  )

  for _cand in "${candidates[@]}"; do
    [ -z "$_cand" ] && continue
    [ -x "$_cand" ] || continue

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
  _fail "No Python with PIL found. Fix: pip install Pillow, or export PYTHON_BIN=/path/to/python3"
fi
echo ""

# ── other preflight checks ────────────────────────────────────────────────────
echo "PYMOL_CMD:    ${PYMOL_CMD:-}"
command -v apptainer >/dev/null 2>&1 || _fail "apptainer not in PATH"
test -s "${PYMOL_CMD:-}"             || _fail "PYMOL_CMD not executable: ${PYMOL_CMD:-unset}"
test -s "scripts/modules/10g_generate_full_composite_figures.py" || _fail "10g script missing"
PYMOL_SIF="${VERMAMG_PYMOL_SIF:-${VERMAMG_ROOT}/resources/containers/pymol_deb12_2.5.0_sc.sif}"
test -s "$PYMOL_SIF"                 || _fail "PyMOL SIF not found: $PYMOL_SIF"

# Require evidence of smoke PASS before full run
FRESH_RUN="${M10G_FRESH_RUN_REL:-runs/smoke_precomputed/smoke_3prot_v1}"
CONTRACT="${VERMAMG_ROOT}/${FRESH_RUN}/06_visual_qc_v6/full/input_manifests/full_visual_overlay_input_contract.tsv"
test -s "$CONTRACT" || _fail "M10G input contract not found: $CONTRACT"
EXPECTED_N=$(awk -F'\t' 'NR==1{for(i=1;i<=NF;i++) if($i=="panel_role") role=i; next} role && $role=="PRIMARY"{c++} END{print c+0}' "$CONTRACT")
[ "$EXPECTED_N" -ge 1 ] || _fail "No PRIMARY rows found in contract: $CONTRACT"
SMOKE_DIR="${VERMAMG_ROOT}/${FRESH_RUN}/06_visual_qc_v6/full/composite_png_smoke"
SMOKE_OK=$(find "$SMOKE_DIR" "$SMOKE_DIR/final_pngs" -maxdepth 1 -name '*_v6_standard_600dpi.png' 2>/dev/null | wc -l || echo 0)
if [ "$SMOKE_OK" -lt 1 ]; then
  _fail "No smoke composite PNGs found. Run smoke first: bash scripts/submit/m10g_composite_local_wsl_smoke.sh"
fi
echo "Smoke evidence: $SMOKE_OK composite PNG(s). Proceeding to full render."
echo ""

# ── paths ────────────────────────────────────────────────────────────────────
OUTDIR="${VERMAMG_ROOT}/${FRESH_RUN}/06_visual_qc_v6/full/composite_png"
LOGBASE="${VERMAMG_ROOT}/logs/m10g_full_$(date +%Y%m%d_%H%M%S)"
SCRIPT="scripts/modules/10g_generate_full_composite_figures.py"
N_PARALLEL="${M10G_N_PARALLEL:-4}"

mkdir -p "${OUTDIR}/pml" "${OUTDIR}/panels" "${OUTDIR}/logs" "${OUTDIR}/tables"
mkdir -p "$(dirname "$LOGBASE")"

echo "OUTDIR:    $OUTDIR"
echo "LOG_BASE:  $LOGBASE"
echo "CONTRACT:  $CONTRACT"
echo "EXPECTED:  $EXPECTED_N primary composites"
echo ""

# ════════════════════════════════════════════════════════════════════════════
# PHASE 1 — PML generation (pure Python, sequential)
# ════════════════════════════════════════════════════════════════════════════
echo "===== PHASE 1: PML generation ====="
echo "DATE: $(date)"

"$PYTHON_BIN" "$SCRIPT" \
  --workspace  "$VERMAMG_ROOT" \
  --outdir     "$OUTDIR" \
  --pymol      "$PYMOL_CMD" \
  --pml-only \
  2>&1 | tee "${LOGBASE}_phase1_pml.log"

PML_COUNT=$(find "${OUTDIR}/pml" -maxdepth 1 -name '*.pml' | wc -l)
echo ""
echo "Phase 1 complete: $PML_COUNT PML files"
echo ""
[ "$PML_COUNT" -ge 1 ] || _fail "Phase 1 produced no PML files"

# ════════════════════════════════════════════════════════════════════════════
# PHASE 2 — PyMOL rendering (parallel via xargs)
# ════════════════════════════════════════════════════════════════════════════
echo "===== PHASE 2: PyMOL rendering (N_PARALLEL=$N_PARALLEL) ====="
echo "DATE: $(date)"

_render_one() {
  local pml_file="$1" log_dir="$2" pymol_cmd="$3" vermamg_root="$4"
  local query log_file ec
  query="$(basename "$pml_file" | sed 's/_v6_standard\.pml$//')"
  log_file="${log_dir}/${query}.pymol.log"
  VERMAMG_ROOT="$vermamg_root" "$pymol_cmd" -cq "$pml_file" >"$log_file" 2>&1
  ec=$?
  if [ $ec -ne 0 ]; then
    echo "RENDER_FAIL: $query"
  else
    echo "RENDER_OK:   $query"
  fi
  return $ec
}
export -f _render_one

RENDER_LOG="${LOGBASE}_phase2_render.log"
echo "Rendering $PML_COUNT PMLs with $N_PARALLEL parallel jobs..."

find "${OUTDIR}/pml" -maxdepth 1 -name '*.pml' | sort | \
  xargs -P "$N_PARALLEL" -I{} \
    bash -c '_render_one "$@"' _ {} "${OUTDIR}/logs" "$PYMOL_CMD" "$VERMAMG_ROOT" \
  2>&1 | tee "$RENDER_LOG"

PANEL_DIRS=$(find "${OUTDIR}/panels" -mindepth 1 -maxdepth 1 -type d | wc -l)
RENDER_FAIL_N=$(grep -c "RENDER_FAIL:" "$RENDER_LOG" 2>/dev/null || echo 0)
echo ""
echo "Phase 2 complete: $PANEL_DIRS protein panel dirs, $RENDER_FAIL_N render failures"
echo ""

# ════════════════════════════════════════════════════════════════════════════
# PHASE 3 — Composite assembly (PIL, sequential)
# ════════════════════════════════════════════════════════════════════════════
echo "===== PHASE 3: Composite assembly ====="
echo "DATE: $(date)"

"$PYTHON_BIN" "$SCRIPT" \
  --workspace    "$VERMAMG_ROOT" \
  --outdir       "$OUTDIR" \
  --compose-only \
  --skip-if-exists \
  --cleanup-panel-pngs \
  2>&1 | tee "${LOGBASE}_phase3_compose.log"

echo ""
echo "===== M10G FULL RENDER COMPLETE ====="
echo "DATE: $(date)"

# ── final QC ──────────────────────────────────────────────────────────────────
MANIFEST="${OUTDIR}/composite_png_manifest.tsv"
FAILED="${OUTDIR}/composite_png_failed.tsv"
QC="${OUTDIR}/composite_png_qc.tsv"

[ -s "$QC" ] && { echo "--- QC report ---"; cat "$QC"; }

PRODUCED_N=$(awk -F'\t' 'NR>1 && $3 != "PML_ONLY" {c++} END{print c+0}' "$MANIFEST" 2>/dev/null || echo 0)
FAILED_N=$(awk 'NR>1{c++} END{print c+0}' "$FAILED" 2>/dev/null || echo 0)

echo ""
echo "FINAL_PRODUCED: $PRODUCED_N"
echo "FINAL_EXPECTED: $EXPECTED_N"
echo "FINAL_FAILED:   $FAILED_N"
echo ""

if [ "$PRODUCED_N" -ge "$EXPECTED_N" ] && [ "$FAILED_N" -le 5 ]; then
  echo "M10G_FULL_COMPOSITE_QC: PASS"
  echo "Composite PNGs: $OUTDIR"
  echo "Open in Explorer: explorer.exe \"\$(wslpath -w ${OUTDIR})\""
else
  echo "M10G_FULL_COMPOSITE_QC: CHECK_NEEDED — produced=$PRODUCED_N failed=$FAILED_N"
  echo "Failed list: $FAILED"
  echo "Render log:  $RENDER_LOG"
  exit 1
fi
