# Ability Score Adjustments — legal-only choices: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the wizard's Adjust Ability Scores step offer only rules-legal adjustments — each lowerable ability drops in even steps, primes rise within the 2:1 budget — and enforce the even-step rule in the engine.

**Architecture:** Add one even-amount check to the existing `validate_ability_adjustments`; expand `_adjust_context` to precompute legal resulting-score options; swap the template's freeform number inputs for `<select>`s of those options; add a small inline vanilla-JS balance helper that disables Next until points freed = 2 × points spent. Server validation remains the backstop.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, vanilla JS. Tests via pytest.

**Spec:** `docs/superpowers/specs/2026-06-01-ability-adjust-legal-only-design.md`

---

## File Structure

- `aose/engine/ability_mods.py` — add even-amount enforcement to `validate_ability_adjustments` (pure function, no new deps).
- `aose/web/wizard.py` — extend `_adjust_context` with `lower_options` / `raise_options`. Route signatures unchanged.
- `aose/web/templates/wizard/adjust.html` — `<select>`s instead of `<input type=number>`, plus a balance tally element and inline JS.
- `tests/test_wizard_ability_adjust.py` — update the tests that encode the now-illegal odd spread; add even-rule and select-render tests.

All commands run from the project root `C:\Users\paulw\OneDrive\Documents\Claude Code\Adv OSE Builder`.

Run tests with: `.venv\Scripts\python.exe -m pytest tests/ -q`
(The trailing PermissionError on `pytest-current` is a known Windows quirk — ignore it.)

---

### Task 1: Engine enforces even-amount lowering

The rule: each prime `+1` costs `−2` from a **single** ability, so each individual lowered amount must be even. The current `validate_ability_adjustments` only checks the aggregate 2:1 total, so it wrongly accepts `{"STR":1,"INT":-1,"WIS":-1}`. Adding the check invalidates several existing tests that encode that spread — they are updated in the same task so the suite stays green per commit.

**Files:**
- Modify: `aose/engine/ability_mods.py` (`validate_ability_adjustments`, ~line 105-147)
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Update the existing tests that encode the now-illegal odd spread, and add the new even-rule tests**

In `tests/test_wizard_ability_adjust.py`, replace these four existing tests so they use a single even reduction:

```python
def test_validate_exact_two_to_one_passes(data):
    validate_ability_adjustments(
        _POST_RACIAL, [data.classes["fighter"]], {"STR": 1, "INT": -2}
    )


def test_validate_lower_below_nine_fails(data):
    scores = {**_POST_RACIAL, "INT": 10}
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            scores, [data.classes["fighter"]], {"STR": 1, "INT": -2}
        )
```

```python
def test_apply_adds_deltas():
    result = apply_ability_adjustments(
        {"STR": 12, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10},
        {"STR": 1, "INT": -2},
    )
    assert result["STR"] == 13
    assert result["INT"] == 11
    assert result["WIS"] == 13
    assert result["DEX"] == 12
```

```python
def test_raised_prime_increases_xp_multiplier(data):
    # Fighter prime is STR. Post-racial STR 15 → multiplier 1.05.
    # Raise to 16 (lower INT by 2) → multiplier 1.10.
    post_racial = {"STR": 15, "INT": 13, "WIS": 13, "DEX": 12, "CON": 12, "CHA": 10}
    before = prime_requisite_xp_multiplier(post_racial["STR"])
    creation = apply_ability_adjustments(post_racial, {"STR": 1, "INT": -2})
    after = prime_requisite_xp_multiplier(creation["STR"])
    assert before == 1.05
    assert after == 1.10
```

Then add two new tests next to the other `validate_*` tests:

```python
def test_validate_odd_single_lower_fails(data):
    # Balance is fine (freed 2 = 2x raised 1) but INT-1, WIS-1 each odd → illegal.
    with pytest.raises(AdjustmentError):
        validate_ability_adjustments(
            _POST_RACIAL, [data.classes["fighter"]],
            {"STR": 1, "INT": -1, "WIS": -1},
        )


def test_validate_even_single_lower_passes(data):
    validate_ability_adjustments(
        _POST_RACIAL, [data.classes["fighter"]], {"STR": 2, "INT": -4}
    )
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py::test_validate_odd_single_lower_fails -q`
Expected: FAIL — `DID NOT RAISE AdjustmentError` (the spread is currently accepted).

