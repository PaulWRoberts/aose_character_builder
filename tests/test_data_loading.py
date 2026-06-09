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
    assert "elvish" in langs.additional
    # UTF-8 diacritic survives the load round-trip (registry value, not the id).
    assert langs.names.get("doppelganger") == "Doppelgänger"


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



def test_protection_scrolls_loaded():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import MagicItem
    data = GameData.load(Path(__file__).parent.parent / "data")
    for sid in ("scroll_of_protection_from_elementals",
                "scroll_of_protection_from_lycanthropes",
                "scroll_of_protection_from_magic",
                "scroll_of_protection_from_undead"):
        item = data.items[sid]
        assert isinstance(item, MagicItem)
        assert item.magic is True
        assert item.category == "scrolls"
        assert item.description


def test_sources_loaded(data):
    classic = data.sources["ose_classic_fantasy"]
    assert classic.name == "Old School Essentials Classic Fantasy"
    assert classic.publisher == "Necrotic Gnome"
    assert classic.core is True
    advanced = data.sources["ose_advanced_fantasy"]
    assert advanced.name == "Old School Essentials Advanced Fantasy"
    assert advanced.core is True


def test_sources_absent_file_is_empty(tmp_path):
    # A bare data dir (no sources.yaml) loads to an empty registry.
    assert GameData.load(tmp_path).sources == {}


def test_race_sources(data):
    assert data.races["human"].source == "ose_classic_fantasy"
    for rid in ("drow", "duergar", "dwarf", "elf", "gnome", "half_elf",
                "half_orc", "halfling", "svirfneblin"):
        assert data.races[rid].source == "ose_advanced_fantasy", rid


def test_class_sources(data):
    for cid in ("cleric", "fighter", "magic_user", "thief",
                "dwarf", "elf", "halfling"):
        assert data.classes[cid].source == "ose_classic_fantasy", cid
    for cid in ("acrobat", "assassin", "barbarian", "bard", "drow", "druid",
                "duergar", "gnome", "half_elf", "half_orc", "illusionist",
                "knight", "paladin", "ranger", "svirfneblin"):
        assert data.classes[cid].source == "ose_advanced_fantasy", cid


def test_spell_list_sources(data):
    assert data.spell_lists["magic_user"].source == "ose_classic_fantasy"
    assert data.spell_lists["cleric"].source == "ose_classic_fantasy"
    assert data.spell_lists["druid"].source == "ose_advanced_fantasy"
    assert data.spell_lists["illusionist"].source == "ose_advanced_fantasy"


def test_spell_sources_match_their_list(data):
    for spell in data.spells.values():
        lists = set(spell.spell_lists)
        # A spell's source must match the source of at least one of its spell
        # lists.  This allows spells from non-OSE sources (e.g. carcass_crawler_1)
        # without hard-coding the source mapping.
        list_sources = {data.spell_lists[lid].source
                        for lid in lists if lid in data.spell_lists}
        assert spell.source in list_sources, (
            f"{spell.id}: source {spell.source!r} not in list sources {list_sources}"
        )


