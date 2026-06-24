from pathlib import Path

from aose.engine.sources import (
    CLASSIC_SOURCE_ID,
    content_enabled,
    source_content_categories,
    class_available,
    race_available,
    class_allowed_for_race,
    class_level_cap,
)
from aose.data.loader import GameData
from aose.models import RuleSet

DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(DATA_DIR)


def _cls(cid):
    return DATA.classes[cid]


def _race(rid):
    return DATA.races[rid]


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


def test_class_available_hides_race_as_class_in_advanced():
    rs = RuleSet(separate_race_class=True)
    assert class_available(_cls("fighter"), rs) is True
    assert class_available(_cls("elf"), rs) is False  # race-locked, hidden


def test_class_available_shows_race_as_class_in_basic():
    rs = RuleSet(separate_race_class=False)
    assert class_available(_cls("elf"), rs) is True


def test_class_available_respects_disabled_content():
    rs = RuleSet(disabled_content=["carcass_crawler_1:classes"])
    assert class_available(_cls("acolyte"), rs) is False
    assert class_available(_cls("fighter"), rs) is True


def test_race_available_respects_disabled_content():
    rs = RuleSet(disabled_content=["ose_advanced_fantasy:classes"])
    assert race_available(_race("dwarf"), rs) is False
    assert race_available(_race("human"), rs) is True


def test_class_allowed_for_race_enforces_allowed_classes():
    rs = RuleSet()
    assert class_allowed_for_race("fighter", _race("dwarf"), rs) is True
    assert class_allowed_for_race("magic_user", _race("dwarf"), rs) is False


def test_class_allowed_for_race_lifted():
    rs = RuleSet(lift_demihuman_restrictions=True)
    assert class_allowed_for_race("magic_user", _race("dwarf"), rs) is True


def test_class_level_cap_lookup_and_lift():
    rs = RuleSet()
    assert class_level_cap(_race("dwarf"), "fighter", rs) == 10
    assert class_level_cap(_race("human"), "fighter", rs) is None
    assert class_level_cap(_race("dwarf"), "fighter",
                           RuleSet(lift_demihuman_restrictions=True)) is None
