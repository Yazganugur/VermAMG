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
cd "$PROJECT_ROOT"

case "$MODE_RAW" in
  smoke|test) MODE="test" ;;
  regression|pilot32) MODE="regression" ;;
  tier1_full|full) MODE="tier1_full" ;;
  *)
    echo "HATA: MODE test/regression/full olmalı. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

echo "===== MODULE 09D: PREPARE P2RANK QUERY + REFERENCE SBATCH ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "EXECUTION_BACKEND=${EXECUTION_BACKEND:-NA}"
echo "DATE=$(date)"
echo "HOST=$(hostname)"
echo

if [ "${EXECUTION_BACKEND:-}" != "slurm" ]; then
  echo "M09D P2Rank sbatch generator supports EXECUTION_BACKEND=slurm only; for local backend use scripts/modules/09d_prepare_p2rank_local_runner.sh"
  exit 0
fi

# Runtime checks
echo "--- P2Rank runtime profile values ---"
echo "JAVA_BIN=${JAVA_BIN:-NA}"
echo "P2RANK_HOME=${P2RANK_HOME:-NA}"
echo "P2RANK_JAR=${P2RANK_JAR:-NA}"
echo "P2RANK_CMD=${P2RANK_CMD:-NA}"
echo "P2RANK_SLURM_ACCOUNT=${P2RANK_SLURM_ACCOUNT:-NA}"
echo "P2RANK_SLURM_PARTITION=${P2RANK_SLURM_PARTITION:-NA}"
echo "P2RANK_SLURM_CPUS=${P2RANK_SLURM_CPUS:-NA}"
echo "P2RANK_SLURM_MEM=${P2RANK_SLURM_MEM:-NA}"
echo "P2RANK_SLURM_TIME=${P2RANK_SLURM_TIME:-NA}"

command -v "${JAVA_BIN:-java}" >/dev/null 2>&1 || { echo "HATA: JAVA_BIN çözülemedi: ${JAVA_BIN:-java}"; exit 1; }
test -d "${P2RANK_HOME:-}" || { echo "HATA: P2RANK_HOME bulunamadı: ${P2RANK_HOME:-NA}"; exit 1; }
test -s "${P2RANK_JAR:-}" || { echo "HATA: P2RANK_JAR bulunamadı: ${P2RANK_JAR:-NA}"; exit 1; }
test -x "${P2RANK_CMD:-}" || { echo "HATA: P2RANK_CMD executable değil: ${P2RANK_CMD:-NA}"; exit 1; }

: "${P2RANK_SLURM_ACCOUNT:?HATA: P2RANK_SLURM_ACCOUNT unset}"
: "${P2RANK_SLURM_PARTITION:?HATA: P2RANK_SLURM_PARTITION unset}"
: "${P2RANK_SLURM_CPUS:?HATA: P2RANK_SLURM_CPUS unset}"
: "${P2RANK_SLURM_MEM:?HATA: P2RANK_SLURM_MEM unset}"
: "${P2RANK_SLURM_TIME:?HATA: P2RANK_SLURM_TIME unset}"

SBATCH_DIR="04_p2rank/${MODE}/sbatch"
LOG_DIR="04_p2rank/${MODE}/logs"
mkdir -p "$SBATCH_DIR" "$LOG_DIR"

QUERY_MANIFEST="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_query_model_manifest.tsv"
UNIQUE_REF_MANIFEST="04_p2rank/${MODE}/input_manifests/${MODE}_p2rank_reference_unique_structure_manifest.tsv"

QUERY_SBATCH="$SBATCH_DIR/run_${MODE}_p2rank_query_models_all.sbatch"
REFERENCE_SBATCH="$SBATCH_DIR/run_${MODE}_p2rank_reference_resolved_unique.sbatch"

test -s "$QUERY_MANIFEST"
test -s "$UNIQUE_REF_MANIFEST"

echo "--- manifests ---"
echo "QUERY_MANIFEST=$QUERY_MANIFEST"
echo "UNIQUE_REF_MANIFEST=$UNIQUE_REF_MANIFEST"
echo -n "query manifest rows: "
tail -n +2 "$QUERY_MANIFEST" | wc -l
echo -n "reference unique manifest rows: "
tail -n +2 "$UNIQUE_REF_MANIFEST" | wc -l

