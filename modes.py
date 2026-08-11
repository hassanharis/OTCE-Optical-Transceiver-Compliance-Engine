"""Reading of the per-mode records stored in a run's modes.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LABEL_KEY = "label"
MODES_FILE = "modes.json"


def read_modes(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    modes = data.get("modes", []) if isinstance(data, dict) else data
    if not isinstance(modes, list):
        return []
    return [mode for mode in modes if isinstance(mode, dict)]


def flatten(value: Any) -> Any:
    """Collapse list and dict values so they fit in a single table cell."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None) or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def mode_label(mode: dict[str, Any], position: int) -> str:
    return str(mode.get(LABEL_KEY) or f"Mode {position}")
