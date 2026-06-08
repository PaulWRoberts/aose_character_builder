# Inventory Item Modals + Shop Property Expander Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every inventory entry on the character sheet open a modal showing its properties + description plus its *safe* management actions (equip/move/load/use-charge/adjust), keep destructive actions (drop/sell/refund) drawer-only, and give the shop the same property expander the management drawer's inventory rows already have.

**Architecture:** Pure view/template change. Reuse the existing `DetailCard` / `item_card()` / `detail_card()` machinery (already shared by `aose/engine/shop.py` and `aose/sheet/view.py` via `aose/engine/detail.py`). Add a `detail` field to three view models (`ShopItem`, `ContainerView`, `AmmoRow`), thread a `show_remove` flag through one macro, and enrich/add server-rendered overlays in `sheet.html`. No new routes, persistence shapes, or engine modules.

**Tech Stack:** Python 3 · FastAPI · Jinja2 · Pydantic v2 · pytest (FastAPI `TestClient`). Run from the project venv.

---

## Background the engineer needs

- **Run the app:** `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload` (the bare `uvicorn` won't work — the venv isn't auto-activated).
- **Run tests:** `.venv\Scripts\python.exe -m pytest tests/ -q`. A trailing `PermissionError` on `pytest-current` is a known Windows-tempdir quirk in pytest 9 — ignore it.
- **The sheet page renders BOTH the per-item modals AND the management drawer** (`drawer-equip`, which `{% include "_equipment_ui.html" %}`). The drawer legitimately keeps Drop/Sell/Refund. Therefore a test asserting "no destructive actions on a sheet modal" **must slice out just that modal's HTML** — never scan the whole page body. A shared helper `_modal_html(body, modal_id)` is introduced in Task 1 for this.
- **The `item_modal` macro** is defined inline at the top of `sheet.html` (lines 6–14) and is called in three loops near the bottom (lines 743–745) for `carried` / `stashed` / `equipped` rows.
- **`detail_card(card)`** (in `_detail_card.html`, imported `with context` in `sheet.html` at line 5) renders `card.stats` as a `<dl>` and `card.description` through `| markdown | safe`. Passing a row's `.detail` (a `DetailCard` from `item_card()`) gives **properties + markdown description** in one call.
- **`inv_row_actions(row, target_url_prefix, state)`** (in `_inv_row_actions.html`, imported `with context`) renders equip/unequip, stow, stash/unstash, and the Drop/Sell/Refund form. It reads `inventory_view` from context (for the stow dropdown).
- **URL-prefix context already available in `sheet.html`:** `target_url_prefix` = `/character/{id}/equipment` (equip/unequip/stash/unstash/stow/equip-magic/unequip-magic/use-charge/equip-enchanted/unequip-enchanted/enchanted/use-charge), `ammo_url_prefix` = `/character/{id}` (ammo/adjust, ammo/load, ammo/unload), plus `ammo_load_options`, `enchanted_rows`, `sheet`, `character_id`.
- **Ammo loading keys line up:** `AttackProfile.manageable_item_id` (which keys the equipped modals) and the keys of `sheet.ammo_load_options` are both the plain catalog weapon id. `ammo_load_options[weapon_id]` is a `list[AmmoOption]` (`.instance_id`, `.name`, `.count`). The load form posts `weapon_key` + `instance_id` to `{{ ammo_url_prefix }}/ammo/load`; unload posts `weapon_key` to `{{ ammo_url_prefix }}/ammo/unload`.

## File-by-file responsibility map

| File | Change | Responsibility |
|---|---|---|
| `aose/web/templates/_inv_row_actions.html` | Modify | Add `show_remove=True` param; gate the Drop/Sell/Refund form on it. |
| `aose/web/templates/sheet.html` | Modify | Enrich `item_modal` (properties + `show_remove=False`); add launcher load block, magic-item modals, container modals, ammo modals; make those entries clickable. |
| `aose/engine/shop.py` | Modify | Add `detail` to `ShopItem` + `ContainerView`; populate via `item_card()`. |
| `aose/sheet/view.py` | Modify | Add `detail` to `AmmoRow`; populate in `ammo_view`. |
| `aose/web/templates/_equipment_ui.html` | Modify | Shop rows become `data-detail-toggle` triggers with a `row-detail` expander rendering `detail_card(item.detail)`. |
| `tests/test_equip_attacks.py` | Modify | Update the now-stale carried-modal comment; add modal/property/launcher tests + `_modal_html` helper. |
| `tests/test_web.py` | Modify | Add shop-expander, container-modal, ammo-modal, magic-item-modal tests. |
| `tests/test_magic_items.py` | Modify | Add explicit guard: `use_charge` to 0 keeps the instance in the list. |
| `docs/CHANGELOG.md` | Modify | One-line landing row. |
| `docs/ARCHITECTURE.md` | Modify | Update the inventory/sheet subsystem section in place. |

