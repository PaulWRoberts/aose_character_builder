# Source-organized Content & Optional Rules — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `/settings` and the wizard `/rules` step into per-source panels with derived content-category toggles (classes / equipment / magic_items) that genuinely gate content, and optional rules attributed to their source with a nesting/dependency tree.

**Architecture:** Replace `RuleSet.disabled_sources` (whole-source) with `disabled_content` (`"{source}:{category}"` keys). A `content_enabled(source, category, ruleset)` engine helper replaces `source_enabled`; content categories are *derived* from loaded `GameData`, not tagged on items. Optional rules move from thematic `RULE_GROUPS` into a source-keyed `SOURCE_RULES` tree whose nesting expresses dependencies. The shared `_ruleset_fields.html` partial is rewritten into source panels.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Windows / PowerShell.

**Spec:** `docs/superpowers/specs/2026-06-10-source-content-rules-organization-design.md`

**Run tests:** `.venv\Scripts\python.exe -m pytest tests/ -q`
(The trailing `PermissionError` on `pytest-current` is a known Windows quirk — ignore it.)

---

## File map

| File | Responsibility | Change |
|---|---|---|
| `aose/models/ruleset.py` | `RuleSet` model | Add `disabled_content` + `CONTENT_CATEGORIES` + legacy-coercion validator; drop `disabled_sources` |
| `aose/models/__init__.py` | model exports | Export `CONTENT_CATEGORIES` |
| `aose/engine/sources.py` | source/content filter | Add `content_enabled` + `source_content_categories`; drop `source_enabled` |
| `aose/web/wizard.py` | wizard race/class/spell filtering + orphan-clear | 4 call sites → `content_enabled(..., "classes", ...)`; `_apply_rule_changes` compares `disabled_content` |
| `aose/engine/shop.py` | shop item filter | `content_enabled(..., "equipment"/"magic_items", ...)` |
| `aose/web/routes.py` | enchant picker filter | `content_enabled(..., "magic_items", ...)` |
| `aose/web/settings_routes.py` | settings GET/POST + rule config | `SOURCE_RULES` tree, `RULE_DESCRIPTIONS`, content-row derivation, rewritten `parse_ruleset_from_form` |
| `aose/web/templates/_ruleset_fields.html` | shared ruleset form body | Rewritten into source panels + generalized greying JS |
| `tests/test_sources_engine.py` | engine filter tests | Rewritten for `content_enabled` / `source_content_categories` |
| `tests/test_settings.py` | settings + parser + wizard-filter tests | Updated for new form fields + `disabled_content` |
| `tests/test_models.py` | model tests | Add `disabled_content` / coercion tests |
| `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, `CLAUDE.md` | docs | Updated |

---

## Task 1: Swap storage + filter mechanism (model + engine + call sites)

This is a cohesive cross-cutting rename: `disabled_sources` → `disabled_content`, `source_enabled` → `content_enabled`. The settings page UI is left **functionally identical** (still whole-source checkboxes) in this task — only the storage shape and filter granularity change underneath. Per project policy there are no migrations, but a coercion validator keeps existing `settings.json` / saved characters loading, and (importantly) keeps the wizard-filter tests green because they set `disabled_sources` on draft rulesets.

**Files:**
- Modify: `aose/models/ruleset.py`
- Modify: `aose/models/__init__.py`
- Modify: `aose/engine/sources.py`
- Modify: `aose/web/wizard.py` (race/class/spell filtering, `_apply_rule_changes`)
- Modify: `aose/engine/shop.py`
- Modify: `aose/web/routes.py`
- Modify: `aose/web/settings_routes.py` (`parse_ruleset_from_form` emits `disabled_content`)
- Test: `tests/test_models.py`, `tests/test_sources_engine.py`, `tests/test_settings.py`

- [ ] **Step 1: Write failing model tests**

Add to `tests/test_models.py` (append at end):

```python
def test_disabled_content_defaults_empty():
    from aose.models import RuleSet
    assert RuleSet().disabled_content == []


def test_disabled_content_round_trips():
    from aose.models import RuleSet
    rs = RuleSet(disabled_content=["carcass_crawler_3:equipment"])
    assert rs.disabled_content == ["carcass_crawler_3:equipment"]


def test_legacy_disabled_sources_is_coerced_to_categories():
    """An old save with disabled_sources expands to all three category keys
    and drops the legacy field (extra='forbid' would otherwise reject it)."""
    from aose.models import RuleSet
    rs = RuleSet.model_validate({"disabled_sources": ["carcass_crawler_3"]})
    assert set(rs.disabled_content) == {
        "carcass_crawler_3:classes",
        "carcass_crawler_3:equipment",
        "carcass_crawler_3:magic_items",
    }


def test_legacy_coercion_skips_classic():
    from aose.models import RuleSet
    rs = RuleSet.model_validate(
        {"disabled_sources": ["ose_classic_fantasy", "ose_advanced_fantasy"]}
    )
    assert all(not k.startswith("ose_classic_fantasy:") for k in rs.disabled_content)
    assert "ose_advanced_fantasy:classes" in rs.disabled_content
```

- [ ] **Step 2: Run model tests — verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -q -k "disabled_content or legacy"`
Expected: FAIL (`disabled_content` field does not exist / `disabled_sources` rejected).

- [ ] **Step 3: Implement the model change**

In `aose/models/ruleset.py`, replace the file body's `disabled_sources` block. Add the import and validator:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EncumbranceMode = Literal["none", "basic", "detailed"]

# The content categories a source can offer. Derived from loaded data at
# runtime (see engine/sources.source_content_categories); listed here so the
# model's legacy-coercion validator can expand an old whole-source disable.
CONTENT_CATEGORIES = ("classes", "equipment", "magic_items")

