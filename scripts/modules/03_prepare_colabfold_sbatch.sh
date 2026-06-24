#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-test}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="local_wsl"
fi

# Preserve launcher/YAML overrides before profile files load their defaults.
LAUNCHER_SLURM_ACCOUNT="${SLURM_ACCOUNT:-}"
LAUNCHER_SLURM_PARTITION_CPU="${SLURM_PARTITION_CPU:-}"
LAUNCHER_SLURM_PARTITION_GPU="${SLURM_PARTITION_GPU:-}"
LAUNCHER_SLURM_CPUS_GPU="${SLURM_CPUS_GPU:-${COLABFOLD_GPU_CPUS:-}}"
LAUNCHER_SLURM_MEM_GPU="${SLURM_MEM_GPU:-${COLABFOLD_GPU_MEM:-}}"
LAUNCHER_SLURM_TIME_GPU="${SLURM_TIME_GPU:-${COLABFOLD_GPU_TIME:-}}"
LAUNCHER_COLABFOLD_GPU_GRES="${COLABFOLD_GPU_GRES:-}"

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"

PROJECT_ROOT="${VERMAMG_ROOT}"
CONFIG="${PROJECT_ROOT}/config/tier1_master_config.env"
source "$CONFIG"

if [ "${EXECUTION_BACKEND:-local}" != "slurm" ]; then
  echo "M03 sbatch generator supports EXECUTION_BACKEND=slurm only; for local backend use scripts/modules/03_prepare_colabfold_local_runner.sh"
  exit 0
fi

PROFILE_NAME="${COLABFOLD_PROFILE:-local_wsl}"
PROFILE_FILE="${PROJECT_ROOT}/config/profiles/${PROFILE_NAME}.env"

if [ ! -s "$PROFILE_FILE" ]; then
  echo "HATA: ColabFold profile bulunamadı: $PROFILE_FILE"
  exit 1
fi

source "$PROFILE_FILE"

# Launcher/YAML values are explicit user intent; apply them after profile defaults.
if [ -n "$LAUNCHER_SLURM_ACCOUNT" ]; then
  SLURM_ACCOUNT="$LAUNCHER_SLURM_ACCOUNT"
  COLABFOLD_GPU_ACCOUNT="$LAUNCHER_SLURM_ACCOUNT"
fi
if [ -n "$LAUNCHER_SLURM_PARTITION_CPU" ]; then
  SLURM_PARTITION_CPU="$LAUNCHER_SLURM_PARTITION_CPU"
fi
if [ -n "$LAUNCHER_SLURM_PARTITION_GPU" ]; then
  SLURM_PARTITION_GPU="$LAUNCHER_SLURM_PARTITION_GPU"
  COLABFOLD_GPU_PARTITION="$LAUNCHER_SLURM_PARTITION_GPU"
fi
if [ -n "$LAUNCHER_SLURM_CPUS_GPU" ]; then
  SLURM_CPUS_GPU="$LAUNCHER_SLURM_CPUS_GPU"
  COLABFOLD_GPU_CPUS="$LAUNCHER_SLURM_CPUS_GPU"
fi
if [ -n "$LAUNCHER_SLURM_MEM_GPU" ]; then
  SLURM_MEM_GPU="$LAUNCHER_SLURM_MEM_GPU"
  COLABFOLD_GPU_MEM="$LAUNCHER_SLURM_MEM_GPU"
fi
if [ -n "$LAUNCHER_SLURM_TIME_GPU" ]; then
  SLURM_TIME_GPU="$LAUNCHER_SLURM_TIME_GPU"
  COLABFOLD_GPU_TIME="$LAUNCHER_SLURM_TIME_GPU"
fi
if [ -n "$LAUNCHER_COLABFOLD_GPU_GRES" ]; then
  COLABFOLD_GPU_GRES="$LAUNCHER_COLABFOLD_GPU_GRES"
fi

case "$MODE_RAW" in
  smoke) MODE="test" ;;
  pilot32) MODE="regression" ;;
  tier1_full) MODE="full" ;;
  test|regression|full) MODE="$MODE_RAW" ;;
  *)
    echo "HATA: MODE test, regression veya full olmalı."
    exit 1
    ;;
esac

echo "===== MODULE 03: PREPARE COLABFOLD SBATCH ====="
echo "MODE_RAW: $MODE_RAW"
echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "PROFILE_NAME: $PROFILE_NAME"
echo "PROFILE_FILE: $PROFILE_FILE"
echo "COLABFOLD_GPU_ACCOUNT: $COLABFOLD_GPU_ACCOUNT"
echo "COLABFOLD_GPU_PARTITION: $COLABFOLD_GPU_PARTITION"
echo "COLABFOLD_GPU_CPUS: $COLABFOLD_GPU_CPUS"
echo "COLABFOLD_GPU_MEM: $COLABFOLD_GPU_MEM"
echo "COLABFOLD_GPU_TIME: $COLABFOLD_GPU_TIME"
echo "COLABFOLD_GPU_GRES: ${COLABFOLD_GPU_GRES:-gpu:1}"
echo "DATE: $(date)"
echo

BATCH_ROOT="${PROJECT_ROOT}/01_colabfold/batches/${MODE}"
BATCH_MANIFEST="${BATCH_ROOT}/${MODE}_colabfold_batch_manifest.tsv"
OUT_ROOT="${PROJECT_ROOT}/01_colabfold/outputs/${MODE}"
LOG_ROOT="${PROJECT_ROOT}/01_colabfold/logs/${MODE}"
SBATCH_ROOT="${PROJECT_ROOT}/01_colabfold/sbatch/${MODE}"
RUN_MANIFEST="${PROJECT_ROOT}/01_colabfold/${MODE}_colabfold_run_manifest.tsv"

