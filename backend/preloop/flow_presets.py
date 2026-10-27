"""Flow preset configurations loaded from YAML files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PRESETS_DIR = BASE_DIR / "presets"

# Allow overriding presets directory via environment variable
# This is used by EE to load enterprise-specific presets
PRESETS_DIR = Path(os.environ.get("PRELOOP_PRESETS_PATH", str(DEFAULT_PRESETS_DIR)))


def _extract_order(filename: str) -> int:
    """Extract numeric order prefix from a preset filename."""

    prefix = filename.split("-", 1)[0]
    try:
        return int(prefix)
    except ValueError:
        return 9999


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - YAML errors rare
        raise ValueError(f"Failed to parse preset file {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Preset file {path} must define a mapping")

    # Ensure presets default to being marked as presets unless explicitly overridden
    data.setdefault("is_preset", True)
    return data


@lru_cache()
def load_flow_presets() -> List[Dict[str, Any]]:
    """Load flow preset configurations from YAML files."""

    if not PRESETS_DIR.exists():
        # Return empty list if presets directory doesn't exist (open source default)
        return []

    preset_entries: List[Tuple[int, Dict[str, Any]]] = []
    for path in sorted(PRESETS_DIR.glob("*.yml")) + sorted(PRESETS_DIR.glob("*.yaml")):
        order = _extract_order(path.stem)
        preset_entries.append((order, _load_yaml_file(path)))

    preset_entries.sort(key=lambda entry: entry[0])
    return [config for _, config in preset_entries]


FLOW_PRESETS: List[Dict[str, Any]] = load_flow_presets()
