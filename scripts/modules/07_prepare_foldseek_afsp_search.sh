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
  pilot32|regression) MODE="regression" ;;
  full|tier1_full) MODE="tier1_full" ;;
  *)
    echo "HATA: MODE smoke, test, pilot32, regression, full veya tier1_full olmali. Gelen: $MODE_RAW"
    exit 1
    ;;
esac

FOLDSEEK_BIN="${FOLDSEEK_BIN}"
AFSP_DB="${AFSP_FOLDSEEK_DB}"

QUERY_PDB_DIR="02_foldseek/querydb/${MODE}/pdb_inputs"
QUERY_DB="02_foldseek/querydb/${MODE}/${MODE}_query_db"
RESULT_DB="02_foldseek/afsp_search/${MODE}/${MODE}_vs_afsp_result_db"
TMP_DIR="02_foldseek/tmp/${MODE}/afsp_search_tmp"

ALL_HITS="02_foldseek/tables/${MODE}/${MODE}_vs_afsp_foldseek_all_hits.tsv"
RUN_SUMMARY="02_foldseek/qc/${MODE}/${MODE}_vs_afsp_foldseek_run_summary.tsv"

SBATCH_SCRIPT="02_foldseek/sbatch/${MODE}/run_${MODE}_foldseek_afsp_search.sbatch"

echo "===== MODULE 07: PREPARE AFSP FOLDSEEK SEARCH ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "DATE=$(date)"
echo

if [[ "${EXECUTION_BACKEND:-}" != "slurm" ]]; then
  echo "M07 Foldseek AFSP sbatch generator supports EXECUTION_BACKEND=slurm only; for local backend use scripts/modules/07_prepare_foldseek_afsp_local_runner.sh"
  exit 0
fi

: "${FOLDSEEK_AFSP_SLURM_ACCOUNT:?HATA: FOLDSEEK_AFSP_SLURM_ACCOUNT unset}"
: "${FOLDSEEK_AFSP_SLURM_PARTITION:?HATA: FOLDSEEK_AFSP_SLURM_PARTITION unset}"
: "${FOLDSEEK_AFSP_SLURM_CPUS:?HATA: FOLDSEEK_AFSP_SLURM_CPUS unset}"
: "${FOLDSEEK_AFSP_SLURM_MEM:?HATA: FOLDSEEK_AFSP_SLURM_MEM unset}"
: "${FOLDSEEK_AFSP_SLURM_TIME:?HATA: FOLDSEEK_AFSP_SLURM_TIME unset}"
FOLDSEEK_AFSP_THREADS="${FOLDSEEK_AFSP_THREADS:-${FOLDSEEK_AFSP_SLURM_CPUS}}"

mkdir -p \
  02_foldseek/afsp_search/${MODE} \
  02_foldseek/tables/${MODE} \
  02_foldseek/qc/${MODE} \
  02_foldseek/logs/${MODE} \
  02_foldseek/tmp/${MODE} \
  02_foldseek/sbatch/${MODE}

echo
echo "===== 1) RESOURCE QC ====="
test -x "$FOLDSEEK_BIN"
test -s "${AFSP_DB}.dbtype"
test -d "$QUERY_PDB_DIR"

ls -lh "$FOLDSEEK_BIN"
ls -lh "${AFSP_DB}.dbtype"

echo -n "query PDB count: "
find "$QUERY_PDB_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l

echo
echo "===== 2) SBATCH SCRIPT YAZILIYOR ====="

cat > "$SBATCH_SCRIPT" <<SBATCH
#!/bin/bash
#SBATCH -J fs_${MODE}_afsp
#SBATCH -A ${FOLDSEEK_AFSP_SLURM_ACCOUNT}
#SBATCH -p ${FOLDSEEK_AFSP_SLURM_PARTITION}
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c ${FOLDSEEK_AFSP_SLURM_CPUS}
#SBATCH --mem=${FOLDSEEK_AFSP_SLURM_MEM}
#SBATCH --time=${FOLDSEEK_AFSP_SLURM_TIME}
#SBATCH -o ${PROJECT_ROOT}/02_foldseek/logs/${MODE}/${MODE}_foldseek_afsp.%j.out
#SBATCH -e ${PROJECT_ROOT}/02_foldseek/logs/${MODE}/${MODE}_foldseek_afsp.%j.err

set -euo pipefail

cd ${PROJECT_ROOT}

echo "===== FOLDSEEK AFSP SEARCH START ====="
echo "DATE: \$(date)"
echo "HOST: \$(hostname)"
echo "PWD: \$(pwd)"
echo "MODE: ${MODE}"

