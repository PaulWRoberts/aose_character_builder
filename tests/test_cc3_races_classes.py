from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


CC3_CLASSES = ["beast_master", "dragonborn", "mutoid", "mycelian", "tiefling"]
CC3_RACES = ["dragonborn", "mutoid", "mycelian", "tiefling"]


def test_classes_loaded(data):
    for cid in CC3_CLASSES:
        assert cid in data.classes, cid
        assert data.classes[cid].source == "carcass_crawler_3"


def test_races_loaded(data):
    for rid in CC3_RACES:
        assert rid in data.races, rid
        assert data.races[rid].source == "carcass_crawler_3"


def test_race_as_class_links(data):
    for cid in ["dragonborn", "mutoid", "mycelian", "tiefling"]:
        assert data.classes[cid].race_locked == cid


def test_choice_spell_ids_resolve(data):
    for owner in list(data.classes.values()) + list(data.races.values()):
        for grp in owner.feature_choices:
            for opt in grp.options:
                if opt.spell_id is not None:
                    assert opt.spell_id in data.spells, opt.spell_id


def test_mutoid_has_distinct_pick_two(data):
    grp = {g.id: g for g in data.classes["mutoid"].feature_choices}["mutations"]
    assert grp.pick == 2
    assert len(grp.options) == 8


def test_tiefling_cosmetic_group(data):
    groups = {g.id: g for g in data.classes["tiefling"].feature_choices}
    assert groups["fiendish_appearance"].cosmetic is True
    assert groups["fiendish_gifts"].cosmetic is False
