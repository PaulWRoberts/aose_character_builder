from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec, Modifier

from .ability_mods import ability_modifier
from .features import all_modifiers
from .magic import effective_abilities

SAVE_FLOOR = 2

_WIS_UNCONDITIONAL = ("save:spells", "save:wands")
_WIS_CONDITIONAL = ("save:death", "save:paralysis")   # magical-origin only

_CONDITION_NOTES = {
    "magical": "magical effects only",
    "poison": "poison only (not death magic)",
    "paralysis": "paralysis only (not petrification)",
}

_VS_DISPLAY = {
    "illusion": "illusions",
}
"""Display name for a ``save:vs:<thing>`` suffix. Unregistered things fall back
to ``thing.replace("_", " ")``."""


def _vs_display(thing: str) -> str:
    return _VS_DISPLAY.get(thing, thing.replace("_", " "))


def wisdom_save_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """WIS modifier vs magical effects. Unconditional on spells/wands (always
    magical); conditional (``magical``) on death/paralysis; never breath. Empty
    when the WIS modifier is 0."""
    wis = ability_modifier(effective_abilities(spec, data)[Ability.WIS])
    if wis == 0:
        return []
    mods = [Modifier(target=t, op="add", value=wis, source="Wisdom") for t in _WIS_UNCONDITIONAL]
    mods += [
        Modifier(target=t, op="add", value=wis, condition="magical", source="Wisdom")
        for t in _WIS_CONDITIONAL
    ]
    return mods


class SaveModLine(BaseModel):
    source: str          # feature/item name, or "Wisdom"
    bonus: int           # +N = bonus (better), -N = penalty (worse)
    conditional: bool    # True when the modifier carries a condition
    note: str            # condition note ("" when unconditional)


class SaveBreakdown(BaseModel):
    category: str        # death / wands / paralysis / breath / spells
    base: int            # class progression best (no modifiers)
    modified: int        # headline (unconditional modifiers, floored)
    lines: list[SaveModLine]


class SituationalSaveBonus(BaseModel):
    """A broad cross-cutting save bonus that applies whenever a particular kind
    of effect (``things``) forces a save, regardless of category. Sourced from a
    ``save:vs:<thing>`` modifier on a race/class feature or magic item."""
    source: str          # feature/item name, or "—"
    bonus: int
    things: list[str]    # display names, sorted


def _level_data(cls, level: int):
    if level in cls.progression:
        return cls.progression[level]
    available = [lv for lv in cls.progression.keys() if lv <= level]
    if not available:
        raise ValueError(f"No progression data for class {cls.id} at level {level}")
    return cls.progression[max(available)]


def _base_saves(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    best: dict[str, int] = {}
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        for name, value in ld.saves.items():
            if name not in best or value < best[name]:
                best[name] = value
    return best


def _all_save_mods(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    return all_modifiers(spec, data) + wisdom_save_modifiers(spec, data)


def saving_throws_detail(spec: CharacterSpec, data: GameData) -> dict[str, SaveBreakdown]:
    """Per-category base, headline (unconditional mods only), and every
    contributing add-modifier as a line (conditional ones flagged, excluded from
    the headline)."""
    base = _base_saves(spec, data)
    mods = _all_save_mods(spec, data)
    out: dict[str, SaveBreakdown] = {}
    for name, base_val in base.items():
        wanted = ("save:all", f"save:{name}")
        relevant = [m for m in mods if m.target in wanted]
        uncond = [m for m in relevant if m.condition is None]

        target = base_val
        sets = [m.value for m in uncond if m.op == "set"]
        if sets:
            target = sets[-1]
        target -= sum(m.value for m in uncond if m.op == "add")
        for m in uncond:
            if m.op == "set_min":
                target = max(target, m.value)
            elif m.op == "set_max":
                target = min(target, m.value)
        modified = max(SAVE_FLOOR, target)

        lines = [
            SaveModLine(
                source=m.source or "—",
                bonus=m.value,
                conditional=m.condition is not None,
                note=_CONDITION_NOTES.get(m.condition, "") if m.condition else "",
            )
            for m in relevant if m.op == "add"
        ]
        out[name] = SaveBreakdown(category=name, base=base_val, modified=modified, lines=lines)
    return out


def situational_save_bonuses(spec: CharacterSpec, data: GameData) -> list[SituationalSaveBonus]:
    """Cross-cutting ``save:vs:<thing>`` bonuses from features and magic items,
    grouped by ``(source, value)`` with their things collected. Never folded
    into any per-category headline."""
    groups: dict[tuple[str, int], list[str]] = {}
    for m in all_modifiers(spec, data):
        if m.op != "add" or not m.target.startswith("save:vs:"):
            continue
        thing = _vs_display(m.target.split("save:vs:", 1)[1])
        key = (m.source or "—", m.value)
        bucket = groups.setdefault(key, [])
        if thing not in bucket:
            bucket.append(thing)
    out = [
        SituationalSaveBonus(source=src, bonus=val, things=sorted(things))
        for (src, val), things in groups.items()
    ]
    out.sort(key=lambda b: (b.source, -b.bonus))
    return out


def saving_throws(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    """Headline (modified) save number per category — thin view over
    ``saving_throws_detail``."""
    return {name: bd.modified for name, bd in saving_throws_detail(spec, data).items()}
