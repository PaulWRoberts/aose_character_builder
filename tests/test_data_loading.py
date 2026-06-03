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


def test_demihuman_ability_modifiers_loaded(data):
    assert data.races["dwarf"].ability_modifiers == {Ability.CHA: -1, Ability.CON: 1}
    assert data.races["duergar"].ability_modifiers == {Ability.CHA: -1, Ability.CON: 1}
    assert data.races["drow"].ability_modifiers == {Ability.CON: -1, Ability.DEX: 1}
    assert data.races["elf"].ability_modifiers == {Ability.CON: -1, Ability.DEX: 1}
    assert data.races["halfling"].ability_modifiers == {Ability.DEX: 1, Ability.STR: -1}
    assert data.races["half_orc"].ability_modifiers == {
        Ability.CHA: -2, Ability.CON: 1, Ability.STR: 1
    }


def test_races_without_modifiers_have_empty_field(data):
    for rid in ("gnome", "half_elf", "svirfneblin"):
        assert data.races[rid].ability_modifiers == {}


def test_human_optional_modifier_feature_untouched(data):
    human = data.races["human"]
    assert human.ability_modifiers == {}
    feature = next(f for f in human.features if f.id == "optional_ability_modifiers")
    assert feature.mechanical["ability_modifiers"] == {"CHA": 1, "CON": 1}


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


def test_languages_loaded(data):
    langs = data.languages
    assert langs.alignment["law"] == "Lawful"
    assert langs.alignment["neutral"] == "Neutral"
    assert langs.alignment["chaos"] == "Chaotic"
    assert "Elvish" in langs.additional
    # UTF-8 diacritic survives the load round-trip.
    assert "Doppelgänger" in langs.additional


def test_character_spec_languages_defaults_empty():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="X", abilities={}, race_id="human",
        classes=[ClassEntry(class_id="fighter")], alignment="law",
    )
    assert spec.languages == []


def test_classes_have_name_level_fields(data):
    fighter = data.classes["fighter"]
    assert fighter.name_level == 9
    assert fighter.hp_after_name_level == 2
    assert data.classes["magic_user"].hp_after_name_level == 1
    assert data.classes["cleric"].hp_after_name_level == 1
    assert data.classes["barbarian"].hp_after_name_level == 3
    assert data.classes["thief"].hp_after_name_level == 2
    # Capped race-as-class options: dice stop at 8, fixed step never fires.
    assert data.classes["gnome"].name_level == 8
    assert data.classes["halfling"].name_level == 8


def test_hit_dice_removed_from_class_level_data():
    from pydantic import ValidationError
    from aose.models.character_class import ClassLevelData

    # The retired `hit_dice` field must now be rejected (extra="forbid").
    with pytest.raises(ValidationError):
        ClassLevelData(
            xp_required=0, thac0=19, hit_dice="1d8",
            saves={"death": 12, "wands": 13, "paralysis": 14,
                   "breath": 15, "spells": 16},
        )
