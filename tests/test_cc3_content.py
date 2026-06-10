"""Carcass Crawler 3 expanded equipment content."""
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_source_registered(data):
    assert "carcass_crawler_3" in data.sources
    assert data.sources["carcass_crawler_3"].core is False


from aose.models import AdventuringGear, Container

CC3_GEAR_IDS = [
    "barrel", "bedroll", "bell_miniature", "block_and_tackle", "bucket",
    "caltrops", "candles", "chain_10ft", "chalk", "chisel", "cooking_pots",
    "firewood", "fishing_rod", "holy_symbol_gold", "holy_symbol_wooden",
    "ink_vial", "ladder_10ft", "lantern_bullseye", "lock", "magnifying_glass",
    "manacles", "marbles", "mining_pick", "instrument_string", "instrument_wind",
    "paper", "quill", "saw", "scroll_case", "sledgehammer", "spade",
    "tent", "twine", "vial_glass", "whistle",
]
CC3_CONTAINERS = {
    "belt_pouch": 50, "box_iron_small": 250, "box_iron_large": 800,
    "chest_wooden_small": 300, "chest_wooden_large": 1000,
}


@pytest.mark.parametrize("gid", CC3_GEAR_IDS)
def test_cc3_gear_loads(data, gid):
    item = data.items[gid]
    assert isinstance(item, AdventuringGear)
    assert item.source == "carcass_crawler_3"


@pytest.mark.parametrize("cid,cap", sorted(CC3_CONTAINERS.items()))
def test_cc3_containers(data, cid, cap):
    item = data.items[cid]
    assert isinstance(item, Container)
    assert item.capacity_cn == cap
    assert item.source == "carcass_crawler_3"


def test_bundle_counts(data):
    assert data.items["candles"].bundle_count == 10
    assert data.items["chalk"].bundle_count == 10
    assert data.items["paper"].bundle_count == 2


@pytest.mark.parametrize("qid", ["knock_out", "entangle", "stealth", "strangle"])
def test_cc3_qualities_loaded(data, qid):
    assert qid in data.qualities
    assert data.qualities[qid].param == "none"


from aose.models import Ammunition, Weapon


def test_bastard_sword_versatile(data):
    w = data.items["bastard_sword"]
    assert isinstance(w, Weapon)
    assert w.versatile is True
    assert w.two_handed_damage == "1d8+1"
    assert w.damage.default == "1d6"
    assert w.damage.variable == "1d6+1"
    assert w.hands == 1
    assert "sword" in w.groups


@pytest.mark.parametrize("wid", ["blowgun", "net"])
def test_no_damage_weapons(data, wid):
    w = data.items[wid]
    assert w.deals_damage is False
    assert w.damage.default == "" and w.damage.variable == ""


def test_blowgun_accepts_darts(data):
    assert data.items["blowgun"].accepts_ammo == ["blowgun_dart"]
    dart = data.items["blowgun_dart"]
    assert isinstance(dart, Ammunition)
    assert dart.bundle_count == 5
    assert dart.groups == ["blowgun_dart"]


@pytest.mark.parametrize("wid,quals", [
    ("blackjack", {"blunt", "knock_out", "melee", "stealth"}),
    ("bolas", {"blunt", "entangle", "missile"}),
    ("garotte", {"melee", "stealth", "strangle", "two_handed"}),
    ("whip", {"entangle", "melee"}),
])
def test_cc3_weapon_qualities(data, wid, quals):
    assert data.items[wid].quality_ids == quals
    assert data.items[wid].source == "carcass_crawler_3"


def test_garotte_two_handed(data):
    assert data.items["garotte"].hands == 2
