from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters.drafts import load_draft, save_draft
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"  # empty so no bootstrap noise
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
    )
    return TestClient(app, follow_redirects=False)


def _start_draft(client) -> str:
    r = client.get("/wizard/new")
    assert r.status_code == 303
    location = r.headers["location"]
    # Expected shape: /wizard/{id}/abilities
    parts = location.strip("/").split("/")
    return parts[1]


def test_new_does_not_pre_roll_abilities(client, tmp_path):
    draft_id = _start_draft(client)
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert "abilities" not in draft


def test_abilities_page_shows_roll_button_before_rolling(client):
    draft_id = _start_draft(client)
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert r.status_code == 200
    assert "Abilities" in r.text
    assert f'/wizard/{draft_id}/abilities/roll' in r.text


def test_abilities_page_shows_scores_after_rolling(client):
    draft_id = _start_draft(client)
    client.post(f"/wizard/{draft_id}/abilities/roll")
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert "Continue" in r.text


def test_roll_stores_per_die_results_on_draft(client, tmp_path):
    draft_id = _start_draft(client)
    client.post(f"/wizard/{draft_id}/abilities/roll")
    draft = load_draft(draft_id, tmp_path / "drafts")
    dice = draft["ability_dice"]
    assert set(dice) == set(draft["abilities"])
    for name, score in draft["abilities"].items():
        assert len(dice[name]) == 3
        assert all(1 <= d <= 6 for d in dice[name])
        assert sum(dice[name]) == score


def test_abilities_page_shows_individual_dice(client, tmp_path):
    draft_id = _start_draft(client)
    client.post(f"/wizard/{draft_id}/abilities/roll")
    draft = load_draft(draft_id, tmp_path / "drafts")
    str_dice = draft["ability_dice"]["STR"]
    r = client.get(f"/wizard/{draft_id}/abilities")
    assert " + ".join(str(d) for d in str_dice) in r.text


def test_per_die_results_not_persisted_to_character(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    client.post(f"/wizard/{draft_id}/finalize")
    char_text = (tmp_path / "characters" / "thorin.json").read_text()
    assert "ability_dice" not in char_text


def test_race_and_class_pages_show_ability_summary(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})

    r = client.get(f"/wizard/{draft_id}/race")
    assert "ability-strip" in r.text
    assert "15" in r.text  # STR score visible on the race step

    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = client.get(f"/wizard/{draft_id}/class")
    assert "ability-strip" in r.text


def _override_abilities(tmp_path, draft_id, abilities):
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["abilities"] = abilities
    save_draft(draft_id, draft, tmp_path / "drafts")


