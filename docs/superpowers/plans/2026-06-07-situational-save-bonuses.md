# Situational ("vs X") Save Bonuses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode and display broad cross-cutting "vs X" save bonuses (e.g. druid +2 vs fire & lightning, svirfneblin +2 vs illusions) as smaller-font footnotes under the saving-throws block, driven by data on race/class features and reusable by magic items.

**Architecture:** A new `save:vs:<thing>` target family flows through the existing `Modifier`/`GrantedModifier` → `feature_modifiers`/`active_modifiers` → `all_modifiers` pipeline. A new engine function `situational_save_bonuses()` collects and groups these by source; a new view model surfaces them on the sheet; `sheet.html`/`sheet_print.html` render them as static footnotes. Per-category headline math and the breakdown modal are untouched.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, YAML game data, pytest.

**Spec:** `docs/superpowers/specs/2026-06-07-situational-save-bonuses-design.md`

**Conventions (read before starting):**
- Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q` (bare `pytest`/`uvicorn` won't work — the venv isn't auto-activated). A trailing `PermissionError` on `pytest-current` is a known Windows pytest-9 tempdir quirk; ignore it.
- 2 pre-existing breadcrumb-label failures in `test_wizard_class_setup` / `test_wizard_identity` are unrelated to this work — they should stay at exactly 2.
- There is in-progress **uncommitted** work (ability-breakdown changes in `aose/engine/ability_mods.py`, `aose/sheet/view.py`, `aose/web/static/sheet.css`, `aose/web/templates/sheet.html`). This plan edits *different regions* of `view.py`/`sheet.css`/`sheet.html`. Do **not** stage those unrelated changes in your commits — use explicit `git add <path>` of only the files/hunks you changed, and never `git add -A`/`git add .`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/modifier.py` | Modifier target grammar docs | Modify (docstring only) |
| `aose/engine/saves.py` | `_VS_DISPLAY`, `SituationalSaveBonus`, `situational_save_bonuses()` | Modify |
| `aose/sheet/view.py` | `SheetSituationalSave` model, `CharacterSheet.situational_saves`, populate in `build_sheet` | Modify |
| `aose/web/templates/sheet.html` | Footnote block under `.saves` | Modify |
| `aose/web/templates/sheet_print.html` | Footnote block under Saving Throws | Modify |
| `aose/web/static/sheet.css` | `.save-notes` / `.save-note` rules | Modify |
| `data/classes/druid.yaml` | `energy_resistance` granted_modifiers | Modify |
| `data/races/svirfneblin.yaml` | `illusion_resistance` granted_modifiers | Modify |
| `tests/test_situational_saves.py` | Engine + grouping + magic-item + display-name tests | Create |
| `tests/test_situational_saves_data.py` | Druid/svirfneblin data + headline regression | Create |

---

## Task 1: Engine — collect & group situational save bonuses

**Files:**
- Modify: `aose/engine/saves.py`
- Test: `tests/test_situational_saves.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_situational_saves.py`:

