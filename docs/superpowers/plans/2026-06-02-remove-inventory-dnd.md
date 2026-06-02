# Remove Inventory Drag-and-Drop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the inventory drag-and-drop UX, leaving the existing button/dropdown forms (Stow, Take Out, Stash, etc.) as the only way to move items.

**Architecture:** Pure deletion. Remove the `/equipment/move` routes (sheet + wizard), the shared `dispatch_move` dispatcher, the drag handlers in the inventory JS (keeping only the container-collapse toggle), the drag-related HTML attributes, and the drag CSS. Delete the tests that exercised those paths.

**Tech Stack:** Python 3 / FastAPI / Jinja2 / vanilla JS. Tests run with `.venv\Scripts\python.exe -m pytest`.

---

## Notes for the implementer

- Run the venv Python explicitly: `.venv\Scripts\python.exe -m pytest tests/ -q`. Bare `pytest`/`uvicorn` won't work.
- The trailing `PermissionError` on `pytest-current` is a known Windows/pytest-9 tempdir quirk — ignore it.
- This is deletion work, so there are no new failing-test-first cycles. Each task removes code/tests together so the suite stays green after every commit, then a final task verifies nothing dangles.
- Order matters: remove the Python imports/routes and delete `move_dispatch.py` in the **same** commit, otherwise `routes.py` / `wizard.py` import a missing module and the app won't start.

---

## File Structure

| File | Change |
|---|---|
| `aose/web/move_dispatch.py` | **Delete** |
| `aose/web/routes.py` | Remove `dispatch_move` import + `equipment_move` route |
| `aose/web/wizard.py` | Remove `dispatch_move` import + `equipment_move` route |
| `aose/web/static/inventory_dnd.js` | **Rename** to `inventory.js`, keep only collapse toggle |
| `aose/web/templates/_equipment_ui.html` | Strip `draggable` / `data-source` / `data-target` / `data-equipment-url-prefix`; update `<script src>` |
| `aose/web/static/sheet.css` | Remove drag-and-drop visual block |
| `tests/test_containers.py` | Delete the 8 DnD-related tests |
| `tests/test_equip_enforcement.py` | Delete the 3 dispatcher tests + import + helper |

---

## Task 1: Remove the backend `/move` routes and dispatcher

**Files:**
- Delete: `aose/web/move_dispatch.py`
- Modify: `aose/web/routes.py` (import line 52; route lines 504–522)
- Modify: `aose/web/wizard.py` (import line 83; route lines 1668–1702)
- Modify: `tests/test_equip_enforcement.py` (lines 160–202)

- [ ] **Step 1: Delete the dispatcher module**

```bash
git rm aose/web/move_dispatch.py
```

- [ ] **Step 2: Remove the import in `routes.py`**

Delete this line (currently line 52):

```python
from aose.web.move_dispatch import dispatch_move
```

- [ ] **Step 3: Remove the `equipment_move` route in `routes.py`**

Delete the whole block (currently lines 504–522, including the blank line above it and the `@router.post` decorator):

```python
@router.post("/character/{character_id}/equipment/move")
async def equipment_move(request: Request, character_id: str,
                         source: str = Form(...),
                         target: str = Form(...),
                         item_id: str = Form(""),
                         instance_id: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    classes = [game_data.classes[e.class_id] for e in spec.classes
               if e.class_id in game_data.classes]
    try:
        dispatch_move(spec, source, target, item_id, instance_id, game_data,
                      allowed_weapons=allowed_weapon_ids(classes, game_data),
                      allowed_armor=allowed_armor_ids(classes, game_data),
                      allow_shields=shields_allowed(classes))
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Leave the `# ── Magic item actions ──` comment and the rest of the file intact. (`allowed_weapon_ids` / `allowed_armor_ids` / `shields_allowed` stay imported — they are still used by the `/equip` route.)

- [ ] **Step 4: Remove the import in `wizard.py`**

Delete this line (currently line 83):

```python
from aose.web.move_dispatch import dispatch_move
```

- [ ] **Step 5: Remove the `equipment_move` route in `wizard.py`**

Delete the whole block (currently lines 1668–1702):

