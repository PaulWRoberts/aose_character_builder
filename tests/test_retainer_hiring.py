from pathlib import Path
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc(cls, level):
    return CharacterSpec(
        name="PC", abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12,
                              "CON": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": cls, "level": level}],
        alignment="neutral")


def test_fighter_unrestricted():
    assert retainers.allowed_retainer_classes(_pc("fighter", 1), DATA) == "any"


def test_assassin_tiers():
    assert retainers.allowed_retainer_classes(_pc("assassin", 2), DATA) == set()
    assert retainers.allowed_retainer_classes(_pc("assassin", 5), DATA) == {"assassin"}
    assert retainers.allowed_retainer_classes(_pc("assassin", 9), DATA) == {"assassin", "thief"}
    assert retainers.allowed_retainer_classes(_pc("assassin", 12), DATA) == "any"
