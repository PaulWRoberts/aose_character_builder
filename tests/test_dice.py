import random

import pytest

from aose.engine.dice import roll, roll_3d6_in_order


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
