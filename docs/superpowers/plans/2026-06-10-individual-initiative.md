# Individual Initiative Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the optional "individual initiative" rule is active, show the player's initiative modifier (DEX-derived + racial/class bonuses) in the sheet's Combat box, with a clickable breakdown.

**Architecture:** A `RuleSet.individual_initiative` flag gates a display-only feature. The DEX→initiative values become a single numeric source in `ability_mods.py` (the existing display strings derive from it). Racial/class bonuses are pure `GrantedModifier` data via a new inert `initiative` modifier target; a generic `mechanical.requires_rule` flag hides rule-specific features when the rule is off. A small `engine/initiative.py` assembles the breakdown, mirroring `armor_class_detail`.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run python via `.venv\Scripts\python.exe`.

**Spec:** `docs/superpowers/specs/2026-06-10-individual-initiative-design.md`

**Conventions reminder:**
- Run tests: `.venv\Scripts\python.exe -m pytest tests/ -q` (the trailing `pytest-current` PermissionError on Windows is a known, ignorable quirk).
- The minus sign in the existing DEX display table is U+2212 (`−`), **not** ASCII hyphen. Preserve it.
- No data migrations needed; the app is local-only.

---

## File map

- `aose/engine/ability_mods.py` — replace `_DEX_INIT` with a numeric source; add `initiative_modifier`.
- `aose/models/ruleset.py` — add `individual_initiative` flag.
- `aose/web/settings_routes.py` — register the rule (label, group, implemented).
- `aose/models/modifier.py` — document the new `initiative` target.
- `data/races/halfling.yaml`, `data/classes/halfling.yaml`, `data/races/human.yaml` — add `granted_modifiers` + `requires_rule`.
- `aose/engine/initiative.py` — **new**: `initiative_detail` + line/detail models.
- `aose/sheet/view.py` — `_feature_visible` filter; new `CharacterSheet` fields; `build_sheet` wiring; `OPTIONAL_RULE_LABELS`.
- `aose/web/templates/sheet.html` — INIT field + `modal-init`.
- `aose/web/static/sheet.css` — `combat-top` layout for HP+INIT row.
- `aose/web/templates/sheet_print.html` — INIT stat row.
- `tests/test_initiative.py` — **new**: all engine/visibility/render tests.
- `tests/test_settings.py` — flag-implemented test.
- `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md` — docs.

---

## Task 1: Single-source DEX initiative table + `initiative_modifier`

**Files:**
- Modify: `aose/engine/ability_mods.py` (the `_DEX_INIT` definition near line 45)
- Test: `tests/test_initiative.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_initiative.py`:

```python
"""Individual-initiative optional rule: DEX modifier, engine breakdown,
feature gating, and sheet rendering."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.data.loader import GameData
from aose.engine.ability_mods import initiative_modifier, ability_table_row
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# ── DEX → initiative modifier (single source of truth) ──────────────────────
@pytest.mark.parametrize("score,expected", [
    (2, -2), (3, -2),               # clamp below 3
    (4, -1), (8, -1),
    (9, 0), (12, 0),
    (13, 1), (17, 1),
    (18, 2), (19, 2),               # clamp above 18
])
def test_initiative_modifier_table(score, expected):
    assert initiative_modifier(score) == expected


def test_dex_init_display_row_unchanged():
    """The Initiative cell of the DEX reference row still renders the book
    strings (derived from the same numeric source)."""
    def init_cell(score):
        return dict(ability_table_row("DEX", score))["Initiative"]
    assert init_cell(3) == "−2"     # U+2212
    assert init_cell(7) == "−1"
    assert init_cell(10) == "None"
    assert init_cell(15) == "+1"
    assert init_cell(18) == "+2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -q`
Expected: FAIL — `ImportError: cannot import name 'initiative_modifier'`.

- [ ] **Step 3: Implement the single-source table + helper**

In `aose/engine/ability_mods.py`, replace the line:

```python
_DEX_INIT = {3: "−2", 4: "−1", 9: "None", 13: "+1", 18: "+2"}
```

with:

```python
# Numeric source of truth for the DEX initiative modifier (used by the
# individual-initiative optional rule). The display column below derives from
# it so the two never drift.
_DEX_INIT_VALUES = {3: -2, 4: -1, 9: 0, 13: 1, 18: 2}


def _fmt_init(value: int) -> str:
    if value == 0:
        return "None"
    return f"+{value}" if value > 0 else f"−{abs(value)}"  # U+2212 minus


_DEX_INIT = {k: _fmt_init(v) for k, v in _DEX_INIT_VALUES.items()}


def initiative_modifier(score: int) -> int:
    """DEX initiative modifier (banded; clamps below 3 and above 18)."""
    chosen = _DEX_INIT_VALUES[min(_DEX_INIT_VALUES)]
    for threshold in sorted(_DEX_INIT_VALUES):
        if score >= threshold:
            chosen = _DEX_INIT_VALUES[threshold]
    return chosen
```

(`initiative_modifier` can be placed right after `ability_modifier`, near the top; the table lines stay where `_DEX_INIT` was so `_DEX_AC`/`_ABILITY_COLUMNS` references resolve.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py tests/test_ability_tables.py -q`
Expected: PASS (the existing ability-table tests must stay green — the display strings are unchanged).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/ability_mods.py tests/test_initiative.py
git commit -m "feat(engine): single-source DEX initiative modifier"
```

---

## Task 2: `RuleSet.individual_initiative` flag + settings wiring

**Files:**
- Modify: `aose/models/ruleset.py:24` (after `two_weapon_fighting`)
- Modify: `aose/web/settings_routes.py` (`RULE_LABELS`, `IMPLEMENTED_RULES`, `RULE_GROUPS` Combat group)
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings.py` (near `test_two_weapon_fighting_flag_is_implemented`):

```python
def test_individual_initiative_flag_is_implemented():
    from aose.web.settings_routes import RULE_LABELS, IMPLEMENTED_RULES, RULE_GROUPS
    from aose.models import RuleSet

    assert RuleSet().individual_initiative is False
    assert "individual_initiative" in RULE_LABELS
    assert "individual_initiative" in IMPLEMENTED_RULES
    combat_fields = dict(RULE_GROUPS)["Combat"]
    assert any(f == "individual_initiative" for f, _ in combat_fields)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py::test_individual_initiative_flag_is_implemented -q`
Expected: FAIL — `AttributeError` / assertion on missing key.

- [ ] **Step 3: Add the flag**

In `aose/models/ruleset.py`, add after the `two_weapon_fighting` line:

```python
    individual_initiative: bool = False
```

- [ ] **Step 4: Register the rule in settings**

In `aose/web/settings_routes.py`:

Add to `RULE_LABELS`:

```python
    "individual_initiative": "Individual Initiative",
```

Add to `IMPLEMENTED_RULES`:

```python
    "individual_initiative",
```

Add to the `"Combat"` entry of `RULE_GROUPS` (alongside the other combat rules):

```python
        ("individual_initiative",
         "Roll initiative for each combatant individually, modified by DEX, "
         "instead of one roll per side. Shows your initiative modifier on the "
         "sheet."),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS — including `test_no_pending_badges_when_all_rules_implemented` (the new rule is in `IMPLEMENTED_RULES`).

- [ ] **Step 6: Commit**

```bash
git add aose/models/ruleset.py aose/web/settings_routes.py tests/test_settings.py
git commit -m "feat(rules): individual_initiative flag + settings toggle"
```

---

## Task 3: `initiative` modifier target + racial/class grants

**Files:**
- Modify: `aose/models/modifier.py` (target-grammar docstring, ~line 26)
- Modify: `data/races/halfling.yaml` (`initiative_bonus_optional_rule`)
- Modify: `data/classes/halfling.yaml` (`initiative_bonus_optional_rule`)
- Modify: `data/races/human.yaml` (`decisiveness`)
- Test: `tests/test_initiative.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_initiative.py`:

```python
def test_initiative_grants_present_in_data():
    data = GameData.load(DATA_DIR)

    def init_grant(feature):
        return [g for g in feature.granted_modifiers if g.target == "initiative"]

    halfling_race = data.races["halfling"]
    feat = next(f for f in halfling_race.features
                if f.id == "initiative_bonus_optional_rule")
    assert init_grant(feat) and init_grant(feat)[0].value == 1
    assert (feat.mechanical or {}).get("requires_rule") == "individual_initiative"

    halfling_class = data.classes["halfling"]
    cfeat = next(f for f in halfling_class.features
                 if f.id == "initiative_bonus_optional_rule")
    assert init_grant(cfeat) and init_grant(cfeat)[0].value == 1
    assert (cfeat.mechanical or {}).get("requires_rule") == "individual_initiative"

    human = data.races["human"]
    dec = next(f for f in human.features if f.id == "decisiveness")
    assert init_grant(dec) and init_grant(dec)[0].value == 1
    # Decisiveness always shows — it must NOT carry requires_rule.
    assert (dec.mechanical or {}).get("requires_rule") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py::test_initiative_grants_present_in_data -q`
Expected: FAIL — no `initiative` grant on the features yet.

- [ ] **Step 3: Document the target**

In `aose/models/modifier.py`, in the `target` grammar list inside the `Modifier` docstring, add `initiative` to the enumerated targets (after `thac0`), e.g.:

```
    ``attack``, ``damage``, ``carry_capacity``, ``thac0``, ``initiative``.
```

- [ ] **Step 4: Add the data grants**

In `data/races/halfling.yaml`, change the `initiative_bonus_optional_rule` feature to:

```yaml
- id: initiative_bonus_optional_rule
  name: Initiative Bonus (Optional Rule)
  text: If using the optional rule for individual initiative, gains a +1 bonus to initiative rolls.
  mechanical:
    optional_rule: true
    initiative_bonus: 1
    condition: individual_initiative
    requires_rule: individual_initiative
  granted_modifiers:
  - {target: initiative, op: add, value: 1}
```

In `data/classes/halfling.yaml`, change the `initiative_bonus_optional_rule` feature to:

```yaml
- id: initiative_bonus_optional_rule
  name: Initiative Bonus (Optional Rule)
  text: |-
    If using the optional rule for individual initiative (see Combat, p222), halflings get a bonus of +1 to initiative rolls.
  gained_at_level: 1
  mechanical:
    requires_rule: individual_initiative
  granted_modifiers:
  - {target: initiative, op: add, value: 1}
```

In `data/races/human.yaml`, change the `decisiveness` feature to add a grant (leave its existing `mechanical` block intact; do **not** add `requires_rule`):

```yaml
- id: decisiveness
  name: Decisiveness
  text: When an initiative roll is tied, humans act first, as if they had won initiative. If using the optional rule for individual initiative, humans get a +1 bonus to initiative rolls.
  mechanical:
    optional_rule: true
    wins_tied_initiative: true
    individual_initiative_bonus: 1
  granted_modifiers:
  - {target: initiative, op: add, value: 1}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py::test_initiative_grants_present_in_data -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/modifier.py data/races/halfling.yaml data/classes/halfling.yaml data/races/human.yaml tests/test_initiative.py
git commit -m "feat(content): initiative target grants for halfling & human"
```

---

## Task 4: `engine/initiative.py` — breakdown assembly

**Files:**
- Create: `aose/engine/initiative.py`
- Test: `tests/test_initiative.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_initiative.py`:

```python
from aose.engine.initiative import initiative_detail


def _spec(race_id, class_id, dex, *, individual_init=True, level=1):
    return CharacterSpec(
        name="Pip",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": dex, "CON": 10, "CHA": 10},
        race_id=race_id,
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[5])],
        alignment="law",
        ruleset=RuleSet(individual_initiative=individual_init),
    )


def test_initiative_detail_dex_only():
    data = GameData.load(DATA_DIR)
    # Human fighter, DEX 13 → +1 from DEX, +1 from Decisiveness = +2
    det = initiative_detail(_spec("human", "fighter", 13), data)
    assert det.base == 1
    assert det.total == 2
    assert det.lines[0].source == "Dexterity" and det.lines[0].bonus == 1
    assert any(l.source == "Decisiveness" and l.bonus == 1 for l in det.lines)


def test_initiative_detail_halfling_split():
    data = GameData.load(DATA_DIR)
    # Halfling thief, DEX 9 → 0 from DEX, +1 from race feature = +1
    det = initiative_detail(_spec("halfling", "thief", 9), data)
    assert det.base == 0
    assert det.total == 1
    assert any(l.bonus == 1 for l in det.lines[1:])


def test_initiative_detail_halfling_race_as_class():
    data = GameData.load(DATA_DIR)
    # Halfling-as-class, DEX 18 → +2 DEX, +1 class feature = +3
    spec = CharacterSpec(
        name="Pip",
        abilities={"STR": 9, "INT": 10, "WIS": 10, "DEX": 18, "CON": 12, "CHA": 10},
        race_id="halfling",
        classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
        alignment="law",
        ruleset=RuleSet(separate_race_class=False, individual_initiative=True),
    )
    det = initiative_detail(spec, data)
    assert det.base == 2
    assert det.total == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -k detail -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.initiative'`.

- [ ] **Step 3: Implement the engine module**

Create `aose/engine/initiative.py`:

```python
"""Initiative modifier breakdown for the individual-initiative optional rule.

Display-only: the sheet renders this only when ``ruleset.individual_initiative``
is set. Cycle-free — imports ability_mods, magic, and features; none import this.
"""
from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec
from aose.engine.ability_mods import initiative_modifier
from aose.engine.features import all_modifiers
from aose.engine.magic import effective_abilities


class InitiativeLine(BaseModel):
    source: str          # "Dexterity", feature/item name
    bonus: int
    conditional: bool
    note: str            # condition note ("" when unconditional)


class InitiativeDetail(BaseModel):
    base: int                       # DEX initiative modifier
    total: int                      # base + unconditional bonuses
    lines: list[InitiativeLine]
    has_conditional: bool


def initiative_detail(spec: CharacterSpec, data: GameData) -> InitiativeDetail:
    eff = effective_abilities(spec, data)
    base = initiative_modifier(eff[Ability.DEX])
    lines = [InitiativeLine(source="Dexterity", bonus=base,
                            conditional=False, note="")]
    total = base
    for m in all_modifiers(spec, data):
        if m.target != "initiative":
            continue
        conditional = m.condition is not None
        lines.append(InitiativeLine(
            source=m.source or "Bonus",
            bonus=m.value,
            conditional=conditional,
            note=(m.condition.replace("_", " ") if conditional else ""),
        ))
        if not conditional:
            total += m.value
    return InitiativeDetail(
        base=base, total=total, lines=lines,
        has_conditional=any(l.conditional for l in lines),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/initiative.py tests/test_initiative.py
git commit -m "feat(engine): initiative_detail breakdown"
```

---

## Task 5: Feature-visibility gating (`requires_rule`)

**Files:**
- Modify: `aose/sheet/view.py` (add `_feature_visible`; apply in `_race_features` ~line 629 and `_class_features` ~line 639)
- Test: `tests/test_initiative.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_initiative.py`:

```python
from aose.sheet.view import _race_features, _class_features


def test_halfling_initiative_feature_hidden_when_rule_off():
    data = GameData.load(DATA_DIR)
    names = lambda spec: [f.name for f in _race_features(spec, data)]
    off = _spec("halfling", "thief", 12, individual_init=False)
    on = _spec("halfling", "thief", 12, individual_init=True)
    assert "Initiative Bonus (Optional Rule)" not in names(off)
    assert "Initiative Bonus (Optional Rule)" in names(on)


def test_halfling_race_as_class_initiative_feature_gated():
    data = GameData.load(DATA_DIR)
    def cls_names(individual_init):
        spec = CharacterSpec(
            name="Pip",
            abilities={"STR": 9, "INT": 10, "WIS": 10, "DEX": 12, "CON": 12, "CHA": 10},
            race_id="halfling",
            classes=[ClassEntry(class_id="halfling", level=1, hp_rolls=[6])],
            alignment="law",
            ruleset=RuleSet(separate_race_class=False,
                            individual_initiative=individual_init),
        )
        return [f.name for f in _class_features(spec, data)]
    assert "Initiative Bonus (Optional Rule)" not in cls_names(False)
    assert "Initiative Bonus (Optional Rule)" in cls_names(True)


def test_human_decisiveness_always_shown():
    data = GameData.load(DATA_DIR)
    names = lambda spec: [f.name for f in _race_features(spec, data)]
    off = _spec("human", "fighter", 12, individual_init=False)
    assert "Decisiveness" in names(off)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -k "hidden or gated or always" -q`
Expected: FAIL — the halfling feature shows regardless of the rule.

- [ ] **Step 3: Implement the filter**

In `aose/sheet/view.py`, add a helper (place near the other `_*_features` helpers, before `_race_features`):

```python
def _feature_visible(feat, ruleset: RuleSet) -> bool:
    """A feature whose ``mechanical.requires_rule`` names a RuleSet flag is
    hidden when that flag is off; otherwise always visible."""
    rule = (getattr(feat, "mechanical", None) or {}).get("requires_rule")
    if rule is None:
        return True
    return bool(getattr(ruleset, rule, False))
```

Replace `_race_features` with:

```python
def _race_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    if _is_race_as_class(spec, data):
        return []
    race = data.races[spec.race_id]
    rs = spec.ruleset
    rows = [_feature_row(f, f"Race: {race.name}", data)
            for f in race.features if _feature_visible(f, rs)]
    rows += [_feature_row(o, f"Race: {race.name}", data)
             for o in selected_options(race, spec.feature_choices)
             if _feature_visible(o, rs)]
    return rows
```

Replace `_class_features` with:

```python
def _class_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    out: list[SheetFeature] = []
    rs = spec.ruleset
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        for f in cls.features:
            if f.gained_at_level <= entry.level and _feature_visible(f, rs):
                out.append(_feature_row(f, f"Class: {cls.name}", data))
        for o in selected_options(cls, spec.feature_choices):
            if _feature_visible(o, rs):
                out.append(_feature_row(o, f"Class: {cls.name}", data))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_initiative.py
git commit -m "feat(sheet): hide rule-gated features via mechanical.requires_rule"
```

---

## Task 6: `CharacterSheet` fields + `build_sheet` wiring

**Files:**
- Modify: `aose/sheet/view.py` (`OPTIONAL_RULE_LABELS` ~line 44; `CharacterSheet` fields ~line 386; `build_sheet` ~line 1242)
- Test: `tests/test_initiative.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_initiative.py`:

```python
from aose.sheet.view import build_sheet


def test_build_sheet_exposes_initiative_when_rule_on():
    data = GameData.load(DATA_DIR)
    sheet = build_sheet(_spec("human", "fighter", 13, individual_init=True), data)
    assert sheet.individual_initiative is True
    assert sheet.initiative_modifier == 2          # +1 DEX, +1 Decisiveness
    assert sheet.initiative_lines[0].source == "Dexterity"
    assert "Individual Initiative" in sheet.enabled_optional_rules


def test_build_sheet_initiative_off_by_default():
    data = GameData.load(DATA_DIR)
    sheet = build_sheet(_spec("human", "fighter", 13, individual_init=False), data)
    assert sheet.individual_initiative is False
    assert "Individual Initiative" not in sheet.enabled_optional_rules
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -k build_sheet -q`
Expected: FAIL — `CharacterSheet` has no `individual_initiative` field.

- [ ] **Step 3: Add the import**

In `aose/sheet/view.py`, add to the engine imports near the top:

```python
from aose.engine.initiative import initiative_detail
```

- [ ] **Step 4: Register the optional-rule label**

In `OPTIONAL_RULE_LABELS`, add:

```python
    "individual_initiative": "Individual Initiative",
```

- [ ] **Step 5: Add the sheet fields**

In the `CharacterSheet` model, after the `attack_has_conditional: bool` line, add:

```python
    individual_initiative: bool
    initiative_modifier: int
    initiative_lines: list[SheetAttackLine]
    initiative_has_conditional: bool
```

- [ ] **Step 6: Wire `build_sheet`**

In `build_sheet`, after the attack breakdown block (where `attack_line_rows` is built), add:

```python
    init_detail = initiative_detail(spec, data)
    initiative_line_rows = [
        SheetAttackLine(source=ln.source, bonus=ln.bonus,
                        conditional=ln.conditional, note=ln.note)
        for ln in init_detail.lines
    ]
```

Then in the `CharacterSheet(...)` constructor, after `attack_has_conditional=...`, add:

```python
        individual_initiative=spec.ruleset.individual_initiative,
        initiative_modifier=init_detail.total,
        initiative_lines=initiative_line_rows,
        initiative_has_conditional=init_detail.has_conditional,
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py tests/test_sheet.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py tests/test_initiative.py
git commit -m "feat(sheet): expose initiative modifier on CharacterSheet"
```

---

## Task 7: Combat-box UI — INIT field, modal, CSS, print

**Files:**
- Modify: `aose/web/templates/sheet.html` (`combat-top` ~lines 100–114; add `modal-init` after `modal-ac` ~line 714)
- Modify: `aose/web/static/sheet.css` (`combat-top`/`shield` ~lines 111–120)
- Modify: `aose/web/templates/sheet_print.html` (after the THAC0 block ~line 73)
- Test: `tests/test_initiative.py`

Background: per the approved mockup, HP and INIT sit as stacked-label boxes in a row at top-left, THAC0 spans below them, and the AC shield stays large on the right. HP becomes a `col-field` (label-on-top) box to match. Read `docs/STYLE-GUIDE.md` before editing CSS.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_initiative.py`. The character's own `ruleset` is stored in
its spec, so the page reflects `spec.ruleset` regardless of the global settings
file — no `save_settings` needed. `save_character(char_id, spec, dir)` writes
`<char_id>.json`; the route is `GET /character/<char_id>`.

```python
def _render(tmp_path, spec, char_id):
    from aose.characters import save_character
    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir,
        drafts_dir=tmp_path / "drafts", examples_dir=examples_dir,
        settings_path=tmp_path / "settings.json",
    )
    save_character(char_id, spec, characters_dir)
    client = TestClient(app, follow_redirects=False)
    return client.get(f"/character/{char_id}")