PROJECT_ROOT="${PROJECT_ROOT}"
FOLDSEEK_ROOT="${PROJECT_ROOT}/02_foldseek"
FOLDSEEK_BIN="${FOLDSEEK_BIN}"
FOLDSEEK_AFSP_THREADS="${FOLDSEEK_AFSP_THREADS}"
AFSP_DB="${AFSP_DB}"
QUERY_PDB_DIR="${QUERY_PDB_DIR}"
QUERY_DB="${QUERY_DB}"
RESULT_DB="${RESULT_DB}"
TMP_DIR="${TMP_DIR}"
ALL_HITS="${ALL_HITS}"
RUN_SUMMARY="${RUN_SUMMARY}"

fatal() {
  echo "HATA: \$*" >&2
  exit 1
}

resolve_project_path() {
  local path="\$1"
  case "\$path" in
    /*) printf '%s\n' "\$path" ;;
    *) printf '%s/%s\n' "\$PROJECT_ROOT" "\$path" ;;
  esac
}

require_under_foldseek() {
  local label="\$1"
  local path="\$2"
  local abs
  [ -n "\$path" ] || fatal "\$label is empty"
  abs="\$(resolve_project_path "\$path")"
  case "\$abs" in
    "\$FOLDSEEK_ROOT"/*) ;;
    *) fatal "\$label outside FOLDSEEK_ROOT: \$path" ;;
  esac
}

echo
echo "===== INPUT QC ====="
ls -lh "\$FOLDSEEK_BIN"
ls -lh "\${AFSP_DB}.dbtype"

echo -n "query PDB count: "
find "\$QUERY_PDB_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l

require_under_foldseek "TMP_DIR" "\$TMP_DIR"
require_under_foldseek "RESULT_DB" "\$RESULT_DB"
require_under_foldseek "ALL_HITS" "\$ALL_HITS"
require_under_foldseek "RUN_SUMMARY" "\$RUN_SUMMARY"
require_under_foldseek "QUERY_DB" "\$QUERY_DB"

echo
echo "===== CLEAN OLD AFSP OUTPUTS ====="
rm -rf "\$TMP_DIR"
mkdir -p "\$TMP_DIR"
rm -f "\$RESULT_DB"* "\$ALL_HITS" "\$RUN_SUMMARY"

echo
echo "===== ENSURE QUERY DB EXISTS ====="
if [ ! -s "\${QUERY_DB}.dbtype" ]; then
  echo "Query DB yok; createdb çalıştırılıyor."
  rm -f "\$QUERY_DB"*
  "\$FOLDSEEK_BIN" createdb "\$QUERY_PDB_DIR" "\$QUERY_DB"
else
  echo "Mevcut query DB kullanılacak: \$QUERY_DB"
fi

echo
echo "===== FOLDSEEK SEARCH VS AFSP ====="
"\$FOLDSEEK_BIN" search "\$QUERY_DB" "\$AFSP_DB" "\$RESULT_DB" "\$TMP_DIR" --threads "\$FOLDSEEK_AFSP_THREADS" --max-seqs 50 -a

echo
echo "===== FOLDSEEK CONVERTALIS ====="
"\$FOLDSEEK_BIN" convertalis "\$QUERY_DB" "\$AFSP_DB" "\$RESULT_DB" "\$ALL_HITS.tmp" --format-output query,target,evalue,bits,prob,alntmscore,qtmscore,ttmscore,lddt,qcov,tcov,qlen,tlen

echo -e "query\ttarget\tevalue\tbits\tprob\talntmscore\tqtmscore\tttmscore\tlddt\tqcov\ttcov\tqlen\ttlen\tbatch" > "\$ALL_HITS"
awk -v OFS='\\t' '{print \$0, "afsp_search"}' "\$ALL_HITS.tmp" >> "\$ALL_HITS"
rm -f "\$ALL_HITS.tmp"

echo
echo "===== RUN SUMMARY ====="
{
  echo -e "metric\tvalue"
  echo -e "mode\t${MODE}"
  echo -e "query_pdb_count\t\$(find "\$QUERY_PDB_DIR" -maxdepth 1 -type f -name "*.pdb" | wc -l)"
  echo -e "afsp_all_hit_rows\t\$(( \$(wc -l < "\$ALL_HITS") - 1 ))"
} > "\$RUN_SUMMARY"

cat "\$RUN_SUMMARY"

echo
echo "===== OUTPUT QC ====="
ls -lh "\$ALL_HITS" "\$RUN_SUMMARY"

echo "FOLDSEEK_AFSP_SEARCH: DONE"
echo "DATE: \$(date)"
SBATCH

chmod +x "$SBATCH_SCRIPT"

echo
echo "===== 3) SBATCH KONTROL ====="
grep -E '^#SBATCH -J|^#SBATCH -A|^#SBATCH -p|^#SBATCH -c|^#SBATCH --mem|^#SBATCH --time' "$SBATCH_SCRIPT"

echo
echo "MODULE07_PREPARE_AFSP_FOLDSEEK_SEARCH: OK"
