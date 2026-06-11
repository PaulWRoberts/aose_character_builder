from pathlib import Path

from aose.engine.sources import (
    CLASSIC_SOURCE_ID,
    content_enabled,
    source_content_categories,
)
from aose.data.loader import GameData
from aose.models import RuleSet

DATA_DIR = Path(__file__).parent.parent / "data"


def test_classic_is_always_enabled():
    rs = RuleSet(disabled_content=["ose_classic_fantasy:classes"])
    assert content_enabled(CLASSIC_SOURCE_ID, "classes", rs) is True


def test_unlisted_category_is_enabled_by_default():
    assert content_enabled("ose_advanced_fantasy", "classes", RuleSet()) is True


def test_disabled_category_is_not_enabled():
    rs = RuleSet(disabled_content=["carcass_crawler_3:equipment"])
    assert content_enabled("carcass_crawler_3", "equipment", rs) is False
    # A different category of the same source stays enabled.
    assert content_enabled("carcass_crawler_3", "classes", rs) is True


def test_source_content_categories_matches_data():
    data = GameData.load(DATA_DIR)
    cats = source_content_categories(data)
    assert cats["ose_classic_fantasy"] == ["classes", "equipment", "magic_items"]
    assert cats["ose_advanced_fantasy"] == ["classes", "magic_items"]
    assert cats["carcass_crawler_1"] == ["classes"]
    assert cats["carcass_crawler_3"] == ["classes", "equipment"]
