"""Guards the template↔route contract that silently broke after the items
refactor: every action <form> the inventory box renders must POST to a live
route with the field names that route declares."""
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import save_character
from aose.models import CharacterSpec, ClassEntry, ItemInstance, MagicItemInstance
from aose.models.storage import StorageLocation
from aose.web.app import app, create_app

DATA_DIR = Path(__file__).parent.parent / "data"


class _Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._cur = {
                "action": a.get("action", ""),
                "method": a.get("method", "get"),
                "fields": set(),
            }
        elif tag in ("input", "select", "button") and self._cur is not None and a.get("name"):
            self._cur["fields"].add(a["name"])

    def handle_endtag(self, tag):
        if tag == "form" and self._cur is not None:
            self.forms.append(self._cur)
            self._cur = None


@pytest.fixture
def inventory_box_character(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    client_app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=tmp_path / "settings.json",
    )
    client = TestClient(client_app, follow_redirects=False)
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        items=[
            ItemInstance(instance_id="sword_eq", catalog_id="sword", equip="main_hand"),
            ItemInstance(instance_id="mace_c", catalog_id="mace",
                         location=StorageLocation(kind="carried")),
            ItemInstance(instance_id="torch_s", catalog_id="torch",
                         location=StorageLocation(kind="stashed")),
            ItemInstance(instance_id="ench_mace", catalog_id="mace",
                         enchantment_id="generic_plus_1",
                         location=StorageLocation(kind="carried")),
        ],
        magic_items=[
            MagicItemInstance(instance_id="mi_amulet",
                              catalog_id="amulet_of_protection_against_possession",
                              equipped=False),
        ],
    )
    save_character("hero", spec, characters_dir)
    return client, "hero"


def test_inventory_action_forms_match_routes(inventory_box_character):
    client, character_id = inventory_box_character
    html = client.get(f"/character/{character_id}").text
    p = _Forms()
    p.feed(html)

    routes = {(r.path, m) for r in app.routes for m in getattr(r, "methods", []) or []}
    EXPECTED = {
        "/inventory/equip": {"category", "instance_id"},
        "/inventory/unequip": {"category", "instance_id"},
        "/inventory/sell": {"category", "instance_id", "mode"},
        "/inventory/move": {"category"},
    }
    seen = set()
    for f in p.forms:
        for suffix, required in EXPECTED.items():
            if f["action"].endswith(suffix):
                seen.add(suffix)
                assert required <= f["fields"], (
                    f"{f['action']} missing {required - f['fields']}")
                tmpl = f["action"].replace(character_id, "{character_id}")
                assert (tmpl, "POST") in routes, f"no POST route for {f['action']}"
    assert {"/inventory/equip", "/inventory/unequip", "/inventory/sell"} <= seen
