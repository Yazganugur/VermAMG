#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${VERMAMG_PROFILE:-}" ]; then
  VERMAMG_PROFILE="truba"
fi

# shellcheck disable=SC1090
source "${AUTO_ROOT}/scripts/utils/load_vermamg_profile.sh" "$VERMAMG_PROFILE"


MODE="${1:-test}"

PROJECT_ROOT="${VERMAMG_ROOT}"
CONFIG="${PROJECT_ROOT}/config/tier1_master_config.env"
source "$CONFIG"

echo "MODE: $MODE"
echo "PROJECT_ROOT: $PROJECT_ROOT"

case "$MODE" in
  test|regression|full|smoke|pilot32|tier1_full)
    ;;
  *)
    echo "HATA: MODE test, regression veya full olmalı."
    exit 1
    ;;
esac

echo
echo "--- Full candidate input QC ---"
test -s "$FULL_CANDIDATE_TABLE"
test -s "$FULL_CANDIDATE_IDS"
test -s "$FULL_CANDIDATE_FASTA"
test -s "$FULL_CANDIDATE_METADATA"

FULL_TABLE_LINES=$(wc -l < "$FULL_CANDIDATE_TABLE")
FULL_IDS_LINES=$(wc -l < "$FULL_CANDIDATE_IDS")
FULL_FASTA_N=$(grep -c '^>' "$FULL_CANDIDATE_FASTA")
FULL_META_LINES=$(wc -l < "$FULL_CANDIDATE_METADATA")

echo "full_candidate_table_lines=$FULL_TABLE_LINES"
echo "full_candidate_ids_lines=$FULL_IDS_LINES"
echo "full_candidate_fasta_proteins=$FULL_FASTA_N"
echo "full_candidate_metadata_lines=$FULL_META_LINES"

if [ "$FULL_TABLE_LINES" -ne 238 ]; then
  echo "HATA: Full candidate table 238 satır olmalı."
  exit 1
fi

if [ "$FULL_IDS_LINES" -ne 237 ]; then
  echo "HATA: Full candidate ID sayısı 237 olmalı."
  exit 1
fi

if [ "$FULL_FASTA_N" -ne 237 ]; then
  echo "HATA: Full candidate FASTA 237 protein içermeli."
  exit 1
fi

echo
echo "--- Regression/control set QC ---"
test -s "$REGRESSION_FASTA"
test -s "$REGRESSION_CANDIDATES"
test -s "$REGRESSION_OLD_DECISION"
test -s "$REGRESSION_OLD_SECTION8"

REGRESSION_FASTA_N=$(grep -c '^>' "$REGRESSION_FASTA")
REGRESSION_CAND_LINES=$(wc -l < "$REGRESSION_CANDIDATES")
REGRESSION_OLD_DECISION_LINES=$(wc -l < "$REGRESSION_OLD_DECISION")
REGRESSION_OLD_SECTION8_LINES=$(wc -l < "$REGRESSION_OLD_SECTION8")

echo "regression_fasta_proteins=$REGRESSION_FASTA_N"
echo "regression_candidates_lines=$REGRESSION_CAND_LINES"
echo "regression_old_decision_lines=$REGRESSION_OLD_DECISION_LINES"
echo "regression_old_section8_lines=$REGRESSION_OLD_SECTION8_LINES"

if [ "$REGRESSION_FASTA_N" -ne 32 ]; then
  echo "HATA: Regression FASTA 32 protein içermeli."
  exit 1
fi

if [ "$REGRESSION_OLD_DECISION_LINES" -ne 33 ]; then
  echo "HATA: Eski regression decision matrix 33 satır olmalı."
  exit 1
fi

if [ "$REGRESSION_OLD_SECTION8_LINES" -ne 33 ]; then
  echo "HATA: Eski Section8 compact view 33 satır olmalı."
  exit 1
fi

echo
echo "--- Tool/resource path QC ---"
for p in \
  "$COLABFOLD_CONTAINER" \
  "$COLABFOLD_DATA" \
  "$FOLDSEEK_BIN" \
  "$P2RANK_JAR" \
  "$SECTION8_ROOT" \
  "$VISUAL_QC_ROOT"
do
  echo "--- $p ---"
  if [ -e "$p" ]; then
    ls -ld "$p"
  else
    echo "HATA: bulunamadı: $p"
    exit 1
  fi
done

echo
echo "--- Basic command QC ---"
command -v "${PYTHON_BIN:-python3}" || true
"${PYTHON_BIN:-python3}" --version || true
which java || true
java -version 2>&1 | head -3 || true
which apptainer || true

echo

echo
echo "--- P2Rank profile runtime QC ---"
echo "JAVA_BIN=${JAVA_BIN:-NA}"
echo "P2RANK_HOME=${P2RANK_HOME:-NA}"
echo "P2RANK_JAR=${P2RANK_JAR:-NA}"
echo "P2RANK_CMD=${P2RANK_CMD:-NA}"
command -v "${JAVA_BIN:-java}" >/dev/null 2>&1 || { echo "HATA: JAVA_BIN çözülemedi: ${JAVA_BIN:-java}"; exit 1; }
test -d "${P2RANK_HOME:-}" || { echo "HATA: P2RANK_HOME bulunamadı: ${P2RANK_HOME:-NA}"; exit 1; }
test -s "${P2RANK_JAR:-}" || { echo "HATA: P2RANK_JAR bulunamadı: ${P2RANK_JAR:-NA}"; exit 1; }
test -x "${P2RANK_CMD:-}" || { echo "HATA: P2RANK_CMD executable değil: ${P2RANK_CMD:-NA}"; exit 1; }

echo "MODULE 00 INPUT QC: OK"
