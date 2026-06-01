# Wizard Slice 5 — Class Setup (P6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the `human_racial_abilities` optional rule (with its dependency gating and Human's conditional +1 CHA / +1 CON), implement Human **Blessed** HP (roll twice, keep the better), lock HP to a single roll, and merge the HP / Proficiencies / Spells wizard steps into one **Class Setup** step.

**Architecture:** The flag is a new `RuleSet` field, registered in the existing settings/rules matrix with a nested JS+server dependency on Advanced + `lift_demihuman_restrictions`. Human's optional ability modifiers become a typed `Race.optional_ability_modifiers` field, folded into `_post_racial_abilities` only when the flag is on — so the +1 CON flows into HP via effective CON with no extra wiring. Blessed/locked HP is pure roll-time logic in a new `aose/engine/dice.py` helper consumed by the unchanged `POST /hp/roll` action. The three steps collapse into one `class_setup` step rendered by a new unified page; **the existing POST action routes (`/hp/roll`, `/proficiencies`, `/spells`, `/hp`) are kept** (per the route-scope decision), so only the GET page and a handful of redirect-target test assertions move.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `aose/models/ruleset.py` | `RuleSet` flags | Modify — add `human_racial_abilities` |
| `aose/models/race.py` | `Race` model | Modify — add `optional_ability_modifiers` |
| `data/races/human.yaml` | Human seed data | Modify — add top-level `optional_ability_modifiers` |
| `aose/web/settings_routes.py` | Rules registry + form parsing | Modify — label, IMPLEMENTED, group entry, server enforcement |
| `aose/web/templates/_ruleset_fields.html` | Shared rules form + JS | Modify — nested-dependency markup + JS |
| `aose/engine/ability_mods.py` | Pure ability math | Modify — `apply_racial_modifiers` gains `include_optional` |
| `aose/engine/dice.py` | Dice rolls | Modify — add `roll_first_level_hp` (Blessed/locked) |
| `aose/web/wizard.py` | Wizard routes + draft helpers | Modify — flag clear, optional mods, Blessed/lock roll, step consolidation, unified GET page |
| `aose/web/templates/wizard/class_setup.html` | Unified Class Setup page | Create |
| `aose/web/templates/wizard/hp.html`, `proficiencies.html`, `spells.html` | Old step partials | Delete (folded into `class_setup.html`) |
| `tests/test_wizard_class_setup.py` | All Slice-5 tests | Create |
| `tests/test_secondary_skills.py`, `test_wizard.py`, `test_weapon_proficiency.py`, `test_spell_routes.py`, `test_multiclassing.py`, `test_settings.py`, `test_wizard_race.py` | Pre-existing wizard tests | Modify — point GET page + redirect-target assertions at `class_setup` |

Notes for the implementer (read once):

- The wizard stores draft state as a plain `dict` persisted via `save_draft`; a step is "complete" when its marker key is present. HP markers are `hp_roll` (single-class) / `hp_rolls` (multi-class); `_has_hp(draft)` checks both.
- Ability values are the plain strings `"STR" "INT" "WIS" "DEX" "CON" "CHA"` (`aose/models/ability.py`, a `str` Enum). `Race.ability_modifiers` / `optional_ability_modifiers` keys are `Ability` enum members.
- The **route-scope decision** for this slice: keep the existing POST action paths. The only URL that changes is the GET page — it moves from three separate pages to one at `/wizard/{id}/class_setup`. Old GET handlers (`get_hp`, `get_proficiencies`, `get_spells`) are deleted.
- Run the **whole** suite after Tasks 5 and 6 — it is the regression guard for the consolidation. Ignore the trailing `pytest-current` PermissionError (known Windows quirk).
- All Slice-5 NEW tests live in `tests/test_wizard_class_setup.py`. The shared client/driver harness (Step 1 of Task 1) is reused by every later task in that file.

---

## Task 1: `human_racial_abilities` flag — model, registry, server enforcement, JS gating

**Files:**
- Modify: `aose/models/ruleset.py:20`
- Modify: `aose/web/settings_routes.py` (RULE_LABELS, IMPLEMENTED_RULES, RULE_GROUPS, `parse_ruleset_from_form`)
- Modify: `aose/web/templates/_ruleset_fields.html`
- Test: `tests/test_wizard_class_setup.py` (create)

- [ ] **Step 1: Write the failing tests + shared harness**

Create `tests/test_wizard_class_setup.py`:

```python
"""Slice 5 (Class Setup / P6): human_racial_abilities flag, Human optional
ability modifiers, Blessed + locked HP, and the consolidated class_setup step."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft, save_settings
from aose.data.loader import GameData
from aose.models import Ability, RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def _make_client(tmp_path, ruleset=None):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, ruleset or RuleSet())
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        examples_dir=examples_dir,
        settings_path=settings_path,
    )
    client = TestClient(app, follow_redirects=False)
    client._drafts_dir = drafts_dir
    client._characters_dir = characters_dir
    client._settings_path = settings_path
    return client


def _new_draft(client):
    r = client.get("/wizard/new")
    return r.headers["location"].split("/")[2]


def _set_abilities(client, draft_id, abilities):
    draft = load_draft(draft_id, client._drafts_dir)
    draft["abilities"] = abilities
    save_draft(draft_id, draft, client._drafts_dir)


# Strong scores so any race/class passes requirements.
_GOOD = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 13, "CHA": 13}


def _rules_form(**overrides):
    """POST body for /rules matching RuleSet() defaults (Advanced)."""
    data = {"encumbrance": "basic", "creation_method": "advanced"}
    for k, v in overrides.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    return data


# ── Task 1: flag gating ────────────────────────────────────────────────────

def test_flag_defaults_off():
    assert RuleSet().human_racial_abilities is False


def test_flag_forced_off_without_lift(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    # Advanced but lift NOT checked -> flag must be forced off.
    client.post(f"/wizard/{draft_id}/rules",
                data=_rules_form(human_racial_abilities="on"))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["human_racial_abilities"] is False


def test_flag_forced_off_in_basic(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        creation_method="basic", lift_demihuman_restrictions="on",
        human_racial_abilities="on"))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["human_racial_abilities"] is False


def test_flag_enabled_with_advanced_and_lift(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        lift_demihuman_restrictions="on", human_racial_abilities="on"))
    rs = load_draft(draft_id, client._drafts_dir)["ruleset"]
    assert rs["human_racial_abilities"] is True


def test_flag_renders_in_advanced_options(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    r = client.get(f"/wizard/{draft_id}/rules")
    assert 'name="human_racial_abilities"' in r.text


def test_flag_no_pending_badge(tmp_path):
    client = _make_client(tmp_path)
    r = client.get("/settings")
    assert "rule-pending" not in r.text
    assert ">pending<" not in r.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q`
Expected: FAIL — `RuleSet` has no `human_racial_abilities` (pydantic `extra="forbid"` rejects the form field / attribute missing).

- [ ] **Step 3: Add the model field**

In `aose/models/ruleset.py`, after line 20 (`advanced_spell_books: bool = False`), add:

```python
    human_racial_abilities: bool = False
```

- [ ] **Step 4: Register the rule in `settings_routes.py`**

