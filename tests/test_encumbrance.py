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
from aose.models import CharacterSpec, ClassEntry, CoinStack, RuleSet
from aose.sheet.view import build_sheet
from aose.web.app import create_app
from tests._itemhelp import coerce_equipment

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _spec(race_id="human", inventory=None, equipped=None, encumbrance="basic", **kw):
    kwargs = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id=race_id,
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(encumbrance=encumbrance),
    )
    kwargs.update(kw)
    if inventory is not None:
        kwargs["inventory"] = list(inventory)
    if equipped is not None:
        kwargs["equipped"] = dict(equipped)
    coerce_equipment(kwargs)
    return CharacterSpec(**kwargs)


# â"€â"€ carried_weight_cn â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_empty_character_weighs_zero(data):
    assert carried_weight_cn(_spec(), data) == 0


def test_weight_sums_inventory(data):
    # Torches are AdventuringGear -> flat 80; sword is a Weapon -> 60 cn
    spec = _spec(inventory=["torch", "torch", "sword"])
    assert carried_weight_cn(spec, data) == 80 + 60


def test_weight_does_not_double_count_equipped_armor(data):
    """Equipped items live inside ``inventory`` already, so weight is counted
    once via the inventory list.  Equipping a piece of armour you already
    own must not add its weight a second time."""
    spec = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"})
    assert carried_weight_cn(spec, data) == 400


def test_weight_does_not_double_count_equipped_weapons(data):
    """Same rule as for armour: an equipped weapon is just a flag on an
    inventory item, not a separate copy."""
    spec = _spec(inventory=["sword"], equipped={"main_hand": "sword"})
    assert carried_weight_cn(spec, data) == 60


def test_unknown_item_id_contributes_zero(data):
    spec = _spec(inventory=["ghost_item"])
    assert carried_weight_cn(spec, data) == 0


# â"€â"€ armor_movement_class â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_no_armor_is_none(data):
    assert armor_movement_class(_spec(), data) == "none"


def test_leather_armor_class(data):
    spec = _spec(inventory=["leather_armor"], equipped={"armor": "leather_armor"})
    assert armor_movement_class(spec, data) == "leather"


def test_metal_armor_class(data):
    spec = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"})
    assert armor_movement_class(spec, data) == "metal"


def test_shield_alone_does_not_count_as_armor(data):
    spec = _spec(inventory=["shield"], equipped={"off_hand": "shield"})
    assert armor_movement_class(spec, data) == "none"


# â"€â"€ effective_movement: NONE mode â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_none_mode_ignores_armor_and_weight(data):
    spec = _spec(
        race_id="human",
        inventory=["chain_mail"] + ["sword"] * 30,  # very heavy
        equipped={"armor": "chain_mail"},
        encumbrance="none",
    )
    # Human base 120, should remain 120 in none mode
    assert effective_movement(spec, data) == 120


# â"€â"€ effective_movement: BASIC mode â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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
    Dwarf in chain mail â†' metal-armour cell â†' 60'."""
    spec = _spec(
        race_id="dwarf", inventory=["chain_mail"],
        equipped={"armor": "chain_mail"},
        encumbrance="basic",
    )
    assert effective_movement(spec, data) == 60


def test_basic_mode_ignores_inventory_weight(data):
    """Basic mode doesn't track item-by-item â€" overloading torches is free."""
    spec = _spec(
        race_id="human",
        inventory=["torch"] * 200,  # 4000 cn
        encumbrance="basic",
    )
    assert effective_movement(spec, data) == 120


# â"€â"€ effective_movement: DETAILED mode â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_detailed_light_load_no_penalty(data):
    # 5 torches = 100 cn â€" well under 400
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
    # 15 swords = 900 cn -> band 3 (801-1600) -> 30' under new bands
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 15,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 30


def test_detailed_load_band_3_drops_90(data):
    # 25 long swords = 1500 cn â†' 1201-1600 band
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 25,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 30