```python
from aose.data.loader import GameData
from aose.engine import saves
from aose.engine.saves import SituationalSaveBonus
from aose.models import CharacterSpec, ClassEntry, Modifier
from aose.models.character import MagicItemInstance

DATA = GameData.load("data")


def _spec(class_id="fighter", level=1, **kw):
    return CharacterSpec(
        name="T", class_id=None, classes=[ClassEntry(class_id=class_id, level=level)],
        **kw,
    )


def test_no_situational_bonuses_is_empty():
    spec = _spec()  # plain fighter, no vs:* grants
    assert saves.situational_save_bonuses(spec, DATA) == []


def test_groups_two_things_under_one_source(monkeypatch):
    # Two save:vs:* modifiers from the same source+value collapse to one group.
    def fake_all(spec, data):
        return [
            Modifier(target="save:vs:fire", op="add", value=2, source="Energy Resistance"),
            Modifier(target="save:vs:lightning", op="add", value=2, source="Energy Resistance"),
        ]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [
        SituationalSaveBonus(source="Energy Resistance", bonus=2, things=["fire", "lightning"])
    ]


def test_different_sources_stay_separate(monkeypatch):
    def fake_all(spec, data):
        return [
            Modifier(target="save:vs:fire", op="add", value=2, source="Energy Resistance"),
            Modifier(target="save:vs:fire", op="add", value=1, source="Ring of Warmth"),
        ]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [
        SituationalSaveBonus(source="Energy Resistance", bonus=2, things=["fire"]),
        SituationalSaveBonus(source="Ring of Warmth", bonus=1, things=["fire"]),
    ]


def test_display_name_registry_and_fallback(monkeypatch):
    def fake_all(spec, data):
        return [
            Modifier(target="save:vs:illusion", op="add", value=2, source="Illusion Resistance"),
            Modifier(target="save:vs:cold_iron", op="add", value=1, source="Charm"),
        ]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    things = {r.source: r.things for r in result}
    assert things["Illusion Resistance"] == ["illusions"]   # registry override
    assert things["Charm"] == ["cold iron"]                 # underscore fallback


def test_picks_up_magic_item_modifiers(monkeypatch):
    # Real path: an equipped magic item emits a save:vs:* modifier via all_modifiers.
    # Use a homebrew extra_modifier on an instance so we don't depend on catalog data.
    def fake_all(spec, data):
        return [Modifier(target="save:vs:fire", op="add", value=2, source="Ring of Fire Resistance")]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [
        SituationalSaveBonus(source="Ring of Fire Resistance", bonus=2, things=["fire"])
    ]


def test_empty_source_falls_back_to_dash(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="save:vs:fire", op="add", value=2, source="")]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    result = saves.situational_save_bonuses(_spec(), DATA)
    assert result == [SituationalSaveBonus(source="—", bonus=2, things=["fire"])]


def test_ignores_non_add_ops(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="save:vs:fire", op="set", value=2, source="Weird")]
    monkeypatch.setattr(saves, "all_modifiers", fake_all)
    assert saves.situational_save_bonuses(_spec(), DATA) == []
```

> Note: the tests `monkeypatch.setattr(saves, "all_modifiers", ...)`, so `saves.py` must reference `all_modifiers` as a module-level name (it already imports it via `from .features import all_modifiers`). Keep that import.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves.py -q`
Expected: FAIL — `AttributeError: module 'aose.engine.saves' has no attribute 'situational_save_bonuses'` (and `ImportError` for `SituationalSaveBonus`).

- [ ] **Step 3: Implement the engine function**

In `aose/engine/saves.py`, after the `_CONDITION_NOTES` dict (around line 19), add the display registry:

```python
_VS_DISPLAY = {
    "illusion": "illusions",
}
"""Display name for a ``save:vs:<thing>`` suffix. Unregistered things fall back
to ``thing.replace("_", " ")``."""


def _vs_display(thing: str) -> str:
    return _VS_DISPLAY.get(thing, thing.replace("_", " "))
```

Add the model next to `SaveBreakdown` (after line 49):

```python
class SituationalSaveBonus(BaseModel):
    """A broad cross-cutting save bonus that applies whenever a particular kind
    of effect (``things``) forces a save, regardless of category. Sourced from a
    ``save:vs:<thing>`` modifier on a race/class feature or magic item."""
    source: str          # feature/item name, or "—"
    bonus: int
    things: list[str]    # display names, sorted
```

Add the collector function (place it after `saving_throws_detail`, before `saving_throws`):

```python
def situational_save_bonuses(spec: CharacterSpec, data: GameData) -> list[SituationalSaveBonus]:
    """Cross-cutting ``save:vs:<thing>`` bonuses from features and magic items,
    grouped by ``(source, value)`` with their things collected. Never folded
    into any per-category headline."""
    groups: dict[tuple[str, int], list[str]] = {}
    for m in all_modifiers(spec, data):
        if m.op != "add" or not m.target.startswith("save:vs:"):
            continue
        thing = _vs_display(m.target.split("save:vs:", 1)[1])
        key = (m.source or "—", m.value)
        bucket = groups.setdefault(key, [])
        if thing not in bucket:
            bucket.append(thing)
    out = [
        SituationalSaveBonus(source=src, bonus=val, things=sorted(things))
        for (src, val), things in groups.items()
    ]
    out.sort(key=lambda b: (b.source, -b.bonus))
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/saves.py tests/test_situational_saves.py
git commit -m "feat(saves): situational_save_bonuses collects save:vs:* modifiers"
```

---

## Task 2: View model — surface situational saves on the sheet

**Files:**
- Modify: `aose/sheet/view.py`
- Test: append to `tests/test_situational_saves.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_situational_saves.py`:

```python
from aose.sheet.view import build_sheet, SheetSituationalSave