echo
echo "--- writing query P2Rank sbatch ---"

cat > "$QUERY_SBATCH" <<SBATCH
#!/bin/bash
#SBATCH -J p2q_${MODE}
#SBATCH -A ${P2RANK_SLURM_ACCOUNT}
#SBATCH -p ${P2RANK_SLURM_PARTITION}
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c ${P2RANK_SLURM_CPUS}
#SBATCH --mem=${P2RANK_SLURM_MEM}
#SBATCH --time=${P2RANK_SLURM_TIME}
#SBATCH -o ${PROJECT_ROOT}/04_p2rank/${MODE}/logs/p2rank_query_all32.%j.out
#SBATCH -e ${PROJECT_ROOT}/04_p2rank/${MODE}/logs/p2rank_query_all32.%j.err

set -euo pipefail

cd ${PROJECT_ROOT}

export JAVA_HOME="\$(dirname "\$(dirname "\$(command -v ${JAVA_BIN:-java})")")"
export PATH="\$JAVA_HOME/bin:\$PATH"

QUERY_MANIFEST="${QUERY_MANIFEST}"
P2RANK_CMD="${P2RANK_CMD}"
OUT_ROOT="${PROJECT_ROOT}/04_p2rank/${MODE}/query_models/all"

mkdir -p "\$OUT_ROOT"

echo "===== P2RANK QUERY ALL MODELS START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "QUERY_MANIFEST=\$QUERY_MANIFEST"
echo "P2RANK_CMD=\$P2RANK_CMD"
echo "OUT_ROOT=\$OUT_ROOT"

echo
echo "===== MANIFEST QC ====="
echo -n "manifest rows: "
tail -n +2 "\$QUERY_MANIFEST" | wc -l
echo -n "model exists YES: "
awk -F'\\t' 'NR>1 && \$6=="YES"{c++} END{print c+0}' "\$QUERY_MANIFEST"

echo
echo "===== RUN P2RANK FOR EACH QUERY MODEL ====="

FAIL_LIST="\$OUT_ROOT/query_p2rank_failed.tsv"
RUN_LOG="\$OUT_ROOT/query_p2rank_run_manifest.tsv"

echo -e "query\\tfamily\\tquery_model_pdb\\tout_dir\\tstatus\\tprediction_csv\\tresidue_csv\\tpocket_rows" > "\$RUN_LOG"
echo -e "query\\tfamily\\tquery_model_pdb\\terror" > "\$FAIL_LIST"

tail -n +2 "\$QUERY_MANIFEST" | while IFS=\$'\\t' read -r mode query protein_id family query_model_pdb query_model_pdb_exists plddt ptm conf_class primary_layer primary_target primary_class manual_level manual_flags p2rank_role; do
  echo "----- RUN \$query / \$family -----"

  OUT_DIR="\$OUT_ROOT/\$query"
  case "\$OUT_DIR" in
    "${PROJECT_ROOT}/04_p2rank/${MODE}/query_models/"*) ;;
    *)
      echo "FATAL: refusing to clean OUT_DIR outside query_models root: \$OUT_DIR"
      exit 1
      ;;
  esac
  rm -rf "\$OUT_DIR"
  mkdir -p "\$OUT_DIR"

  if [ ! -s "\$query_model_pdb" ]; then
    echo "Missing PDB: \$query_model_pdb"
    echo -e "\$query\\t\$family\\t\$query_model_pdb\\tMISSING_PDB" >> "\$FAIL_LIST"
    echo -e "\$query\\t\$family\\t\$query_model_pdb\\t\$OUT_DIR\\tMISSING_PDB\\t\\t\\t0" >> "\$RUN_LOG"
    continue
  fi

  set +e
  "\$P2RANK_CMD" predict -f "\$query_model_pdb" -o "\$OUT_DIR" > "\$OUT_DIR/prank.stdout.log" 2> "\$OUT_DIR/prank.stderr.log"
  STATUS=\$?
  set -e

  PRED_CSV="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_predictions.csv" | head -n 1)"
  RES_CSV="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_residues.csv" | head -n 1)"
  POCKET_ROWS=0
  if [ -s "\$PRED_CSV" ]; then
    POCKET_ROWS="\$(tail -n +2 "\$PRED_CSV" | wc -l)"
  fi

  RUN_STATUS="OK"
  if [ "\$STATUS" -ne 0 ]; then
    RUN_STATUS="PRANK_EXIT_\$STATUS"
    echo -e "\$query\\t\$family\\t\$query_model_pdb\\tPRANK_EXIT_\$STATUS" >> "\$FAIL_LIST"
  fi

  echo -e "\$query\\t\$family\\t\$query_model_pdb\\t\$OUT_DIR\\t\$RUN_STATUS\\t\$PRED_CSV\\t\$RES_CSV\\t\$POCKET_ROWS" >> "\$RUN_LOG"