_CLASSIC_SOURCE_ID = "ose_classic_fantasy"  # mirrors engine.sources.CLASSIC_SOURCE_ID


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ascending_ac: bool = False
    secondary_skills: bool = False
    weapon_proficiency: bool = False
    multiclassing: bool = False
    reroll_1s_2s_hp_l1: bool = False
    separate_race_class: bool = True
    lift_demihuman_restrictions: bool = False
    variable_weapon_damage: bool = False
    advanced_spell_books: bool = False
    human_racial_abilities: bool = False
    strict_mode: bool = True
    optional_staves: bool = False
    two_weapon_fighting: bool = False
    individual_initiative: bool = False

    encumbrance: EncumbranceMode = "basic"

    # Content the user has switched off, as "{source_id}:{category}" keys. A
    # category is enabled unless its key is listed here. Classic Fantasy
    # categories are never added (its content is locked on).
    disabled_content: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_disabled_sources(cls, data):
        """Fold a legacy whole-source `disabled_sources` value into
        `disabled_content` by expanding each disabled source to all three
        category keys. The validator has no GameData, so it emits all three —
        harmless, since content_enabled is only queried for categories a
        source actually provides."""
        if isinstance(data, dict) and "disabled_sources" in data:
            legacy = data.pop("disabled_sources") or []
            expanded = [
                f"{sid}:{cat}"
                for sid in legacy
                if sid != _CLASSIC_SOURCE_ID
                for cat in CONTENT_CATEGORIES
            ]
            existing = list(data.get("disabled_content") or [])
            data["disabled_content"] = existing + [
                k for k in expanded if k not in existing
            ]
        return data
```

In `aose/models/__init__.py`, add `CONTENT_CATEGORIES` to the import from `.ruleset` and to `__all__`:

```python
from .ruleset import RuleSet, EncumbranceMode, CONTENT_CATEGORIES
```
(Append `"CONTENT_CATEGORIES"` to `__all__` if that file maintains one.)

- [ ] **Step 4: Run model tests — verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -q -k "disabled_content or legacy"`
Expected: PASS.

- [ ] **Step 5: Rewrite the engine filter tests (failing)**

Replace the entire contents of `tests/test_sources_engine.py`:

```python
from pathlib import Path

from aose.engine.sources import (
    CLASSIC_SOURCE_ID,
    content_enabled,
    source_content_categories,
)
from aose.data.loader import GameData
from aose.models import RuleSet

DATA_DIR = Path(__file__).parent.parent / "data"


def test_classic_is_always_enabled():
    rs = RuleSet(disabled_content=["ose_classic_fantasy:classes"])
    assert content_enabled(CLASSIC_SOURCE_ID, "classes", rs) is True


def test_unlisted_category_is_enabled_by_default():
    assert content_enabled("ose_advanced_fantasy", "classes", RuleSet()) is True


def test_disabled_category_is_not_enabled():
    rs = RuleSet(disabled_content=["carcass_crawler_3:equipment"])
    assert content_enabled("carcass_crawler_3", "equipment", rs) is False
    # A different category of the same source stays enabled.
    assert content_enabled("carcass_crawler_3", "classes", rs) is True


def test_source_content_categories_matches_data():
    data = GameData.load(DATA_DIR)
    cats = source_content_categories(data)
    assert cats["ose_classic_fantasy"] == ["classes", "equipment", "magic_items"]
    assert cats["ose_advanced_fantasy"] == ["classes", "magic_items"]
    assert cats["carcass_crawler_1"] == ["classes"]
    assert cats["carcass_crawler_3"] == ["classes", "equipment"]
```

- [ ] **Step 6: Run engine tests — verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sources_engine.py -q`
Expected: FAIL (`content_enabled` / `source_content_categories` not defined).

- [ ] **Step 7: Implement the engine change**

Replace the contents of `aose/engine/sources.py`:

```python
"""Source / content-category filter.  Cycle-free: imports only models + the
GameData type.

A character's :class:`RuleSet` may disable individual content categories
(``classes`` / ``equipment`` / ``magic_items``) per source; this module decides
whether a given source+category is currently active, and derives which
categories each source actually offers from loaded data.  Classic Fantasy is
the baseline and can never be disabled.
"""
from aose.models import RuleSet, CONTENT_CATEGORIES

CLASSIC_SOURCE_ID = "ose_classic_fantasy"


def content_enabled(source_id: str, category: str, ruleset: RuleSet) -> bool:
    """Whether ``category`` content from ``source_id`` is available."""
    if source_id == CLASSIC_SOURCE_ID:
        return True
    return f"{source_id}:{category}" not in ruleset.disabled_content


def source_content_categories(data) -> dict[str, list[str]]:
    """Map each source id to the ordered content categories it provides,
    derived from loaded ``GameData`` (no per-item tagging needed).

    - ``classes``     — the source has any class or race (spell lists ride along)
    - ``equipment``   — the source has any non-magic item
    - ``magic_items`` — the source has any magic item or enchantment
    """
    cats: dict[str, set[str]] = {}

    def add(source_id: str, category: str) -> None:
        cats.setdefault(source_id, set()).add(category)

    for cls in data.classes.values():
        add(cls.source, "classes")
    for race in data.races.values():
        add(race.source, "classes")
    for item in data.items.values():
        is_magic = getattr(item, "item_type", None) == "magic" or getattr(
            item, "magic", False
        )
        add(item.source, "magic_items" if is_magic else "equipment")
    for ench in data.enchantments.values():
        add(ench.source, "magic_items")

    order = {c: n for n, c in enumerate(CONTENT_CATEGORIES)}
    return {sid: sorted(s, key=lambda c: order[c]) for sid, s in cats.items()}
```

- [ ] **Step 8: Run engine tests — verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sources_engine.py -q`
Expected: PASS.

