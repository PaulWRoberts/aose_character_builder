"""Tests for the equipment shop: gold rolls, buy/remove, wizard step,
sheet integration."""
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_character, save_draft, save_settings
from aose.data.loader import GameData
from aose.engine.shop import (
    InsufficientGold,
    UnknownItem,
    buy,
    inventory_rows,
    remove,
    roll_starting_gold,
    shop_categories,
)
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    client._settings_path = settings_path
    return client


@pytest.fixture
def client(tmp_path):
    return _make_client(tmp_path)


# ════════════════════════════════════════════════════════════════════════════
# Engine helpers (pure functions, no FastAPI)
# ════════════════════════════════════════════════════════════════════════════

def test_roll_starting_gold_in_range():
    rng = random.Random(0)
    for _ in range(50):
        v = roll_starting_gold(rng)
        assert 30 <= v <= 180
        assert v % 10 == 0


def test_shop_categories_is_data_driven(data):
    cats = shop_categories(data)
    ids = {c.id for c in cats}
    # Categories are read from items' category field — adding a new YAML
    # category should appear here automatically.
    assert "weapons" in ids
    assert "armor" in ids
    assert "adventuring_gear" in ids


def test_shop_categories_sorted_alphabetically(data):
    cats = shop_categories(data)
    ids = [c.id for c in cats]
    assert ids == sorted(ids)


def test_shop_items_sorted_by_cost_within_category(data):
    cats = {c.id: c for c in shop_categories(data)}
    weapons = cats["weapons"].items
    costs = [w.cost_gp for w in weapons]
    assert costs == sorted(costs)


def test_inventory_rows_groups_duplicates(data):
    rows = inventory_rows(["torch", "torch", "long_sword", "torch"], data)
    by_id = {r.id: r for r in rows}
    assert by_id["torch"].count == 3
    assert by_id["long_sword"].count == 1


def test_inventory_rows_carry_sell_value(data):
    rows = inventory_rows(["long_sword"], data)
    sword = rows[0]
    assert sword.cost_gp == 10
    assert sword.sell_gp == 5  # 50% of 10


def test_inventory_rows_handles_stale_id(data):
    """If an item id no longer exists in the data, surface it with cost=0."""
    rows = inventory_rows(["a_ghost_item"], data)
    assert rows[0].name == "a_ghost_item"
    assert rows[0].cost_gp == 0


# ── buy ────────────────────────────────────────────────────────────────────

def test_buy_appends_and_deducts(data):
    inv, gold = buy([], 50, "long_sword", data)
    assert inv == ["long_sword"]
    assert gold == 40  # 50 - 10


def test_buy_respects_existing_inventory(data):
    inv, gold = buy(["torch"], 5, "torch", data)
    assert inv == ["torch", "torch"]
    assert gold == 4


def test_buy_rejects_unaffordable(data):
    with pytest.raises(InsufficientGold):
        buy([], 5, "plate_mail", data)


def test_buy_rejects_unknown_item(data):
    with pytest.raises(UnknownItem):
        buy([], 100, "imaginary_thing", data)


# ── remove ────────────────────────────────────────────────────────────────

def test_remove_drop_no_refund(data):
    inv, gold = remove(["long_sword"], 0, "long_sword", "drop", data)
    assert inv == []
    assert gold == 0


def test_remove_sell_half_refund(data):
    inv, gold = remove(["long_sword"], 0, "long_sword", "sell", data)
    assert inv == []
    assert gold == 5


def test_remove_refund_full(data):
    inv, gold = remove(["long_sword"], 0, "long_sword", "refund", data)
    assert inv == []
    assert gold == 10


def test_remove_only_one_instance(data):
    inv, gold = remove(["torch", "torch", "torch"], 0, "torch", "drop", data)
    assert inv == ["torch", "torch"]


def test_remove_rejects_missing(data):
    with pytest.raises(ValueError, match="not in inventory"):
        remove([], 0, "torch", "drop", data)


def test_remove_rejects_bad_mode(data):
    with pytest.raises(ValueError, match="Unknown remove mode"):
        remove(["torch"], 0, "torch", "burn", data)


# ════════════════════════════════════════════════════════════════════════════
# Wizard equipment step
# ════════════════════════════════════════════════════════════════════════════

def _walk_to_equipment(client):
    """Walk a draft up through the HP step so the next step is equipment."""
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    # Skip past rules using defaults
    client.post(f"/wizard/{draft_id}/rules", data={
        "ability_roll_method": "3d6_in_order", "encumbrance": "basic",
        "separate_race_class": "on",
        "demihuman_level_limits": "on",
        "demihuman_class_restrictions": "on",
    })
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Thorin"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    return draft_id


