# Source-organized content & optional rules — design

**Date:** 2026-06-10
**Status:** approved (pending spec review)
**Touches:** `/settings` page, wizard `/rules` step, `RuleSet` model, `aose/engine/sources.py`,
the source-filter call sites, `settings_routes.py`, `_ruleset_fields.html`.

## Motivation

Carcass Crawler optional rules are arriving, so the ruleset UI needs to (a) attribute
every optional rule to the source it comes from and (b) let the user enable/disable
content at a finer grain than whole-source. Today `RuleSet.disabled_sources` is
all-or-nothing per source, and optional rules are grouped *thematically* (Combat,
Magic, …) with no source attribution.

The new layout (both `/settings` and the wizard `/rules` step, which share
`_ruleset_fields.html`):

```
Strict Mode                      ← standalone toggle, NOT a source rule

Classic Fantasy
  Content (locked)
    Classes · Equipment · Magic Items
  Optional Rules
    Ascending AC · Variable Weapon Damage · Reroll 1s & 2s
    Individual Initiative · Encumbrance (none/basic/detailed)

Advanced Fantasy
  Content
    Classes & Races · Magic Items
  Optional Rules
    Separate Race and Class
      Lifting Class & Level Restrictions
        Human Racial Abilities
      Multi-Classing
    Secondary Skills · Weapon Proficiency
    Spellcasters and Staves · Attacking with Two Weapons · Advanced Spell Books

Carcass Crawler Issue 1
  Content
    Classes & Races

Carcass Crawler Issue 3
  Content
    Classes & Races · Equipment
```

Each source is an expandable panel. Classic Fantasy content is locked (always on).

## Scope

In scope: the two pages above, the `RuleSet` storage shape, the source-filter helper,
and every existing call site that filters by source (so the granular toggles genuinely
gate content). Out of scope: any new Carcass Crawler *rules content* itself — this is
the organizing chassis those rules will slot into.

## Data model

### Content categories (derived, not declared)

A **content category** is one of `classes`, `equipment`, `magic_items`. It is computed
from already-loaded `GameData`, not tagged on items:

- `classes`  — the source has any `CharClass` or `Race` (spell lists ride along).
- `equipment` — the source has any non-magic `Item` (`item_type != "magic"` and not `magic`).
- `magic_items` — the source has any `MagicItem` (`item_type == "magic"` or `magic == True`)
  **or** any `Enchantment`.

A derivation `source_content_categories(data) -> dict[str, list[str]]` returns, per source
id, the ordered categories it offers (order: classes, equipment, magic_items). Verified
against current data this yields exactly the mockup:

| Source | Categories |
|---|---|
| `ose_classic_fantasy` | classes, equipment, magic_items |
| `ose_advanced_fantasy` | classes, magic_items |
| `carcass_crawler_1` | classes |
| `carcass_crawler_3` | classes, equipment |

Adding content for a new source auto-populates its Content panel — no declaration.

**Display label** for the `classes` row is `"Classes & Races"` when the source contributes
selectable races, else `"Classes"`. Classic is special-cased to `"Classes"` (its single
baseline-human race record is an implementation detail, not a selectable race). `equipment`
→ `"Equipment"`, `magic_items` → `"Magic Items"`.

### `RuleSet` change

Replace `disabled_sources: list[str]` with:

```python
# Content the user has switched off, as "{source_id}:{category}" keys.
# A category is enabled unless its key is listed here. Classic Fantasy
# categories are never added (its content is locked on).
disabled_content: list[str] = Field(default_factory=list)
```

