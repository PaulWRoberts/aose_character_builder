from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.sheet.view import build_sheet
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc():
    return CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral")


def test_sheet_has_retainer_card_with_derived_stats():
    pc = _pc()
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    sheet = build_sheet(pc, DATA)
    assert sheet.companions is not None
    card = sheet.companions.retainers[0]
    assert card.name == "Sten"
    assert card.loyalty == ret.loyalty
    assert card.hp_max >= 1
    assert card.ac_descending  # has an AC
    assert "death" in card.saves


def test_max_retainers_shown():
    pc = _pc()       # CHA 13 → 5 max
    ret = retainers.generate_retainer(
        name="A", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    sheet = build_sheet(pc, DATA)
    assert sheet.companions.max_retainers == 5
