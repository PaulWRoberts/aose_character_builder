# Conditional Attack Modifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface character-wide conditional attack-roll modifiers (light sensitivity −2 in bright light; knight +1 mounted) as a breakdown reachable from the Attack stat, with a ★ indicator — without changing any existing to-hit number.

**Architecture:** Mirror the existing conditional-AC feature. Add a pure engine breakdown function (`attack_modifiers_detail`) over the `attack` add-modifiers already collected by `all_modifiers`; the per-weapon math in `_atk_dmg` already carries-but-excludes unrecognised conditions, so no combat number changes. Expose the breakdown on `CharacterSheet`, merge it into the existing `modal-matrix` (retitled "Attack") with the to-hit matrix gated to descending AC, and add a print footnote. Data: race-file `attack -2 condition:bright_light` grants (race-as-class is covered via `race_locked`) plus a knight `attack +1 condition:mounted` grant.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run Python via `.venv\Scripts\python.exe` (the venv is not auto-activated).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/engine/attacks.py` | attack profiles + (new) attack-modifier breakdown | Add `AttackModLine`, `AttackBreakdown`, `_ATTACK_CONDITION_NOTES`, `_attack_condition_note`, `_HEADLINE_ATTACK_CONDITIONS`, `attack_modifiers_detail` |
| `aose/sheet/view.py` | sheet view-model assembly | Add `SheetAttackLine`; `CharacterSheet.attack_lines` + `.attack_has_conditional`; wire in `build_sheet` |
| `aose/web/templates/sheet.html` | live sheet | ★ on Attack box; merge breakdown + gated matrix into `modal-matrix` |
| `aose/web/templates/sheet_print.html` | print sheet | conditional-attack footnotes |
| `data/races/{drow,duergar,svirfneblin}.yaml` | racial features | add `attack -2 condition:bright_light` grant |
| `data/classes/knight.yaml` | knight features | add `attack +1 condition:mounted` grant |
| `tests/test_conditional_attack.py` | engine + view tests | new |
| `tests/test_conditional_attack_data.py` | data tests | new |
| `CLAUDE.md` | agent notes | add current-state section |

---

## Task 1: Engine — attack-modifier breakdown

**Files:**
- Modify: `aose/engine/attacks.py`
- Test: `tests/test_conditional_attack.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_conditional_attack.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import attacks as atk
from aose.engine.attacks import (
    AttackBreakdown,
    AttackModLine,
    attack_modifiers_detail,
    attack_profiles,
)
from aose.models import CharacterSpec, ClassEntry, Modifier

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id="human", class_id="fighter", level=1, **kw):
    defaults = dict(
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id=race_id,
        alignment="neutral",
    )
    defaults.update(kw)
    return CharacterSpec(
        name="T", classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[8])],
        **defaults,
    )


def test_conditional_attack_mod_not_in_weapon_to_hit(monkeypatch):
    # A bright_light -2 attack modifier must NOT change any weapon's to-hit.
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=-2,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    spec = _spec()
    profiles = attack_profiles(spec, DATA)
    unarmed = next(p for p in profiles if p.unarmed)
    # STR 10 -> +0, base fighter THAC0 19 -> attack bonus 0, no conditional applied.
    assert unarmed.to_hit_ascending == 0
    assert unarmed.to_hit_thac0 == 19


def test_breakdown_lists_conditional_line(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=-2,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert isinstance(bd, AttackBreakdown)
    assert bd.thac0 == 19
    assert bd.attack_bonus == 0
    cond = [ln for ln in bd.lines if ln.conditional]
    assert len(cond) == 1
    assert cond[0].source == "Light Sensitivity"
    assert cond[0].bonus == -2
    assert cond[0].note == "in bright light"
    assert bd.has_conditional is True


def test_breakdown_mounted_note(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=1,
                         condition="mounted", source="Mounted Combat")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].bonus == 1
    assert cond[0].note == "while mounted"


def test_unconditional_global_attack_mod_is_non_conditional_line(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=1, source="Ring of Aiming")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert bd.has_conditional is False
    assert any(ln.source == "Ring of Aiming" and ln.bonus == 1
               and not ln.conditional for ln in bd.lines)


