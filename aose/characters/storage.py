import json
import re
from pathlib import Path

from aose.models import CharacterSpec
from aose.characters.migrate_items import migrate_legacy_items

DEFAULT_CHARACTERS_DIR = Path("characters")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "character"


def unique_character_id(base: str, characters_dir: Path = DEFAULT_CHARACTERS_DIR) -> str:
    if not (characters_dir / f"{base}.json").exists():
        return base
    i = 2
    while (characters_dir / f"{base}-{i}.json").exists():
        i += 1
    return f"{base}-{i}"


def list_character_ids(characters_dir: Path = DEFAULT_CHARACTERS_DIR) -> list[str]:
    if not characters_dir.exists():
        return []
    return sorted(p.stem for p in characters_dir.glob("*.json"))


def load_character(
    character_id: str, characters_dir: Path = DEFAULT_CHARACTERS_DIR,
    data=None,
) -> CharacterSpec:
    path = characters_dir / f"{character_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No character at {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if data is not None:
        raw = migrate_legacy_items(raw, data)
    return CharacterSpec.model_validate(raw)


def save_character(
    character_id: str,
    spec: CharacterSpec,
    characters_dir: Path = DEFAULT_CHARACTERS_DIR,
) -> Path:
    characters_dir.mkdir(parents=True, exist_ok=True)
    path = characters_dir / f"{character_id}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(spec.model_dump(mode="json"), f, indent=2)
    return path


def delete_character(
    character_id: str, characters_dir: Path = DEFAULT_CHARACTERS_DIR
) -> None:
    path = characters_dir / f"{character_id}.json"
    if path.exists():
        path.unlink()
