"""Leveling-up engine: per-class XP grants, per-class advancement state, and the
level-up mutation that bumps a class and rolls fresh hit points.

XP is tracked separately per class (``ClassEntry.xp``).  When XP is awarded, the
total is split evenly between the classes (integer division) and each class's
*prime-requisite XP adjustment* is applied to its share before it lands on that
class's count — faithful to the AOSE Advanced Multiple Classes rule.  This also
wires the prime-requisite adjustment in for single-class characters, which the
builder previously ignored.

Level-up rules (max-HP-at-L1, re-roll 1s & 2s at L1) intentionally do NOT apply
at higher levels — those toggles are L1-only by name.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.ability_mods import prime_requisite_xp_multiplier
from aose.engine.dice import roll_hp
from aose.models import CharacterSpec, ClassEntry


def _prime_req_multiplier(cls, abilities: dict) -> float:
    """The class's prime-requisite XP multiplier.

    Classes with a single prime requisite use that score.  For classes with
    multiple prime requisites we use the *lowest* of them (a conservative,
    uniform rule — the per-class multi-prime tables in the book vary, so this is
    a deliberate simplification).  No prime requisites → no adjustment.
    """
    if not cls.prime_requisites:
        return 1.0
    score = min(abilities[ab] for ab in cls.prime_requisites)
    return prime_requisite_xp_multiplier(score)


def grant_xp(spec: CharacterSpec, data: GameData, amount: int) -> None:
    """Award (or remove) XP, mutating ``spec`` in place.

    The amount is split evenly across the character's classes (integer
    division).  For awards (positive amount) each class's share is scaled by
    that class's prime-requisite multiplier before being added.  Removals
    (negative amount, a GM clawback) are split evenly without the multiplier.
    Each class's XP is clamped at zero — leveling down is not modelled.
    """
    n = len(spec.classes)
    share = amount // n
    for entry in spec.classes:
        if share >= 0:
            mult = _prime_req_multiplier(data.classes[entry.class_id], spec.abilities)
            delta = math.floor(share * mult + 1e-9)
        else:
            delta = share
        entry.xp = max(0, entry.xp + delta)


def _effective_max_level(spec: CharacterSpec, data: GameData, entry: ClassEntry) -> int:
    cls = data.classes[entry.class_id]
    eff = cls.max_level
    if not spec.ruleset.lift_demihuman_restrictions:
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
    next_threshold: int | None  # XP the class needs for its next level
    current_threshold: int      # XP floor of the current level (0 for L1)
    current_xp: int             # the class's own XP count
    can_level: bool
    at_max: bool


def class_advancement(spec: CharacterSpec, data: GameData,
                      entry: ClassEntry) -> ClassAdvancement:
    cls = data.classes[entry.class_id]
    next_level = entry.level + 1
    eff_max = _effective_max_level(spec, data, entry)
    current = entry.xp
    current_level_data = cls.progression.get(entry.level)
    current_threshold = current_level_data.xp_required if current_level_data else 0

    if next_level > eff_max or next_level not in cls.progression:
        return ClassAdvancement(
            class_id=entry.class_id,
            name=cls.name,
            current_level=entry.level,
            next_level=None,
            next_threshold=None,
            current_threshold=current_threshold,
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
        current_threshold=current_threshold,
        current_xp=current,
        can_level=current >= threshold,
        at_max=False,
    )


def all_advancement(spec: CharacterSpec, data: GameData) -> list[ClassAdvancement]:
    """One advancement row per class entry on the spec, preserving order."""
    return [class_advancement(spec, data, e) for e in spec.classes]


def cancel_pending_level_up(spec: CharacterSpec, class_id: str) -> None:
    """Idempotently clear any pending level-up HP roll for ``class_id``."""
    spec.pending_level_up.pop(class_id, None)


def level_up(spec: CharacterSpec, data: GameData, class_id: str,
             rng: Optional[random.Random] = None) -> int:
    """Advance the named class by one level and roll its hit die.

    Mutates ``spec`` in place: increments ``entry.level`` and appends the new
    HP roll to ``entry.hp_rolls``.  Returns the new HP roll.  Raises
    ``ValueError`` if the class is at max level, missing from the spec, or
    short on XP.

    HP rules: standard ``roll_hp(hit_die)`` until name level.  At or beyond
    ``cls.name_level`` no die is rolled and ``hp_rolls`` is left unchanged
    (returns 0); the flat post-name-level HP is applied by ``hp.py``.
    Max-HP-at-L1 and Re-roll 1s/2s apply only at character creation.
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
    # At or beyond name level the class no longer rolls Hit Dice; it gains a
    # flat `hp_after_name_level` per level instead (applied in hp.py, no CON).
    if entry.level >= cls.name_level:
        entry.level += 1
        return 0

    new_hp = roll_hp(cls.hit_die, rng=rng)
    entry.level += 1
    entry.hp_rolls.append(new_hp)
    return new_hp