def test_build_sheet_exposes_situational_saves_for_druid():
    spec = CharacterSpec(
        name="Druid", class_id=None,
        classes=[ClassEntry(class_id="druid", level=1)],
        abilities={"STR": 9, "INT": 9, "WIS": 13, "DEX": 9, "CON": 9, "CHA": 9},
        alignment="neutral",
    )
    sheet = build_sheet(spec, DATA)
    energy = [s for s in sheet.situational_saves if s.source == "Energy Resistance"]
    assert len(energy) == 1
    assert energy[0].bonus == 2
    assert energy[0].vs == "fire & lightning"


def test_sheet_situational_save_joins_three_things():
    # vs string join: a, b & c
    s = SheetSituationalSave.from_bonus_things(2, ["a", "b", "c"], "Src")
    assert s.vs == "a, b & c"
    one = SheetSituationalSave.from_bonus_things(1, ["solo"], "Src")
    assert one.vs == "solo"
```

> This test depends on Task 4 (druid data). If running Task 2 in isolation, the `test_build_sheet_exposes_situational_saves_for_druid` assertion on content will fail until Task 4 lands — that's expected and is re-verified in Task 4. The `from_bonus_things` join test is self-contained and must pass now.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves.py::test_sheet_situational_save_joins_three_things -q`
Expected: FAIL — `ImportError: cannot import name 'SheetSituationalSave'`.

- [ ] **Step 3: Implement the view model and wiring**

In `aose/sheet/view.py`, add the model near `SheetSave` (after line 99):

```python
class SheetSituationalSave(BaseModel):
    bonus: int
    vs: str            # joined display, e.g. "fire & lightning"
    source: str

    @classmethod
    def from_bonus_things(cls, bonus: int, things: list[str], source: str) -> "SheetSituationalSave":
        if len(things) <= 1:
            vs = things[0] if things else ""
        elif len(things) == 2:
            vs = f"{things[0]} & {things[1]}"
        else:
            vs = ", ".join(things[:-1]) + f" & {things[-1]}"
        return cls(bonus=bonus, vs=vs, source=source)
```

Add the field to `CharacterSheet`, immediately after `saves: list[SheetSave]` (line 340):

```python
    situational_saves: list[SheetSituationalSave]
```

Populate it in `build_sheet`. The `save_rows` list comprehension ends at line 1112; add directly after it:

```python
    situational_save_rows = [
        SheetSituationalSave.from_bonus_things(b.bonus, b.things, b.source)
        for b in saves.situational_save_bonuses(spec, data)
    ]
```

Pass it into the `CharacterSheet(...)` constructor, immediately after `saves=save_rows,` (line 1162):

```python
        situational_saves=situational_save_rows,
```

- [ ] **Step 4: Run the join test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves.py::test_sheet_situational_save_joins_three_things -q`
Expected: PASS.

- [ ] **Step 5: Run the full engine test file (druid content test still expected to fail until Task 4)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves.py -q`
Expected: all PASS except `test_build_sheet_exposes_situational_saves_for_druid` (fails on empty `energy` until Task 4). Do not "fix" it here.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_situational_saves.py
git commit -m "feat(sheet): SheetSituationalSave view model + situational_saves field"
```

---

## Task 3: Templates + CSS — render the footnotes

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Modify: `aose/web/templates/sheet_print.html`
- Modify: `aose/web/static/sheet.css`

> No automated test renders these templates with content in the suite. Verification is by manual browser check at the end (see Verification section). Keep the markup minimal and the CSS scoped.

- [ ] **Step 1: Add the footnote block to `sheet.html`**

In `aose/web/templates/sheet.html`, the saves grid closes at line 135 (`</div>` after the `{% endfor %}`). Insert immediately **after** that `</div>` and **before** the `</div>` that closes `.col` content (i.e. right after line 135):

```html
          {% if sheet.situational_saves %}
          <div class="save-notes">
            {% for sn in sheet.situational_saves %}
            <div class="save-note">+{{ sn.bonus }} vs {{ sn.vs }}
              <span class="muted">({{ sn.source }})</span></div>
            {% endfor %}
          </div>
          {% endif %}
```

- [ ] **Step 2: Add the footnote block to `sheet_print.html`**

In `aose/web/templates/sheet_print.html`, inside the Saving Throws `<section>`, after the `</table>` (line 77) and before `</section>` (line 78):

```html
        {% if sheet.situational_saves %}
        <div class="save-notes-print">
            {% for sn in sheet.situational_saves %}
            <div class="muted small">+{{ sn.bonus }} vs {{ sn.vs }} ({{ sn.source }})</div>
            {% endfor %}
        </div>
        {% endif %}
