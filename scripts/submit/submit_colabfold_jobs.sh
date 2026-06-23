#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-regression}"

PROJECT_ROOT="/arf/scratch/yugur/baps_faz_c_v2/structural_validation_tier1_full"
cd "$PROJECT_ROOT"

case "$MODE" in
  test|regression|full)
    ;;
  *)
    echo "HATA: MODE test, regression veya full olmalı."
    exit 1
    ;;
esac

RUN_MANIFEST="01_colabfold/${MODE}_colabfold_run_manifest.tsv"
SUBMIT_LOG="pipeline_state/${MODE}_colabfold_submitted_jobs.tsv"

if [ ! -s "$RUN_MANIFEST" ]; then
  echo "HATA: run manifest yok veya boş: $RUN_MANIFEST"
  exit 1
fi

echo "mode	batch_id	job_id	partition	sbatch_script	submit_time" > "$SUBMIT_LOG"

echo "===== COLABFOLD JOB SUBMIT ====="
echo "MODE=$MODE"
echo "RUN_MANIFEST=$RUN_MANIFEST"
echo "SUBMIT_LOG=$SUBMIT_LOG"
echo "DATE=$(date)"
echo

tail -n +2 "$RUN_MANIFEST" | while IFS=$'\t' read -r mode batch_id batch_fasta output_dir sbatch_script log_out log_err msa_mode model_type status; do
  echo
  echo "===== SUBMITTING $batch_id ====="
  echo "SBATCH=$sbatch_script"

  if [ ! -s "$sbatch_script" ]; then
    echo "HATA: sbatch script yok: $sbatch_script"
    exit 1
  fi

  PARTITION=$(grep '^#SBATCH -p ' "$sbatch_script" | awk '{print $3}')
  CPUS=$(grep '^#SBATCH -c ' "$sbatch_script" | awk '{print $3}')
  GRES=$(grep '^#SBATCH --gres=' "$sbatch_script" | sed 's/#SBATCH --gres=//')

  echo "PARTITION=$PARTITION"
  echo "CPUS=$CPUS"
  echo "GRES=$GRES"

  JOB_OUTPUT=$(sbatch "$sbatch_script")
  echo "$JOB_OUTPUT"

  JOB_ID=$(echo "$JOB_OUTPUT" | awk '{print $4}')
  echo -e "${MODE}\t${batch_id}\t${JOB_ID}\t${PARTITION}\t${sbatch_script}\t$(date '+%Y-%m-%d %H:%M:%S')" >> "$SUBMIT_LOG"
done

echo
echo "===== SUBMITTED JOBS ====="
cat "$SUBMIT_LOG"

echo
echo "===== SQUEUE ====="
JOB_IDS=$(tail -n +2 "$SUBMIT_LOG" | cut -f3 | paste -sd, -)
squeue -j "$JOB_IDS" -o "%.18i %.12P %.24j %.10u %.2t %.10M %.6D %R" || true

echo
echo "SUBMIT_COLABFOLD_JOBS: OK"
