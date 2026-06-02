# Wizard Equipment — Lock Starting Gold (remove reroll) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roll starting gold exactly once on first visit to the wizard equipment step, lock it immediately, and remove the "Re-roll Starting Gold" affordance and route entirely.

**Architecture:** Starting gold is seeded in `get_equipment` (`wizard.py`). Change the seed so `gold_locked` is `True` from the first visit instead of `False`. Delete the `reroll-gold` route and the template block that renders the button. Buy/Continue still set `gold_locked = True` (now redundant but harmless). The live character sheet (`routes.py`) already passes `gold_locked = True` and `show_gold_reroll = False`, so it is unaffected.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, pytest. Run commands via `.venv\Scripts\python.exe`.

---

## File Structure

| File | Change |
|---|---|
| `aose/web/wizard.py` | Seed `gold_locked = True`; delete `post_equipment_reroll_gold` route |
| `aose/web/templates/_equipment_ui.html` | Delete `show_gold_reroll` button block + header-comment line |
| `aose/web/templates/wizard/equipment.html` | Update intro copy; drop `show_gold_reroll` `{% with %}` wrapper |
| `tests/test_equipment.py` | Delete two reroll tests; flip one assertion; update add-route test; add route-gone test |
| `tests/test_containers.py` | Update one `gold_locked` assertion |

Note (Windows): the trailing `PermissionError` on `pytest-current` is a known pytest-9 tempdir quirk — ignore it (see CLAUDE.md).

---

### Task 1: Lock starting gold on first visit + add route-gone test

**Files:**
- Modify: `aose/web/wizard.py:1207-1211` (seed block in `get_equipment`)
- Modify: `aose/web/wizard.py:1218-1226` (delete `post_equipment_reroll_gold`)
- Test: `tests/test_equipment.py`

- [ ] **Step 1: Update the seed-gold assertion test**

In `tests/test_equipment.py`, change `test_equipment_get_seeds_starting_gold` (currently around line 208-215) so the locked assertion expects `True`. Replace this line:

```python
    assert draft.get("gold_locked") is False
```

with:

```python
    assert draft.get("gold_locked") is True
```

- [ ] **Step 2: Add a test that the reroll route is gone**

In `tests/test_equipment.py`, add this test immediately after `test_equipment_get_seeds_starting_gold`:

```python
def test_reroll_gold_route_removed(client):
    """The reroll-gold endpoint no longer exists — starting gold is fixed."""
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    r = client.post(f"/wizard/{draft_id}/equipment/reroll-gold")
    assert r.status_code in (404, 405)
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py::test_equipment_get_seeds_starting_gold tests/test_equipment.py::test_reroll_gold_route_removed -q`

Expected: FAIL. `test_equipment_get_seeds_starting_gold` fails because gold is still seeded `False`; `test_reroll_gold_route_removed` fails because the route still returns 303 (not 404/405).

- [ ] **Step 4: Seed `gold_locked = True` in `get_equipment`**

In `aose/web/wizard.py`, in `get_equipment`, change the seed block. Replace:

```python
    if "gold" not in draft:
        draft["gold"] = roll_starting_gold()
        draft.setdefault("inventory", [])
        draft.setdefault("gold_locked", False)
        save_draft(draft_id, draft, _drafts_dir(request))
```

with:

```python
    if "gold" not in draft:
        draft["gold"] = roll_starting_gold()
        draft.setdefault("inventory", [])
        draft["gold_locked"] = True  # rolled once, locked immediately — no reroll
        save_draft(draft_id, draft, _drafts_dir(request))
```

- [ ] **Step 5: Delete the `post_equipment_reroll_gold` route**

In `aose/web/wizard.py`, delete the entire route (currently lines 1218-1226):

```python
@router.post("/{draft_id}/equipment/reroll-gold")
async def post_equipment_reroll_gold(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if draft.get("gold_locked"):
        raise HTTPException(400, "Starting gold is locked — a purchase has already been made.")
    draft["gold"] = roll_starting_gold()
    draft.setdefault("inventory", [])
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")
```

Leave the two blank lines that separated it from the surrounding routes so `get_equipment` and `post_equipment_buy` remain separated by one blank-line gap.

- [ ] **Step 6: Run both tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py::test_equipment_get_seeds_starting_gold tests/test_equipment.py::test_reroll_gold_route_removed -q`

Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add aose/web/wizard.py tests/test_equipment.py
git commit -m "feat(equipment): lock starting gold on first visit; remove reroll route"
```