def test_ranged_melee_mods_excluded_from_breakdown(monkeypatch):
    # ranged/melee are weapon-type-automatic; they belong on per-weapon rows,
    # not the character-level breakdown, and must not light up has_conditional.
    def fake_all(spec, data):
        return [
            Modifier(target="attack", op="add", value=1, condition="ranged",
                     source="Missile Attack Bonus"),
            Modifier(target="attack", op="add", value=1, condition="melee",
                     source="Melee Thing"),
        ]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert bd.lines == []
    assert bd.has_conditional is False


def test_unknown_condition_falls_back_to_underscore_replace(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="attack", op="add", value=2,
                         condition="prone_target", source="Homebrew")]
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].note == "prone target"


def test_no_attack_mods_empty_breakdown(monkeypatch):
    def fake_all(spec, data):
        return []
    monkeypatch.setattr(atk, "all_modifiers", fake_all)
    bd = attack_modifiers_detail(_spec(), DATA)
    assert bd.lines == []
    assert bd.has_conditional is False
    assert bd.thac0 == 19
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_attack.py -q`
Expected: FAIL with `ImportError: cannot import name 'AttackBreakdown'` (or `attack_modifiers_detail`).

- [ ] **Step 3: Implement the engine additions**

In `aose/engine/attacks.py`, after the `ConditionalAttack` class (before `AttackProfile`), add the condition registry and helper:

```python
_ATTACK_CONDITION_NOTES = {
    "bright_light": "in bright light",
    "mounted": "while mounted",
}
"""Display note for a conditional ``attack`` modifier. Unregistered conditions
fall back to ``condition.replace("_", " ")`` — mirrors ``_AC_CONDITION_NOTES``
and ``_VS_DISPLAY``."""

# Conditions the per-weapon to-hit math (`_atk_dmg`) evaluates itself: they are
# weapon-type-automatic and excluded from the character-level breakdown.
_HEADLINE_ATTACK_CONDITIONS = frozenset({"ranged", "melee"})


def _attack_condition_note(condition: str) -> str:
    return _ATTACK_CONDITION_NOTES.get(condition, condition.replace("_", " "))


class AttackModLine(BaseModel):
    source: str          # feature/item name, "—" fallback
    bonus: int           # +N bonus (better) / −N penalty (worse), signed
    conditional: bool    # True for situational modifiers
    note: str            # condition note ("" when unconditional)


class AttackBreakdown(BaseModel):
    thac0: int           # base class headline (unchanged by attack mods)
    attack_bonus: int    # 19 − thac0
    lines: list[AttackModLine]   # unconditional first, then conditional
    has_conditional: bool
```

At the end of the module, add the breakdown function:

```python
def attack_modifiers_detail(spec: CharacterSpec, data: GameData) -> AttackBreakdown:
    """Character-wide ``attack`` add-modifier breakdown for the Attack modal.

    The headline ``thac0``/``attack_bonus`` are the base class numbers (they
    apply only ``thac0``-target mods, never ``attack`` mods), so a global
    ``attack +1`` shows here as a line that explains a weapon's higher to-hit.
    Unconditional mods are listed first; situational mods (condition outside
    ``ranged``/``melee``) follow, flagged. ``ranged``/``melee`` mods are excluded
    — they are applied per-weapon by ``_atk_dmg`` and already shown on each row.
    """
    base_thac0 = thac0(spec, data)
    atk_adds = [m for m in all_modifiers(spec, data)
                if m.target == "attack" and m.op == "add"]
    lines: list[AttackModLine] = [
        AttackModLine(source=m.source or "—", bonus=m.value,
                      conditional=False, note="")
        for m in atk_adds if m.condition is None
    ]
    lines += [
        AttackModLine(source=m.source or "—", bonus=m.value, conditional=True,
                      note=_attack_condition_note(m.condition))
        for m in atk_adds
        if m.condition is not None and m.condition not in _HEADLINE_ATTACK_CONDITIONS
    ]
    return AttackBreakdown(
        thac0=base_thac0,
        attack_bonus=19 - base_thac0,
        lines=lines,
        has_conditional=any(ln.conditional for ln in lines),
    )
```

Note: `thac0`, `all_modifiers`, `CharacterSpec`, `GameData`, and `BaseModel` are
already imported at the top of `attacks.py` — no new imports needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_attack.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/attacks.py tests/test_conditional_attack.py
git commit -m "feat(engine): attack_modifiers_detail breakdown for conditional attack mods"
```

---

