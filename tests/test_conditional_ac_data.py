from pathlib import Path

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class_detail
from aose.models import CharacterSpec, ClassEntry

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id, class_id="fighter"):
    return CharacterSpec(
        name="T", race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=1, hp_rolls=[8])],
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
    )


def _cond(race_id, class_id="fighter"):
    bd = armor_class_detail(_spec(race_id, class_id), DATA)
    return [ln for ln in bd.lines if ln.conditional]


def test_drow_light_sensitivity_minus_one():
    lines = _cond("drow")
    assert any(ln.source == "Light Sensitivity" and ln.effect == "−1"
               and ln.note == "in bright light" for ln in lines)


def test_duergar_light_sensitivity_minus_one():
    lines = _cond("duergar", class_id="fighter")
    assert any(ln.source == "Light Sensitivity" and ln.effect == "−1" for ln in lines)


def test_gnome_defensive_bonus_plus_two():
    lines = _cond("gnome")
    assert any(ln.source == "Defensive Bonus" and ln.effect == "+2"
               and ln.note == "vs attackers larger than human-sized" for ln in lines)


def test_halfling_defensive_bonus_plus_two():
    lines = _cond("halfling")
    assert any(ln.source == "Defensive Bonus" and ln.effect == "+2" for ln in lines)


def test_svirfneblin_has_both():
    lines = _cond("svirfneblin")
    effects = {(ln.source, ln.effect) for ln in lines}
    assert ("Light Sensitivity", "−1") in effects
    assert ("Defensive Bonus", "+2") in effects


def test_human_has_no_conditional_ac():
    assert _cond("human") == []
