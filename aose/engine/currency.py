"""Multi-coin currency — the cycle-free core for the character's purse.

Five denominations (pp/gp/ep/sp/cp). ``gold`` (gp) stays the shop-spendable
balance; the others are held coins contributing value + weight (1 cn each).
Values are computed in a copper base to avoid floats. ``convert`` makes change
at the official AOSE rates and refuses non-whole-coin results. Pure functions:
``convert`` returns the changed field values; the caller applies them. Imports
only models; nothing imports it back.
"""
from __future__ import annotations

from aose.models import CharacterSpec

DENOMINATIONS = ("pp", "gp", "ep", "sp", "cp")
RATES = {"pp": 500, "gp": 100, "ep": 50, "sp": 10, "cp": 1}   # cp-equivalents
_ATTR = {"pp": "platinum", "gp": "gold", "ep": "electrum",
         "sp": "silver", "cp": "copper"}


class CurrencyError(ValueError):
    """Currency validation / conversion errors (routes map to HTTP 400)."""


def total_value_cp(spec: CharacterSpec) -> int:
    return sum(getattr(spec, _ATTR[d]) * RATES[d] for d in DENOMINATIONS)


def total_value_gp(spec: CharacterSpec) -> int:
    """Whole-gp worth of the purse (floors any sub-gp remainder)."""
    return total_value_cp(spec) // RATES["gp"]


def coin_count(spec: CharacterSpec) -> int:
    """Total number of coins — the encumbrance weight (1 cn per coin)."""
    return sum(getattr(spec, _ATTR[d]) for d in DENOMINATIONS)


def convert(spec: CharacterSpec, frm: str, to: str, count: int) -> dict[str, int]:
    """Convert ``count`` coins of ``frm`` into ``to`` at official rates.

    Returns ``{attr_name: new_count}`` for the two affected denominations.
    Raises ``CurrencyError`` on unknown/identical denom, non-positive count,
    insufficient source coins, or a result that isn't a whole number of ``to``.
    """
    if frm not in RATES or to not in RATES:
        raise CurrencyError(f"unknown denomination: {frm!r} / {to!r}")
    if frm == to:
        raise CurrencyError("cannot convert a coin to itself")
    if count <= 0:
        raise CurrencyError("convert count must be positive")
    have = getattr(spec, _ATTR[frm])
    if have < count:
        raise CurrencyError(f"only {have} {frm} available, need {count}")
    value_cp = count * RATES[frm]
    if value_cp % RATES[to] != 0:
        raise CurrencyError(
            f"{count}{frm} does not convert to a whole number of {to}")
    gained = value_cp // RATES[to]
    return {
        _ATTR[frm]: have - count,
        _ATTR[to]: getattr(spec, _ATTR[to]) + gained,
    }