---

### Task 2: Remove the reroll affordance from templates

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html:5-23`
- Modify: `aose/web/templates/wizard/equipment.html`

- [ ] **Step 1: Delete the reroll button block in `_equipment_ui.html`**

In `aose/web/templates/_equipment_ui.html`, delete this block (currently lines 17-23):

```html
    {% if show_gold_reroll and not gold_locked %}
    <form method="post" action="{{ target_url_prefix }}/reroll-gold" class="inline-form">
        <button type="submit">Re-roll Starting Gold</button>
    </form>
    {% elif show_gold_reroll and gold_locked %}
    <span class="muted small">Starting roll locked &mdash; a purchase has been made.</span>
    {% endif %}
```

The `equipment-header` div now contains only the gold display and the (sheet-only) `show_gold_grant` form.

- [ ] **Step 2: Remove the `show_gold_reroll` doc line from the header comment**

In `aose/web/templates/_equipment_ui.html`, delete this line from the leading `{# ... #}` comment (currently line 8):

```
     - show_gold_reroll    bool   (wizard only — for the starting-gold reroll)
```

Also update the `gold_locked` doc line (currently line 5) so it no longer references the now-deleted button. Replace:

```
     - gold_locked         bool   (re-roll button hidden when true)
```

with:

```
     - gold_locked         bool   (true once a purchase locks the gold; always true in the wizard)
```

- [ ] **Step 3: Update `wizard/equipment.html` copy and drop the `with` wrapper**

Replace the entire contents of `aose/web/templates/wizard/equipment.html` with:

```html
<h2>Equipment</h2>
<p class="muted">
    Your starting gold was rolled once with 3d6 &times; 10 and is now fixed.
    Buy what you need from the shop below.
</p>

{% include "_equipment_ui.html" %}

<form method="post" action="/wizard/{{ draft_id }}/equipment" class="step-form">
    <button type="submit" class="primary">Next: Review &rarr;</button>
</form>
```

(`show_gold_reroll` is no longer passed, so the deleted button block can never render.)

- [ ] **Step 4: Verify no stray references remain**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py -q -k "equipment_step or accessible_after_identity"`

Expected: PASS — the equipment step still renders (GET returns 200) and Continue still advances to review.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/_equipment_ui.html aose/web/templates/wizard/equipment.html
git commit -m "feat(equipment): remove starting-gold reroll button from wizard UI"
```

---

### Task 3: Update the remaining tests that assumed an unlocked roll

These tests are no longer valid because `gold_locked` is now `True` from first visit and the reroll route is gone.

**Files:**
- Modify: `tests/test_equipment.py` (delete two tests; update one)
- Modify: `tests/test_containers.py` (update one assertion)

- [ ] **Step 1: Delete `test_equipment_reroll_works_before_first_purchase`**

In `tests/test_equipment.py`, delete the whole test (currently lines 218-227):

```python
def test_equipment_reroll_works_before_first_purchase(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    before = load_draft(draft_id, client._drafts_dir)["gold"]
    for _ in range(10):
        client.post(f"/wizard/{draft_id}/equipment/reroll-gold")
        after = load_draft(draft_id, client._drafts_dir)["gold"]
        if after != before:
            return
    pytest.fail("Gold reroll never changed value across 10 tries")
```

- [ ] **Step 2: Delete `test_reroll_after_lock_is_rejected`**

In `tests/test_equipment.py`, delete the whole test (currently lines 245-253):

```python
def test_reroll_after_lock_is_rejected(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")
    draft = load_draft(draft_id, client._drafts_dir)
    draft["gold"] = 50
    save_draft(draft_id, draft, client._drafts_dir)
    client.post(f"/wizard/{draft_id}/equipment/buy", data={"item_id": "torch"})
    r = client.post(f"/wizard/{draft_id}/equipment/reroll-gold")
    assert r.status_code == 400
```

- [ ] **Step 3: Update `test_wizard_add_route_does_not_lock_gold`**

The add route no longer governs gold locking (gold is locked on first visit), and the reroll route is gone. Replace the whole test (currently lines 410-421) with a version that keeps the still-valid behaviour — Add grants an item without spending gold:

```python
def test_wizard_add_route_grants_item_without_spending_gold(client):
    draft_id = _walk_to_equipment(client)
    client.get(f"/wizard/{draft_id}/equipment")  # seeds gold (already locked)
    before_gold = load_draft(draft_id, client._drafts_dir)["gold"]
    r = client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "torch"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert draft["inventory"] == ["torch"]
    assert draft["gold"] == before_gold  # Add is free
```

- [ ] **Step 4: Update the container add test's locked assertion**

In `tests/test_containers.py`, `test_wizard_add_creates_container_without_locking_gold` (currently lines 630-637) asserts `gold_locked is False`, which is no longer true. Rewrite the test to assert what still matters — Add creates the container without charging gold. The `_walk_to_equipment` helper in this file already GETs equipment (line 612), seeding a random 3d6×10 starting gold, so capture it before the add. Replace the whole test:

```python
def test_wizard_add_creates_container_without_locking_gold(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    r = client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "bag_of_holding"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert len(draft["containers"]) == 1
    assert draft.get("gold_locked") is False
```

with:

```python
def test_wizard_add_creates_container_without_spending_gold(tmp_path):
    client = _make_client(tmp_path)
    draft_id = _walk_to_equipment(client)
    before_gold = load_draft(draft_id, client._drafts_dir)["gold"]
    r = client.post(f"/wizard/{draft_id}/equipment/add", data={"item_id": "bag_of_holding"})
    assert r.status_code == 303
    draft = load_draft(draft_id, client._drafts_dir)
    assert len(draft["containers"]) == 1
    assert draft["gold"] == before_gold  # Add is free
```

- [ ] **Step 5: Run the full equipment + containers suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py tests/test_containers.py -q`

Expected: PASS (all selected tests pass; ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 6: Commit**

```bash
git add tests/test_equipment.py tests/test_containers.py
git commit -m "test(equipment): drop reroll tests; gold locked from first visit"
```

---

### Task 4: Full-suite regression + leftover-reference sweep

**Files:** none (verification only)

- [ ] **Step 1: Grep for any leftover references to the removed reroll/flag**

Run: `.venv\Scripts\python.exe -m pytest --collect-only -q > NUL` is not needed; instead search the source tree. Use the Grep tool (or `git grep`) for `show_gold_reroll` and `reroll-gold` / `reroll_gold`.

Expected matches: only the spec file (`docs/superpowers/specs/2026-05-31-wizard-equipment-gold-design.md`), this plan, and the unrelated `tests/test_sheet*` assertion `test_sheet_does_not_offer_reroll_button` (which asserts the endpoint is *absent* from the sheet and is still correct). There must be **no** match in `aose/web/wizard.py`, `aose/web/templates/`, or `routes.py` (other than `routes.py`'s existing `"show_gold_reroll": False` context value, which is harmless and may stay).

- [ ] **Step 2: Run the whole test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`

Expected: all tests pass (the suite was 577 green before this slice; expect 577 − 2 deleted = 575, +1 added = 576, net depending on prior count — the important signal is zero failures). Ignore the trailing `pytest-current` PermissionError.

- [ ] **Step 3: Manual smoke check (optional but recommended)**

Run the app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`, walk a draft to the equipment step, and confirm: gold shows a fixed value, there is no "Re-roll Starting Gold" button, and the intro copy says the gold is fixed.

- [ ] **Step 4: Final commit (if Step 1 surfaced any stray reference to fix)**

Only if you had to remove a leftover reference:

```bash
git add -A
git commit -m "chore(equipment): remove leftover reroll references"
```

---

## Self-Review Notes

- **Spec coverage:** wizard.py seed flip (Task 1) ✓; remove route (Task 1) ✓; stop passing `show_gold_reroll` (Task 2, equipment.html drops the `{% with %}`) ✓; delete template button block + comment line (Task 2) ✓; update intro copy (Task 2) ✓; remove reroll tests (Task 3) ✓; new route-gone + locked-on-first-visit tests (Task 1) ✓; grep sweep (Task 4) ✓; sheet unaffected (verified — `routes.py:102,114` already pass `gold_locked=True`, `show_gold_reroll=False`) ✓.
- **No migration** — nothing deployed (per CLAUDE.md / `project_no_migrations_needed`).
- **`routes.py`'s `"show_gold_reroll": False`** is intentionally left in place; the shared partial no longer reads it, but removing it is out of scope and harmless. The plan does not require touching `routes.py`.
