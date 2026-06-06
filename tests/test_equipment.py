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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Engine helpers (pure functions, no FastAPI)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_roll_starting_gold_in_range():
    rng = random.Random(0)
    for _ in range(50):
        v = roll_starting_gold(rng)
        assert 30 <= v <= 180
        assert v % 10 == 0


def test_shop_categories_is_data_driven(data):
    cats = shop_categories(data)
    ids = {c.id for c in cats}
    # Categories are read from items' category field â€" adding a new YAML
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
    rows = inventory_rows(["torch", "torch", "sword", "torch"], data)
    by_id = {r.id: r for r in rows}
    assert by_id["torch"].count == 3
    assert by_id["sword"].count == 1


def test_inventory_rows_carry_sell_value(data):
    rows = inventory_rows(["sword"], data)
    sword = rows[0]
    assert sword.cost_gp == 10
    assert sword.sell_gp == 5  # 50% of 10


def test_inventory_rows_handles_stale_id(data):
    """If an item id no longer exists in the data, surface it with cost=0."""
    rows = inventory_rows(["a_ghost_item"], data)
    assert rows[0].name == "a_ghost_item"
    assert rows[0].cost_gp == 0


# â"€â"€ buy â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_buy_appends_and_deducts(data):
    inv, gold = buy([], 50, "sword", data)
    assert inv == ["sword"]
    assert gold == 40  # 50 - 10


def test_buy_respects_existing_inventory(data):
    inv, gold = buy(["rope_50ft"], 5, "rope_50ft", data)
    assert inv == ["rope_50ft", "rope_50ft"]
    assert gold == 4


def test_buy_torch_grants_a_stack_of_six(data):
    inv, gold = buy([], 5, "torch", data)
    assert inv == ["torch"] * 6
    assert gold == 4  # one 1 gp charge for the stack


def test_buy_rejects_unaffordable(data):
    with pytest.raises(InsufficientGold):
        buy([], 5, "plate_mail", data)


def test_buy_rejects_unknown_item(data):
    with pytest.raises(UnknownItem):
        buy([], 100, "imaginary_thing", data)


# â"€â"€ remove â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_remove_drop_no_refund(data):
    inv, gold, _eq, _wp = remove(["sword"], 0, "sword", "drop", data)
    assert inv == []
    assert gold == 0


def test_remove_sell_half_refund(data):
    inv, gold, _eq, _wp = remove(["sword"], 0, "sword", "sell", data)
    assert inv == []
    assert gold == 5


def test_remove_refund_full(data):
    inv, gold, _eq, _wp = remove(["sword"], 0, "sword", "refund", data)
    assert inv == []
    assert gold == 10


def test_remove_only_one_instance(data):
    inv, gold, _eq, _wp = remove(["torch", "torch", "torch"], 0, "torch", "drop", data)
    assert inv == ["torch", "torch"]


def test_remove_rejects_missing(data):
    with pytest.raises(ValueError, match="not in inventory"):
        remove([], 0, "torch", "drop", data)


def test_remove_rejects_bad_mode(data):
    with pytest.raises(ValueError, match="Unknown remove mode"):
        remove(["torch"], 0, "torch", "burn", data)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Wizard equipment step
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
        "strict_mode": "on",
    })
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    return draft_id


def test_equipment_accessible_after_identity(client):
    """Equipment is reachable once identity (name + alignment) is complete."""
    draft_id = _walk_to_equipment(client)
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200


def test_equipment_get_does_not_auto_roll_gold(client):
    draft_id = _walk_to_equipment(client)
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200
    draft = load_draft(draft_id, client._drafts_dir)
    assert "gold" not in draft
    assert f"/wizard/{draft_id}/equipment/roll-gold" in r.text


def test_roll_gold_route_sets_and_locks_gold_in_strict(client):
    draft_id = _walk_to_equipment(client)
    r = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert 30 <= draft["gold"] <= 180 and draft["gold"] % 10 == 0
    assert draft["gold_locked"] is True
    # Strict default: a second roll is rejected.
    r2 = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r2.status_code == 400


