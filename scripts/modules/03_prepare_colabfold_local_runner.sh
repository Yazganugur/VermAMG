#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-test}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="local_wsl"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"
CONFIG="${PROJECT_ROOT}/config/tier1_master_config.env"
source "$CONFIG"

case "$MODE_RAW" in
  smoke) MODE="test" ;;
  pilot32) MODE="regression" ;;
  tier1_full) MODE="full" ;;
  test|regression|full) MODE="$MODE_RAW" ;;
  *)
    echo "HATA: MODE test, regression veya full olmali. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

echo "===== MODULE 03 LOCAL: PREPARE COLABFOLD LOCAL RUNNERS ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "VERMAMG_PROFILE: $VERMAMG_PROFILE"
echo "EXECUTION_BACKEND: ${EXECUTION_BACKEND:-NA}"
echo "COLABFOLD_BACKEND: ${COLABFOLD_BACKEND:-NA}"
echo "DATE: $(date)"
echo

if [ "${COLABFOLD_BACKEND:-}" != "apptainer" ]; then
  echo "HATA: Local ColabFold runner generator requires COLABFOLD_BACKEND=apptainer. Current: ${COLABFOLD_BACKEND:-NA}"
  exit 1
fi

test -s "${COLABFOLD_CONTAINER:-}" || { echo "HATA: COLABFOLD_CONTAINER missing or empty: ${COLABFOLD_CONTAINER:-NA}"; exit 1; }
test -d "${COLABFOLD_DATA:-}" || { echo "HATA: COLABFOLD_DATA directory missing: ${COLABFOLD_DATA:-NA}"; exit 1; }

BATCH_ROOT="${PROJECT_ROOT}/01_colabfold/batches/${MODE}"
BATCH_MANIFEST="${BATCH_ROOT}/${MODE}_colabfold_batch_manifest.tsv"
OUT_ROOT="${PROJECT_ROOT}/01_colabfold/outputs/${MODE}"
LOG_ROOT="${PROJECT_ROOT}/01_colabfold/logs/${MODE}"
LOCAL_RUN_ROOT="${PROJECT_ROOT}/01_colabfold/local_runs/${MODE}"
RUN_MANIFEST="${PROJECT_ROOT}/01_colabfold/${MODE}_colabfold_local_run_manifest.tsv"

test -s "$BATCH_MANIFEST"

