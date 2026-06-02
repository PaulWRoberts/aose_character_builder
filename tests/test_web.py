from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EXAMPLES_DIR = PROJECT_ROOT / "examples"


@pytest.fixture(scope="module")
def client():
    app = create_app(data_dir=DATA_DIR, characters_dir=EXAMPLES_DIR)
    return TestClient(app)


def test_index_lists_thorin(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Thorin" in response.text
    assert 'href="/character/thorin"' in response.text


def test_sheet_renders(client):
    response = client.get("/character/thorin")
    assert response.status_code == 200
    body = response.text
    assert "Thorin" in body
    assert "Dwarf" in body
    assert "Fighter 1" in body
    assert "Lawful" in body
    # Combat block — current_hp / max_hp format (damage_taken=0 → current=max)
    assert "8 / 8" in body  # current HP / max HP
    # THAC0 (default ruleset is descending AC)
    assert "THAC0" in body
    assert "19" in body
    # Race feature (book-accurate dwarf feature names)
    assert "Detect Construction Tricks" in body


def test_sheet_404_for_missing_character(client):
    response = client.get("/character/no-such-id")
    assert response.status_code == 404