def test_buy_locks_starting_gold_roll(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    # Force enough gold to buy a torch (1 gp)
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 50
    save_draft(draft_id, draft, client._drafts_dir)

    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "rope_50ft"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["gold_locked"] is True
    assert draft["gold"] == 49
    assert draft["inventory"] == ["rope_50ft"]


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
    # Buy three ropes (1 gp each, bundle_count 1)
    for _ in range(3):
        client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "rope_50ft"})

    # Drop one (no refund)
    r = client.post(f"/wizard/{draft_id}/equipment/remove",
                    data={"item_id": "rope_50ft", "mode": "drop"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"].count("rope_50ft") == 2
    gold_after_drop = draft["gold"]

    # Sell next (half of 1 gp floors to 0)
    client.post(f"/wizard/{draft_id}/equipment/remove",
                data={"item_id": "rope_50ft", "mode": "sell"})
    # Refund the last (full price, bundle of 1)
    client.post(f"/wizard/{draft_id}/equipment/remove",
                data={"item_id": "rope_50ft", "mode": "refund"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"].count("rope_50ft") == 0
    # 0 (drop) + 0 (sell floor) + 1 (refund) = +1 from drop point
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
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "sword"})
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "chain_mail"})
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert set(spec.inventory) == {"sword", "chain_mail"}
    # 200 - 10 (long sword) - 40 (chain mail) = 150
    assert spec.gold == 150


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Sheet-side equipment management
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
    assert "Sword" in r.text


def test_sheet_buy_deducts_gold_and_adds_inventory(client):
    _seed_character(client, gold=50)
    r = client.post("/character/test/equipment/buy", data={"item_id": "sword"})
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 40
    assert spec.inventory == ["sword"]


def test_sheet_buy_rejects_when_short(client):
    _seed_character(client, gold=5)
    r = client.post("/character/test/equipment/buy", data={"item_id": "plate_mail"})
    assert r.status_code == 400


def test_sheet_remove_modes(client):
    _seed_character(client, gold=0, inventory=["sword"])
    # Refund returns full price
    r = client.post("/character/test/equipment/remove",
                    data={"item_id": "sword", "mode": "refund"})
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


# â"€â"€ Add (free) button â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_sheet_add_route_grants_item_without_spending_gold(client):
    _seed_character(client, gold=5)
    r = client.post("/character/test/equipment/add", data={"item_id": "sword"})
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.inventory == ["sword"]
    assert spec.gold == 5  # unchanged


def test_sheet_add_rejects_unknown_item(client):
    _seed_character(client, gold=100)
    r = client.post("/character/test/equipment/add", data={"item_id": "imaginary"})
    assert r.status_code == 400


def test_sheet_renders_add_button_alongside_buy(client):
    _seed_character(client, gold=50)
    r = client.get("/character/test")
    assert 'action="/character/test/equipment/add"' in r.text
    # The add button appears (lowercase, link-style) even when the user can't afford Buy
    assert ">add</button>" in r.text


def test_wizard_add_route_grants_item_without_spending_gold(client):
    draft_id = _walk_to_equipment(client)
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")  # roll gold first
    before_gold = load_draft(draft_id, client._drafts_dir)["gold"]
    r = client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"] == ["torch"]
    assert draft["gold"] == before_gold  # Add is free


# â"€â"€ Shop search box â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_sheet_shop_has_search_input(client):
    _seed_character(client, gold=50)
    r = client.get("/character/test")
    assert 'id="shop-search"' in r.text


def test_sheet_shop_rows_carry_search_metadata(client):
    """Each shop row needs data-shop-name so the client-side filter works."""
    _seed_character(client, gold=50)
    r = client.get("/character/test")
    # weapons.yaml has Sword → row should expose 'sword' as name
    assert 'data-shop-name="sword"' in r.text


# â"€â"€ Gold-grant form on the sheet â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def test_sheet_grant_gold_form_present(client):
    _seed_character(client, gold=10)
    r = client.get("/character/test")
    assert 'action="/character/test/gold"' in r.text


def test_grant_gold_adds(client):
    _seed_character(client, gold=10)
    r = client.post("/character/test/gold", data={"amount": "50"})
    assert r.status_code == 303
    assert r.headers["location"] == "/character/test"
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 60


def test_grant_gold_negative_clamps_at_zero(client):
    _seed_character(client, gold=5)
    client.post("/character/test/gold", data={"amount": "-9999"})
    spec = load_character("test", client._characters_dir)
    assert spec.gold == 0


def test_grant_gold_missing_character_404s(client):
    r = client.post("/character/nobody/gold", data={"amount": "100"})
    assert r.status_code == 404


def test_shop_categories_filters_by_source():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.engine.shop import shop_categories
    from aose.models import RuleSet

    data = GameData.load(Path(__file__).parent.parent / "data")
    rs = RuleSet(disabled_sources=["ose_advanced_fantasy"])
    all_ids = {i.id for cat in shop_categories(data) for i in cat.items}
    filtered_ids = {i.id for cat in shop_categories(data, rs) for i in cat.items}
    # A known Advanced magic item drops out; a mundane Classic item stays.
    assert "luckstone" in all_ids
    assert "luckstone" not in filtered_ids
    assert "backpack" in filtered_ids  # mundane gear is Classic
