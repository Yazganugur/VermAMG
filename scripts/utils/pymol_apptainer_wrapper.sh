#!/usr/bin/env bash
set -euo pipefail

if [ -z "${VERMAMG_ROOT:-}" ]; then
  echo "FATAL: VERMAMG_ROOT is not set; source scripts/utils/load_vermamg_profile.sh first." >&2
  exit 1
fi

PYMOL_CONTAINER="${PYMOL_CONTAINER:-${VERMAMG_ROOT}/resources/containers/pymol_deb12_2.5.0_sc.sif}"

if ! command -v apptainer >/dev/null 2>&1; then
  echo "FATAL: apptainer command not found in PATH." >&2
  exit 1
fi

if [ ! -s "$PYMOL_CONTAINER" ]; then
  echo "FATAL: PyMOL container missing or empty: $PYMOL_CONTAINER" >&2
  exit 1
fi

exec apptainer exec \
  --bind "${VERMAMG_ROOT}:${VERMAMG_ROOT}" \
  "$PYMOL_CONTAINER" pymol "$@"
