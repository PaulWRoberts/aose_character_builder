"""Persistent storage for the user's chosen default :class:`RuleSet`.

Settings live in a single JSON file at the project root (gitignored).  A new
character draft snapshots these defaults so that later edits to the global
settings never retroactively alter old characters.
"""
from __future__ import annotations

import json
from pathlib import Path

from aose.models import RuleSet

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "settings.json"


def load_settings(settings_path: Path) -> RuleSet:
    """Return the saved default :class:`RuleSet`, or a fresh one if no file exists."""
    if not settings_path.exists():
        return RuleSet()
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    return RuleSet(**data.get("ruleset", {}))


def save_settings(settings_path: Path, ruleset: RuleSet) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ruleset": ruleset.model_dump()}
    settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
