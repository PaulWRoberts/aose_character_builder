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
from aose.engine import ability_mods
from aose.models import Ability, CharacterSpec, Retainer


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