```python
@router.post("/{draft_id}/equipment/move")
async def equipment_move(request: Request, draft_id: str,
                         source: str = Form(...),
                         target: str = Form(...),
                         item_id: str = Form(""),
                         instance_id: str = Form("")):
    draft = _load(request, draft_id)
    game_data = request.app.state.game_data

    class _DraftShim:
        pass

    shim = _DraftShim()
    shim.inventory = draft.get("inventory", [])
    shim.stashed = draft.get("stashed", [])
    shim.equipped = draft.get("equipped", {})
    shim.equipped_weapons = draft.get("equipped_weapons", [])
    shim.containers = [ContainerInstance.model_validate(c)
                       for c in draft.get("containers", [])]
    classes = [game_data.classes[cid] for cid in _class_ids(draft)
               if cid in game_data.classes]
    try:
        dispatch_move(shim, source, target, item_id, instance_id, game_data,
                      allowed_weapons=allowed_weapon_ids(classes, game_data),
                      allowed_armor=allowed_armor_ids(classes, game_data),
                      allow_shields=shields_allowed(classes))
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = shim.inventory
    draft["stashed"] = shim.stashed
    draft["equipped"] = shim.equipped
    draft["equipped_weapons"] = shim.equipped_weapons
    draft["containers"] = [c.model_dump() for c in shim.containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)
```

> **Check after deleting:** `ContainerInstance` may now be unused in `wizard.py`. Search the file for `ContainerInstance` — if this was its only use, also remove it from the imports; if it appears elsewhere, leave the import alone. (Do the same sanity check for `_DraftShim`-only helpers — there are none beyond this block.)

- [ ] **Step 6: Delete the dispatcher tests in `tests/test_equip_enforcement.py`**

Delete everything from the comment header through `test_dispatch_move_unrestricted_by_default` (currently lines 160–202):

```python
# ── drag-and-drop dispatcher enforcement ────────────────────────────────────

from aose.web.move_dispatch import dispatch_move


class _MoveState:
    def __init__(self, inventory):
        self.inventory = list(inventory)
        self.stashed = []
        self.equipped = {}
        self.equipped_weapons = []
        self.containers = []


def test_dispatch_move_enforces_weapon_allowance(data):
    # A magic-user dragging a sword to Equipped must be rejected.
    classes = [data.classes["magic_user"]]
    state = _MoveState(["sword"])
    with pytest.raises(ValueError, match="cannot use"):
        dispatch_move(
            state, "carried", "equipped", "sword", "", data,
            allowed_weapons=allowed_weapon_ids(classes, data),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )


def test_dispatch_move_allows_permitted_weapon(data):
    classes = [data.classes["magic_user"]]
    state = _MoveState(["dagger"])
    dispatch_move(
        state, "carried", "equipped", "dagger", "", data,
        allowed_weapons=allowed_weapon_ids(classes, data),
        allowed_armor=allowed_armor_ids(classes, data),
        allow_shields=shields_allowed(classes),
    )
    assert state.equipped_weapons == ["dagger"]


def test_dispatch_move_unrestricted_by_default(data):
    state = _MoveState(["sword"])
    dispatch_move(state, "carried", "equipped", "sword", "", data)
    assert state.equipped_weapons == ["sword"]
```

Keep the `# ── inventory_view class_allowed flag ...` section and everything after it. If `allowed_weapon_ids` / `allowed_armor_ids` / `shields_allowed` / `pytest` become unused in the file after this deletion, leave them — they are used by the earlier tests in the file (verify with a quick search; do not remove imports that are still referenced).

- [ ] **Step 7: Run the affected test files to confirm they still collect and pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -q`
Expected: PASS (no import error for `move_dispatch`).

- [ ] **Step 8: Confirm the app still imports**

Run: `.venv\Scripts\python.exe -c "import aose.web.app"`
Expected: no output, exit code 0 (no `ModuleNotFoundError: aose.web.move_dispatch`).

- [ ] **Step 9: Commit**

```bash
git add aose/web/move_dispatch.py aose/web/routes.py aose/web/wizard.py tests/test_equip_enforcement.py
git commit -m "refactor(web): remove inventory drag-and-drop dispatcher and /move routes"
```

---

## Task 2: Strip the JS to collapse-only and rename it

**Files:**
- Rename: `aose/web/static/inventory_dnd.js` → `aose/web/static/inventory.js`
- Modify: `aose/web/templates/_equipment_ui.html` (script tag, currently line 324)

- [ ] **Step 1: Rename the file**

```bash
git mv aose/web/static/inventory_dnd.js aose/web/static/inventory.js
```

- [ ] **Step 2: Replace the file contents with collapse-only logic**

Overwrite `aose/web/static/inventory.js` with exactly:

```javascript
/* Container collapse toggle.
 *
 * Each container row has a ▾ button (.container-toggle) that shows/hides its
 * child rows (tr.container-child) by toggling the .container-collapsed class.
 * Rows are matched by data-instance-id. */
