from pathlib import Path
import random
import pytest
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc_with_retainer():
    pc = CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral", inventory=["torch"])
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    pc.retainers = [ret]
    return pc


def test_transfer_to_retainer_moves_item():
    pc = _pc_with_retainer()
    rid = pc.retainers[0].id
    retainers.transfer_to_retainer(pc, rid, "torch", DATA)
    assert "torch" not in pc.inventory
    assert "torch" in pc.retainers[0].spec.inventory


def test_transfer_to_pc_moves_item_back():
    pc = _pc_with_retainer()
    rid = pc.retainers[0].id
    pc.retainers[0].spec.inventory.append("torch")
    retainers.transfer_to_pc(pc, rid, "torch", DATA)
    assert "torch" in pc.inventory


def test_transfer_missing_item_raises():
    pc = _pc_with_retainer()
    with pytest.raises(ValueError):
        retainers.transfer_to_retainer(pc, pc.retainers[0].id, "nope", DATA)
