from pathlib import Path

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class, unarmored_ac
from aose.models import CharacterSpec, ClassEntry
from tests._itemhelp import coerce_equipment

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _spec(**kw):
    base = dict(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 13, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    coerce_equipment(base)
    return CharacterSpec(**base)


def test_unarmored_ac_is_base_minus_dex():
    # DEX 13 -> +1; unarmoured descending = 9 - 1 = 8, ascending = 11.
    spec = _spec()
    assert unarmored_ac(spec, DATA) == (8, 11)


def test_unarmored_ignores_worn_armour_but_armored_does_not():
    spec = _spec(equipped={"armor": "chain_mail"})
    desc_armored, _ = armor_class(spec, DATA)
    desc_unarmored, _ = unarmored_ac(spec, DATA)
    assert desc_unarmored == 8            # armour ignored
    assert desc_armored < desc_unarmored  # chainmail improves (lowers) descending AC
