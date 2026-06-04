"""Tests for the encumbrance engine and its effect on the sheet.

Three modes: ``none`` ignores everything, ``basic`` reads armour type only,
``detailed`` walks the full OSE Advanced load table.
"""
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import save_character, save_settings
from aose.data.loader import GameData
from aose.engine.encumbrance import (
    armor_movement_class,
    carried_weight_cn,
    effective_movement,
)
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import build_sheet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _spec(race_id="human", inventory=None, equipped=None, equipped_weapons=None,
          encumbrance="basic"):
    return CharacterSpec(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id=race_id,
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        inventory=list(inventory or []),
        equipped=dict(equipped or {}),
        equipped_weapons=list(equipped_weapons or []),
        ruleset=RuleSet(encumbrance=encumbrance),
    )


# â”€â”€ carried_weight_cn â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_empty_character_weighs_zero(data):
    assert carried_weight_cn(_spec(), data) == 0


def test_weight_sums_inventory(data):
    # Torch is 20 cn, Long Sword is 60 cn
    spec = _spec(inventory=["torch", "torch", "sword"])
    assert carried_weight_cn(spec, data) == 20 + 20 + 60


def test_weight_does_not_double_count_equipped_armor(data):
    """Equipped items live inside ``inventory`` already, so weight is counted
    once via the inventory list.  Equipping a piece of armour you already
    own must not add its weight a second time."""
    spec = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"})
    assert carried_weight_cn(spec, data) == 400


def test_weight_does_not_double_count_equipped_weapons(data):
    """Same rule as for armour: an equipped weapon is just a flag on an
    inventory item, not a separate copy."""
    spec = _spec(inventory=["sword"], equipped_weapons=["sword"])
    assert carried_weight_cn(spec, data) == 60


def test_unknown_item_id_contributes_zero(data):
    spec = _spec(inventory=["ghost_item"])
    assert carried_weight_cn(spec, data) == 0


# â”€â”€ armor_movement_class â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_no_armor_is_none(data):
    assert armor_movement_class(_spec(), data) == "none"


def test_leather_armor_class(data):
    spec = _spec(inventory=["leather_armor"], equipped={"armor": "leather_armor"})
    assert armor_movement_class(spec, data) == "leather"


def test_metal_armor_class(data):
    spec = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"})
    assert armor_movement_class(spec, data) == "metal"


def test_shield_alone_does_not_count_as_armor(data):
    spec = _spec(inventory=["shield"], equipped={"shield": "shield"})
    assert armor_movement_class(spec, data) == "none"


# â”€â”€ effective_movement: NONE mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_none_mode_ignores_armor_and_weight(data):
    spec = _spec(
        race_id="human",
        inventory=["chain_mail"] + ["sword"] * 30,  # very heavy
        equipped={"armor": "chain_mail"},
        encumbrance="none",
    )
    # Human base 120, should remain 120 in none mode
    assert effective_movement(spec, data) == 120


# â”€â”€ effective_movement: BASIC mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_basic_mode_unarmored_human_unchanged(data):
    spec = _spec(race_id="human", encumbrance="basic")
    assert effective_movement(spec, data) == 120


def test_basic_mode_leather_drops_to_90ft(data):
    """OSE Advanced table: leather + light load = 90' for a 120'-base human."""
    spec = _spec(
        race_id="human", inventory=["leather_armor"],
        equipped={"armor": "leather_armor"},
        encumbrance="basic",
    )
    assert effective_movement(spec, data) == 90


def test_basic_mode_metal_drops_to_60ft(data):
    """OSE Advanced table: metal + light load = 60' for a 120'-base human."""
    spec = _spec(
        race_id="human", inventory=["chain_mail"],
        equipped={"armor": "chain_mail"},
        encumbrance="basic",
    )
    assert effective_movement(spec, data) == 60


def test_basic_mode_dwarf_in_chain_scales_to_60(data):
    """OSE Advanced dwarves have base_movement 120' (same as humans).
    Dwarf in chain mail â†’ metal-armour cell â†’ 60'."""
    spec = _spec(
        race_id="dwarf", inventory=["chain_mail"],
        equipped={"armor": "chain_mail"},
        encumbrance="basic",
    )
    assert effective_movement(spec, data) == 60


def test_basic_mode_ignores_inventory_weight(data):
    """Basic mode doesn't track item-by-item â€” overloading torches is free."""
    spec = _spec(
        race_id="human",
        inventory=["torch"] * 200,  # 4000 cn
        encumbrance="basic",
    )
    assert effective_movement(spec, data) == 120


