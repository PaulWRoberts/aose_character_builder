from pathlib import Path

from aose.data.loader import GameData
from aose.engine.attacks import attack_modifiers_detail
from aose.models import CharacterSpec, ClassEntry

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id, class_id="fighter", level=1):
    return CharacterSpec(
        name="T", race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[8])],
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
    )


def _cond(race_id, class_id="fighter", level=1):
    bd = attack_modifiers_detail(_spec(race_id, class_id, level), DATA)
    return [ln for ln in bd.lines if ln.conditional]


def test_drow_light_sensitivity_attack_penalty():
    lines = _cond("drow")
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               and ln.note == "in bright light" for ln in lines)


def test_duergar_light_sensitivity_attack_penalty():
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               for ln in _cond("duergar"))


def test_svirfneblin_light_sensitivity_attack_penalty():
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               for ln in _cond("svirfneblin"))


def test_light_sensitivity_applies_exactly_once_separate_and_race_as_class():
    # Separate mode: race_id=drow, class_id=fighter.
    sep = [ln for ln in _cond("drow", "fighter")
           if ln.source == "Light Sensitivity" and ln.bonus == -2]
    assert len(sep) == 1
    # Race-as-class: race_id=drow, class_id=drow. The drow *class* carries the
    # Light Sensitivity grant (self-contained); the race is not read for
    # race-as-class, so it applies exactly once.
    rac = [ln for ln in _cond("drow", "drow")
           if ln.source == "Light Sensitivity" and ln.bonus == -2]
    assert len(rac) == 1


def test_knight_mounted_attack_bonus():
    lines = _cond("human", "knight", level=1)
    assert any(ln.source == "Mounted Combat" and ln.bonus == 1
               and ln.note == "while mounted" for ln in lines)


def test_human_fighter_has_no_conditional_attack():
    assert _cond("human", "fighter") == []