In `RULE_LABELS` (after the `advanced_spell_books` entry, ~line 25), add:

```python
    "human_racial_abilities": "Human Racial Abilities",
```

In `IMPLEMENTED_RULES` (the set, ~line 31), add:

```python
    "human_racial_abilities",
```

In `RULE_GROUPS`, extend the **Advanced Options** group (the first tuple, ~lines 46-52) so its field list becomes:

```python
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
```

- [ ] **Step 5: Enforce the dependency in `parse_ruleset_from_form`**

In `parse_ruleset_from_form` (`settings_routes.py`), immediately after the
existing `if not advanced:` block that forces the Advanced-only rules off
(~line 136, before `choices = {}`), add:

```python
    # human_racial_abilities is gated behind BOTH Advanced and lifted demihuman
    # restrictions — force it off unless both hold (mirrors the rules-page JS).
    if not (bools["separate_race_class"] and bools.get("lift_demihuman_restrictions")):
        bools["human_racial_abilities"] = False
```

- [ ] **Step 6: Add the nested-dependency markup + JS**

In `aose/web/templates/_ruleset_fields.html`, the Advanced Options checkboxes
render generically from `rule_groups`. Tag the dependent input by extending the
checkbox `<input>` (line 32-33) with a data attribute keyed on the field name:

```html
        <input type="checkbox" name="{{ field }}"
               {% if field == "human_racial_abilities" %}data-requires-lift{% endif %}
               {% if ruleset[field] %}checked{% endif %}>
```

Then extend the `<script>` block's `sync()` so the dependent input is also
disabled whenever `lift_demihuman_restrictions` is unchecked. Replace the whole
`<script>` (lines 67-83) with:

```html
<script>
(function () {
    var radios = document.querySelectorAll('[data-creation-method]');
    var advancedInputs = document.querySelectorAll('[data-advanced-only] input');
    var lift = document.querySelector('input[name="lift_demihuman_restrictions"]');
    var dependent = document.querySelector('[data-requires-lift]');
    function sync() {
        var basic = document.querySelector('[data-creation-method][value="basic"]');
        var disable = !!(basic && basic.checked);
        advancedInputs.forEach(function (el) {
            el.disabled = disable;
            var row = el.closest('.rule');
            if (row) { row.classList.toggle('rule-disabled', disable); }
        });
        // Nested dependency: human_racial_abilities also needs lift checked.
        if (dependent) {
            var liftOff = disable || !(lift && lift.checked);
            dependent.disabled = liftOff;
            if (liftOff) { dependent.checked = false; }
            var drow = dependent.closest('.rule');
            if (drow) { drow.classList.toggle('rule-disabled', liftOff); }
        }
    }
    radios.forEach(function (r) { r.addEventListener('change', sync); });
    if (lift) { lift.addEventListener('change', sync); }
    sync();
})();
</script>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k flag`
Expected: PASS (6 tests).

- [ ] **Step 8: Run the settings/rules regression guards**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py tests/test_wizard_rules_step.py -q`
Expected: PASS (the "no pending badge" invariant and rules-matrix tests still hold).

- [ ] **Step 9: Commit**

```bash
git add aose/models/ruleset.py aose/web/settings_routes.py aose/web/templates/_ruleset_fields.html tests/test_wizard_class_setup.py
git commit -m "feat(rules): human_racial_abilities flag with Advanced+lift gating"
```

---

## Task 2: Human optional ability modifiers (+1 CHA / +1 CON)

**Files:**
- Modify: `aose/models/race.py:25`
- Modify: `data/races/human.yaml`
- Modify: `aose/engine/ability_mods.py:34-45` (`apply_racial_modifiers`)
- Modify: `aose/web/wizard.py:412-423` (`_post_racial_abilities`)
- Test: `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wizard_class_setup.py`:

```python
# ── Task 2: Human optional ability modifiers ───────────────────────────────

from aose.engine.ability_mods import apply_racial_modifiers


def test_human_optional_modifiers_loaded(data):
    human = data.races["human"]
    assert human.optional_ability_modifiers == {Ability.CHA: 1, Ability.CON: 1}


def test_non_human_has_no_optional_modifiers(data):
    for rid in ("elf", "dwarf", "halfling"):
        assert data.races[rid].optional_ability_modifiers == {}


def test_apply_includes_optional_when_requested(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10}
    human = data.races["human"]
    without = apply_racial_modifiers(base, human, include_optional=False)
    with_opt = apply_racial_modifiers(base, human, include_optional=True)
    assert without["CON"] == 10 and without["CHA"] == 10
    assert with_opt["CON"] == 11 and with_opt["CHA"] == 11


