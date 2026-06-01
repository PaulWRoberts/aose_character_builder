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