---

### Task 1: `show_remove` flag + enriched sheet item modal

Make the sheet's per-item modal show structured properties (not just raw description) and drop the destructive Drop/Sell/Refund actions, keeping them in the management drawer.

**Files:**
- Modify: `aose/web/templates/_inv_row_actions.html`
- Modify: `aose/web/templates/sheet.html:6-14` (the `item_modal` macro)
- Modify/Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Add the `_modal_html` helper + write the failing test**

Add this helper near the top of `tests/test_equip_attacks.py` (after the imports, before the first test):

```python
def _modal_html(body: str, modal_id: str) -> str:
    """Return just the HTML of the overlay whose id is `modal_id`.

    The sheet renders per-item modals AND the management drawer (which keeps
    Drop/Sell/Refund), so destructive-action assertions must be scoped to a
    single modal, not the whole page."""
    start = body.index(f'id="{modal_id}"')
    nxt = body.find('class="overlay', start + 10)
    return body[start:nxt if nxt != -1 else len(body)]
```

Then add the test:

```python
def test_sheet_item_modal_shows_properties_and_no_destructive_actions(tmp_path, data):
    from aose.characters import save_character
    client = _make_client(tmp_path)
    spec = CharacterSpec(
        name="Modal",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        inventory=["sword"], equipped_weapons=["sword"],
    )
    save_character("modal", spec, client._characters_dir)
    body = client.get("/character/modal").text

    modal = _modal_html(body, "modal-item-equipped-sword")
    # Properties from item_card() (detail_card stats) are present.
    assert "Damage" in modal
    assert "Weight" in modal
    # Safe management action present...
    assert "/character/modal/equipment/unequip" in modal
    # ...but destructive shop actions are NOT in the modal.
    assert 'value="drop"' not in modal
    assert 'value="sell"' not in modal
    assert 'value="refund"' not in modal
    # The management drawer (whole page) still offers them.
    assert 'value="sell"' in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_sheet_item_modal_shows_properties_and_no_destructive_actions -q`
Expected: FAIL — the modal currently renders `value="sell"` (the macro includes the remove form) and shows raw description, not the `Damage`/`Weight` stat labels.

- [ ] **Step 3: Add `show_remove` to `inv_row_actions`**

In `aose/web/templates/_inv_row_actions.html`, change the macro signature and gate the remove form. The macro currently starts:

```jinja
{% macro inv_row_actions(row, target_url_prefix, state) %}
```

Change it to:

```jinja
{% macro inv_row_actions(row, target_url_prefix, state, show_remove=True) %}
```

Then wrap the final remove form (the `<form ... action="{{ target_url_prefix }}/remove" class="remove-form">` block, currently lines 42–53) in a `{% if show_remove %}` … `{% endif %}`:

```jinja
    {% if show_remove %}
    <form method="post" action="{{ target_url_prefix }}/remove" class="remove-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <input type="hidden" name="from_state" value="{{ state }}">
        <button type="submit" name="mode" value="drop"
                title="Throw away — no gold back">Drop</button>
        <button type="submit" name="mode" value="sell"
                title="Sell one for half its per-item price">Sell&nbsp;(+{{ row.sell_gp }}&nbsp;gp)</button>
        {% if row.can_refund %}
        <button type="submit" name="mode" value="refund"
                title="Refund a full purchased stack">Refund{% if row.bundle_count > 1 %}&nbsp;stack&nbsp;of&nbsp;{{ row.bundle_count }}{% endif %}&nbsp;(+{{ row.cost_gp | int }}&nbsp;gp)</button>
        {% endif %}
    </form>
    {% endif %}
```

(The management drawer in `_equipment_ui.html` calls `inv_row_actions` without the flag, so it keeps the default `True` and is unchanged.)

- [ ] **Step 4: Enrich the `item_modal` macro**

In `aose/web/templates/sheet.html`, replace the `item_modal` macro body (lines 6–14):

```jinja
{% macro item_modal(row, state, id_prefix, url_prefix) %}
<div class="overlay modal" id="modal-item-{{ id_prefix }}-{{ row.id }}" role="dialog" aria-label="{{ row.name }}">
  <div class="ov-head"><h3>{{ row.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    {% if row.detail %}{{ detail_card(row.detail) }}{% elif row.description %}<div class="prose">{{ row.description | markdown | safe }}</div>{% endif %}
    <div class="row-actions">{{ inv_row_actions(row, url_prefix, state, show_remove=False) }}</div>
  </div>
</div>
{% endmacro %}
```

(`row.detail` is the `DetailCard` from `item_card()`, already populated on every `InventoryRow` by `shop._build_row`. The `elif` keeps a graceful fallback for any row lacking a detail card.)

