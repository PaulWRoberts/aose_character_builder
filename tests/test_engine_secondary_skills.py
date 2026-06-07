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