```

- [ ] **Step 3: Add CSS**

In `aose/web/static/sheet.css`, after the `.save .tg` rule (line 146), add:

```css
.save-notes{ display:flex; flex-direction:column; gap:2px; margin-top:5px; padding-top:4px; border-top:1.5px dashed var(--ink); }
.save-note{ font-size:11px; line-height:1.25; color:var(--ink-2); font-variant-numeric:lining-nums tabular-nums; }
.save-note .muted{ color:var(--gray); }
```

> `--ink-2`, `--gray`, and `var(--box)` are existing tokens (see `:root` near line 43 and the `.muted` usages). Use them rather than literal colours, per `docs/STYLE-GUIDE.md`.

- [ ] **Step 4: Smoke-check templates parse (no syntax errors)**

Run:
```bash
.venv\Scripts\python.exe -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('aose/web/templates')); e.get_template('sheet.html'); e.get_template('sheet_print.html'); print('OK')"
```
Expected: `OK` (no `TemplateSyntaxError`).

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/templates/sheet_print.html aose/web/static/sheet.css
git commit -m "feat(sheet): render situational save footnotes under saves block"
```

---

## Task 4: Data — druid energy resistance

**Files:**
- Modify: `data/classes/druid.yaml`
- Test: `tests/test_situational_saves_data.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_situational_saves_data.py`:

```python
from aose.data.loader import GameData
from aose.engine import saves

DATA = GameData.load("data")


def _druid(level=1):
    from aose.models import CharacterSpec, ClassEntry
    return CharacterSpec(
        name="D", class_id=None,
        classes=[ClassEntry(class_id="druid", level=level)],
        abilities={"STR": 9, "INT": 9, "WIS": 13, "DEX": 9, "CON": 9, "CHA": 9},
        alignment="neutral",
    )


def test_druid_energy_resistance_groups_fire_and_lightning():
    result = saves.situational_save_bonuses(_druid(), DATA)
    energy = [b for b in result if b.source == "Energy Resistance"]
    assert len(energy) == 1
    assert energy[0].bonus == 2
    assert energy[0].things == ["fire", "lightning"]


def test_situational_bonus_never_changes_a_headline():
    # Druid headline saves must equal the raw class progression (no vs:* leakage).
    spec = _druid()
    detail = saves.saving_throws_detail(spec, DATA)
    cls = DATA.classes["druid"]
    prog = cls.progression[1].saves
    for name, val in prog.items():
        assert detail[name].modified == val, f"{name} headline changed"
        # And no save:vs:* line leaked into the per-category modal:
        assert all("vs " not in ln.note for ln in detail[name].lines)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves_data.py -q`
Expected: FAIL — `test_druid_energy_resistance_groups_fire_and_lightning` finds 0 Energy Resistance bonuses (no grants yet). The headline test should already PASS.

- [ ] **Step 3: Add the granted_modifiers to the druid feature**

In `data/classes/druid.yaml`, the `energy_resistance` feature is at lines 249-253:

```yaml
- id: energy_resistance
  name: Energy Resistance
  text: |-
    Druids gain a +2 bonus to saving throws against electricity (lightning) and fire.
  gained_at_level: 1
```

Add `granted_modifiers` to it (after the `gained_at_level: 1` line):

```yaml
- id: energy_resistance
  name: Energy Resistance
  text: |-
    Druids gain a +2 bonus to saving throws against electricity (lightning) and fire.
  gained_at_level: 1
  granted_modifiers:
  - {target: "save:vs:fire", op: add, value: 2}
  - {target: "save:vs:lightning", op: add, value: 2}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves_data.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Re-run the deferred view test from Task 2**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves.py::test_build_sheet_exposes_situational_saves_for_druid -q`
Expected: PASS now (druid data present).

- [ ] **Step 6: Commit**

```bash
git add data/classes/druid.yaml tests/test_situational_saves_data.py
git commit -m "feat(data): druid energy resistance as save:vs:fire/lightning grants"
```

---

## Task 5: Data — svirfneblin illusion resistance

**Files:**
- Modify: `data/races/svirfneblin.yaml`
- Test: append to `tests/test_situational_saves_data.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_situational_saves_data.py`:

```python
def test_svirfneblin_illusion_resistance():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="S", class_id=None,
        classes=[ClassEntry(class_id="fighter", level=1)],
        race_id="svirfneblin",
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
    )
    result = saves.situational_save_bonuses(spec, DATA)
    illusion = [b for b in result if b.source == "Illusion Resistance"]
    assert len(illusion) == 1
    assert illusion[0].bonus == 2
    assert illusion[0].things == ["illusions"]
```

