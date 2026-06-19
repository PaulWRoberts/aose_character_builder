"""Gems & jewellery — the cycle-free core for owned treasure valuables.

Gems stack by (value, label); jewellery pieces are individual with a damaged
toggle.  All weightless and free to acquire (Add-only).  Mutators return new
lists (no in-place mutation) and raise ``ValuableError`` on bad input; routes
map it to HTTP 400.  Imports only models + the dice engine; nothing imports it
back.
"""
from __future__ import annotations

import random
import uuid
from typing import Optional

from aose.engine.dice import roll
from aose.models import CharacterSpec, GemStack, JewelleryPiece
from aose.models.storage import StorageLocation

# Table increments — a dropdown affordance only; custom values are also valid.
GEM_INCREMENTS = (10, 50, 100, 500, 1000)


class ValuableError(ValueError):
    """All gem/jewellery validation / mutation errors (routes map to HTTP 400)."""


# ---------------------------------------------------------------------------
# Gem helpers
# ---------------------------------------------------------------------------

def _gem_index(gems: list[GemStack], instance_id: str) -> int:
    for i, g in enumerate(gems):
        if g.instance_id == instance_id:
            return i
    raise ValuableError(f"No gem stack with id {instance_id!r}")


def add_gem(gems: list[GemStack], value: int, count: int = 1,
            label: str = "",
            location: StorageLocation | None = None) -> list[GemStack]:
    """Add ``count`` gems worth ``value`` each.  Stacks onto an existing entry
    with the same (value, label, location); otherwise appends a new stack."""
    if value <= 0:
        raise ValuableError("a gem must be worth more than 0 gp")
    if count <= 0:
        raise ValuableError("gem count must be positive")
    label = label.strip()
    location = location or StorageLocation(kind="carried")
    for i, g in enumerate(gems):
        if g.value == value and g.label == label and g.location == location:
            updated = g.model_copy(update={"count": g.count + count})
            return [*gems[:i], updated, *gems[i + 1:]]
    return [*gems, GemStack(instance_id=uuid.uuid4().hex, value=value,
                            count=count, label=label, location=location)]


def adjust_gem_count(gems: list[GemStack], instance_id: str,
                     delta: int) -> list[GemStack]:
    """Add ``delta`` (may be negative) to a stack's count, clamped at 0.  A
    stack reaching 0 is removed."""
    idx = _gem_index(gems, instance_id)
    g = gems[idx]
    new_count = max(0, g.count + delta)
    if new_count == 0:
        return [*gems[:idx], *gems[idx + 1:]]
    updated = g.model_copy(update={"count": new_count})
    return [*gems[:idx], updated, *gems[idx + 1:]]


def remove_gem(gems: list[GemStack], instance_id: str) -> list[GemStack]:
    """Drop the whole stack (no gold)."""
    idx = _gem_index(gems, instance_id)
    return [*gems[:idx], *gems[idx + 1:]]


def sell_gem(gems: list[GemStack], gold: int,
             instance_id: str) -> tuple[list[GemStack], int]:
    """Sell one gem from the stack: -1 count, +value gold.  Empties → removed."""
    idx = _gem_index(gems, instance_id)
    g = gems[idx]
    new_gems = adjust_gem_count(gems, instance_id, -1)
    return new_gems, gold + g.value


def sell_gem_all(gems: list[GemStack], gold: int,
                 instance_id: str) -> tuple[list[GemStack], int]:
    """Sell the whole stack at once: +value*count gold, row removed."""
    idx = _gem_index(gems, instance_id)
    g = gems[idx]
    return [*gems[:idx], *gems[idx + 1:]], gold + g.value * g.count


def gem_stack_value(stack: GemStack) -> int:
    return stack.value * stack.count


# ---------------------------------------------------------------------------
# Jewellery helpers
# ---------------------------------------------------------------------------

def _jewellery_index(jewellery: list[JewelleryPiece], instance_id: str) -> int:
    for i, j in enumerate(jewellery):
        if j.instance_id == instance_id:
            return i
    raise ValuableError(f"No jewellery piece with id {instance_id!r}")


def roll_jewellery_value(rng: Optional[random.Random] = None) -> int:
    """3d6 × 100 gp — the Advanced Fantasy jewellery value (300–1800 gp)."""
    return roll("3d6", rng) * 100


def add_jewellery(jewellery: list[JewelleryPiece], value: int,
                  damaged: bool = False, label: str = "",
                  location: StorageLocation | None = None) -> list[JewelleryPiece]:
    """Append a jewellery piece (Add-only).  ``value`` is the full, un-halved
    worth even when ``damaged`` is set."""
    if value <= 0:
        raise ValuableError("a jewellery piece must be worth more than 0 gp")
    location = location or StorageLocation(kind="carried")
    return [*jewellery, JewelleryPiece(
        instance_id=uuid.uuid4().hex, value=value,
        damaged=damaged, label=label.strip(), location=location,
    )]


def set_jewellery_damaged(jewellery: list[JewelleryPiece], instance_id: str,
                          damaged: bool) -> list[JewelleryPiece]:
    """Toggle the damaged flag (reversible)."""
    idx = _jewellery_index(jewellery, instance_id)
    updated = jewellery[idx].model_copy(update={"damaged": damaged})
    return [*jewellery[:idx], updated, *jewellery[idx + 1:]]


def remove_jewellery(jewellery: list[JewelleryPiece],
                     instance_id: str) -> list[JewelleryPiece]:
    """Drop the piece (no gold)."""
    idx = _jewellery_index(jewellery, instance_id)
    return [*jewellery[:idx], *jewellery[idx + 1:]]


def sell_jewellery(jewellery: list[JewelleryPiece], gold: int,
                   instance_id: str) -> tuple[list[JewelleryPiece], int]:
    """Sell the piece: +effective value gold (halved if damaged), piece removed."""
    idx = _jewellery_index(jewellery, instance_id)
    value = jewellery_value(jewellery[idx])
    return [*jewellery[:idx], *jewellery[idx + 1:]], gold + value


def jewellery_value(piece: JewelleryPiece) -> int:
    """Effective gp worth — full, or floored half when damaged."""
    return piece.value // 2 if piece.damaged else piece.value


def total_value(spec: CharacterSpec) -> int:
    """Sum of all gem-stack values + all jewellery effective values."""
    return (
        sum(gem_stack_value(g) for g in spec.gems)
        + sum(jewellery_value(j) for j in spec.jewellery)
    )


def total_wealth_gp(spec: CharacterSpec) -> int:
    """Whole-gp wealth across all PC buckets (coins + gems + jewellery),
    excluding retainers (they own their own purse)."""
    from aose.engine import currency
    return currency.total_value_gp(spec) + total_value(spec)


def valuables_weight_cn(spec: CharacterSpec) -> int:
    """Encumbrance weight of CARRIED gems + jewellery: 1 cn per gem,
    10 cn per piece. Stashed / on-carrier treasure weighs nothing for the PC."""
    gems = sum(g.count for g in spec.gems if g.location.kind == "carried")
    jewel = 10 * sum(1 for j in spec.jewellery if j.location.kind == "carried")
    return gems + jewel