- [ ] **Step 5: Run the new test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_sheet_item_modal_shows_properties_and_no_destructive_actions -q`
Expected: PASS.

- [ ] **Step 6: Fix the now-stale existing test comment**

The existing `test_sheet_carried_and_stashed_items_are_clickable` (around line 469) has a comment claiming the carried modal "offers Stash + Drop". Drop is now drawer-only. Update only the comment (the `/stash` and `/unstash` assertions remain valid because the drawer still renders those forms):

```python
    # Carried item modal offers Stash; stashed offers Unstash. (Drop/Sell/Refund
    # are drawer-only — see test_sheet_item_modal_shows_properties_and_no_destructive_actions.)
    assert "/character/packrat/equipment/stash" in body
    assert "/character/packrat/equipment/unstash" in body
```

- [ ] **Step 7: Run the full equip-attacks test file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -q`
Expected: PASS (all tests, including the updated comment test and the new one).

- [ ] **Step 8: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html aose/web/templates/sheet.html tests/test_equip_attacks.py
git commit -m "feat(sheet): item modal shows properties; drop destructive actions to drawer"
```

---

### Task 2: Ranged weapons load ammo from their modal

When an equipped weapon accepts ammo, its modal shows the current load (or an "Unloaded" badge) plus Load `<select>`+button and an Unload button, reusing the existing `/ammo/load` & `/ammo/unload` routes.

**Files:**
- Modify: `aose/web/templates/sheet.html` (the `item_modal` macro + the equipped-modal call loop, line 745)
- Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_equip_attacks.py`:

```python
def test_equipped_launcher_modal_has_load_control(tmp_path, data):
    from aose.characters import save_character
    from aose.models import AmmoStack
    client = _make_client(tmp_path)
    spec = CharacterSpec(
        name="Archer",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 13, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        inventory=["short_bow"], equipped_weapons=["short_bow"],
        ammo=[AmmoStack(instance_id="q1", base_id="arrow", count=20)],
    )
    save_character("archer", spec, client._characters_dir)
    body = client.get("/character/archer").text

    modal = _modal_html(body, "modal-item-equipped-short_bow")
    # Load control: posts to the ammo/load route with the weapon key + a stack option.
    assert "/character/archer/ammo/load" in modal
    assert 'name="weapon_key" value="short_bow"' in modal
    assert 'value="q1"' in modal          # the loadable stack instance
    assert "/character/archer/ammo/unload" in modal
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_equipped_launcher_modal_has_load_control -q`
Expected: FAIL — the equipped modal has no load control yet.

- [ ] **Step 3: Add a `launcher` block to the `item_modal` macro**

Give the macro two optional args (`load_options`, `attack`) and render the ammo block when present. Replace the macro from Task 1 with:

```jinja
{% macro item_modal(row, state, id_prefix, url_prefix, load_options=none, attack=none) %}
<div class="overlay modal" id="modal-item-{{ id_prefix }}-{{ row.id }}" role="dialog" aria-label="{{ row.name }}">
  <div class="ov-head"><h3>{{ row.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    {% if row.detail %}{{ detail_card(row.detail) }}{% elif row.description %}<div class="prose">{{ row.description | markdown | safe }}</div>{% endif %}
    {% if load_options %}
    <div class="ov-section">
      <h4>Ammunition</h4>
      <p class="muted small" style="margin:0 0 6px">
        {% if attack and attack.unloaded %}<span class="tag stamp">Unloaded</span>
        {% elif attack and attack.loaded_ammo_name %}Loaded: <strong>{{ attack.loaded_ammo_name }}</strong>
        {% else %}<span class="tag stamp">Unloaded</span>{% endif %}
      </p>
      <form method="post" action="{{ ammo_url_prefix }}/ammo/load" class="inline-form">
        <input type="hidden" name="weapon_key" value="{{ row.id }}">
        <select name="instance_id">
          {% for opt in load_options %}
          <option value="{{ opt.instance_id }}">{{ opt.name }} ({{ opt.count }})</option>
          {% endfor %}
        </select>
        <button class="btn" type="submit">Load</button>
      </form>
      <form method="post" action="{{ ammo_url_prefix }}/ammo/unload" class="inline-form">
        <input type="hidden" name="weapon_key" value="{{ row.id }}">
        <button class="btn link" type="submit">Unload</button>
      </form>
    </div>
    {% endif %}
    <div class="row-actions">{{ inv_row_actions(row, url_prefix, state, show_remove=False) }}</div>
  </div>
</div>
{% endmacro %}
```