- [ ] **Step 9: Migrate the wizard call sites**

In `aose/web/wizard.py`:

Change the import (line ~103) from:
```python
from aose.engine.sources import CLASSIC_SOURCE_ID, source_enabled
```
to:
```python
from aose.engine.sources import CLASSIC_SOURCE_ID, content_enabled
```

Race step (line ~617):
```python
        if not content_enabled(race.source, "classes", ruleset):
```
Class step (line ~709):
```python
        if not content_enabled(cls.source, "classes", ruleset):
```
Spell-candidate filter (line ~1483):
```python
            and content_enabled(data.spell_lists[lid].source, "classes", ruleset)
```
`_apply_rule_changes` orphan-clear (lines ~471–483) — change the guard and both calls:
```python
    if data is not None and new_rs.disabled_content != old_rs.disabled_content:
        race_id = draft.get("race_id")
        if race_id in data.races and not content_enabled(
            data.races[race_id].source, "classes", new_rs
        ):
            _clear_after_abilities(draft)
            return
        for cid in _class_ids(draft):
            if cid in data.classes and not content_enabled(
                data.classes[cid].source, "classes", new_rs
            ):
                _clear_after_race(draft)
                break
```

- [ ] **Step 10: Migrate the shop filter**

In `aose/engine/shop.py`, change the import:
```python
from aose.engine.sources import content_enabled
```
and the filter loop (lines ~100–103):
```python
    for item in data.items.values():
        if ruleset is not None:
            is_magic = getattr(item, "item_type", None) == "magic" or getattr(
                item, "magic", False
            )
            category = "magic_items" if is_magic else "equipment"
            if not content_enabled(item.source, category, ruleset):
                continue
        by_cat.setdefault(item.category, []).append(item)
```

- [ ] **Step 11: Migrate the enchant filter**

In `aose/web/routes.py`, change the import of `source_enabled` (line ~91) to `content_enabled`, and the filter (line ~114):
```python
        if ruleset is not None and not content_enabled(ench.source, "magic_items", ruleset):
            continue
```

- [ ] **Step 12: Update `parse_ruleset_from_form` to emit `disabled_content`**

In `aose/web/settings_routes.py`, the source-handling tail of `parse_ruleset_from_form` (lines ~184–191). Keep the existing `source_{sid}` checkbox form contract for now (the template is unchanged in this task); just translate unchecked sources into all three category keys:

```python
    from aose.models import CONTENT_CATEGORIES  # local import avoids a cycle at module load

    disabled_content = []
    for sid in (source_ids or []):
        if sid == CLASSIC_SOURCE_ID:
            continue
        if f"source_{sid}" not in form:
            disabled_content.extend(f"{sid}:{cat}" for cat in CONTENT_CATEGORIES)

    return RuleSet(**bools, **choices, disabled_content=disabled_content)
```

- [ ] **Step 13: Update the settings tests that assert `disabled_sources`**

In `tests/test_settings.py`, update the four parser source tests and the POST test to assert `disabled_content`:

`test_parser_disables_unchecked_sources`:
```python
def test_parser_disables_unchecked_sources():
    rs = parse_ruleset_from_form(
        _Form({"creation_method": "advanced"}),
        source_ids=["ose_classic_fantasy", "ose_advanced_fantasy"],
    )
    assert rs.disabled_content == [
        "ose_advanced_fantasy:classes",
        "ose_advanced_fantasy:equipment",
        "ose_advanced_fantasy:magic_items",
    ]
```

`test_parser_keeps_checked_sources_enabled`:
```python
def test_parser_keeps_checked_sources_enabled():
    rs = parse_ruleset_from_form(
        _Form({"creation_method": "advanced", "source_ose_advanced_fantasy": "on"}),
        source_ids=["ose_classic_fantasy", "ose_advanced_fantasy"],
    )
    assert rs.disabled_content == []
```

`test_parser_never_disables_classic`:
```python
def test_parser_never_disables_classic():
    rs = parse_ruleset_from_form(
        _Form({}),
        source_ids=["ose_classic_fantasy", "ose_advanced_fantasy"],
    )
    assert not any(k.startswith("ose_classic_fantasy:") for k in rs.disabled_content)
```

`test_parser_without_source_ids_disables_nothing`:
```python
def test_parser_without_source_ids_disables_nothing():
    rs = parse_ruleset_from_form(_Form({"creation_method": "advanced"}))
    assert rs.disabled_content == []
```

`test_post_settings_persists_disabled_source`:
```python
def test_post_settings_persists_disabled_source(client):
    r = client.post("/settings", data={"creation_method": "advanced"})
    assert r.status_code == 303
    rs = load_settings(client._settings_path)
    assert "ose_advanced_fantasy:classes" in rs.disabled_content
    assert "carcass_crawler_1:classes" in rs.disabled_content
    assert not any(k.startswith("ose_classic_fantasy:") for k in rs.disabled_content)
```

The wizard-filter helper `_new_draft_with_sources` (sets `draft["ruleset"]["disabled_sources"]`) is left as-is — the model's coercion validator converts it on load, so `test_race_step_hides_advanced_when_disabled` etc. keep passing unchanged. This deliberately exercises the legacy path.

- [ ] **Step 14: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError). If any test still references `source_enabled` or `disabled_sources`, fix it to the new API.

- [ ] **Step 15: Commit**

