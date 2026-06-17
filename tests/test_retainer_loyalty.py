from pathlib import Path
from aose.data.loader import GameData
from aose.engine import ability_mods, retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _spec(cha, race="human", cls="fighter"):
    return CharacterSpec(
        name="PC", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                              "CON": 10, "CHA": cha},
        race_id=race, classes=[{"class_id": cls}], alignment="neutral")


def test_cha_accessors():
    assert ability_mods.max_retainers(3) == 1
    assert ability_mods.max_retainers(13) == 5
    assert ability_mods.max_retainers(18) == 7
    assert ability_mods.base_loyalty(9) == 7
    assert ability_mods.base_loyalty(18) == 10


def test_human_grants_plus_one_loyalty():
    # human CHA 9 base loyalty 7, +1 from human → 8
    assert retainers.initial_loyalty(_spec(9, race="human"), "elf", DATA) == 8


def test_half_orc_minus_one_except_for_half_orc_retainers():
    pc = _spec(9, race="half_orc", cls="half_orc")
    assert retainers.initial_loyalty(pc, "human", DATA) == 6      # 7 - 1
    assert retainers.initial_loyalty(pc, "half_orc", DATA) == 7   # exception
