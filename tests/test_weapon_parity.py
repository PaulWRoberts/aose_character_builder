"""Parametric weapons.yaml derives exactly the pre-refactor stored values."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Weapon

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


# (id, melee, ranged, hands, ranges_or_None, variable_damage, two_handed_damage)
EXPECTED = {
    "battle_axe":      (True,  False, 2, None,            "1d8",  None),
    "club":            (True,  False, 1, None,            "1d4",  None),
    "crossbow":        (False, True,  2, (80, 160, 240),  "1d6",  None),
    "dagger":          (True,  True,  1, (10, 20, 30),    "1d4",  None),
    "hand_axe":        (True,  True,  1, (10, 20, 30),    "1d6",  None),
    "javelin":         (False, True,  1, (30, 60, 90),    "1d4",  None),
    "lance":           (True,  False, 1, None,            "1d6",  None),
    "long_bow":        (False, True,  2, (70, 140, 210),  "1d6",  None),
    "mace":            (True,  False, 1, None,            "1d6",  None),
    "polearm":         (True,  False, 2, None,            "1d10", None),
    "short_bow":       (False, True,  2, (50, 100, 150),  "1d6",  None),
    "short_sword":     (True,  False, 1, None,            "1d6",  None),
    "silver_dagger":   (True,  True,  1, (10, 20, 30),    "1d4",  None),
    "sling":           (False, True,  1, (40, 80, 160),   "1d4",  None),
    "spear":           (True,  True,  1, (20, 40, 60),    "1d6",  None),
    "staff":           (True,  False, 2, None,            "1d4",  None),
    "sword":           (True,  False, 1, None,            "1d8",  None),
    "two_handed_sword":(True,  False, 2, None,            "1d10", None),
    "war_hammer":      (True,  False, 1, None,            "1d6",  None),
    "trident":         (True,  False, 1, None,            "1d6",  None),
}


@pytest.mark.parametrize("wid", sorted(EXPECTED))
def test_weapon_derives_legacy_values(data, wid):
    w = data.items[wid]
    assert isinstance(w, Weapon)
    melee, ranged, hands, ranges, var, two_h = EXPECTED[wid]
    assert w.melee is melee
    assert w.ranged is ranged
    assert w.hands == hands
    got = (w.range_short, w.range_medium, w.range_long) if w.ranged else None
    assert got == ranges
    assert w.damage.default == "1d6"     # standard rule, uniform
    assert w.damage.variable == var
    assert w.two_handed_damage == two_h
    assert w.deals_damage is True


def test_spear_is_not_versatile(data):
    assert data.items["spear"].versatile is False
