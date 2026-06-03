"""Phase-2 bulk magic-item import: load-and-spot-check against real data."""
import random
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Armor, MagicItem, Weapon

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_gear_preserves_referenced_ids(data):
    for gid in ("torch", "crowbar", "lantern", "waterskin", "thieves_tools"):
        assert gid in data.items
    assert data.items["torch"].weight_cn == 20


def test_gear_has_descriptions(data):
    assert data.items["crowbar"].description
    assert "forcing doors" in data.items["crowbar"].description.lower()


def test_gear_adds_new_markdown_items(data):
    for gid in ("garlic", "grappling_hook", "holy_symbol", "wolfsbane", "pole_10ft"):
        assert gid in data.items


def test_containers_have_descriptions(data):
    bp = data.items["backpack"]
    assert "400 coins" in (bp.description or "")
    assert data.items["bag_of_holding"].magic is True


def test_rolled_modifier_rolls_into_extra_modifiers():
    """A MagicItem.rolled_modifiers entry becomes a concrete per-instance
    extra_modifier with a rolled value when the instance is created."""
    from aose.engine.magic import new_magic_instance
    d = GameData()
    d.items["test_bracers"] = MagicItem(
        id="test_bracers", name="Test Bracers", category="x", item_type="magic",
        cost_gp=0, magic=True, equippable=True,
        rolled_modifiers=[{"target": "ac", "op": "set", "dice": "1d4+3"}],
    )
    inst = new_magic_instance("test_bracers", d, rng=random.Random(1))
    assert len(inst.extra_modifiers) == 1
    m = inst.extra_modifiers[0]
    assert m.target == "ac" and m.op == "set" and 4 <= m.value <= 7
