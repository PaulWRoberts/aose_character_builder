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
    SecondarySkillEntry,
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


def _load_secondary_skills(data_dir: Path) -> list[SecondarySkillEntry]:
    """Read ``secondary_skills.yaml`` as a weighted table of skill entries.

    Each item is a mapping ``{name, weight, [roll_twice]}``.  Returns an empty
    list if the file is absent (keeps minimal test data dirs usable).  When
    present, weights must sum to 100 and exactly one entry must be ``roll_twice``.
    """
    path = data_dir / "secondary_skills.yaml"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("secondary_skills.yaml must be a YAML list of mappings")
    entries: list[SecondarySkillEntry] = []
    seen: set[str] = set()
    for obj in raw:
        if not isinstance(obj, dict):
            raise ValueError(
                "secondary_skills.yaml entries must be mappings with name/weight"
            )
        entry = SecondarySkillEntry.model_validate(obj)
        if entry.name in seen:
            continue
        seen.add(entry.name)
        entries.append(entry)
    if not entries:
        return []
    total = sum(e.weight for e in entries)
    if total != 100:
        raise ValueError(
            f"secondary_skills.yaml weights must sum to 100 (got {total})"
        )
    roll_twice_count = sum(1 for e in entries if e.roll_twice)
    if roll_twice_count != 1:
        raise ValueError(
            "secondary_skills.yaml must have exactly one roll_twice entry "
            f"(got {roll_twice_count})"
        )
    return entries


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


def _load_table(data_dir: Path, filename: str) -> dict:
    """Read a flat mapping table (band -> values). Empty dict if absent."""
    path = data_dir / filename
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{filename} must be a YAML mapping")
    return raw


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


def _validate_weapon_qualities(
    items: dict, qualities: dict
) -> None:
    """Every weapon's quality refs must name a known quality and carry the
    param shape that quality's registry entry declares (``ranges`` = three
    ints; ``damage`` = a non-empty string; ``none`` = no param)."""
    from aose.models import Weapon

    for item in items.values():
        if not isinstance(item, Weapon):
            continue
        for ref in item.qualities:
            q = qualities.get(ref.id)
            if q is None:
                raise ValueError(
                    f"weapon {item.id!r} references unknown quality {ref.id!r}")
            if q.param == "ranges":
                ok = (isinstance(ref.param, (list, tuple))
                      and len(ref.param) == 3
                      and all(isinstance(n, int) for n in ref.param))
                if not ok:
                    raise ValueError(
                        f"weapon {item.id!r} quality {ref.id!r} needs three "
                        f"integer ranges, got {ref.param!r}")
            elif q.param == "damage":
                if not (isinstance(ref.param, str) and ref.param):
                    raise ValueError(
                        f"weapon {item.id!r} quality {ref.id!r} needs a damage "
                        f"string, got {ref.param!r}")
            else:  # "none"
                if ref.param is not None:
                    raise ValueError(
                        f"weapon {item.id!r} quality {ref.id!r} takes no "
                        f"parameter, got {ref.param!r}")


@dataclass
class GameData:
    races: dict[str, Race] = field(default_factory=dict)
    classes: dict[str, CharClass] = field(default_factory=dict)
    spells: dict[str, Spell] = field(default_factory=dict)
    spell_lists: dict[str, SpellList] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    qualities: dict[str, WeaponQuality] = field(default_factory=dict)
    secondary_skills: list[SecondarySkillEntry] = field(default_factory=list)
    languages: LanguageData = field(default_factory=LanguageData)
    enchantments: dict[str, Enchantment] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    monster_attack_matrix: dict = field(default_factory=dict)
    monster_saves: dict = field(default_factory=dict)
    quick_equipment: dict = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: Path) -> "GameData":
        items = _load_items(data_dir / "equipment")
        qualities = _load_weapon_qualities(data_dir)
        _validate_weapon_qualities(items, qualities)
        return cls(
            races=_load_models(data_dir / "races", Race),
            classes=_load_models(data_dir / "classes", CharClass),
            spells=_load_models(data_dir / "spells", Spell),
            spell_lists=_load_spell_lists(data_dir),
            items=items,
            qualities=qualities,
            secondary_skills=_load_secondary_skills(data_dir),
            languages=_load_languages(data_dir),
            enchantments=_load_enchantments(data_dir),
            sources=_load_sources(data_dir),
            monster_attack_matrix=_load_table(data_dir, "monster_attack_matrix.yaml"),
            monster_saves=_load_table(data_dir, "monster_saves.yaml"),
            quick_equipment=_load_table(data_dir, "quick_equipment.yaml"),
        )
