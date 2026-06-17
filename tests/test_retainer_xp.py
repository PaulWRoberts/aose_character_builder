from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec

DATA = GameData.load(Path("data"))


def _pc():
    return CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": 13},
        race_id="human", classes=[{"class_id": "fighter", "level": 5}],
        alignment="neutral")


def test_grant_retainer_xp_halves_awards():
    ret = retainers.generate_retainer(
        name="X", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_pc(), data=DATA, rng=random.Random(1))
    before = ret.spec.classes[0].xp
    retainers.grant_retainer_xp(ret, DATA, 1000)     # fighter prime-req mult ~1.0
    assert ret.spec.classes[0].xp == before + 500    # -50% penalty


def test_promote_normal_human_swaps_class_keeping_xp():
    ret = retainers.generate_retainer(
        name="Boy", class_ids=["normal_human"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_pc(), data=DATA, rng=random.Random(2))
    ret.spec.classes[0].xp = 300
    retainers.promote_normal_human(ret, "fighter", DATA, rng=random.Random(2))
    assert ret.spec.classes[0].class_id == "fighter"
    assert ret.spec.classes[0].level == 1
    assert ret.spec.classes[0].xp == 300