```bash
git add aose/models/ruleset.py aose/models/__init__.py aose/engine/sources.py aose/web/wizard.py aose/engine/shop.py aose/web/routes.py aose/web/settings_routes.py tests/test_models.py tests/test_sources_engine.py tests/test_settings.py
git commit -F - <<'MSG'
refactor: per-category content filtering (disabled_content)

Replace whole-source disabled_sources with disabled_content
("{source}:{category}" keys) and source_enabled with
content_enabled(source, category, ruleset). Content categories are
derived from loaded data via source_content_categories. A model
validator coerces legacy disabled_sources so existing saves load.
Settings page UI unchanged in this commit.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
```
(On Windows, if the heredoc form is awkward, write the message to a temp file and use `git commit -F <file>`. Do **not** use a PowerShell `@'...'@` here-string with `git commit -m` — it leaks a leading `@` into the subject.)

---

## Task 2: Rule config — `SOURCE_RULES` tree + descriptions + content-row derivation

Pure additions to `settings_routes.py`: the source-keyed optional-rule tree, a flat descriptions map, a tree-flattening helper, and a content-row builder. Nothing renders these yet (template rewrite is Task 3), so the suite stays green. The old `RULE_GROUPS` stays in place until Task 3 removes it.

**Files:**
- Modify: `aose/web/settings_routes.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write failing config tests**

Append to `tests/test_settings.py`:

```python
def test_source_rules_attributes_rules_to_sources():
    from aose.web.settings_routes import SOURCE_RULES, flatten_rule_fields
    classic = flatten_rule_fields(SOURCE_RULES["ose_classic_fantasy"])
    advanced = flatten_rule_fields(SOURCE_RULES["ose_advanced_fantasy"])
    assert "individual_initiative" in classic
    assert "ascending_ac" in classic
    assert "separate_race_class" in advanced
    assert "multiclassing" in advanced
    # strict_mode is standalone, never inside a source tree.
    assert "strict_mode" not in classic and "strict_mode" not in advanced
    # Carcass Crawler issues contribute no optional rules.
    assert SOURCE_RULES.get("carcass_crawler_1", []) == []
    assert SOURCE_RULES.get("carcass_crawler_3", []) == []


def test_source_rules_nesting_expresses_dependencies():
    from aose.web.settings_routes import SOURCE_RULES
    # separate_race_class -> {lift -> human, multiclassing}
    srx = next(n for n in SOURCE_RULES["ose_advanced_fantasy"]
               if n["field"] == "separate_race_class")
    child_fields = {c["field"] for c in srx["children"]}
    assert {"lift_demihuman_restrictions", "multiclassing"} <= child_fields
    lift = next(c for c in srx["children"]
                if c["field"] == "lift_demihuman_restrictions")
    assert any(g["field"] == "human_racial_abilities" for g in lift["children"])


def test_every_rule_field_has_a_description():
    from aose.web.settings_routes import SOURCE_RULES, RULE_DESCRIPTIONS, flatten_rule_fields
    fields = set()
    for tree in SOURCE_RULES.values():
        fields |= set(flatten_rule_fields(tree))
    fields.discard(None)  # choice nodes have no field
    missing = fields - set(RULE_DESCRIPTIONS)
    assert not missing, f"missing descriptions: {missing}"


def test_content_rows_for_source_locks_classic():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import RuleSet
    from aose.web.settings_routes import content_rows_for_source
    data = GameData.load(Path(__file__).parent.parent / "data")
    rows = content_rows_for_source(data, "ose_classic_fantasy", RuleSet())
    assert [r["category"] for r in rows] == ["classes", "equipment", "magic_items"]
    assert all(r["locked"] and r["enabled"] for r in rows)
    # Classic's classes row label is just "Classes" (no "& Races").
    assert next(r for r in rows if r["category"] == "classes")["label"] == "Classes"


def test_content_rows_reflect_disabled_content():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import RuleSet
    from aose.web.settings_routes import content_rows_for_source
    data = GameData.load(Path(__file__).parent.parent / "data")
    rs = RuleSet(disabled_content=["carcass_crawler_3:equipment"])
    rows = content_rows_for_source(data, "carcass_crawler_3", rs)
    by_cat = {r["category"]: r for r in rows}
    assert by_cat["classes"]["label"] == "Classes & Races"
    assert by_cat["classes"]["enabled"] is True
    assert by_cat["equipment"]["enabled"] is False
    assert all(not r["locked"] for r in rows)
```

- [ ] **Step 2: Run config tests — verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q -k "source_rules or content_rows or description"`
Expected: FAIL (symbols not defined).

- [ ] **Step 3: Add the config + helpers**

In `aose/web/settings_routes.py`, add near the top (after `RULE_LABELS`):

```python
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
        out.append(node.get("field"))
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
```

- [ ] **Step 4: Run config tests — verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q -k "source_rules or content_rows or description"`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/settings_routes.py tests/test_settings.py
git commit -F - <<'MSG'
feat(settings): source-keyed SOURCE_RULES tree + content-row derivation

Add the per-source optional-rule tree (nesting = dependencies), a flat
RULE_DESCRIPTIONS map, flatten_rule_fields, and content_rows_for_source
(derived content categories with display labels + locked/enabled state).
Not yet rendered — wired up in the template rewrite.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
```

---

## Task 3: Rewrite the UI — source panels, `parse_ruleset_from_form`, GET context, JS

Replace the thematic form body with per-source panels. The Advanced/Basic radio is removed; `separate_race_class` becomes a nested checkbox. `parse_ruleset_from_form` is rewritten to derive bools from the form + enforce the dependency tree + build `disabled_content` from per-category checkboxes. The greying JS is generalized to walk parent→child relationships.

**Files:**
- Modify: `aose/web/settings_routes.py` (GET context, `parse_ruleset_from_form`, POST content keys)
- Modify: `aose/web/templates/_ruleset_fields.html` (full rewrite)
- Test: `tests/test_settings.py`

- [ ] **Step 1: Rewrite `parse_ruleset_from_form` (write failing parser tests first)**