def test_detailed_over_encumbered_returns_zero(data):
    # 30 long swords = 1800 cn â†' over the 1600 cap
    spec = _spec(
        race_id="human",
        inventory=["sword"] * 30,
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 0


def test_detailed_armor_and_load_via_single_axis(data):
    # Detailed mode is single-axis by total weight (no armour column).
    # Chain mail (400 cn) + 5 torches (flat-80 gear) = 480 cn -> band 1 -> 90'.
    spec = _spec(
        race_id="human",
        inventory=["chain_mail"] + ["torch"] * 5,
        equipped={"armor": "chain_mail"},
        encumbrance="detailed",
    )
    assert effective_movement(spec, data) == 90


# â"€â"€ Sheet integration â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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
    # torches are AdventuringGear -> flat 80 cn (book RAW) for all carried gear
    assert sheet.carried_weight_cn == 80


def test_sheet_encounter_move_follows_exploration_third(data):
    spec = _spec(race_id="dwarf", encumbrance="basic")
    sheet = build_sheet(spec, data)
    assert sheet.movement_encounter == sheet.movement_base // 3


# â"€â"€ HTTP sheet rendering â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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
    # New zine sheet shows "carried / max_load cn" in the inventory bar.
    assert "80 / 1600 cn" in r.text


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
    spec.coins = [CoinStack(denom="gp", count=50), CoinStack(denom="sp", count=30)]
    spec.gems = [GemStack(instance_id="g", value=100, count=5)]
    spec.jewellery = [JewelleryPiece(instance_id="j", value=900)]
    assert treasure_weight_cn(spec, data) == 50 + 30 + 5 + 10


def test_treasure_weight_potion_and_scroll(data):
    spec = _spec()
    spec.magic_items = [MagicItemInstance(instance_id="m", catalog_id="potion_clairvoyance")]
    spec.spell_sources = [SpellSource(instance_id="s", kind="scroll", caster_type="arcane", entries=[])]
    assert treasure_weight_cn(spec, data) == 10 + 1


# ---------------------------------------------------------------------------
# Task 6: equipment_weight_cn
# ---------------------------------------------------------------------------
from aose.engine.encumbrance import equipment_weight_cn


def test_equipment_weapon_armour_by_weight(data):
    # Long Sword 60 cn + Chain Mail 400 cn; no adventuring gear -> no flat 80
    spec = _spec(inventory=["sword", "chain_mail"], equipped={"armor": "chain_mail"})
    assert equipment_weight_cn(spec, data) == 60 + 400


def test_equipment_flat_80_for_adventuring_gear(data):
    # torch is AdventuringGear (item_type "gear") -> flat 80, its own 20 cn ignored
    spec = _spec(inventory=["sword", "torch", "torch"])
    assert equipment_weight_cn(spec, data) == 60 + 80


def test_equipment_no_gear_no_flat_80(data):
    assert equipment_weight_cn(_spec(inventory=["sword"]), data) == 60


def test_non_treasure_magic_item_does_not_trigger_flat_80(data):
    # ring_control_animals is magic_rings — NOT adventuring gear
    spec = _spec()
    spec.magic_items = [MagicItemInstance(instance_id="m", catalog_id="ring_control_animals")]
    assert equipment_weight_cn(spec, data) == 0


# ---------------------------------------------------------------------------
# Task 7: weight_band, carried_weight_cn, effective_movement (detailed)
# ---------------------------------------------------------------------------

def test_weight_band_thresholds():
    from aose.engine.encumbrance import weight_band
    assert weight_band(0) == 0
    assert weight_band(400) == 0
    assert weight_band(401) == 1
    assert weight_band(600) == 1
    assert weight_band(800) == 2
    assert weight_band(1600) == 3
    assert weight_band(1601) == 4


def test_carried_weight_is_treasure_plus_equipment(data):
    spec = _spec(inventory=["sword"])   # 60 cn equipment, no gear
    spec.coins = [CoinStack(denom="gp", count=100)]   # 100 cn treasure
    assert carried_weight_cn(spec, data) == 160


def test_detailed_movement_bands(data):
    def move(coins):
        s = _spec(encumbrance="detailed")
        s.coins = [CoinStack(denom="cp", count=coins)]
        return effective_movement(s, data)
    assert move(400) == 120
    assert move(600) == 90
    assert move(800) == 60
    assert move(1600) == 30
    assert move(1601) == 0


def test_detailed_includes_armour_weight(data):
    # Chain mail 400 + 1 coin -> band 1 (>400) -> 90'
    s = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"},
              encumbrance="detailed")
    s.coins = [CoinStack(denom="cp", count=1)]
    assert effective_movement(s, data) == 90


# ---------------------------------------------------------------------------
# Task 8: basic-mode movement
# ---------------------------------------------------------------------------

def test_basic_unarmoured(data):
    s = _spec(encumbrance="basic")
    assert effective_movement(s, data) == 120
    s.carrying_treasure = True
    assert effective_movement(s, data) == 90


def test_basic_light_armour(data):
    s = _spec(inventory=["leather_armor"], equipped={"armor": "leather_armor"},
              encumbrance="basic")
    assert effective_movement(s, data) == 90
    s.carrying_treasure = True
    assert effective_movement(s, data) == 60


def test_basic_heavy_armour(data):
    s = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"},
              encumbrance="basic")
    assert effective_movement(s, data) == 60
    s.carrying_treasure = True
    assert effective_movement(s, data) == 30


