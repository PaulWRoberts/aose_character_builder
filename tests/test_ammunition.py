"""Ammunition model + engine tests — updated for unified ItemInstance ammo."""
import uuid
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


# ── Model tests ──────────────────────────────────────────────────────────────

def test_ammunition_parses_minimal():
    from aose.models import Ammunition
    a = Ammunition(id="arrow", name="Arrows", category="ammunition",
                   item_type="ammunition", cost_gp=5)
    assert a.weight_cn == 0          # ammo never weighs in
    assert a.bundle_count == 1
    assert a.groups == []


def test_ammunition_full_fields():
    from aose.models import Ammunition
    a = Ammunition(id="arrow", name="Arrows (quiver of 20)", category="ammunition",
                   item_type="ammunition", cost_gp=5, bundle_count=20,
                   groups=["arrow"], description="A quiver of 20 arrows.")
    assert a.bundle_count == 20 and a.groups == ["arrow"]


def test_ammunition_is_in_item_union():
    from pydantic import TypeAdapter
    from aose.models import Ammunition, Item
    parsed = TypeAdapter(Item).validate_python(
        {"id": "arrow", "name": "Arrows", "category": "ammunition",
         "item_type": "ammunition", "cost_gp": 5, "groups": ["arrow"]})
    assert isinstance(parsed, Ammunition)


def test_weapon_accepts_ammo_defaults_empty():
    from aose.models import Weapon, WeaponDamage
    w = Weapon(id="sword", name="Sword", category="weapons", item_type="weapon",
               cost_gp=10, damage=WeaponDamage())
    assert w.accepts_ammo == []


def test_enchantment_kind_allows_ammunition():
    from aose.models import Enchantment
    e = Enchantment(id="arrows_plus_1", name_template="{base} +1",
                    kind="ammunition", applies_to={"include": ["arrow"]},
                    magic_bonus=1)
    assert e.kind == "ammunition"


def test_spec_has_items_list():
    """CharacterSpec has items: list[ItemInstance] — no separate ammo field."""
    from aose.models import CharacterSpec, ClassEntry, ItemInstance
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law")
    assert spec.items == []
    # Ammo can be added as ItemInstances
    spec.items.append(ItemInstance(instance_id="x", catalog_id="arrow", count=20))
    assert spec.items[0].count == 20


def _ammo(id, groups=()):
    from aose.models import Ammunition
    return Ammunition(id=id, name=id.title(), category="ammunition",
                      item_type="ammunition", cost_gp=1, groups=list(groups))


def _ammo_ench(id, include, exclude=()):
    from aose.models import Enchantment
    return Enchantment(id=id, name_template="{base} +1", kind="ammunition",
                       applies_to={"include": list(include), "exclude": list(exclude)})


def test_ammunition_nature_and_wildcard():
    from aose.engine.enchant import matches, is_compatible
    arrow = _ammo("arrow", groups=["arrow"])
    assert matches(arrow, "any_ammunition")
    assert matches(arrow, "arrow")
    assert is_compatible(arrow, _ammo_ench("arrows_plus_1", ["arrow"]))


def test_silver_arrow_takes_arrow_slaying():
    from aose.engine.enchant import is_compatible
    silver = _ammo("silver_arrow", groups=["arrow"])
    assert is_compatible(silver, _ammo_ench("arrow_slaying", ["arrow"]))


def test_ammo_enchantment_not_compatible_with_weapon():
    from aose.engine.enchant import is_compatible
    from aose.models import Weapon, WeaponDamage
    bow = Weapon(id="short_bow", name="Short Bow", category="weapons",
                 item_type="weapon", cost_gp=25, damage=WeaponDamage(),
                 qualities=[{"missile": [20, 40, 80]}])
    assert not is_compatible(bow, _ammo_ench("arrows_plus_1", ["arrow"]))


def test_resolve_weapon_preserves_accepts_ammo():
    from aose.engine.enchant import resolve_weapon
    from aose.models import Enchantment, Weapon, WeaponDamage
    bow = Weapon(id="short_bow", name="Short Bow", category="weapons",
                 item_type="weapon", cost_gp=25, damage=WeaponDamage(),
                 qualities=[{"missile": [20, 40, 80]}], groups=["bow"], accepts_ammo=["arrow"])
    ench = Enchantment(id="bow_plus_1", name_template="{base} +1", kind="weapon",
                       applies_to={"include": ["bow"]}, magic_bonus=1)
    resolved = resolve_weapon(bow, ench, "iid")
    assert resolved.accepts_ammo == ["arrow"]