## Task 2: View — expose breakdown on CharacterSheet

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_conditional_attack.py` (append)

- [ ] **Step 1: Write the failing view tests**

Append to `tests/test_conditional_attack.py`:

```python
# ── view-model tests ──────────────────────────────────────────────────────────

from aose.sheet.view import build_sheet, SheetAttackLine


def test_build_sheet_flags_conditional_attack_for_drow():
    sheet = build_sheet(_spec(race_id="drow"), DATA)
    assert sheet.attack_has_conditional is True
    cond = [ln for ln in sheet.attack_lines if ln.conditional]
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               and ln.note == "in bright light" for ln in cond)
    assert all(isinstance(ln, SheetAttackLine) for ln in sheet.attack_lines)


def test_build_sheet_flags_conditional_attack_for_knight():
    sheet = build_sheet(_spec(class_id="knight"), DATA)
    cond = [ln for ln in sheet.attack_lines if ln.conditional]
    assert any(ln.source == "Mounted Combat" and ln.bonus == 1
               and ln.note == "while mounted" for ln in cond)


def test_build_sheet_no_conditional_attack_for_human_fighter():
    sheet = build_sheet(_spec(race_id="human", class_id="fighter"), DATA)
    assert sheet.attack_has_conditional is False
    assert all(not ln.conditional for ln in sheet.attack_lines)
```

(These will fully pass only after Task 3 lands the data; the human-fighter test
passes now, the drow/knight tests pass after Task 3. That is acceptable for
subagent-driven execution — run the human test here, defer the data-dependent
two to Task 3's verification. To keep this task green on its own, run only the
human assertion in Step 4 below.)

- [ ] **Step 2: Run the human test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_attack.py::test_build_sheet_no_conditional_attack_for_human_fighter -q`
Expected: FAIL with `AttributeError`/`ImportError` (`SheetAttackLine` / `attack_has_conditional` not defined).

- [ ] **Step 3: Implement the view additions**

In `aose/sheet/view.py`, add the line model next to `SheetACLine` (after its
definition, around line 122):

```python
class SheetAttackLine(BaseModel):
    source: str
    bonus: int
    conditional: bool
    note: str
```

Add two fields to `CharacterSheet`, immediately after `attack_bonus: int`
(around line 362):

```python
    attack_lines: list[SheetAttackLine]
    attack_has_conditional: bool
```

Import the engine helper: change the existing import near the top
```python
from aose.engine.attacks import AttackProfile, attack_profiles
```
to
```python
from aose.engine.attacks import AttackProfile, attack_modifiers_detail, attack_profiles
```

In `build_sheet`, just after `attacks = attack_profiles(spec, data)`
(around line 1172), build the rows:

```python
    attack_breakdown = attack_modifiers_detail(spec, data)
    attack_line_rows = [
        SheetAttackLine(source=ln.source, bonus=ln.bonus,
                        conditional=ln.conditional, note=ln.note)
        for ln in attack_breakdown.lines
    ]
```

In the `CharacterSheet(...)` constructor, add the two arguments right after
`attack_bonus=attack_bonus.attack_bonus(spec, data),` (around line 1198):

```python
        attack_lines=attack_line_rows,
        attack_has_conditional=attack_breakdown.has_conditional,
```

- [ ] **Step 4: Run the human test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_attack.py::test_build_sheet_no_conditional_attack_for_human_fighter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_conditional_attack.py
git commit -m "feat(sheet): expose conditional attack breakdown on CharacterSheet"
```

---

## Task 3: Data — light sensitivity (race files) + knight mounted

**Files:**
- Modify: `data/races/drow.yaml`, `data/races/duergar.yaml`, `data/races/svirfneblin.yaml`
- Modify: `data/classes/knight.yaml`
- Test: `tests/test_conditional_attack_data.py` (create)

- [ ] **Step 1: Write the failing data tests**

Create `tests/test_conditional_attack_data.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.attacks import attack_modifiers_detail
from aose.models import CharacterSpec, ClassEntry

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id, class_id="fighter", level=1):
    return CharacterSpec(
        name="T", race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[8])],
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
    )


def _cond(race_id, class_id="fighter", level=1):
    bd = attack_modifiers_detail(_spec(race_id, class_id, level), DATA)
    return [ln for ln in bd.lines if ln.conditional]


def test_drow_light_sensitivity_attack_penalty():
    lines = _cond("drow")
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               and ln.note == "in bright light" for ln in lines)


