from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter

from aose.models import (
    CharClass,
    Enchantment,
    Item,
    LanguageData,
    Race,
    Source,
    Spell,
    SpellList,
    WeaponQuality,
)

T = TypeVar("T", bound=BaseModel)


def _read_yaml_objects(directory: Path, exclude_names: set[str] | None = None) -> list[dict]:
    """Read every *.yaml in a directory, yielding each top-level object.
    A file may contain a single mapping or a list of mappings.
    Filenames in ``exclude_names`` are skipped."""
    objs: list[dict] = []
    if not directory.exists():
        return objs
    exclude = exclude_names or set()
    for path in sorted(directory.glob("*.yaml")):
        if path.name in exclude:
            continue
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
    for obj in _read_yaml_objects(directory, exclude_names={"weapon_qualities.yaml"}):
        parsed = adapter.validate_python(obj)
        result[parsed.id] = parsed
    return result


def _load_secondary_skills(data_dir: Path) -> list[str]:
    """Read ``secondary_skills.yaml`` as a flat list of skill names.

    Returns an empty list if the file is absent so the loader stays usable
    in test fixtures that pass minimal data dirs.
    """
    path = data_dir / "secondary_skills.yaml"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("secondary_skills.yaml must be a YAML list of strings")
    skills = [str(s).strip() for s in raw if str(s).strip()]
    # Preserve order but drop duplicates so re-roll distributions stay uniform.
    seen: set[str] = set()
    unique: list[str] = []
    for skill in skills:
        if skill not in seen:
            seen.add(skill)
            unique.append(skill)
    return unique


def _load_spell_lists(data_dir: Path) -> dict[str, SpellList]:
    """Read ``spell_lists.yaml`` (a list of mappings) into an id-keyed dict.

    Returns an empty dict when the file is absent so minimal test fixtures
    (a bare data dir) still load.
    """
    path = data_dir / "spell_lists.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("spell_lists.yaml must be a YAML list of mappings")
    result: dict[str, SpellList] = {}
    for obj in raw:
        parsed = SpellList.model_validate(obj)
        result[parsed.id] = parsed
    return result


def _load_languages(data_dir: Path) -> LanguageData:
    """Read ``languages.yaml`` (a mapping with ``alignment`` + ``additional``).

    Returns an empty ``LanguageData`` when the file is absent so minimal test
    fixtures (a bare data dir) still load.
    """
    path = data_dir / "languages.yaml"
    if not path.exists():
        return LanguageData()
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("languages.yaml must be a YAML mapping")
    return LanguageData.model_validate(raw)


def _load_sources(data_dir: Path) -> dict[str, Source]:
    """Read ``sources.yaml`` (a list of mappings) into an id-keyed dict.

    Returns an empty dict when the file is absent so minimal test fixtures
    (a bare data dir) still load.
    """
    path = data_dir / "sources.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("sources.yaml must be a YAML list of mappings")
    result: dict[str, Source] = {}
    for obj in raw:
        parsed = Source.model_validate(obj)
        result[parsed.id] = parsed
    return result


def _load_enchantments(data_dir: Path) -> dict[str, Enchantment]:
    """Read ``enchantments.yaml`` (a list of mappings) into an id-keyed dict.

    Returns an empty dict when the file is absent so minimal test fixtures
    (a bare data dir) still load.
    """
    path = data_dir / "enchantments.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("enchantments.yaml must be a YAML list of mappings")
    result: dict[str, Enchantment] = {}
    for obj in raw:
        parsed = Enchantment.model_validate(obj)
        result[parsed.id] = parsed
    return result


def _load_weapon_qualities(data_dir: Path) -> dict[str, WeaponQuality]:
    """Read ``equipment/weapon_qualities.yaml`` (a list of mappings) into an
    id-keyed dict.  Returns an empty dict when absent (minimal fixtures)."""
    path = data_dir / "equipment" / "weapon_qualities.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("weapon_qualities.yaml must be a YAML list of mappings")
    result: dict[str, WeaponQuality] = {}
    for obj in raw:
        parsed = WeaponQuality.model_validate(obj)
        result[parsed.id] = parsed
    return result


@dataclass
class GameData:
    races: dict[str, Race] = field(default_factory=dict)
    classes: dict[str, CharClass] = field(default_factory=dict)
    spells: dict[str, Spell] = field(default_factory=dict)
    spell_lists: dict[str, SpellList] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    qualities: dict[str, WeaponQuality] = field(default_factory=dict)
    secondary_skills: list[str] = field(default_factory=list)
    languages: LanguageData = field(default_factory=LanguageData)
    enchantments: dict[str, Enchantment] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: Path) -> "GameData":
        return cls(
            races=_load_models(data_dir / "races", Race),
            classes=_load_models(data_dir / "classes", CharClass),
            spells=_load_models(data_dir / "spells", Spell),
            spell_lists=_load_spell_lists(data_dir),
            items=_load_items(data_dir / "equipment"),
            qualities=_load_weapon_qualities(data_dir),
            secondary_skills=_load_secondary_skills(data_dir),
            languages=_load_languages(data_dir),
            enchantments=_load_enchantments(data_dir),
            sources=_load_sources(data_dir),
        )
