"""Leveling-up engine: XP shares, per-class advancement state, and the
level-up mutation that bumps a class and rolls fresh hit points.

XP splitting follows the AOSE Advanced multi-class rule: total XP is divided
evenly between classes (integer division).  Level-up rules (max-HP-at-L1,
re-roll 1s & 2s at L1) intentionally do NOT apply at higher levels — those
toggles are L1-only by name.
"""
from __future__ import annotations

import random
from typing import Optional

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.dice import roll_hp
from aose.models import CharacterSpec, ClassEntry


def xp_share(spec: CharacterSpec) -> int:
    """XP each class effectively has.

    Single-class characters get the full ``spec.xp``.  Multi-class characters
    split it evenly via integer division; the remainder isn't lost forever —
    it shows up as soon as more XP is awarded and the share crosses the
    integer boundary.
    """
    n = len(spec.classes)
    return spec.xp if n == 1 else spec.xp // n


def _effective_max_level(spec: CharacterSpec, data: GameData, entry: ClassEntry) -> int:
    cls = data.classes[entry.class_id]
    eff = cls.max_level
    if spec.ruleset.demihuman_level_limits:
        race = data.races[spec.race_id]
        race_cap = race.class_level_caps.get(entry.class_id)
        if race_cap is not None:
            eff = min(eff, race_cap)
    return eff


class ClassAdvancement(BaseModel):
    class_id: str
    name: str
    current_level: int
    next_level: int | None
    next_threshold: int | None  # XP needed in the class's *share* scale
    current_xp: int             # the class's own XP share
    can_level: bool
    at_max: bool


def class_advancement(spec: CharacterSpec, data: GameData,
                      entry: ClassEntry) -> ClassAdvancement:
    cls = data.classes[entry.class_id]
    next_level = entry.level + 1
    eff_max = _effective_max_level(spec, data, entry)
    current = xp_share(spec)

    if next_level > eff_max or next_level not in cls.progression:
        return ClassAdvancement(
            class_id=entry.class_id,
            name=cls.name,
            current_level=entry.level,
            next_level=None,
            next_threshold=None,
            current_xp=current,
            can_level=False,
            at_max=True,
        )

    threshold = cls.progression[next_level].xp_required
    return ClassAdvancement(
        class_id=entry.class_id,
        name=cls.name,
        current_level=entry.level,
        next_level=next_level,
        next_threshold=threshold,
        current_xp=current,
        can_level=current >= threshold,
        at_max=False,
    )


def all_advancement(spec: CharacterSpec, data: GameData) -> list[ClassAdvancement]:
    """One advancement row per class entry on the spec, preserving order."""
    return [class_advancement(spec, data, e) for e in spec.classes]


def level_up(spec: CharacterSpec, data: GameData, class_id: str,
             rng: Optional[random.Random] = None) -> int:
    """Advance the named class by one level and roll its hit die.

    Mutates ``spec`` in place: increments ``entry.level`` and appends the new
    HP roll to ``entry.hp_rolls``.  Returns the new HP roll.  Raises
    ``ValueError`` if the class is at max level, missing from the spec, or
    short on XP.

    HP rules: standard ``roll_hp(hit_die)`` — Max-HP-at-L1 and Re-roll 1s/2s
    apply only at character creation, not at subsequent level-ups.
    """
    entry = next((e for e in spec.classes if e.class_id == class_id), None)
    if entry is None:
        raise ValueError(f"Character has no class {class_id!r}")

    advancement = class_advancement(spec, data, entry)
    if advancement.at_max:
        raise ValueError(f"{advancement.name} is already at maximum level")
    if not advancement.can_level:
        raise ValueError(
            f"Need {advancement.next_threshold} XP for {advancement.name} L"
            f"{advancement.next_level}, have {advancement.current_xp}"
        )

    cls = data.classes[class_id]
    new_hp = roll_hp(cls.hit_die, rng=rng)
    entry.level += 1
    entry.hp_rolls.append(new_hp)
    return new_hp
