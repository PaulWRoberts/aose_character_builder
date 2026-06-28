"""Guards the template↔route contract that silently broke after the items
refactor: every action <form> the inventory box renders must POST to a live
route with the field names that route declares."""
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import save_character
from aose.data.loader import GameData
from aose.engine import retainers as retainers_engine
from aose.engine.shop import new_container_instance
from aose.models import (
    AnimalInstance,
    CharacterSpec,
    ClassEntry,
    ItemInstance,
    MagicItemInstance,
)
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
                # name -> last rendered value (None when no value attr / not hidden)
                "values": {},
            }
        elif tag in ("input", "select", "button") and self._cur is not None and a.get("name"):
            self._cur["fields"].add(a["name"])
            self._cur["values"][a["name"]] = a.get("value")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

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


# ---------------------------------------------------------------------------
# Regression guard for bug 2 ("no item instance ''"): every per-item action
# form the inventory box renders — for items inside containers, on carriers,
# and inside a retainer-owned container — must carry a NON-EMPTY reference id.
# ---------------------------------------------------------------------------

_DATA = GameData.load(DATA_DIR)

# Action routes that act on one stack/instance. Each must identify its target by
# a non-empty hidden ref (instance_id / item_id for items, denom for coins).
_ACTION_SUFFIXES = (
    "/inventory/move",
    "/inventory/sell",
    "/inventory/equip",
    "/inventory/unequip",
    "/inventory/consume",
)
_REF_FIELDS = ("instance_id", "item_id", "denom")


def _make_app(tmp_path):
    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    client_app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=tmp_path / "settings.json",
    )
    return TestClient(client_app, follow_redirects=False), characters_dir


def _base_spec() -> CharacterSpec:
    return CharacterSpec(
        name="Hero",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
    )


@pytest.fixture
def nested_storage_character(tmp_path):
    """A character whose stuff lives everywhere a ref id could go empty: inside a
    carried container, on an animal carrier, and inside a retainer-owned
    container in the retainer's own world."""
    client, characters_dir = _make_app(tmp_path)
    spec = _base_spec()

    # (1) Item inside a carried container.
    cont = new_container_instance("backpack", _DATA)
    spec.containers.append(cont)
    spec.items.append(ItemInstance(
        instance_id="torch_in_pack", catalog_id="torch", count=3,
        location=StorageLocation(kind="container", id=cont.instance_id)))

    # (2) Item on an animal carrier.
    mule = AnimalInstance(instance_id="mule1", catalog_id="mule")
    spec.animals.append(mule)
    spec.items.append(ItemInstance(
        instance_id="rope_on_mule", catalog_id="rope_50ft", count=1,
        location=StorageLocation(kind="animal", id="mule1")))

    # (3) Retainer owning a container with an item inside it (retainer world).
    ret = retainers_engine.generate_retainer(
        name="Hench", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=spec, data=_DATA)
    rcont = new_container_instance("backpack", _DATA)
    ret.spec.containers.append(rcont)
    ret.spec.items.append(ItemInstance(
        instance_id="ration_in_ret_pack", catalog_id="torch", count=2,
        location=StorageLocation(kind="container", id=rcont.instance_id)))
    spec.retainers.append(ret)

    save_character("hero", spec, characters_dir)
    return client, "hero"


def test_every_action_form_carries_a_nonempty_ref(nested_storage_character):
    """Bug-2 regression: no action <form> may submit an empty target id.

    Render the sheet (which surfaces container/animal/retainer contents) and
    assert every move/sell/equip/unequip/consume form posts to a live route AND
    carries a non-empty instance_id / item_id / denom hidden input."""
    client, character_id = nested_storage_character
    html = client.get(f"/character/{character_id}").text
    p = _Forms()
    p.feed(html)

    routes = {(r.path, m) for r in app.routes for m in getattr(r, "methods", []) or []}

    checked = 0
    for f in p.forms:
        if not any(f["action"].endswith(s) for s in _ACTION_SUFFIXES):
            continue
        # Points at a live route.
        tmpl = f["action"].replace(character_id, "{character_id}")
        assert (tmpl, "POST") in routes, f"no POST route for {f['action']}"
        # Carries exactly the ref the route needs, and it is non-empty.
        present = [name for name in _REF_FIELDS if name in f["fields"]]
        assert present, f"{f['action']} has no target ref field ({_REF_FIELDS})"
        for name in present:
            val = f["values"].get(name)
            assert val, (
                f"{f['action']} renders an EMPTY {name!r} "
                f"(value={val!r}) — would submit `no item instance ''`")
        checked += 1

    # Sanity: the fixture really did surface nested/carrier/retainer rows, so the
    # loop above actually exercised the dangerous paths.
    assert checked >= 3, f"expected several action forms, only saw {checked}"