ADVANCED_MAGIC_ITEM_IDS = {
    "alchemists_beaker", "amulet_of_protection_against_possession",
    "apparatus_of_the_crab", "arrow_of_location", "bag_of_transformation",
    "book_of_foul_corruption", "book_of_infinite_spells",
    "book_of_sublime_holiness", "boots_of_dancing", "bracers_of_armour",
    "bracers_of_defencelessness", "brooch_of_shielding", "candle_of_invocation",
    "chime_of_opening", "chime_of_ravening", "cloak_of_defence",
    "cloak_of_flight", "cloak_of_poison", "cloak_of_the_manta_ray",
    "crystal_hypnosis_ball", "cube_of_force", "cube_of_frost_resistance",
    "decanter_of_endless_water", "deck_of_many_things", "drums_of_thunder",
    "dust_of_appearance", "dust_of_disappearance", "dust_of_sneezing_and_choking",
    "eyes_of_charming", "eyes_of_minuscule_sight", "eyes_of_petrification",
    "eyes_of_the_eagle", "feather_token", "figurine_of_wondrous_power",
    "folding_boat", "gem_of_brightness", "gem_of_monster_attraction",
    "gem_of_pristine_faceting", "gem_of_seeing", "gloves_of_dexterity",
    "gloves_of_swimming_and_climbing", "horn_of_cave_ins", "horn_of_frothing",
    "horn_of_the_tritons", "horn_of_valhalla", "horseshoes_of_a_zephyr",
    "horseshoes_of_speed", "incense_of_meditation", "incense_of_obsession",
    "instant_fortress", "ioun_stones", "iron_flask", "jug_of_endless_liquids",
    "libram_of_arcane_power", "loadstone", "luckstone", "lyre_of_building",
    "marvellous_pigments", "medallion_of_thought_projection",
    "mirror_of_mental_prowess", "mirror_of_opposition", "necklace_of_adaptation",
    "necklace_of_fireballs", "necklace_of_strangulation", "net_of_aquatic_snaring",
    "net_of_snaring", "oil_of_insubstantiality", "oil_of_slipperiness",
    "pearl_of_power", "pearl_of_wisdom", "periapt_of_foul_rotting",
    "periapt_of_health", "periapt_of_proof_against_poison",
    "periapt_of_wound_closure", "phylactery_of_betrayal",
    "phylactery_of_faithfulness", "phylactery_of_longevity", "pipes_of_the_sewers",
    "portable_hole", "purse_of_plentiful_coin", "restorative_ointment",
    "robe_of_blending", "robe_of_eyes", "robe_of_powerlessness",
    "robe_of_scintillating_colours", "robe_of_the_archmagi", "robe_of_useful_items",
    "rod_absorption", "rod_captivation", "rod_immovable", "rod_lordly_might",
    "rod_parrying", "rod_resurrection", "rod_striking", "rope_of_entanglement",
    "rope_of_strangulation", "rug_of_suffocation", "saw_of_felling",
    "scarab_of_chaos", "scarab_of_death", "scarab_of_rage", "spade_of_mighty_digging",
    "sphere_of_annihilation", "staff_dispelling", "staff_of_the_healer",
    "staff_of_the_woodlands", "staff_swarming_insects", "sweet_water",
    "talisman_of_the_sphere", "vacuous_grimoire", "wand_magic_missiles",
    "wand_radiance", "wand_summoning", "well_of_many_worlds",
}

ADVANCED_ENCHANTMENT_IDS = {
    "short_sword_of_quickness", "sword_minus_1_berserker", "sword_plus_1_vs_reptiles",
    "sword_plus_1_vs_shapechangers", "sword_dragon_slayer", "sword_frost_brand",
    "sword_giant_slayer", "luck_blade", "sword_sharpness", "sword_sun_blade",
    "sword_wounding", "sword_dancing", "sword_nine_lives_stealer", "sword_venger",
    "sword_vorpal", "sword_defender", "sword_holy_avenger", "arrow_slaying",
    "crossbow_distance", "crossbow_speed", "crossbow_accuracy", "dagger_buckle",
    "dagger_throwing", "dagger_venomous", "dagger_biter", "javelin_of_lightning",
    "javelin_of_seeking", "mace_disrupting", "sling_bullet_impact", "spear_backbiter",
    "staff_growing", "trident_yearning", "trident_fish_command", "trident_submission",
    "trident_warning", "war_hammer_thunderbolts",
}


def test_magic_item_sources(data):
    assert len(ADVANCED_MAGIC_ITEM_IDS) == 114
    for iid, item in data.items.items():
        if iid in ADVANCED_MAGIC_ITEM_IDS:
            assert item.source == "ose_advanced_fantasy", iid
        else:
            assert item.source == "ose_classic_fantasy", iid


def test_enchantment_sources(data):
    assert len(ADVANCED_ENCHANTMENT_IDS) == 36
    for eid, ench in data.enchantments.items():
        if eid in ADVANCED_ENCHANTMENT_IDS:
            assert ench.source == "ose_advanced_fantasy", eid
        else:
            assert ench.source == "ose_classic_fantasy", eid


# ── Carcass Crawler 1: classes ────────────────────────────────────────────────

def test_acolyte_loaded(data):
    cls = data.classes["acolyte"]
    assert cls.name == "Acolyte"
    assert cls.source == "carcass_crawler_1"
    assert "WIS" in [a.value for a in cls.prime_requisites]
    assert cls.spell_lists == ["cleric"]
    assert cls.max_level == 14
    assert cls.hit_die == "1d6"
    assert cls.progression[1].spell_slots is None


