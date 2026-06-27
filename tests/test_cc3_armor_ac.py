"""Full plate AC: tailored (2 [17]) vs untailored (3 [16])."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class
from aose.models import Ability, CharacterSpec, ClassEntry, ItemInstance

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _knight_in_plate(tailored):
    return CharacterSpec(
        name="T",
        abilities={a: 10 for a in Ability},   # DEX 10 → +0
        race_id="human",
        classes=[ClassEntry(class_id="fighter", xp=0)],
        alignment="neutral",
        items=[ItemInstance(instance_id="t_plate", catalog_id="full_plate",
                            equip="armor", tailored=tailored)],
    )


def _armor_inst(spec):
    return next(i for i in spec.items if i.equip == "armor")


def test_full_plate_tailored_is_ac2(data):
    desc, asc = armor_class(_knight_in_plate(True), data, use_shield=False)
    assert desc == 2 and asc == 17


def test_full_plate_untailored_is_ac3(data):
    desc, asc = armor_class(_knight_in_plate(False), data, use_shield=False)
    assert desc == 3 and asc == 16


def test_default_armor_tailored_is_true(data):
    # New default: ItemInstance.tailored defaults to True.
    spec = CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        classes=[ClassEntry(class_id="fighter", xp=0)], alignment="neutral",
        items=[ItemInstance(instance_id="t_plate", catalog_id="full_plate",
                            equip="armor")],
    )
    assert _armor_inst(spec).tailored is True


def test_tailored_route_flips_flag(tmp_path):
    from fastapi.testclient import TestClient
    from aose.web.app import app
    from aose.characters.storage import save_character, load_character

    data = GameData.load(DATA_DIR)
    app.state.game_data = data
    app.state.characters_dir = tmp_path
    spec = _knight_in_plate(True)
    iid = _armor_inst(spec).instance_id
    save_character("c1", spec, tmp_path)

    client = TestClient(app)
    r = client.post("/character/c1/equipment/tailored",
                    data={"instance_id": iid, "value": "false"},
                    follow_redirects=False)
    assert r.status_code == 303
    reloaded = load_character("c1", tmp_path)
    assert next(i for i in reloaded.items if i.equip == "armor").tailored is False
