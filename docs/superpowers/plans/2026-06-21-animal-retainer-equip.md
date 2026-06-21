# Animal & Retainer Equip/Unequip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the live-sheet inventory box equip/unequip gear for animals (barding) and retainers (weapons/armour), and show a modal when their equipped items are clicked.

**Architecture:** Three thin FastAPI routes wrap existing engine functions (`equip.equip`, `equip.unequip`, `companions.clear_armor`). The Jinja `item_modal` macro and `inv_row_actions` macro are reused with retainer/animal URL prefixes — no new modal markup logic, no engine or model changes.

**Tech Stack:** Python 3, FastAPI, Jinja2, Pydantic v2, pytest + FastAPI TestClient.

---

## Reference: how the existing pieces fit

- `aose/sheet/view.py::build_inventory_groups` already emits a `TopLevelGroup` per
  retainer (kind `"retainer"`, `id`=retainer id, `equipped`=rows from
  `retainer.spec.equipped.values()`, `loose`=loose inventory rows) and per animal
  (kind `"animal"`, `id`=instance id, `equipped`=`[barding row]` when `armor_id` set).
- `aose/web/templates/_inv_pane.html` renders each group; equipped rows are only
  made `clickable` when `group.kind == "carried"`.
- `aose/web/templates/sheet.html` defines the `item_modal(row, state, id_prefix,
  url_prefix, ...)` macro (lines ~8-39). For `state == "equipped"` the embedded
  `inv_row_actions` macro renders an Unequip button posting to `{url_prefix}/unequip`;
  for `state == "carried"` it renders an Equip button posting to `{url_prefix}/equip`.
- `aose/web/templates/_inv_row_actions.html` has branches for `equipped`, `carried`,
  `stashed` — but none for `retainer`.
- Retainer routes live in `aose/web/routes.py` under the `# ── Retainer routes ──`
  banner (~line 1865). `_equip` / `_unequip` are imported at top of routes.py as
  `from aose.engine.equip import WieldError, equip as _equip, unequip as _unequip`.
- Animal armor route `POST /character/{id}/animal/{inst_id}/armor` already exists and
  calls `companions_engine.clear_armor` when `armor_id == ""`.

Known catalog ids for tests: weapon `dagger`, armour `leather_armor`, shield `shield`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/web/routes.py` | HTTP routes | Add 3 POST routes (retainer equip, retainer unequip, animal unequip) |
| `aose/web/templates/_inv_row_actions.html` | Per-row action buttons | Add `retainer` state branch |
| `aose/web/templates/_inv_pane.html` | Inventory pane rendering | Replace hardcoded `carried` clickability with computed `eq_modal_prefix` |
| `aose/web/templates/sheet.html` | Overlay modals | Add retainer/animal equipped modals; give retainer loose modals a per-retainer URL prefix and `retainer` state |
| `tests/test_retainer_routes.py` | Retainer route tests | Add equip/unequip tests |
| `tests/test_companion_routes.py` | Animal route tests | Add animal unequip test |

---

## Task 1: Retainer equip route

**Files:**
- Modify: `aose/web/routes.py` (Retainer routes section, after the `retainer_take` route ~line 1984)
- Test: `tests/test_retainer_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retainer_routes.py`:

```python
def _save_char_with_retainer(client) -> tuple[str, str]:
    """PC with one fighter retainer holding a loose dagger. Returns (cid, ret_id)."""
    from aose.engine import retainers as retainers_engine
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    pc = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
    )
    ret = retainers_engine.generate_retainer(
        name="Sten", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=data)
    ret.spec.equipped = {}
    ret.spec.inventory = ["dagger"]
    pc.retainers = [ret]
    save_character("boss", pc, client._characters_dir)
    return "boss", ret.id