- [ ] **Step 3: Add the even-amount check to `validate_ability_adjustments`**

In `aose/engine/ability_mods.py`, inside `validate_ability_adjustments`, add the check right after the `lowered` dict is built and the `bad_lower` check, before the total-balance check. Insert:

```python
    odd_lowers = sorted(a for a, amt in lowered.items() if amt % 2 != 0)
    if odd_lowers:
        raise AdjustmentError(
            "Each lowered ability must drop by an even amount "
            f"(2 points buys 1 raise): {odd_lowers}."
        )
```

Also extend the docstring's bullet list with: `* each lowered amount is even (−2 per +1, from a single score)`.

- [ ] **Step 4: Run the full ability-adjust test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py -q`
Expected: the two new tests PASS, the four updated tests PASS. The wizard-route POST tests (`test_adjust_post_valid_stores_and_advances`, `test_finalize_reflects_adjustment`, `test_changing_class_clears_adjustment`) will now FAIL because they still post odd `lower_INT:1, lower_WIS:1` — they are fixed in Step 5.

- [ ] **Step 5: Update the wizard-route POST tests to use a single even reduction**

In `tests/test_wizard_ability_adjust.py`, change the three route tests' POST data and assertions:

```python
def test_adjust_post_valid_stores_and_advances(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2",
    })
    assert r.status_code == 303
    assert r.headers["location"].endswith("/class_setup")
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["ability_adjustments"] == {"STR": 1, "INT": -2}
```

```python
def test_finalize_reflects_adjustment(tmp_path):
    import json
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2",
    })
    client.post(f"/wizard/{draft_id}/hp/roll")
    client.post(f"/wizard/{draft_id}/hp")
    client.post(f"/wizard/{draft_id}/identity", data={"name": "Conan", "alignment": "law"})
    client.get(f"/wizard/{draft_id}/equipment")
    client.post(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/finalize")
    char_id = r.headers["location"].split("/")[-1]
    saved = json.loads((client._characters_dir / f"{char_id}.json").read_text())
    assert saved["abilities"]["STR"] == 14  # 13 +1
    assert saved["abilities"]["INT"] == 11  # 13 -2
    assert saved["abilities"]["WIS"] == 13  # unchanged
```

```python
def test_changing_class_clears_adjustment(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "2",
    })
    # Re-pick a different class — the stored adjustment must be cleared.
    client.post(f"/wizard/{draft_id}/class", data={"class_id": "thief"})
    draft = load_draft(draft_id, client._drafts_dir)
    assert "ability_adjustments" not in draft
```

Add one new route test asserting the even-rule is enforced through the route (balance is valid, but the spread is odd):

```python
def test_adjust_post_odd_spread_rejected(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)
    r = client.post(f"/wizard/{draft_id}/adjust", data={
        "raise_STR": "1", "lower_INT": "1", "lower_WIS": "1",
    })
    assert r.status_code == 400
```

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 7: Commit**

```bash
git add aose/engine/ability_mods.py tests/test_wizard_ability_adjust.py
git commit -m "fix(abilities): require even per-ability reductions when adjusting scores

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Precompute legal resulting-score options in `_adjust_context`

Give the template the exact list of legal resulting scores per ability so it never renders an illegal value. Lower steps by 2 down to the floor; raise steps by 1 up to 18. Each option carries the resulting `final` score and the `amount` of points moved (the delta that the form field submits).

**Files:**
- Modify: `aose/web/wizard.py` (`_adjust_context`, lines 683-705)
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write a failing test for the options**

Add to `tests/test_wizard_ability_adjust.py`:

```python
def test_adjust_context_legal_options(data):
    from aose.web.wizard import _adjust_context

    draft = {
        "abilities": dict(_FIGHTER_ABILITIES),  # STR/INT/WIS = 13
        "ruleset": RuleSet().model_dump(mode="json"),
        "race_id": "human",
        "class_id": "fighter",
    }
    rows = {r["name"]: r for r in _adjust_context(draft, data)["adjust_rows"]}

    # STR is the prime → raise options step by 1 up to 18, starting at 13.
    assert [o["final"] for o in rows["STR"]["raise_options"]] == list(range(13, 19))
    assert rows["STR"]["raise_options"][0]["amount"] == 0
    assert rows["STR"]["lower_options"] == []  # prime is not lowerable

    # INT is lowerable, floor 9 → resulting scores 13, 11, 9; deltas 0, 2, 4.
    assert [o["final"] for o in rows["INT"]["lower_options"]] == [13, 11, 9]
    assert [o["amount"] for o in rows["INT"]["lower_options"]] == [0, 2, 4]
    assert rows["INT"]["raise_options"] == []  # not a prime → not raisable
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py::test_adjust_context_legal_options -q`
Expected: FAIL — `KeyError: 'raise_options'`.

