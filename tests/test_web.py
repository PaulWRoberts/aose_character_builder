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


def test_sheet_renders_valuables_section(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry
    from aose.engine import valuables as v
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=Path(__file__).parent.parent / "data",
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Bran",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    spec.gems = v.add_gem([], 100, count=2, label="ruby")
    spec.jewellery = v.add_jewellery([], 700, label="necklace")
    save_character("bran", spec, characters_dir)

    client = TestClient(app, follow_redirects=False)
    html = client.get("/character/bran").text
    # The "Gems & Jewellery" section header moved to the Treasure drawer tab;
    # verify the gem/jewellery data is present in the body and the Treasure tab is shown.
    assert "Treasure" in html   # Treasure tab label is present
    assert "ruby" in html       # gem label still in body (Treasure tab)
    assert "necklace" in html   # jewellery label still in body (Treasure tab)


def test_noncaster_has_no_spells_group(client):
    """Thorin is a dwarf fighter — no spells group should appear."""
    response = client.get("/character/thorin")
    assert response.status_code == 200
    assert "Spells —" not in response.text


def test_caster_has_spells_group(tmp_path):
    """A magic-user should render the arcane spells group."""
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=Path(__file__).parent.parent / "data",
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Mage",
        abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human",
        classes=[ClassEntry(class_id="magic_user", level=1, hp_rolls=[4],
                            spellbook=["magic_user_magic_missile"])],
        alignment="neutral",
    )
    save_character("mage", spec, characters_dir)

    client = TestClient(app, follow_redirects=False)
    html = client.get("/character/mage").text
    assert "Spells —" in html


def test_sheet_per_spell_modal_with_cast_forms(tmp_path):
    from aose.characters import save_character
    from aose.data.loader import GameData
    from aose.engine import spells as se
    from aose.models import CharacterSpec, ClassEntry

    data = GameData.load(DATA_DIR)
    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()

    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=["magic_user_magic_missile", "magic_user_light"])
    cls = data.classes["magic_user"]
    e = se.assign_slot(e, cls, data, level=1, spell_id="magic_user_light", reversed=True)
    spec = CharacterSpec(
        name="Raistlin",
        abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    save_character("raistlin", spec, characters_dir)

    app = create_app(data_dir=DATA_DIR, characters_dir=characters_dir,
                     examples_dir=examples_dir)
    client = TestClient(app)
    body = client.get("/character/raistlin").text

    # Reversed spell shows under its reverse name and has its own modal + cast form.
    assert "Darkness" in body
    assert 'id="modal-spell-magic_user-magic_user_light-r"' in body
    assert "/character/raistlin/spells/cast" in body
    # The old static placeholder modal is gone.
    assert 'id="modal-spell"' not in body