def test_retainer_equip_route(client):
    cid, rid = _save_char_with_retainer(client)
    resp = client.post(f"/character/{cid}/retainer/{rid}/equip",
                       data={"item_id": "dagger"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert spec.retainers[0].spec.equipped.get("main_hand") == "dagger"


def test_retainer_equip_missing_item_400(client):
    cid, rid = _save_char_with_retainer(client)
    resp = client.post(f"/character/{cid}/retainer/{rid}/equip",
                       data={"item_id": "nonexistent"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py::test_retainer_equip_route tests/test_retainer_routes.py::test_retainer_equip_missing_item_400 -q`
Expected: FAIL — 404 (route not found) instead of 303/400.

- [ ] **Step 3: Add the route**

In `aose/web/routes.py`, after the `retainer_take` route, add:

```python
@router.post("/character/{character_id}/retainer/{retainer_id}/equip")
async def retainer_equip(request: Request, character_id: str, retainer_id: str,
                         item_id: str = Form(...),
                         slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    ret = next((r for r in spec.retainers if r.id == retainer_id), None)
    if ret is None:
        raise HTTPException(404, "No such retainer")
    try:
        ret.spec.equipped = _equip(
            item_id,
            inventory=ret.spec.inventory, equipped=ret.spec.equipped,
            enchanted=ret.spec.enchanted, data=data,
            slot=slot,
            two_weapon=ret.spec.ruleset.two_weapon_fighting,
        )
    except (ValueError, WieldError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

Note: retainer equip intentionally omits `allowed_weapons`/`allowed_armor` (NPCs —
DM controls gear), matching the spec decision.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py::test_retainer_equip_route tests/test_retainer_routes.py::test_retainer_equip_missing_item_400 -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_retainer_routes.py
git commit -m "feat(retainers): equip route reusing PC equip engine"
```

---

## Task 2: Retainer unequip route

**Files:**
- Modify: `aose/web/routes.py` (after the `retainer_equip` route from Task 1)
- Test: `tests/test_retainer_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_retainer_routes.py`:

```python
def test_retainer_unequip_route(client):
    cid, rid = _save_char_with_retainer(client)
    client.post(f"/character/{cid}/retainer/{rid}/equip", data={"item_id": "dagger"})
    resp = client.post(f"/character/{cid}/retainer/{rid}/unequip",
                       data={"item_id": "dagger"})
    assert resp.status_code == 303
    spec = load_character(cid, client._characters_dir)
    assert "dagger" not in spec.retainers[0].spec.equipped.values()
    assert "dagger" in spec.retainers[0].spec.inventory
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py::test_retainer_unequip_route -q`
Expected: FAIL — 404 on the unequip POST.

- [ ] **Step 3: Add the route**

In `aose/web/routes.py`, after `retainer_equip`, add:

```python
@router.post("/character/{character_id}/retainer/{retainer_id}/unequip")
async def retainer_unequip(request: Request, character_id: str, retainer_id: str,
                           item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    ret = next((r for r in spec.retainers if r.id == retainer_id), None)
    if ret is None:
        raise HTTPException(404, "No such retainer")
    try:
        ret.spec.equipped = _unequip(item_id, equipped=ret.spec.equipped)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py::test_retainer_unequip_route -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_retainer_routes.py
git commit -m "feat(retainers): unequip route"
```

---

## Task 3: Animal unequip route

**Files:**
- Modify: `aose/web/routes.py` (after the existing `animal_armor` route ~line 1741)
- Test: `tests/test_companion_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_companion_routes.py`:

```python
def test_animal_unequip_returns_barding_to_inventory(client):
    animals = [AnimalInstance(instance_id="a1", catalog_id="war_horse",
                              armor_id="horse_barding")]
    _save_char(client, animals=animals)
    resp = client.post("/character/finn/animal/a1/unequip")
    assert resp.status_code == 303
    spec = load_character("finn", client._characters_dir)
    assert spec.animals[0].armor_id is None
    assert "horse_barding" in spec.inventory
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py::test_animal_unequip_returns_barding_to_inventory -q`
Expected: FAIL — 404 on the unequip POST.

- [ ] **Step 3: Add the route**

In `aose/web/routes.py`, directly after the `animal_armor` route, add:

```python
@router.post("/character/{character_id}/animal/{instance_id}/unequip")
async def animal_unequip(request: Request, character_id: str, instance_id: str):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.animals = companions_engine.clear_armor(
            spec.inventory, spec.animals, instance_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_companion_routes.py::test_animal_unequip_returns_barding_to_inventory -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_companion_routes.py
git commit -m "feat(animals): unequip route wrapping clear_armor"
```

---

## Task 4: `retainer` branch in `_inv_row_actions.html`

**Files:**
- Modify: `aose/web/templates/_inv_row_actions.html`

This adds the Equip button used by the retainer loose-item modal (wired up in Task 6).

- [ ] **Step 1: Add the branch**

In `aose/web/templates/_inv_row_actions.html`, the macro has an `{% if state == "equipped" %}` … `{% elif state == "stashed" %}` chain. Add a new `elif` for `retainer` before the final `{% endif %}` of that chain (i.e. after the `stashed` branch, lines ~27-31):

Change:

```jinja
    {% elif state == "stashed" %}
    <form method="post" action="{{ target_url_prefix }}/unstash" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit">Unstash</button>
    </form>
    {% endif %}
```

to:

```jinja
    {% elif state == "stashed" %}
    <form method="post" action="{{ target_url_prefix }}/unstash" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit">Unstash</button>
    </form>
    {% elif state == "retainer" and row.equippable %}
    <form method="post" action="{{ target_url_prefix }}/equip" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit">Equip</button>
    </form>
    {% endif %}
```

Note: retainer equip auto-detects the slot (PC logic), so no off-hand picker is shown.
The `inv_move_groups` block below this chain is unaffected (it is only rendered when
`inv_move_groups is defined`, which the retainer modal does not pass).

- [ ] **Step 2: Verify template parses**

Run: `.venv\Scripts\python.exe -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('aose/web/templates')).get_template('_inv_row_actions.html')"`
Expected: no output, exit 0 (template compiles).

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html
git commit -m "feat(inventory): retainer equip action in row-actions macro"
```

---

## Task 5: Computed `eq_modal_prefix` in `_inv_pane.html`

**Files:**
- Modify: `aose/web/templates/_inv_pane.html`

Make equipped attack/worn rows clickable for retainer and animal groups (not just carried).

- [ ] **Step 1: Introduce the prefix variable**

In `aose/web/templates/_inv_pane.html`, immediately inside the macro body (after the
`{% macro inv_pane(...) %}` line and the existing `{%- set n_items ... -%}` block, before
the `<details ...>` element), add:

```jinja
{%- if group.kind == "carried" -%}{%- set eq_modal_prefix = "equipped" -%}
{%- elif group.kind == "retainer" -%}{%- set eq_modal_prefix = "retainer-" ~ group.id ~ "-eq" -%}
{%- elif group.kind == "animal" -%}{%- set eq_modal_prefix = "animal-" ~ group.id ~ "-eq" -%}
{%- else -%}{%- set eq_modal_prefix = "" -%}
{%- endif -%}
```

- [ ] **Step 2: Use the prefix for equipped-attack rows**

Replace the equipped-attack `<li>` opening tag (currently):

```jinja
      <li{% if atk.manageable_item_id and group.kind == "carried" %} class="clickable" data-modal="modal-item-equipped-{{ atk.manageable_item_id }}"{% endif %}>
```

with:

```jinja
      <li{% if atk.manageable_item_id and eq_modal_prefix %} class="clickable" data-modal="modal-item-{{ eq_modal_prefix }}-{{ atk.manageable_item_id }}"{% endif %}>
```

- [ ] **Step 3: Use the prefix for equipped-worn rows**

Replace the equipped-worn `<li>` opening tag (currently):

```jinja
      <li{% if e.item_id and group.kind == "carried" %} class="clickable" data-modal="modal-item-equipped-{{ e.item_id }}"{% endif %}>
```

with:

```jinja
      <li{% if e.item_id and eq_modal_prefix %} class="clickable" data-modal="modal-item-{{ eq_modal_prefix }}-{{ e.item_id }}"{% endif %}>
```

- [ ] **Step 4: Verify template parses**

Run: `.venv\Scripts\python.exe -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('aose/web/templates')).get_template('_inv_pane.html')"`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/_inv_pane.html
git commit -m "feat(inventory): clickable equipped rows for retainer & animal panes"
```

---

## Task 6: Equipped & loose modals in `sheet.html`

**Files:**
- Modify: `aose/web/templates/sheet.html`

Render the modals that the pane rows from Task 5 target, and fix the retainer loose
modals' URL prefix so the Task 4 Equip button posts to the retainer.

- [ ] **Step 1: Split the existing non-PC loose-modal block**

In `aose/web/templates/sheet.html`, find this block (~lines 955-958):

```jinja
{# MODALS: loose-item modals for animal / vehicle / retainer inventories #}
{% for group in sheet.inventory_groups %}{% if group.kind in ("animal","vehicle","retainer") %}
{% for row in group.loose %}{{ item_modal(row, group.kind, group.kind ~ "-" ~ group.id, target_url_prefix, src_id=group.id) }}{% endfor %}
{% endif %}{% endfor %}
```

Replace it with (animals/vehicles keep the PC `target_url_prefix`; retainers get their
own URL prefix and the `retainer` state so the Equip button works):

```jinja
{# MODALS: loose-item modals for animal / vehicle inventories (PC-side move actions) #}
{% for group in sheet.inventory_groups %}{% if group.kind in ("animal","vehicle") %}
{% for row in group.loose %}{{ item_modal(row, group.kind, group.kind ~ "-" ~ group.id, target_url_prefix, src_id=group.id) }}{% endfor %}
{% endif %}{% endfor %}

{# MODALS: loose-item modals for retainer inventories — per-retainer URL prefix so
   the Equip action targets the retainer's equip route #}
{% for group in sheet.inventory_groups %}{% if group.kind == "retainer" %}
{%- set ret_url = "/character/" ~ character_id ~ "/retainer/" ~ group.id -%}
{% for row in group.loose %}{{ item_modal(row, "retainer", "retainer-" ~ group.id, ret_url, src_id=group.id) }}{% endfor %}
{% endif %}{% endfor %}
```

- [ ] **Step 2: Add equipped-item modals for retainers and animals**

Immediately after the block from Step 1, add:

```jinja
{# MODALS: equipped-item modals for retainers (Unequip → retainer unequip route) #}
{% for group in sheet.inventory_groups %}{% if group.kind == "retainer" %}
{%- set ret_url = "/character/" ~ character_id ~ "/retainer/" ~ group.id -%}
{% for row in group.equipped %}{{ item_modal(row, "equipped", "retainer-" ~ group.id ~ "-eq", ret_url, src_id=group.id) }}{% endfor %}
{% endif %}{% endfor %}

{# MODALS: equipped-barding modals for animals (Unequip → animal unequip route) #}
{% for group in sheet.inventory_groups %}{% if group.kind == "animal" %}
{%- set animal_url = "/character/" ~ character_id ~ "/animal/" ~ group.id -%}
{% for row in group.equipped %}{{ item_modal(row, "equipped", "animal-" ~ group.id ~ "-eq", animal_url, src_id=group.id) }}{% endfor %}
{% endif %}{% endfor %}
```

These ids exactly match what `_inv_pane.html` produces:
`modal-item-retainer-{id}-eq-{item_id}` and `modal-item-animal-{id}-eq-{item_id}`.
For `state == "equipped"`, `inv_row_actions` renders an Unequip button posting to
`{url}/unequip` — i.e. the routes from Tasks 2 and 3.

- [ ] **Step 3: Verify template parses**

Run: `.venv\Scripts\python.exe -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('aose/web/templates')).get_template('sheet.html')"`
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat(inventory): equipped & loose modals for retainers and animals"
```

---

## Task 7: End-to-end render verification

**Files:**
- Test: `tests/test_retainer_routes.py`

A full-page render test proving the modals and clickable rows appear in the HTML, so a
future template regression is caught without manual checking.

- [ ] **Step 1: Write the test**

Append to `tests/test_retainer_routes.py`:

```python
def test_sheet_renders_retainer_equip_modals(client):
    cid, rid = _save_char_with_retainer(client)
    # equip the dagger so there is both an equipped row and (no) loose dagger
    client.post(f"/character/{cid}/retainer/{rid}/equip", data={"item_id": "dagger"})
    resp = client.get(f"/character/{cid}")
    assert resp.status_code == 200
    html = resp.text
    # equipped-item modal id present
    assert f"modal-item-retainer-{rid}-eq-dagger" in html
    # unequip action targets the retainer route
    assert f"/character/{cid}/retainer/{rid}/unequip" in html


def test_sheet_renders_animal_barding_modal(client):
    from aose.models import AnimalInstance
    pc = CharacterSpec(
        name="Boss",
        abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 13},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=3, hp_rolls=[8, 8, 8])],
        alignment="neutral",
        animals=[AnimalInstance(instance_id="a1", catalog_id="war_horse",
                                armor_id="horse_barding")],
    )
    save_character("boss", pc, client._characters_dir)
    resp = client.get("/character/boss")
    assert resp.status_code == 200
    assert "modal-item-animal-a1-eq-horse_barding" in resp.text
    assert "/character/boss/animal/a1/unequip" in resp.text
```

- [ ] **Step 2: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_retainer_routes.py::test_sheet_renders_retainer_equip_modals tests/test_retainer_routes.py::test_sheet_renders_animal_barding_modal -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_retainer_routes.py
git commit -m "test(inventory): end-to-end render of retainer/animal equip modals"
```

---

## Task 8: Full suite + docs

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ARCHITECTURE.md` (companions/retainers subsystem section, edit in place)

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all pass (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

- [ ] **Step 2: Update CHANGELOG**

Add a one-line row to the top of `docs/CHANGELOG.md`:

```
| 2026-06-21 | Animal/retainer equip-unequip + click-to-modal in inventory box | main | 2026-06-21-animal-retainer-equip |
```

(Match the existing column format in that file — open it first and mirror the header row.)

- [ ] **Step 3: Update ARCHITECTURE.md**

Find the companions/retainers subsystem section in `docs/ARCHITECTURE.md` and edit in
place to note that retainer gear and animal barding are now equippable/unequippable from
the live-sheet inventory panes via `/retainer/{id}/equip|unequip` and
`/animal/{id}/unequip`, reusing the PC `equip.equip`/`equip.unequip` engine and the
`item_modal`/`inv_row_actions` templates. Do not append a dated entry — edit the topic.

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: animal/retainer equip-unequip landing notes"
```

---

## Self-Review notes

- **Spec coverage:** 3 routes (Tasks 1-3), `_inv_row_actions` retainer branch (Task 4),
  `_inv_pane` eq_modal_prefix (Task 5), sheet.html equipped + loose modals (Task 6).
  All four spec "Files changed" rows are covered, plus render test (Task 7) and docs (Task 8).
- **Type consistency:** modal id `modal-item-{eq_modal_prefix}-{item_id}` in Task 5 matches
  `item_modal(row, "equipped", "retainer-{id}-eq" | "animal-{id}-eq", ...)` in Task 6
  (the macro emits `modal-item-{id_prefix}-{row.id}`). Retainer loose modal prefix
  `"retainer-" ~ group.id` (Task 6) matches `_inv_pane.html` loose row target
  `modal-item-{prefix}-{row.id}` where prefix is `group.kind ~ "-" ~ group.id` =
  `retainer-{id}`. Consistent.
- **Edge case (documented in spec):** if a retainer wields the same catalog item in two
  slots, two identical equipped modal ids are emitted; the browser uses the first.
  Acceptable for NPCs.
