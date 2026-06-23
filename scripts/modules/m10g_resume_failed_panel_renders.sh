#!/usr/bin/env bash
set -euo pipefail

OUTDIR="${1:?usage: m10g_resume_failed_panel_renders.sh OUTDIR [N_PARALLEL]}"
N_PARALLEL="${2:-8}"
FAILED="${OUTDIR}/composite_png_failed.tsv"
LIST="${OUTDIR}/m10g_resume_missing_pmls.txt"

: "${VERMAMG_ROOT:?VERMAMG_ROOT must be set}"
: "${PYMOL_CMD:?PYMOL_CMD must be set}"

test -s "$FAILED" || { echo "ERROR: failed table missing: $FAILED" >&2; exit 2; }
mkdir -p "${OUTDIR}/logs"

awk -F'\t' 'NR > 1 {print $1}' "$FAILED" |
while read -r query; do
  find "${OUTDIR}/pml" -maxdepth 1 -type f -name "${query}_*_v6_standard.pml" -print
done | sort -u > "$LIST"

count="$(wc -l < "$LIST" | tr -d ' ')"
echo "RESUME_PMLS	${count}"
if [ "$count" = "0" ]; then
  exit 0
fi

render_one() {
  local pml="$1"
  local outdir="$2"
  local pymol="$3"
  local root="$4"
  local query
  query="$(basename "$pml" | sed 's/_v6_standard\.pml$//')"
  VERMAMG_ROOT="$root" "$pymol" -cq "$pml" >"${outdir}/logs/${query}.resume.pymol.log" 2>&1
}
export -f render_one

xargs -P "$N_PARALLEL" -I{} bash -c 'render_one "$@"' _ {} "$OUTDIR" "$PYMOL_CMD" "$VERMAMG_ROOT" < "$LIST"