def test_duergar_light_sensitivity_attack_penalty():
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               for ln in _cond("duergar"))


def test_svirfneblin_light_sensitivity_attack_penalty():
    assert any(ln.source == "Light Sensitivity" and ln.bonus == -2
               for ln in _cond("svirfneblin"))


def test_light_sensitivity_applies_exactly_once_separate_and_race_as_class():
    # Separate mode: race_id=drow, class_id=fighter.
    sep = [ln for ln in _cond("drow", "fighter")
           if ln.source == "Light Sensitivity" and ln.bonus == -2]
    assert len(sep) == 1
    # Race-as-class: race_id=drow, class_id=drow (class light_sensitivity carries
    # NO grant, so the race-file grant must not be doubled).
    rac = [ln for ln in _cond("drow", "drow")
           if ln.source == "Light Sensitivity" and ln.bonus == -2]
    assert len(rac) == 1


def test_knight_mounted_attack_bonus():
    lines = _cond("human", "knight", level=1)
    assert any(ln.source == "Mounted Combat" and ln.bonus == 1
               and ln.note == "while mounted" for ln in lines)


def test_human_fighter_has_no_conditional_attack():
    assert _cond("human", "fighter") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_attack_data.py -q`
Expected: FAIL — drow/duergar/svirfneblin/knight assertions fail (no grants yet);
the human test passes.

- [ ] **Step 3a: Add the attack penalty to the three race files**

In `data/races/drow.yaml`, the `light_sensitivity` feature currently ends:

```yaml
  granted_modifiers:
  - {target: "ac", op: add, value: -1, condition: bright_light}
```

Change to:

```yaml
  granted_modifiers:
  - {target: "ac", op: add, value: -1, condition: bright_light}
  - {target: "attack", op: add, value: -2, condition: bright_light}
```

Make the **identical** change in `data/races/duergar.yaml` and
`data/races/svirfneblin.yaml` (each has the same existing `ac -1` grant line
under its `light_sensitivity` feature).

**Do not modify** `data/classes/{drow,duergar,svirfneblin}.yaml` — their
`light_sensitivity` features must stay grant-free to avoid double-application
(race-as-class characters get `race_id` = the race via `race_locked`).

- [ ] **Step 3b: Add the mounted bonus to the knight**

In `data/classes/knight.yaml`, the `mounted_combat` feature is:

```yaml
- id: mounted_combat
  name: Mounted Combat
  text: |-
    Knights gain a +1 bonus to attack rolls when mounted.
  gained_at_level: 1
```

Add a `granted_modifiers` block to it:

```yaml
- id: mounted_combat
  name: Mounted Combat
  text: |-
    Knights gain a +1 bonus to attack rolls when mounted.
  gained_at_level: 1
  granted_modifiers:
  - {target: "attack", op: add, value: 1, condition: mounted}
```

- [ ] **Step 4: Run the data tests + the deferred view tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_attack_data.py tests/test_conditional_attack.py -q`
Expected: PASS (all data tests + the drow/knight view tests from Task 2 now green).

- [ ] **Step 5: Commit**

```bash
git add data/races/drow.yaml data/races/duergar.yaml data/races/svirfneblin.yaml data/classes/knight.yaml tests/test_conditional_attack_data.py
git commit -m "feat(data): conditional attack modifiers — light sensitivity & knight mounted"
```

---

## Task 4: Templates — ★ indicator, merged Attack modal, print footnote

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Modify: `aose/web/templates/sheet_print.html`

- [ ] **Step 1: Add the ★ indicator to the Attack box**

In `aose/web/templates/sheet.html`, the Attack box is (around line 86):

```html
            <div class="field col-field editable" data-modal="modal-matrix" title="Show to-hit matrix">
              <span class="tab">{{ 'ATTACK' if sheet.use_ascending else 'THAC0' }}</span>
              <span class="box" style="font-weight:600">{% if sheet.use_ascending %}{{ "%+d"|format(sheet.attack_bonus) }}{% else %}{{ sheet.thac0 }}{% endif %}</span>
            </div>
```

Replace with (adds the conditional mark, matching the AC box at line 82):

