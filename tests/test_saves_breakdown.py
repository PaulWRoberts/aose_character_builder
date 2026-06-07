"""WIS magic saves + breakdown view model."""
from pathlib import Path

from aose.models import CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    from aose.data.loader import GameData
    return GameData.load(DATA_DIR)


DATA = _data()


def _spec(*, wis=10, con=10, race="human", cls="fighter", level=1):
    return CharacterSpec(
        name="W",
        abilities={"STR": 10, "INT": 10, "WIS": wis, "DEX": 10, "CON": con, "CHA": 10},
        race_id=race, alignment="neutral",
        classes=[ClassEntry(class_id=cls, level=level, hp_rolls=[8])],
    )


def test_wisdom_mods_unconditional_on_spells_and_wands():
    from aose.engine.saves import wisdom_save_modifiers
    mods = wisdom_save_modifiers(_spec(wis=16), DATA)   # +2
    by_target = {(m.target, m.condition): m for m in mods}
    assert by_target[("save:spells", None)].value == 2
    assert by_target[("save:wands", None)].value == 2


def test_wisdom_mods_conditional_on_death_and_paralysis():
    from aose.engine.saves import wisdom_save_modifiers
    mods = wisdom_save_modifiers(_spec(wis=16), DATA)
    by_target = {(m.target, m.condition): m for m in mods}
    assert by_target[("save:death", "magical")].value == 2
    assert by_target[("save:paralysis", "magical")].value == 2
    # WIS never targets breath.
    assert not any(m.target == "save:breath" for m in mods)


def test_wisdom_mods_empty_when_zero():
    from aose.engine.saves import wisdom_save_modifiers
    assert wisdom_save_modifiers(_spec(wis=10), DATA) == []


def test_wisdom_mods_negative_penalty():
    from aose.engine.saves import wisdom_save_modifiers
    mods = wisdom_save_modifiers(_spec(wis=4), DATA)    # -2
    assert all(m.value == -2 for m in mods)
    assert all(m.source == "Wisdom" for m in mods)
