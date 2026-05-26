import random

import pytest

from aose.engine.dice import roll, roll_3d6_in_order, roll_hp


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


# ── roll_hp: max_hp_at_l1 ────────────────────────────────────────────────

def test_roll_hp_take_max_d8():
    # Deterministic — RNG is ignored entirely
    assert roll_hp("1d8", take_max=True) == 8


def test_roll_hp_take_max_d6():
    assert roll_hp("1d6", take_max=True) == 6


def test_roll_hp_take_max_does_not_consume_rng():
    rng = random.Random(0)
    roll_hp("1d8", rng, take_max=True)
    # If take_max ignored RNG, the next consumer should see seed-0 state.
    expected = random.Random(0).randint(1, 8)
    assert rng.randint(1, 8) == expected


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
