"""Ammunition model + engine tests."""
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


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


def test_ammo_stack_and_spec_fields():
    from aose.models import AmmoStack, CharacterSpec, ClassEntry
    s = AmmoStack(instance_id="x", base_id="arrow", count=20)
    assert s.enchantment_id is None and s.count == 20
    spec = CharacterSpec(name="A", abilities={}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law")
    assert spec.ammo == [] and spec.loaded_ammo == {}


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
from aose.models import AmmoStack, Ammunition, Enchantment, Weapon, WeaponDamage


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


def test_buy_ammo_adds_bundle_and_combines():
    from aose.engine.ammo import buy_ammo
    d = _data_with_ammo()
    stacks, gold = buy_ammo([], 10, "arrow", d)
    assert gold == 5 and stacks[0].count == 20 and stacks[0].enchantment_id is None
    stacks, gold = buy_ammo(stacks, gold, "arrow", d)   # second quiver combines
    assert gold == 0 and len(stacks) == 1 and stacks[0].count == 40


def test_buy_ammo_insufficient_gold():
    from aose.engine.ammo import buy_ammo, InsufficientGold
    d = _data_with_ammo()
    with pytest.raises(InsufficientGold):
        buy_ammo([], 2, "arrow", d)


def test_add_free_magic_ammo_validates_compat():
    from aose.engine.ammo import add_free_ammo, IncompatibleAmmo
    d = _data_with_ammo()
    stacks = add_free_ammo([], "arrow", "arrows_plus_1", d)
    assert stacks[0].enchantment_id == "arrows_plus_1" and stacks[0].count == 1
    d.enchantments["bolts"] = Enchantment(id="bolts", name_template="{base}",
        kind="ammunition", applies_to={"include": ["crossbow_bolt"]})
    with pytest.raises(IncompatibleAmmo):
        add_free_ammo([], "arrow", "bolts", d)


def test_adjust_count_clamps_and_removes_at_zero():
    from aose.engine.ammo import adjust_count
    s = [AmmoStack(instance_id="a", base_id="arrow", count=3)]
    s = adjust_count(s, "a", -1)
    assert s[0].count == 2
    s = adjust_count(s, "a", -5)        # clamps to 0 → stack removed
    assert s == []


def test_load_unload_and_loaded_stack():
    from aose.engine.ammo import load, unload, loaded_stack
    d = _data_with_ammo()
    stacks = [AmmoStack(instance_id="a", base_id="arrow",
                        enchantment_id="arrows_plus_1", count=20)]

    class _Spec:  # minimal stand-in
        ammo = stacks
        loaded_ammo = {}
    spec = _Spec()
    spec.loaded_ammo = load(spec.loaded_ammo, "short_bow", "a")
    assert loaded_stack("short_bow", spec, d).instance_id == "a"
    spec.loaded_ammo = unload(spec.loaded_ammo, "short_bow")
    assert loaded_stack("short_bow", spec, d) is None


def test_loaded_bonus_from_magic_ammo():
    from aose.engine.ammo import load, loaded_bonus
    d = _data_with_ammo()
    stacks = [AmmoStack(instance_id="a", base_id="arrow",
                        enchantment_id="arrows_plus_1", count=20)]

    class _Spec:
        ammo = stacks
        loaded_ammo = {}
    spec = _Spec()
    spec.loaded_ammo = load(spec.loaded_ammo, "short_bow", "a")
    bonus, cond = loaded_bonus("short_bow", spec, d)
    assert bonus == 1 and cond is None


def test_is_unloaded_flag():
    from aose.engine.ammo import is_unloaded
    d = _data_with_ammo()

    class _Spec:
        ammo = []
        loaded_ammo = {}
    assert is_unloaded("short_bow", d.items["short_bow"], _Spec(), d) is True


def _bow_spec(loaded=True, ench=True):
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="B", abilities={"STR": 12, "INT": 10, "WIS": 10,
                             "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="law")
    spec.inventory = ["short_bow"]
    spec.equipped_weapons = ["short_bow"]
    eid = "arrows_plus_1" if ench else None
    spec.ammo = [AmmoStack(instance_id="a", base_id="arrow",
                           enchantment_id=eid, count=20)]
    if loaded:
        spec.loaded_ammo = {"short_bow": "a"}
    return spec


def _real_data():
    return GameData.load(DATA_DIR)


def _bow_profile(profiles):
    return next(p for p in profiles if p.weapon_id == "short_bow")


def test_plus1_arrow_in_plus0_bow_is_plus1():
    from aose.engine.attacks import attack_profiles
    d = _real_data()
    p = _bow_profile(attack_profiles(_bow_spec(loaded=True, ench=True), d))
    base = _bow_profile(attack_profiles(_bow_spec(loaded=True, ench=False), d))
    assert p.to_hit_ascending == base.to_hit_ascending + 1


def test_unloaded_bow_flagged():
    from aose.engine.attacks import attack_profiles
    d = _real_data()
    p = _bow_profile(attack_profiles(_bow_spec(loaded=False), d))
    assert p.unloaded is True
    p2 = _bow_profile(attack_profiles(_bow_spec(loaded=True, ench=True), d))
    assert p2.unloaded is False
    assert p2.loaded_ammo_name and "+1" in p2.loaded_ammo_name


def test_profile_adds_ammo_bonus_unit():
    from aose.engine.attacks import attack_profiles
    d = _data_with_ammo()
    from aose.models import CharacterSpec, ClassEntry
    # Minimal class so thac0() resolves; reuse fighter from real data.
    rd = _real_data()
    d.classes = rd.classes
    spec = CharacterSpec(name="U", abilities={"STR": 10, "INT": 10, "WIS": 10,
                         "DEX": 10, "CON": 10, "CHA": 10}, race_id="human",
                         classes=[ClassEntry(class_id="fighter")], alignment="law")
    spec.equipped_weapons = ["short_bow"]
    spec.ammo = [AmmoStack(instance_id="a", base_id="arrow",
                           enchantment_id="arrows_plus_1", count=5)]
    spec.loaded_ammo = {"short_bow": "a"}
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
    spec = _bow_spec(loaded=True, ench=True)
    sheet = build_sheet(spec, d)
    names = [row.name for row in sheet.ammo]
    assert any("+1" in n for n in names)
    assert sheet.ammo[0].count == 20
    # the bow launcher offers the loaded stack as an option
    opts = sheet.ammo_load_options["short_bow"]
    assert any(o.instance_id == "a" for o in opts)


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
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(),
    )
    base.update(overrides)
    spec = CharacterSpec(**base)
    save_character("test", spec, client._characters_dir)
    return "test"


def test_buy_then_load_then_adjust(tmp_path):
    client = _make_client(tmp_path)
    cid = _seed(client, gold=100)
    # add a bow and equip it
    client.post(f"/character/{cid}/equipment/add", data={"item_id": "short_bow"})
    client.post(f"/character/{cid}/equipment/equip", data={"item_id": "short_bow"})
    # buy a quiver → ammo stack of 20, gold -5
    client.post(f"/character/{cid}/equipment/buy", data={"item_id": "arrow"})
    spec = load_character(cid, client._characters_dir)
    assert spec.ammo[0].count == 20 and spec.ammo[0].base_id == "arrow"
    iid = spec.ammo[0].instance_id
    # load + adjust
    r = client.post(f"/character/{cid}/ammo/load",
                    data={"weapon_key": "short_bow", "instance_id": iid})
    assert r.status_code == 303
    r = client.post(f"/character/{cid}/ammo/adjust",
                    data={"instance_id": iid, "delta": -1})
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.loaded_ammo["short_bow"] == iid and spec.ammo[0].count == 19


def test_add_magic_ammo_and_remove(tmp_path):
    client = _make_client(tmp_path)
    cid = _seed(client)
    r = client.post(f"/character/{cid}/ammo/add",
                    data={"base_id": "arrow", "enchantment_id": "arrows_plus_1"})
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.ammo[0].enchantment_id == "arrows_plus_1"
    iid = spec.ammo[0].instance_id
    r = client.post(f"/character/{cid}/ammo/remove", data={"instance_id": iid})
    assert r.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.ammo == []


# ── Wizard test ───────────────────────────────────────────────────────────

def _wizard_client(tmp_path):
    """Create a TestClient with a fresh wizard-capable app."""
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
    """Drive a wizard draft through all steps up to equipment; return draft_id."""
    from aose.characters.drafts import load_draft, save_draft
    r = client.get("/wizard/new")
    assert r.status_code == 303
    draft_id = r.headers["location"].strip("/").split("/")[1]

    # Force abilities
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
    # Roll starting gold
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    return draft_id


def test_wizard_ammo_carries_into_character(tmp_path):
    """Buy a bow + quiver in the wizard, load the ammo, finalize; assert
    the saved CharacterSpec has the ammo stack and loaded_ammo entry."""
    from aose.characters.drafts import load_draft, save_draft
    client = _wizard_client(tmp_path)
    draft_id = _drive_wizard_to_equipment(client, tmp_path)

    # Give enough gold for a bow + quiver
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["gold"] = 100
    save_draft(draft_id, draft, tmp_path / "drafts")

    # Buy a bow (regular item → goes to inventory)
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "short_bow"})
    assert r.status_code == 303

    # Buy a quiver of arrows (ammunition → goes to ammo stacks)
    r = client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "arrow"})
    assert r.status_code == 303

    # Load the arrow stack into the bow
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert len(draft.get("ammo", [])) == 1
    iid = draft["ammo"][0]["instance_id"]
    r = client.post(f"/wizard/{draft_id}/ammo/load",
                    data={"weapon_key": "short_bow", "instance_id": iid})
    assert r.status_code == 303

    # Finalize
    client.post(f"/wizard/{draft_id}/equipment")  # advance to review
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303

    # Verify the saved character has ammo + loaded_ammo
    location = r.headers["location"]  # e.g. "/character/archer"
    char_id = location.strip("/").split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert len(spec.ammo) == 1
    assert spec.ammo[0].count == 20
    assert spec.loaded_ammo.get("short_bow") == iid


def test_spec_verification_spotchecks():
    """Spec "Verification" spot-checks against the real data dir."""
    d = GameData.load(DATA_DIR)
    from aose.engine.ammo import accepts, buy_ammo
    from aose.engine.enchant import is_compatible
    # silver_arrow + arrow_slaying compatible
    assert is_compatible(d.items["silver_arrow"], d.enchantments["arrow_slaying"])
    # buying two quivers combines to 40 for 10 gp
    stacks, gold = buy_ammo([], 100, "arrow", d)
    stacks, gold = buy_ammo(stacks, gold, "arrow", d)
    assert len(stacks) == 1 and stacks[0].count == 40 and gold == 90
    # a launcher accepts its ammo
    assert accepts(d.items["crossbow"], d.items["crossbow_bolt"])
