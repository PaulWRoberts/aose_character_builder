from aose.engine.sources import CLASSIC_SOURCE_ID, source_enabled
from aose.models import RuleSet


def test_classic_is_always_enabled():
    rs = RuleSet(disabled_sources=["ose_classic_fantasy", "ose_advanced_fantasy"])
    assert source_enabled(CLASSIC_SOURCE_ID, rs) is True


def test_unlisted_source_is_enabled_by_default():
    assert source_enabled("ose_advanced_fantasy", RuleSet()) is True


def test_disabled_source_is_not_enabled():
    rs = RuleSet(disabled_sources=["ose_advanced_fantasy"])
    assert source_enabled("ose_advanced_fantasy", rs) is False


def test_disabled_sources_defaults_empty():
    assert RuleSet().disabled_sources == []