Replace the parser tests block in `tests/test_settings.py` (the "Creation method + Basic enforcement" section, `test_parser_*` and `test_settings_page_shows_creation_method`, `test_post_settings_basic_forces_advanced_rules_off`) with checkbox-driven versions:

```python
def test_parser_separate_race_class_checkbox_on():
    rs = parse_ruleset_from_form(_Form({"separate_race_class": "on"}))
    assert rs.separate_race_class is True


def test_parser_separate_race_class_unchecked_is_basic():
    rs = parse_ruleset_from_form(_Form({}))
    assert rs.separate_race_class is False


def test_parser_basic_forces_descendant_rules_off():
    """separate_race_class off forces its whole subtree off, even if posted."""
    rs = parse_ruleset_from_form(_Form({
        "multiclassing": "on",
        "lift_demihuman_restrictions": "on",
        "human_racial_abilities": "on",
    }))
    assert rs.separate_race_class is False
    assert rs.multiclassing is False
    assert rs.lift_demihuman_restrictions is False
    assert rs.human_racial_abilities is False


def test_parser_lift_off_forces_human_off():
    rs = parse_ruleset_from_form(_Form({
        "separate_race_class": "on",
        "human_racial_abilities": "on",
    }))  # lift not checked
    assert rs.lift_demihuman_restrictions is False
    assert rs.human_racial_abilities is False


def test_parser_full_advanced_chain_kept():
    rs = parse_ruleset_from_form(_Form({
        "separate_race_class": "on",
        "lift_demihuman_restrictions": "on",
        "human_racial_abilities": "on",
        "multiclassing": "on",
    }))
    assert rs.lift_demihuman_restrictions is True
    assert rs.human_racial_abilities is True
    assert rs.multiclassing is True


def test_parser_strict_mode_is_standalone():
    assert parse_ruleset_from_form(_Form({"strict_mode": "on"})).strict_mode is True
    assert parse_ruleset_from_form(_Form({})).strict_mode is False


def test_parser_disables_unchecked_content_categories():
    rs = parse_ruleset_from_form(
        _Form({}),
        content_keys=["carcass_crawler_3:classes", "carcass_crawler_3:equipment"],
    )
    assert set(rs.disabled_content) == {
        "carcass_crawler_3:classes", "carcass_crawler_3:equipment",
    }


def test_parser_keeps_checked_content_categories():
    rs = parse_ruleset_from_form(
        _Form({"content_carcass_crawler_3:classes": "on"}),
        content_keys=["carcass_crawler_3:classes", "carcass_crawler_3:equipment"],
    )
    assert rs.disabled_content == ["carcass_crawler_3:equipment"]
```

Delete the now-obsolete `test_parser_disables_unchecked_sources`, `test_parser_keeps_checked_sources_enabled`, `test_parser_never_disables_classic`, `test_parser_without_source_ids_disables_nothing`, `test_settings_page_shows_creation_method`, `test_settings_page_renders_sources_section`, `test_post_settings_persists_disabled_source`, `test_post_settings_basic_forces_advanced_rules_off` (their concerns are covered by the new tests + Task-3 render tests below).

- [ ] **Step 2: Run new parser tests — verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q -k parser`
Expected: FAIL (`content_keys` kwarg unknown / `creation_method` logic still present).

- [ ] **Step 3: Rewrite `parse_ruleset_from_form`**

Replace the function in `aose/web/settings_routes.py`:

```python
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
```

- [ ] **Step 4: Run new parser tests — verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q -k parser`
Expected: PASS.

- [ ] **Step 5: Update GET context + POST content keys**

In `aose/web/settings_routes.py`, rewrite `get_settings` to build panels and pass the new context, and `post_settings` to compute content keys:

```python
def _ruleset_view_context(request, ruleset):
    """Shared template context for the source-panel ruleset form. `ruleset` must
    be a RuleSet **object** (content_rows_for_source reads `.disabled_content`).
    The template subscripts it (`ruleset['field']`) — Jinja's `[]` falls back to
    attribute access, so the object works directly."""
    from aose.engine.sources import CLASSIC_SOURCE_ID
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
        "classic_source_id": CLASSIC_SOURCE_ID,
    }


def _content_keys(request):
    from aose.engine.sources import CLASSIC_SOURCE_ID, source_content_categories
    data = request.app.state.game_data
    cats = source_content_categories(data)
    return [
        f"{sid}:{cat}"
        for sid, cs in cats.items()
        if sid != CLASSIC_SOURCE_ID
        for cat in cs
    ]


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    ruleset = load_settings(_settings_path(request))
    saved = request.query_params.get("saved") == "1"
    context = _ruleset_view_context(request, ruleset)
    context["saved"] = saved
    return templates.TemplateResponse(request, "settings.html", context)


@router.post("/settings")
async def post_settings(request: Request):
    form = await request.form()
    new_ruleset = parse_ruleset_from_form(form, content_keys=_content_keys(request))
    save_settings(_settings_path(request), new_ruleset)
    return RedirectResponse("/settings?saved=1", status_code=303)
```

Now update the wizard handlers in `aose/web/wizard.py`. Add the import (it already imports `RULE_GROUPS`, `RULE_LABELS`, etc. from `settings_routes`, so no new cycle):

```python
from aose.web.settings_routes import _ruleset_view_context, _content_keys
```

In `get_rules` (lines ~388–410), replace the `ctx.update({...})` block (the one passing `rule_groups`, `implemented_rules`, `advanced_options_group`, `sources`, …) with the shared context. Pass the RuleSet **object**, not `model_dump()`:

```python
    ruleset = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "rules")
    ctx.update(_ruleset_view_context(request, ruleset))
    return templates.TemplateResponse(request, "wizard.html", ctx)
```

