"""Tests for magic items: Modifier value type, MagicItem catalog variant,
magic Weapon/Armor enchantment fields, MagicItemInstance runtime model, the
magic engine (active_modifiers / effective_abilities / charge helpers), the
derivation hooks (AC / saves / THAC0 / attacks / encumbrance), acquisition
routing, and the sheet + wizard HTTP routes."""
from pathlib import Path

import pytest

from aose.models import Modifier

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_modifier_parses_and_defaults():
    m = Modifier(target="ability:STR", op="set", value=18)
    assert m.target == "ability:STR"
    assert m.op == "set"
    assert m.value == 18


def test_modifier_rejects_unknown_op():
    with pytest.raises(ValueError):
        Modifier(target="ac", op="multiply", value=2)


def test_modifier_forbids_extra_fields():
    with pytest.raises(ValueError):
        Modifier(target="ac", op="add", value=1, bogus=True)