def test_race_card_is_trimmed_and_carries_detail(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 12, "INT": 12, "WIS": 12, "DEX": 12, "CON": 12, "CHA": 12
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    r = client.get(f"/wizard/{draft_id}/race")
    assert r.status_code == 200
    # Trimmed: no Movement line, no "languages" count line.
    assert "Movement:" not in r.text
    assert "languages</div>" not in r.text
    # Book detail body present (hidden) for the modal to inject.
    assert 'class="detail-body"' in r.text
    assert 'data-role="select"' in r.text  # shared shell rendered on the page


def test_class_card_carries_detail_and_reason(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    r = client.get(f"/wizard/{draft_id}/class")
    assert r.status_code == 200
    assert 'class="detail-body"' in r.text
    # A class Dwarf can't take (e.g. magic_user) carries a select reason.
    assert "Not available to Dwarf" in r.text


def _to_spells_step(client, tmp_path, draft_id):
    _override_abilities(tmp_path, draft_id, {
        "STR": 10, "INT": 16, "WIS": 10, "DEX": 12, "CON": 12, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return client.get(f"/wizard/{draft_id}/class_setup")  # spells live on this step


def test_spell_cards_have_learn_and_expander_not_jammed(client, tmp_path):
    draft_id = _start_draft(client)
    r = _to_spells_step(client, tmp_path, draft_id)
    assert r.status_code == 200
    # Learn button + expander body present.
    assert "btn-learn" in r.text
    assert "spell-detail" in r.text
    # The card no longer dumps the full description inline as a card-detail.
    assert 'class="card-detail small">{{' not in r.text  # sanity: no raw template


def test_full_wizard_flow_creates_character(client, tmp_path):
    draft_id = _start_draft(client)
    # Force abilities that meet Dwarf (CON 9+)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })

    # Abilities (name moved to identity step)
    r = client.post(f"/wizard/{draft_id}/abilities", data={})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/race"

    # Race
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/class"

    # Class
    r = client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/adjust"

    # Ability adjustments (skip)
    r = client.post(f"/wizard/{draft_id}/adjust", data={})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/class_setup"

    # HP roll
    r = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r.status_code == 303
    draft = load_draft(draft_id, tmp_path / "drafts")
    assert 1 <= draft["hp_roll"] <= 8

    # HP advances to identity
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/identity"

    # Identity (name + alignment)
    r = client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/equipment"

    # Roll starting gold (now a deliberate button press), then continue.
    r = client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    assert r.status_code == 303
    r = client.post(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/review"

    # Review renders the built sheet
    r = client.get(f"/wizard/{draft_id}/review")
    assert r.status_code == 200
    assert "Thorin" in r.text
    assert "Dwarf" in r.text
    assert "Fighter 1" in r.text

    # Finalize
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.status_code == 303
    assert r.headers["location"] == "/character/thorin"

    # Draft is gone, character file exists
    char_path = tmp_path / "characters" / "thorin.json"
    assert char_path.exists()
    draft_path = tmp_path / "drafts" / f"{draft_id}.json"
    assert not draft_path.exists()


def test_unique_id_on_name_collision(client, tmp_path):
    # Pre-existing character with the same slug
    # (the fixture's create_app already created characters/ during bootstrap)
    (tmp_path / "characters").mkdir(exist_ok=True)
    (tmp_path / "characters" / "thorin.json").write_text("{}")

    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/finalize")
    assert r.headers["location"] == "/character/thorin-2"


def test_race_rejected_if_abilities_too_low(client, tmp_path):
    draft_id = _start_draft(client)
    _override_abilities(tmp_path, draft_id, {
        "STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 5, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    r = client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    assert r.status_code == 400


def test_gate_redirects_to_first_incomplete_step(client):
    draft_id = _start_draft(client)
    # Jump straight to review without completing prerequisites
    r = client.get(f"/wizard/{draft_id}/review")
    assert r.status_code == 303
    assert r.headers["location"] == f"/wizard/{draft_id}/abilities"


def test_cancel_deletes_draft(client, tmp_path):
    draft_id = _start_draft(client)
    r = client.post(f"/wizard/{draft_id}/cancel")
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert not (tmp_path / "drafts" / f"{draft_id}.json").exists()


def test_index_has_new_character_button(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "New Character" in r.text
    assert 'href="/wizard/new"' in r.text


def test_bootstrap_seeds_from_examples(tmp_path):
    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    (examples_dir / "sample.json").write_text('{"name": "Sample"}')

    create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    assert (characters_dir / "sample.json").exists()


def _advance_to_equipment(client, tmp_path, draft_id):
    """Advance a fresh draft through all pre-equipment steps."""
    _override_abilities(tmp_path, draft_id, {
        "STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10
    })
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Boxtest", "alignment": "neutral"})


def test_wizard_use_as_container_promotes_loose_backpack(client, tmp_path):
    draft_id = _start_draft(client)
    _advance_to_equipment(client, tmp_path, draft_id)
    # Inject a loose backpack directly into the items list (bypassing the add
    # route, which already promotes Container items).
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft.setdefault("items", []).append(
        {"instance_id": "bp_test", "catalog_id": "backpack",
         "location": {"kind": "carried"}}
    )
    save_draft(draft_id, draft, tmp_path / "drafts")
    # Promote the loose backpack to a container instance
    r = client.post(f"/wizard/{draft_id}/inventory/use-as-container",
                    data={"owner_kind": "carried", "item_id": "backpack"})
    assert r.status_code == 303
    draft = load_draft(draft_id, tmp_path / "drafts")
    # Loose backpack gone from items; a container instance promoted
    assert not any(i.get("catalog_id") == "backpack" for i in draft.get("items", []))
    assert any(c.get("catalog_id") == "backpack" for c in draft.get("containers", []))


def test_wizard_equipment_renders_with_a_container(client, tmp_path):
    """The equipment step must render its container_modal without error when a
    container is present in inventory (regression: stale 4th macro arg)."""
    draft_id = _start_draft(client)
    _advance_to_equipment(client, tmp_path, draft_id)
    # The inventory box (and its container modals) only render once gold is rolled.
    client.post(f"/wizard/{draft_id}/equipment/roll-gold")
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft.setdefault("items", []).append(
        {"instance_id": "bp_test", "catalog_id": "backpack",
         "location": {"kind": "carried"}}
    )
    save_draft(draft_id, draft, tmp_path / "drafts")
    client.post(f"/wizard/{draft_id}/inventory/use-as-container",
                data={"owner_kind": "carried", "item_id": "backpack"})
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200
    assert "modal-container-" in r.text


def test_bootstrap_skipped_when_characters_present(tmp_path):
    characters_dir = tmp_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "existing.json").write_text("{}")
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    (examples_dir / "sample.json").write_text("{}")

    create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir,
    )
    assert (characters_dir / "existing.json").exists()
    assert not (characters_dir / "sample.json").exists()
