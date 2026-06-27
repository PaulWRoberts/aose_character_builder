"""HTTP route tests for retainer actions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_character, save_character
from aose.models import CharacterSpec, ClassEntry, RuleSet, CoinStack, ItemInstance
from aose.models.storage import StorageLocation
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir, drafts_dir=drafts_dir,
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    c = TestClient(app, follow_redirects=False)
    c._characters_dir = characters_dir
    return c


def _save_char(client) -> str:
    spec = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
        coins=[CoinStack(denom="gp", count=50)],
    )
    save_character("boss", spec, client._characters_dir)
    return "boss"


def test_add_retainer_route(client):
    cid = _save_char(client)
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "Sten", "class_id": "fighter", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert len(spec.retainers) == 1
    assert spec.retainers[0].spec.name == "Sten"


def test_add_normal_human_retainer(client):
    cid = _save_char(client)
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "Boy", "class_id": "normal_human", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.retainers[0].spec.classes[0].class_id == "normal_human"


def _save_char_with_retainer(client) -> tuple[str, str]:
    """PC with one fighter retainer holding a loose dagger. Returns (cid, ret_id)."""
    from aose.engine import retainers as retainers_engine
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    pc = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
    )
    ret = retainers_engine.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=data)
    ret.spec.items.append(ItemInstance(instance_id="dag1", catalog_id="dagger"))
    pc.retainers = [ret]
    save_character("boss", pc, client._characters_dir)
    return "boss", ret.id


def test_retainer_hp_route(client):
    cid, rid = _save_char_with_retainer(client)
    # take 1 point of damage
    resp = client.post(f"/character/{cid}/retainer/{rid}/hp", data={"delta": -1})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.retainers[0].spec.damage_taken == 1
    # over-heal floors damage_taken at 0 (current HP never exceeds max)
    resp = client.post(f"/character/{cid}/retainer/{rid}/hp", data={"delta": 5})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.retainers[0].spec.damage_taken == 0


def test_retainer_equip_route(client):
    cid, rid = _save_char_with_retainer(client)
    resp = client.post(f"/character/{cid}/retainer/{rid}/equip",
                       data={"category": "item", "instance_id": "dag1"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    ret_items = spec.retainers[0].spec.items
    assert any(i.catalog_id == "dagger" and i.equip == "main_hand" for i in ret_items)


def test_retainer_equip_missing_item_400(client):
    cid, rid = _save_char_with_retainer(client)
    resp = client.post(f"/character/{cid}/retainer/{rid}/equip",
                       data={"category": "item", "instance_id": "nonexistent_iid"})
    assert resp.status_code == 400


def test_retainer_unequip_route(client):
    cid, rid = _save_char_with_retainer(client)
    client.post(f"/character/{cid}/retainer/{rid}/equip",
                data={"category": "item", "instance_id": "dag1"})
    resp = client.post(f"/character/{cid}/retainer/{rid}/unequip",
                       data={"category": "item", "instance_id": "dag1"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    ret_items = spec.retainers[0].spec.items
    assert not any(i.catalog_id == "dagger" and i.equip is not None for i in ret_items)
    assert any(i.catalog_id == "dagger" and i.location.kind == "carried" for i in ret_items)


def test_sheet_renders_retainer_equip_modals(client):
    cid, rid = _save_char_with_retainer(client)
    # equip the dagger so there is both an equipped row and (no) loose dagger
    client.post(f"/character/{cid}/retainer/{rid}/equip",
                data={"category": "item", "instance_id": "dag1"})
    resp = client.get(f"/character/{cid}")
    assert resp.status_code == 200
    html = resp.text
    # equipped-item modal id present (keyed by instance_id now, not catalog_id)
    assert f"modal-item-retainer-{rid}-eq-dag1" in html
    # unequip action targets the retainer route
    assert f"/character/{cid}/retainer/{rid}/unequip" in html


def test_sheet_renders_animal_barding_modal(client):
    from aose.models import AnimalInstance
    pc = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="a1", catalog_id="war_horse",
                                armor_id="horse_barding")],
    )
    save_character("boss", pc, client._characters_dir)
    resp = client.get("/character/boss")
    assert resp.status_code == 200
    assert "modal-item-animal-a1-eq-horse_barding" in resp.text
    assert "/character/boss/animal/a1/unequip" in resp.text


def _save_char_rs(client, ruleset) -> str:
    spec = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=11, hp_rolls=[8] * 9)],
        alignment="neutral",
        coins=[CoinStack(denom="gp", count=50)],
        ruleset=ruleset,
    )
    save_character("boss", spec, client._characters_dir)
    return "boss"


def test_hire_rejects_disabled_class(client):
    cid = _save_char_rs(client, RuleSet(disabled_content=["carcass_crawler_1:classes"]))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "acolyte", "level": "1",
        "race_id": "human", "alignment": "neutral"})
    assert resp.status_code == 400


def test_hire_rejects_illegal_demihuman_combo(client):
    cid = _save_char_rs(client, RuleSet(separate_race_class=True))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "magic_user", "level": "1",
        "race_id": "dwarf", "alignment": "neutral"})
    assert resp.status_code == 400


def test_hire_allows_combo_when_restrictions_lifted(client):
    cid = _save_char_rs(client, RuleSet(separate_race_class=True,
                                        lift_demihuman_restrictions=True))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "magic_user", "level": "1",
        "race_id": "dwarf", "alignment": "neutral"})
    assert resp.status_code == 303


def test_hire_rejects_level_above_race_cap(client):
    # PC is fighter L11; dwarf fighter cap is 10, so level 11 is illegal.
    cid = _save_char_rs(client, RuleSet(separate_race_class=True))
    resp = client.post(f"/character/{cid}/retainer/add", data={
        "name": "X", "class_id": "fighter", "level": "11",
        "race_id": "dwarf", "alignment": "neutral"})
    assert resp.status_code == 400


def test_retainer_equip_accepts_instance_id(client):
    """Retainer equip route accepts category+instance_id (dispatcher form)."""
    cid, rid = _save_char_with_retainer(client)
    # The helper adds a dagger with instance_id="dag1"
    resp = client.post(f"/character/{cid}/retainer/{rid}/equip",
                       data={"category": "item", "instance_id": "dag1"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    ret_items = spec.retainers[0].spec.items
    assert any(i.instance_id == "dag1" and i.equip == "main_hand" for i in ret_items)
