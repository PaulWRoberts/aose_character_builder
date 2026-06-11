"""Routes for viewing and editing the project-wide default :class:`RuleSet`."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from aose.web.templating import make_templates

from aose.characters import load_settings, save_settings
from aose.engine.sources import CLASSIC_SOURCE_ID
from aose.models import RuleSet

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = make_templates(str(TEMPLATES_DIR))


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
    "strict_mode": "Strict Mode",
    "optional_staves": "Spellcasters and Staves",
    "two_weapon_fighting": "Attacking with Two Weapons",
    "individual_initiative": "Individual Initiative",
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
    "strict_mode",
    "optional_staves",
    "two_weapon_fighting",
    "individual_initiative",
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
        ("strict_mode",
         "Ability scores, hit points, and starting gold are locked after a "
         "single roll (a hopeless ability set may always be re-rolled). Turn "
         "off to allow free re-rolls."),
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
        ("optional_staves",
         "Magic-users and illusionists may wield a staff in combat."),
        ("two_weapon_fighting",
         "Characters with STR or DEX as a prime requisite may wield a small "
         "weapon in the off hand: −2 to the primary attack, an extra off-hand "
         "attack at −4."),
        ("individual_initiative",
         "Roll initiative for each combatant individually, modified by DEX, "
         "instead of one roll per side. Shows your initiative modifier on the "
         "sheet."),
    ]),
]

# Name of the rule group whose inputs are disabled when Basic is selected.
ADVANCED_OPTIONS_GROUP = "Advanced Options"

# Flat field -> description map (UI copy). Keyed by RuleSet field name so the
# SOURCE_RULES tree carries structure only, not prose.
RULE_DESCRIPTIONS = {
    "separate_race_class":
        "Choose race and class separately. Off = Basic: pick a class that "
        "determines race (race-as-class), with no separate race step; "
        "multi-classing and lifting demihuman restrictions are unavailable.",
    "lift_demihuman_restrictions":
        "Demihuman races ignore their normal class options and per-class "
        "maximum-level caps.",
    "human_racial_abilities":
        "Humans gain optional racial abilities: +1 CHA, +1 CON, and Blessed "
        "(roll HP twice, keep the better). Requires lifting demihuman "
        "restrictions.",
    "multiclassing":
        "Demihumans may pursue two or three classes simultaneously, sharing XP.",
    "weapon_proficiency":
        "Characters are only proficient with specific weapons; non-proficient "
        "attacks suffer −2 to hit.",
    "secondary_skills":
        "Each character has a secondary skill (a non-adventuring trade).",
    "optional_staves":
        "Magic-users and illusionists may wield a staff in combat.",
    "two_weapon_fighting":
        "Characters with STR or DEX as a prime requisite may wield a small "
        "weapon in the off hand: −2 to the primary attack, an extra off-hand "
        "attack at −4.",
    "advanced_spell_books":
        "Arcane spell books have no size limit and the number of beginning "
        "spells is set by Intelligence. Off = standard rules: the book holds "
        "exactly the spells the caster can memorise.",
    "ascending_ac":
        "Show armour class as ascending (10 = unarmoured) and use Attack Bonus, "
        "instead of descending (9 = unarmoured) with THAC0.",
    "variable_weapon_damage":
        "Each weapon rolls its specific damage die instead of the default 1d6.",
    "reroll_1s_2s_hp_l1":
        "When rolling 1st-level HP, re-roll any result of 1 or 2.",
    "individual_initiative":
        "Roll initiative for each combatant individually, modified by DEX, "
        "instead of one roll per side. Shows your initiative modifier on the "
        "sheet.",
}


def _rule(field, *children):
    return {"kind": "rule", "field": field, "children": list(children)}


def _choice(field):
    return {"kind": "choice", "field": field}


# Optional rules attributed to the source they come from, in display order.
# Nesting expresses dependencies: a child rule is unavailable when any ancestor
# is unchecked. Sources absent from this map (Carcass Crawler 1 & 3) contribute
# no optional rules.
SOURCE_RULES = {
    "ose_classic_fantasy": [
        _rule("ascending_ac"),
        _rule("variable_weapon_damage"),
        _rule("reroll_1s_2s_hp_l1"),
        _rule("individual_initiative"),
        _choice("encumbrance"),
    ],
    "ose_advanced_fantasy": [
        _rule("separate_race_class",
              _rule("lift_demihuman_restrictions",
                    _rule("human_racial_abilities")),
              _rule("multiclassing")),
        _rule("secondary_skills"),
        _rule("weapon_proficiency"),
        _rule("optional_staves"),
        _rule("two_weapon_fighting"),
        _rule("advanced_spell_books"),
    ],
}


def flatten_rule_fields(tree):
    """Depth-first list of every rule node's field in a SOURCE_RULES subtree
    (choice nodes contribute None)."""
    out = []
    for node in tree:
        out.append(None if node.get("kind") == "choice" else node.get("field"))
        out.extend(flatten_rule_fields(node.get("children", [])))
    return out


def content_rows_for_source(data, source_id, ruleset):
    """Build the Content subsection rows for a source: one row per derived
    category, with display label, locked flag (Classic), and current state."""
    from aose.engine.sources import (
        CLASSIC_SOURCE_ID,
        source_content_categories,
    )
    sources_with_races = {r.source for r in data.races.values()} - {CLASSIC_SOURCE_ID}
    cats = source_content_categories(data).get(source_id, [])
    locked = source_id == CLASSIC_SOURCE_ID
    rows = []
    for cat in cats:
        if cat == "equipment":
            label = "Equipment"
        elif cat == "magic_items":
            label = "Magic Items"
        else:  # classes
            label = "Classes & Races" if source_id in sources_with_races else "Classes"
        key = f"{source_id}:{cat}"
        rows.append({
            "category": cat,
            "label": label,
            "locked": locked,
            "enabled": locked or key not in ruleset.disabled_content,
            "key": key,
            "field": f"content_{key}",
        })
    return rows


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
    sources = sorted(
        request.app.state.game_data.sources.values(),
        key=lambda s: (not s.core, s.name),
    )
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
            "sources": sources,
            "classic_source_id": CLASSIC_SOURCE_ID,
            "saved": saved,
        },
    )


def parse_ruleset_from_form(form, source_ids=None) -> RuleSet:
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

    from aose.models import CONTENT_CATEGORIES  # local import avoids a cycle at module load

    disabled_content = []
    for sid in (source_ids or []):
        if sid == CLASSIC_SOURCE_ID:
            continue
        if f"source_{sid}" not in form:
            disabled_content.extend(f"{sid}:{cat}" for cat in CONTENT_CATEGORIES)

    return RuleSet(**bools, **choices, disabled_content=disabled_content)


@router.post("/settings")
async def post_settings(request: Request):
    form = await request.form()
    source_ids = list(request.app.state.game_data.sources)
    new_ruleset = parse_ruleset_from_form(form, source_ids=source_ids)
    save_settings(_settings_path(request), new_ruleset)
    return RedirectResponse("/settings?saved=1", status_code=303)
