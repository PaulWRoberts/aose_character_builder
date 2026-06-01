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
    "reroll_1s_2s_hp_l1": "Reroll 1s & 2s for HP at L1",
    "lift_demihuman_restrictions": "Lift Demihuman Class & Level Restrictions",
    "secondary_skills": "Secondary Skills",
    "multiclassing": "Multiclassing",
    "advanced_spell_books": "Advanced Spell Books",
    "human_racial_abilities": "Human Racial Abilities",
}

# Rules whose engine/builder integration is fully wired up.  The settings
# page marks unimplemented rules so the user knows their choice is persisted
# but not yet enforced.
IMPLEMENTED_RULES = {
    "ascending_ac",
    "reroll_1s_2s_hp_l1",
    "secondary_skills",
    "lift_demihuman_restrictions",
    "weapon_proficiency",
    "multiclassing",
    "variable_weapon_damage",
    "advanced_spell_books",
    "human_racial_abilities",
}

# Choice-group rules that have full integration too.
IMPLEMENTED_CHOICE_GROUPS = {"encumbrance"}

RULE_GROUPS = [
    ("Advanced Options", [
        ("multiclassing",
         "Demihumans may pursue two or three classes simultaneously, sharing XP."),
        ("lift_demihuman_restrictions",
         "Demihuman races ignore their normal class options and per-class "
         "maximum-level caps."),
        ("human_racial_abilities",
         "Humans gain optional racial abilities: +1 CHA, +1 CON, and Blessed "
         "(roll HP twice, keep the better). Requires lifting demihuman "
         "restrictions."),
    ]),
    ("Character Options", [
        ("weapon_proficiency",
         "Characters are only proficient with specific weapons; non-proficient "
         "attacks suffer −2 to hit."),
        ("secondary_skills",
         "Each character has a secondary skill (a non-adventuring trade)."),
    ]),
    ("Survivability & Logistics", [
        ("reroll_1s_2s_hp_l1",
         "When rolling 1st-level HP, re-roll any result of 1 or 2."),
    ]),
    ("Magic", [
        ("advanced_spell_books",
         "Arcane spell books have no size limit and the number of beginning "
         "spells is set by Intelligence. Off = standard rules: the book holds "
         "exactly the spells the caster can memorise."),
    ]),
    ("Combat", [
        ("variable_weapon_damage",
         "Each weapon rolls its specific damage die instead of the default 1d6."),
        ("ascending_ac",
         "Show armour class as ascending (10 = unarmoured) and use Attack Bonus, "
         "instead of descending (9 = unarmoured) with THAC0."),
    ]),
]

# Name of the rule group whose inputs are disabled when Basic is selected.
ADVANCED_OPTIONS_GROUP = "Advanced Options"

CHOICE_GROUPS = [
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
            "advanced_options_group": ADVANCED_OPTIONS_GROUP,
            "saved": saved,
        },
    )


def parse_ruleset_from_form(form) -> RuleSet:
    """Build a :class:`RuleSet` from the toggle/radio form fields used by the
    settings page AND the wizard's per-character rules step.

    ``creation_method`` (a radio with values ``"advanced"`` / ``"basic"``) is
    the single source for ``separate_race_class``: Advanced ⇒ True. When Basic
    is chosen the Advanced-only rules (``multiclassing`` and
    ``lift_demihuman_restrictions``) are forced off regardless of what was
    posted. Unknown radio choices are silently dropped so the RuleSet defaults
    take over."""
    bool_field_names = {
        field for _, fields in RULE_GROUPS for field, _ in fields
    }
    bools = {field: field in form for field in bool_field_names}

    # Creation method radio → separate_race_class (default Advanced when absent).
    advanced = form.get("creation_method") != "basic"
    bools["separate_race_class"] = advanced
    if not advanced:
        bools["multiclassing"] = False
        bools["lift_demihuman_restrictions"] = False

    # human_racial_abilities is gated behind BOTH Advanced and lifted demihuman
    # restrictions — force it off unless both hold (mirrors the rules-page JS).
    if not (bools["separate_race_class"] and bools.get("lift_demihuman_restrictions")):
        bools["human_racial_abilities"] = False

    choices = {}
    for field, _label, options in CHOICE_GROUPS:
        chosen = form.get(field)
        valid_values = [v for v, _ in options]
        if chosen in valid_values:
            choices[field] = chosen

    return RuleSet(**bools, **choices)


@router.post("/settings")
async def post_settings(request: Request):
    form = await request.form()
    new_ruleset = parse_ruleset_from_form(form)
    save_settings(_settings_path(request), new_ruleset)
    return RedirectResponse("/settings?saved=1", status_code=303)
