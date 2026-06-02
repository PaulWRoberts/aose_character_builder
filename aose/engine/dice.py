import random
import re
from typing import Optional

_DICE_RE = re.compile(r"^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$")
_NDS_RE = re.compile(r"^\s*(\d+)d(\d+)")


def roll(dice: str, rng: Optional[random.Random] = None) -> int:
    """Roll standard NdS or NdS+M notation."""
    m = _DICE_RE.match(dice)
    if not m:
        raise ValueError(f"Invalid dice notation: {dice!r}")
    n, s = int(m.group(1)), int(m.group(2))
    mod = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    r = rng or random.Random()
    return sum(r.randint(1, s) for _ in range(n)) + mod


def roll_3d6_in_order(rng: Optional[random.Random] = None) -> list[int]:
    r = rng or random.Random()
    return [sum(r.randint(1, 6) for _ in range(3)) for _ in range(6)]


def roll_blessed_hp_sets(
    hit_dice: list[str],
    *,
    min_die: int = 1,
    rng: Optional[random.Random] = None,
) -> tuple[list[int], list[int]]:
    """Roll two complete first-level HP sets (one die per class each) for the
    Human Blessed ability. Returns ``(set_a, set_b)`` in draw order; the caller
    decides which to keep (larger sum, ties keep ``set_a``)."""
    r = rng or random.Random()
    set_a = [roll_hp(hd, r, min_die=min_die) for hd in hit_dice]
    set_b = [roll_hp(hd, r, min_die=min_die) for hd in hit_dice]
    return set_a, set_b


def roll_first_level_hp(
    hit_dice: list[str],
    *,
    blessed: bool,
    min_die: int = 1,
    rng: Optional[random.Random] = None,
) -> list[int]:
    """Roll first-level HP, one entry per class in ``hit_dice`` order.

    ``min_die`` is forwarded to :func:`roll_hp` (the reroll-1s-2s house rule
    passes 3). When ``blessed`` is set (Human Blessed racial ability) two
    *complete* sets are rolled — one die per class each — and the set with the
    larger sum of rolls is kept; ties keep the first set. There is no per-class
    cherry-picking across sets (N and CON are identical, so summed rolls is the
    correct comparison).
    """
    r = rng or random.Random()

    def one_set() -> list[int]:
        return [roll_hp(hd, r, min_die=min_die) for hd in hit_dice]

    if not blessed:
        return one_set()
    set_a, set_b = roll_blessed_hp_sets(hit_dice, min_die=min_die, rng=r)
    return set_a if sum(set_a) >= sum(set_b) else set_b


def roll_hp(
    hit_die: str,
    rng: Optional[random.Random] = None,
    *,
    min_die: int = 1,
) -> int:
    """Roll first-level HP from a hit die, with an optional re-roll house rule.

    min_die > 1 -> any single-die result below ``min_die`` is re-rolled until it
                   lands at or above it ("re-roll 1s & 2s" uses 3). Silently
                   treated as 1 if the die can't reach ``min_die``.
    """
    m = _NDS_RE.match(hit_die)
    if not m:
        raise ValueError(f"Invalid dice notation: {hit_die!r}")
    n, s = int(m.group(1)), int(m.group(2))

    effective_min = min_die if min_die <= s else 1
    r = rng or random.Random()
    total = 0
    for _ in range(n):
        v = r.randint(1, s)
        while v < effective_min:
            v = r.randint(1, s)
        total += v
    return total