(function () {
    document.querySelectorAll(".container-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const row = btn.closest("tr.container-row");
            if (!row) return;
            const instanceId = row.dataset.instanceId;
            const expanded = btn.getAttribute("aria-expanded") === "true";
            btn.setAttribute("aria-expanded", expanded ? "false" : "true");
            document.querySelectorAll(
                `tr.container-child[data-instance-id="${instanceId}"]`
            ).forEach(r => r.classList.toggle("container-collapsed"));
        });
    });
})();
```

- [ ] **Step 3: Point the template at the renamed file**

In `aose/web/templates/_equipment_ui.html`, change (currently line 324):

```html
<script src="/static/inventory_dnd.js" defer></script>
```

to:

```html
<script src="/static/inventory.js" defer></script>
```

- [ ] **Step 4: Commit**

```bash
git add aose/web/static/inventory.js aose/web/templates/_equipment_ui.html
git commit -m "refactor(web): reduce inventory JS to container-collapse only"
```

---

## Task 3: Remove drag attributes from the template

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html`

- [ ] **Step 1: Drop the DnD wrapper attribute**

Change the opening wrapper (currently line 13) from:

```html
<div data-equipment-url-prefix="{{ target_url_prefix }}">
```

to a plain div:

```html
<div>
```

- [ ] **Step 2: Remove `data-target` from the two section-head macros**

In the `inv_table` macro (currently line 79), change:

```html
<h4 class="inv-section-head" data-target="{{ state }}">{{ label }} {% if weight_note %}<span class="muted small">{{ weight_note }}</span>{% endif %}</h4>
```

to:

```html
<h4 class="inv-section-head">{{ label }} {% if weight_note %}<span class="muted small">{{ weight_note }}</span>{% endif %}</h4>
```

In the `container_table` macro (currently line 106), change:

```html
<h4 class="inv-section-head" data-target="{{ state }}">{{ label }} containers</h4>
```

to:

```html
<h4 class="inv-section-head">{{ label }} containers</h4>
```

- [ ] **Step 3: Remove `draggable` + `data-source` from the inventory row**

In the `inv_table` macro (currently line 91), change:

```html
        <tr class="inv-row" draggable="true" data-source="{{ state }}" data-item-id="{{ row.id }}">
```

to (keep `data-item-id` — harmless, and keeps the row identifiable):

```html
        <tr class="inv-row" data-item-id="{{ row.id }}">
```

- [ ] **Step 4: Remove `draggable` from the container row**

In the `container_table` macro (currently lines 118–121), change:

```html
        <tr class="container-row"
            data-instance-id="{{ c.instance_id }}"
            data-state="{{ c.state }}"
            draggable="true">
```

to (keep `data-instance-id` — the collapse toggle needs it):

```html
        <tr class="container-row"
            data-instance-id="{{ c.instance_id }}"
            data-state="{{ c.state }}">
```

- [ ] **Step 5: Remove `data-source` + `draggable` from the container-child row**

In the `container_table` macro (currently lines 157–161), change:

```html
        <tr class="container-child" id="cnt-{{ c.instance_id }}"
            data-instance-id="{{ c.instance_id }}"
            data-item-id="{{ row.id }}"
            data-source="container:{{ c.instance_id }}"
            draggable="true">
```

to (keep `data-instance-id` for collapse + `data-item-id`):

```html
        <tr class="container-child" id="cnt-{{ c.instance_id }}"
            data-instance-id="{{ c.instance_id }}"
            data-item-id="{{ row.id }}">
```

- [ ] **Step 6: Confirm no drag attributes remain in the template**

Run: `.venv\Scripts\python.exe -m pytest tests/test_containers.py -q -k collapse`
Expected: the collapse-button test still passes.

Then grep the template:
Run (PowerShell): `Select-String -Path aose\web\templates\_equipment_ui.html -Pattern 'draggable|data-source|data-target|data-equipment-url-prefix'`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/_equipment_ui.html
git commit -m "refactor(web): strip drag-and-drop attributes from equipment template"
```

---

## Task 4: Remove the drag CSS

**Files:**
- Modify: `aose/web/static/sheet.css` (currently lines 944–958)

- [ ] **Step 1: Delete the drag-and-drop visual block**

Remove this entire block (currently lines 944–958):

```css
/* ── Drag-and-drop visual feedback ─────────────────────────────────── */

[draggable="true"] {
    cursor: grab;
}

[draggable="true"]:active {
    cursor: grabbing;
}

.drag-over {
    outline: 2px dashed #5b8f3e;
    outline-offset: -2px;
    background: #ecf3e0;
}
```

Leave the `/* ── Magic items ── */` block immediately after it intact.

- [ ] **Step 2: Confirm the rules are gone**

Run (PowerShell): `Select-String -Path aose\web\static\sheet.css -Pattern 'draggable|drag-over'`
Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add aose/web/static/sheet.css
git commit -m "style(web): remove drag-and-drop CSS"
```