done

echo
echo -n "query output dirs: "
find "\$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l
echo -n "failed rows: "
tail -n +2 "\$FAIL_LIST" | wc -l
echo -n "run log rows: "
tail -n +2 "\$RUN_LOG" | wc -l

echo "===== P2RANK QUERY ALL MODELS DONE ====="
echo "DATE: \$(date)"
SBATCH

echo
echo "--- writing reference P2Rank sbatch ---"

cat > "$REFERENCE_SBATCH" <<SBATCH
#!/bin/bash
#SBATCH -J p2ref_${MODE}
#SBATCH -A ${P2RANK_SLURM_ACCOUNT}
#SBATCH -p ${P2RANK_SLURM_PARTITION}
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c ${P2RANK_SLURM_CPUS}
#SBATCH --mem=${P2RANK_SLURM_MEM}
#SBATCH --time=${P2RANK_SLURM_TIME}
#SBATCH -o ${PROJECT_ROOT}/04_p2rank/${MODE}/logs/p2rank_reference_resolved_unique.%j.out
#SBATCH -e ${PROJECT_ROOT}/04_p2rank/${MODE}/logs/p2rank_reference_resolved_unique.%j.err

set -euo pipefail

cd ${PROJECT_ROOT}

export JAVA_HOME="\$(dirname "\$(dirname "\$(command -v ${JAVA_BIN:-java})")")"
export PATH="\$JAVA_HOME/bin:\$PATH"

UNIQUE_REF_MANIFEST="${UNIQUE_REF_MANIFEST}"
P2RANK_CMD="${P2RANK_CMD}"
OUT_ROOT="${PROJECT_ROOT}/04_p2rank/${MODE}/reference_models/resolved_unique"

mkdir -p "\$OUT_ROOT"

echo "===== P2RANK REFERENCE RESOLVED UNIQUE START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "UNIQUE_REF_MANIFEST=\$UNIQUE_REF_MANIFEST"
echo "P2RANK_CMD=\$P2RANK_CMD"
echo "OUT_ROOT=\$OUT_ROOT"

echo
echo "===== MANIFEST QC ====="
echo -n "manifest rows: "
tail -n +2 "\$UNIQUE_REF_MANIFEST" | wc -l
echo -n "reference file exists YES: "
awk -F'\\t' 'NR>1 && \$4!=""{c++} END{print c+0}' "\$UNIQUE_REF_MANIFEST"

echo
echo "===== RUN P2RANK FOR EACH RESOLVED REFERENCE STRUCTURE ====="

FAIL_LIST="\$OUT_ROOT/reference_p2rank_failed.tsv"
RUN_LOG="\$OUT_ROOT/reference_p2rank_run_manifest.tsv"

echo -e "unique_reference_id\\treference_layer\\ttarget\\treference_file_path\\tout_dir\\tstatus\\tprediction_csv\\tresidue_csv\\tpocket_rows" > "\$RUN_LOG"
echo -e "unique_reference_id\\treference_layer\\ttarget\\treference_file_path\\terror" > "\$FAIL_LIST"

