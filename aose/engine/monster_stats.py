"""Derive monster / normal-human combat stats from Hit Dice via table lookup.

Cycle-free: imports only the loader's GameData type. The single home for
"given HD, what are the THAC0 / attack bonus / saving throws". AC is stored
descending; ascending is the 19-minus convention used across the app.
"""
from __future__ import annotations

from pydantic import BaseModel

from aose.data.loader import GameData


class AttackStats(BaseModel):
    thac0: int
    attack_bonus: int


def ascending_ac(descending: int) -> int:
    """AOSE descending→ascending AC: AAC = 19 − descending (AC 9 → 10, 7 → 12)."""
    return 19 - descending


# Attack-matrix bands in ascending order, each as (lower_exclusive, key).
# A band covers HD strictly greater than `lower` up to the next band's lower.
_ATTACK_BANDS = [
    (1, "1+_to_2"), (2, "2+_to_3"), (3, "3+_to_4"), (4, "4+_to_5"),
    (5, "5+_to_6"), (6, "6+_to_7"), (7, "7+_to_9"), (9, "9+_to_11"),
    (11, "11+_to_13"), (13, "13+_to_15"), (15, "15+_to_17"),
    (17, "17+_to_19"), (19, "19+_to_21"), (21, "21+"),
]


def hd_to_attack_band(hd: str) -> str:
    """Map an HD-rating string to an attack-matrix band key.

    "NH" → nh; "½"/"0"/"1" → up_to_1; "N+x" (any plus) → band starting at N;
    a plain integer N ≥ 2 → band whose top is N.
    """
    s = str(hd).strip()
    if s.upper() == "NH":
        return "nh"
    if s in ("½", "1/2", "0", "1"):
        return "up_to_1"
    has_plus = "+" in s
    base = int(s.split("+", 1)[0])
    if base <= 1 and not has_plus:
        return "up_to_1"
    # "N+x" sits in the band whose lower bound is N; a plain "N" sits in the
    # band whose lower bound is N-1. Normalise to a "lower exclusive" value.
    lower = base if has_plus else base - 1
    for lo, key in _ATTACK_BANDS:
        if lower <= lo:
            return key
    return "21+"


def attack_for_hd(hd: str, data: GameData) -> AttackStats:
    row = data.monster_attack_matrix[hd_to_attack_band(hd)]
    return AttackStats(thac0=row["thac0"], attack_bonus=row["attack_bonus"])


# Save bands: (inclusive_upper, key). "NH" handled separately.
_SAVE_BANDS = [
    (3, "1-3"), (6, "4-6"), (9, "7-9"), (12, "10-12"),
    (15, "13-15"), (18, "16-18"), (21, "19-21"),
]


def _save_band(save_as_hd: int | str) -> str:
    if str(save_as_hd).upper() == "NH":
        return "nh"
    n = int(save_as_hd)
    for upper, key in _SAVE_BANDS:
        if n <= upper:
            return key
    return "22+"


def saves_for_hd(save_as_hd: int | str, data: GameData) -> dict[str, int]:
    return dict(data.monster_saves[_save_band(save_as_hd)])