In `post_rules` (lines ~487+), change the line that parses the form from
`parse_ruleset_from_form(form, source_ids=...)` to:
```python
    new_ruleset = parse_ruleset_from_form(form, content_keys=_content_keys(request))
```
Keep the surrounding `_apply_rule_changes(draft, old_rs, new_ruleset, data=...)` call and strict-gate logic unchanged.

After this, the old context keys (`rule_groups`, `implemented_rules`, `implemented_choice_groups`, `advanced_options_group`, `sources`) are no longer passed by either handler. The names `RULE_GROUPS`, `ADVANCED_OPTIONS_GROUP` etc. may still be imported in `wizard.py`'s import block — remove any that are now unused (leave `RULE_LABELS`, `IMPLEMENTED_RULES`, `CLASSIC_SOURCE_ID` if still referenced elsewhere; `grep` to confirm before deleting).

Then delete the now-dead `RULE_GROUPS` and `ADVANCED_OPTIONS_GROUP` definitions from `settings_routes.py` (the rewritten `parse_ruleset_from_form`, GET context, and template no longer use them; the only test that referenced `RULE_GROUPS` is rewritten in Step 7). Keep `RULE_LABELS`, `IMPLEMENTED_RULES`, `IMPLEMENTED_CHOICE_GROUPS`, and `CHOICE_GROUPS` — they are still referenced by tests and/or the new template.

- [ ] **Step 6: Rewrite the template**

Replace the entire contents of `aose/web/templates/_ruleset_fields.html`:

```jinja
{# Shared ruleset form body: a standalone Strict Mode toggle, then one
   expandable panel per content source. Each panel has a Content subsection
   (derived category checkboxes; Classic locked) and an Optional Rules
   subsection (SOURCE_RULES tree, nested rows = dependencies). Included by
   settings.html and wizard/rules.html inside their own <form>. #}

{% macro rule_row(node, ruleset, rule_labels, rule_descriptions, choice_groups, depth=0, parent=None) %}
  {% if node.kind == "choice" %}
    {% for field, label, options in choice_groups if field == node.field %}
    <div class="rule rule-choice" style="--rule-depth: {{ depth }};"
         data-rule="{{ field }}"{% if parent %} data-parent="{{ parent }}"{% endif %}>
      <span class="rule-name">{{ label }}</span>
      <div class="radio-stack">
        {% for value, opt_label in options %}
        <label class="radio-card {% if ruleset[field] == value %}selected{% endif %}">
          <input type="radio" name="{{ field }}" value="{{ value }}"
                 {% if ruleset[field] == value %}checked{% endif %}>
          <span class="radio-label">{{ opt_label }}</span>
        </label>
        {% endfor %}
      </div>
    </div>
    {% endfor %}
  {% else %}
    <label class="rule" style="--rule-depth: {{ depth }};"
           data-rule="{{ node.field }}"{% if parent %} data-parent="{{ parent }}"{% endif %}>
      <input type="checkbox" name="{{ node.field }}"
             {% if ruleset[node.field] %}checked{% endif %}>
      <span class="rule-body">
        <span class="rule-name">{{ rule_labels[node.field] }}</span>
        <span class="rule-desc">{{ rule_descriptions[node.field] }}</span>
      </span>
    </label>
    {% for child in node.children %}
      {{ rule_row(child, ruleset, rule_labels, rule_descriptions, choice_groups, depth + 1, node.field) }}
    {% endfor %}
  {% endif %}
{% endmacro %}

<fieldset class="rule-group strict-standalone">
  <legend>Strict Mode</legend>
  <label class="rule">
    <input type="checkbox" name="strict_mode" {% if ruleset['strict_mode'] %}checked{% endif %}>
    <span class="rule-body">
      <span class="rule-name">Strict Mode</span>
      <span class="rule-desc">Ability scores, hit points, and starting gold are
        locked after a single roll (a hopeless ability set may always be
        re-rolled). Turn off to allow free re-rolls. This governs how the wizard
        operates and is not a source option.</span>
    </span>
  </label>
</fieldset>

{% for panel in panels %}
<details class="source-panel" open>
  <summary class="source-panel-summary">
    {{ panel.source.name }}
    {% if panel.source.core %}<span class="rule-core" title="Core source">core</span>{% endif %}
  </summary>

  {% if panel.content_rows %}
  <fieldset class="rule-group content-group">
    <legend>Content{% if panel.source.id == classic_source_id %} <span class="rule-core" title="Always enabled">locked</span>{% endif %}</legend>
    {% for row in panel.content_rows %}
    <label class="rule {% if row.locked %}rule-disabled{% endif %}">
      <input type="checkbox" name="{{ row.field }}"
             {% if row.enabled %}checked{% endif %}
             {% if row.locked %}disabled{% endif %}>
      <span class="rule-body">
        <span class="rule-name">{{ row.label }}</span>
      </span>
    </label>
    {% endfor %}
  </fieldset>
  {% endif %}

  {% if panel.rule_tree %}
  <fieldset class="rule-group optional-rules-group">
    <legend>Optional Rules</legend>
    {% for node in panel.rule_tree %}
      {{ rule_row(node, ruleset, rule_labels, rule_descriptions, choice_groups) }}
    {% endfor %}
  </fieldset>
  {% endif %}
</details>
{% endfor %}

<script>
(function () {
  // Generalized dependency greying: a rule's descendants (data-parent chain)
  // grey out and force off whenever any ancestor checkbox is unchecked.
  var form = document.currentScript.closest('form');
  if (!form) { return; }

  function inputFor(field) {
    return form.querySelector('[data-rule="' + field + '"] input[type="checkbox"]');
  }
  function childrenOf(field) {
    return form.querySelectorAll('[data-parent="' + field + '"]');
  }
  function setDisabled(row, disabled) {
    row.classList.toggle('rule-disabled', disabled);
    row.querySelectorAll('input').forEach(function (el) {
      el.disabled = disabled;
      if (disabled && el.type === 'checkbox') { el.checked = false; }
    });
  }
  function syncFrom(field) {
    var parentInput = inputFor(field);
    var parentOff = !parentInput || !parentInput.checked || parentInput.disabled;
    childrenOf(field).forEach(function (row) {
      setDisabled(row, parentOff);
      var childField = row.getAttribute('data-rule');
      if (childField) { syncFrom(childField); }
    });
  }

  form.querySelectorAll('[data-rule] input[type="checkbox"]').forEach(function (el) {
    el.addEventListener('change', function () {
      var field = el.closest('[data-rule]').getAttribute('data-rule');
      syncFrom(field);
    });
  });
  // Initial pass over every top-level rule that has children.
  form.querySelectorAll('[data-rule]').forEach(function (row) {
    if (!row.getAttribute('data-parent')) {
      syncFrom(row.getAttribute('data-rule'));
    }
  });
})();
</script>
```

