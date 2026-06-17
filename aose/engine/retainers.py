"""Retainer generation, loyalty, hiring rules, XP, and PC<->retainer transfer.

A retainer is an embedded CharacterSpec, so this module orchestrates existing
engine helpers (quick_equipment, leveling, ability_mods, equip) rather than
re-implementing them. Cycle-free: models/loader + those engine modules.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from aose.data.loader import GameData
from aose.engine import ability_mods, quick_equipment
from aose.engine.ability_mods import apply_racial_modifiers
from aose.engine.dice import roll_hp
from aose.models import Ability, CharacterSpec, ClassEntry, Retainer


def _features_with(spec: CharacterSpec, data: GameData, key: str):
    """Yield mechanical dicts carrying ``key`` from the hiring PC's race features
    (all) and class features reached at the class's level. Read-only scan.

    Race-as-class: when the primary class is race-locked to the same race as
    spec.race_id, only class features are scanned (race entries are redundant
    and would double-count a modifier shared by both stat blocks)."""
    primary = data.classes.get(spec.classes[0].class_id) if spec.classes else None
    is_race_as_class = bool(primary and primary.race_locked == spec.race_id)

    if not is_race_as_class:
        race = data.races.get(spec.race_id)
        if race is not None:
            for f in race.features:
                if f.mechanical and key in f.mechanical:
                    yield f.mechanical[key]
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if not cls:
            continue
        for f in cls.features:
            if f.gained_at_level <= entry.level and f.mechanical and key in f.mechanical:
                yield f.mechanical[key]


_ABILITIES = ["STR", "INT", "WIS", "DEX", "CON", "CHA"]


def generate_retainer(*, name: str, class_ids: list[str], level: int,
                      race_id: str, alignment: str,
                      hiring_spec: CharacterSpec, data: GameData,
                      rng: Optional[random.Random] = None) -> Retainer:
    rng = rng or random.Random()
    primary = data.classes[class_ids[0]]

    # 1. baseline 10s
    abilities: dict[str, int] = {a: 10 for a in _ABILITIES}

    # 2. race-as-class vs split: a race-locked class is self-contained (no racial
    #    mods); a split race+class applies Advanced racial modifiers.
    race_locked = primary.race_locked is not None
    if race_locked:
        race_id = primary.race_locked
    elif hiring_spec.ruleset.separate_race_class and race_id in data.races:
        abilities = apply_racial_modifiers(abilities, data.races[race_id])

    # 3. bump each class's ability_requirements to its minimum (post-racial)
    for cid in class_ids:
        for ab, req in data.classes[cid].ability_requirements.items():
            k = ab.value
            if abilities.get(k, 0) < req:
                abilities[k] = req

    # 4. class entries: roll `level` hit dice (capped at name level); xp set to
    #    the level's threshold so XP is consistent with the level.
    entries: list[ClassEntry] = []
    for cid in class_ids:
        cls = data.classes[cid]
        n_rolls = min(level, cls.name_level)
        rolls = [roll_hp(cls.hit_die, rng) for _ in range(max(1, n_rolls))]
        xp = cls.progression[level].xp_required if level in cls.progression else 0
        entries.append(ClassEntry(class_id=cid, level=level, hp_rolls=rolls, xp=xp))

    spec = CharacterSpec(
        name=name, abilities=abilities, race_id=race_id, classes=entries,
        alignment=alignment, ruleset=hiring_spec.ruleset.model_copy(deep=True))

    # 5. quick-equipment kit
    kit = quick_equipment.roll_kit(class_ids[0], data, rng=rng)
    quick_equipment.apply_kit(spec, kit)

    # 6. loyalty
    loyalty = initial_loyalty(hiring_spec, race_id, data)

    return Retainer(id=uuid.uuid4().hex, spec=spec, loyalty=loyalty, role="")


def allowed_retainer_classes(hiring_spec: CharacterSpec, data: GameData):
    """Effective hiring allowance across the PC's classes (most permissive wins):
    returns "any", or a set of class ids (empty set == may not hire). A class
    with no retainer_hiring rules is unrestricted ("any")."""
    per_class = []
    for entry in hiring_spec.classes:
        cls = data.classes.get(entry.class_id)
        if not cls or not cls.retainer_hiring:
            return "any"                      # an unrestricted class permits all
        tier = None
        for rule in sorted(cls.retainer_hiring, key=lambda r: r.min_level):
            if entry.level >= rule.min_level:
                tier = rule
        if tier is None or tier.allows == "any":
            return "any"
        per_class.append(set() if tier.allows == "none" else set(tier.allows))
    union: set = set()
    for s in per_class:
        union |= s
    return union


def initial_loyalty(hiring_spec: CharacterSpec, retainer_race_id: str,
                    data: GameData) -> int:
    """Base loyalty from the hiring PC's CHA, adjusted by class/race
    retainer_loyalty_modifier features (human +1; half-orc -1 except for
    half-orc retainers)."""
    cha = hiring_spec.abilities.get(Ability.CHA, 9)
    total = ability_mods.base_loyalty(int(cha))
    for mod in _features_with(hiring_spec, data, "retainer_loyalty_modifier"):
        if mod.get("except_same_race") and retainer_race_id == hiring_spec.race_id:
            continue
        total += int(mod.get("value", 0))
    return total