def test_sheet_renders_init_box_only_when_rule_on(tmp_path):
    on = _render(tmp_path / "on",
                 _spec("human", "fighter", 13, individual_init=True), "pip_on")
    assert on.status_code == 200
    assert 'id="modal-init"' in on.text
    assert ">INIT" in on.text          # the INIT tab label

    off = _render(tmp_path / "off",
                  _spec("human", "fighter", 13, individual_init=False), "pip_off")
    assert off.status_code == 200
    assert 'id="modal-init"' not in off.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -k renders_init -q`
Expected: FAIL — no `modal-init` in the page.

- [ ] **Step 3: Restructure the `combat-top` markup**

In `aose/web/templates/sheet.html`, replace the `combat-top` block (the `<div class="combat-top"> … </div>` containing HP, shield, THAC0) with:

```html
          <div class="combat-top">
            <div class="combat-stats">
              <div class="hp-init">
                <div class="field col-field editable" data-pop="pop-hp">
                  <span class="tab">HP</span>
                  <span class="box big">{{ sheet.current_hp }}<span style="font-size:13px;color:var(--gray)"> / {{ sheet.max_hp }}</span></span>
                </div>
                {% if sheet.individual_initiative %}
                <div class="field col-field editable" data-modal="modal-init" title="Show initiative breakdown">
                  <span class="tab">INIT{% if sheet.initiative_has_conditional %}<span class="cond-mark" title="Has a conditional modifier — tap for details">★</span>{% endif %}</span>
                  <span class="box" style="font-weight:600">{{ "%+d"|format(sheet.initiative_modifier) }}</span>
                </div>
                {% endif %}
              </div>
              <div class="field col-field editable" data-modal="modal-matrix" title="Show attack breakdown">
                <span class="tab">{{ 'ATTACK' if sheet.use_ascending else 'THAC0' }}{% if sheet.attack_has_conditional %}<span class="cond-mark" title="Has a conditional modifier — tap for details">★</span>{% endif %}</span>
                <span class="box" style="font-weight:600">{% if sheet.use_ascending %}{{ "%+d"|format(sheet.attack_bonus) }}{% else %}{{ sheet.thac0 }}{% endif %}</span>
              </div>
            </div>
            <div class="shield{% if sheet.ac_has_conditional %} clickable{% endif %}"{% if sheet.ac_has_conditional %} data-modal="modal-ac"{% endif %}>
              <div class="lab">Armour Class{% if sheet.ac_has_conditional %}<span class="cond-mark" title="Has a conditional modifier — tap for details">★</span>{% endif %}</div>
              <div class="ac">{% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}</div>
              <div class="unarm">unarmoured <b>{% if sheet.use_ascending %}{{ sheet.unarmored_ac_ascending }}{% else %}{{ sheet.unarmored_ac_descending }}{% endif %}</b></div>
            </div>
          </div>
