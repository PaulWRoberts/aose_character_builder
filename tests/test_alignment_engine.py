"""Tests for typed class alignment restrictions + the alignment engine."""
from pathlib import Path

from aose.data.loader import GameData

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_class_allowed_alignments_loaded_from_data():
    data = GameData.load(DATA_DIR)
    assert data.classes["paladin"].allowed_alignments == ["law"]
    assert data.classes["druid"].allowed_alignments == ["neutral"]
    assert data.classes["ranger"].allowed_alignments == ["law", "neutral"]
    assert data.classes["assassin"].allowed_alignments == ["neutral", "chaos"]


def test_unrestricted_classes_have_empty_allowed_alignments():
    data = GameData.load(DATA_DIR)
    for cid in ("fighter", "cleric", "thief", "magic_user", "knight", "bard"):
        assert data.classes[cid].allowed_alignments == [], cid


from aose.engine.alignment import ALL, allowed_alignments


def _cls(data, cid):
    return data.classes[cid]


def test_allowed_alignments_single_unrestricted_is_all_three():
    data = GameData.load(DATA_DIR)
    assert allowed_alignments([_cls(data, "fighter")]) == ALL == {"law", "neutral", "chaos"}


def test_allowed_alignments_single_restricted():
    data = GameData.load(DATA_DIR)
    assert allowed_alignments([_cls(data, "paladin")]) == {"law"}
    assert allowed_alignments([_cls(data, "ranger")]) == {"law", "neutral"}


def test_allowed_alignments_intersection():
    data = GameData.load(DATA_DIR)
    # paladin [law] ∩ fighter [all] = {law}
    assert allowed_alignments([_cls(data, "paladin"), _cls(data, "fighter")]) == {"law"}
    # ranger [law, neutral] ∩ assassin [neutral, chaos] = {neutral}
    assert allowed_alignments([_cls(data, "ranger"), _cls(data, "assassin")]) == {"neutral"}


def test_allowed_alignments_empty_for_incompatible_combo():
    data = GameData.load(DATA_DIR)
    # paladin [law] ∩ assassin [neutral, chaos] = {}
    assert allowed_alignments([_cls(data, "paladin"), _cls(data, "assassin")]) == set()


def test_allowed_alignments_no_classes_is_all_three():
    assert allowed_alignments([]) == ALL