A `@model_validator(mode="before")` folds a legacy `disabled_sources` value (if present
on an old `settings.json` or saved character) into `disabled_content` by expanding each
disabled source id to all three category keys (`{source}:classes`, `:equipment`,
`:magic_items`), then drops the legacy key so `extra="forbid"` is satisfied. The validator
has no access to `GameData`, so it cannot know which categories a source actually offers —
emitting all three is harmless because `content_enabled` is only ever queried for
categories a source provides. (No-migration policy: this is a courtesy coercion, not a hard
requirement, but it keeps the user's existing saves loading.)

### Engine helper (`aose/engine/sources.py`)

```python
CLASSIC_SOURCE_ID = "ose_classic_fantasy"

def content_enabled(source_id: str, category: str, ruleset: RuleSet) -> bool:
    if source_id == CLASSIC_SOURCE_ID:
        return True
    return f"{source_id}:{category}" not in ruleset.disabled_content
```

`source_content_categories(data)` also lives here (or in a tiny derivation module) — it
imports only models/loaded data, preserving the cycle-free DAG.

`source_enabled` is removed; every caller moves to `content_enabled` with the category it
already knows at that site:

| Call site | Category passed |
|---|---|
| wizard race step (`races` list) | `classes` |
| wizard class step (`classes` list) | `classes` |
| wizard race/class orphan-clear (`_apply_rule_changes`) | `classes` |
| spell candidates (`spell_lists[lid].source`) | `classes` |
| `shop.py` item filter | `magic_items` if `item.magic`/`MagicItem` else `equipment` |
| `routes.py` enchant choices (`ench.source`) | `magic_items` |

## Optional-rules structure (`settings_routes.py`)

Replace the thematic `RULE_GROUPS` with a per-source ordered tree. A node is a rule field
name plus optional nested children; a choice node renders the encumbrance radio.

```python
def rule(field, *children): return {"kind": "rule", "field": field, "children": list(children)}
def choice(field):          return {"kind": "choice", "field": field}

SOURCE_RULES = {
    "ose_classic_fantasy": [
        rule("ascending_ac"),
        rule("variable_weapon_damage"),
        rule("reroll_1s_2s_hp_l1"),
        rule("individual_initiative"),
        choice("encumbrance"),
    ],
    "ose_advanced_fantasy": [
        rule("separate_race_class",
            rule("lift_demihuman_restrictions",
                rule("human_racial_abilities")),
            rule("multiclassing")),
        rule("secondary_skills"),
        rule("weapon_proficiency"),
        rule("optional_staves"),
        rule("two_weapon_fighting"),
        rule("advanced_spell_books"),
    ],
    # carcass_crawler_1 / _3: no optional rules — Content only.
}
```

- **Attribution** is the dict key (source id). The renderer walks `SOURCE_RULES[source_id]`
  for that source's panel.
- **Dependencies** are the nesting. Children grey out (and force off) when any ancestor is
  unchecked. This generalizes today's hand-wired `separate_race_class → lift → human` /
  `multiclassing` logic into a tree walk.
- `RULE_LABELS` and the descriptions map stay keyed by field name — no new copy, no YAML.
- `strict_mode` is **not** in any source tree. It renders as a standalone toggle above the
  source panels (it governs how the wizard operates, not a source's optional rule).

### Creation method: radio → nested toggle

The Advanced/Basic `creation_method` radio is removed. `separate_race_class` becomes the
top-level checkbox under Advanced Fantasy's optional rules (checked = Advanced/separate;
unchecked = Basic/race-as-class). Its descendants (`lift_demihuman_restrictions` →
`human_racial_abilities`, and `multiclassing`) grey out when it is unchecked.

`parse_ruleset_from_form` is rewritten to derive `separate_race_class` straight from the
checkbox and to enforce dependencies by walking `SOURCE_RULES`: any rule whose ancestor is
unchecked is forced off (replacing the current `creation_method` / lift / human special
cases). `disabled_content` is built from the per-source content checkboxes — a category key
is added to the list when its checkbox is absent from the form, skipping Classic.

## Rendering (`_ruleset_fields.html`)

Rewritten around source panels:

1. **Strict Mode** — standalone toggle at the top (reuses the existing `.rule` row).
2. For each source (core first, then by name), an expandable panel:
   - **Content** subsection — one checkbox row per derived category. Classic's rows render
     `checked disabled` (locked). Others reflect `disabled_content`.
   - **Optional Rules** subsection — walk `SOURCE_RULES[source_id]`; render rule rows
     (checkboxes) and the encumbrance choice; indent children; tag nodes with
     `data-rule="<field>"` / `data-parent="<field>"` so the JS can drive greying generically.
   - A source with no `SOURCE_RULES` entry omits the Optional Rules subsection.

The progressive-enhancement `<script>` is generalized: on any rule toggle, walk the DOM
tree of `data-parent` relationships and disable+uncheck descendants of any unchecked
ancestor. This replaces the bespoke `data-creation-method` / `data-advanced-only` /
`data-requires-lift` wiring. The panels use the existing OSR-zine `fieldset`/`.rule`
styling; expand/collapse follows the style-guide overlay/disclosure idiom (details/summary
or a `.panel` disclosure — pick whichever the style guide already blesses).

## "Pending" badges

Every `RuleSet` flag is already implemented, and the settings page asserts no "pending"
badge renders (a regression test guards this). This change keeps that invariant — the
`IMPLEMENTED_RULES` / `pending` machinery can stay as-is (now unused for badges) or be
dropped; the regression test must still pass.

## Testing

- **Model:** `disabled_content` round-trips; legacy `disabled_sources` coercion expands to
  the right category keys; Classic categories are never added.
- **Derivation:** `source_content_categories` returns the table above for current data.
- **Engine:** `content_enabled` — Classic always on regardless of `disabled_content`;
  a disabled `"carcass_crawler_3:equipment"` hides CC3 equipment but not CC3 classes.
- **Filtering integration:** disabling `"carcass_crawler_3:equipment"` removes CC3 gear
  from the shop while CC3 classes remain selectable in the wizard; disabling
  `"ose_advanced_fantasy:magic_items"` removes Advanced enchant choices.
- **Form parse:** unchecking `separate_race_class` forces `lift`, `human`, `multiclassing`
  off; unchecking `lift` forces `human` off; content checkboxes map to `disabled_content`.
- **Web:** `/settings` and `/rules` render the source panels; no "pending" badge (existing
  regression test); existing source-disable tests updated to the new shape.
- Update `tests/test_sources_engine.py`, `tests/test_settings.py`, and any source-filter
  tests in `test_web.py` / shop / enchant tests to the category-aware API.

## Docs

- `docs/CHANGELOG.md` — one-line row.
- `docs/ARCHITECTURE.md` — rewrite the "Content sources & optional rules" section in place:
  `disabled_content` + `content_enabled` + derived categories + source-keyed `SOURCE_RULES`.
- `CLAUDE.md` storage-shapes line — `disabled_sources` → `disabled_content` shape note.
```