import random as _random

from aose.data.loader import GameData
from aose.models import Ammunition, Enchantment, Weapon, WeaponDamage


def _data_with_ammo():
    """In-memory GameData: a bow launcher, arrow + silver arrow bases, two ammo
    enchantments."""
    d = GameData()
    d.items["short_bow"] = Weapon(id="short_bow", name="Short Bow",
        category="weapons", item_type="weapon", cost_gp=25, damage=WeaponDamage(),
        qualities=[{"missile": [20, 40, 80]}], groups=["bow"], accepts_ammo=["arrow"])
    d.items["arrow"] = Ammunition(id="arrow", name="Arrows (quiver of 20)",
        category="ammunition", item_type="ammunition", cost_gp=5, bundle_count=20,
        groups=["arrow"])
    d.items["silver_arrow"] = Ammunition(id="silver_arrow", name="Silver Arrow",
        category="ammunition", item_type="ammunition", cost_gp=5, bundle_count=1,
        groups=["arrow"])
    d.enchantments["arrows_plus_1"] = Enchantment(id="arrows_plus_1",
        name_template="{base} +1", kind="ammunition",
        applies_to={"include": ["arrow"]}, magic_bonus=1)
    return d


def test_accepts():
    from aose.engine.ammo import accepts
    d = _data_with_ammo()
    assert accepts(d.items["short_bow"], d.items["arrow"]) is True


def test_buy_item_creates_ammo_instance():
    """buy_item adds ammo as ItemInstance in spec.items."""
    from aose.engine.shop import buy_item
    from aose.models import CharacterSpec, ClassEntry, CoinStack, ItemInstance
    from aose.models.storage import StorageLocation
    d = _data_with_ammo()
    carried = StorageLocation(kind="carried")
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law",
                         coins=[CoinStack(denom="gp", count=10, location=carried)])
    buy_item(spec, "arrow", d)
    ammo_items = [i for i in spec.items if i.catalog_id == "arrow"]
    assert len(ammo_items) == 1
    assert ammo_items[0].count == 20   # bundle_count=20
    # Second buy combines
    buy_item(spec, "arrow", d)
    ammo_items = [i for i in spec.items if i.catalog_id == "arrow"]
    assert len(ammo_items) == 1 and ammo_items[0].count == 40


def test_buy_item_insufficient_gold():
    from aose.engine.shop import buy_item, InsufficientFunds
    from aose.models import CharacterSpec, ClassEntry, CoinStack
    from aose.models.storage import StorageLocation
    d = _data_with_ammo()
    carried = StorageLocation(kind="carried")
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law",
                         coins=[CoinStack(denom="gp", count=2, location=carried)])
    with pytest.raises((InsufficientFunds, ValueError)):
        buy_item(spec, "arrow", d)


def test_loaded_stack_finds_ammo_instance():
    from aose.engine.ammo import loaded_stack
    from aose.models import CharacterSpec, ClassEntry, ItemInstance
    from aose.models.storage import StorageLocation
    carried = StorageLocation(kind="carried")
    bow_iid = uuid.uuid4().hex
    ammo_iid = uuid.uuid4().hex
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law",
                         items=[
                             ItemInstance(instance_id=bow_iid, catalog_id="short_bow",
                                          equip="main_hand", loaded_ammo_id=ammo_iid),
                             ItemInstance(instance_id=ammo_iid, catalog_id="arrow",
                                          count=20, location=carried),
                         ])
    bow_inst = next(i for i in spec.items if i.instance_id == bow_iid)
    d = _data_with_ammo()
    stack = loaded_stack(bow_inst, spec, d)
    assert stack is not None and stack.instance_id == ammo_iid

    bow_inst.loaded_ammo_id = None
    assert loaded_stack(bow_inst, spec, d) is None


def test_loaded_bonus_from_magic_ammo():
    from aose.engine.ammo import loaded_bonus
    from aose.models import CharacterSpec, ClassEntry, ItemInstance
    from aose.models.storage import StorageLocation
    carried = StorageLocation(kind="carried")
    bow_iid = uuid.uuid4().hex
    ammo_iid = uuid.uuid4().hex
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law",
                         items=[
                             ItemInstance(instance_id=bow_iid, catalog_id="short_bow",
                                          equip="main_hand", loaded_ammo_id=ammo_iid),
                             ItemInstance(instance_id=ammo_iid, catalog_id="arrow",
                                          enchantment_id="arrows_plus_1", count=20,
                                          location=carried),
                         ])
    d = _data_with_ammo()
    bow_inst = next(i for i in spec.items if i.instance_id == bow_iid)
    bonus, cond = loaded_bonus(bow_inst, spec, d)
    assert bonus == 1 and cond is None


