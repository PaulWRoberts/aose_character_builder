import pytest
from pathlib import Path
from aose.data.loader import GameData
from aose.engine import monster_stats as ms

DATA = GameData.load(Path("data"))


@pytest.mark.parametrize("hd,thac0,ab", [
    ("½", 19, 0), ("1", 19, 0), ("2", 18, 1), ("3", 17, 2),
    ("1+2", 18, 1), ("2+2", 17, 2), ("NH", 20, -1),
])
def test_attack_for_hd(hd, thac0, ab):
    stats = ms.attack_for_hd(hd, DATA)
    assert stats.thac0 == thac0
    assert stats.attack_bonus == ab


@pytest.mark.parametrize("save_as,expected", [
    ("NH", {"death": 14, "wands": 15, "paralysis": 16, "breath": 17, "spells": 18}),
    (1, {"death": 12, "wands": 13, "paralysis": 14, "breath": 15, "spells": 16}),
    (2, {"death": 12, "wands": 13, "paralysis": 14, "breath": 15, "spells": 16}),
    (5, {"death": 10, "wands": 11, "paralysis": 12, "breath": 13, "spells": 14}),
])
def test_saves_for_hd(save_as, expected):
    assert ms.saves_for_hd(save_as, DATA) == expected


@pytest.mark.parametrize("desc,asc", [(7, 12), (9, 10), (8, 11)])
def test_ascending_ac(desc, asc):
    assert ms.ascending_ac(desc) == asc