# â”€â”€ effective_movement: DETAILED mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_detailed_light_load_no_penalty(data):
    # 5 torches = 100 cn â€” well under 400
    spec = _spec(
        race_id="human",
        inventory=["torch"] * 5,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 120


def test_detailed_load_band_1_drops_30(data):
    # Push weight into the 401-800 band
    # 8 long swords = 480 cn
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 8,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 90


def test_detailed_load_band_2_drops_60(data):
    # 15 long swords = 900 cn â†’ 801-1200 band
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 15,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 60


def test_detailed_load_band_3_drops_90(data):
    # 25 long swords = 1500 cn â†’ 1201-1600 band
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 25,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 30


def test_detailed_over_encumbered_returns_zero(data):
    # 30 long swords = 1800 cn â†’ over the 1600 cap
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 30,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 0


def test_detailed_armor_and_load_via_table_lookup(data):
    """Armour and load combine through the OSE Advanced table â€” armour
    picks the column, load picks the row.  Chain mail + 500 cn total â†’
    metal column, 401-800 band â†’ 45'."""
    # chain mail = 400 cn; 5 torches = 100 cn; total = 500 cn â†’ band 1
    # (401-800).  metal Ã— band 1 = 45'.
    spec = _spec(
        race_id="human",
        inventory=["chain_mail"] + ["torch"] * 5,
        equipped={"armor": "chain_mail"},
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 45


# â”€â”€ Sheet integration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_sheet_shows_unencumbered_only_when_encumbered(data):
    """If movement_base != movement_unencumbered, that fact is exposed."""
    spec = _spec(
        race_id="human", inventory=["chain_mail"],
        equipped={"armor": "chain_mail"},
        encumbrance="basic",
    )
    sheet = build_sheet(spec, data)
    assert sheet.movement_base == 60
    assert sheet.movement_unencumbered == 120
    assert sheet.armor_movement_class == "metal"


def test_sheet_carried_weight_none_in_none_mode(data):
    spec = _spec(encumbrance="none", inventory=["torch", "torch"])
    sheet = build_sheet(spec, data)
    assert sheet.carried_weight_cn is None


def test_sheet_carried_weight_reported_in_basic_mode(data):
    spec = _spec(encumbrance="basic", inventory=["torch", "torch"])
    sheet = build_sheet(spec, data)
    # weights are tracked even in basic mode for display, just not enforced
    assert sheet.carried_weight_cn == 40


def test_sheet_encounter_move_follows_exploration_third(data):
    spec = _spec(race_id="dwarf", encumbrance="basic")
    sheet = build_sheet(spec, data)
    assert sheet.movement_encounter == sheet.movement_base // 3


# â”€â”€ HTTP sheet rendering â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _make_client(tmp_path, ruleset):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset)
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir,
        drafts_dir=drafts_dir, examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    return client


def test_sheet_html_renders_carried_weight_in_basic(tmp_path):
    client = _make_client(tmp_path, RuleSet(encumbrance="basic"))
    spec = _spec(encumbrance="basic", inventory=["torch", "torch"])
    save_character("test", spec, client._characters_dir)
    r = client.get("/character/test")
    assert "40 cn" in r.text


def test_sheet_html_hides_carried_weight_in_none(tmp_path):
    """The Movement section's Carried-weight stat row is suppressed in
    ``none`` mode.  The inventory partial may still mention "Carried" as an
    inventory section, so check for the specific Movement-section markup."""
    client = _make_client(tmp_path, RuleSet(encumbrance="none"))
    spec = _spec(encumbrance="none", inventory=["torch", "torch"])
    save_character("test", spec, client._characters_dir)
    r = client.get("/character/test")
    assert "<span>Carried</span>" not in r.text


def test_sheet_html_warns_when_over_encumbered(tmp_path):
    client = _make_client(tmp_path, RuleSet(encumbrance="detailed"))
    spec = _spec(encumbrance="detailed", inventory=["sword"] * 30)
    save_character("test", spec, client._characters_dir)
    r = client.get("/character/test")
    assert "Over-encumbered" in r.text


# ---------------------------------------------------------------------------
# Task 5: treasure_weight_cn
# ---------------------------------------------------------------------------
from aose.engine.encumbrance import treasure_weight_cn
from aose.models import GemStack, JewelleryPiece, MagicItemInstance, SpellSource


def test_treasure_weight_coins_gems_jewellery(data):
    spec = _spec()
    spec.gold = 50
    spec.silver = 30
    spec.gems = [GemStack(instance_id="g", value=100, count=5)]
    spec.jewellery = [JewelleryPiece(instance_id="j", value=900)]
    assert treasure_weight_cn(spec, data) == 50 + 30 + 5 + 10


def test_treasure_weight_potion_and_scroll(data):
    spec = _spec()
    spec.magic_items = [MagicItemInstance(instance_id="m", catalog_id="potion_clairvoyance")]
    spec.spell_sources = [SpellSource(instance_id="s", kind="scroll", caster_type="arcane", entries=[])]
    assert treasure_weight_cn(spec, data) == 10 + 1
