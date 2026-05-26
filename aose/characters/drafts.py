import json
import secrets
from pathlib import Path
from typing import Any

DEFAULT_DRAFTS_DIR = Path("drafts")


def new_draft_id() -> str:
    return secrets.token_hex(4)


def load_draft(draft_id: str, drafts_dir: Path = DEFAULT_DRAFTS_DIR) -> dict[str, Any]:
    path = drafts_dir / f"{draft_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No draft at {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_draft(
    draft_id: str,
    draft: dict[str, Any],
    drafts_dir: Path = DEFAULT_DRAFTS_DIR,
) -> Path:
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / f"{draft_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2)
    return path


def delete_draft(draft_id: str, drafts_dir: Path = DEFAULT_DRAFTS_DIR) -> None:
    path = drafts_dir / f"{draft_id}.json"
    if path.exists():
        path.unlink()