case "$LOCAL_RUN_ROOT" in
  "$PROJECT_ROOT"/01_colabfold/local_runs/*) ;;
  *)
    echo "HATA: Unsafe LOCAL_RUN_ROOT outside PROJECT_ROOT: $LOCAL_RUN_ROOT"
    exit 1
    ;;
esac

mkdir -p "$OUT_ROOT" "$LOG_ROOT" "$LOCAL_RUN_ROOT"

RUNTIME_NOTE="OK"
if ! command -v apptainer >/dev/null 2>&1; then
  RUNTIME_NOTE="RUNTIME_MISSING=apptainer"
fi

printf "mode\tbatch_id\tbatch_fasta\toutput_dir\tlocal_runner\tlog_out\tlog_err\tmsa_mode\tmodel_type\tstatus\truntime_note\n" > "$RUN_MANIFEST"

tail -n +2 "$BATCH_MANIFEST" | cut -f1-3 | sort -u | while IFS=$'\t' read -r mode batch_id batch_fasta; do
  test -s "$batch_fasta" || { echo "HATA: batch_fasta missing or empty: $batch_fasta"; exit 1; }

  batch_out="${OUT_ROOT}/${batch_id}_colabfold_msa"
  mkdir -p "$batch_out"

  local_runner="${LOCAL_RUN_ROOT}/run${MODE}_${batch_id}_colabfold_local.sh"
  log_out="${LOG_ROOT}/${MODE}_${batch_id}_colabfold_local.out"
  log_err="${LOG_ROOT}/${MODE}_${batch_id}_colabfold_local.err"

  cat > "$local_runner" <<RUNNER
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$PROJECT_ROOT"
MODE="$MODE"
BATCH_ID="$batch_id"
BATCH_FASTA="$batch_fasta"
BATCH_OUT="$batch_out"
LOG_OUT="$log_out"
LOG_ERR="$log_err"
COLABFOLD_CONTAINER="$COLABFOLD_CONTAINER"
COLABFOLD_DATA="$COLABFOLD_DATA"
COLABFOLD_CMD="${COLABFOLD_CMD:-colabfold_batch}"
COLABFOLD_MSA_MODE="$COLABFOLD_MSA_MODE"
COLABFOLD_MODEL_TYPE="$COLABFOLD_MODEL_TYPE"
COLABFOLD_NUM_RECYCLE="$COLABFOLD_NUM_RECYCLE"
COLABFOLD_NUM_MODELS="$COLABFOLD_NUM_MODELS"

cd "\$PROJECT_ROOT"

START_TIME="\$(date)"
echo "===== COLABFOLD LOCAL RUNNER ====="
echo "STAGE: PREFLIGHT"
echo "START_TIME: \$START_TIME"
echo "HOST: \$(hostname)"
echo "PWD: \$(pwd)"
echo "MODE: \$MODE"
echo "BATCH: \$BATCH_ID"
echo "INPUT: \$BATCH_FASTA"
echo "OUTPUT: \$BATCH_OUT"
echo "LOG_OUT: \$LOG_OUT"
echo "LOG_ERR: \$LOG_ERR"

command -v apptainer >/dev/null 2>&1 || {
  echo "STATUS: FAIL"
  echo "HATA: apptainer command not found; cannot run COLABFOLD_BACKEND=apptainer."
  exit 1
}

test -s "\$COLABFOLD_CONTAINER" || { echo "STATUS: FAIL"; echo "HATA: COLABFOLD_CONTAINER missing: \$COLABFOLD_CONTAINER"; exit 1; }
test -d "\$COLABFOLD_DATA" || { echo "STATUS: FAIL"; echo "HATA: COLABFOLD_DATA missing: \$COLABFOLD_DATA"; exit 1; }
test -s "\$BATCH_FASTA" || { echo "STATUS: FAIL"; echo "HATA: BATCH_FASTA missing: \$BATCH_FASTA"; exit 1; }
mkdir -p "\$BATCH_OUT" "\$(dirname "\$LOG_OUT")"

if find "\$BATCH_OUT" -mindepth 1 -maxdepth 1 | grep -q . && [ "\${FORCE:-0}" != "1" ]; then
  echo "STATUS: BLOCKED_OUTPUT_NONEMPTY"
  echo "HATA: Output directory is non-empty: \$BATCH_OUT"
  echo "Set FORCE=1 only after reviewing existing outputs."
  exit 1
fi

echo
echo "===== GPU PREFLIGHT ====="
command -v nvidia-smi >/dev/null 2>&1 || {
  echo "STATUS: FAIL"
  echo "HATA: nvidia-smi command not found; ColabFold local runner requires visible NVIDIA GPU for --nv."
  exit 1
}
nvidia-smi >/dev/null 2>&1 || {
  echo "STATUS: FAIL"
  echo "HATA: nvidia-smi failed; GPU is not visible/usable."
  exit 1
}
nvidia-smi

echo
echo "===== APPTAINER CHECK ====="
apptainer --version

echo
echo "===== INPUT FASTA QC ====="
grep -c '^>' "\$BATCH_FASTA"
grep '^>' "\$BATCH_FASTA"

echo
echo "STAGE: RUN_COLABFOLD"
echo "===== RUN COLABFOLD ====="
apptainer exec --nv \\
  -B "\$PROJECT_ROOT:\$PROJECT_ROOT" \\
  -B "\$COLABFOLD_DATA:\$COLABFOLD_DATA" \\
  "\$COLABFOLD_CONTAINER" \\
  "\$COLABFOLD_CMD" \\
    --data "\$COLABFOLD_DATA" \\
    --msa-mode "\$COLABFOLD_MSA_MODE" \\
    --model-type "\$COLABFOLD_MODEL_TYPE" \\
    --num-recycle "\$COLABFOLD_NUM_RECYCLE" \\
    --num-models "\$COLABFOLD_NUM_MODELS" \\
    "\$BATCH_FASTA" \\
    "\$BATCH_OUT" > "\$LOG_OUT" 2> "\$LOG_ERR"

echo
echo "STAGE: OUTPUT_QC"
echo "===== OUTPUT QC ====="
echo -n "PDB count: "
find "\$BATCH_OUT" -maxdepth 1 -type f -name "*.pdb" | wc -l
echo -n "score JSON count: "
find "\$BATCH_OUT" -maxdepth 1 -type f -name "*scores*.json" | wc -l
echo -n "PAE JSON count: "
find "\$BATCH_OUT" -maxdepth 1 -type f -name "*predicted_aligned_error*.json" | wc -l
echo -n "PNG count: "
find "\$BATCH_OUT" -maxdepth 1 -type f -name "*.png" | wc -l

echo "===== COLABFOLD LOCAL RUNNER END ====="
echo "DATE: \$(date)"
echo "STATUS: COMPLETED"
RUNNER

  chmod +x "$local_runner"

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "$MODE" "$batch_id" "$batch_fasta" "$batch_out" "$local_runner" "$log_out" "$log_err" \
    "$COLABFOLD_MSA_MODE" "$COLABFOLD_MODEL_TYPE" "PREPARED" "$RUNTIME_NOTE" >> "$RUN_MANIFEST"
done

echo
echo "--- ColabFold local run manifest ---"
cat "$RUN_MANIFEST"

echo
echo "--- Local runner scripts ---"
find "$LOCAL_RUN_ROOT" -type f -name "*.sh" | sort

echo
echo "--- Runtime note ---"
echo "$RUNTIME_NOTE"

echo
echo "MODULE03_PREPARE_COLABFOLD_LOCAL_RUNNER: OK"
