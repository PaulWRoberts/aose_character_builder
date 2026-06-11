import pytest
from pydantic import ValidationError

from aose.models import CharacterSpec, RuleSet


def test_default_ruleset():
    rs = RuleSet()
    assert rs.ascending_ac is False
    assert rs.separate_race_class is True
    assert rs.lift_demihuman_restrictions is False
    assert rs.encumbrance == "basic"


def test_ruleset_has_no_removed_flags():
    """max_hp_at_l1, the two split demihuman flags, and ability_roll_method are
    gone; extra='forbid' means passing them raises rather than silently
    accepting."""
    for dead in ("max_hp_at_l1", "demihuman_level_limits",
                 "demihuman_class_restrictions", "ability_roll_method"):
        with pytest.raises(ValidationError):
            RuleSet(**{dead: True})  # type: ignore[arg-type]


def test_ruleset_rejects_unknown_field():
    with pytest.raises(ValidationError):
        RuleSet(does_not_exist=True)  # type: ignore[call-arg]


def test_character_requires_at_least_one_class():
    with pytest.raises(ValidationError):
        CharacterSpec(
            name="Nobody",
            abilities={
                "STR": 10, "INT": 10, "WIS": 10,
                "DEX": 10, "CON": 10, "CHA": 10,
            },
            race_id="dwarf",
            classes=[],
            alignment="law",
        )


def test_character_spec_temp_ability_modifiers_default_empty():
    from aose.models import ClassEntry
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
    )
    assert spec.temp_ability_modifiers == {}


def test_character_spec_temp_ability_modifiers_keyed_by_ability_enum():
    from aose.models import Ability, ClassEntry
    spec = CharacterSpec(
        name="T",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        temp_ability_modifiers={"STR": -2},
    )
    assert spec.temp_ability_modifiers[Ability.STR] == -2


def test_spell_source_round_trips():
    from aose.models import CharacterSpec, ClassEntry, SpellSource, SpellSourceEntry
    src = SpellSource(
        instance_id="abc", kind="scroll", caster_type="arcane", name="Found Scroll",
        entries=[SpellSourceEntry(spell_id="magic_user_magic_missile"),
                 SpellSourceEntry(spell_id="magic_user_sleep", copy_failed=True)],
    )
    spec = CharacterSpec(
        name="X", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral", spell_sources=[src],
    )
    reloaded = CharacterSpec.model_validate(spec.model_dump())
    assert reloaded.spell_sources[0].kind == "scroll"
    assert reloaded.spell_sources[0].entries[1].copy_failed is True
    # default is an empty list
    bare = CharacterSpec(
        name="Y", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral",
    )
    assert bare.spell_sources == []


def test_valuable_models_defaults():
    from aose.models import GemStack, JewelleryPiece, CharacterSpec

    g = GemStack(instance_id="abc", value=100)
    assert g.count == 1
    assert g.label == ""

    j = JewelleryPiece(instance_id="def", value=700)
    assert j.damaged is False
    assert j.label == ""

    spec = CharacterSpec(
        name="T",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [8]}],
        alignment="neutral",
    )
    assert spec.gems == []
    assert spec.jewellery == []


def test_content_models_default_to_classic_source():
    from aose.models import (
        AdventuringGear, CharClass, Enchantment, Race, Spell, SpellList,
    )
    from aose.models.enchantment import AppliesTo

    gear = AdventuringGear(id="x", name="X", category="c", cost_gp=1, item_type="gear")
    assert gear.source == "ose_classic_fantasy"

    race = Race(id="x", name="X")
    assert race.source == "ose_classic_fantasy"

    cls = CharClass(id="x", name="X", prime_requisites=[], hit_die="1d6",
                    weapons_allowed="all", armor_allowed="all", shields_allowed=True)
    assert cls.source == "ose_classic_fantasy"

    sl = SpellList(id="x", name="X", caster_type="arcane")
    assert sl.source == "ose_classic_fantasy"

    ench = Enchantment(id="x", name_template="{base} +1", kind="weapon",
                       applies_to=AppliesTo(include=["any_weapon"]))
    assert ench.source == "ose_classic_fantasy"

    spell = Spell(id="x", name="X", level=1, range="0", duration="0", description="d")
    assert spell.source == "ose_classic_fantasy"


def test_disabled_content_defaults_empty():
    from aose.models import RuleSet
    assert RuleSet().disabled_content == []


def test_disabled_content_round_trips():
    from aose.models import RuleSet
    rs = RuleSet(disabled_content=["carcass_crawler_3:equipment"])
    assert rs.disabled_content == ["carcass_crawler_3:equipment"]


def test_legacy_disabled_sources_is_coerced_to_categories():
    """An old save with disabled_sources expands to all three category keys
    and drops the legacy field (extra='forbid' would otherwise reject it)."""
    from aose.models import RuleSet
    rs = RuleSet.model_validate({"disabled_sources": ["carcass_crawler_3"]})
    assert set(rs.disabled_content) == {
        "carcass_crawler_3:classes",
        "carcass_crawler_3:equipment",
        "carcass_crawler_3:magic_items",
    }


def test_legacy_coercion_skips_classic():
    from aose.models import RuleSet
    rs = RuleSet.model_validate(
        {"disabled_sources": ["ose_classic_fantasy", "ose_advanced_fantasy"]}
    )
    assert all(not k.startswith("ose_classic_fantasy:") for k in rs.disabled_content)
    assert "ose_advanced_fantasy:classes" in rs.disabled_content