def test_optional_modifiers_clamp_at_18(data):
    base = {"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 18, "CHA": 18}
    human = data.races["human"]
    result = apply_racial_modifiers(base, human, include_optional=True)
    assert result["CON"] == 18 and result["CHA"] == 18


def test_post_racial_applies_optional_only_when_flag_on(tmp_path):
    # Flag on -> human CON/CHA +1 reflected in the adjust step's post-racial row.
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        lift_demihuman_restrictions="on", human_racial_abilities="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "H"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    r = client.get(f"/wizard/{draft_id}/adjust")
    # CON row shows 14 (13 + 1); CHA row shows 14.
    assert "14" in r.text


def test_post_racial_no_optional_when_flag_off(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())  # flag off
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "H"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    from aose.web.wizard import _post_racial_abilities, _ruleset_of
    draft = load_draft(draft_id, client._drafts_dir)
    pr = _post_racial_abilities(draft, GameData.load(DATA_DIR))
    assert pr["CON"] == 13 and pr["CHA"] == 13
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "optional or post_racial or apply_includes or clamp"`
Expected: FAIL — `Race` has no `optional_ability_modifiers`, and `apply_racial_modifiers` has no `include_optional` keyword.

- [ ] **Step 3: Add the `Race` field**

In `aose/models/race.py`, after line 25 (`ability_modifiers: dict[Ability, int] = Field(default_factory=dict)`), add:

```python
    # Applied on top of ability_modifiers only when the human_racial_abilities
    # optional rule is active (today: Human +1 CHA / +1 CON). Empty otherwise.
    optional_ability_modifiers: dict[Ability, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Populate `human.yaml`**

In `data/races/human.yaml`, add a top-level key (place it right after the
`allowed_classes: []` line, before `features:`). The descriptive feature text
stays in place for the sheet:

```yaml
optional_ability_modifiers:
  CHA: 1
  CON: 1
```

- [ ] **Step 5: Extend `apply_racial_modifiers`**

Replace `apply_racial_modifiers` in `aose/engine/ability_mods.py` (lines 34-45) with:

```python
def apply_racial_modifiers(base: dict[str, int], race, *,
                           include_optional: bool = False) -> dict[str, int]:
    """Return ``base`` with ``race.ability_modifiers`` applied (and, when
    ``include_optional`` is set, ``race.optional_ability_modifiers`` on top),
    each score clamped to ``[3, 18]``.

    The input dict is not mutated. Callers decide whether to apply (Advanced
    only) and whether the optional human_racial_abilities rule is active; this
    helper does not consult the ruleset.
    """
    result = dict(base)
    deltas: dict = dict(race.ability_modifiers)
    if include_optional:
        for ability, delta in race.optional_ability_modifiers.items():
            key = ability.value if hasattr(ability, "value") else ability
            deltas[key] = deltas.get(key, 0) + delta
    for ability, delta in deltas.items():
        key = ability.value if hasattr(ability, "value") else ability
        result[key] = max(3, min(18, result.get(key, 0) + delta))
    return result
```

(Note: merging into `deltas` first lets a base modifier and an optional modifier
on the same ability sum before the single clamp.)

- [ ] **Step 6: Apply optional mods in `_post_racial_abilities`**

In `aose/web/wizard.py`, replace `_post_racial_abilities` (lines 412-423) with:

```python
def _post_racial_abilities(draft: dict[str, Any], data) -> dict[str, int]:
    """Rolled base plus racial modifiers (Advanced only, once a race is chosen).

    In Basic / race-as-class mode, or before a race is picked, this is the
    rolled base unchanged. When the human_racial_abilities rule is on, the
    race's optional modifiers (Human +1 CHA / +1 CON) are folded in too.
    Modifiers are clamped to [3, 18]. This is the input and baseline for the
    ability-adjustment step and the class requirement check.
    """
    base = draft["abilities"]
    rs = _ruleset_of(draft)
    if not rs.separate_race_class or "race_id" not in draft:
        return dict(base)
    return apply_racial_modifiers(
        base, data.races[draft["race_id"]],
        include_optional=rs.human_racial_abilities,
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "optional or post_racial or apply_includes or clamp"`
Expected: PASS (6 tests).

- [ ] **Step 8: Run the wider regression (race + adjust + sheet)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_race.py tests/test_wizard_ability_adjust.py -q`
Expected: PASS — `apply_racial_modifiers` keeps its default behaviour (the new
keyword defaults to `False`), so the race step's `ability_changes` display and
all existing call sites are unchanged.

- [ ] **Step 9: Commit**

```bash
git add aose/models/race.py data/races/human.yaml aose/engine/ability_mods.py aose/web/wizard.py tests/test_wizard_class_setup.py
git commit -m "feat(race): human optional ability modifiers gated on the flag"
```

---

## Task 3: Blessed + locked HP roll engine helper

A pure helper so Blessed (roll two complete sets, keep the higher-summing one;
ties keep set A) and the existing reroll-1s-2s rule are testable with a seeded
RNG. It generalises single- and multi-class (single = a one-element list).

**Files:**
- Modify: `aose/engine/dice.py`
- Test: `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wizard_class_setup.py`:

```python
# ── Task 3: Blessed / locked HP roll helper ────────────────────────────────

import random
from aose.engine.dice import roll_first_level_hp


def test_non_blessed_single_rolls_once():
    rng = random.Random(1)
    result = roll_first_level_hp(["1d8"], blessed=False, min_die=1, rng=rng)
    # One class -> one roll; reproduce the exact sequence the helper consumed.
    expected = random.Random(1).randint(1, 8)
    assert result == [expected]


def test_blessed_single_keeps_higher():
    # With seed 1 the first two d8 rolls are A then B; helper keeps max(A, B).
    probe = random.Random(1)
    a = probe.randint(1, 8)
    b = probe.randint(1, 8)
    result = roll_first_level_hp(["1d8"], blessed=True, min_die=1,
                                 rng=random.Random(1))
    assert result == [max(a, b)]
    assert a != b  # seed 1 yields distinct rolls so the test is meaningful


def test_blessed_multi_keeps_better_complete_set():
    # Two classes (d8, d4). Blessed rolls set A (two dice) then set B (two dice)
    # and keeps the set with the larger SUM — never a cross-set cherry-pick.
    probe = random.Random(7)
    a = [probe.randint(1, 8), probe.randint(1, 4)]
    b = [probe.randint(1, 8), probe.randint(1, 4)]
    winner = a if sum(a) >= sum(b) else b
    result = roll_first_level_hp(["1d8", "1d4"], blessed=True, min_die=1,
                                 rng=random.Random(7))
    assert result == winner
    # Prove the cross-set cherry-pick (max per die) is NOT what we returned,
    # for a seed where it would differ.
    cherry = [max(a[0], b[0]), max(a[1], b[1])]
    if cherry != winner:
        assert result != cherry


def test_blessed_tie_keeps_first_set():
    # Construct a tie via a fake RNG yielding set A sum == set B sum.
    class _FakeRng:
        def __init__(self, seq):
            self.seq = list(seq)
        def randint(self, lo, hi):
            return self.seq.pop(0)
    # set A = [5, 2] (sum 7), set B = [3, 4] (sum 7) -> keep A.
    fake = _FakeRng([5, 2, 3, 4])
    result = roll_first_level_hp(["1d8", "1d4"], blessed=True, min_die=1, rng=fake)
    assert result == [5, 2]


def test_reroll_min_die_applies():
    # min_die=3 must never yield 1 or 2 on any die across many rolls.
    rng = random.Random(123)
    for _ in range(60):
        result = roll_first_level_hp(["1d8", "1d4"], blessed=True, min_die=3, rng=rng)
        assert all(v >= 3 for v in result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "blessed or non_blessed or reroll_min"`
Expected: FAIL with `ImportError: cannot import name 'roll_first_level_hp'`.

- [ ] **Step 3: Add the helper**

Append to `aose/engine/dice.py`:

```python
def roll_first_level_hp(
    hit_dice: list[str],
    *,
    blessed: bool,
    min_die: int = 1,
    rng: Optional[random.Random] = None,
) -> list[int]:
    """Roll first-level HP, one entry per class in ``hit_dice`` order.

    ``min_die`` is forwarded to :func:`roll_hp` (the reroll-1s-2s house rule
    passes 3). When ``blessed`` is set (Human Blessed racial ability) two
    *complete* sets are rolled — one die per class each — and the set with the
    larger sum of rolls is kept; ties keep the first set. There is no per-class
    cherry-picking across sets (N and CON are identical, so summed rolls is the
    correct comparison).
    """
    r = rng or random.Random()

    def one_set() -> list[int]:
        return [roll_hp(hd, r, min_die=min_die) for hd in hit_dice]

    if not blessed:
        return one_set()
    set_a = one_set()
    set_b = one_set()
    return set_a if sum(set_a) >= sum(set_b) else set_b
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "blessed or non_blessed or reroll_min"`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/dice.py tests/test_wizard_class_setup.py
git commit -m "feat(dice): roll_first_level_hp with Blessed two-set keep-better"
```

---

## Task 4: Wire Blessed + lock into `POST /hp/roll`

HP is rolled once and **locked**. The roll handler uses the new helper and
rejects a second roll. Effective CON (including Human's +1 when the flag is on)
already flows into displayed HP via `_creation_abilities` → `hp.py`; this task
adds a focused end-to-end CON test too.

**Files:**
- Modify: `aose/web/wizard.py` — `post_hp_roll` (lines 961-980); import the helper
- Modify: `tests/test_settings.py` — the statistical reroll test (locking makes a 40× re-roll loop invalid)
- Test: `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wizard_class_setup.py`:

```python
# ── Task 4: Blessed + locked HP via the roll route ─────────────────────────

def _drive_to_class_setup(client, draft_id, race="human", cls="fighter",
                          flag=False, abilities=None):
    rules = (_rules_form(lift_demihuman_restrictions="on", human_racial_abilities="on")
             if flag else _rules_form())
    client.post(f"/wizard/{draft_id}/rules", data=rules)
    _set_abilities(client, draft_id, dict(abilities or _GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "H"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": race})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": cls})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})


def test_hp_locked_after_first_roll(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)
    r1 = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r1.status_code == 303
    first = load_draft(draft_id, client._drafts_dir)["hp_roll"]
    # A second roll attempt is rejected; the stored roll is unchanged.
    r2 = client.post(f"/wizard/{draft_id}/hp/roll")
    assert r2.status_code == 400
    assert load_draft(draft_id, client._drafts_dir)["hp_roll"] == first


def test_blessed_human_hp_uses_two_sets(tmp_path, monkeypatch):
    # With the flag on for a human, the roll handler must call the helper with
    # blessed=True. Patch the helper to capture the kwarg.
    import aose.web.wizard as wiz
    captured = {}
    real = wiz.roll_first_level_hp

    def spy(hit_dice, *, blessed, min_die, rng=None):
        captured["blessed"] = blessed
        return real(hit_dice, blessed=blessed, min_die=min_die, rng=rng)

    monkeypatch.setattr(wiz, "roll_first_level_hp", spy)
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert captured["blessed"] is True


def test_non_human_not_blessed(tmp_path, monkeypatch):
    import aose.web.wizard as wiz
    captured = {}
    real = wiz.roll_first_level_hp

    def spy(hit_dice, *, blessed, min_die, rng=None):
        captured["blessed"] = blessed
        return real(hit_dice, blessed=blessed, min_die=min_die, rng=rng)

    monkeypatch.setattr(wiz, "roll_first_level_hp", spy)
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    # Elf with the flag on -> Blessed is human-only, so blessed must be False.
    _drive_to_class_setup(client, draft_id, race="elf", cls="fighter", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert captured["blessed"] is False


def test_human_plus_one_con_raises_hp(tmp_path):
    """Effective CON includes Human +1 when the flag is on: HP reflects it."""
    from aose.web.wizard import _draft_to_spec
    from aose.engine.hp import max_hp
    # CON 13 (mod +1). With the flag, effective CON 14 (still +1) — pick a value
    # that crosses a modifier boundary: CON 12 (mod 0) -> 13 (mod +1).
    abil = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 12, "CHA": 13}
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True, abilities=abil)
    client.post(f"/wizard/{draft_id}/hp/roll")
    data = GameData.load(DATA_DIR)
    spec = _draft_to_spec(load_draft(draft_id, client._drafts_dir), data)
    assert spec.abilities["CON"] == 13  # 12 + 1 optional
    # Roll is fixed in storage; HP = roll + effective CON mod (+1), min 1.
    roll = load_draft(draft_id, client._drafts_dir)["hp_roll"]
    assert max_hp(spec, data) == max(1, roll + 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "hp_locked or blessed_human or non_human_not or plus_one_con"`
Expected: FAIL — `post_hp_roll` neither locks nor uses `roll_first_level_hp`; `wiz.roll_first_level_hp` is not imported.

- [ ] **Step 3: Import the helper**

In `aose/web/wizard.py`, extend the dice import (line 26) to:

```python
from aose.engine.dice import roll_3d6_in_order, roll_first_level_hp, roll_hp
```

- [ ] **Step 4: Rewrite `post_hp_roll`**

Replace `post_hp_roll` (lines 961-980) with:

```python
@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if _has_hp(draft):
        # HP is rolled once and locked (like abilities and gold). To change it
        # the player cancels and starts over.
        raise HTTPException(400, "Hit points are already rolled and locked.")
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]

    blessed = (draft.get("race_id") == "human" and ruleset.human_racial_abilities)
    min_die = 3 if ruleset.reroll_1s_2s_hp_l1 else 1
    rolls = roll_first_level_hp(
        [c.hit_die for c in classes], blessed=blessed, min_die=min_die,
    )

    if len(ids) == 1:
        draft["hp_roll"] = rolls[0]
        draft.pop("hp_rolls", None)
    else:
        draft["hp_rolls"] = rolls
        draft.pop("hp_roll", None)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")
```

(The redirect target `class_setup` is introduced in Task 5/6; until then the
new Slice-5 tests assert draft state, not the redirect body, so they pass.)

- [ ] **Step 5: Fix the now-invalid statistical reroll test**

In `tests/test_settings.py`, `test_reroll_rule_never_yields_1_or_2_after_many_rolls`
loops `POST /hp/roll` 40× on one draft — locking makes every call after the
first a 400. Replace the loop body so each iteration uses a **fresh** draft:

Replace (around lines 235-241):

```python
    for _ in range(40):
        client.post(f"/wizard/{draft_id}/hp/roll")
        draft = load_draft(draft_id, tmp_path / "drafts")
        assert draft["hp_roll"] >= 3, f"got {draft['hp_roll']} which should have been rerolled"
```

with:

```python
    for _ in range(40):
        fresh = _start_draft_with(client, tmp_path / "drafts")
        client.post(f"/wizard/{fresh}/hp/roll")
        draft = load_draft(fresh, tmp_path / "drafts")
        assert draft["hp_roll"] >= 3, f"got {draft['hp_roll']} which should have been rerolled"
```

(`_start_draft_with` is the helper already used elsewhere in this file to build
a draft positioned at the HP step. If it isn't reusable as-is, inline the same
sequence it performs.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "hp_locked or blessed_human or non_human_not or plus_one_con"`
Expected: PASS (4 tests).

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q -k reroll`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py tests/test_wizard_class_setup.py tests/test_settings.py
git commit -m "feat(wizard): Blessed + locked first-level HP roll"
```

---

## Task 5: Consolidate the step list — `class_setup` plumbing + flag clears

Step/plumbing only. After this task the breadcrumb shows one **Class Setup**
step in place of HP / Proficiencies / Spells, completion is gated on all three
sections, and toggling the flag clears HP + adjustments. The unified GET page +
template land in Task 6.

**Files:**
- Modify: `aose/web/wizard.py` — `STEP_LABELS`, `_wizard_steps`, `_next_incomplete_step`, `_apply_rule_changes`
- Test: `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wizard_class_setup.py`:

```python
# ── Task 5: consolidated step plumbing ─────────────────────────────────────

def _breadcrumb(text):
    start = text.index("wizard-steps")
    return text[start:text.index("</ol>", start)]


def test_breadcrumb_shows_single_class_setup(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    bc = _breadcrumb(r.text)
    assert "Class Setup" in bc
    assert "Hit Points" not in bc
    assert "Proficiencies" not in bc
    # Exactly one occurrence of the Class Setup label in the breadcrumb.
    assert bc.count("Class Setup") == 1


def test_class_setup_incomplete_until_hp(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)
    # No HP yet -> equipment bounces back to class_setup.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/class_setup")
    client.post(f"/wizard/{draft_id}/hp/roll")
    # HP rolled, no prof/spells required for a plain human fighter -> equipment.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200


def test_class_setup_incomplete_until_proficiencies(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "H"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    client.post(f"/wizard/{draft_id}/hp/roll")
    # HP done but proficiencies still required -> equipment bounces back.
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 303 and r.headers["location"].endswith("/class_setup")
    client.post(f"/wizard/{draft_id}/proficiencies",
                data={"weapon": ["sword", "spear", "mace", "hand_axe"]})
    r = client.get(f"/wizard/{draft_id}/equipment")
    assert r.status_code == 200


def test_flag_toggle_clears_hp_and_adjustments(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id, race="human", flag=True)
    client.post(f"/wizard/{draft_id}/hp/roll")
    assert "hp_roll" in load_draft(draft_id, client._drafts_dir)
    # Turn the flag off — Blessed eligibility + post-racial scores changed.
    client.post(f"/wizard/{draft_id}/rules",
                data=_rules_form(lift_demihuman_restrictions="on"))  # flag now off
    draft = load_draft(draft_id, client._drafts_dir)
    assert "hp_roll" not in draft
    assert "ability_adjustments" not in draft
    assert draft.get("race_id") == "human"  # race survives
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "breadcrumb_shows or incomplete_until or flag_toggle_clears"`
Expected: FAIL — there is no `class_setup` step/label yet; `GET /class_setup` 404s; the breadcrumb still shows Hit Points/Proficiencies.

- [ ] **Step 3: Update `STEP_LABELS`**

In `STEP_LABELS` (lines 92-105), remove the `"proficiencies"`, `"hp"`, and
`"spells"` entries and add a single `class_setup` entry, so the dict becomes:

```python
STEP_LABELS = {
    "rules": "Rules",
    "abilities": "Abilities",
    "race": "Race",
    "class": "Class",
    "adjust": "Ability Adjustments",
    "alignment": "Alignment",
    "skill": "Secondary Skill",
    "class_setup": "Class Setup",
    "equipment": "Equipment",
    "review": "Review",
}
```

- [ ] **Step 4: Collapse the steps in `_wizard_steps`**

Replace the tail of `_wizard_steps` (lines 124-131) — from the
`if rs.weapon_proficiency:` line through `steps += ["equipment", "review"]` —
with:

```python
    if rs.secondary_skills:
        steps.append("skill")
    # HP, weapon proficiencies, and spells are consolidated into one always-on
    # Class Setup step; proficiencies/spells are sections within it.
    steps.append("class_setup")
    steps += ["equipment", "review"]
    return steps
```

- [ ] **Step 5: Gate the consolidated step in `_next_incomplete_step`**

In `_next_incomplete_step` (lines 201-229), replace the three separate checks
(the `weapon_proficiency` proficiencies check, the `_has_hp` check, and the
`spellcasting` spells check — lines 221-226) with a single block:

```python
    if not _class_setup_complete(draft):
        return "class_setup"
```

Then add this helper immediately above `_next_incomplete_step`:

```python
def _class_setup_complete(draft: dict[str, Any]) -> bool:
    """The consolidated Class Setup step is complete when HP is rolled AND
    weapon proficiencies are chosen (if the rule is on) AND starting spells are
    chosen (if any picked class casts at L1)."""
    rs = _ruleset_of(draft)
    if not _has_hp(draft):
        return False
    if rs.weapon_proficiency and "proficiencies" not in draft:
        return False
    if draft.get("spellcasting") and not draft.get("spells_done"):
        return False
    return True
```

- [ ] **Step 6: Clear HP + adjustments when the flag toggles**

In `_apply_rule_changes` (lines 326-364), add a new branch after the
`reroll_1s_2s_hp_l1` branch (after line 358) and before the
`weapon_proficiency` branch:

```python
    if new_rs.human_racial_abilities != old_rs.human_racial_abilities:
        # Blessed eligibility AND post-racial scores changed; clear the HP roll
        # and any ability adjustments computed off the old post-racial baseline.
        draft.pop("hp_roll", None)
        draft.pop("hp_rolls", None)
        draft.pop("ability_adjustments", None)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "breadcrumb_shows or incomplete_until or flag_toggle_clears"`
Expected: FAIL still on the two tests that GET `/class_setup` (no route yet) but PASS on `test_class_setup_incomplete_until_*` redirect assertions and `test_flag_toggle_clears_hp_and_adjustments`. The breadcrumb test stays red until Task 6 adds the page. **This is expected** — proceed to Task 6, which adds the route and re-runs these. Do **not** commit a half-green state on its own; combine the commit with Task 6.

(If you prefer a green checkpoint here, temporarily skip the two GET-page tests
with `@pytest.mark.skip(reason="page added in Task 6")` and remove the markers
in Task 6 Step 1.)

---

## Task 6: Unified Class Setup page — GET route, template, redirect targets, test migration

Adds the single page that renders HP → Proficiencies → Spells sections in order,
deletes the three old GET step handlers, points the section POST redirects and
the single Continue at the consolidated step, and migrates the pre-existing
tests that asserted the old GET URLs / redirect targets.

**Files:**
- Modify: `aose/web/wizard.py` — delete `get_hp`/`get_proficiencies`/`get_spells`; add `get_class_setup`; retarget `post_proficiencies` redirect; keep `post_spells` (→ next-incomplete) and `post_hp` (Continue → next-incomplete)
- Create: `aose/web/templates/wizard/class_setup.html`
- Delete: `aose/web/templates/wizard/hp.html`, `proficiencies.html`, `spells.html`
- Modify (test migration): `tests/test_secondary_skills.py`, `test_wizard.py`, `test_weapon_proficiency.py`, `test_multiclassing.py`, `test_spell_routes.py`, `test_settings.py`, `test_wizard_race.py`
- Test: `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the failing tests (page rendering + section visibility)**

If you added skip markers in Task 5, remove them now. Append to
`tests/test_wizard_class_setup.py`:

```python
# ── Task 6: unified page rendering ─────────────────────────────────────────

def test_page_shows_hp_section_only_for_plain_fighter(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)  # human fighter, no prof/spells
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    assert "Hit Points" in r.text or "Roll" in r.text
    assert "Weapon Proficiencies" not in r.text
    assert "Spells" not in r.text


def test_page_shows_proficiency_section_when_rule_on(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(weapon_proficiency="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "H"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "fighter"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Sword" in r.text  # weapon picker present


def test_page_shows_spell_section_for_caster(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form())
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "H"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Magic Missile" in r.text


def test_continue_advances_only_when_complete(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    _drive_to_class_setup(client, draft_id)  # human fighter
    # Continue (POST /hp) before HP rolled -> bounce back to class_setup.
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.status_code == 303 and r.headers["location"].endswith("/class_setup")
    client.post(f"/wizard/{draft_id}/hp/roll")
    r = client.post(f"/wizard/{draft_id}/hp")
    assert r.headers["location"].endswith("/equipment")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k "page_shows or continue_advances or breadcrumb_shows"`
Expected: FAIL — `GET /class_setup` 404s; `POST /hp` raises 400 when HP unrolled (current behaviour) instead of bouncing to `class_setup`.

- [ ] **Step 3: Delete the three old GET handlers**

In `aose/web/wizard.py`, delete the function bodies of `get_hp`
(lines 911-958), `get_proficiencies` (lines 849-864), and `get_spells`
(lines 1027-1035) along with their `@router.get(...)` decorators. **Keep**
`_proficiency_context`, `_caster_entries`, `_multiclass_total_hp`, and all the
POST handlers (`post_hp_roll`, `post_proficiencies`, `post_spells`, `post_hp`).

- [ ] **Step 4: Add `get_class_setup` and an HP-context helper**

In `aose/web/wizard.py`, add a small HP-rendering helper plus the unified GET
route. Place them where `get_hp` was (after `_multiclass_total_hp`):

```python
def _hp_context(draft: dict[str, Any], data) -> dict:
    """Per-class HP rolls + total for the Class Setup HP section. Rolls are
    None until the locked roll happens."""
    ruleset = _ruleset_of(draft)
    con_mod = ability_modifier(_creation_abilities(draft, data)["CON"])
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]
    is_multi = len(ids) > 1

    rolls_for_template: list[dict] = []
    total = None
    if is_multi:
        existing = draft.get("hp_rolls", [None] * len(ids))
        for cls, roll_val in zip(classes, existing):
            rolls_for_template.append({
                "class_name": cls.name, "hit_die": cls.hit_die, "roll": roll_val,
            })
        if existing and all(r is not None for r in existing):
            total = _multiclass_total_hp(existing, con_mod)
    else:
        rolls_for_template.append({
            "class_name": classes[0].name, "hit_die": classes[0].hit_die,
            "roll": draft.get("hp_roll"),
        })
        if "hp_roll" in draft:
            total = max(1, draft["hp_roll"] + con_mod)

    blessed = (draft.get("race_id") == "human" and ruleset.human_racial_abilities)
    return {
        "is_multi": is_multi,
        "hp_class_name": " / ".join(c.name for c in classes),
        "hit_die": classes[0].hit_die,
        "con_mod": con_mod,
        "rolls": rolls_for_template,
        "total_hp": total,
        "reroll_rule": ruleset.reroll_1s_2s_hp_l1,
        "blessed": blessed,
        "hp_done": (total is not None),
    }


@router.get("/{draft_id}/class_setup", response_class=HTMLResponse)
async def get_class_setup(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "class_setup", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "class_setup")
    ctx.update(_hp_context(draft, data))
    # Proficiency section (only when the rule is on).
    ctx["show_proficiencies"] = ruleset.weapon_proficiency
    if ruleset.weapon_proficiency:
        ctx.update(_proficiency_context(draft, data))
        ctx["proficiencies_done"] = "proficiencies" in draft
    else:
        ctx["proficiencies_done"] = True
    # Spell section (only when a picked class casts at L1).
    ctx["show_spells"] = bool(draft.get("spellcasting"))
    if draft.get("spellcasting"):
        ctx["caster_classes"] = _caster_entries(draft, data)
        ctx["spells_done"] = bool(draft.get("spells_done"))
    else:
        ctx["spells_done"] = True
    ctx["ready"] = _class_setup_complete(draft)
    return templates.TemplateResponse(request, "wizard.html", ctx)
```

- [ ] **Step 5: Retarget the section POST redirects**

The single **Continue** is `POST /hp`; the **section saves** are `POST /hp/roll`,
`POST /proficiencies`, `POST /spells`. Adjust their redirects so saving a
section returns to the page and Continue advances when complete:

1. `post_hp_roll` already redirects to `class_setup` (Task 4). ✓

2. `post_proficiencies` (last line, ~901): change

   ```python
       return _redirect(f"/wizard/{draft_id}/hp")
   ```
   to
   ```python
       return _redirect(f"/wizard/{draft_id}/class_setup")
   ```

3. `post_spells` (last line, ~1077): leave it returning
   `_redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")` — when the
   caster still owes HP/prof this lands back on `class_setup`; when everything
   is done it advances to `equipment` (preserves the divine-autocomplete test).

4. `post_hp` (the Continue handler, ~983-988): replace its body so it never
   400s and simply advances via the gate:

   ```python
   @router.post("/{draft_id}/hp")
   async def post_hp(request: Request, draft_id: str):
       """Single 'Continue' action for the Class Setup page. Advances only when
       every applicable section is complete; otherwise bounces back to the page
       via _next_incomplete_step."""
       draft = _load(request, draft_id)
       return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
   ```

- [ ] **Step 6: Create the unified template**

Create `aose/web/templates/wizard/class_setup.html` (folds the old three
partials; section forms post to the kept routes; one Continue posts `/hp`):

```html
<h2>Class Setup</h2>

{# ── Hit Points ─────────────────────────────────────────────────────────── #}
<section class="class-setup-section">
    <h3>Hit Points</h3>
    <p>
        {{ hp_class_name }} rolls
        {% if is_multi %}one hit die per class{% else %}<strong>{{ hit_die }}</strong>{% endif %}
        for level&nbsp;1 HP. CON modifier: <strong>{{ "%+d"|format(con_mod) }}</strong>.
    </p>
    {% if reroll_rule %}
    <p class="rule-active"><strong>Reroll 1s &amp; 2s at L1</strong> is active &mdash; any 1 or 2 on a hit die is rerolled.</p>
    {% endif %}
    {% if blessed %}
    <p class="rule-active"><strong>Blessed</strong> &mdash; rolled twice, kept the better result.</p>
    {% endif %}
    {% if is_multi %}
    <p class="muted small">Multi-class HP: <em>floor(average of class rolls)</em> + CON modifier (minimum&nbsp;1).</p>
    {% endif %}

    {% if rolls %}
    <div class="hp-display">
        {% for r in rolls %}
        <div class="stat-row">
            <span>{{ r.class_name }} ({{ r.hit_die }})</span>
            <span class="stat-big">{{ r.roll if r.roll is not none else '—' }}</span>
        </div>
        {% endfor %}
        {% if total_hp is not none %}
        <div class="stat-row" style="border-top: 1px solid #c8b89a; margin-top: 6px; padding-top: 6px;">
            <span><strong>Total HP</strong></span>
            <span class="stat-big">{{ total_hp }}</span>
        </div>
        {% endif %}
    </div>
    {% endif %}

    {% if not hp_done %}
    <form method="post" action="/wizard/{{ draft_id }}/hp/roll" class="inline-form">
        <button type="submit">Roll HP</button>
    </form>
    {% else %}
    <p class="muted small">Hit points are locked. To re-roll, cancel and start over.</p>
    {% endif %}
</section>

{# ── Weapon Proficiencies ───────────────────────────────────────────────── #}
{% if show_proficiencies %}
<section class="class-setup-section">
    <h3>Weapon Proficiencies</h3>
    <p>{{ class_name }} starts with <strong>{{ required }}</strong> weapon
       proficiency slot{{ "s" if required != 1 else "" }}.{% if allow_specialise %}
       A martial character may <strong>specialise</strong> in a weapon
       (costs 2 slots) for +1 to hit and +1 damage.{% endif %}</p>
    <form method="post" action="/wizard/{{ draft_id }}/proficiencies" class="step-form">
        <table class="prof-table" data-required="{{ required }}"
               data-specialise="{{ 1 if allow_specialise else 0 }}">
            <thead>
                <tr><th>Proficient</th><th>Weapon</th><th>Qualities</th>
                {% if allow_specialise %}<th>Specialise (2)</th>{% endif %}</tr>
            </thead>
            <tbody>
                {% for w in weapons %}
                <tr>
                    <td><input type="checkbox" name="weapon" value="{{ w.id }}"
                               class="prof-weapon" {% if w.selected %}checked{% endif %}></td>
                    <td>{{ w.name }}</td>
                    <td class="muted small">{{ w.qualities }}</td>
                    {% if allow_specialise %}
                    <td><input type="checkbox" name="specialise" value="{{ w.id }}"
                               class="prof-special" {% if w.specialised %}checked{% endif %}></td>
                    {% endif %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <p class="muted" id="prof-counter">Spend exactly {{ required }} slot{{ "s" if required != 1 else "" }}.</p>
        <button type="submit">{% if proficiencies_done %}Update proficiencies{% else %}Save proficiencies{% endif %}</button>
    </form>
    <script>
        (function () {
            const required = {{ required }};
            const table = document.querySelector('.prof-table');
            const counter = document.getElementById('prof-counter');
            function rowOf(el) { return el.closest('tr'); }
            function spent() {
                let n = 0;
                table.querySelectorAll('.prof-weapon:checked').forEach(() => n += 1);
                table.querySelectorAll('.prof-special:checked').forEach(() => n += 1);
                return n;
            }
            function refresh() {
                table.querySelectorAll('.prof-special:checked').forEach(s => {
                    const w = rowOf(s).querySelector('.prof-weapon');
                    if (w && !w.checked) { w.checked = true; }
                });
                const n = spent();
                counter.textContent = `Spent ${n} of ${required}.`;
                counter.className = (n === required) ? '' : 'muted';
            }
            table.addEventListener('change', refresh);
            refresh();
        })();
    </script>
</section>
{% endif %}

{# ── Spells ─────────────────────────────────────────────────────────────── #}
{% if show_spells %}
<section class="class-setup-section">
    <h3>Spells</h3>
    {% for c in caster_classes %}
    <div class="spell-class">
        <h4>{{ c.class_name }}</h4>
        {% if c.caster_type == "divine" %}
        <p>{{ c.class_name }} casters know <strong>every spell</strong> on their list
           that they are high enough level to cast. Nothing to choose here.</p>
        <ul>
            {% for s in c.candidates %}
            <li><strong>{{ s.name }}</strong> <span class="small muted">(L{{ s.level }})</span></li>
            {% endfor %}
        </ul>
        <form method="post" action="/wizard/{{ draft_id }}/spells" class="step-form">
            <input type="hidden" name="class_id" value="{{ c.class_id }}">
            <button type="submit">Confirm {{ c.class_name }} spells</button>
        </form>
        {% else %}
        <p>Choose <strong>{{ c.required }}</strong> starting spell(s) for your spell
           book{% if c.advanced %} (Advanced Spell Book rules: determined by Intelligence){% else %} (the spells you can memorise at this level){% endif %}.</p>
        <form method="post" action="/wizard/{{ draft_id }}/spells" class="step-form">
            <input type="hidden" name="class_id" value="{{ c.class_id }}">
            <div class="card-grid" data-required="{{ c.required }}">
                {% for s in c.candidates %}
                <label class="card {% if s.selected %}selected{% endif %}">
                    <input type="checkbox" name="spell_{{ c.class_id }}" value="{{ s.id }}"
                           class="spell-checkbox" {% if s.selected %}checked{% endif %}>
                    <div class="card-name">{{ s.name }}</div>
                    <div class="card-detail small">{{ s.description }}</div>
                </label>
                {% endfor %}
            </div>
            <p class="muted spell-counter">Pick exactly {{ c.required }}.</p>
            <button type="submit">Save {{ c.class_name }} spells</button>
        </form>
        {% endif %}
    </div>
    {% endfor %}
    <script>
        (function () {
            document.querySelectorAll('.card-grid[data-required]').forEach(function (grid) {
                const required = parseInt(grid.dataset.required, 10);
                const boxes = Array.from(grid.querySelectorAll('.spell-checkbox'));
                const form = grid.closest('form');
                const counter = form ? form.querySelector('.spell-counter') : null;
                const submit = form ? form.querySelector('button[type="submit"]') : null;
                function update() {
                    const checked = boxes.filter(b => b.checked).length;
                    boxes.forEach(function (b) {
                        b.disabled = !b.checked && checked >= required;
                        b.closest('.card').classList.toggle('selected', b.checked);
                    });
                    if (counter) { counter.textContent = 'Picked ' + checked + ' of ' + required + '.'; }
                    if (submit) { submit.disabled = checked !== required; }
                }
                boxes.forEach(b => b.addEventListener('change', update));
                update();
            });
        })();
    </script>
</section>
{% endif %}

{# ── Continue ───────────────────────────────────────────────────────────── #}
<form method="post" action="/wizard/{{ draft_id }}/hp" class="step-form">
    <button type="submit" class="primary" {% if not ready %}disabled{% endif %}>Next: Equipment &rarr;</button>
</form>
```

- [ ] **Step 7: Delete the old partials**

```bash
git rm aose/web/templates/wizard/hp.html aose/web/templates/wizard/proficiencies.html aose/web/templates/wizard/spells.html
```

- [ ] **Step 8: Migrate the pre-existing test references**

These are the only call sites that named the old GET pages or asserted a
redirect target that is now `class_setup`. Apply each exact replacement:

`tests/test_secondary_skills.py` (two assertions):
- `assert r.headers["location"] == f"/wizard/{draft_id}/hp"` → `... == f"/wizard/{draft_id}/class_setup"` (the assertion after `POST /alignment`, ~line 114)
- `assert r.headers["location"] == f"/wizard/{draft_id}/hp"` → `... == f"/wizard/{draft_id}/class_setup"` (the assertion after `POST /skill`, ~line 180)

`tests/test_wizard.py` (~line 89):
- `assert r.headers["location"] == f"/wizard/{draft_id}/hp"` → `... == f"/wizard/{draft_id}/class_setup"`

`tests/test_weapon_proficiency.py`:
- GET `f"/wizard/{draft_id}/proficiencies"` → `f"/wizard/{draft_id}/class_setup"` (the two picker-render tests, ~lines 206, 215)
- `assert r.headers["location"].endswith("/hp")` → `.endswith("/class_setup")` (~line 227, after `POST /proficiencies`)

`tests/test_multiclassing.py`:
- GET `f"/wizard/{draft_id}/hp"` → `f"/wizard/{draft_id}/class_setup"` (~line 228)
- GET `f"/wizard/{draft_id}/proficiencies"` → `f"/wizard/{draft_id}/class_setup"` (~line 298)

`tests/test_spell_routes.py`:
- GET `f"/wizard/{draft_id}/spells"` → `f"/wizard/{draft_id}/class_setup"` (~lines 119, 134)

`tests/test_settings.py`:
- GET `f"/wizard/{draft_id}/hp"` → `f"/wizard/{draft_id}/class_setup"` (three reroll/baseline tests, ~lines 231, 250, 260)

`tests/test_wizard_race.py`:
- GET `f"/wizard/{draft_id}/hp"` → `f"/wizard/{draft_id}/class_setup"` (~line 229)

After editing, confirm none remain:

Run: `.venv\Scripts\python.exe -m pytest --collect-only -q >NUL` then
Grep check (PowerShell): `Select-String -Path tests\*.py -Pattern "/wizard/\{draft_id\}/(hp|proficiencies|spells)\b" | Where-Object { $_.Line -match '\.get\(|location' }`
Expected: no matches for `.get(... /hp|/proficiencies|/spells)` or `location ... /hp` (the POST *action* calls to `/hp/roll`, `/proficiencies`, `/spells`, and the Continue `/hp` remain and are correct).

- [ ] **Step 9: Run the Slice-5 file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q`
Expected: PASS (entire Slice-5 file).

- [ ] **Step 10: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: full suite PASS. (Ignore the trailing `pytest-current` PermissionError.)
If a test fails on a missing `/hp`/`/proficiencies`/`/spells` GET, it was a
reference missed in Step 8 — grep and fix per the same rule (GET page → `class_setup`).

- [ ] **Step 11: Commit**

```bash
git add aose/web/wizard.py aose/web/templates/wizard/class_setup.html tests/
git rm aose/web/templates/wizard/hp.html aose/web/templates/wizard/proficiencies.html aose/web/templates/wizard/spells.html
git commit -m "feat(wizard): consolidate HP/proficiencies/spells into Class Setup step"
```

---

## Task 7: End-to-end smoke — full creation flow through the consolidated step

A single end-to-end test proving the consolidated step works in a real
multi-section flow (caster + proficiencies + Blessed human), exercising the page
and finalize. No new production code.

**Files:**
- Test: `tests/test_wizard_class_setup.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_wizard_class_setup.py`:

```python
# ── Task 7: end-to-end through Class Setup ─────────────────────────────────

def test_full_flow_caster_with_proficiencies_and_blessed(tmp_path):
    import json
    client = _make_client(tmp_path)
    draft_id = _new_draft(client)
    client.post(f"/wizard/{draft_id}/rules", data=_rules_form(
        weapon_proficiency="on", lift_demihuman_restrictions="on",
        human_racial_abilities="on"))
    _set_abilities(client, draft_id, dict(_GOOD))
    client.post(f"/wizard/{draft_id}/abilities", data={"name": "Gandalf"})
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "magic_user"})
    client.post(f"/wizard/{draft_id}/adjust", data={})
    client.post(f"/wizard/{draft_id}/alignment", data={"alignment": "law"})

    # All three sections on one page.
    page = client.get(f"/wizard/{draft_id}/class_setup")
    assert "Hit Points" in page.text
    assert "Dagger" in page.text          # magic-user proficiency picker
    assert "Magic Missile" in page.text   # arcane spell section

    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/proficiencies", data={"weapon": ["dagger"]})
    client.post(f"/wizard/{draft_id}/spells",
                data={"class_id": "magic_user", "spell_magic_user": ["magic_user_magic_missile"]})

    # Continue now advances to equipment.
    cont = client.post(f"/wizard/{draft_id}/hp")
    assert cont.headers["location"].endswith("/equipment")

    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["CON"] == 14  # 13 + 1 optional CON
    assert saved["weapon_proficiencies"] == ["dagger"]
    assert saved["classes"][0]["spellbook"] == ["magic_user_magic_missile"]
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_class_setup.py -q -k full_flow`
Expected: PASS.

- [ ] **Step 3: Run the full suite one final time**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: full suite PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wizard_class_setup.py
git commit -m "test(wizard): end-to-end Class Setup flow (caster + prof + Blessed)"
```

---

## Self-Review

**Spec coverage (§ by §):**
- §1 flag with nested dependency gating, server enforcement, RULE_LABELS / IMPLEMENTED_RULES / RULE_GROUPS, no pending badge → Task 1. ✓
- §2 `Race.optional_ability_modifiers`, human data, folded into `_post_racial_abilities` only when flag on, clamp at 18, +1 CON auto-flows to HP / +1 CHA to sheet → Task 2 (model/data/engine/helper) + Task 4 (`test_human_plus_one_con_raises_hp`). ✓
- §3 Blessed eligibility (human + flag), roll-time two-set keep-better for single + multi, summed-rolls comparison, no cross-set cherry-pick, tie keeps set A, reroll min_die unchanged → Task 3 (helper + tests) + Task 4 (route wiring, human-only). ✓
- §4 HP locked to one roll, roll affordance only while unrolled → Task 4 (`post_hp_roll` 400 on second roll) + Task 6 template (`hp_done` hides Roll button). ✓
- §5 `class_setup` step: drop hp/proficiencies/spells from `_wizard_steps`, always-present, sections gated; `_next_incomplete_step` incomplete until HP + (prof) + (spells); GET page renders HP → Proficiencies → Spells; HP roll its own action; section validators reused; single Continue; STEP_LABELS + breadcrumb one entry → Tasks 5 (plumbing) + 6 (page/template/routes). Route paths kept per the route-scope decision (only the GET page moved to `/class_setup`). ✓
- §6 `_apply_rule_changes` clears `hp_roll`/`hp_rolls` + `ability_adjustments` on flag change; existing weapon_proficiency / class / race clears still cover prof + spells → Task 5 Step 6. ✓
- §7 tests: flag gating + no pending (T1); optional modifiers load/apply/clamp/non-human (T2); Blessed single + multi + cross-set + tie, reroll (T3); effective CON +1 (T4); HP locked (T4); class_setup single breadcrumb + incomplete-until + section visibility + Continue gating (T5/T6); flag-toggle clears (T5). ✓

**Placeholder scan:** Every code step contains complete code; test-migration step quotes each exact old→new string with file + approximate line. No "TBD"/"handle edge cases"/"similar to". ✓

**Type consistency:** `roll_first_level_hp(hit_dice: list[str], *, blessed, min_die, rng) -> list[int]` is defined in Task 3 and called identically in Task 4 and the Task 4 spy tests. `apply_racial_modifiers(base, race, *, include_optional=False)` signature matches its Task 2 callers (`_post_racial_abilities`, the engine tests) and the unchanged `get_race`/Slice-4 default calls. `_class_setup_complete(draft)` defined in Task 5 and consumed by `_next_incomplete_step` (Task 5) and `get_class_setup`/`ready` (Task 6). `optional_ability_modifiers` is `dict[Ability,int]` across model, data (CHA/CON), and helper. Step id/label/route are consistently `class_setup` / "Class Setup" / `/class_setup`. ✓

**Risk notes:** The bulk of the diff is route/template plumbing over unchanged proficiency/spell validators (kept intact, only re-hosted). Blessed multi-class comparison is by summed rolls with a documented set-A tie rule. No migration (nothing deployed).