test -s "$BATCH_MANIFEST"

mkdir -p "$OUT_ROOT" "$LOG_ROOT" "$SBATCH_ROOT"

rm -f "$RUN_MANIFEST"

echo -e "mode\tbatch_id\tbatch_fasta\toutput_dir\tsbatch_script\tlog_out\tlog_err\tmsa_mode\tmodel_type\tstatus" > "$RUN_MANIFEST"

tail -n +2 "$BATCH_MANIFEST" | cut -f1-3 | sort -u | while IFS=$'\t' read -r mode batch_id batch_fasta; do
  batch_out="${OUT_ROOT}/${batch_id}_colabfold_msa"
  mkdir -p "$batch_out"

  sbatch_script="${SBATCH_ROOT}/run_${MODE}_${batch_id}_colabfold.sbatch"
  log_out="${LOG_ROOT}/${MODE}_${batch_id}_colabfold.%j.out"
  log_err="${LOG_ROOT}/${MODE}_${batch_id}_colabfold.%j.err"

  cat > "$sbatch_script" <<SBATCH
#!/bin/bash
#SBATCH -J cf_${MODE}_${batch_id}
#SBATCH -A ${COLABFOLD_GPU_ACCOUNT}
#SBATCH -p ${COLABFOLD_GPU_PARTITION}
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c ${COLABFOLD_GPU_CPUS}
#SBATCH --gres=${COLABFOLD_GPU_GRES}
#SBATCH --mem=${COLABFOLD_GPU_MEM}
#SBATCH --time=${COLABFOLD_GPU_TIME}
#SBATCH -o ${log_out}
#SBATCH -e ${log_err}

set -euo pipefail

cd ${PROJECT_ROOT}

echo "===== COLABFOLD JOB START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "PWD: \$(pwd)"
echo "MODE: ${MODE}"
echo "BATCH_ID: ${batch_id}"
echo "BATCH_FASTA: ${batch_fasta}"
echo "OUTPUT_DIR: ${batch_out}"
echo "SBATCH_ACCOUNT: ${COLABFOLD_GPU_ACCOUNT}"
echo "SBATCH_PARTITION: ${COLABFOLD_GPU_PARTITION}"
echo "SBATCH_CPUS: ${COLABFOLD_GPU_CPUS}"
echo "SBATCH_MEM: ${COLABFOLD_GPU_MEM}"
echo "SBATCH_TIME: ${COLABFOLD_GPU_TIME}"
echo "SBATCH_GPU_GRES: ${COLABFOLD_GPU_GRES:-gpu:1}"

module purge || true
module load ${COLABFOLD_CUDA_MODULE} || true

export MPLCONFIGDIR="${PROJECT_ROOT}/work/mpl_cache"
mkdir -p "\$MPLCONFIGDIR"

echo
echo "===== GPU CHECK ====="
which nvidia-smi || true
nvidia-smi || true

echo
echo "===== APPTAINER CHECK ====="
which apptainer
apptainer --version || true

echo
echo "===== INPUT FASTA QC ====="
grep -c '^>' "${batch_fasta}"
grep '^>' "${batch_fasta}"

echo
echo "===== RUN COLABFOLD ====="
apptainer exec --nv \\
  -B ${PROJECT_ROOT}:${PROJECT_ROOT} \\
  -B ${COLABFOLD_DATA}:${COLABFOLD_DATA} \\
  ${COLABFOLD_CONTAINER} \\
  colabfold_batch \\
    --data ${COLABFOLD_DATA} \\
    --msa-mode ${COLABFOLD_MSA_MODE} \\
    --model-type ${COLABFOLD_MODEL_TYPE} \\
    --num-recycle ${COLABFOLD_NUM_RECYCLE} \\
    --num-models ${COLABFOLD_NUM_MODELS} \\
    "${batch_fasta}" \\
    "${batch_out}"

echo
echo "===== OUTPUT QC ====="
echo -n "PDB count: "
find "${batch_out}" -maxdepth 1 -type f -name "*.pdb" | wc -l
echo -n "score JSON count: "
find "${batch_out}" -maxdepth 1 -type f -name "*scores*.json" | wc -l
echo -n "PAE JSON count: "
find "${batch_out}" -maxdepth 1 -type f -name "*predicted_aligned_error*.json" | wc -l
echo -n "PNG count: "
find "${batch_out}" -maxdepth 1 -type f -name "*.png" | wc -l

echo "===== COLABFOLD JOB END ====="
echo "DATE: \$(date)"
SBATCH

  chmod +x "$sbatch_script"

  echo -e "${MODE}\t${batch_id}\t${batch_fasta}\t${batch_out}\t${sbatch_script}\t${log_out}\t${log_err}\t${COLABFOLD_MSA_MODE}\t${COLABFOLD_MODEL_TYPE}\tPREPARED" >> "$RUN_MANIFEST"
done

echo
echo "--- ColabFold run manifest ---"
cat "$RUN_MANIFEST"

echo
echo "--- SBATCH scripts ---"
find "$SBATCH_ROOT" -type f -name "*.sbatch" | sort

echo
echo "--- SBATCH preview first script ---"
first_script=$(find "$SBATCH_ROOT" -type f -name "*.sbatch" | sort | head -1)
sed -n '1,120p' "$first_script"

echo
echo "MODULE 03 PREPARE COLABFOLD SBATCH: OK"