- [ ] **Step 3: Add the option lists to `_adjust_context`**

Replace the `rows.append({...})` block in `aose/web/wizard.py` so each row also builds `lower_options` and `raise_options`:

```python
    rows = []
    for ab in ABILITY_ORDER:
        name = ab.value
        delta = stored.get(name, 0)
        score = post_racial[name]
        raisable = name in adj["raisable"]
        lowerable = name in adj["lowerable"]
        floor = _ability_floor(name, classes) if lowerable else None

        raise_options = []
        if raisable:
            raise_options = [
                {"amount": amt, "final": score + amt}
                for amt in range(0, 18 - score + 1)
            ]
        lower_options = []
        if lowerable:
            lower_options = [
                {"amount": amt, "final": score - amt}
                for amt in range(0, score - floor + 1, 2)
            ]

        rows.append({
            "name": name,
            "score": score,
            "raisable": raisable,
            "lowerable": lowerable,
            "floor": floor,
            "raise_val": delta if delta > 0 else 0,
            "lower_val": -delta if delta < 0 else 0,
            "raise_options": raise_options,
            "lower_options": lower_options,
        })
    return {"adjust_rows": rows}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py::test_adjust_context_legal_options -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py tests/test_wizard_ability_adjust.py
git commit -m "feat(abilities): precompute legal adjustment options for the adjust step

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Swap template inputs for legal-value dropdowns

Render the precomputed options as `<select>`s. Visible label is the resulting score (with a "(no change)" hint on the zero option); option value is the delta the form already expects. Illegal in-between values are simply never options.

**Files:**
- Modify: `aose/web/templates/wizard/adjust.html`
- Test: `tests/test_wizard_ability_adjust.py`

- [ ] **Step 1: Write a failing render test**

Add to `tests/test_wizard_ability_adjust.py`:

```python
def test_adjust_get_renders_select_options(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _drive_to_adjust(client)  # STR/INT/WIS = 13, fighter
    r = client.get(f"/wizard/{draft_id}/adjust")
    assert r.status_code == 200
    # INT lowerable: even resulting scores are options, odd ones never are.
    assert '<select name="lower_INT"' in r.text
    assert '<option value="2"' in r.text   # → 11
    assert '<option value="4"' in r.text   # → 9
    # STR raisable via a select, not a freeform number input.
    assert '<select name="raise_STR"' in r.text
    assert 'type="number"' not in r.text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py::test_adjust_get_renders_select_options -q`
Expected: FAIL — the template still emits `type="number"` and no `<select>`.

- [ ] **Step 3: Rewrite the Raise/Lower cells as selects**

Replace the two `<td class="num">` cells (the Raise and Lower columns) in `aose/web/templates/wizard/adjust.html` with:

```html
                <td class="num">
                    {% if row.raisable %}
                    <select name="raise_{{ row.name }}" class="adjust-raise">
                        {% for opt in row.raise_options %}
                        <option value="{{ opt.amount }}"
                            {% if opt.amount == row.raise_val %}selected{% endif %}>
                            {{ opt.final }}{% if opt.amount == 0 %} (no change){% endif %}
                        </option>
                        {% endfor %}
                    </select>
                    {% else %}&mdash;{% endif %}
                </td>
                <td class="num">
                    {% if row.lowerable %}
                    <select name="lower_{{ row.name }}" class="adjust-lower">
                        {% for opt in row.lower_options %}
                        <option value="{{ opt.amount }}"
                            {% if opt.amount == row.lower_val %}selected{% endif %}>
                            {{ opt.final }}{% if opt.amount == 0 %} (no change){% endif %}
                        </option>
                        {% endfor %}
                    </select>
                    <span class="muted">(floor {{ row.floor }})</span>
                    {% else %}&mdash;{% endif %}
                </td>
```

- [ ] **Step 4: Run the render test plus the existing GET test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_ability_adjust.py::test_adjust_get_renders_select_options tests/test_wizard_ability_adjust.py::test_adjust_get_renders_scores_and_marks -q`
Expected: both PASS (`test_adjust_get_renders_scores_and_marks` still finds the `raise_STR` / `lower_INT` / `lower_WIS` names and confirms no `lower_STR`).

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/wizard/adjust.html tests/test_wizard_ability_adjust.py
git commit -m "feat(abilities): render adjustment choices as legal-value dropdowns

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Live balance helper (vanilla JS)

Add an inline script that keeps a running tally of points freed (Σ lower deltas) vs spent (Σ raise deltas) and disables **Next** until `freed == 2 * spent`. Progressive enhancement — without JS the dropdowns still submit and the server validates. This task is presentation-only; verify it by manual run, since the no-JS path is already covered by the route tests.

**Files:**
- Modify: `aose/web/templates/wizard/adjust.html`

- [ ] **Step 1: Add an id to the submit button and a tally element**

In `aose/web/templates/wizard/adjust.html`, change the submit button line to give it an id, and add a balance paragraph just before it:

```html
    <p id="adjust-balance" class="muted" aria-live="polite"></p>
    <button type="submit" id="adjust-next" class="primary">Next: Choose Alignment &rarr;</button>
```

- [ ] **Step 2: Add the inline balance script at the end of the file**

Append to `aose/web/templates/wizard/adjust.html`:

```html
<script>
(function () {
    var lowers = Array.prototype.slice.call(document.querySelectorAll('.adjust-lower'));
    var raises = Array.prototype.slice.call(document.querySelectorAll('.adjust-raise'));
    var tally = document.getElementById('adjust-balance');
    var next = document.getElementById('adjust-next');
    if (!tally || !next) { return; }

    function sum(els) {
        return els.reduce(function (acc, el) { return acc + (parseInt(el.value, 10) || 0); }, 0);
    }

    function recompute() {
        var freed = sum(lowers);
        var spent = sum(raises);
        var balanced = freed === 2 * spent;
        next.disabled = !balanced;
        if (freed === 0 && spent === 0) {
            tally.textContent = 'No adjustments — leave as is, or trade points to raise a prime.';
        } else if (balanced) {
            tally.textContent = 'Balanced: ' + freed + ' points freed buy ' + spent + ' raised.';
        } else {
            tally.textContent = 'Unbalanced: ' + freed + ' points freed, ' + spent +
                ' raised (need exactly 2 freed per 1 raised).';
        }
    }

    lowers.concat(raises).forEach(function (el) {
        el.addEventListener('change', recompute);
    });
    recompute();
})();
</script>
```

- [ ] **Step 3: Run the suite to confirm nothing broke**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (the no-JS server path is unchanged).

- [ ] **Step 4: Manual verification**

Start the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Create a character, roll/seed abilities, pick Human + Fighter, reach the Adjust step, and confirm:
- The Raise/Lower columns are dropdowns; lowering INT offers only 13 / 11 / 9.
- Lowering INT to 11 with STR left at 13 shows "Unbalanced" and Next is disabled.
- Raising STR to 14 then shows "Balanced" and Next is enabled.
- Submitting the balanced choice advances to the next step and the saved sheet reflects STR 14 / INT 11.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/wizard/adjust.html
git commit -m "feat(abilities): live 2:1 balance helper on the adjust step

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Engine even-amount enforcement → Task 1. ✔
- `_adjust_context` legal options → Task 2. ✔
- Template dropdowns of resulting scores → Task 3. ✔
- Live balance helper → Task 4. ✔
- Updated tests for the now-illegal spread + new even-rule/route/render tests → Tasks 1–3. ✔
- No data/model/migration changes; step flow untouched → confirmed, no such tasks. ✔

**Placeholder scan:** No TBD/TODO; every code step shows full code and exact commands.

**Type/name consistency:** Option dicts use `{"amount", "final"}` in Task 2 and are read as `opt.amount` / `opt.final` in Task 3; form fields stay `raise_<name>` / `lower_<name>` carrying point deltas across engine, route, and template; select classes `adjust-raise` / `adjust-lower` and ids `adjust-balance` / `adjust-next` are defined in Task 3/4 and consumed by the Task 4 script.
