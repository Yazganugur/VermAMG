from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if os.name == "nt":
        path.write_text(data, encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    try:
        tmp.replace(path)
    except PermissionError:
        # Some Windows/WSL shared-drive files reject atomic replace even when
        # direct writes are permitted. Keep the write inside the same run dir.
        path.write_text(data, encoding="utf-8")
        try:
            tmp.unlink()
        except OSError:
            pass


def status_path(run_root: Path) -> Path:
    return run_root / "state/status.json"


def checkpoint_path(run_root: Path, stage_id: str) -> Path:
    return run_root / "state/checkpoints" / f"{stage_id}.json"


def read_status(run_root: Path) -> dict[str, Any] | None:
    path = status_path(run_root)
    if not path.is_file():
        return None
    for _ in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            time.sleep(0.05)
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(run_root: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = utc_now()
    _write_json(status_path(run_root), payload)


def read_checkpoint(run_root: Path, stage_id: str) -> dict[str, Any] | None:
    path = checkpoint_path(run_root, stage_id)
    if not path.is_file():
        return None
    for _ in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            time.sleep(0.05)
    return json.loads(path.read_text(encoding="utf-8"))


def write_checkpoint(run_root: Path, stage_id: str, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["stage_id"] = stage_id
    payload.setdefault("finished_at", utc_now())
    _write_json(checkpoint_path(run_root, stage_id), payload)
