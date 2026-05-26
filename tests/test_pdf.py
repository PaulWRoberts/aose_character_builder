"""Tests for the print and PDF endpoints."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters.storage import save_character
from aose.models.character import CharacterSpec, ClassEntry
from aose.models.ruleset import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

_SAMPLE_SPEC = CharacterSpec(
    name="Thorin",
    race_id="dwarf",
    abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
    alignment="law",
    classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[7])],
    ruleset=RuleSet(),
)


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    characters_dir.mkdir()
    # Pre-seed one character so the routes have something to serve.
    save_character("thorin", _SAMPLE_SPEC, characters_dir)
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts",
        examples_dir=tmp_path / "examples",
    )
    return TestClient(app, follow_redirects=False)


# ── /print ─────────────────────────────────────────────────────────────────

def test_print_route_returns_html(client):
    r = client.get("/character/thorin/print")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_print_route_contains_character_data(client):
    r = client.get("/character/thorin/print")
    assert "Thorin" in r.text
    assert "Dwarf" in r.text
    assert "Fighter 1" in r.text


def test_print_route_has_auto_print_script(client):
    r = client.get("/character/thorin/print")
    assert "window.print()" in r.text


def test_print_route_contains_all_save_labels(client):
    r = client.get("/character/thorin/print")
    assert "Death / Poison" in r.text
    assert "Breath Attacks" in r.text
    assert "Spells / Rods / Staves" in r.text


def test_print_route_404_for_unknown(client):
    r = client.get("/character/nobody/print")
    assert r.status_code == 404


def test_print_route_has_no_site_nav(client):
    """Print page must not include the site chrome (nav, header, etc.)."""
    r = client.get("/character/thorin/print")
    assert "AOSE Character Builder" not in r.text


def test_print_page_has_print_css(client):
    """Print page should embed the print CSS inline."""
    r = client.get("/character/thorin/print")
    assert "@page" in r.text


# ── /pdf ───────────────────────────────────────────────────────────────────

def test_pdf_route_404_for_unknown(client):
    r = client.get("/character/nobody/pdf")
    assert r.status_code == 404


def test_pdf_route_availability(client):
    """When WeasyPrint is available the route returns a PDF; otherwise 503."""
    from aose.web import pdf as pdf_module

    r = client.get("/character/thorin/pdf")
    if pdf_module.is_available():
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
    else:
        assert r.status_code == 503
        assert "GTK3" in r.json()["detail"] or "WeasyPrint" in r.json()["detail"]


# ── sheet.html action bar ──────────────────────────────────────────────────

def test_sheet_page_has_print_link(client):
    r = client.get("/character/thorin")
    assert r.status_code == 200
    assert 'href="/character/thorin/print"' in r.text


def test_sheet_page_has_pdf_link(client):
    r = client.get("/character/thorin")
    assert 'href="/character/thorin/pdf"' in r.text