(`ammo_url_prefix` is in the sheet's render context and is accessible from the call site that passes `load_options`. The macro references it; if a future context lacks it, only launcher modals — which only the sheet renders — use it.)

- [ ] **Step 4: Pass load options from the equipped-modal loop**

In `sheet.html`, the equipped per-item modals are generated at line 745:

```jinja
{% for row in inventory_view.equipped %}{{ item_modal(row, "equipped", "equipped", target_url_prefix) }}{% endfor %}
```

Replace that single line with:

```jinja
{% for row in inventory_view.equipped %}
{%- set lo = ammo_load_options.get(row.id) -%}
{%- set atk = sheet.attacks | selectattr('manageable_item_id', 'equalto', row.id) | first -%}
{{ item_modal(row, "equipped", "equipped", target_url_prefix, load_options=lo, attack=atk) }}
{% endfor %}
```

(`ammo_load_options` and `sheet` are top-level render-context variables, so referencing them at the call site is safe. `selectattr(...) | first` yields the matching `AttackProfile` or an `Undefined` that the macro's `{% if attack ... %}` guards treat as falsy.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_equipped_launcher_modal_has_load_control -q`
Expected: PASS.

- [ ] **Step 6: Run the full equip-attacks test file (regression)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/sheet.html tests/test_equip_attacks.py
git commit -m "feat(sheet): load/unload ammo from an equipped launcher's modal"
```

---

### Task 3: Worn magic-item modal with use-charge

Replace the description-only `modal-feature` link on worn magic items with a dedicated modal showing modifier chips, markdown description, Unequip, and a Use-one charge control (disabled at 0). Routes auto-select between magic and enchanted instances.

**Files:**
- Modify: `aose/web/templates/sheet.html` (equipped-column worn-magic loop, lines 342–349; add modals near the item modals at line 745)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py`. Reuse the `_modal_html` slicing approach locally (defined inline so this file is self-contained):

```python
def test_worn_magic_item_modal_has_charges_and_unequip(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry, MagicItemInstance
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=Path(__file__).parent.parent / "data",
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Mage",
        abilities={"STR": 10, "INT": 12, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        magic_items=[MagicItemInstance(
            instance_id="mi1",
            catalog_id="amulet_of_protection_against_possession",
            equipped=True, charges_max=3, charges_remaining=3)],
    )
    save_character("mage", spec, characters_dir)
    body = TestClient(app, follow_redirects=False).get("/character/mage").text

    # Worn item is a clickable trigger into its own modal.
    assert 'data-modal="modal-magic-mi1"' in body
    assert 'id="modal-magic-mi1"' in body
    start = body.index('id="modal-magic-mi1"')
    nxt = body.find('class="overlay', start + 10)
    modal = body[start:nxt if nxt != -1 else len(body)]
    # Use-one charge control + count, and Unequip; no destructive remove.
    assert "/character/mage/equipment/use-charge" in modal
    assert "3 / 3" in modal
    assert "/character/mage/equipment/unequip-magic" in modal
    assert "/remove-magic" not in modal
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_worn_magic_item_modal_has_charges_and_unequip -q`
Expected: FAIL — worn magic items currently link to `modal-feature`; there is no `modal-magic-mi1`.

- [ ] **Step 3: Make worn magic items trigger their own modal**

In `sheet.html`, the equipped column renders worn magic items (lines 342–349). Replace that loop body:

```jinja
            {# Worn magic items #}
            {% for mi in sheet.magic_items %}
            {% if mi.equipped %}
            <li class="info clickable" data-modal="modal-magic-{{ mi.instance_id }}">
              <span>{{ mi.name }} <span class="tag stamp">magic</span></span>
              <span class="st">{% for chip in mi.modifier_summary %}{{ chip }}{% if not loop.last %}, {% endif %}{% endfor %}</span>
            </li>
            {% endif %}
            {% endfor %}
```

- [ ] **Step 4: Add the per-instance magic-item modals**

In `sheet.html`, immediately after the three item-modal loops (line 745, right after the `{% for row in inventory_view.equipped %}…{% endfor %}` block from Task 2), add:

```jinja
{# MODALS: per-worn-magic-item (properties + unequip + use-charge) #}
{% set ench_ids = enchanted_rows | map(attribute='instance_id') | list %}
{% for mi in sheet.magic_items %}{% if mi.equipped %}
{% set is_ench = mi.instance_id in ench_ids %}
<div class="overlay modal" id="modal-magic-{{ mi.instance_id }}" role="dialog" aria-label="{{ mi.name }}">
  <div class="ov-head"><h3>{{ mi.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    {% if mi.modifier_summary %}<p style="margin:0 0 8px">{% for chip in mi.modifier_summary %}<span class="tag stamp">{{ chip }}</span> {% endfor %}</p>{% endif %}
    {% if mi.description %}<div class="prose">{{ mi.description | markdown | safe }}</div>{% endif %}
    <div class="row-actions">
      <form method="post" action="{{ target_url_prefix }}/{{ 'unequip-enchanted' if is_ench else 'unequip-magic' }}" class="inline-form">
        <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
        <button type="submit">Unequip</button>
      </form>
      {% if mi.charges_remaining is not none %}
      <span class="muted small">Charges {{ mi.charges_remaining }} / {{ mi.charges_max }}</span>
      <form method="post" action="{{ target_url_prefix }}/{{ 'enchanted/use-charge' if is_ench else 'use-charge' }}" class="inline-form">
        <input type="hidden" name="instance_id" value="{{ mi.instance_id }}">
        <button type="submit" {% if mi.charges_remaining == 0 %}disabled{% endif %}>Use one</button>
      </form>
      {% endif %}
    </div>
  </div>
</div>
{% endif %}{% endfor %}
```

(`enchanted_rows` is in the sheet's render context. `is_ench` routes enchanted instances to `/unequip-enchanted` + `/enchanted/use-charge` and plain magic instances to `/unequip-magic` + `/use-charge`. Charge **reset**, note, and remove stay in the drawer.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_worn_magic_item_modal_has_charges_and_unequip -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/sheet.html tests/test_web.py
git commit -m "feat(sheet): worn magic-item modal with use-charge + unequip"
```

---

### Task 4: Container modal

Make carried/stashed bags clickable into a modal showing the live capacity badge, the container's catalog detail card, and Stash/Unstash.

**Files:**
- Modify: `aose/engine/shop.py` (`ContainerView` + `inventory_view`)
- Modify: `aose/web/templates/sheet.html` (bag `<li>`s in carried/stashed columns; add container modals)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py`:

```python
def test_container_modal_shows_capacity_and_stash(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry, ContainerInstance
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=Path(__file__).parent.parent / "data",
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Bagger",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        containers=[ContainerInstance(instance_id="b1", catalog_id="backpack", state="carried")],
    )
    save_character("bagger", spec, characters_dir)
    body = TestClient(app, follow_redirects=False).get("/character/bagger").text

    assert 'data-modal="modal-container-b1"' in body
    assert 'id="modal-container-b1"' in body
    start = body.index('id="modal-container-b1"')
    nxt = body.find('class="overlay', start + 10)
    modal = body[start:nxt if nxt != -1 else len(body)]
    assert "Capacity" in modal                                  # from item_card stats
    assert "/character/bagger/equipment/stash-container" in modal
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_container_modal_shows_capacity_and_stash -q`
Expected: FAIL — there is no `modal-container-b1`.

- [ ] **Step 3: Add `detail` to `ContainerView` and populate it**

In `aose/engine/shop.py`, add a field to `ContainerView` (after `contents`, around line 68):

```python
    contents: list[InventoryRow]
    detail: DetailCard | None = None   # catalog item card for the per-container modal
```

In `inventory_view`, the container-build loop already fetches `catalog` (line 207). Add `detail=item_card(catalog)` to the `ContainerView(...)` construction (around line 221):

```python
        container_views.append(ContainerView(
            instance_id=c.instance_id,
            catalog_id=c.catalog_id,
            name=catalog.name,
            state=c.state,
            capacity_cn=catalog.capacity_cn,
            used_cn=raw_used,
            weight_multiplier=catalog.weight_multiplier,
            own_weight_cn=catalog.weight_cn,
            effective_weight_cn=effective,
            contents=content_rows,
            detail=item_card(catalog),
        ))
```

(`item_card` and `DetailCard` are already imported at the top of `shop.py`.)

- [ ] **Step 4: Make bag rows clickable + add container modals**

In `sheet.html`, the **carried** column's container loop (around lines 361–368) renders the bag `<li>`. Make it clickable:

```jinja
            {# Carried containers #}
            {% for c in inventory_view.containers %}
            {% if c.state == "carried" %}
            <li class="bag clickable" data-modal="modal-container-{{ c.instance_id }}"><span>{{ c.name }}</span><span class="q">{{ c.total_weight_cn }} cn</span></li>
            {% if c.contents %}
            <li class="sub"><span>{% for row in c.contents %}{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}</span><span class="q">↳ {{ c.used_cn }}</span></li>
            {% endif %}
            {% endif %}
            {% endfor %}
```

In the **stashed** column's container loop (around lines 395–399):

```jinja
            {# Stashed containers #}
            {% for c in inventory_view.containers %}
            {% if c.state == "stashed" %}
            <li class="bag clickable" data-modal="modal-container-{{ c.instance_id }}"><span>{{ c.name }}</span><span class="q">—</span></li>
            {% endif %}
            {% endfor %}
```

Then add the container modals after the worn-magic-item modals from Task 3 (still near line 745):

```jinja
{# MODALS: per-container (live capacity badge + catalog card + stash/unstash) #}
{% for c in inventory_view.containers %}
<div class="overlay modal" id="modal-container-{{ c.instance_id }}" role="dialog" aria-label="{{ c.name }}">
  <div class="ov-head"><h3>{{ c.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    <p style="margin:0 0 8px">
      <span class="capacity-badge{% if c.capacity_cn and c.used_cn >= c.capacity_cn %} capacity-full{% endif %}">
        {{ c.used_cn }} / {{ c.capacity_cn if c.capacity_cn else "∞" }} cn
      </span>
    </p>
    {% if c.detail %}{{ detail_card(c.detail) }}{% endif %}
    <div class="row-actions">
      {% if c.state == "carried" %}
      <form method="post" action="{{ target_url_prefix }}/stash-container" class="inline-form">
        <input type="hidden" name="instance_id" value="{{ c.instance_id }}">
        <button type="submit" title="Move container off-person">Stash</button>
      </form>
      {% else %}
      <form method="post" action="{{ target_url_prefix }}/unstash-container" class="inline-form">
        <input type="hidden" name="instance_id" value="{{ c.instance_id }}">
        <button type="submit">Unstash</button>
      </form>
      {% endif %}
    </div>
  </div>
</div>
{% endfor %}
```

(Take-out of contents and container removal stay drawer-only.)

- [ ] **Step 5: Run the container view + web tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_container_modal_shows_capacity_and_stash tests/test_inventory_view.py -q`
Expected: PASS (the new field has a default, so existing inventory-view tests are unaffected).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/shop.py aose/web/templates/sheet.html tests/test_web.py
git commit -m "feat(sheet): container modal with capacity badge + stash/unstash"
```

---

### Task 5: Ammo modal with count adjust

Make ammo rows clickable into a modal showing the ammo's catalog properties + description and a +/- count adjuster (reusing `/ammo/adjust`). Destructive remove stays in the drawer.

**Files:**
- Modify: `aose/sheet/view.py` (`AmmoRow` + `ammo_view`)
- Modify: `aose/web/templates/sheet.html` (ammo `<li>` in carried column; add ammo modals)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py`:

```python
def test_ammo_modal_shows_properties_and_count_adjust(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry, AmmoStack
    from aose.web.app import create_app

    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=Path(__file__).parent.parent / "data",
        characters_dir=characters_dir, drafts_dir=tmp_path / "drafts",
        examples_dir=examples_dir, settings_path=tmp_path / "settings.json",
    )
    spec = CharacterSpec(
        name="Fletch",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        ammo=[AmmoStack(instance_id="a1", base_id="arrow", count=20)],
    )
    save_character("fletch", spec, characters_dir)
    body = TestClient(app, follow_redirects=False).get("/character/fletch").text

    assert 'data-modal="modal-ammo-a1"' in body
    assert 'id="modal-ammo-a1"' in body
    start = body.index('id="modal-ammo-a1"')
    nxt = body.find('class="overlay', start + 10)
    modal = body[start:nxt if nxt != -1 else len(body)]
    assert "Ammunition" in modal                     # item_card Type stat
    assert "/character/fletch/ammo/adjust" in modal   # +/- count adjust
    assert 'name="delta" value="1"' in modal
    assert 'name="delta" value="-1"' in modal
    assert "/ammo/remove" not in modal               # destructive remove stays in drawer
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ammo_modal_shows_properties_and_count_adjust -q`
Expected: FAIL — there is no `modal-ammo-a1`.

- [ ] **Step 3: Add `detail` to `AmmoRow` and populate it**

In `aose/sheet/view.py`, add to the `AmmoRow` model (after `magic`, around line 181):

```python
class AmmoRow(BaseModel):
    instance_id: str
    name: str
    count: int
    magic: bool
    detail: "DetailCard | None" = None
```

Add the import near the other engine imports at the top of `view.py` (alongside the existing `from aose.engine...` imports):

```python
from aose.engine.detail import DetailCard, item_card
```

In `ammo_view` (around lines 1010–1014), populate the detail from the base catalog item:

```python
    ammo_rows = []
    for s in spec.ammo:
        view = resolve_ammo(s, data)
        base = data.items.get(s.base_id)
        ammo_rows.append(AmmoRow(
            instance_id=s.instance_id, name=view["name"],
            count=s.count, magic=s.enchantment_id is not None,
            detail=item_card(base) if base is not None else None))
```

(If `from aose.engine.detail import DetailCard` already exists in `view.py`, don't duplicate it — keep a single import. The forward-ref quotes on the model field are harmless either way.)

- [ ] **Step 4: Make ammo rows clickable + add ammo modals**

In `sheet.html`, the carried column's ammo loop (around lines 381–383). Make the `<li>` clickable:

```jinja
            {# Ammo #}
            {% for a in sheet.ammo %}
            <li class="clickable" data-modal="modal-ammo-{{ a.instance_id }}"><span>{{ a.name }}{% if a.magic %}<span class="tag stamp">magic</span>{% endif %}</span><span class="q">× {{ a.count }}</span></li>
            {% endfor %}
```

Add the ammo modals after the container modals from Task 4 (near line 745):

```jinja
{# MODALS: per-ammo (properties + count adjust) #}
{% for a in sheet.ammo %}
<div class="overlay modal" id="modal-ammo-{{ a.instance_id }}" role="dialog" aria-label="{{ a.name }}">
  <div class="ov-head"><h3>{{ a.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    {% if a.detail %}{{ detail_card(a.detail) }}{% endif %}
    <div class="row-actions">
      <span class="muted small">Count {{ a.count }}</span>
      <form method="post" action="{{ ammo_url_prefix }}/ammo/adjust" class="inline-form">
        <input type="hidden" name="instance_id" value="{{ a.instance_id }}">
        <input type="hidden" name="delta" value="1">
        <button class="btn tool dark" type="submit">+</button>
      </form>
      <form method="post" action="{{ ammo_url_prefix }}/ammo/adjust" class="inline-form">
        <input type="hidden" name="instance_id" value="{{ a.instance_id }}">
        <input type="hidden" name="delta" value="-1">
        <button class="btn tool dark" type="submit">−</button>
      </form>
    </div>
  </div>
</div>
{% endfor %}
```

- [ ] **Step 5: Run the ammo + sheet tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_ammo_modal_shows_properties_and_count_adjust tests/test_ammunition.py tests/test_sheet.py -q`
Expected: PASS (the new `AmmoRow.detail` field has a default, so existing tests are unaffected).

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py aose/web/templates/sheet.html tests/test_web.py
git commit -m "feat(sheet): ammo modal with properties + count adjust"
```

---

### Task 6: Shop property expander

Give each shop row a `data-detail-toggle` expander (the same pattern the drawer's inventory rows use) showing the item's full `detail_card`. The existing `inventory.js` toggle already ignores clicks inside the Buy/add forms.

**Files:**
- Modify: `aose/engine/shop.py` (`ShopItem` + `shop_categories`)
- Modify: `aose/web/templates/_equipment_ui.html` (Shop pane table, lines 624–652)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py` (uses the module-level `client` fixture and the `thorin` example, whose shop lists every item including `sword`):

```python
def test_shop_rows_have_property_expander(client):
    body = client.get("/character/thorin").text
    # Every shop row is a detail-toggle trigger with a sibling detail row.
    assert 'data-detail-toggle="shop-weapons-sword"' in body
    assert 'data-detail-for="shop-weapons-sword"' in body
    # The expander renders the item's properties via detail_card.
    start = body.index('data-detail-for="shop-weapons-sword"')
    assert "Damage" in body[start:start + 400]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_shop_rows_have_property_expander -q`
Expected: FAIL — shop rows have no `data-detail-toggle`/`data-detail-for` and `ShopItem` carries no detail.

- [ ] **Step 3: Add `detail` to `ShopItem` and populate it**

In `aose/engine/shop.py`, add to the `ShopItem` model (after `bundle_count`, around line 32):

```python
class ShopItem(BaseModel):
    id: str
    name: str
    category: str
    cost_gp: float
    weight_cn: int = 0
    magic: bool = False
    bundle_count: int = 1
    detail: DetailCard | None = None
```

In `shop_categories`, populate `detail=item_card(i)` in the `ShopItem(...)` construction (around lines 108–113):

```python
                ShopItem(
                    id=i.id, name=i.name, category=i.category,
                    cost_gp=i.cost_gp, weight_cn=i.weight_cn,
                    magic=i.magic, bundle_count=_bundle_count(i),
                    detail=item_card(i),
                )
```

(`item_card` is already imported in `shop.py`.)

- [ ] **Step 4: Add the expander rows to the shop table**

In `aose/web/templates/_equipment_ui.html`, the shop table body (lines 629–650). Replace the `shop-row` `<tr>` and add a sibling detail row. The `inventory.js` row-detail toggle is delegated on document click and ignores clicks inside `form, button, a, select`, so the Buy/add controls keep working while a click elsewhere on the row toggles the expander:

```jinja
    {% for item in category.items %}
        {% set uid = "shop-" ~ category.id ~ "-" ~ item.id %}
        <tr class="shop-row {% if not item.magic and item.cost_gp > gold %}out{% endif %}"
            data-shop-name="{{ item.name | lower }}"
            data-detail-toggle="{{ uid }}" aria-expanded="false">
            <td>{{ item.name }}{% if item.bundle_count > 1 %} <span class="tag faint">buys {{ item.bundle_count }}</span>{% endif %}</td>
            <td class="n">{% if item.magic %}—{% else %}{{ item.cost_gp | int }} gp{% endif %}</td>
            <td class="n">{{ item.weight_cn }}</td>
            <td class="n">
                {% if not item.magic %}
                <form method="post" action="{{ target_url_prefix }}/buy" class="inline-form">
                    <input type="hidden" name="item_id" value="{{ item.id }}">
                    <button class="btn tool dark" type="submit"
                            {% if item.cost_gp > gold %}disabled{% endif %}>Buy</button>
                </form>
                {% endif %}
                <form method="post" action="{{ target_url_prefix }}/add" class="inline-form">
                    <input type="hidden" name="item_id" value="{{ item.id }}">
                    <button class="btn link" type="submit"
                            title="Add to inventory without spending gold">add</button>
                </form>
            </td>
        </tr>
        {% if item.detail %}
        <tr class="row-detail collapsed" data-detail-for="{{ uid }}">
            <td colspan="4">{{ detail_card(item.detail) }}</td>
        </tr>
        {% endif %}
    {% endfor %}
```

(The shop search script filters on `.shop-row`; the detail rows are hidden by `.collapsed` and aren't `.shop-row`, so search is unaffected.)

- [ ] **Step 5: Run the shop + equipment tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_shop_rows_have_property_expander tests/test_equipment.py -q`
Expected: PASS (the new `ShopItem.detail` field has a default).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/shop.py aose/web/templates/_equipment_ui.html tests/test_web.py
git commit -m "feat(shop): per-row property expander matching the inventory drawer"
```

---

### Task 7: Engine guard — using the last charge keeps the item

Lock in "using all charges shouldn't remove the item" with an explicit regression test. `magic.use_charge` already decrements to 0 without removing the instance; this test guards that behaviour.

**Files:**
- Test: `tests/test_magic_items.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_magic_items.py`:

```python
def test_use_charge_to_zero_keeps_item_in_list():
    from aose.engine.magic import add_free_magic_item, use_charge
    items = add_free_magic_item([], "wand_of_paralysis", charges_max=2)
    iid = items[0].instance_id
    items = use_charge(items, iid)   # 2 -> 1
    items = use_charge(items, iid)   # 1 -> 0
    # The instance is still present, now at 0 charges (not removed).
    assert len(items) == 1
    assert items[0].instance_id == iid
    assert items[0].charges_remaining == 0
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_items.py::test_use_charge_to_zero_keeps_item_in_list -q`
Expected: PASS (no production change — this guards existing behaviour). If `add_free_magic_item`'s signature differs, mirror the construction used by the adjacent `test_use_charge_decrements_and_raises_at_zero` test in the same file.

- [ ] **Step 3: Commit**

```bash
git add tests/test_magic_items.py
git commit -m "test(magic): guard that the last charge doesn't remove the item"
```

---

### Task 8: Full suite + docs

- [ ] **Step 1: Run the entire test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` `PermissionError` Windows quirk).

- [ ] **Step 2: Manual smoke check (optional but recommended)**

Start the app (`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`), open a character with a launcher + ammo + a container, and confirm: clicking a carried item / bag / ammo / worn magic item opens a modal with properties; the launcher modal loads/unloads ammo; the ammo modal adjusts count; no Drop/Sell/Refund appears in any sheet modal; the shop rows expand to show properties and Buy still works.

- [ ] **Step 3: Update `docs/CHANGELOG.md`**

Add a one-line row at the top of the ledger (match the existing format):

```
| 2026-06-08 | Inventory item modals (properties + safe actions) & shop property expander | feat/inventory-item-modals | 2026-06-08-inventory-item-modals |
```

- [ ] **Step 4: Update `docs/ARCHITECTURE.md`**

Find the inventory/sheet subsystem section and edit it **in place** (don't append a dated entry) to note: per-item sheet modals now render `item_card` properties + markdown description; destructive actions (drop/sell/refund) are drawer-only via the `inv_row_actions(show_remove=…)` flag; equipped launchers load/unload ammo from their modal; worn magic items expose use-charge; containers and ammo have property modals; shop rows reuse the `detail_card` expander (`ShopItem.detail`).

- [ ] **Step 5: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: record inventory-modals + shop-expander feature"
```

---

## Self-review

**Spec coverage:**
- §1 `show_remove` flag → Task 1 ✓
- §2 sheet modal properties + description → Task 1 ✓
- §3 containers clickable → Task 4 ✓; ammunition clickable + count adjust → Task 5 ✓; worn magic items modal + use-charge → Task 3 ✓
- §4 ranged-weapon ammo loading from modal → Task 2 ✓
- §5 shop property expander → Task 6 ✓
- Invariant "markdown everywhere" → `detail_card` (Tasks 1/4/5/6) + explicit `| markdown | safe` in the magic-item modal (Task 3) ✓
- Invariant "destructive only in drawer" → Task 1 (slice test) + drawer-still-has assertion ✓
- Invariant "last charge keeps item" → Task 7 ✓
- Testing items 1–8 in the spec → covered across Tasks 1–7 ✓
- Docs → Task 8 ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code; every run step has an exact command + expected result.

**Type/name consistency:** `detail: DetailCard | None` added consistently to `ShopItem`, `ContainerView`, `AmmoRow`; `item_card`/`detail_card`/`inv_row_actions`/`item_modal` names match their definitions; route paths (`/ammo/load`, `/ammo/unload`, `/ammo/adjust`, `/use-charge`, `/enchanted/use-charge`, `/unequip-magic`, `/unequip-enchanted`, `/stash-container`, `/unstash-container`) verified against `aose/web/routes.py`; macro arg names (`load_options`, `attack`, `show_remove`) are consistent between definition (Task 2) and call site.
