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
