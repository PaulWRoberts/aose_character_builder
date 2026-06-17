from pathlib import Path
from aose.data.loader import GameData
from aose.models import RetainerHiringRule

DATA = GameData.load(Path("data"))


def test_assassin_encodes_tiered_hiring():
    cls = DATA.classes["assassin"]
    tiers = {r.min_level: r.allows for r in cls.retainer_hiring}
    assert tiers[1] == "none"
    assert tiers[4] == ["assassin"]
    assert tiers[8] == ["assassin", "thief"]
    assert tiers[12] == "any"


def test_default_class_has_no_hiring_rules():
    assert DATA.classes["fighter"].retainer_hiring == []


def test_rule_model_accepts_list_or_keyword():
    assert RetainerHiringRule(min_level=4, allows=["assassin"]).allows == ["assassin"]
    assert RetainerHiringRule(min_level=1, allows="none").allows == "none"