def test_is_unloaded_flag():
    from aose.engine.ammo import is_unloaded
    from aose.models import CharacterSpec, ClassEntry, ItemInstance
    d = _data_with_ammo()
    bow_iid = uuid.uuid4().hex
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law",
                         items=[ItemInstance(instance_id=bow_iid, catalog_id="short_bow",
                                             equip="main_hand")])
    bow_inst = next(i for i in spec.items if i.instance_id == bow_iid)
    assert is_unloaded(bow_inst, d.items["short_bow"], spec, d) is True


def _make_bow_spec(loaded=True, ench=True):
    """Build a CharacterSpec with equipped short_bow and carried arrows."""
    from aose.models import CharacterSpec, ClassEntry, ItemInstance
    from aose.models.storage import StorageLocation
    carried = StorageLocation(kind="carried")
    bow_iid = uuid.uuid4().hex
    ammo_iid = "ammo-1"
    eid = "arrows_plus_1" if ench else None
    items = [
        ItemInstance(instance_id=bow_iid, catalog_id="short_bow", equip="main_hand",
                     loaded_ammo_id=(ammo_iid if loaded else None)),
        ItemInstance(instance_id=ammo_iid, catalog_id="arrow",
                     enchantment_id=eid, count=20, location=carried),
    ]
    return CharacterSpec(
        name="B", abilities={"STR": 12, "INT": 10, "WIS": 10,
                             "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="law",
        items=items,
    )


def _real_data():
    return GameData.load(DATA_DIR)


def _bow_profile(profiles):
    return next(p for p in profiles if p.weapon_id == "short_bow")


def test_plus1_arrow_in_plus0_bow_is_plus1():
    from aose.engine.attacks import attack_profiles
    d = _real_data()
    p = _bow_profile(attack_profiles(_make_bow_spec(loaded=True, ench=True), d))
    base = _bow_profile(attack_profiles(_make_bow_spec(loaded=True, ench=False), d))
    assert p.to_hit_ascending == base.to_hit_ascending + 1


def test_unloaded_bow_flagged():
    from aose.engine.attacks import attack_profiles
    d = _real_data()
    p = _bow_profile(attack_profiles(_make_bow_spec(loaded=False), d))
    assert p.unloaded is True
    p2 = _bow_profile(attack_profiles(_make_bow_spec(loaded=True, ench=True), d))
    assert p2.unloaded is False
    assert p2.loaded_ammo_name and "+1" in p2.loaded_ammo_name


def test_profile_adds_ammo_bonus_unit():
    from aose.engine.attacks import attack_profiles
    from aose.models import CharacterSpec, ClassEntry, ItemInstance
    from aose.models.storage import StorageLocation
    d = _data_with_ammo()
    rd = _real_data()
    d.classes = rd.classes
    carried = StorageLocation(kind="carried")
    bow_iid = uuid.uuid4().hex
    ammo_iid = "a1"
    spec = CharacterSpec(
        name="U", abilities={"STR": 10, "INT": 10, "WIS": 10,
                             "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="law",
        items=[
            ItemInstance(instance_id=bow_iid, catalog_id="short_bow", equip="main_hand",
                         loaded_ammo_id=ammo_iid),
            ItemInstance(instance_id=ammo_iid, catalog_id="arrow",
                         enchantment_id="arrows_plus_1", count=5, location=carried),
        ],
    )
    p = _bow_profile(attack_profiles(spec, d))
    assert p.unloaded is False and "+1" in (p.loaded_ammo_name or "")


def test_data_ammunition_loads():
    d = GameData.load(DATA_DIR)
    arrow = d.items["arrow"]
    assert isinstance(arrow, Ammunition)
    assert arrow.bundle_count == 20 and arrow.weight_cn == 0
    assert "arrow" in arrow.groups
    assert d.items["sling_stone"].cost_gp == 0


def test_launchers_accept_ammo():
    d = GameData.load(DATA_DIR)
    assert d.items["short_bow"].accepts_ammo == ["arrow"]
    assert d.items["long_bow"].accepts_ammo == ["arrow"]
    assert d.items["crossbow"].accepts_ammo == ["crossbow_bolt"]
    assert d.items["sling"].accepts_ammo == ["sling_stone"]


def test_ammo_enchantments_load():
    d = GameData.load(DATA_DIR)
    assert d.enchantments["arrows_plus_1"].kind == "ammunition"
    assert d.enchantments["arrows_plus_1"].magic_bonus == 1
    assert d.enchantments["crossbow_bolts_plus_2"].magic_bonus == 2
    assert d.enchantments["sling_bullet_impact"].applies_to.include == ["sling_stone"]


def test_sheet_exposes_ammo_section():
    from aose.sheet.view import build_sheet
    d = GameData.load(DATA_DIR)
    spec = _make_bow_spec(loaded=True, ench=True)
    sheet = build_sheet(spec, d)
    names = [row.name for row in sheet.ammo]
    assert any("+1" in n for n in names)
    assert sheet.ammo[0].count == 20
    # the bow launcher offers the loaded stack as an option;
    # load_options is keyed by weapon instance_id
    bow_iid = next(i.instance_id for i in spec.items if i.catalog_id == "short_bow")
    opts = sheet.ammo_load_options.get(bow_iid, [])
    assert any(o.instance_id == "ammo-1" for o in opts)


# ── Route tests ───────────────────────────────────────────────────────────

from fastapi.testclient import TestClient

from aose.characters import load_character, save_character, save_settings
from aose.web.app import create_app

PROJECT_ROOT = DATA_DIR.parent


def _make_client(tmp_path, ruleset=None):
    from aose.models import RuleSet
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(data_dir=DATA_DIR, characters_dir=characters_dir,
                     drafts_dir=drafts_dir, examples_dir=examples_dir,
                     settings_path=settings_path)
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    client._drafts_dir = drafts_dir
    return client


def _seed(client, **overrides):
    from aose.models import CharacterSpec, ClassEntry, CoinStack, RuleSet
    from aose.models.storage import StorageLocation
    carried = StorageLocation(kind="carried")
    gold = overrides.pop("gold", 0)
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(),
        coins=([CoinStack(denom="gp", count=gold, location=carried)] if gold else []),
    )
    base.update(overrides)
    spec = CharacterSpec(**base)
    save_character("test", spec, client._characters_dir)
    return "test"


def test_buy_then_load_then_adjust(tmp_path):
    from aose.models import Ammunition
    client = _make_client(tmp_path)
    d = GameData.load(DATA_DIR)
    cid = _seed(client, gold=100)
    # Equip a bow via items
    bow_iid = uuid.uuid4().hex
    from aose.models import ItemInstance
    spec = load_character(cid, client._characters_dir)
    spec.items.append(ItemInstance(instance_id=bow_iid, catalog_id="short_bow",
                                   equip="main_hand"))
    save_character(cid, spec, client._characters_dir)

    # Buy a quiver → ammo ItemInstance added
    client.post(f"/character/{cid}/equipment/buy", data={"item_id": "arrow"})
    spec = load_character(cid, client._characters_dir)
    ammo_items = [i for i in spec.items
                  if isinstance(d.items.get(i.catalog_id), Ammunition)]
    assert len(ammo_items) == 1 and ammo_items[0].count == 20
    ammo_iid = ammo_items[0].instance_id

    # Load ammo onto the bow
    r = client.post(f"/character/{cid}/ammo/load",
                    data={"weapon_instance_id": bow_iid, "ammo_instance_id": ammo_iid})
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    bow_inst = next(i for i in spec.items if i.instance_id == bow_iid)
    assert bow_inst.loaded_ammo_id == ammo_iid

    # Adjust count
    r = client.post(f"/character/{cid}/ammo/adjust",
                    data={"instance_id": ammo_iid, "delta": -1})
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    ammo_inst = next(i for i in spec.items if i.instance_id == ammo_iid)
    assert ammo_inst.count == 19


def test_add_magic_ammo_and_remove(tmp_path):
    client = _make_client(tmp_path)
    cid = _seed(client)
    r = client.post(f"/character/{cid}/ammo/add",
                    data={"base_id": "arrow", "enchantment_id": "arrows_plus_1"})
    assert r.status_code == 303
    from aose.models import Ammunition
    d = GameData.load(DATA_DIR)
    spec = load_character(cid, client._characters_dir)
    ammo_items = [i for i in spec.items
                  if isinstance(d.items.get(i.catalog_id), Ammunition)]
    assert len(ammo_items) == 1
    assert ammo_items[0].enchantment_id == "arrows_plus_1"
    ammo_iid = ammo_items[0].instance_id

    r = client.post(f"/character/{cid}/ammo/remove", data={"instance_id": ammo_iid})
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    ammo_items2 = [i for i in spec.items
                   if isinstance(d.items.get(i.catalog_id), Ammunition)]
    assert ammo_items2 == []


# ── Wizard test ───────────────────────────────────────────────────────────

def _wizard_client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    from aose.characters import save_settings
    from aose.models import RuleSet
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet())
    app = create_app(data_dir=DATA_DIR, characters_dir=characters_dir,
                     drafts_dir=drafts_dir, examples_dir=examples_dir,
                     settings_path=settings_path)
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    client._drafts_dir = drafts_dir
    return client


