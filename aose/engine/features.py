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


def selected_options(owner, selections: dict[str, list[str]]):
    """Yield the chosen ``ChoiceOption``s for a race/class given the character's
    selection map (group id -> chosen option ids). Unknown ids are skipped."""
    for group in getattr(owner, "feature_choices", []):
        chosen = selections.get(group.id, [])
        by_id = {o.id: o for o in group.options}
        for oid in chosen:
            if oid in by_id:
                yield by_id[oid]


def iter_reached(spec: CharacterSpec, data: GameData):
    """Yield ``(feature_or_option, level_or_None, source_label)`` for everything
    that applies: reached class features + chosen class options (with the class's
    level), and — unless race-as-class — race features + chosen race options
    (level None). The single source of truth for "what applies"; every
    feature-derived collector iterates this so they all agree."""
    sel = spec.feature_choices
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level <= entry.level:
                yield feat, entry.level, cls.name
        for opt in selected_options(cls, sel):
            yield opt, entry.level, cls.name
    if not is_race_as_class(spec, data):
        race = data.races.get(spec.race_id)
        if race is not None:
            for feat in race.features:
                yield feat, None, race.name
            for opt in selected_options(race, sel):
                yield opt, None, race.name


def _reached_features(spec: CharacterSpec, data: GameData):
    """Back-compat ``(feature, source_label)`` view over ``iter_reached`` for
    collectors that don't need the level (open-doors, 1h-2h)."""
    for feat, _level, src in iter_reached(spec, data):
        yield feat, src


def feature_weapons(spec: CharacterSpec, data: GameData) -> list[tuple[str, dict]]:
    """Synthetic always-available weapons declared by reached features/options via
    ``mechanical['weapon']`` (gargantua rock, mutoid claws, mycelian fist).
    A descriptor with ``damage_per_level_die`` (mycelian fist) resolves to
    ``"{level}{die}"`` against the granting class's level."""
    out: list[tuple[str, dict]] = []
    for feat, level, _src in iter_reached(spec, data):
        if not feat.mechanical:
            continue
        descriptor = feat.mechanical.get("weapon")
        if not descriptor:
            continue
        descriptor = dict(descriptor)
        die = descriptor.pop("damage_per_level_die", None)
        if die is not None and level is not None:
            descriptor["damage"] = f"{level}{die}"
        out.append((feat.id, descriptor))
    return out


def open_doors_category_bonus(spec: CharacterSpec, data: GameData) -> tuple[int, str]:
    """Total STR-category bump for Open Doors from reached features'
    ``mechanical['str_category_bonus']``, paired with the granting race/class
    name for display. Returns ``(0, "")`` when no feature grants one."""
    total = 0
    source = ""
    for feat, src in _reached_features(spec, data):
        if feat.mechanical:
            bonus = feat.mechanical.get("str_category_bonus")
            if bonus:
                total += bonus
                if not source:
                    source = src
    return total, source


def one_handed_two_handed_weapons(spec: CharacterSpec, data: GameData) -> bool:
    """True when a reached feature grants wielding two-handed *melee* weapons in
    one hand (gargantua). Reads ``mechanical['one_handed_two_handed_melee']``."""
    for feat, _src in _reached_features(spec, data):
        if feat.mechanical and feat.mechanical.get("one_handed_two_handed_melee"):
            return True
    return False


def feature_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Concrete ``Modifier``s from every reached class/race feature and chosen
    option. Level-scaling resolves against the granting class's level (None on a
    race feature/option). For a race-as-class character the linked race
    contributes nothing — handled inside ``iter_reached``."""
    eff = effective_abilities(spec, data)
    out: list[Modifier] = []
    for feat, level, _src in iter_reached(spec, data):
        for g in feat.granted_modifiers:
            out.append(Modifier(
                target=g.target, op=g.op,
                value=resolve_value(g, level=level, eff=eff),
                condition=g.condition, source=feat.name,
            ))
    return out


def all_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """The single modifier list every derivation consumes: equipped magic items
    plus class/race feature grants."""
    return active_modifiers(spec, data) + feature_modifiers(spec, data)
