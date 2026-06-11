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


def _ruleset_view_context(request, ruleset):
    """Shared template context for the source-panel ruleset form. `ruleset` must
    be a RuleSet **object** (content_rows_for_source reads `.disabled_content`).
    The template subscripts it (`ruleset['field']`) — Jinja's `[]` falls back to
    attribute access, so the object works directly."""
    from aose.engine.sources import CLASSIC_SOURCE_ID as _CLASSIC
    data = request.app.state.game_data
    sources = sorted(data.sources.values(), key=lambda s: (not s.core, s.name))
    panels = []
    for src in sources:
        panels.append({
            "source": src,
            "content_rows": content_rows_for_source(data, src.id, ruleset),
            "rule_tree": SOURCE_RULES.get(src.id, []),
        })
    return {
        "ruleset": ruleset,
        "panels": panels,
        "rule_labels": RULE_LABELS,
        "rule_descriptions": RULE_DESCRIPTIONS,
        "choice_groups": CHOICE_GROUPS,
        "classic_source_id": _CLASSIC,
    }


def _content_keys(request):
    from aose.engine.sources import CLASSIC_SOURCE_ID as _CLASSIC, source_content_categories
    data = request.app.state.game_data
    cats = source_content_categories(data)
    return [
        f"{sid}:{cat}"
        for sid, cs in cats.items()
        if sid != _CLASSIC
        for cat in cs
    ]


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    ruleset = load_settings(_settings_path(request))
    saved = request.query_params.get("saved") == "1"
    context = _ruleset_view_context(request, ruleset)
    context["saved"] = saved
    return templates.TemplateResponse(request, "settings.html", context)


def _enforce_rule_tree(bools, tree):
    """Force every descendant off when an ancestor rule is unchecked."""
    for node in tree:
        field = node.get("field")
        children = node.get("children", [])
        if field is not None and not bools.get(field, False):
            for f in flatten_rule_fields(children):
                if f is not None:
                    bools[f] = False
        else:
            _enforce_rule_tree(bools, children)


def parse_ruleset_from_form(form, content_keys=None) -> RuleSet:
    """Build a :class:`RuleSet` from the per-source panel form used by both the
    settings page and the wizard's /rules step.

    Bool rule fields come from checkbox presence; `strict_mode` is standalone.
    The SOURCE_RULES nesting is enforced server-side: a child rule is forced off
    whenever any ancestor is unchecked (replaces the old creation_method / lift
    special cases). `disabled_content` lists every content-category key whose
    checkbox was absent."""
    rule_fields = set()
    for tree in SOURCE_RULES.values():
        rule_fields |= {f for f in flatten_rule_fields(tree) if f is not None}
    rule_fields.add("strict_mode")  # standalone toggle

    bools = {field: field in form for field in rule_fields}
    for tree in SOURCE_RULES.values():
        _enforce_rule_tree(bools, tree)

    choices = {}
    for field, _label, options in CHOICE_GROUPS:
        chosen = form.get(field)
        if chosen in [v for v, _ in options]:
            choices[field] = chosen

    disabled_content = [
        key for key in (content_keys or []) if f"content_{key}" not in form
    ]

    return RuleSet(**bools, **choices, disabled_content=disabled_content)


@router.post("/settings")
async def post_settings(request: Request):
    form = await request.form()
    new_ruleset = parse_ruleset_from_form(form, content_keys=_content_keys(request))
    save_settings(_settings_path(request), new_ruleset)
    return RedirectResponse("/settings?saved=1", status_code=303)
