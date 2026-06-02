from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters.drafts import load_draft, save_draft
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    c = TestClient(app, follow_redirects=False)
    c._drafts = tmp_path / "drafts"
    return c


def test_strict_mode_defaults_on():
    assert RuleSet().strict_mode is True


def test_strict_mode_no_pending_badge(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert 'name="strict_mode"' in r.text
    # The strict_mode row must not carry a pending badge.
    idx = r.text.index('name="strict_mode"')
    snippet = r.text[idx:idx + 400]
    assert "pending" not in snippet
