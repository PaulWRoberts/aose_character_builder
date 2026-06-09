"""Feature-granted modifiers — resolves class/race feature grants into the same
``Modifier`` objects magic items emit.

Cycle-free: imports only models, the data loader, and ``magic`` (for
``active_modifiers`` + ``effective_abilities``).  The derivation modules
(``armor_class``, ``saves``, ``attacks``) import ``all_modifiers`` *from here*;
this module never imports them.
"""
from __future__ import annotations

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec, Modifier
from aose.engine.magic import active_modifiers, effective_abilities


def _band_lookup(table: dict[int, int], key: int) -> int:
    """Value for the greatest table key ≤ ``key``; 0 below the lowest band."""
    candidates = [k for k in table if k <= key]
    return table[max(candidates)] if candidates else 0


def resolve_value(g, *, level: int | None, eff: dict) -> int:
    """Concrete value for a ``GrantedModifier`` given the granting class's
    ``level`` (None on a race feature) and effective ability scores ``eff``."""
    if g.scale is None:
        return g.value
    by = g.scale.by
    if by == "level":
        if level is None:
            raise ValueError("level scaling is not valid on a race feature")
        return _band_lookup(g.scale.table, level)
    if by.startswith("ability:"):
        ability = Ability(by.split(":", 1)[1])
        return _band_lookup(g.scale.table, eff[ability])
    raise ValueError(f"Unknown scale.by {by!r}")


def is_race_as_class(spec: CharacterSpec, data: GameData) -> bool:
    """True when the character's single class is race-locked to their race —
    i.e. a "race-as-class" entry (Dwarf-as-class, Gargantua, …).

    The linked ``Race`` and the race-locked ``CharClass`` share only a name:
    they are distinct stat blocks. A race-as-class character is defined wholly
    by its class, so the race's *features* and *feature-grants* must NOT apply
    (the class carries its own). Multi-class characters never qualify.
    """
    if len(spec.classes) != 1:
        return False
    cls = data.classes.get(spec.classes[0].class_id)
    return cls is not None and cls.race_locked == spec.race_id


def feature_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Concrete ``Modifier``s from every reached class feature (per the class's
    level) and every race feature.  Each carries the grant's ``condition`` and
    the feature's name as ``source``.

    For a race-as-class character the linked race contributes nothing — the
    class is self-contained (see ``is_race_as_class``)."""
    eff = effective_abilities(spec, data)
    out: list[Modifier] = []
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level > entry.level:
                continue
            for g in feat.granted_modifiers:
                out.append(Modifier(
                    target=g.target, op=g.op,
                    value=resolve_value(g, level=entry.level, eff=eff),
                    condition=g.condition, source=feat.name,
                ))
    race = None if is_race_as_class(spec, data) else data.races.get(spec.race_id)
    if race is not None:
        for feat in race.features:
            for g in feat.granted_modifiers:
                out.append(Modifier(
                    target=g.target, op=g.op,
                    value=resolve_value(g, level=None, eff=eff),
                    condition=g.condition, source=feat.name,
                ))
    return out


def all_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """The single modifier list every derivation consumes: equipped magic items
    plus class/race feature grants."""
    return active_modifiers(spec, data) + feature_modifiers(spec, data)
