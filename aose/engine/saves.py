from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec, Modifier

from .ability_mods import ability_modifier
from .features import all_modifiers
from .magic import effective_abilities

SAVE_FLOOR = 2

_WIS_UNCONDITIONAL = ("save:spells", "save:wands")
_WIS_CONDITIONAL = ("save:death", "save:paralysis")   # magical-origin only


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


def _level_data(cls, level: int):
    if level in cls.progression:
        return cls.progression[level]
    available = [lv for lv in cls.progression.keys() if lv <= level]
    if not available:
        raise ValueError(f"No progression data for class {cls.id} at level {level}")
    return cls.progression[max(available)]


def saving_throws(spec: CharacterSpec, data: GameData) -> dict[str, int]:
    """Best (lowest) save in each category across all classes, then magic
    modifiers.  ``add`` improves (target -= value); ``set`` / bounds use literal
    save numbers.  Targets clamp at ``SAVE_FLOOR``."""
    best: dict[str, int] = {}
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ld = _level_data(cls, entry.level)
        for name, value in ld.saves.items():
            if name not in best or value < best[name]:
                best[name] = value

    # Saves recognise no V1 conditions; situational (conditioned) save mods are
    # excluded from the number until a derivation learns to evaluate them.
    mods = [m for m in all_modifiers(spec, data) if m.condition is None]
    for name in list(best):
        wanted = ("save:all", f"save:{name}")
        target = best[name]
        sets = [m.value for m in mods if m.op == "set" and m.target in wanted]
        if sets:
            target = sets[-1]
        target -= sum(m.value for m in mods if m.op == "add" and m.target in wanted)
        for m in mods:
            if m.target in wanted and m.op == "set_min":
                target = max(target, m.value)
            elif m.target in wanted and m.op == "set_max":
                target = min(target, m.value)
        best[name] = max(SAVE_FLOOR, target)
    return best