tail -n +2 "\$UNIQUE_REF_MANIFEST" | while IFS=\$'\\t' read -r unique_reference_id reference_layer target reference_file_path reference_file_source_class support_class example_query p2rank_role; do
  echo "----- RUN \$unique_reference_id / \$reference_layer / \$target -----"

  SAFE_ID="\$(echo "\${unique_reference_id}_\${reference_layer}_\${target}" | sed 's/[^A-Za-z0-9_.-]/_/g')"
  OUT_DIR="\$OUT_ROOT/\$SAFE_ID"
  case "\$OUT_DIR" in
    "${PROJECT_ROOT}/04_p2rank/${MODE}/reference_models/"*) ;;
    *)
      echo "FATAL: refusing to clean OUT_DIR outside reference_models root: \$OUT_DIR"
      exit 1
      ;;
  esac
  rm -rf "\$OUT_DIR"
  mkdir -p "\$OUT_DIR"

  if [ ! -s "\$reference_file_path" ]; then
    echo "Missing reference file: \$reference_file_path"
    echo -e "\$unique_reference_id\\t\$reference_layer\\t\$target\\t\$reference_file_path\\tMISSING_REFERENCE_FILE" >> "\$FAIL_LIST"
    echo -e "\$unique_reference_id\\t\$reference_layer\\t\$target\\t\$reference_file_path\\t\$OUT_DIR\\tMISSING_REFERENCE_FILE\\t\\t\\t0" >> "\$RUN_LOG"
    continue
  fi

  set +e
  "\$P2RANK_CMD" predict -f "\$reference_file_path" -o "\$OUT_DIR" > "\$OUT_DIR/prank.stdout.log" 2> "\$OUT_DIR/prank.stderr.log"
  STATUS=\$?
  set -e

  PRED_CSV="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_predictions.csv" | head -n 1)"
  RES_CSV="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_residues.csv" | head -n 1)"
  POCKET_ROWS=0
  if [ -s "\$PRED_CSV" ]; then
    POCKET_ROWS="\$(tail -n +2 "\$PRED_CSV" | wc -l)"
  fi

  RUN_STATUS="OK"
  if [ "\$STATUS" -ne 0 ]; then
    RUN_STATUS="PRANK_EXIT_\$STATUS"
    echo -e "\$unique_reference_id\\t\$reference_layer\\t\$target\\t\$reference_file_path\\tPRANK_EXIT_\$STATUS" >> "\$FAIL_LIST"
  fi

  echo -e "\$unique_reference_id\\t\$reference_layer\\t\$target\\t\$reference_file_path\\t\$OUT_DIR\\t\$RUN_STATUS\\t\$PRED_CSV\\t\$RES_CSV\\t\$POCKET_ROWS" >> "\$RUN_LOG"
done

echo
echo -n "reference output dirs: "
find "\$OUT_ROOT" -mindepth 1 -maxdepth 1 -type d | wc -l
echo -n "failed rows: "
tail -n +2 "\$FAIL_LIST" | wc -l
echo -n "run log rows: "
tail -n +2 "\$RUN_LOG" | wc -l

echo "===== P2RANK REFERENCE RESOLVED UNIQUE DONE ====="
echo "DATE: \$(date)"
SBATCH

echo
echo "--- generated sbatch preview ---"
echo "QUERY_SBATCH=$QUERY_SBATCH"
echo "REFERENCE_SBATCH=$REFERENCE_SBATCH"
wc -l "$QUERY_SBATCH" "$REFERENCE_SBATCH"

echo
echo "--- sbatch directive preview ---"
grep -E '^#SBATCH -J|^#SBATCH -A|^#SBATCH -p|^#SBATCH -c|^#SBATCH --mem|^#SBATCH --time' "$QUERY_SBATCH"
grep -E '^#SBATCH -J|^#SBATCH -A|^#SBATCH -p|^#SBATCH -c|^#SBATCH --mem|^#SBATCH --time' "$REFERENCE_SBATCH"

echo
echo "MODULE09D_PREPARE_P2RANK_QUERY_AND_REFERENCE_SBATCH: OK"
