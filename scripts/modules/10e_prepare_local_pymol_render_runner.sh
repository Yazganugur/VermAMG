#!/usr/bin/env bash
set -euo pipefail

MODE_RAW="${1:-test}"
SCOPE_RAW="${2:-smoke}"

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

case "$SCOPE_RAW" in
  smoke|all) SCOPE="$SCOPE_RAW" ;;
  *)
    echo "ERROR: scope must be smoke or all. Got: $SCOPE_RAW"
    exit 1
    ;;
esac

MODE_ROOT="${PROJECT_ROOT}/06_visual_qc_v6/${MODE}"
MANIFEST="${MODE_ROOT}/all_query_visual_scripts/${MODE}_all_query_visual_script_manifest.tsv"
LOCAL_RUN_DIR="${MODE_ROOT}/local_runs"
RUNNER="${LOCAL_RUN_DIR}/run${MODE}_pymol_render_${SCOPE}_local.sh"
RUN_MANIFEST="${MODE_ROOT}/${MODE}_pymol_render_local_run_manifest.tsv"
OUT_ROOT="${MODE_ROOT}/rendered_png_lite/${SCOPE}"
LOG_ROOT="${MODE_ROOT}/rendered_png_lite/logs"
WRAPPED_PML_DIR="${OUT_ROOT}/wrapped_pml"
ALLOWED_ROOT="${MODE_ROOT}/rendered_png_lite"
PYMOL_CMD_RESOLVED="${PYMOL_CMD:-pymol}"

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

require_under "$OUT_ROOT" "$ALLOWED_ROOT"
require_under "$LOG_ROOT" "$ALLOWED_ROOT"
require_under "$WRAPPED_PML_DIR" "$OUT_ROOT"
require_under "$RUNNER" "$LOCAL_RUN_DIR"
require_under "$RUN_MANIFEST" "$MODE_ROOT"

if [ ! -s "$MANIFEST" ]; then
  echo "ERROR: M10C visual script manifest missing or empty: $MANIFEST"
  exit 1
fi

mkdir -p "$LOCAL_RUN_DIR" "$OUT_ROOT" "$LOG_ROOT" "$WRAPPED_PML_DIR"

ROW_COUNT="$(tail -n +2 "$MANIFEST" | wc -l | tr -d ' ')"
if [ "$SCOPE" = "smoke" ]; then
  SELECTED_COUNT=1
else
  SELECTED_COUNT="$ROW_COUNT"
fi

cat > "$RUNNER" <<'RUNNER'
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="__PROJECT_ROOT__"
MODE="__MODE__"
SCOPE="__SCOPE__"
RUN_MANIFEST="__RUN_MANIFEST__"
OUT_ROOT="__OUT_ROOT__"
LOG_ROOT="__LOG_ROOT__"
ALLOWED_ROOT="__ALLOWED_ROOT__"
PYMOL_CMD="__PYMOL_CMD__"
RUN_LOG="${OUT_ROOT}/${MODE}_pymol_render_${SCOPE}_run_log.tsv"