def test_mage_cc1_loaded(data):
    cls = data.classes["mage"]
    assert cls.name == "Mage"
    assert cls.source == "carcass_crawler_1"
    assert {a.value for a in cls.prime_requisites} == {"INT", "WIS"}
    assert cls.spell_lists == ["magic_user"]
    assert cls.max_level == 14
    assert cls.hit_die == "1d6"
    assert cls.progression[1].spell_slots is None


def test_gargantua_class_loaded(data):
    cls = data.classes["gargantua"]
    assert cls.source == "carcass_crawler_1"
    assert cls.race_locked == "gargantua"
    assert {a.value for a in cls.prime_requisites} == {"CON", "STR"}
    assert cls.hit_die == "1d10"
    assert cls.max_level == 10
    assert cls.name_level == 9
    assert cls.hp_after_name_level == 3
    assert cls.progression[1].thac0 == 19
    assert cls.progression[10].thac0 == 12


def test_goblin_class_loaded(data):
    cls = data.classes["goblin"]
    assert cls.source == "carcass_crawler_1"
    assert cls.race_locked == "goblin"
    assert cls.hit_die == "1d6"
    assert cls.max_level == 8
    assert cls.name_level == 8
    assert cls.progression[1].thac0 == 19
    assert cls.progression[8].thac0 == 14


def test_hephaestan_class_loaded(data):
    cls = data.classes["hephaestan"]
    assert cls.source == "carcass_crawler_1"
    assert cls.race_locked == "hephaestan"
    assert {a.value for a in cls.prime_requisites} == {"INT", "WIS"}
    assert cls.hit_die == "1d6"
    assert cls.max_level == 10
    assert cls.name_level == 9
    assert cls.hp_after_name_level == 2
    assert cls.progression[1].thac0 == 19
    assert cls.progression[10].thac0 == 12


# ── Carcass Crawler 1: races ──────────────────────────────────────────────────

def test_gargantua_race_loaded(data):
    r = data.races["gargantua"]
    assert r.source == "carcass_crawler_1"
    assert r.ability_requirements[Ability.CON] == 9
    assert r.ability_requirements[Ability.STR] == 9
    assert r.ability_modifiers[Ability.INT] == -1
    assert r.ability_modifiers[Ability.STR] == 1
    assert "fighter" in r.allowed_classes
    assert r.class_level_caps["fighter"] == 10
    assert r.class_level_caps["assassin"] == 6


def test_goblin_race_loaded(data):
    r = data.races["goblin"]
    assert r.source == "carcass_crawler_1"
    assert r.ability_requirements[Ability.DEX] == 9
    assert r.ability_modifiers[Ability.DEX] == 1
    assert r.ability_modifiers[Ability.STR] == -1
    assert r.infravision == 60
    assert "thief" in r.allowed_classes
    assert "magic_user" in r.allowed_classes
    assert r.class_level_caps["thief"] == 8


def test_hephaestan_race_loaded(data):
    r = data.races["hephaestan"]
    assert r.source == "carcass_crawler_1"
    assert r.ability_requirements[Ability.INT] == 9
    assert r.ability_modifiers[Ability.STR] == -1
    assert r.ability_modifiers[Ability.CHA] == 1
    assert "illusionist" in r.allowed_classes
    assert r.class_level_caps["illusionist"] == 11
    assert r.class_level_caps["magic_user"] == 11


def test_cc1_scroll_only_casters_have_caster_type_but_no_slots(data):
    from aose.engine.spells import caster_type_of, memorizable_slots
    from aose.models import ClassEntry

    acolyte = data.classes["acolyte"]
    assert caster_type_of(acolyte, data) == "divine"
    assert memorizable_slots(ClassEntry(class_id="acolyte", level=5), acolyte) == {}

    mage = data.classes["mage"]
    assert caster_type_of(mage, data) == "arcane"
    assert memorizable_slots(ClassEntry(class_id="mage", level=5), mage) == {}


def test_cc1_languages_loaded(data):
    assert "hephaestan" in data.languages.names
    assert "language_of_wolves" in data.languages.names