---

## Task 5: Delete the DnD tests in `tests/test_containers.py`

**Files:**
- Modify: `tests/test_containers.py`

- [ ] **Step 1: Delete the six `/equipment/move` route tests**

Remove these test functions in full (currently lines 849–931):
`test_move_carried_to_equipped_equips`, `test_move_equipped_to_carried_unequips`,
`test_move_carried_to_container_stows`, `test_move_container_row_to_stashed_section_stashes`,
`test_move_container_to_carried_takes_out`, `test_move_invalid_combo_returns_400`.

For reference, the first and last to delete are:

```python
def test_move_carried_to_equipped_equips(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["sword"])
    r = client.post("/character/test/equipment/move", data={
        "source": "carried", "target": "equipped",
        "item_id": "sword",
    })
    assert r.status_code == 303
    spec = load_character("test", client._characters_dir)
    assert spec.equipped_weapons == ["sword"]
```

```python
def test_move_invalid_combo_returns_400(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["torch"])
    r = client.post("/character/test/equipment/move", data={
        "source": "carried", "target": "equipped",
        "item_id": "torch",   # torch isn't equippable
    })
    assert r.status_code == 400
```

- [ ] **Step 2: Delete the two DnD-rendering tests**

Remove these two functions in full (currently lines 997–1009):

```python
def test_sheet_includes_dnd_script_tag(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client)
    r = client.get("/character/test")
    assert "inventory_dnd.js" in r.text


def test_sheet_inventory_rows_carry_dnd_attributes(tmp_path):
    client = _make_client(tmp_path)
    _seed_character(client, inventory=["sword"])
    r = client.get("/character/test")
    assert 'data-source="carried"' in r.text
    assert 'data-item-id="sword"' in r.text
```

> **Keep** `test_sheet_renders_container_row_with_capacity_badge` (it asserts `data-instance-id` and the Stow form, both still present) and `test_sheet_container_row_collapse_button_present`.

- [ ] **Step 3: Run the file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_containers.py -q`
Expected: PASS, no references to `/equipment/move`, `inventory_dnd.js`, or `data-source`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_containers.py
git commit -m "test(web): drop inventory drag-and-drop tests"
```

---

## Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Grep the whole tree for dangling references**

Run (PowerShell):
`Select-String -Path aose,tests -Recurse -Pattern 'dispatch_move|move_dispatch|inventory_dnd|data-source|data-target|/equipment/move|draggable'`
Expected: no matches. (Doc files under `docs/` may still mention DnD historically — that's fine; only `aose/` and `tests/` must be clean.)

- [ ] **Step 2: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all tests pass (the count drops by 11 vs. before: 8 from `test_containers.py` + 3 from `test_equip_enforcement.py`). Ignore the trailing `pytest-current` `PermissionError`.

- [ ] **Step 3: Smoke-test the running app (manual)**

Start: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
Open a character sheet with a container, confirm: the collapse ▾ toggle still expands/collapses container contents; Stow (dropdown + button), Take Out, Stash/Unstash, and Equip/Unequip all still work; no console errors about a missing `/move` endpoint or `inventory_dnd.js`.

- [ ] **Step 4: Update CLAUDE.md**

In `CLAUDE.md`, the container-items bullet currently ends with a description of drag-and-drop (the `/move` dispatcher, `inventory_dnd.js`, "vanilla HTML5 DnD"). Update that sentence to reflect that moves are now button/dropdown-only and DnD was removed on 2026-06-02. Keep it to one or two sentences; do not rewrite the rest of the bullet.

- [ ] **Step 5: Commit the doc update**

```bash
git add CLAUDE.md
git commit -m "docs: note inventory drag-and-drop removal"
```

---

## Self-Review

**Spec coverage:**
- Delete `move_dispatch.py` → Task 1 ✓
- Remove `/move` route + import in `routes.py` → Task 1 ✓
- Remove `/move` route + import in `wizard.py` → Task 1 ✓
- Strip drag attrs from `_equipment_ui.html` → Task 3 ✓
- Rename JS to collapse-only → Task 2 ✓
- Remove drag CSS → Task 4 ✓
- Delete DnD tests (containers + equip_enforcement) → Tasks 1 & 5 ✓
- Success criteria (no dangling refs, collapse works, suite passes) → Task 6 ✓

**Placeholder scan:** No TBD/TODO; every code step shows exact content. ✓

**Type consistency:** No new types or signatures introduced — deletion only. The collapse JS keeps the exact class/attribute names (`.container-toggle`, `tr.container-row`, `tr.container-child`, `data-instance-id`, `.container-collapsed`) used by the template. ✓