```html
            <div class="field col-field editable" data-modal="modal-matrix" title="Show attack breakdown">
              <span class="tab">{{ 'ATTACK' if sheet.use_ascending else 'THAC0' }}{% if sheet.attack_has_conditional %}<span class="cond-mark" title="Has a conditional modifier — tap for details">★</span>{% endif %}</span>
              <span class="box" style="font-weight:600">{% if sheet.use_ascending %}{{ "%+d"|format(sheet.attack_bonus) }}{% else %}{{ sheet.thac0 }}{% endif %}</span>
            </div>
```

- [ ] **Step 2: Replace the `modal-matrix` modal with the merged Attack modal**

In `aose/web/templates/sheet.html`, the existing modal (around lines 864–878):

```html
{# MODAL: to-hit matrix #}
<div class="overlay modal" id="modal-matrix" role="dialog" aria-label="To-hit matrix">
  <div class="ov-head"><h3>To-Hit Matrix — {% if sheet.use_ascending %}Attack Bonus {{ "%+d"|format(sheet.attack_bonus) }}{% else %}THAC0 {{ sheet.thac0 }}{% endif %}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body matrix">
    <p class="hint">Roll needed to hit each descending Armour Class (before per-weapon bonuses).</p>
    <div class="cells">
      {% for ac in range(9, -1, -1) %}
      <div>
        <div class="ac">{% if loop.first %}AC 9{% else %}{{ ac }}{% endif %}</div>
        <div class="hit">{{ sheet.thac0 - ac }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>
```

Replace with:

```html
{# MODAL: attack breakdown + to-hit matrix #}
<div class="overlay modal" id="modal-matrix" role="dialog" aria-label="Attack">
  <div class="ov-head"><h3>Attack — {% if sheet.use_ascending %}Attack Bonus {{ "%+d"|format(sheet.attack_bonus) }}{% else %}THAC0 {{ sheet.thac0 }}{% endif %}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body matrix" style="font-size:14px">
    <p style="margin:0 0 6px">
      {% if sheet.use_ascending %}Attack Bonus <strong>{{ "%+d"|format(sheet.attack_bonus) }}</strong>{% else %}THAC0 <strong>{{ sheet.thac0 }}</strong>{% endif %}
    </p>
    {% if sheet.attack_lines %}
    <ul style="list-style:none;margin:0 0 10px;padding:0">
      {% for ln in sheet.attack_lines %}
      <li style="margin:2px 0">
        <strong>{{ ln.source }}:</strong>
        {% if ln.bonus >= 0 %}+{{ ln.bonus }} bonus{% else %}{{ ln.bonus }} penalty{% endif %}
        {% if ln.conditional %}<span class="muted"> — {{ ln.note }}</span>{% endif %}
      </li>
      {% endfor %}
    </ul>
    {% endif %}
    {% if not sheet.use_ascending %}
    <p class="hint">Roll needed to hit each descending Armour Class (before per-weapon bonuses).</p>
    <div class="cells">
      {% for ac in range(9, -1, -1) %}
      <div>
        <div class="ac">{% if loop.first %}AC 9{% else %}{{ ac }}{% endif %}</div>
        <div class="hit">{{ sheet.thac0 - ac }}</div>
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>
</div>
```

(Keeping the `matrix` class on `ov-body` preserves the existing `.matrix .cells`
/ `.matrix .ac` / `.matrix .hit` CSS.)

- [ ] **Step 3: Add the print-sheet footnote**

In `aose/web/templates/sheet_print.html`, the THAC0/Attack stat row ends at
(around lines 65–73):

```html
        <div class="stat-row">
        {% if sheet.use_ascending %}
            <span>Attack Bonus</span>
            <span class="stat-big">{{ "%+d"|format(sheet.attack_bonus) }}</span>
        {% else %}
            <span>THAC0</span>
            <span class="stat-big">{{ sheet.thac0 }}</span>
        {% endif %}
        </div>
    </section>
```

Insert the footnote block between the closing `</div>` of the stat-row and
`</section>`:

```html
        <div class="stat-row">
        {% if sheet.use_ascending %}
            <span>Attack Bonus</span>
            <span class="stat-big">{{ "%+d"|format(sheet.attack_bonus) }}</span>
        {% else %}
            <span>THAC0</span>
            <span class="stat-big">{{ sheet.thac0 }}</span>
        {% endif %}
        </div>
        {% if sheet.attack_has_conditional %}
        <div class="save-notes-print">
            {% for ln in sheet.attack_lines if ln.conditional %}
            <div class="muted small">{% if ln.bonus >= 0 %}+{{ ln.bonus }}{% else %}{{ ln.bonus }}{% endif %} to-hit {{ ln.note }} ({{ ln.source }})</div>
            {% endfor %}
        </div>
        {% endif %}
    </section>
```

