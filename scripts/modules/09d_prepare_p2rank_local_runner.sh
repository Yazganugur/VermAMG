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

case "$MODE_RAW" in
  smoke|test) MODE="test" ;;
  pilot32|regression) MODE="regression" ;;
  full|tier1_full) MODE="tier1_full" ;;
  *)
    echo "ERROR: mode must be one of test/regression/tier1_full. Got: $MODE_RAW"
    exit 1
    ;;
esac

JAVA_BIN="${JAVA_BIN:-java}"
P2RANK_CMD="${P2RANK_CMD:-}"
P2RANK_JAR="${P2RANK_JAR:-}"

MODE_ROOT="${PROJECT_ROOT}/04_p2rank/${MODE}"
LOCAL_RUN_DIR="${MODE_ROOT}/local_runs"
RUN_MANIFEST="${MODE_ROOT}/${MODE}_p2rank_local_run_manifest.tsv"

QUERY_MANIFEST="${MODE_ROOT}/input_manifests/${MODE}_p2rank_query_model_manifest.tsv"
UNIQUE_REF_MANIFEST="${MODE_ROOT}/input_manifests/${MODE}_p2rank_reference_unique_structure_manifest.tsv"

QUERY_RUNNER="${LOCAL_RUN_DIR}/run${MODE}_p2rank_query_models_local.sh"
REFERENCE_RUNNER="${LOCAL_RUN_DIR}/run${MODE}_p2rank_reference_resolved_unique_local.sh"

QUERY_OUT_ROOT="${MODE_ROOT}/query_models/all"
REFERENCE_OUT_ROOT="${MODE_ROOT}/reference_models/resolved_unique"

