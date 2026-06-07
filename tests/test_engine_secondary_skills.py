"""Tests for the SecondarySkillEntry model and the secondary-skill roll engine."""
import random

import pytest

from aose.models import SecondarySkillEntry


def test_entry_defaults_roll_twice_false():
    e = SecondarySkillEntry(name="Farmer", weight=11)
    assert e.name == "Farmer"
    assert e.weight == 11
    assert e.roll_twice is False


def test_entry_rejects_zero_weight():
    with pytest.raises(ValueError):
        SecondarySkillEntry(name="Farmer", weight=0)


# ── Engine tests ────────────────────────────────────────────────────────────

from aose.engine.secondary_skills import (
    SecondarySkillError,
    roll,
    selectable_names,
)

TABLE = [
    SecondarySkillEntry(name="Farmer", weight=11),
    SecondarySkillEntry(name="Mason", weight=2),
    SecondarySkillEntry(name="Bookbinder", weight=1),
    SecondarySkillEntry(name="Roll for two skills", weight=2, roll_twice=True),
]


def test_selectable_names_excludes_roll_twice():
    assert selectable_names(TABLE) == ["Farmer", "Mason", "Bookbinder"]


def test_roll_normal_returns_single_trade():
    out = roll(TABLE, rng=random.Random(0))
    assert len(out) == 1
    assert out[0] in selectable_names(TABLE)


def test_roll_twice_returns_two_distinct_trades():
    # Force the roll-twice row by using a table where it dominates.
    table = [
        SecondarySkillEntry(name="A", weight=1),
        SecondarySkillEntry(name="B", weight=1),
        SecondarySkillEntry(name="C", weight=1),
        SecondarySkillEntry(name="Roll for two skills", weight=97, roll_twice=True),
    ]
    for seed in range(50):
        out = roll(table, rng=random.Random(seed))
        if len(out) == 2:
            assert out[0] != out[1]
            assert "Roll for two skills" not in out
            return
    pytest.fail("never hit a roll-twice expansion in 50 seeds")


def test_roll_never_nests_roll_twice():
    table = [
        SecondarySkillEntry(name="A", weight=1),
        SecondarySkillEntry(name="B", weight=1),
        SecondarySkillEntry(name="RT1", weight=49, roll_twice=True),
        SecondarySkillEntry(name="RT2", weight=49, roll_twice=True),
    ]
    for seed in range(50):
        out = roll(table, rng=random.Random(seed))
        assert "RT1" not in out and "RT2" not in out
        assert len(set(out)) == len(out)


def test_roll_twice_raises_without_two_trades():
    table = [
        SecondarySkillEntry(name="Only", weight=1),
        SecondarySkillEntry(name="Roll for two skills", weight=99, roll_twice=True),
    ]
    raised = False
    for seed in range(50):
        try:
            roll(table, rng=random.Random(seed))
        except SecondarySkillError:
            raised = True
            break
    assert raised, "SecondarySkillError never raised with only one trade"


def test_roll_empty_table_raises():
    with pytest.raises(SecondarySkillError):
        roll([], rng=random.Random(0))


def test_roll_distribution_tracks_weights():
    counts = {"Farmer": 0, "Mason": 0, "Bookbinder": 0}
    rng = random.Random(1234)
    table = [
        SecondarySkillEntry(name="Farmer", weight=11),
        SecondarySkillEntry(name="Mason", weight=2),
        SecondarySkillEntry(name="Bookbinder", weight=1),
    ]
    for _ in range(4000):
        counts[roll(table, rng=rng)[0]] += 1
    assert counts["Farmer"] > counts["Mason"] > counts["Bookbinder"]
