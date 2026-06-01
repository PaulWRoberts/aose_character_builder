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


import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.models import RuleSet
from aose.web.app import create_app


@pytest.fixture
def mc_client(tmp_path):
    """Client with Multiclassing + Separate Race/Class on (free-form combos)."""
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet(multiclassing=True, separate_race_class=True))
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = tmp_path / "drafts"
    return client


def _seed_human_high_stats(client):
    """New draft on a human with stats high enough for paladin+assassin."""
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 13, "WIS": 13, "DEX": 15, "CON": 13, "CHA": 13}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    return draft_id


def test_class_step_rejects_alignment_incompatible_combo(mc_client):
    draft_id = _seed_human_high_stats(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class", data={"class_id": ["paladin", "assassin"]}
    )
    assert r.status_code == 400
    assert "alignment" in r.text.lower()


def test_class_step_allows_alignment_compatible_combo(mc_client):
    draft_id = _seed_human_high_stats(mc_client)
    r = mc_client.post(
        f"/wizard/{draft_id}/class", data={"class_id": ["paladin", "fighter"]}
    )
    assert r.status_code == 303  # paladin [law] ∩ fighter [all] = {law}, OK
