# Unified Expandable Inventory Box — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the live character sheet's fixed three-column inventory grid with a vertical accordion of every top-level inventory (Carried, Stashed, Other Possessions, animals, vehicles, retainers), each collapsible with a rich equipped sub-section, nested collapsible containers, coins shown anywhere, and every item row clickable to move it.

**Architecture:** The data already exists — `build_inventory_groups(spec, data)` in `aose/sheet/view.py` returns a `TopLevelGroup` per location. We (1) add rich equipped display data to `TopLevelGroup`, (2) rewrite the inventory box markup in `sheet.html` to render `<details>` panes from `sheet.inventory_groups` plus an "Other Possessions" pane from `sheet.other_possessions`, (3) generalize the per-row Move control to any source location, (4) relocate Spells to full width and move the inventory box into layout column 3, (5) strip storage controls from the Companions cards, and (6) add CSS. No data-model / route / storage-engine changes.

**Tech Stack:** Python 3 · FastAPI · Jinja2 · Pydantic v2 · vanilla JS · zine CSS design system. Tests: pytest. Spec: `docs/superpowers/specs/2026-06-20-unified-inventory-box-design.md`. Style rules: `docs/STYLE-GUIDE.md`.

**Run the app:** `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`
**Run tests:** `.venv\Scripts\python.exe -m pytest tests/ -q` (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `aose/engine/shop.py` | `TopLevelGroup` model — add rich equipped fields | Modify |
| `aose/sheet/view.py` | `build_inventory_groups` — populate rich equipped per group | Modify |
| `aose/web/templates/_inv_pane.html` | **New** macro: render one inventory `<details>` pane | Create |
| `aose/web/templates/sheet.html` | Inventory box body → panes; per-location item/container modals; move inventory to col 3; move Spells to full width | Modify |
| `aose/web/templates/_inv_row_actions.html` | Generalize Move form to any `src_kind`/`src_id` | Modify |
| `aose/web/templates/_companions.html` | Remove load/cargo/inventory `<details>` | Modify |
| `aose/web/static/sheet.css` | Pane / nested-container / full-width-spells / print styles | Modify |
| `tests/test_inventory_view.py` | Unit tests for rich equipped fields | Modify |
| `tests/test_sheet_inventory_box.py` | **New** route/render tests for the box | Create |
| `tests/test_companions.py` | Repoint asserts off the removed storage `<details>` | Modify |

---

## Task 1: Rich equipped fields on `TopLevelGroup`

Add three display lists so each pane can show a rich equipped block: weapon attack rows, worn armour/shield rows, worn magic rows. We keep the existing `equipped` plain list untouched (the Manage drawer and print sheet still use it), and add the rich fields alongside.

**Files:**
- Modify: `aose/engine/shop.py` (the `TopLevelGroup` class, ~line 82)

- [ ] **Step 1: Add the three fields to `TopLevelGroup`**

In `aose/engine/shop.py`, in `class TopLevelGroup`, after the existing `equipped: list[InventoryRow] = Field(default_factory=list)` line, add:

```python
    # Rich equipped display for the live sheet pane (loose-typed to avoid an
    # attacks.py import cycle, mirroring treasure_* below). PC + retainers fill
    # equipped_attacks (AttackProfile); equipped_worn holds armour/shield rows
    # (EquippedRow); equipped_magic holds worn magic rows (MagicItemView).
    equipped_attacks: list = Field(default_factory=list)
    equipped_worn: list = Field(default_factory=list)
    equipped_magic: list = Field(default_factory=list)
```

- [ ] **Step 2: Run the suite to confirm nothing broke**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`
Expected: PASS (new optional fields default empty; existing assertions on `equipped`, `has_equipped` still hold).

- [ ] **Step 3: Commit**

```bash
git add aose/engine/shop.py
git commit -m "feat(inventory): add rich equipped fields to TopLevelGroup"
```

---

## Task 2: Populate rich equipped data in `build_inventory_groups`

Fill `equipped_attacks` / `equipped_worn` / `equipped_magic` for Carried (PC), animals (barding), and retainers (computed attacks + worn armour). Vehicles and Stashed stay empty.

**Files:**
- Modify: `aose/sheet/view.py` (`build_inventory_groups`, lines ~1258–1398; and its call site uses `attack_profiles`, already imported at module top via `from aose.engine.attacks import ... attack_profiles` — verify the import in Step 1)
- Test: `tests/test_inventory_view.py`

- [ ] **Step 1: Write failing tests for the rich equipped fields**

Add to `tests/test_inventory_view.py`:

```python
def test_carried_equipped_attacks_mirror_pc_attacks(data):
    from aose.models import CharacterSpec, ClassEntry
    from aose.sheet.view import build_inventory_groups
    spec = CharacterSpec(
        name="Hero",
        abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["sword"], equipped={"main_hand": "sword"},
    )
    carried = next(g for g in build_inventory_groups(spec, data) if g.kind == "carried")
    assert carried.equipped_attacks, "PC carried group should expose weapon attack rows"
    assert any(a.name.lower().startswith("sword") for a in carried.equipped_attacks)


def test_retainer_equipped_attacks_computed_from_npc_spec(data):
    from aose.models import CharacterSpec, ClassEntry, Retainer
    from aose.sheet.view import build_inventory_groups
    npc = CharacterSpec(
        name="Hireling",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral",
        inventory=["dagger"], equipped={"main_hand": "dagger"},
    )
    spec = _base_spec(retainers=[Retainer(id="r1", spec=npc, loyalty=7)])
    retainer = next(g for g in build_inventory_groups(spec, data) if g.kind == "retainer")
    assert retainer.equipped_attacks, "retainer should expose computed attack rows"
    a = retainer.equipped_attacks[0]
    assert hasattr(a, "to_hit_ascending") and hasattr(a, "damage")


def test_animal_barding_in_equipped_worn(data):
    from aose.models import AnimalInstance
    from aose.sheet.view import build_inventory_groups
    spec = _base_spec(animals=[AnimalInstance(
        instance_id="a1", catalog_id="war_dog", armor_id="dog_armour")])
    animal = next(g for g in build_inventory_groups(spec, data) if g.kind == "animal")
    assert animal.equipped_worn, "animal barding should appear as a worn row"
    assert any(getattr(r, "item_id", None) == "dog_armour" for r in animal.equipped_worn)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -k "equipped_attacks or equipped_worn" -q`
Expected: FAIL (`equipped_attacks` / `equipped_worn` are empty lists).

- [ ] **Step 3: Confirm `attack_profiles` and `EquippedRow` are importable in view.py**

`attack_profiles` is already imported in `aose/sheet/view.py` (used at line ~1516: `attacks = attack_profiles(spec, data)`). `EquippedRow` is defined in `aose/sheet/view.py` (used by `_equipped`). Both are in-module — no new imports needed. If a grep shows `attack_profiles` is imported under an alias, use that alias below.

- [ ] **Step 4: Populate the Carried group's rich fields**

In `build_inventory_groups`, the Carried group is appended near line 1325. Replace that `groups.append(TopLevelGroup(... kind="carried" ...))` call with one that also passes the rich fields. Before the append (just after the `carried_loc = StorageLocation(kind="carried")` line) compute:

```python
    carried_loc = StorageLocation(kind="carried")
    pc_attacks = attack_profiles(spec, data)
    pc_worn = _equipped(spec, data)
    pc_magic = [mi for mi in _magic_items(spec, data) if mi.equipped]
    groups.append(TopLevelGroup(
        kind="carried", label="Carried",
        has_equipped=bool(pc_attacks or pc_worn or pc_magic),
        equipped=inv_view.equipped,
        equipped_attacks=pc_attacks,
        equipped_worn=pc_worn,
        equipped_magic=pc_magic,
        loose=inv_view.carried,
        coins=_coin_rows(carried_loc),
        treasure_gems=_gem_rows(carried_loc),
        treasure_jewellery=_jewellery_rows(carried_loc),
        containers=carried_containers,
    ))
```

(`_equipped` and `_magic_items` are module-level helpers already defined in `view.py`.)

- [ ] **Step 5: Populate the Animal group's barding as `equipped_worn`**

In the `for animal in spec.animals:` block (~line 1348), the current code builds `barding = [_build_row(animal.armor_id, 1, data)] if animal.armor_id else []` and passes `equipped=barding`. Add a worn-row form and pass it as `equipped_worn`. Replace the `barding = ...` line and the `TopLevelGroup(... kind="animal" ...)` append with:

```python
        barding = [_build_row(animal.armor_id, 1, data)] if animal.armor_id else []
        barding_worn = (
            [EquippedRow(slot="barding",
                         item_name=(data.items[animal.armor_id].name
                                    if animal.armor_id in data.items else animal.armor_id),
                         item_id=animal.armor_id)]
            if animal.armor_id else []
        )
        groups.append(TopLevelGroup(
            kind="animal", id=animal.instance_id, label=label,
            has_equipped=bool(barding_worn), equipped=barding,
            equipped_worn=barding_worn,
            loose=sorted([_build_row(i, n, data) for i, n in count.items()],
                         key=lambda r: r.name),
            coins=_coin_rows(animal_loc),
            treasure_gems=_gem_rows(animal_loc),
            treasure_jewellery=_jewellery_rows(animal_loc),
            containers=_carrier_container_views(animal_loc),
        ))
```

- [ ] **Step 6: Populate the Retainer group's computed attacks + worn armour**

In the `for retainer in spec.retainers:` block (~line 1382), replace the `ret_equipped = ...` line and the `TopLevelGroup(... kind="retainer" ...)` append with:

```python
        ret_equipped = [_build_row(iid, 1, data)
                        for iid in retainer.spec.equipped.values()]
        ret_attacks = attack_profiles(retainer.spec, data)
        ret_worn = [
            EquippedRow(slot=slot,
                        item_name=(data.items[iid].name if iid in data.items else iid),
                        item_id=iid)
            for slot, iid in retainer.spec.equipped.items()
            if slot != "main_hand"   # main-hand weapon already shown as an attack row
        ]
        groups.append(TopLevelGroup(
            kind="retainer", id=retainer.id, label=retainer.spec.name,
            has_equipped=bool(ret_attacks or ret_worn), equipped=ret_equipped,
            equipped_attacks=ret_attacks,
            equipped_worn=ret_worn,
            loose=sorted([_build_row(i, n, data) for i, n in count.items()],
                         key=lambda r: r.name),
            coins=ret_coins,
        ))
```

- [ ] **Step 7: Run the new tests + the full inventory-view file**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`
Expected: PASS (new tests green; `test_animal_group_renders_barding_in_equipped` and `test_retainer_group_renders_equipped_gear` still green because `equipped` is unchanged).

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py tests/test_inventory_view.py
git commit -m "feat(inventory): populate rich equipped data per top-level group"
```

---

## Task 3: Generalize the per-row Move control to any source

Today `inv_row_actions` only emits a Move form for `state in ("carried","stashed")` with an empty `src_id`. Widen it so a row in any location (animal / vehicle / retainer / container) gets a Move control, gated on `inv_move_groups` being defined (so the wizard, which doesn't pass it, is unaffected).

**Files:**
- Modify: `aose/web/templates/_inv_row_actions.html`

- [ ] **Step 1: Add a `src_id` parameter and widen the Move branch**

Replace the macro signature line:

```jinja
{% macro inv_row_actions(row, target_url_prefix, state, show_remove=True) %}
```

with:

```jinja
{% macro inv_row_actions(row, target_url_prefix, state, show_remove=True, src_id="") %}
```

Then replace the existing Move block:

```jinja
    {% if state in ("carried", "stashed") and inv_move_groups is defined %}
    <form method="post" action="{{ inv_move_url }}" class="inline-form move-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <input type="hidden" name="src_kind" value="{{ state }}">
        <input type="hidden" name="src_id" value="">
        {{ move_dest_control(inv_move_groups, state, none) }}
    </form>
    {% endif %}
```

with:

```jinja
    {% if inv_move_groups is defined %}
    <form method="post" action="{{ inv_move_url }}" class="inline-form move-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <input type="hidden" name="src_kind" value="{{ state }}">
        <input type="hidden" name="src_id" value="{{ src_id }}">
        {{ move_dest_control(inv_move_groups, state, src_id) }}
    </form>
    {% endif %}
```

The `equip` / `unequip` / `unstash` branches above are keyed on the literal states `carried`/`stashed`/`equipped`, so for a `state` of `animal`/`vehicle`/`retainer`/`container` only the Move (and, when `show_remove`, Drop/Sell) controls render. Per-item modals pass `show_remove=False`, so non-PC rows show only Move. `move_dest_control` already excludes the current `(kind,id)` from its options.

- [ ] **Step 2: Confirm the wizard still renders Carried + Shop only**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py -q`
Expected: PASS (the Move branch is still gated on `inv_move_groups`, which the wizard does not pass).

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html
git commit -m "feat(inventory): generalize per-row Move control to any location"
```

---

## Task 4: The inventory pane macro (`_inv_pane.html`)

A reusable macro that renders one top-level inventory as a `<details>` pane: summary header + equipped / items / containers / coins / treasure subsections. Triggers only (modals live in the overlay block — Task 5).

**Files:**
- Create: `aose/web/templates/_inv_pane.html`

- [ ] **Step 1: Create the macro file**

Create `aose/web/templates/_inv_pane.html` with:

```jinja
{# One top-level inventory rendered as a collapsible <details> pane. Triggers
   only — per-item / per-container modals are rendered in the overlay block of
   sheet.html. `prefix` is the modal id-prefix for this group's loose rows
   (e.g. "carried", "animal-<id>"). `is_carrier` true for animal/vehicle/
   retainer (their rows carry a src_id = group.id for Move). #}
{% macro inv_pane(group, prefix, src_id, open) %}
{%- set n_items = group.loose|length + group.equipped_attacks|length
                  + group.equipped_worn|length + group.equipped_magic|length
                  + group.containers|length -%}
<details class="inv-pane"{% if open %} open{% endif %} data-pane-kind="{{ group.kind }}">
  <summary class="inv-pane-head">
    <span class="inv-pane-name">{{ group.label }}</span>
    <span class="tag faint">{{ group.kind }}</span>
    <span class="inv-pane-summary">
      {{ n_items }} item{{ '' if n_items == 1 else 's' }}
      {%- if group.coins %} · {% for c in group.coins %}{{ c.count }}{{ c.denom }}{% if not loop.last %}/{% endif %}{% endfor %}{% endif -%}
    </span>
  </summary>
  <div class="inv-pane-body">

    {% if group.equipped_attacks or group.equipped_worn or group.equipped_magic %}
    <div class="subhead">Equipped</div>
    <ul class="inv-list">
      {% for atk in group.equipped_attacks %}
      <li{% if atk.manageable_item_id and group.kind == "carried" %} class="clickable" data-modal="modal-item-equipped-{{ atk.manageable_item_id }}"{% endif %}>
        <span>{{ atk.name }}{% if atk.count > 1 %} ×{{ atk.count }}{% endif %}
          {% if atk.specialised %}<span class="tag">spec</span>{% endif %}
          {% if not atk.proficient %}<span class="tag faint">non-prof</span>{% endif %}
          {% if atk.unloaded %}<span class="tag stamp">Unloaded</span>{% elif atk.loaded_ammo_name %}<span class="tag faint">{{ atk.loaded_ammo_name }}</span>{% endif %}
          {% if atk.hand == "main" %}<span class="tag faint">primary −2</span>{% elif atk.hand == "off" %}<span class="tag faint">off-hand −4</span>{% endif %}
        </span>
        <span class="st">{{ "%+d"|format(atk.to_hit_ascending) }} · {{ atk.damage }} · {% if atk.range_ft %}{{ atk.range_ft[0] }}/{{ atk.range_ft[1] }}/{{ atk.range_ft[2] }}′{% else %}—{% endif %}</span>
      </li>
      {% endfor %}
      {% for e in group.equipped_worn %}
      <li><span>{{ e.item_name }}</span><span class="st">{{ e.slot | title }}</span></li>
      {% endfor %}
      {% for mi in group.equipped_magic %}
      <li class="clickable" data-modal="modal-magic-{{ mi.instance_id }}">
        <span>{{ mi.name }} <span class="tag stamp">magic</span></span>
        <span class="st">{% for chip in mi.modifier_summary %}{{ chip }}{% if not loop.last %}, {% endif %}{% endfor %}</span>
      </li>
      {% endfor %}
    </ul>
    {% endif %}

    {% if group.loose %}
    <div class="subhead">Items</div>
    <ul class="inv-list">
      {% for row in group.loose %}
      <li class="clickable" data-modal="modal-item-{{ prefix }}-{{ row.id }}">
        <span>{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}</span>
        <span class="q">{% if group.kind == "stashed" %}—{% elif row.weight_cn is defined %}{{ row.weight_cn }} cn{% endif %}</span>
      </li>
      {% endfor %}
    </ul>
    {% endif %}

    {% for c in group.containers %}
    <details class="inv-container">
      <summary>
        <strong>{{ c.name }}</strong>
        <span class="capacity-badge{% if c.capacity_cn and c.used_cn >= c.capacity_cn %} capacity-full{% endif %}">{{ c.used_cn }} / {{ c.capacity_cn if c.capacity_cn else "∞" }} cn</span>
      </summary>
      <ul class="inv-list">
        {% for row in c.contents %}
        <li class="clickable" data-modal="modal-item-container-{{ c.instance_id }}-{{ row.id }}">
          <span><span class="indent">↳</span> {{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}</span>
          <span class="q">{% if row.weight_cn is defined %}{{ row.weight_cn }} cn{% endif %}</span>
        </li>
        {% else %}
        <li class="muted small">empty</li>
        {% endfor %}
      </ul>
    </details>
    {% endfor %}

    {% if group.coins %}
    <div class="subhead">Coins</div>
    <ul class="inv-list">
      {% for c in group.coins %}
      <li><span>{{ c.count }} {{ c.denom }}<span class="tag faint">coin</span></span><span class="q">{% if group.kind in ("stashed",) %}—{% else %}{{ c.count }} cn{% endif %}</span></li>
      {% endfor %}
    </ul>
    {% endif %}

    {% if group.treasure_gems or group.treasure_jewellery %}
    <div class="subhead">Treasure</div>
    <ul class="inv-list">
      {% for g in group.treasure_gems %}
      <li><span>{% if g.label %}{{ g.label }}{% else %}{{ g.value }} gp gem{% endif %} × {{ g.count }}<span class="tag faint">gem · {{ g.stack_value }} gp</span></span><span class="q">{{ g.count }} cn</span></li>
      {% endfor %}
      {% for j in group.treasure_jewellery %}
      <li><span>{% if j.label %}{{ j.label }}{% else %}jewellery{% endif %}<span class="tag faint">jewel · {{ j.effective_value }} gp</span></span><span class="q">10 cn</span></li>
      {% endfor %}
    </ul>
    {% endif %}

  </div>
</details>
{% endmacro %}
```

- [ ] **Step 2: Sanity-check the template parses (import smoke test)**

This macro is exercised in Task 5's render test. For now just confirm the file is valid Jinja by importing it in a throwaway render — skip if running Task 5 immediately. No commit yet; commit with Task 5 so the macro and its caller land together. (If you prefer an isolated commit: `git add aose/web/templates/_inv_pane.html && git commit -m "feat(inventory): add inv_pane macro"`.)

---

## Task 5: Rewrite the inventory box body + per-location modals in `sheet.html`

Replace the three-column inventory grid with a stack of `inv_pane` panes (all `inventory_groups` + an Other Possessions pane), and render per-item modals for every location plus a generalized per-container modal.

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Test: `tests/test_sheet_inventory_box.py` (created in Task 8)

- [ ] **Step 1: Import the pane macro**

At the top of `sheet.html`, beside the existing `{% from "_inv_row_actions.html" import inv_row_actions with context %}` line, add:

```jinja
{% from "_inv_pane.html" import inv_pane with context %}
```

- [ ] **Step 2: Replace the inventory `.gbody` body**

Replace everything between `<div class="gbody scroll" style="max-height:320px">` (line ~360) and its matching `</div>` that closes before `  </section>` (line ~516) — i.e. the whole current body: the `_cg`/`_sg` set-blocks, the `.inv-cols` three-column grid, the custom-item add form, and the `.print-only` block — with:

```jinja
    <div class="gbody scroll" style="max-height:560px">
      <div class="inv-accordion no-print">
        {% for group in sheet.inventory_groups %}
        {%- set prefix = group.kind if group.kind in ("carried","stashed") else group.kind ~ "-" ~ group.id -%}
        {{ inv_pane(group, prefix, group.id or "", group.kind == "carried") }}
        {% endfor %}

        {# Other Possessions — free-text custom items, with the add form inside #}
        <details class="inv-pane" data-pane-kind="other">
          <summary class="inv-pane-head">
            <span class="inv-pane-name">Other Possessions</span>
            <span class="tag faint">notes</span>
            <span class="inv-pane-summary">{{ sheet.other_possessions|length }} item{{ '' if sheet.other_possessions|length == 1 else 's' }}</span>
          </summary>
          <div class="inv-pane-body">
            {% if sheet.other_possessions %}
            <ul class="inv-list">
              {% for item in sheet.other_possessions %}
              <li><span>{{ item }}</span>
                <form method="post" action="/character/{{ character_id }}/possessions/remove" style="margin:0">
                  <input type="hidden" name="index" value="{{ loop.index0 }}">
                  <button type="submit" class="btn link" style="padding:0 2px;margin:0" title="Remove">×</button>
                </form>
              </li>
              {% endfor %}
            </ul>
            {% else %}
            <p class="hint" style="margin:4px 0">No custom items yet.</p>
            {% endif %}
            <form method="post" action="/character/{{ character_id }}/possessions/add" class="inline-form" style="padding:6px 0 0;width:100%">
              <input type="text" name="text" placeholder="Custom item (e.g. bronze key)…" style="flex:1;min-width:0;font-size:13px">
              <button type="submit" class="btn">Add</button>
            </form>
          </div>
        </details>
      </div>

      {# Print-only flat inventory (browser print of the live sheet) #}
      <div class="print-only">
        {% for group in sheet.inventory_groups %}
        {% if group.loose or group.equipped or group.containers or group.coins %}
        <h3>{{ group.label }}</h3>
        <ul>
          {% for row in group.equipped %}<li>{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %} <em>(equipped)</em></li>{% endfor %}
          {% for row in group.loose %}<li>{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}</li>{% endfor %}
          {% for c in group.containers %}<li><strong>{{ c.name }}</strong>: {% if c.contents %}{% for row in c.contents %}{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}{% else %}empty{% endif %}</li>{% endfor %}
          {% for c in group.coins %}<li>{{ c.count }} {{ c.denom }}</li>{% endfor %}
        </ul>
        {% endif %}
        {% endfor %}
        {% if sheet.other_possessions %}
        <h3>Other Possessions</h3>
        <ul>{% for item in sheet.other_possessions %}<li>{{ item }}</li>{% endfor %}</ul>
        {% endif %}
      </div>
    </div>
```

(Keep the surrounding `<section class="group full">` open tag and the `.bar` above it for now — Task 6 changes the section's column placement, not its inner markup. Note the opening `<div class="gbody scroll" ...>` is part of this replacement; do not leave the old one.)

- [ ] **Step 3: Replace the per-item / per-container modal loops in the overlay block**

In the overlay block near the bottom of `sheet.html`, the existing per-item modal loops are:

```jinja
{% for row in inventory_view.carried %}{{ item_modal(row, "carried", "carried", target_url_prefix) }}{% endfor %}
{% for row in inventory_view.stashed %}{{ item_modal(row, "stashed", "stashed", target_url_prefix) }}{% endfor %}
{% for row in inventory_view.equipped %}
{%- set lo = ammo_load_options.get(row.id) -%}
{%- set atk = sheet.attacks | selectattr('manageable_item_id', 'equalto', row.id) | first -%}
{{ item_modal(row, "equipped", "equipped", target_url_prefix, load_options=lo, attack=atk) }}
{% endfor %}
```

Leave those three loops as-is, and **immediately after them** add modals for carrier/retainer loose rows and all container contents:

```jinja
{# Loose-item modals for animal / vehicle / retainer inventories #}
{% for group in sheet.inventory_groups %}{% if group.kind in ("animal","vehicle","retainer") %}
{% for row in group.loose %}{{ item_modal(row, group.kind, group.kind ~ "-" ~ group.id, target_url_prefix, src_id=group.id) }}{% endfor %}
{% endif %}{% endfor %}
{# Item modals for every container's contents (any location) #}
{% for group in sheet.inventory_groups %}{% for c in group.containers %}
{% for row in c.contents %}{{ item_modal(row, "container", "container-" ~ c.instance_id, target_url_prefix, src_id=c.instance_id) }}{% endfor %}
{% endfor %}{% endfor %}
```

- [ ] **Step 4: Teach `item_modal` to forward `src_id`**

The `item_modal` macro is defined at the top of `sheet.html` (line ~6). Change its signature from:

```jinja
{% macro item_modal(row, state, id_prefix, url_prefix, load_options=none, attack=none) %}
```

to:

```jinja
{% macro item_modal(row, state, id_prefix, url_prefix, load_options=none, attack=none, src_id="") %}
```

and change its `inv_row_actions(...)` call (inside the macro, the `<div class="row-actions">` line) from:

```jinja
    <div class="row-actions">{{ inv_row_actions(row, url_prefix, state, show_remove=False) }}</div>
```

to:

```jinja
    <div class="row-actions">{{ inv_row_actions(row, url_prefix, state, show_remove=False, src_id=src_id) }}</div>
```

- [ ] **Step 5: Generalize the per-container modal to a Move control**

In the overlay block, the per-container modal loop currently iterates `inventory_view.containers` and offers carried-only Stash/Unstash. Replace the whole block:

```jinja
{# MODALS: per-container (live capacity badge + catalog card + stash/unstash) #}
{% for c in inventory_view.containers %}
<div class="overlay modal" id="modal-container-{{ c.instance_id }}" role="dialog" aria-label="{{ c.name }}">
  ...
</div>
{% endfor %}
```

with one that iterates every group's containers and uses `move_dest_control`:

```jinja
{# MODALS: per-container (capacity badge + catalog card + Move to any location) #}
{% for group in sheet.inventory_groups %}{% for c in group.containers %}
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
      <form method="post" action="{{ target_url_prefix }}/inventory/move-container" class="inline-form move-form">
        <input type="hidden" name="container_id" value="{{ c.instance_id }}">
        {{ move_dest_control(sheet.inventory_groups, group.kind, group.id or "", allow_containers=False) }}
      </form>
    </div>
  </div>
</div>
{% endfor %}{% endfor %}
```

Add the macro import for `move_dest_control` near the top of `sheet.html` if not already present:

```jinja
{% from "_move_dest.html" import move_dest_control with context %}
```

The route prefix: `target_url_prefix` is `/character/<id>` (verify from the route context in `routes.py` — `inv_move_url` is `/character/<id>/inventory/move-item`, so `target_url_prefix` + `/inventory/move-container` is correct).

- [ ] **Step 6: Ensure `inv_move_groups` / `inv_move_url` are in the sheet context**

The generalized Move form needs `inv_move_groups` and `inv_move_url`. `routes.py` already passes `inv_move_url` (line ~240). Confirm it also passes `inv_move_groups = sheet.inventory_groups` for the sheet route; if absent, add it to the sheet route's template context dict alongside `inv_move_url`.

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -q` (after Task 8 exists) — for now, verify the page renders:

Run: `.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from aose.web.app import app; c=TestClient(app); import aose.characters.storage as s"` then load any saved character id via `GET /character/<id>` and assert 200 (Task 8 automates this).

- [ ] **Step 7: Manual smoke via preview**

Start the app, open a character with a retainer + an animal carrying a container, and verify: Carried pane open with equipped weapon rows; other panes collapsed; container expands; coins visible; clicking an item in the animal opens a modal with a Move control. (Use the preview tools workflow.)

- [ ] **Step 8: Commit**

```bash
git add aose/web/templates/_inv_pane.html aose/web/templates/sheet.html
git commit -m "feat(inventory): render all inventories as collapsible panes on the sheet"
```

---

## Task 6: Move inventory to column 3 and Spells to full width

The inventory accordion is tall-and-narrow → it belongs in a layout column. Spells become a full-width region below the grid.

**Files:**
- Modify: `aose/web/templates/sheet.html`

- [ ] **Step 1: Cut the Spells column out of the grid**

In `sheet.html`, locate the `{# ═══ COLUMN 3: SPELLS / MENTAL POWERS / INNATE ═══ #}` block — it is `{% if sheet.spellbook or sheet.mental_powers or sheet.innate_abilities %} <div class="col col-spells"> … </div> {% endif %}` (lines ~234–342). Cut this entire block (including the `{% if %}`/`{% endif %}`).

- [ ] **Step 2: Move the Inventory section into column 3**

The Inventory `<section class="group full">…</section>` currently sits **after** the `.layout` closing `</div>` (line ~347). Move that whole section so it becomes the third column inside `.layout`, i.e. paste it where the Spells column was cut, wrapped in a column div, and change `group full` to `group`:

```jinja
    {# ═══ COLUMN 3: INVENTORY (accordion) ═══ #}
    <div class="col col-inventory">
      <section class="group">
        <div class="bar">Inventory
          <span class="tools">
            {% if sheet.carried_weight_cn is not none %}
            <span class="meta">{{ sheet.carried_weight_cn }} / {{ sheet.max_load }} cn{% if sheet.current_weight_band %} · {{ sheet.current_weight_band }}{% endif %}</span>
            {% endif %}
            <span class="meta">{{ sheet.total_wealth_gp }} gp wealth</span>
            {% if sheet.encumbrance_table %}<button class="btn tool" data-modal="modal-encumbrance">Thresholds</button>{% endif %}
            <button class="btn tool" data-drawer="drawer-equip">Manage</button>
          </span>
        </div>
        <div class="gbody scroll" style="max-height:560px">
          … (the accordion + print-only body from Task 5 Step 2) …
        </div>
      </section>
    </div>
```

(Reuse the exact `.bar` markup that was already on the inventory section — do not retype the meta logic differently. The body is the Task-5 accordion.)

- [ ] **Step 3: Add the full-width Spells region below the grid**

After the `.layout` closing `</div>`, paste the Spells block you cut in Step 1, wrapped in a full-width region:

```jinja
  {# ════════ SPELLS · MENTAL POWERS · INNATE (full width) ════════ #}
  {% if sheet.spellbook or sheet.mental_powers or sheet.innate_abilities %}
  <div class="spells-fullwidth">
    … (the exact contents that were inside <div class="col col-spells">: the
       {% for block in sheet.spellbook %}…, {% for block in sheet.mental_powers %}…,
       and {% if sheet.innate_abilities %}… sections, unchanged) …
  </div>
  {% endif %}
```

Then `{% include "_companions.html" %}` and the footer follow as before.

- [ ] **Step 4: Verify the page renders and overlays still work**

Run the app; confirm a caster character shows Spells full-width below the grid with blocks side-by-side, the Manage Spells drawer still opens, and a non-caster shows inventory in column 3 with no empty spell column.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "feat(sheet): inventory to column 3, spells to full-width region"
```

---

## Task 7: CSS for panes, nested containers, full-width spells, and print

**Files:**
- Modify: `aose/web/static/sheet.css` (add rules **above** the `LEGACY / SITE-WIDE` banner; tokens only)

- [ ] **Step 1: Add the zine pane / list / container styles**

Add above the legacy banner:

```css
/* ── Inventory accordion ───────────────────────────────────────────── */
.inv-accordion { display:flex; flex-direction:column; gap:6px; }

.inv-pane { border:1px solid var(--hair); background:var(--box); }
.inv-pane > summary.inv-pane-head {
  list-style:none; cursor:pointer; display:flex; align-items:center; gap:6px;
  padding:5px 8px; background:var(--box-sunk);
  font-family:var(--display); text-transform:uppercase; letter-spacing:.06em;
  font-weight:600; font-size:12px; color:var(--ink);
}
.inv-pane > summary.inv-pane-head::-webkit-details-marker { display:none; }
.inv-pane > summary.inv-pane-head::before {
  content:"▸"; color:var(--gray); font-size:10px; transition:transform .12s;
}
.inv-pane[open] > summary.inv-pane-head::before { transform:rotate(90deg); }
.inv-pane-name { flex:0 0 auto; }
.inv-pane-summary {
  margin-left:auto; font-weight:400; letter-spacing:0; text-transform:none;
  color:var(--faint); font-size:11px;
  font-variant-numeric:lining-nums tabular-nums;
}
.inv-pane-body { padding:6px 8px 8px; }
.inv-pane-body .subhead { margin-top:6px; }
.inv-pane-body .subhead:first-child { margin-top:0; }

.inv-list { list-style:none; margin:0 0 2px; padding:0; }
.inv-list > li {
  display:flex; justify-content:space-between; gap:8px; align-items:baseline;
  padding:2px 0; font-family:var(--body); font-size:13px;
}
.inv-list > li.clickable { cursor:pointer; }
.inv-list > li.clickable:hover { color:var(--stamp); }
.inv-list .q, .inv-list .st {
  flex:0 0 auto; color:var(--gray); font-size:11px;
  font-variant-numeric:lining-nums tabular-nums; white-space:nowrap;
}
.inv-list .indent { color:var(--faint); }

.inv-container { margin:4px 0 4px 6px; border-left:2px solid var(--hair); }
.inv-container > summary {
  list-style:none; cursor:pointer; display:flex; align-items:center; gap:6px;
  padding:2px 6px; font-family:var(--body); font-size:13px;
}
.inv-container > summary::-webkit-details-marker { display:none; }
.inv-container > summary::before { content:"▸"; color:var(--gray); font-size:9px; transition:transform .12s; }
.inv-container[open] > summary::before { transform:rotate(90deg); }
.inv-container .inv-list { padding-left:10px; }
```

- [ ] **Step 2: Add the full-width spells region styles**

```css
/* Spells / mental / innate, moved below the grid as a full-width band */
.spells-fullwidth {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:var(--gap); margin-top:var(--gap);
}
.spells-fullwidth > .group { margin:0; }
```

- [ ] **Step 3: Print degradation — force panes open, show the flat list**

```css
@media print {
  .inv-accordion { display:none; }            /* hide interactive accordion */
  .inv-pane, .inv-container { border:none; }
  details.inv-pane[open] > .inv-pane-body,
  details.inv-container[open] > * { display:block; }
}
```

(The `.print-only` flat block from Task 5 Step 2 is the canonical printed inventory; `@media print` already shows `.print-only` and hides `.no-print` per the existing rules.)

- [ ] **Step 4: Remove now-dead three-column rules**

Grep `sheet.css` for `.inv-cols` and `.eqhead`. `.inv-cols` (the old three-column grid) is no longer used — delete its rule block. `.eqhead`/`.st` may still be referenced by the equipped rows in the pane (`.st` is reused) — keep `.st`; delete `.eqhead` only if grep shows no remaining template use.

Run: `.venv\Scripts\python.exe -m pytest tests/ -q -k "sheet or inventory or companion"` then a manual print-preview check.

- [ ] **Step 5: Commit**

```bash
git add aose/web/static/sheet.css
git commit -m "style(inventory): accordion panes, nested containers, full-width spells, print"
```

---

## Task 8: Strip storage from Companions cards + integration tests

Remove the load/cargo/inventory `<details>` from the companion cards (storage now lives only in the inventory box) and add route-level tests for the new box.

**Files:**
- Modify: `aose/web/templates/_companions.html`
- Create: `tests/test_sheet_inventory_box.py`
- Modify: `tests/test_companions.py`

- [ ] **Step 1: Write failing integration tests for the box**

Create `tests/test_sheet_inventory_box.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from aose.models import (AnimalInstance, CharacterSpec, ClassEntry, CoinStack,
                         ContainerInstance, Retainer)
from aose.models.storage import StorageLocation
from aose.web.app import app


def _save(tmp_dir, spec):
    from aose.characters.storage import save_character
    cid = "tc-inv"
    save_character(cid, spec, tmp_dir)
    return cid


def _client(tmp_path, monkeypatch):
    # Route dirs come from request.state; the app wires them from settings.
    # Use the app's TestClient and the configured characters dir.
    return TestClient(app)


def _spec():
    npc = CharacterSpec(
        name="Hireling",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[5])],
        alignment="neutral", inventory=["dagger"], equipped={"main_hand": "dagger"},
    )
    return CharacterSpec(
        name="Boxtest",
        abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
        inventory=["torch", "sword"], equipped={"main_hand": "sword"},
        coins=[CoinStack(denom="gp", count=5,
                         location=StorageLocation(kind="animal", id="a1"))],
        animals=[AnimalInstance(instance_id="a1", catalog_id="mule")],
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      contents=["torch"],
                                      location=StorageLocation(kind="animal", id="a1"))],
        retainers=[Retainer(id="r1", spec=npc, loyalty=7)],
        other_possessions=["bronze key"],
    )
```

Then a test that renders the page. The exact character-dir wiring should mirror the existing route tests — open `tests/test_routes.py` (or whichever test issues `GET /character/<id>`) and copy its client/fixture setup. Add:

```python
def test_inventory_box_renders_all_panes(<fixtures from existing route test>):
    cid = _save(<chars_dir>, _spec())
    r = <client>.get(f"/character/{cid}")
    assert r.status_code == 200
    body = r.text
    # Every top-level inventory appears as a pane
    assert "Other Possessions" in body
    assert "bronze key" in body
    # Coins shown on a carrier (the animal)
    assert "5 gp" in body or "5gp" in body
    # A move control exists for a non-PC row (generalized Move form)
    assert "move-dest" in body
    # Custom item add box is no longer in a "Carried" column header context:
    # it now lives only inside the Other Possessions pane
    assert body.count('name="text"') >= 1
```

> Implementation note: match the existing route test's setup for `characters_dir` (the app reads it from `request.state`; existing tests use a tmp dir + dependency/middleware override). Do not invent a new wiring — copy the working one.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_inventory_box.py -q`
Expected: FAIL before the template work is loadable, or assertion failures if run before Tasks 5–6. (If Tasks 5–6 are already committed, this should pass — in which case skip to Step 3.)

- [ ] **Step 3: Remove the animal load `<details>`**

In `_companions.html`, delete the animal card's `{% if a.load_capacity %} <details class="companion-load"> … </details> {% endif %}` block (lines ~67–100). Keep the HP and Barding controls.

- [ ] **Step 4: Remove the vehicle cargo `<details>`**

Delete the vehicle card's `<details class="companion-load"> … </details>` block (lines ~138–169). Keep the Hull and extra-animals controls. (The header still shows `Cargo {{ v.cargo_used }}/{{ v.cargo_capacity }} cn` — leave that summary stat.)

- [ ] **Step 5: Remove the retainer inventory `<details>`**

Delete the retainer card's `<details class="companion-load"> … </details>` block (lines ~229–255). Keep loyalty/role/promote/dismiss and the `r.equipped` gear summary line.

- [ ] **Step 6: Repoint companions tests off the removed storage UI**

Open `tests/test_companions.py`. Any assertion that the rendered companion card contains load/cargo/give/take controls or the `companion-load` summary must move to asserting the same data now appears in the inventory box, or be removed if redundant with `tests/test_sheet_inventory_box.py`. Keep assertions about stats/HP/barding/loyalty/promote/dismiss. (Grep the file for `load`, `cargo`, `Give`, `Take`, `companion-load`, `Unload` and fix each.)

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError). In particular `tests/test_wizard.py`, `tests/test_containers.py`, `tests/test_companions.py`, `tests/test_sheet_inventory_box.py` green.

- [ ] **Step 8: Commit**

```bash
git add aose/web/templates/_companions.html tests/test_sheet_inventory_box.py tests/test_companions.py
git commit -m "feat(companions): move storage into inventory box; cards keep stats/management"
```

---

## Task 9: Docs

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`

- [ ] **Step 1: Changelog row**

Add a one-line row to the **top** of `docs/CHANGELOG.md`:

```
| 2026-06-20 | Unified expandable inventory box (all top-level inventories, rich equipped, nested containers, coins anywhere, Other Possessions) | feat/unified-inventory-box | 2026-06-20-unified-inventory-box |
```

(Match the existing table's column format exactly — open the file and mirror the header row.)

- [ ] **Step 2: Update the inventory subsystem section in ARCHITECTURE.md**

Find the inventory / storage subsystem section in `docs/ARCHITECTURE.md` and edit it in place to note: the live sheet renders `sheet.inventory_groups` as a collapsible accordion (one `<details>` pane per top-level inventory) in layout column 3; each group carries rich equipped display (`equipped_attacks`/`equipped_worn`/`equipped_magic`); Spells moved to a full-width region; custom items live in an "Other Possessions" pane; Companions cards no longer hold storage. Do not append a dated entry — edit the existing topic.

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: unified inventory box landing notes"
```

---

## Self-review notes (carried out while writing)

- **Spec coverage:** all-inventories accordion (T4/T5), equipped-where-appropriate + rich (T1/T2/T4), nested collapsible containers (T4/T7), coins anywhere (T4 — `group.coins` rendered per pane), Other Possessions pane with internal add form (T5), clickable-everywhere move (T3 + T5 modals), Carried-open/rest-collapsed (T5 `inv_pane(... open=group.kind=="carried")`; containers default closed), layout swap (T6), companions shed storage (T8), print (T5 print-only + T7 media query), tests (T2/T8), docs (T9). ✅
- **No formatter refactor:** `AttackProfile` is already the template's display shape, so retainer rows come straight from `attack_profiles(retainer.spec, data)` — the spec's "shared `format_attack_rows`" risk is avoided; the spec note is superseded by this simpler approach.
- **Type consistency:** new fields `equipped_attacks` / `equipped_worn` / `equipped_magic` used identically in T1 (defn), T2 (populate), T4 (render). `item_modal` gains `src_id=""` (T5 Step 4) used by callers in T5 Step 3. `inv_row_actions` gains `src_id=""` (T3) forwarded by `item_modal` (T5 Step 4).
- **Open verification points flagged for the implementer:** confirm `inv_move_groups` is in the sheet route context (T5 Step 6); copy the existing route test's characters-dir wiring rather than inventing one (T8 Step 1); confirm `target_url_prefix == /character/<id>` (T5 Step 5).
```
