"""Routes for viewing and editing the project-wide default :class:`RuleSet`."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aose.characters import load_settings, save_settings
from aose.models import RuleSet

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


RULE_LABELS = {
    "ascending_ac": "Ascending AC",
    "variable_weapon_damage": "Variable Weapon Damage",
    "weapon_proficiency": "Weapon Proficiency",
    "max_hp_at_l1": "Max HP at L1",
    "reroll_1s_2s_hp_l1": "Reroll 1s & 2s for HP at L1",
    "demihuman_level_limits": "Demihuman Level Limits",
    "demihuman_class_restrictions": "Demihuman Class Restrictions",
    "separate_race_class": "Separate Race & Class",
    "secondary_skills": "Secondary Skills",
    "multiclassing": "Multiclassing",
}

# Rules whose engine/builder integration is fully wired up.  The settings
# page marks unimplemented rules so the user knows their choice is persisted
# but not yet enforced.
IMPLEMENTED_RULES = {
    "ascending_ac",
    "max_hp_at_l1",
    "reroll_1s_2s_hp_l1",
    "secondary_skills",
    "demihuman_level_limits",
    "demihuman_class_restrictions",
    "weapon_proficiency",
    "separate_race_class",
    "multiclassing",
    "variable_weapon_damage",
}

# Choice-group rules that have full integration too.
IMPLEMENTED_CHOICE_GROUPS = {"ability_roll_method", "encumbrance"}

RULE_GROUPS = [
    ("Combat", [
        ("ascending_ac",
         "Show armour class as ascending (10 = unarmoured) and use Attack Bonus, "
         "instead of descending (9 = unarmoured) with THAC0."),
        ("variable_weapon_damage",
         "Each weapon rolls its specific damage die instead of the default 1d6."),
        ("weapon_proficiency",
         "Characters are only proficient with specific weapons; non-proficient "
         "attacks suffer −2 to hit."),
    ]),
    ("Hit Points (1st Level)", [
        ("max_hp_at_l1",
         "Take the maximum result on the hit die instead of rolling at 1st level."),
        ("reroll_1s_2s_hp_l1",
         "When rolling 1st-level HP, re-roll any result of 1 or 2."),
    ]),
    ("Demihumans", [
        ("demihuman_level_limits",
         "Demihuman races have a maximum level in each class."),
        ("demihuman_class_restrictions",
         "Demihuman races may only enter certain classes."),
        ("separate_race_class",
         "Race and class are chosen independently.  Disable for classic "
         "race-as-class (Dwarf/Elf/Halfling are entire classes)."),
    ]),
    ("Skills & Multiclass", [
        ("secondary_skills",
         "Each character has a secondary skill (a non-adventuring trade)."),
        ("multiclassing",
         "Demihumans may pursue two or three classes simultaneously, sharing XP."),
    ]),
]

CHOICE_GROUPS = [
    ("ability_roll_method", "Ability Score Method", [
        ("3d6_in_order", "3d6 in order — traditional and most deadly"),
        ("3d6_arrange", "3d6, arrange to taste"),
        ("4d6_drop_lowest", "4d6, drop the lowest"),
    ]),
    ("encumbrance", "Encumbrance", [
        ("none", "None — ignore encumbrance entirely"),
        ("basic", "Basic — track only armour and significant loads"),
        ("detailed", "Detailed — track item-by-item weight in coins"),
    ]),
]


def _settings_path(request: Request) -> Path:
    return request.app.state.settings_path


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    ruleset = load_settings(_settings_path(request))
    saved = request.query_params.get("saved") == "1"
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "ruleset": ruleset,
            "rule_groups": RULE_GROUPS,
            "choice_groups": CHOICE_GROUPS,
            "rule_labels": RULE_LABELS,
            "implemented_rules": IMPLEMENTED_RULES,
            "implemented_choice_groups": IMPLEMENTED_CHOICE_GROUPS,
            "saved": saved,
        },
    )


@router.post("/settings")
async def post_settings(request: Request):
    form = await request.form()

    bool_field_names = {
        field for _, fields in RULE_GROUPS for field, _ in fields
    }
    bools = {field: field in form for field in bool_field_names}

    choices = {}
    for field, _label, options in CHOICE_GROUPS:
        chosen = form.get(field)
        valid_values = [v for v, _ in options]
        if chosen in valid_values:
            choices[field] = chosen

    new_ruleset = RuleSet(**bools, **choices)
    save_settings(_settings_path(request), new_ruleset)
    return RedirectResponse("/settings?saved=1", status_code=303)
