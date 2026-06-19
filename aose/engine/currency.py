"""Multi-coin currency — location-aware value & weight helpers.

Coins live as ``CoinStack``s on ``CharacterSpec.coins`` (denom/count/location).
This module computes value (all locations, for the wealth readout) and weight
(carried-only, for encumbrance), plus the pure ``convert_amount`` core that the
movement engine's per-stack conversion calls. Imports only models.
"""
from __future__ import annotations

from aose.models import CharacterSpec, CoinStack

DENOMINATIONS = ("pp", "gp", "ep", "sp", "cp")
RATES = {"pp": 500, "gp": 100, "ep": 50, "sp": 10, "cp": 1}   # cp-equivalents


class CurrencyError(ValueError):
    """Currency validation / conversion errors (routes map to HTTP 400)."""


def carried_coins(spec: CharacterSpec) -> list[CoinStack]:
    """Coin stacks on the person (Carried bucket) — the only shop-spendable
    coins. Excludes stashed, on-carrier, and coins packed in containers."""
    return [s for s in spec.coins if s.location.kind == "carried"]


def total_value_cp(spec: CharacterSpec) -> int:
    """cp-worth of every coin the character holds, all locations."""
    return sum(s.count * RATES[s.denom] for s in spec.coins)


def total_value_gp(spec: CharacterSpec) -> int:
    """Whole-gp worth of the purse (floors any sub-gp remainder)."""
    return total_value_cp(spec) // RATES["gp"]


def coin_count(spec: CharacterSpec, carried_only: bool = False) -> int:
    """Number of coins (1 cn each). ``carried_only`` gives the encumbrance
    weight (Carried bucket only); else every coin."""
    stacks = carried_coins(spec) if carried_only else spec.coins
    return sum(s.count for s in stacks)


def convert_amount(frm: str, to: str, count: int) -> int:
    """Pure: how many ``to`` coins ``count`` ``frm`` coins convert to, at
    official rates. Raises ``CurrencyError`` on unknown/identical denom,
    non-positive count, or a non-whole-coin result."""
    if frm not in RATES or to not in RATES:
        raise CurrencyError(f"unknown denomination: {frm!r} / {to!r}")
    if frm == to:
        raise CurrencyError("cannot convert a coin to itself")
    if count <= 0:
        raise CurrencyError("convert count must be positive")
    value_cp = count * RATES[frm]
    if value_cp % RATES[to] != 0:
        raise CurrencyError(f"{count}{frm} does not convert to a whole number of {to}")
    return value_cp // RATES[to]
