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


def test_detail_headline_includes_wis_on_spells_only():
    from aose.engine.saves import saving_throws, saving_throws_detail
    base = saving_throws(_spec(wis=10), DATA)
    hi = saving_throws_detail(_spec(wis=16), DATA)        # +2
    assert hi["spells"].modified == base["spells"] - 2    # WIS in headline
    assert hi["wands"].modified == base["wands"] - 2
    assert hi["death"].modified == base["death"]          # conditional: not in headline
    assert hi["paralysis"].modified == base["paralysis"]
    assert hi["breath"].modified == base["breath"]


def test_detail_death_has_conditional_wis_line():
    from aose.engine.saves import saving_throws_detail
    detail = saving_throws_detail(_spec(wis=16), DATA)
    wis_lines = [ln for ln in detail["death"].lines
                 if ln.source == "Wisdom" and ln.conditional]
    assert len(wis_lines) == 1
    assert wis_lines[0].bonus == 2
    assert "magical" in wis_lines[0].note


def test_detail_base_is_class_progression():
    from aose.engine.saves import saving_throws_detail
    detail = saving_throws_detail(_spec(wis=16), DATA)
    # Base excludes all modifiers; fighter L1 death base is 12.
    assert detail["death"].base == 12


def test_detail_dwarf_poison_and_spells_lines():
    from aose.engine.saves import saving_throws_detail
    detail = saving_throws_detail(_spec(con=13, race="dwarf"), DATA)
    # spells: unconditional resilience line, in the headline.
    spells_res = [ln for ln in detail["spells"].lines if ln.source == "Resilience"]
    assert spells_res and spells_res[0].conditional is False and spells_res[0].bonus == 3
    # death: conditional poison line, NOT in the headline.
    death_res = [ln for ln in detail["death"].lines if ln.source == "Resilience"]
    assert death_res and death_res[0].conditional is True
    assert death_res[0].note.startswith("poison")