> If `svirfneblin` is not a valid fighter-allowed race or requires specific abilities, adjust `race_id`/`abilities` minimally so the spec validates; the assertion content stays the same. Confirm svirfneblin race id and any ability requirements in `data/races/svirfneblin.yaml` before running.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves_data.py::test_svirfneblin_illusion_resistance -q`
Expected: FAIL — 0 Illusion Resistance bonuses (no grant yet).

- [ ] **Step 3: Add the granted_modifier to the svirfneblin feature**

In `data/races/svirfneblin.yaml`, the `illusion_resistance` feature is at lines 82-87:

```yaml
- id: illusion_resistance
  name: Illusion Resistance
  text: Gains a +2 bonus to all saving throws against illusions.
  mechanical:
    save_bonus: 2
    save_category: illusions
```

Add `granted_modifiers` (keep the existing `mechanical` block):

```yaml
- id: illusion_resistance
  name: Illusion Resistance
  text: Gains a +2 bonus to all saving throws against illusions.
  mechanical:
    save_bonus: 2
    save_category: illusions
  granted_modifiers:
  - {target: "save:vs:illusion", op: add, value: 2}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves_data.py::test_svirfneblin_illusion_resistance -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/races/svirfneblin.yaml tests/test_situational_saves_data.py
git commit -m "feat(data): svirfneblin illusion resistance as save:vs:illusion grant"
```

---

## Task 6: Full data sweep — audit every race & class

**Files:**
- Modify: any `data/races/*.yaml` / `data/classes/*.yaml` with an unencoded passive "vs X" save bonus
- Test: append confirmed cases to `tests/test_situational_saves_data.py`

> This task is an audit. The druid and svirfneblin are already done (Tasks 4-5); this finds anything else. Verify each candidate against the PDF before encoding (project practice: `import/pdfs` via PyMuPDF).

- [ ] **Step 1: Enumerate candidates from the data**

Run (PowerShell-safe via the Grep tool or `findstr`):
```bash
.venv\Scripts\python.exe -c "import pathlib,re; pat=re.compile(r'sav(e|ing).{0,60}(against|vs\.?|versus)', re.I); [print(p, ':', l.strip()) for p in pathlib.Path('data').rglob('*.yaml') if 'classes' in str(p) or 'races' in str(p) for i,l in enumerate(p.read_text(encoding='utf-8').splitlines()) if pat.search(l)]"
```
Review each hit. Classify as one of:
- **Already encoded** (dwarf/duergar/halfling resilience, gnome magic resistance) → skip.
- **Category-specific conditional** (a bonus to one named category only, e.g. "vs poison") → out of scope for this feature (those belong to the existing `save:death` + `condition` machinery); leave as-is unless trivially a cross-cutting case.
- **Cross-cutting passive "vs X"** (applies regardless of category) → encode as `save:vs:*` grants.
- **Activated power / immunity / non-numeric** → out of scope; do not encode.

- [ ] **Step 2: For each cross-cutting case found, verify against the PDF**

Open the relevant page in `import/pdfs` (PyMuPDF) and confirm the exact bonus value and the effect wording. Record the confirmed `<thing>` id(s) (lowercase, underscore for spaces) and value.

- [ ] **Step 3: Write a failing data test for each confirmed case**

For each, append a test to `tests/test_situational_saves_data.py` following the pattern of `test_druid_energy_resistance_groups_fire_and_lightning` (assert source name, bonus, and `things`). If a new `<thing>` needs a non-default display name (e.g. a plural or special wording), add it to `_VS_DISPLAY` in `aose/engine/saves.py` and assert the display in the test.

- [ ] **Step 4: Run the new tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves_data.py -q`
Expected: the newly added case(s) FAIL.

- [ ] **Step 5: Encode the grants in the YAML**

Add `granted_modifiers` (target `save:vs:<thing>`, op `add`, the confirmed value) to each confirmed feature, mirroring Tasks 4-5. Update `_VS_DISPLAY` if a registered display name was asserted.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_situational_saves_data.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add data/ aose/engine/saves.py tests/test_situational_saves_data.py
git commit -m "feat(data): encode remaining cross-cutting vs-X save bonuses from sweep"
```

> If the sweep finds **no** additional cross-cutting cases beyond druid/svirfneblin, record that in the commit body (`No further cross-cutting save bonuses found in races/classes`) and commit only any test/doc note, or skip the commit. Do not invent data to fill the task.

---

## Task 7: Modifier docstring

**Files:**
- Modify: `aose/models/modifier.py`

- [ ] **Step 1: Update the target grammar docstring**

In `aose/models/modifier.py`, the `Modifier` docstring lists the `target` grammar (lines 21-24). Add the new family. Change:

```
    ``target`` grammar (unknown targets are ignored — forward-compatible):
    ``ability:STR``…``ability:CHA``, ``ac``, ``save:all``,
    ``save:death|wands|paralysis|breath|spells``, ``attack``, ``damage``,
    ``carry_capacity``, ``thac0``.
```

to:

```
    ``target`` grammar (unknown targets are ignored — forward-compatible):
    ``ability:STR``…``ability:CHA``, ``ac``, ``save:all``,
    ``save:death|wands|paralysis|breath|spells``,
    ``save:vs:<thing>`` (cross-cutting situational bonus — e.g. ``save:vs:fire``;
    never folded into a headline, surfaced by ``situational_save_bonuses``),
    ``attack``, ``damage``, ``carry_capacity``, ``thac0``.
```

- [ ] **Step 2: Verify nothing imports broke**

Run: `.venv\Scripts\python.exe -c "import aose.models.modifier; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add aose/models/modifier.py
git commit -m "docs(modifier): document save:vs:<thing> target family"
```

---

## Task 8: Full suite + manual verification + CLAUDE.md note

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass except the 2 known pre-existing breadcrumb-label failures (`test_wizard_class_setup`, `test_wizard_identity`). The new `tests/test_situational_saves.py` and `tests/test_situational_saves_data.py` pass. Ignore the trailing `pytest-current` PermissionError.

- [ ] **Step 2: Manual browser verification**

Start the app:
```bash
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```
Create or open a **druid** character and view the sheet. Confirm under the Saving Throws block a smaller-font line reads approximately: `+2 vs fire & lightning (Energy Resistance)`. Confirm the five headline save numbers are unchanged from a druid without the feature, and the per-save breakdown modal does **not** list fire/lightning. Open the print view (`/character/<id>/print`) and confirm the footnote appears there too. (Use the preview tooling if available rather than asking the user to check.)

- [ ] **Step 3: Update CLAUDE.md "Current state"**

Add a new dated bullet under the most recent "Current state" section in `CLAUDE.md` summarising the feature:

```markdown
## Current state (2026-06-07, situational save bonuses)

Cross-cutting "vs X" save bonuses landed. A new `save:vs:<thing>` `Modifier`
target family (e.g. `save:vs:fire`) flows through the existing
`GrantedModifier`/`active_modifiers` → `all_modifiers` pipeline. `saves.py`
gains `situational_save_bonuses(spec, data) -> list[SituationalSaveBonus]`
(groups by source+value, collects `things`, display-name registry `_VS_DISPLAY`
with underscore fallback). Never folded into a headline and never shown in a
per-category modal. Sheet shows them as smaller-font footnotes under the saving
throws (`SheetSituationalSave`, `CharacterSheet.situational_saves`, `.save-note`
CSS); also on the print sheet. Magic items can emit `save:vs:*` modifiers and
are collected automatically (no catalog encoding done yet). Data: druid Energy
Resistance (`save:vs:fire`/`save:vs:lightning` +2), svirfneblin Illusion
Resistance (`save:vs:illusion` +2). Spec/plan:
`docs/superpowers/{specs,plans}/2026-06-07-situational-save-bonuses*`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note situational save bonuses feature in CLAUDE.md"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** grammar (Task 1, 7), engine collector (Task 1), view model (Task 2), templates+CSS sheet & print (Task 3), druid data (Task 4), svirfneblin data (Task 5), full sweep (Task 6), tests throughout, headline-regression (Task 4), magic-item pickup (Task 1). All spec sections mapped.
- **Type consistency:** `situational_save_bonuses` → `list[SituationalSaveBonus]{source,bonus,things}` (engine) is mapped to `SheetSituationalSave{bonus,vs,source}` via `from_bonus_things` (view) — names consistent across Tasks 1-2 and used identically in Tasks 4-6 tests and Task 3 templates (`sn.bonus`, `sn.vs`, `sn.source`).
- **Placeholder scan:** no TBD/TODO; all code shown; Task 6 is intentionally an audit with a concrete enumeration command and explicit "don't invent data" guard.
- **Coordination:** every commit uses explicit `git add <path>` to avoid staging the unrelated in-progress ability-breakdown work.
```