def test_basic_over_max_load_is_immobile(data):
    s = _spec(encumbrance="basic")
    s.coins = [CoinStack(denom="cp", count=1601)]   # treasure alone exceeds the 1,600 cap
    assert effective_movement(s, data) == 0


# ---------------------------------------------------------------------------
# Task 9: EncumbranceTable shape
# ---------------------------------------------------------------------------
from aose.engine.encumbrance import encumbrance_table


def test_encumbrance_table_none_mode(data):
    assert encumbrance_table(_spec(encumbrance="none"), data) is None


def test_basic_table_shape_and_current(data):
    s = _spec(inventory=["leather_armor"], equipped={"armor": "leather_armor"},
              encumbrance="basic")
    s.carrying_treasure = True
    t = encumbrance_table(s, data)
    assert t.mode == "basic"
    assert t.columns == ["Without Treasure", "Carrying Treasure"]
    assert [r.label for r in t.rows] == ["Unarmoured", "Light armour", "Heavy armour"]
    assert t.current_col == 1
    light = next(r for r in t.rows if r.label == "Light armour")
    assert light.movements == [90, 60]
    assert light.is_current_row is True


def test_detailed_table_shape_and_current(data):
    s = _spec(encumbrance="detailed")
    s.coins = [CoinStack(denom="cp", count=500)]   # band 1 (401-600)
    t = encumbrance_table(s, data)
    assert t.mode == "detailed"
    assert t.columns == ["Movement"]
    assert len(t.rows) == 4
    assert [r.movements[0] for r in t.rows] == [120, 90, 60, 30]
    current = [r for r in t.rows if r.is_current_row]
    assert len(current) == 1 and current[0].movements[0] == 90


# ---------------------------------------------------------------------------
# Task 10: sheet view wiring
# ---------------------------------------------------------------------------
from aose.sheet.view import build_sheet


def test_sheet_exposes_purse_and_treasure(data):
    s = _spec(encumbrance="basic")
    s.coins = [CoinStack(denom="gp", count=5), CoinStack(denom="sp", count=30)]
    s.gems = [GemStack(instance_id="g", value=100, count=2)]
    sheet = build_sheet(s, data)
    assert sheet.coins == {"pp": 0, "gp": 5, "ep": 0, "sp": 30, "cp": 0}
    assert sheet.treasure_value_gp == 8   # 5gp + 30sp(=3gp)
    assert sheet.treasure_weight_cn == 5 + 30 + 2
    assert sheet.carrying_treasure is False
    assert sheet.max_load == 1600


# ── Task 8: location-aware magic/enchanted/ammo weight ───────────────────────

def test_magic_on_a_mule_does_not_count_toward_carried(data):
    from aose.models import AnimalInstance, MagicItemInstance
    from aose.models.storage import StorageLocation
    mule_loc = StorageLocation(kind="animal", id="mule1")
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="mule1", catalog_id="mule")],
        magic_items=[MagicItemInstance(instance_id="m1", catalog_id="rod_lordly_might",
                     location=mule_loc)],
    )
    carried_on_mule = carried_weight_cn(spec, data)
    # Moving the same magic item to carried should increase carried weight.
    spec.magic_items[0].location = StorageLocation(kind="carried")
    assert carried_weight_cn(spec, data) > carried_on_mule


def test_enchanted_on_mule_does_not_count_toward_carried(data):
    from aose.models import AnimalInstance
    from aose.models.character import ItemInstance
    from aose.models.storage import StorageLocation
    mule_loc = StorageLocation(kind="animal", id="mule1")
    spec = CharacterSpec(
        name="X",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="mule1", catalog_id="mule")],
        items=[ItemInstance(instance_id="e1", catalog_id="sword",
                            enchantment_id="generic_plus_1", location=mule_loc)],
    )
    carried_on_mule = carried_weight_cn(spec, data)
    spec.items[0].location = StorageLocation(kind="carried")
    assert carried_weight_cn(spec, data) > carried_on_mule


def test_carried_container_weight_uses_location_load_cn(data):
    from aose.engine import storage
    from aose.engine.encumbrance import equipment_weight_cn
    from aose.models import ContainerInstance, CoinStack
    from aose.models.character import ItemInstance
    from aose.models.storage import StorageLocation
    here = StorageLocation(kind="container", id="c1")
    spec = CharacterSpec(
        name="E", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=StorageLocation(kind="carried"))],
        items=[ItemInstance(instance_id="t_sword", catalog_id="sword", location=here)],
        coins=[CoinStack(denom="gp", count=10, location=here)],
    )
    raw = storage.location_load_cn(spec, here, data)
    cat = data.items["backpack"]
    expected_contribution = cat.weight_cn + int(cat.weight_multiplier * raw)
    assert equipment_weight_cn(spec, data) >= expected_contribution
