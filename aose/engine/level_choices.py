"""Unspent-capacity model: how many selections a character has *earned* by their
current level vs. *spent*. Subsystem-agnostic — each provider (weapon
proficiencies, combat talents) reports its own capacity, and any with
``remaining > 0`` contributes a picker to the level-up/sheet UI.

Cycle-free: imports models, the loader, and ``proficiency`` only.
"""
from __future__ import annotations

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine.proficiency import slots_spent, total_proficiency_slots
from aose.models import CharacterSpec


class Capacity(BaseModel):
    kind: str                 # "proficiency" | "talent"
    group_id: str | None      # FeatureChoice id for talents; None for proficiencies
    label: str
    earned: int
    spent: int

    @property
    def remaining(self) -> int:
        return max(0, self.earned - self.spent)


def proficiency_capacity(spec: CharacterSpec, data: GameData) -> Capacity | None:
    """Weapon-proficiency slots earned vs spent. ``None`` when the rule is off."""
    if not spec.ruleset.weapon_proficiency:
        return None
    pairs = [(data.classes[e.class_id], e.level) for e in spec.classes
             if e.class_id in data.classes]
    return Capacity(
        kind="proficiency", group_id=None, label="Weapon Proficiency",
        earned=total_proficiency_slots(pairs), spent=slots_spent(spec),
    )


def talent_capacities(spec: CharacterSpec, data: GameData) -> list[Capacity]:
    """One Capacity per applicable level-banded choice group whose ``requires_rule``
    is satisfied (combat talents today). ``earned`` bands by the granting class's
    level; ``spent`` is how many options are already chosen."""
    from aose.engine.feature_choices import effective_pick
    out: list[Capacity] = []
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for g in cls.feature_choices:
            if g.pick_by_level is None:
                continue
            if g.requires_rule and not getattr(spec.ruleset, g.requires_rule, False):
                continue
            out.append(Capacity(
                kind="talent", group_id=g.id, label=g.name,
                earned=effective_pick(g, entry.level),
                spent=len(spec.feature_choices.get(g.id, [])),
            ))
    return out


def all_capacities(spec: CharacterSpec, data: GameData) -> list[Capacity]:
    """Every provider's capacity with ``remaining > 0``."""
    out: list[Capacity] = []
    prof = proficiency_capacity(spec, data)
    if prof is not None and prof.remaining > 0:
        out.append(prof)
    out += [c for c in talent_capacities(spec, data) if c.remaining > 0]
    return out
