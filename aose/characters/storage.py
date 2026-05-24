import json
from pathlib import Path

from aose.models import CharacterSpec

DEFAULT_CHARACTERS_DIR = Path("characters")


def list_character_ids(characters_dir: Path = DEFAULT_CHARACTERS_DIR) -> list[str]:
    if not characters_dir.exists():
        return []
    return sorted(p.stem for p in characters_dir.glob("*.json"))


def load_character(
    character_id: str, characters_dir: Path = DEFAULT_CHARACTERS_DIR
) -> CharacterSpec:
    path = characters_dir / f"{character_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No character at {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
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
