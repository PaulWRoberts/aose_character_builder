from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter

from aose.models import (
    CharClass,
    Item,
    Race,
    Spell,
)

T = TypeVar("T", bound=BaseModel)


def _read_yaml_objects(directory: Path) -> list[dict]:
    """Read every *.yaml in a directory, yielding each top-level object.
    A file may contain a single mapping or a list of mappings."""
    objs: list[dict] = []
    if not directory.exists():
        return objs
    for path in sorted(directory.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            continue
        if isinstance(raw, list):
            objs.extend(raw)
        else:
            objs.append(raw)
    return objs


def _load_models(directory: Path, model: type[T]) -> dict[str, T]:
    result: dict[str, T] = {}
    for obj in _read_yaml_objects(directory):
        parsed = model.model_validate(obj)
        result[parsed.id] = parsed
    return result


def _load_items(directory: Path) -> dict[str, Item]:
    adapter = TypeAdapter(Item)
    result: dict[str, Item] = {}
    for obj in _read_yaml_objects(directory):
        parsed = adapter.validate_python(obj)
        result[parsed.id] = parsed
    return result


@dataclass
class GameData:
    races: dict[str, Race] = field(default_factory=dict)
    classes: dict[str, CharClass] = field(default_factory=dict)
    spells: dict[str, Spell] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: Path) -> "GameData":
        return cls(
            races=_load_models(data_dir / "races", Race),
            classes=_load_models(data_dir / "classes", CharClass),
            spells=_load_models(data_dir / "spells", Spell),
            items=_load_items(data_dir / "equipment"),
        )
