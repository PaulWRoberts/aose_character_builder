from pathlib import Path
from aose.data.loader import GameData
from aose.engine import saves, hp
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _nh_spec():
    return CharacterSpec(
        name="Linkboy", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                                   "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "normal_human", "level": 1,
                                    "hp_rolls": [2]}],
        alignment="neutral")


def test_normal_human_loads_with_nh_saves():
    cls = DATA.classes["normal_human"]
    assert cls.max_level == 1
    row = cls.progression[1]
    assert row.thac0 == 20
    assert row.saves == {"death": 14, "wands": 15, "paralysis": 16,
                         "breath": 17, "spells": 18}


def test_normal_human_saving_throws_are_nh_row():
    spec = _nh_spec()
    st = saves.saving_throws(spec, DATA)
    assert st["death"] == 14 and st["spells"] == 18


def test_normal_human_hp_is_small():
    assert hp.max_hp(_nh_spec(), DATA) >= 1
