"""Innate daily-use abilities (CC3): breath weapons, fungal spores, and chosen
spell-granting options (Fiendish Gifts). The non-caster analogue of the mental-
power pool — a per-ability daily counter reset on rest.

Cycle-free: imports models, loader, and ``iter_reached`` from features (which
imports only models/loader/magic). Never imported by features.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from aose.data.loader import GameData
from aose.models import CharacterSpec
from aose.engine.features import iter_reached


class InnateError(Exception):
    """Raised on an invalid innate-use operation (unknown id, over/under flow)."""


@dataclass
class InnateAbility:
    id: str
    name: str
    text: str
    source: str
    spell_id: str | None
    max_uses: int
    used: int
    remaining: int


def _max_uses(daily_uses, level: int | None) -> int:
    if daily_uses.scales_with_level:
        return max(1, level or 1)
    return daily_uses.per_day


def innate_abilities(spec: CharacterSpec, data: GameData) -> list[InnateAbility]:
    """Every reached feature/option carrying ``daily_uses``, with resolved max
    uses and the character's spent count. Ordered by appearance in iter_reached."""
    out: list[InnateAbility] = []
    for feat, level, src in iter_reached(spec, data):
        du = getattr(feat, "daily_uses", None)
        if du is None:
            continue
        mx = _max_uses(du, level)
        used = min(spec.innate_uses.get(feat.id, 0), mx)
        out.append(InnateAbility(
            id=feat.id, name=feat.name, text=feat.text, source=src,
            spell_id=getattr(feat, "spell_id", None),
            max_uses=mx, used=used, remaining=max(0, mx - used),
        ))
    return out


def _ability_max(spec: CharacterSpec, data: GameData, ability_id: str) -> int:
    for ab in innate_abilities(spec, data):
        if ab.id == ability_id:
            return ab.max_uses
    raise InnateError(f"No innate ability {ability_id!r}")


def spend_innate(spec: CharacterSpec, ability_id: str,
                 data: GameData | None = None) -> CharacterSpec:
    """Increment one use; raise if already at max. ``data`` is required to know
    the max — callers on the live sheet pass the loaded GameData."""
    if data is None:
        raise InnateError("spend_innate requires GameData to resolve the max")
    mx = _ability_max(spec, data, ability_id)
    used = spec.innate_uses.get(ability_id, 0)
    if used >= mx:
        raise InnateError(f"{ability_id!r} has no uses remaining")
    new = dict(spec.innate_uses)
    new[ability_id] = used + 1
    return spec.model_copy(update={"innate_uses": new})


def restore_innate(spec: CharacterSpec, ability_id: str) -> CharacterSpec:
    """Decrement one use (floor 0); drops the key at 0."""
    used = spec.innate_uses.get(ability_id, 0)
    new = dict(spec.innate_uses)
    if used <= 1:
        new.pop(ability_id, None)
    else:
        new[ability_id] = used - 1
    return spec.model_copy(update={"innate_uses": new})


def reset_innate(spec: CharacterSpec) -> CharacterSpec:
    """Clear all innate use counters (a new day)."""
    return spec.model_copy(update={"innate_uses": {}})