def test_hp_post_redirects_to_equipment(client):
    """Confirms the new step order — HP now flows to /equipment, not /review."""
    draft_id = _walk_to_equipment(client)
    # The above already POSTed /hp; the draft is now sitting on equipment
    draft = load_draft(draft_id, client._drafts_dir)
    # Visiting GET /equipment should land on equipment (no gate bounce)
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200


def test_equipment_get_seeds_starting_gold(client):
    draft_id = _walk_to_equipment(client)
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200
    draft = load_draft(draft_id, client._drafts_dir)
    assert 30 <= draft["gold"] <= 180
    assert draft["gold"] % 10 == 0
    assert draft.get("gold_locked") is False


def test_equipment_reroll_works_before_first_purchase(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    before = load_draft(draft_id, client._drafts_dir)["gold"]
    for _ in range(10):
        client.post(f"/wizard/{draft_id}/equipment/reroll-gold")
        after = load_draft(draft_id, client._drafts_dir)["gold"]
        if after != before:
            return
    pytest.fail("Gold reroll never changed value across 10 tries")


def test_buy_locks_starting_gold_roll(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    # Force enough gold to buy a torch (1 gp)
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 50
    save_draft(draft_id, draft, client._drafts_dir)

    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "torch"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["gold_locked"] is True
    assert draft["gold"] == 49
    assert draft["inventory"] == ["torch"]


def test_reroll_after_lock_is_rejected(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 50
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "torch"})
    r = client.post(f"/wizard/{draft_id}/equipment/reroll-gold")
    assert r.status_code == 400


def test_buy_rejects_when_short(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 5
    save_draft(draft_id, draft, client._drafts_dir)
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "plate_mail"})
    assert r.status_code == 400


def test_remove_modes_via_wizard(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 100
    save_draft(draft_id, draft, client._drafts_dir)
    # Buy three torches
    for _ in range(3):
        client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "torch"})

    # Drop one (no refund)
    r = client.post(f"/wizard/{draft_id}/equipment/remove",
                    data={"item_id": "torch", "mode": "drop"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"].count("torch") == 2
    gold_after_drop = draft["gold"]

    # Sell next (half refund — torch costs 1, sell value 0 due to floor)
    client.post(f"/wizard/{draft_id}/equipment/remove",
                data={"item_id": "torch", "mode": "sell"})
    # And refund the last (full price)
    client.post(f"/wizard/{draft_id}/equipment/remove",
                data={"item_id": "torch", "mode": "refund"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"].count("torch") == 0
    # 0 (drop) + 0 (sell, torch half=0) + 1 (refund) = +1 from drop point
    assert draft["gold"] == gold_after_drop + 0 + 1


def test_equipment_step_continues_to_review(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/review")


def test_inventory_persists_to_saved_character(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 200
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "long_sword"})
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "chain_mail"})
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert set(spec.inventory) == {"long_sword", "chain_mail"}
    # 200 - 10 (long sword) - 40 (chain mail) = 150
    assert spec.gold == 150


# ════════════════════════════════════════════════════════════════════════════
# Sheet-side equipment management
# ════════════════════════════════════════════════════════════════════════════

def _seed_character(client, gold=100, inventory=None) -> str:
    spec = CharacterSpec(
        name="Thorin",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
        gold=gold,
        inventory=list(inventory or []),
        ruleset=RuleSet(),
    )
    save_character("test", spec, client._characters_dir)
    return "test"


def test_sheet_shows_gold_and_shop(client):
    _seed_character(client, gold=75)
    r = client.get("/character/test")
    assert r.status_code == 200
    assert "75 gp" in r.text
    assert "Shop" in r.text
    assert "Long Sword" in r.text


def test_sheet_buy_deducts_gold_and_adds_inventory(client):
    _seed_character(client, gold=50)
    r = client.post("/character/test/equipment/buy", data={"item_id": "long_sword"})
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 40
    assert spec.inventory == ["long_sword"]


def test_sheet_buy_rejects_when_short(client):
    _seed_character(client, gold=5)
    r = client.post("/character/test/equipment/buy", data={"item_id": "plate_mail"})
    assert r.status_code == 400


def test_sheet_remove_modes(client):
    _seed_character(client, gold=0, inventory=["long_sword"])
    # Refund returns full price
    r = client.post("/character/test/equipment/remove",
                    data={"item_id": "long_sword", "mode": "refund"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 10
    assert spec.inventory == []


def test_sheet_does_not_offer_reroll_button(client):
    """Re-roll starting gold is wizard-only.  Sheet shows the locked notice."""
    _seed_character(client, gold=50)
    r = client.get("/character/test")
    # The reroll endpoint should not appear in any form on the sheet
    assert 'action="/character/test/equipment/reroll-gold"' not in r.text
