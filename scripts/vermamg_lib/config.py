from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised on lean local installs
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SLUG_MAX_LENGTH = 80


def _strip_inline_comment(value: str) -> str:
    quote = ""
    out = []
    for ch in value:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in {"'", '"'}:
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_scalar(value: str) -> Any:
    value = _strip_inline_comment(value).strip()
    if value == "":
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _simple_yaml_load(text: str, path: Path) -> dict[str, Any]:
    """Small YAML subset loader for VermAMG run configs when PyYAML is absent."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if stripped.startswith("- "):
            raise SystemExit(
                f"CONFIG_ERROR: list-item YAML syntax requires PyYAML: {path}:{lineno}"
            )
        if ":" not in stripped:
            raise SystemExit(f"CONFIG_ERROR: invalid YAML line: {path}:{lineno}: {raw}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"CONFIG_ERROR: empty YAML key: {path}:{lineno}")
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value = value.strip()
        if value == "" or value.startswith("#"):
            node: dict[str, Any] = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = _parse_scalar(value)
    return root


def load_run_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.is_file():
        raise SystemExit(f"CONFIG_ERROR: config not found: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text) if yaml is not None else _simple_yaml_load(text, config_path)
    if not isinstance(cfg, dict):
        raise SystemExit(f"CONFIG_ERROR: config is empty or invalid: {config_path}")
    return cfg


def get_nested(cfg: dict[str, Any], *keys: str, default: Any = None) -> Any:
    node: Any = cfg
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return default if node is None else node


def bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def slugify(value: str, *, fallback: str = "vermamg_project", max_length: int = SLUG_MAX_LENGTH) -> str:
    """Return a conservative filesystem-safe slug for user-provided names."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    if not text:
        text = fallback
    if len(text) > max_length:
        text = text[:max_length].rstrip("._-")
    return text or fallback


def first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def expand_template(
    value: str,
    *,
    run_label: str,
    mode: str,
    project_slug: str = "",
    sample_slug: str = "",
    project_name: str = "",
    sample_name: str = "",
) -> str:
    return (
        value.replace("{run_label}", run_label)
        .replace("{mode}", mode)
        .replace("{project_slug}", project_slug)
        .replace("{sample_slug}", sample_slug)
        .replace("{project_name}", project_name)
        .replace("{sample_name}", sample_name)
        .replace("{project_root}", str(PROJECT_ROOT))
    )


def resolve_project_path(
    raw: str | Path,
    *,
    run_label: str = "",
    mode: str = "",
    project_slug: str = "",
    sample_slug: str = "",
) -> Path:
    text = str(raw)
    if run_label or mode:
        text = expand_template(
            text,
            run_label=run_label,
            mode=mode,
            project_slug=project_slug,
            sample_slug=sample_slug,
        )
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def require_text(cfg: dict[str, Any], path: str) -> str:
    node: Any = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise SystemExit(f"CONFIG_ERROR: missing required field: {path}")
        node = node[part]
    text = "" if node is None else str(node).strip()
    if not text:
        raise SystemExit(f"CONFIG_ERROR: empty required field: {path}")
    return text
