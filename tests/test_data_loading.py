from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Ability

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_dwarf_loaded(data):
    dwarf = data.races["dwarf"]
    assert dwarf.name == "Dwarf"
    assert dwarf.infravision == 60
    # OSE Advanced dwarves move at the same base rate as humans (120').
    assert dwarf.base_movement == 120
    assert dwarf.ability_requirements[Ability.CON] == 9
    assert "fighter" in dwarf.allowed_classes
    assert dwarf.class_level_caps["fighter"] == 10


def test_fighter_loaded(data):
    fighter = data.classes["fighter"]
    assert fighter.name == "Fighter"
    assert fighter.hit_die == "1d8"
    assert fighter.weapons_allowed == "all"
    assert fighter.armor_allowed == "all"
    assert fighter.shields_allowed is True
    assert 1 in fighter.progression
    assert fighter.progression[1].thac0 == 19
    assert fighter.progression[1].saves["death"] == 12
    assert fighter.progression[4].thac0 == 17


def test_spell_model_fields():
    from aose.models import Spell

    s = Spell(
        id="magic_missile",
        name="Magic Missile",
        level=1,
        spell_lists=["magic_user"],
        source="ose-advanced",
        range="150'",
        duration="instant",
        description="A glowing dart strikes unerringly for 1d6+1 damage.",
    )
    assert s.spell_lists == ["magic_user"]
    assert s.source == "ose-advanced"
    assert not hasattr(s, "classes")


def test_charclass_spell_lists_field():
    from aose.models import CharClass

    caster = CharClass(
        id="magic_user",
        name="Magic-User",
        prime_requisites=["INT"],
        hit_die="1d4",
        weapons_allowed=["dagger"],
        armor_allowed=[],
        shields_allowed=False,
        spell_lists=["magic_user"],
    )
    assert caster.spell_lists == ["magic_user"]

    fighter = CharClass(
        id="fighter", name="Fighter", prime_requisites=["STR"],
        hit_die="1d8", weapons_allowed="all", armor_allowed="all",
        shields_allowed=True,
    )
    assert fighter.spell_lists == []