require_under() {
  local path="$1"
  local base="$2"
  case "$path" in
    "$base"|"$base"/*) ;;
    *)
      echo "FATAL: refusing path outside allowed root: path=$path base=$base"
      exit 1
      ;;
  esac
}

require_project_path() {
  local path="$1"
  case "$path" in
    "$PROJECT_ROOT"|"$PROJECT_ROOT"/*|06_visual_qc_v6/*) ;;
    *)
      echo "FATAL: refusing non-project PML path: $path"
      exit 1
      ;;
  esac
}

echo "===== M10E LOCAL PYMOL RENDER RUNNER ====="
echo "MODE=$MODE"
echo "SCOPE=$SCOPE"
echo "RUN_MANIFEST=$RUN_MANIFEST"
echo "OUT_ROOT=$OUT_ROOT"
echo "LOG_ROOT=$LOG_ROOT"
echo "PYMOL_CMD=$PYMOL_CMD"

cd "$PROJECT_ROOT"

require_under "$OUT_ROOT" "$ALLOWED_ROOT"
require_under "$LOG_ROOT" "$ALLOWED_ROOT"
mkdir -p "$OUT_ROOT" "$LOG_ROOT"

if [ "${M10E_ENABLE_LOCAL_RENDER:-0}" != "1" ]; then
  echo "M10E_ENABLE_LOCAL_RENDER=${M10E_ENABLE_LOCAL_RENDER:-0}; render not started."
  exit 0
fi

test -x "$PYMOL_CMD" || { echo "FATAL: PYMOL_CMD missing or not executable: $PYMOL_CMD"; exit 1; }

printf "mode\tscope\trow_index\tvisual_id\tquery_id\tunique_reference_id\tvisual_status\treference_pocket_signal\tpml_script\texpected_png\tstdout_log\tstderr_log\texit_code\n" > "$RUN_LOG"

"${PYTHON_BIN:-python3}" - "$RUN_MANIFEST" "$OUT_ROOT" "$LOG_ROOT" <<'PY' | while IFS=$'\t' read -r ROW_INDEX VISUAL_ID QUERY_ID UNIQUE_REFERENCE_ID VISUAL_STATUS REFERENCE_POCKET_SIGNAL REFERENCE_POCKET_OVERLAY QUERY_POCKET_OVERLAY PML_SCRIPT EXPECTED_PNG STDOUT_LOG STDERR_LOG; do
import csv
import sys
from pathlib import Path

run_manifest, out_root, log_root = map(Path, sys.argv[1:4])
required = [
    "visual_id",
    "pml_script",
    "expected_png",
    "stdout_log",
    "stderr_log",
    "reference_pocket_signal",
    "reference_pocket_overlay",
    "query_pocket_overlay",
]

with run_manifest.open(newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    missing = [col for col in required if col not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit("FATAL: run manifest missing required columns: " + ",".join(missing))
    for idx, row in enumerate(reader, start=1):
        values = [
            str(idx),
            row.get("visual_id", ""),
            row.get("query_id", ""),
            row.get("unique_reference_id", ""),
            row.get("visual_status", ""),
            row.get("reference_pocket_signal", ""),
            row.get("reference_pocket_overlay", ""),
            row.get("query_pocket_overlay", ""),
            row.get("pml_script", ""),
            row.get("expected_png", ""),
            row.get("stdout_log", ""),
            row.get("stderr_log", ""),
        ]
        print("\t".join(values))
PY
  require_project_path "$PML_SCRIPT"
  if [ ! -s "$PML_SCRIPT" ]; then
    echo "FATAL: PML missing or empty: $PML_SCRIPT"
    exit 1
  fi

  PNG_BASE="${EXPECTED_PNG%.png}"
  PYMOL_PNG_CREATED="${PNG_BASE}.png"
  require_under "$EXPECTED_PNG" "$OUT_ROOT"
  require_under "$PYMOL_PNG_CREATED" "$OUT_ROOT"
  require_under "$STDOUT_LOG" "$LOG_ROOT"
  require_under "$STDERR_LOG" "$LOG_ROOT"

  set +e
  "$PYMOL_CMD" -cq "$PML_SCRIPT" > "$STDOUT_LOG" 2> "$STDERR_LOG"
  status=$?
  set -e

  if [ "$status" -eq 0 ] && [ ! -s "$EXPECTED_PNG" ] && [ -s "$PYMOL_PNG_CREATED" ]; then
    if [ "$PYMOL_PNG_CREATED" != "$EXPECTED_PNG" ]; then
      cp "$PYMOL_PNG_CREATED" "$EXPECTED_PNG"
    fi
  fi

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$MODE" "$SCOPE" "$ROW_INDEX" "$VISUAL_ID" "$QUERY_ID" "$UNIQUE_REFERENCE_ID" "$VISUAL_STATUS" "$REFERENCE_POCKET_SIGNAL" "$PML_SCRIPT" "$EXPECTED_PNG" "$STDOUT_LOG" "$STDERR_LOG" "$status" >> "$RUN_LOG"

  if [ "$status" -ne 0 ]; then
    echo "FATAL: PyMOL render failed for row $ROW_INDEX: $PML_SCRIPT"
    exit "$status"
  fi
done

echo "RUN_LOG=$RUN_LOG"
echo "M10E_LOCAL_PYMOL_RENDER_DONE"
RUNNER

python_safe_replace() {
  local file="$1"
  local key="$2"
  local value="$3"
  "${PYTHON_BIN:-python3}" - "$file" "$key" "$value" <<'PY'
import sys
from pathlib import Path
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
p = Path(path)
p.write_text(p.read_text().replace(key, value))
PY
}

python_safe_replace "$RUNNER" "__PROJECT_ROOT__" "$PROJECT_ROOT"
python_safe_replace "$RUNNER" "__MODE__" "$MODE"
python_safe_replace "$RUNNER" "__SCOPE__" "$SCOPE"
python_safe_replace "$RUNNER" "__RUN_MANIFEST__" "$RUN_MANIFEST"
python_safe_replace "$RUNNER" "__OUT_ROOT__" "$OUT_ROOT"
python_safe_replace "$RUNNER" "__LOG_ROOT__" "$LOG_ROOT"
python_safe_replace "$RUNNER" "__ALLOWED_ROOT__" "$ALLOWED_ROOT"
python_safe_replace "$RUNNER" "__PYMOL_CMD__" "$PYMOL_CMD_RESOLVED"

chmod +x "$RUNNER"

"${PYTHON_BIN:-python3}" - "$PROJECT_ROOT" "$MODE" "$SCOPE" "$MANIFEST" "$RUN_MANIFEST" "$RUNNER" "$OUT_ROOT" "$LOG_ROOT" "$WRAPPED_PML_DIR" <<'PY'
import csv
import re
import sys
from pathlib import Path

project_root = Path(sys.argv[1])
mode = sys.argv[2]
scope = sys.argv[3]
manifest = Path(sys.argv[4])
run_manifest = Path(sys.argv[5])
runner = Path(sys.argv[6])
out_root = Path(sys.argv[7])
log_root = Path(sys.argv[8])
wrapped_pml_dir = Path(sys.argv[9])

def resolve_project_path(value: str) -> Path:
    raw = Path(value)
    return raw if raw.is_absolute() else project_root / raw

def require_under(path: Path, base: Path, label: str) -> None:
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise SystemExit(f"ERROR: {label} outside allowed root: path={path} base={base}") from exc

def q(value: Path) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')

with manifest.open(newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))

if not rows:
    raise SystemExit(f"ERROR: manifest has no data rows: {manifest}")

if scope == "smoke":
    selected = [next((row for row in rows if row.get("panel_order") == "1"), rows[0])]
else:
    selected = rows

headers = [
    "mode",
    "scope",
    "row_index",
    "visual_id",
    "query_id",
    "unique_reference_id",
    "visual_status",
    "reference_pocket_signal",
    "reference_pocket_overlay",
    "query_pocket_overlay",
    "pml_script",
    "source_pml_script",
    "expected_png",
    "stdout_log",
    "stderr_log",
    "runner_path",
    "render_started",
    "status",
    "note",
]

with run_manifest.open("w", newline="") as out_handle:
    writer = csv.DictWriter(out_handle, fieldnames=headers, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for idx, row in enumerate(selected, start=1):
        query_id = row.get("query", "")
        panel_order = row.get("panel_order", str(idx))
        reference_layer = row.get("reference_layer", "")
        target = row.get("target", "")
        unique_reference_id = row.get("unique_reference_id", "")
        visual_status = row.get("visual_status", "")
        reference_pocket_signal = row.get("reference_pocket_signal", "")
        reference_pocket_overlay = row.get("reference_pocket_overlay", "")
        query_pocket_overlay = row.get("query_pocket_overlay", "")
        source_pml_script = row.get("pymol_script", "")

        source_pml_path = resolve_project_path(source_pml_script)
        if not source_pml_path.is_file():
            raise SystemExit(f"ERROR: source PML missing: {source_pml_script}")
        require_under(source_pml_path, project_root, "source PML")

        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{query_id}_panel{panel_order}_{reference_layer}_{target}")
        visual_id = safe_id
        wrapper_pml = wrapped_pml_dir / f"{safe_id}.wrapped.pml"
        expected_png = out_root / f"{safe_id}.png"
        stdout_log = log_root / f"{safe_id}.stdout.log"
        stderr_log = log_root / f"{safe_id}.stderr.log"

        require_under(wrapper_pml, wrapped_pml_dir, "wrapper PML")
        require_under(expected_png, out_root, "expected PNG")
        require_under(stdout_log, log_root, "stdout log")
        require_under(stderr_log, log_root, "stderr log")

        original_lines = source_pml_path.read_text().splitlines()
        wrapped_lines = []
        for line in original_lines:
            stripped = line.lstrip()
            if stripped.startswith("png ") or stripped.startswith("# png ") or stripped.startswith("save "):
                wrapped_lines.append(f"# M10E disabled original output command: {line}")
            else:
                wrapped_lines.append(line)
        png_base = expected_png.with_suffix("")
        require_under(png_base, out_root, "PyMOL PNG base")

        wrapped_lines.extend([
            "",
            "# M10E active local render output",
            f"png {q(png_base)}, dpi=200, ray=0",
            "quit",
        ])
        wrapper_pml.write_text("\n".join(wrapped_lines) + "\n")

        writer.writerow({
            "mode": mode,
            "scope": scope,
            "row_index": idx,
            "visual_id": visual_id,
            "query_id": query_id,
            "unique_reference_id": unique_reference_id,
            "visual_status": visual_status,
            "reference_pocket_signal": reference_pocket_signal,
            "reference_pocket_overlay": reference_pocket_overlay,
            "query_pocket_overlay": query_pocket_overlay,
            "pml_script": str(wrapper_pml),
            "source_pml_script": source_pml_script,
            "expected_png": str(expected_png),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "runner_path": str(runner),
            "render_started": "NO",
            "status": "READY",
            "note": "wrapper_generated_no_render",
        })
PY

SELECTED_COUNT="$(tail -n +2 "$RUN_MANIFEST" | wc -l | tr -d ' ')"

echo "===== MODULE 10E: PREPARE LOCAL PYMOL RENDER RUNNER ====="
echo "MODE_RAW=$MODE_RAW"
echo "MODE=$MODE"
echo "SCOPE=$SCOPE"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "VERMAMG_PROFILE=$VERMAMG_PROFILE"
echo "MANIFEST=$MANIFEST"
echo "PYMOL_CMD=$PYMOL_CMD_RESOLVED"
echo "RUNNER=$RUNNER"
echo "RUN_MANIFEST=$RUN_MANIFEST"
echo "INPUT_ROWS=$ROW_COUNT"
echo "SELECTED_ROWS=$SELECTED_COUNT"
echo "RENDER_STARTED=NO"