def _drive_wizard_to_equipment(client, tmp_path) -> str:
    from aose.characters.drafts import load_draft, save_draft
    r = client.get("/wizard/new")
    assert r.status_code == 303
    draft_id = r.headers["location"].strip("/").split("/")[1]

    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, tmp_path / "drafts")

    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Archer", "alignment": "law"})
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    return draft_id


def test_wizard_ammo_carries_into_character(tmp_path):
    """Buy a bow + quiver in the wizard, load the ammo, finalize; assert
    the saved CharacterSpec has the ammo ItemInstance and bow has loaded_ammo_id."""
    from aose.characters.drafts import load_draft, save_draft
    from aose.models import Ammunition
    d = GameData.load(DATA_DIR)
    client = _wizard_client(tmp_path)
    draft_id = _drive_wizard_to_equipment(client, tmp_path)

    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["gold"] = 100
    save_draft(draft_id, draft, tmp_path / "drafts")

    # Buy a bow and a quiver
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "short_bow"})
    assert r.status_code == 303
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "arrow"})
    assert r.status_code == 303

    # Get instance IDs from draft
    draft = load_draft(draft_id, tmp_path / "drafts")
    items = draft.get("items", [])
    ammo_raw = [i for i in items if i.get("catalog_id") == "arrow"]
    bow_raw = [i for i in items if i.get("catalog_id") == "short_bow"]
    assert ammo_raw, "arrow should be in draft items"
    assert bow_raw, "short_bow should be in draft items"
    ammo_iid = ammo_raw[0]["instance_id"]
    bow_iid = bow_raw[0]["instance_id"]

    # Equip the bow
    r = client.post(f"/wizard/{draft_id}/inventory/equip",
                    data={"category": "item", "instance_id": bow_iid})
    assert r.status_code == 303

    # Load ammo (weapon_key = bow instance_id)
    r = client.post(f"/wizard/{draft_id}/ammo/load",
                    data={"weapon_key": bow_iid, "instance_id": ammo_iid})
    assert r.status_code == 303

    # Finalize
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303

    char_id = r.headers["location"].strip("/").split("/")[-1]
    spec = load_character(char_id, client._characters_dir)

    # Verify ammo in spec.items
    ammo_items = [i for i in spec.items
                  if isinstance(d.items.get(i.catalog_id), Ammunition)]
    assert len(ammo_items) == 1 and ammo_items[0].count == 20

    # Verify bow has loaded_ammo_id set
    bow_inst = next((i for i in spec.items if i.catalog_id == "short_bow"), None)
    assert bow_inst is not None
    assert bow_inst.loaded_ammo_id == ammo_iid


def test_spec_verification_spotchecks():
    """Spot-checks against the real data dir."""
    from aose.engine.ammo import accepts
    from aose.engine.enchant import is_compatible
    d = GameData.load(DATA_DIR)
    # silver_arrow + arrow_slaying compatible
    assert is_compatible(d.items["silver_arrow"], d.enchantments["arrow_slaying"])
    # buying two quivers via buy_item stacks to 40
    from aose.models import CharacterSpec, ClassEntry, CoinStack
    from aose.models.storage import StorageLocation
    from aose.engine.shop import buy_item
    carried = StorageLocation(kind="carried")
    spec = CharacterSpec(name="T", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law",
                         coins=[CoinStack(denom="gp", count=100, location=carried)])
    buy_item(spec, "arrow", d)
    buy_item(spec, "arrow", d)
    arrow_items = [i for i in spec.items if i.catalog_id == "arrow"]
    assert len(arrow_items) == 1 and arrow_items[0].count == 40
    # launcher accepts its ammo
    assert accepts(d.items["crossbow"], d.items["crossbow_bolt"])
