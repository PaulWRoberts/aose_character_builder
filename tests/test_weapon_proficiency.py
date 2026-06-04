"""Weapon Proficiency optional rule — engine."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.proficiency import (
    base_slot_count,
    combat_category,
    improvements_through_level,
    nonproficiency_penalty,
    proficiency_slots,
)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_combat_category_derivation():
    data = GameData.load(DATA_DIR)
    assert combat_category(data.classes["fighter"]) == "martial"
    assert combat_category(data.classes["cleric"]) == "semi_martial"
    assert combat_category(data.classes["magic_user"]) == "non_martial"


def test_base_slot_count_by_category():
    assert base_slot_count("martial") == 4
    assert base_slot_count("semi_martial") == 3
    assert base_slot_count("non_martial") == 1


def test_nonproficiency_penalty_by_category():
    assert nonproficiency_penalty("martial") == -2
    assert nonproficiency_penalty("semi_martial") == -3
    assert nonproficiency_penalty("non_martial") == -5


def test_improvements_through_level_fighter():
    data = GameData.load(DATA_DIR)
    fighter = data.classes["fighter"]
    assert improvements_through_level(fighter, 1) == 0
    assert improvements_through_level(fighter, 4) == 1   # drop at L4
    assert improvements_through_level(fighter, 7) == 2   # +drop at L7
    assert improvements_through_level(fighter, 13) == 4  # L4/7/10/13


def test_proficiency_slots_full_leveling():
    data = GameData.load(DATA_DIR)
    fighter = data.classes["fighter"]
    assert proficiency_slots(fighter, 1) == 4
    assert proficiency_slots(fighter, 7) == 6
    assert proficiency_slots(fighter, 13) == 8
    assert proficiency_slots(data.classes["cleric"], 1) == 3
    assert proficiency_slots(data.classes["magic_user"], 1) == 1
    assert proficiency_slots(data.classes["magic_user"], 6) == 2  # first drop at L6


# ---------------------------------------------------------------------------
# Task 5: per-weapon proficiency fields on CharacterSpec
# ---------------------------------------------------------------------------
from aose.models import CharacterSpec, ClassEntry, RuleSet


def _base_spec(**over):
    kwargs = dict(
        name="X",
        abilities={"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10},
        race_id="dwarf",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="law",
    )
    kwargs.update(over)
    return CharacterSpec(**kwargs)


def test_new_proficiency_fields_default_empty():
    spec = _base_spec()
    assert spec.weapon_proficiencies == []
    assert spec.weapon_specialisations == []


def test_legacy_chosen_proficiencies_is_dropped_on_load():
    raw = _base_spec().model_dump()
    raw["chosen_proficiencies"] = ["sword", "axe"]
    spec = CharacterSpec.model_validate(raw)  # must not raise under extra=forbid
    assert not hasattr(spec, "chosen_proficiencies")
    assert spec.weapon_proficiencies == []


def test_proficiency_config_removed():
    import aose.models as m
    assert not hasattr(m, "ProficiencyConfig")
    from aose.models import CharClass
    assert "proficiency" not in CharClass.model_fields


from aose.engine.proficiency import (
    category_for_classes,
    is_proficient,
    is_specialised,
    penalty_for_classes,
    slots_spent,
    specialisation_allowed,
    total_proficiency_slots,
)


def test_is_proficient_and_specialised():
    spec = _base_spec(weapon_proficiencies=["sword", "spear"],
                      weapon_specialisations=["sword"])
    assert is_proficient("sword", spec) is True
    assert is_proficient("spear", spec) is True
    assert is_proficient("club", spec) is False
    assert is_specialised("sword", spec) is True
    assert is_specialised("spear", spec) is False


def test_slots_spent_counts_specialisation_extra():
    spec = _base_spec(weapon_proficiencies=["sword", "spear"],
                      weapon_specialisations=["sword"])
    # 2 proficiencies + 1 specialisation extra = 3 slots
    assert slots_spent(spec) == 3


def test_multiclass_category_and_penalty_most_martial(data):
    fighter = data.classes["fighter"]        # martial
    magic_user = data.classes["magic_user"]  # non_martial
    assert category_for_classes([fighter, magic_user]) == "martial"
    assert penalty_for_classes([fighter, magic_user]) == -2
    assert specialisation_allowed([fighter, magic_user]) is True
    assert specialisation_allowed([magic_user]) is False


def test_total_proficiency_slots_is_max_over_classes(data):
    fighter = data.classes["fighter"]        # 4 @ L1
    magic_user = data.classes["magic_user"]  # 1 @ L1
    assert total_proficiency_slots([(fighter, 1), (magic_user, 1)]) == 4


# ---------------------------------------------------------------------------
# Task 10: wizard per-weapon proficiency picker
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient

from aose.characters import load_character, load_draft, save_draft, save_settings
from aose.web.app import create_app


@pytest.fixture
def client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, RuleSet(weapon_proficiency=True))
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    c = TestClient(app, follow_redirects=False)
    c._settings_path = settings_path
    c._drafts_dir = drafts_dir
    c._characters_dir = characters_dir
    return c


def _start_fighter(client):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 15, "INT": 11, "WIS": 12, "DEX": 13, "CON": 14, "CHA": 10}
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "dwarf"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return draft_id


def _start_magic_user(client, optional_staves=False):
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = {"STR": 10, "INT": 15, "WIS": 11, "DEX": 13, "CON": 12, "CHA": 10}
    if optional_staves:
        draft.setdefault("ruleset", {})["optional_staves"] = True
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/abilities", data={})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    return draft_id


def test_fighter_picker_shows_four_slots_and_weapons(client):
    draft_id = _start_fighter(client)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "4" in r.text
    assert "Sword" in r.text
    assert "Specialise" in r.text


def test_magic_user_picker_shows_one_slot_filtered(client):
    draft_id = _start_magic_user(client)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "Dagger" in r.text
    # Staff is combat-optional; not offered unless the optional_staves rule is on.
    assert "Staff" not in r.text
    assert "Sword" not in r.text
    assert "Specialise" not in r.text


def test_magic_user_picker_shows_staff_when_rule_on(client):
    draft_id = _start_magic_user(client, optional_staves=True)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "Staff" in r.text


def test_magic_user_can_take_staff_proficiency_when_rule_on(client):
    draft_id = _start_magic_user(client, optional_staves=True)
    r = client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["staff"]})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["staff"]


def test_magic_user_post_one_weapon_advances(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["dagger"]})
    assert r.status_code == 303
    assert r.headers["location"].endswith("/class_setup")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["dagger"]


def test_post_wrong_count_rejected(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["dagger", "staff"]})
    assert r.status_code == 400


def test_post_disallowed_weapon_rejected(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["sword"]})
    assert r.status_code == 400


def test_fighter_specialise_costs_two_slots(client):
    draft_id = _start_fighter(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["sword", "spear", "mace"], "specialise": ["sword"]})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["proficiencies"]["weapons"] == ["sword", "spear", "mace"]
    assert draft["proficiencies"]["specialisations"] == ["sword"]


def test_specialise_for_non_martial_rejected(client):
    draft_id = _start_magic_user(client)
    r = client.post(f"/wizard/{draft_id}/proficiencies",
                    data={"weapon": ["dagger"], "specialise": ["dagger"]})
    assert r.status_code == 400


def test_proficiencies_persist_to_character(client):
    draft_id = _start_fighter(client)
    client.post(f"/wizard/{draft_id}/proficiencies",
                data={"weapon": ["sword", "spear", "mace", "hand_axe"]})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    spec = load_character(char_id, client._characters_dir)
    assert set(spec.weapon_proficiencies) == {"sword", "spear", "mace", "hand_axe"}


# ---------------------------------------------------------------------------
# Task 11: sheet per-weapon proficiency view + weapon qualities reference
# ---------------------------------------------------------------------------
from aose.sheet.view import build_sheet


def test_sheet_proficiency_view_per_weapon(data):
    spec = _base_spec(
        weapon_proficiencies=["sword", "spear"],
        weapon_specialisations=["sword"],
        ruleset=RuleSet(weapon_proficiency=True),
    )
    sheet = build_sheet(spec, data)
    view = sheet.proficiencies
    names = {p.name for p in view.weapons}
    assert names == {"Sword", "Spear"}
    sword = next(p for p in view.weapons if p.name == "Sword")
    assert sword.specialised is True
    assert view.category == "martial"
    assert view.penalty == -2


def test_sheet_proficiency_view_empty_when_rule_off(data):
    spec = _base_spec(weapon_proficiencies=["sword"],
                      ruleset=RuleSet(weapon_proficiency=False))
    sheet = build_sheet(spec, data)
    assert sheet.proficiencies is None
    assert sheet.weapon_proficiency_active is False


def test_sheet_lists_qualities_reference_for_equipped_weapons(data):
    spec = _base_spec(
        inventory=["sword"],
        equipped_weapons=["sword"],
        ruleset=RuleSet(weapon_proficiency=True),
        weapon_proficiencies=["sword"],
    )
    sheet = build_sheet(spec, data)
    ref_ids = {q.id for q in sheet.weapon_qualities_reference}
    assert "melee" in ref_ids


# ---------------------------------------------------------------------------
# Enchanted weapon variants normalise to their base weapon type for proficiency
# ---------------------------------------------------------------------------
from aose.engine.attacks import attack_profiles
from aose.engine.proficiency import base_weapon_id


def test_enchanted_weapon_uses_base_weapon_proficiency(data):
    from aose.engine.enchant import add_free_enchanted, equip
    from aose.models import Enchantment
    import copy
    d = copy.deepcopy(data)
    d.enchantments["sword_plus_1_prof"] = Enchantment(
        id="sword_plus_1_prof", name_template="{base} +1", kind="weapon",
        applies_to={"include": ["sword"]}, magic_bonus=1)
    spec = _base_spec(
        ruleset=RuleSet(weapon_proficiency=True),
        weapon_proficiencies=["short_sword"],
        weapon_specialisations=["short_sword"],
    )
    spec.enchanted = add_free_enchanted([], "short_sword", "sword_plus_1_prof", d)
    spec.enchanted = equip(spec.enchanted, spec.enchanted[0].instance_id)
    profiles = attack_profiles(spec, d)
    ench_prof = next(p for p in profiles if p.name.startswith("Short Sword +1"))
    assert ench_prof.proficient is True


def test_sheet_html_renders_per_weapon_section(client):
    draft_id = _start_fighter(client)
    client.post(f"/wizard/{draft_id}/proficiencies",
                data={"weapon": ["sword", "spear", "mace", "hand_axe"]})
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Thorin", "alignment": "law"})
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    r = client.get(f"/character/{char_id}")
    assert "Weapon Proficiencies" in r.text
    assert "Sword" in r.text
    assert "&minus;2" in r.text