```

- [ ] **Step 4: Add the breakdown modal**

In `aose/web/templates/sheet.html`, immediately after the `modal-ac` block (closes at the `</div>` near line 714), add:

```html
{% if sheet.individual_initiative %}
<div class="overlay modal" id="modal-init" role="dialog" aria-label="Initiative">
  <div class="ov-head"><h3>Initiative</h3><button class="x" data-close>×</button></div>
  <div class="ov-body" style="font-size:14px">
    <p style="margin:0 0 6px">Initiative modifier <strong>{{ "%+d"|format(sheet.initiative_modifier) }}</strong></p>
    <ul style="list-style:none;margin:0;padding:0">
      {% for ln in sheet.initiative_lines %}
      <li style="margin:2px 0">
        <strong>{{ ln.source }}:</strong>
        {% if ln.bonus >= 0 %}+{{ ln.bonus }}{% else %}{{ ln.bonus }}{% endif %}
        {% if ln.conditional %}<span class="muted"> — {{ ln.note }}</span>{% endif %}
      </li>
      {% endfor %}
    </ul>
  </div>
</div>
{% endif %}
```

- [ ] **Step 5: Update the CSS**

In `aose/web/static/sheet.css`, replace the `.combat-top` and `.shield` rules (lines ~111–112) with:

```css
.combat-top{ display:grid; grid-template-columns:1fr 1fr; gap:8px; align-items:stretch; }
.combat-stats{ display:flex; flex-direction:column; gap:8px; }
.hp-init{ display:flex; gap:8px; }
.hp-init > *{ flex:1; min-width:0; }
.shield{ display:flex; flex-direction:column; align-items:center; justify-content:center; border:2px solid var(--ink); background:var(--box); padding:4px; }
```

(`grid-row:span 2` is removed from `.shield`: `combat-top` now has two direct children — `.combat-stats` and `.shield` — so the shield fills the right cell and stretches to the left column's height. The `.shield .lab/.ac/.unarm` rules below are unchanged.)

- [ ] **Step 6: Add the print row**

In `aose/web/templates/sheet_print.html`, after the THAC0/Attack-Bonus `stat-row` block (the `{% endif %}` near line 73, before the `{% if sheet.attack_has_conditional %}` block), add:

```html
        {% if sheet.individual_initiative %}
        <div class="stat-row">
            <span>Initiative</span>
            <span class="stat-big">{{ "%+d"|format(sheet.initiative_modifier) }}</span>
        </div>
        {% endif %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_initiative.py -q`
Expected: PASS.

- [ ] **Step 8: Visual verification**

Start the server and verify both states in the browser preview (use the preview tools; do not ask the user to check manually):

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

Verify on a halfling or human character with the rule on: HP + INIT sit side-by-side at top-left, THAC0 below, AC shield large on the right (matches the mockup); clicking INIT opens the breakdown modal listing Dexterity + the racial/class bonus. Toggle the rule off (via `/settings` or the wizard rules step) and confirm the INIT box and the halfling "Initiative Bonus (Optional Rule)" feature both disappear, while Human "Decisiveness" remains. Capture a screenshot of the rule-on combat box.

- [ ] **Step 9: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/static/sheet.css aose/web/templates/sheet_print.html tests/test_initiative.py
git commit -m "feat(sheet): INIT combat box + breakdown modal"
```

---

## Task 8: Documentation

**Files:**
- Modify: `docs/CHANGELOG.md` (top row of the table)
- Modify: `docs/ARCHITECTURE.md` (modifier-pipeline / features section)

- [ ] **Step 1: Add the changelog row**

In `docs/CHANGELOG.md`, add as the new top data row of the table:

```
| 2026-06-10 | Individual initiative optional rule: DEX-derived initiative modifier in the Combat box (clickable breakdown) + halfling/human bonuses; generic `mechanical.requires_rule` feature gating | feat/individual-initiative | 2026-06-10-individual-initiative |
```

- [ ] **Step 2: Update ARCHITECTURE.md**

Find the modifier-pipeline / feature-grants section in `docs/ARCHITECTURE.md` and update it in place to note: (a) the new inert `initiative` modifier target consumed only by `engine/initiative.py`; (b) the `mechanical.requires_rule` convention that hides a feature from the sheet when the named `RuleSet` flag is off; (c) that `engine/initiative.py` is display-only, rendered solely when `individual_initiative` is set. Edit the existing topic — do not append a dated entry.

- [ ] **Step 3: Full test run**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: individual initiative optional rule"
```

---

## Self-review notes

- **Spec coverage:** Rule flag → Task 2; single-source DEX table + `initiative_modifier` → Task 1; `initiative` target + grants → Task 3; `initiative_detail` → Task 4; `requires_rule` gating → Task 5; sheet fields/wiring + `OPTIONAL_RULE_LABELS` → Task 6; combat-box UI + modal + print + CSS → Task 7; tests across Tasks 1–7; docs → Task 8. No cascading-clear work (intentionally none — noted in spec §1).
- **Type consistency:** `initiative_detail` returns `InitiativeDetail{base,total,lines,has_conditional}` with `InitiativeLine{source,bonus,conditional,note}`; `build_sheet` maps those lines to `SheetAttackLine` (same field names) and uses `init_detail.total` for `initiative_modifier`. `_feature_visible(feat, ruleset)` is used by both `_race_features` and `_class_features`.
- **API confirmed:** `save_character(char_id, spec, characters_dir)` and route `GET /character/<char_id>` verified against `aose/characters/storage.py` and `tests/test_sheet.py`; the sheet reflects `spec.ruleset`, so render tests need no settings file.