require_under() {
  local path="$1"
  local base="$2"
  case "$path" in
    "$base"|"$base"/*) ;;
    *)
      echo "ERROR: refusing path outside allowed root: path=$path base=$base"
      exit 1
      ;;
  esac
}

require_under "$MODE_ROOT" "${PROJECT_ROOT}/04_p2rank"
require_under "$LOCAL_RUN_DIR" "$MODE_ROOT"
require_under "$RUN_MANIFEST" "$MODE_ROOT"
require_under "$QUERY_RUNNER" "$LOCAL_RUN_DIR"
require_under "$REFERENCE_RUNNER" "$LOCAL_RUN_DIR"
require_under "$QUERY_OUT_ROOT" "${MODE_ROOT}/query_models"
require_under "$REFERENCE_OUT_ROOT" "${MODE_ROOT}/reference_models"

command -v "$JAVA_BIN" >/dev/null 2>&1 || {
  echo "ERROR: JAVA_BIN command not found: $JAVA_BIN"
  exit 1
}
test -x "$P2RANK_CMD" || {
  echo "ERROR: P2RANK_CMD missing or not executable: ${P2RANK_CMD:-NA}"
  exit 1
}
test -s "$P2RANK_JAR" || {
  echo "ERROR: P2RANK_JAR missing or empty: ${P2RANK_JAR:-NA}"
  exit 1
}
test -s "$QUERY_MANIFEST" || {
  echo "ERROR: query manifest missing or empty: $QUERY_MANIFEST"
  exit 1
}
test -s "$UNIQUE_REF_MANIFEST" || {
  echo "ERROR: reference unique manifest missing or empty: $UNIQUE_REF_MANIFEST"
  exit 1
}

QUERY_ROWS="$(tail -n +2 "$QUERY_MANIFEST" | wc -l | tr -d ' ')"
REFERENCE_ROWS="$(tail -n +2 "$UNIQUE_REF_MANIFEST" | wc -l | tr -d ' ')"

query_missing=0
while IFS=$'\t' read -r mode query protein_id family query_model_pdb rest; do
  [ -n "${query:-}" ] || continue
  if [ ! -s "$query_model_pdb" ]; then
    echo "ERROR: query model PDB missing: query=$query path=$query_model_pdb"
    query_missing=$((query_missing + 1))
  fi
done < <(tail -n +2 "$QUERY_MANIFEST")

reference_missing=0
while IFS=$'\t' read -r unique_reference_id reference_layer target reference_file_path rest; do
  [ -n "${unique_reference_id:-}" ] || continue
  if [ ! -s "$reference_file_path" ]; then
    echo "ERROR: reference PDB missing: reference=$unique_reference_id target=$target path=$reference_file_path"
    reference_missing=$((reference_missing + 1))
  fi
done < <(tail -n +2 "$UNIQUE_REF_MANIFEST")

if [ "$query_missing" -ne 0 ] || [ "$reference_missing" -ne 0 ]; then
  echo "ERROR: missing PDB files detected; refusing to generate runners."
  exit 1
fi

mkdir -p "$LOCAL_RUN_DIR"

cat > "$QUERY_RUNNER" <<QUERY_RUNNER
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$PROJECT_ROOT"
MODE="$MODE"
JAVA_BIN="$JAVA_BIN"
P2RANK_CMD="$P2RANK_CMD"
P2RANK_JAR="$P2RANK_JAR"
QUERY_MANIFEST="$QUERY_MANIFEST"
OUT_ROOT="$QUERY_OUT_ROOT"
ALLOWED_ROOT="${MODE_ROOT}/query_models"

require_under() {
  local path="\$1"
  local base="\$2"
  case "\$path" in
    "\$base"|"\$base"/*) ;;
    *)
      echo "FATAL: refusing path outside allowed root: path=\$path base=\$base"
      exit 1
      ;;
  esac
}

command -v "\$JAVA_BIN" >/dev/null 2>&1 || { echo "FATAL: JAVA_BIN command not found: \$JAVA_BIN"; exit 1; }
test -x "\$P2RANK_CMD" || { echo "FATAL: P2RANK_CMD missing or not executable: \$P2RANK_CMD"; exit 1; }
test -s "\$P2RANK_JAR" || { echo "FATAL: P2RANK_JAR missing or empty: \$P2RANK_JAR"; exit 1; }
test -s "\$QUERY_MANIFEST" || { echo "FATAL: query manifest missing or empty: \$QUERY_MANIFEST"; exit 1; }
require_under "\$OUT_ROOT" "\$ALLOWED_ROOT"

mkdir -p "\$OUT_ROOT"

FAIL_LIST="\$OUT_ROOT/query_p2rank_failed.tsv"
RUN_LOG="\$OUT_ROOT/query_p2rank_run_manifest.tsv"

printf "query\tfamily\tquery_model_pdb\tout_dir\tstatus\tprediction_csv\tresidue_csv\tpocket_rows\n" > "\$RUN_LOG"
printf "query\tfamily\tquery_model_pdb\terror\n" > "\$FAIL_LIST"

echo "===== P2RANK QUERY LOCAL RUN START ====="
echo "DATE=\$(date)"
echo "HOST=\$(hostname)"
echo "QUERY_MANIFEST=\$QUERY_MANIFEST"
echo "P2RANK_CMD=\$P2RANK_CMD"
echo "OUT_ROOT=\$OUT_ROOT"

tail -n +2 "\$QUERY_MANIFEST" | while IFS=\$'\t' read -r mode query protein_id family query_model_pdb query_model_pdb_exists plddt ptm conf_class primary_layer primary_target primary_class manual_level manual_flags p2rank_role; do
  [ -n "\${query:-}" ] || continue
  run_id="\$(printf "%s" "\$query" | sed 's/[^A-Za-z0-9_.-]/_/g')"
  OUT_DIR="\$OUT_ROOT/\$run_id"
  require_under "\$OUT_DIR" "\$ALLOWED_ROOT"
  rm -rf "\$OUT_DIR"
  mkdir -p "\$OUT_DIR"

  if [ ! -s "\$query_model_pdb" ]; then
    printf "%s\t%s\t%s\tMISSING_PDB\n" "\$query" "\$family" "\$query_model_pdb" >> "\$FAIL_LIST"
    printf "%s\t%s\t%s\t%s\tMISSING_PDB\t\t\t0\n" "\$query" "\$family" "\$query_model_pdb" "\$OUT_DIR" >> "\$RUN_LOG"
    continue
  fi

  set +e
  "\$P2RANK_CMD" predict -f "\$query_model_pdb" -o "\$OUT_DIR" > "\$OUT_DIR/prank.stdout.log" 2> "\$OUT_DIR/prank.stderr.log"
  status=\$?
  set -e

  pred_csv="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_predictions.csv" | head -n 1)"
  res_csv="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_residues.csv" | head -n 1)"
  pocket_rows=0
  if [ -s "\$pred_csv" ]; then
    pocket_rows="\$(tail -n +2 "\$pred_csv" | wc -l | tr -d ' ')"
  fi

  run_status="OK"
  if [ "\$status" -ne 0 ]; then
    run_status="PRANK_EXIT_\$status"
    printf "%s\t%s\t%s\t%s\n" "\$query" "\$family" "\$query_model_pdb" "\$run_status" >> "\$FAIL_LIST"
  fi

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "\$query" "\$family" "\$query_model_pdb" "\$OUT_DIR" "\$run_status" "\$pred_csv" "\$res_csv" "\$pocket_rows" >> "\$RUN_LOG"
done

echo "query run log rows: \$(tail -n +2 "\$RUN_LOG" | wc -l | tr -d ' ')"
echo "query failed rows: \$(tail -n +2 "\$FAIL_LIST" | wc -l | tr -d ' ')"
echo "===== P2RANK QUERY LOCAL RUN DONE ====="
QUERY_RUNNER

cat > "$REFERENCE_RUNNER" <<REFERENCE_RUNNER
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$PROJECT_ROOT"
MODE="$MODE"
JAVA_BIN="$JAVA_BIN"
P2RANK_CMD="$P2RANK_CMD"
P2RANK_JAR="$P2RANK_JAR"
UNIQUE_REF_MANIFEST="$UNIQUE_REF_MANIFEST"
OUT_ROOT="$REFERENCE_OUT_ROOT"
ALLOWED_ROOT="${MODE_ROOT}/reference_models"

require_under() {
  local path="\$1"
  local base="\$2"
  case "\$path" in
    "\$base"|"\$base"/*) ;;
    *)
      echo "FATAL: refusing path outside allowed root: path=\$path base=\$base"
      exit 1
      ;;
  esac
}

command -v "\$JAVA_BIN" >/dev/null 2>&1 || { echo "FATAL: JAVA_BIN command not found: \$JAVA_BIN"; exit 1; }
test -x "\$P2RANK_CMD" || { echo "FATAL: P2RANK_CMD missing or not executable: \$P2RANK_CMD"; exit 1; }
test -s "\$P2RANK_JAR" || { echo "FATAL: P2RANK_JAR missing or empty: \$P2RANK_JAR"; exit 1; }
test -s "\$UNIQUE_REF_MANIFEST" || { echo "FATAL: reference unique manifest missing or empty: \$UNIQUE_REF_MANIFEST"; exit 1; }
require_under "\$OUT_ROOT" "\$ALLOWED_ROOT"

mkdir -p "\$OUT_ROOT"

FAIL_LIST="\$OUT_ROOT/reference_p2rank_failed.tsv"
RUN_LOG="\$OUT_ROOT/reference_p2rank_run_manifest.tsv"

printf "unique_reference_id\treference_layer\ttarget\treference_file_path\tout_dir\tstatus\tprediction_csv\tresidue_csv\tpocket_rows\n" > "\$RUN_LOG"
printf "unique_reference_id\treference_layer\ttarget\treference_file_path\terror\n" > "\$FAIL_LIST"

echo "===== P2RANK REFERENCE LOCAL RUN START ====="
echo "DATE=\$(date)"
echo "HOST=\$(hostname)"
echo "UNIQUE_REF_MANIFEST=\$UNIQUE_REF_MANIFEST"
echo "P2RANK_CMD=\$P2RANK_CMD"
echo "OUT_ROOT=\$OUT_ROOT"

tail -n +2 "\$UNIQUE_REF_MANIFEST" | while IFS=\$'\t' read -r unique_reference_id reference_layer target reference_file_path reference_file_source_class support_class example_query p2rank_role; do
  [ -n "\${unique_reference_id:-}" ] || continue
  run_id="\$(printf "%s" "\${unique_reference_id}_\${reference_layer}_\${target}" | sed 's/[^A-Za-z0-9_.-]/_/g')"
  OUT_DIR="\$OUT_ROOT/\$run_id"
  require_under "\$OUT_DIR" "\$ALLOWED_ROOT"
  rm -rf "\$OUT_DIR"
  mkdir -p "\$OUT_DIR"

  if [ ! -s "\$reference_file_path" ]; then
    printf "%s\t%s\t%s\t%s\tMISSING_REFERENCE_FILE\n" "\$unique_reference_id" "\$reference_layer" "\$target" "\$reference_file_path" >> "\$FAIL_LIST"
    printf "%s\t%s\t%s\t%s\t%s\tMISSING_REFERENCE_FILE\t\t\t0\n" "\$unique_reference_id" "\$reference_layer" "\$target" "\$reference_file_path" "\$OUT_DIR" >> "\$RUN_LOG"
    continue
  fi

  set +e
  "\$P2RANK_CMD" predict -f "\$reference_file_path" -o "\$OUT_DIR" > "\$OUT_DIR/prank.stdout.log" 2> "\$OUT_DIR/prank.stderr.log"
  status=\$?
  set -e

  pred_csv="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_predictions.csv" | head -n 1)"
  res_csv="\$(find "\$OUT_DIR" -maxdepth 3 -type f -name "*_residues.csv" | head -n 1)"
  pocket_rows=0
  if [ -s "\$pred_csv" ]; then
    pocket_rows="\$(tail -n +2 "\$pred_csv" | wc -l | tr -d ' ')"
  fi

  run_status="OK"
  if [ "\$status" -ne 0 ]; then
    run_status="PRANK_EXIT_\$status"
    printf "%s\t%s\t%s\t%s\t%s\n" "\$unique_reference_id" "\$reference_layer" "\$target" "\$reference_file_path" "\$run_status" >> "\$FAIL_LIST"
  fi

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "\$unique_reference_id" "\$reference_layer" "\$target" "\$reference_file_path" "\$OUT_DIR" "\$run_status" "\$pred_csv" "\$res_csv" "\$pocket_rows" >> "\$RUN_LOG"
done

echo "reference run log rows: \$(tail -n +2 "\$RUN_LOG" | wc -l | tr -d ' ')"
echo "reference failed rows: \$(tail -n +2 "\$FAIL_LIST" | wc -l | tr -d ' ')"
echo "===== P2RANK REFERENCE LOCAL RUN DONE ====="
REFERENCE_RUNNER

chmod +x "$QUERY_RUNNER" "$REFERENCE_RUNNER"

{
  printf "mode\trunner_role\trunner_path\tinput_manifest\toutput_root\tinput_rows\tstatus\tnote\n"
  printf "%s\tquery\t%s\t%s\t%s\t%s\tREADY\tgenerator_does_not_run_p2rank\n" "$MODE" "$QUERY_RUNNER" "$QUERY_MANIFEST" "$QUERY_OUT_ROOT" "$QUERY_ROWS"
  printf "%s\treference\t%s\t%s\t%s\t%s\tREADY\tgenerator_does_not_run_p2rank\n" "$MODE" "$REFERENCE_RUNNER" "$UNIQUE_REF_MANIFEST" "$REFERENCE_OUT_ROOT" "$REFERENCE_ROWS"
} > "$RUN_MANIFEST"

echo "===== MODULE 09D: PREPARE P2RANK LOCAL RUNNERS ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "JAVA_BIN=$JAVA_BIN"
echo "P2RANK_CMD=$P2RANK_CMD"
echo "QUERY_MANIFEST=$QUERY_MANIFEST"
echo "UNIQUE_REF_MANIFEST=$UNIQUE_REF_MANIFEST"
echo "QUERY_ROWS=$QUERY_ROWS"
echo "REFERENCE_ROWS=$REFERENCE_ROWS"
echo "QUERY_RUNNER=$QUERY_RUNNER"
echo "REFERENCE_RUNNER=$REFERENCE_RUNNER"
echo "RUN_MANIFEST=$RUN_MANIFEST"
echo
echo "MODULE09D_PREPARE_P2RANK_LOCAL_RUNNER: OK"