> Styling note: `--rule-depth` is consumed by the OSR-zine stylesheet to indent nested rows. Add a small rule (e.g. `.rule { margin-left: calc(var(--rule-depth, 0) * 1.5rem); }`) to the existing settings/wizard CSS following `docs/STYLE-GUIDE.md`. The `<details>/<summary>` disclosure should be styled per the style guide's disclosure idiom; if the guide prefers a `.panel` pattern over native `<details>`, use that instead and drive open/close with the existing overlay JS.

- [ ] **Step 7: Update remaining render tests**

In `tests/test_settings.py`:

`test_get_settings_renders` — keep (`Ascending AC` still appears). Confirm panel text:
```python
def test_get_settings_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Ruleset Settings" in r.text
    assert "Ascending AC" in r.text
    assert "Strict Mode" in r.text
    assert "Carcass Crawler Issue 3" in r.text  # a source panel header
```

Add a content-toggle render + persistence test:
```python
def test_settings_renders_content_category_checkbox(client):
    r = client.get("/settings")
    assert 'name="content_carcass_crawler_3:equipment"' in r.text
    # Classic content rows are present but disabled (locked on).
    import re
    assert re.search(
        r'name="content_ose_classic_fantasy:classes"[^>]*\bdisabled\b', r.text
    )


def test_post_settings_persists_disabled_content_category(client):
    keys = _content_keys_for(client)  # helper below
    # Re-check every content category except CC3 equipment -> only that disabled.
    data = {f"content_{k}": "on" for k in keys if k != "carcass_crawler_3:equipment"}
    client.post("/settings", data=data)
    rs = load_settings(client._settings_path)
    assert "carcass_crawler_3:equipment" in rs.disabled_content
    assert "carcass_crawler_3:classes" not in rs.disabled_content
```

Add a tiny helper near the top of the file (after the `client` fixture):
```python
def _content_keys_for(client):
    from aose.web.settings_routes import _content_keys

    class _Req:
        app = client.app
    return _content_keys(_Req())
```

Update `test_individual_initiative_flag_is_implemented` — it reads the removed `RULE_GROUPS["Combat"]`. Replace with:
```python
def test_individual_initiative_attributed_to_classic():
    from aose.web.settings_routes import SOURCE_RULES, flatten_rule_fields, RULE_LABELS
    from aose.models import RuleSet
    assert RuleSet().individual_initiative is False
    assert "individual_initiative" in RULE_LABELS
    assert "individual_initiative" in flatten_rule_fields(
        SOURCE_RULES["ose_classic_fantasy"]
    )
```

`test_no_pending_badges_when_all_rules_implemented` / `test_no_pending_badge_for_ascending_ac` — still valid (the new template renders no `pending` badge). Keep.

`test_two_weapon_fighting_flag_is_implemented` reads `IMPLEMENTED_RULES` — keep `IMPLEMENTED_RULES`/`IMPLEMENTED_CHOICE_GROUPS` defined in `settings_routes.py` even though the template no longer renders pending badges (the regression tests still reference them).

The wizard-filter tests (`test_race_step_hides_advanced_when_disabled`, etc.) using `_new_draft_with_sources` continue to pass via legacy coercion. To also cover the granular path, add:
```python
def test_race_step_hides_advanced_via_disabled_content(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, drafts)
    draft["abilities"] = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 13, "CHA": 13}
    draft["abilities_confirmed"] = True
    draft["ruleset"]["disabled_content"] = ["ose_advanced_fantasy:classes"]
    save_draft(draft_id, draft, drafts)
    r = client.get(f"/wizard/{draft_id}/race")
    assert 'value="human"' in r.text
    assert 'value="elf"' not in r.text
```

The orphan-clear tests `test_disabling_source_clears_orphaned_race` and
`test_disabling_source_keeps_classic_race` post `{"creation_method": "advanced"}`
to `/wizard/{id}/rules`. Under the new form, that posts no `separate_race_class`
checkbox (→ flips to Basic, clearing race) and no content checkboxes (→ disables
everything). Replace both with form data that keeps separate race/class on and
re-checks all content except the source under test:

```python
def test_disabling_content_clears_orphaned_race(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    draft_id = _new_draft_with_sources(client, drafts, [])
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})  # advanced race
    draft = load_draft(draft_id, drafts)
    draft["ruleset"]["strict_mode"] = False
    save_draft(draft_id, draft, drafts)
    keys = _content_keys_for(client)
    data = {"separate_race_class": "on"}
    data.update({f"content_{k}": "on" for k in keys
                 if k != "ose_advanced_fantasy:classes"})
    client.post(f"/wizard/{draft_id}/rules", data=data)
    draft = load_draft(draft_id, drafts)
    assert "race_id" not in draft


def test_disabling_content_keeps_classic_race(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    draft_id = _new_draft_with_sources(client, drafts, [])
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})  # classic race
    draft = load_draft(draft_id, drafts)
    draft["ruleset"]["strict_mode"] = False
    save_draft(draft_id, draft, drafts)
    keys = _content_keys_for(client)
    data = {"separate_race_class": "on"}
    data.update({f"content_{k}": "on" for k in keys
                 if k != "ose_advanced_fantasy:classes"})
    client.post(f"/wizard/{draft_id}/rules", data=data)
    draft = load_draft(draft_id, drafts)
    assert draft.get("race_id") == "human"
```

Delete the old `test_disabling_source_clears_orphaned_race` and
`test_disabling_source_keeps_classic_race`.

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS. Fix any test still referencing removed symbols (`creation_method`, `RULE_GROUPS`, `source_*` form fields, `disabled_sources`).

- [ ] **Step 9: Manual smoke check**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Visit `/settings`: confirm Strict Mode toggle at top; one panel per source; Classic content checkboxes disabled+checked; unchecking "Separate Race and Class" greys Lifting/Human/Multi-classing; unchecking Lifting greys Human. Save, reload, confirm state persists. Repeat on a wizard `/rules` step.

- [ ] **Step 10: Commit**

```bash
git add aose/web/settings_routes.py aose/web/wizard.py aose/web/templates/_ruleset_fields.html tests/test_settings.py
git commit -F - <<'MSG'
feat(settings/wizard): source-panel ruleset UI

Rewrite the shared ruleset form into a standalone Strict Mode toggle plus
one expandable panel per source (derived content-category checkboxes +
nested optional-rule tree). Replace the Advanced/Basic radio with a
separate_race_class checkbox; rewrite parse_ruleset_from_form to enforce
the SOURCE_RULES dependency tree and build disabled_content from
per-category checkboxes. Generalized greying JS walks parent->child.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
```

---

## Task 4: Documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md` (the "Content sources & optional rules" section)
- Modify: `docs/CHANGELOG.md` (one-line row at top)
- Modify: `CLAUDE.md` (storage-shapes line)

- [ ] **Step 1: Update ARCHITECTURE.md**

Rewrite the "Content sources & optional rules" bullet (around line 428) to describe the new model. Replace the `disabled_sources` / `source_enabled` prose with:

```markdown
- **Sources** — `Source` model + `data/sources.yaml`. A `source` field on
  `ItemBase`/`Race`/`CharClass`/`SpellList`/`Enchantment`/`Spell` defaults to
  `ose_classic_fantasy`. Content is enabled per **category** (`classes` /
  `equipment` / `magic_items`), not per whole source.
  `RuleSet.disabled_content: list[str]` holds `"{source}:{category}"` keys
  (Classic categories never added). `aose/engine/sources.py`:
  `content_enabled(source_id, category, ruleset)` + `source_content_categories(data)`
  (categories derived from loaded data — classes/races ⇒ `classes`, non-magic
  items ⇒ `equipment`, magic items/enchantments ⇒ `magic_items`). A `RuleSet`
  `model_validator` coerces any legacy `disabled_sources` save into the
  equivalent category keys. Gated in wizard race/class steps (`classes`), spell
  candidates (`classes`), `shop_categories` (per-item `equipment`/`magic_items`),
  `_enchant_choices` (`magic_items`). Mid-wizard, disabling content clears
  orphaned race/class picks via `_apply_rule_changes`.
- **Optional rules** — every flag in `RuleSet` is integrated end-to-end. The
  settings page and wizard `/rules` step render one expandable panel per source
  (`_ruleset_fields.html`): a standalone Strict Mode toggle, then per-source
  Content (derived `content_rows_for_source`) + Optional Rules. Rules are
  attributed to their source and nested for dependencies via
  `SOURCE_RULES` (`settings_routes.py`); `parse_ruleset_from_form` enforces the
  tree (a child forced off when any ancestor is unchecked — this replaces the
  old Advanced/Basic creation-method radio; `separate_race_class` is now a
  nested checkbox). No "pending" badge ever renders (regression test guards this).
```

- [ ] **Step 2: Add CHANGELOG row**

Add to the top of `docs/CHANGELOG.md` (match the existing row format):

```markdown
| 2026-06-10 | Source-organized content & optional rules (per-category `disabled_content`, source-panel settings/wizard UI) | <current-branch> | source-content-rules-organization |
```

- [ ] **Step 3: Update CLAUDE.md storage-shapes line**

In `CLAUDE.md` under "Storage shapes", replace any `disabled_sources` mention with:

```markdown
- `RuleSet.disabled_content`: `list[str]` of `"{source}:{category}"` keys
  (category ∈ `classes`/`equipment`/`magic_items`); Classic categories never
  listed. Replaces the old whole-source `disabled_sources` (coerced on load).
```

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md docs/CHANGELOG.md CLAUDE.md
git commit -F - <<'MSG'
docs: source-organized content & optional rules

Update ARCHITECTURE (disabled_content + content_enabled + SOURCE_RULES
source panels), add CHANGELOG row, refresh CLAUDE.md storage-shapes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
```

---

## Final verification

- [ ] Run the full suite once more: `.venv\Scripts\python.exe -m pytest tests/ -q` — all green (ignore the `pytest-current` PermissionError).
- [ ] `grep` the repo for stragglers: no remaining references to `source_enabled`, `disabled_sources`, `RULE_GROUPS`, or `creation_method` outside the spec/plan/changelog history.
- [ ] Manual: `/settings` and a wizard `/rules` step render panels, greying works, content toggles persist and actually hide content (disable CC3 equipment → CC3 gear gone from the shop; disable Advanced magic items → Advanced enchant options gone).
```