- [ ] **Step 4: Run the full test suite (no template regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS — all prior tests plus the new ones. (Ignore the trailing
`PermissionError` on `pytest-current` — known Windows-tempdir quirk.)

- [ ] **Step 5: Verify in the browser**

Start the app:
`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

Then via the preview tools:
- Create/open a **drow** character's sheet. Confirm the THAC0/ATTACK box shows a
  `★`. Click it: the modal titled "Attack" lists `Light Sensitivity: −2 penalty —
  in bright light` and (under descending AC) the to-hit matrix below.
- Confirm a **human fighter** sheet shows **no** `★`, and clicking the box still
  opens the matrix (descending) / breakdown-only (ascending).
- Toggle the ruleset to **ascending AC** and confirm the matrix is hidden in the
  modal while the breakdown lines remain.

Capture a screenshot of the drow Attack modal as proof.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/templates/sheet_print.html
git commit -m "feat(sheet): conditional attack breakdown modal + indicator + print footnote"
```

---

## Task 5: Docs — update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a current-state section**

In `CLAUDE.md`, immediately after the `## Current state (2026-06-07, conditional
AC modifiers)` section, insert:

```markdown
## Current state (2026-06-08, conditional attack modifiers)

Character-wide conditional attack-roll modifiers landed, mirroring conditional AC.
An `attack add` `Modifier` carrying a condition the per-weapon math can't evaluate
(anything other than `ranged`/`melee`) is excluded from every weapon's to-hit (it
already was — `_atk_dmg` carries-but-excludes unknown conditions) and surfaced as
a breakdown line. `attacks.py` gains `attack_modifiers_detail(spec, data) ->
AttackBreakdown` (base `thac0`/`attack_bonus` + `AttackModLine`s: unconditional
global mods first, then situational; `ranged`/`melee` excluded), an
`_ATTACK_CONDITION_NOTES` registry (`bright_light`/`mounted`, underscore fallback),
and the `AttackModLine`/`AttackBreakdown` models. The sheet exposes `attack_lines`
+ `attack_has_conditional`; the Attack box shows a `★` and opens the retitled
`modal-matrix` ("Attack") — breakdown lines on top, the to-hit matrix below, gated
to descending AC (no THAC0 under ascending). Print sheet shows conditional attack
lines as footnotes. Per-weapon conditional bonuses (Sword +1, Giant Slayer) are
unchanged (`Weapon.conditional_bonus` → `ConditionalAttack`, per-weapon row). Data
encoded: Light Sensitivity (drow/duergar/svirfneblin, `attack -2
condition:bright_light`, race files only — race-as-class is covered via
`race_locked`, so the class files stay grant-free to avoid double-application) and
Knight Mounted Combat (`attack +1 condition:mounted`). Action-gated bonuses
(acrobat tumbling, assassin assassination) are intentionally not modelled. Spec/
plan: `docs/superpowers/{specs,plans}/2026-06-08-conditional-attack-modifiers*`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note conditional attack modifiers feature in CLAUDE.md"
```

---

## Self-Review Notes

- **Spec coverage:** engine breakdown (Task 1) ✓; view exposure (Task 2) ✓;
  merged modal + matrix gating + ★ + print footnote (Task 4) ✓; race-file-only
  light-sensitivity data + knight mounted (Task 3) ✓; no-double-application
  invariant pinned (Task 3 `test_light_sensitivity_applies_exactly_once...`) ✓;
  no-behaviour-change pinned (Task 1 `test_conditional_attack_mod_not_in_weapon_to_hit`) ✓.
- **Out-of-scope confirmed:** no task touches `Weapon.conditional_bonus`,
  `_atk_dmg`, or the class light_sensitivity features; no `damage`-target
  collection.
- **Type consistency:** `AttackModLine`/`AttackBreakdown` (engine) ↔
  `SheetAttackLine` (view) field names match (`source`, `bonus`, `conditional`,
  `note`); `attack_modifiers_detail` signature consistent across tasks; template
  references (`attack_lines`, `attack_has_conditional`) match the `CharacterSheet`
  fields added in Task 2.
```
