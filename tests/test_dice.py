import random

import pytest

from aose.engine.dice import (
    roll,
    roll_3d6_in_order,
    roll_3d6_in_order_detailed,
    roll_hp,
)


def test_roll_1d6_range():
    rng = random.Random(0)
    for _ in range(50):
        assert 1 <= roll("1d6", rng) <= 6


def test_roll_with_modifier():
    rng = random.Random(0)
    for _ in range(50):
        assert 3 <= roll("1d4+2", rng) <= 6


def test_roll_negative_modifier():
    rng = random.Random(0)
    for _ in range(50):
        result = roll("1d6-1", rng)
        assert 0 <= result <= 5


def test_roll_invalid_notation_raises():
    with pytest.raises(ValueError):
        roll("not a die")


def test_roll_3d6_in_order_returns_six_values():
    scores = roll_3d6_in_order(random.Random(0))
    assert len(scores) == 6
    assert all(3 <= s <= 18 for s in scores)


def test_roll_3d6_deterministic_with_seed():
    a = roll_3d6_in_order(random.Random(42))
    b = roll_3d6_in_order(random.Random(42))
    assert a == b


def test_roll_3d6_detailed_returns_six_triples():
    rolls = roll_3d6_in_order_detailed(random.Random(0))
    assert len(rolls) == 6
    for dice in rolls:
        assert len(dice) == 3
        assert all(1 <= d <= 6 for d in dice)


def test_roll_3d6_detailed_sums_match_in_order():
    seed = 7
    detailed = roll_3d6_in_order_detailed(random.Random(seed))
    scores = roll_3d6_in_order(random.Random(seed))
    assert [sum(dice) for dice in detailed] == scores


# ── roll_hp: reroll 1s & 2s ──────────────────────────────────────────────

def test_roll_hp_reroll_never_returns_below_three_on_d8():
    rng = random.Random(123)
    for _ in range(200):
        assert roll_hp("1d8", rng, min_die=3) >= 3


def test_roll_hp_reroll_within_die_max():
    rng = random.Random(0)
    for _ in range(200):
        assert 3 <= roll_hp("1d8", rng, min_die=3) <= 8


def test_roll_hp_reroll_falls_back_when_die_cannot_reach_min():
    # min_die=3 on a d2 is impossible — should silently treat as no reroll
    rng = random.Random(0)
    for _ in range(50):
        v = roll_hp("1d2", rng, min_die=3)
        assert 1 <= v <= 2


# ── roll_hp: default behaviour ───────────────────────────────────────────

def test_roll_hp_default_matches_plain_roll():
    rng_a = random.Random(7)
    rng_b = random.Random(7)
    assert roll_hp("1d8", rng_a) == roll("1d8", rng_b)


def test_roll_hp_invalid_notation_raises():
    with pytest.raises(ValueError):
        roll_hp("not a die")


def test_roll_blessed_hp_sets_returns_two_complete_sets():
    from aose.engine.dice import roll_blessed_hp_sets
    probe = random.Random(7)
    a = [probe.randint(1, 8), probe.randint(1, 4)]
    b = [probe.randint(1, 8), probe.randint(1, 4)]
    set_a, set_b = roll_blessed_hp_sets(["1d8", "1d4"], min_die=1,
                                        rng=random.Random(7))
    assert set_a == a
    assert set_b == b


def test_roll_blessed_hp_sets_respects_min_die():
    from aose.engine.dice import roll_blessed_hp_sets
    set_a, set_b = roll_blessed_hp_sets(["1d8", "1d4"], min_die=3,
                                        rng=random.Random(123))
    assert all(v >= 3 for v in set_a + set_b)

