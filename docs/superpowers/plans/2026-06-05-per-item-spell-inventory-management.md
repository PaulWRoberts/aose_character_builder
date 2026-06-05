# Per-item Spell & Inventory Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the player click a spell on the sheet to cast/restore/clear it, and click any plain inventory item (Equipped / Carried / Stashed) to read its description and manage it — all in per-row modals — instead of detouring to the "Manage" drawers.

**Architecture:** Server-rendered per-row overlay modals (Approach A). Each spell/item row becomes a `data-modal` trigger opening a dedicated `<div class="overlay modal">` that carries the description and real `<form>`s. The existing overlay controller (`sheet_overlays.js`) opens any modal by id — no JS change. The drawer's per-row action forms are extracted into a shared Jinja macro so the drawer and the new modals render identical forms. Reversed arcane memorisations become distinct rows by keying the spellbook view on `(level, spell_id, reversed)`.

**Tech Stack:** Python 3 · FastAPI · Jinja2 · Pydantic v2 · pytest. No JS framework. Zine CSS design system (`sheet.css`).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `aose/sheet/view.py` | Modify | `SpellbookRow` gains `display_name`/`reversed`/`ready_slots`/`spent_slots`; `spellbook_view` keys tallies on `(level, spell_id, reversed)`. `EquippedRow` gains `item_id`. |
| `aose/engine/shop.py` | Modify | `InventoryRow` gains `description`; `_build_row` populates it. |
| `aose/engine/attacks.py` | Modify | `AttackProfile` gains `manageable_item_id`; set only for plain equipped weapons. |
| `aose/web/templates/_inv_row_actions.html` | Create | The extracted `inv_row_actions` macro (single source of per-row item forms). |
| `aose/web/templates/_equipment_ui.html` | Modify | Import the macro `with context`; delete the inline macro definition. |
| `aose/web/templates/sheet.html` | Modify | Spell rows → per-spell modals (cast/restore/clear); plain inventory rows → per-item modals (shared macro). |
| `docs/STYLE-GUIDE.md` | Modify | Revise the "stateful spell ops live in the drawer" note. |
| `tests/test_spellbook_view.py` | Modify | Reversed-row unit test. |
| `tests/test_equip_attacks.py` | Modify | `manageable_item_id` unit tests + inventory-modal web test. |
| `tests/test_inventory_view.py` | Create | `InventoryRow.description` unit test. |
| `tests/test_web.py` | Modify | Per-spell modal web test. |

---

## Task 1: Reversed-aware spellbook rows

**Files:**
- Modify: `aose/sheet/view.py` (`SpellbookRow` class ~222-230; `spellbook_view` ~662-732)
- Test: `tests/test_spellbook_view.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spellbook_view.py`:

```python
LIGHT = "magic_user_light"   # level 1, reversible → "Darkness"


def _mu_reversed():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM, LIGHT])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    cls = DATA.classes["magic_user"]
    e2 = se.assign_slot(e, cls, DATA, level=1, spell_id=LIGHT)                    # normal
    e2 = se.assign_slot(e2, cls, DATA, level=1, spell_id=LIGHT, reversed=True)    # reversed
    spec.classes = [e2]
    return spec


def test_reversed_memorisation_is_distinct_row():
    blocks = spellbook_view(_mu_reversed(), DATA)
    lvl1 = next(g for g in blocks[0].levels if g.level == 1)
    light_rows = [r for r in lvl1.rows if r.spell_id == LIGHT]
    assert len(light_rows) == 2
    normal = next(r for r in light_rows if not r.reversed)
    rev = next(r for r in light_rows if r.reversed)
    assert normal.display_name == "Light"
    assert rev.display_name == "Darkness"
    assert normal.ready == 1 and rev.ready == 1
    assert len(normal.ready_slots) == 1 and len(rev.ready_slots) == 1
    assert set(normal.ready_slots).isdisjoint(rev.ready_slots)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spellbook_view.py::test_reversed_memorisation_is_distinct_row -q`
Expected: FAIL — `SpellbookRow` has no `display_name` (pydantic ValidationError or AttributeError), or only one Light row.

- [ ] **Step 3: Extend the `SpellbookRow` model**

In `aose/sheet/view.py`, replace the `SpellbookRow` class (currently ~222-230) with:

```python
class SpellbookRow(BaseModel):
    spell_id: str
    name: str
    display_name: str    # reverse name when reversed, else name
    level: int
    reversible: bool
    reversed: bool = False
    description: str
    known: bool          # in book (arcane) / on accessible list (divine)
    ready: int           # memorised copies with casts remaining
    spent: int           # memorised copies already cast
    ready_slots: list[int] = []   # ClassEntry.slots indices, ready (for cast)
    spent_slots: list[int] = []   # ClassEntry.slots indices, spent (for restore)
```

- [ ] **Step 4: Rewrite the tally + row generation in `spellbook_view`**

In `aose/sheet/view.py`, replace the body of `spellbook_view` from the `# tally memorised copies` block through the end of the per-level loop (currently ~676-727) with:

```python
        # tally memorised copies per (level, spell_id, reversed), tracking slot indices
        ready: dict[tuple[int, str, bool], int] = {}
        spent: dict[tuple[int, str, bool], int] = {}
        ready_idx: dict[tuple[int, str, bool], list[int]] = {}
        spent_idx: dict[tuple[int, str, bool], list[int]] = {}
        used_by_level: dict[int, int] = {}
        for i, slot in enumerate(entry.slots):
            if slot.spell_id is None:
                continue
            key = (slot.level, slot.spell_id, slot.reversed)
            if slot.spent:
                spent[key] = spent.get(key, 0) + 1
                spent_idx.setdefault(key, []).append(i)
            else:
                ready[key] = ready.get(key, 0) + 1
                ready_idx.setdefault(key, []).append(i)
            used_by_level[slot.level] = used_by_level.get(slot.level, 0) + 1

        def _row(spell, level: int, rev: bool) -> SpellbookRow:
            key = (level, spell.id, rev)
            return SpellbookRow(
                spell_id=spell.id, name=spell.name,
                display_name=_slot_display_name(spell, rev),
                level=spell.level, reversible=spell.reversible, reversed=rev,
                description=spell.description, known=spell.id in known_ids,
                ready=ready.get(key, 0), spent=spent.get(key, 0),
                ready_slots=ready_idx.get(key, []), spent_slots=spent_idx.get(key, []),
            )

        levels: list[SpellbookLevelGroup] = []
        for level in sorted(caps):
            rows: list[SpellbookRow] = []
            # (spell_id, reversed) combos that have at least one memorised copy here
            memo_keys = {
                (sid, rev)
                for (lv, sid, rev) in list(ready.keys()) + list(spent.keys())
                if lv == level
            }
            if ctype == "arcane":
                level_known = [s for s in known if s.level == level]
                known_ids_at_level = {s.id for s in level_known}
                # 1) every known book spell (normal orientation)
                for s in level_known:
                    rows.append(_row(s, level, False))
                # 2) reversed memorisations + any memorised spell not in the book
                for (sid, rev) in sorted(memo_keys):
                    if not rev and sid in known_ids_at_level:
                        continue  # already emitted as a known row above
                    s = data.spells.get(sid)
                    if s is not None:
                        rows.append(_row(s, level, rev))
            else:
                # Divine: only show memorised spells (ready or spent)
                for (sid, rev) in sorted(memo_keys):
                    s = data.spells.get(sid)
                    if s is not None:
                        rows.append(_row(s, level, rev))
            levels.append(SpellbookLevelGroup(
                level=level, cap=caps[level],
                used=used_by_level.get(level, 0), rows=rows,
            ))
```

Leave the surrounding `for entry in spec.classes` loop, the `caps`/`known`/`known_ids` setup above it, and the `out.append(SpellbookBlock(...))` after it unchanged.

- [ ] **Step 5: Run the spellbook-view tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spellbook_view.py -q`
Expected: PASS — both the new reversed test and the existing `test_spellbook_view_groups_by_level_with_cast_counts` (the known Magic Missile row still reports `ready=1, spent=1, known=True`).

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_spellbook_view.py
git commit -m "feat(sheet): reversed memorisations are distinct spellbook rows"
```

---

## Task 2: Per-spell management modals on the sheet

**Files:**
- Modify: `aose/web/templates/sheet.html` (spell column ~198-212; static `modal-spell` ~525-532; overlay block near bottom)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py`:

```python
def test_sheet_per_spell_modal_with_cast_forms(tmp_path):
    from aose.characters import save_character
    from aose.data.loader import GameData
    from aose.engine import spells as se
    from aose.models import CharacterSpec, ClassEntry

    data = GameData.load(DATA_DIR)
    characters_dir = tmp_path / "characters"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()

    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=["magic_user_magic_missile", "magic_user_light"])
    cls = data.classes["magic_user"]
    e = se.assign_slot(e, cls, data, level=1, spell_id="magic_user_light", reversed=True)
    spec = CharacterSpec(
        name="Raistlin",
        abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    save_character("raistlin", spec, characters_dir)

    app = create_app(data_dir=DATA_DIR, characters_dir=characters_dir,
                     examples_dir=examples_dir)
    client = TestClient(app)
    body = client.get("/character/raistlin").text

    # Reversed spell shows under its reverse name and has its own modal + cast form.
    assert "Darkness" in body
    assert 'id="modal-spell-magic_user-magic_user_light-r"' in body
    assert "/character/raistlin/spells/cast" in body
    # The old static placeholder modal is gone.
    assert 'id="modal-spell"' not in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_sheet_per_spell_modal_with_cast_forms -q`
Expected: FAIL — `id="modal-spell"` still present and the per-row modal id absent.

- [ ] **Step 3: Point each spell row at its own modal and use the display name**

In `aose/web/templates/sheet.html`, replace the spell-row block (currently ~199-212) with:

```html
          <div class="spell{% if row.ready == 0 and row.spent > 0 %} allspent{% endif %}"
               data-modal="modal-spell-{{ block.class_id }}-{{ row.spell_id }}-{{ 'r' if row.reversed else 'n' }}">
            <span class="snm">{{ row.display_name }}</span>
            {% if row.ready > 0 or row.spent > 0 %}
            <span class="pips">
              {% for _ in range(row.ready) %}<i class="pip"></i>{% endfor %}
              {% for _ in range(row.spent) %}<i class="pip spent"></i>{% endfor %}
            </span>
            {% elif row.known %}
            <span class="known-tag">known</span>
            {% endif %}
          </div>
```

- [ ] **Step 4: Replace the static `modal-spell` with per-spell modals**

In `aose/web/templates/sheet.html`, delete the entire static spell-detail modal block (currently ~525-532):

```html
{# MODAL: spell detail (description-only; stateful ops in the spells drawer) #}
<div class="overlay modal" id="modal-spell" role="dialog" aria-label="Spell">
  ...
</div>
```

and replace it with a loop that renders one management modal per spell row:

```html
{# MODALS: per-spell management (cast / restore / clear) #}
{% if sheet.spellbook %}
{% for block in sheet.spellbook %}
{% for lvl in block.levels %}
{% for row in lvl.rows %}
<div class="overlay modal" id="modal-spell-{{ block.class_id }}-{{ row.spell_id }}-{{ 'r' if row.reversed else 'n' }}"
     role="dialog" aria-label="{{ row.display_name }}">
  <div class="ov-head"><h3>{{ row.display_name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    <p style="font-size:15px;margin:0 0 12px">{{ row.description }}</p>
    {% if row.ready_slots or row.spent_slots %}
    <div class="row-actions">
      {% if row.ready_slots %}
      <form method="post" action="/character/{{ character_id }}/spells/cast" style="display:inline">
        <input type="hidden" name="class_id" value="{{ block.class_id }}">
        <input type="hidden" name="slot_index" value="{{ row.ready_slots[0] }}">
        <button class="btn solid" type="submit" data-close>Cast</button>
      </form>
      {% endif %}
      {% if row.spent_slots %}
      <form method="post" action="/character/{{ character_id }}/spells/restore" style="display:inline">
        <input type="hidden" name="class_id" value="{{ block.class_id }}">
        <input type="hidden" name="slot_index" value="{{ row.spent_slots[0] }}">
        <button class="btn" type="submit" data-close>Restore</button>
      </form>
      {% endif %}
      <form method="post" action="/character/{{ character_id }}/spells/clear" style="display:inline">
        <input type="hidden" name="class_id" value="{{ block.class_id }}">
        <input type="hidden" name="slot_index" value="{{ (row.ready_slots + row.spent_slots)[0] }}">
        <button class="btn" type="submit" data-close>Clear</button>
      </form>
    </div>
    {% else %}
    <p class="hint" style="margin:0">Memorise this spell from the
      <button class="btn" data-drawer="drawer-spells" style="font-size:10px;padding:3px 7px;">Manage Spells</button> drawer.</p>
    {% endif %}
  </div>
</div>
{% endfor %}
{% endfor %}
{% endfor %}
{% endif %}
```

- [ ] **Step 5: Run the spell web test + the full web suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q`
Expected: PASS — the new test passes and no existing web test regresses.

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/sheet.html tests/test_web.py
git commit -m "feat(sheet): cast/restore/clear a spell from its own modal"
```

---

## Task 3: Carry item description into the inventory view

**Files:**
- Modify: `aose/engine/shop.py` (`InventoryRow` ~39-50; `_build_row` ~126-148)
- Test: `tests/test_inventory_view.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_inventory_view.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.shop import inventory_view

DATA = GameData.load(Path(__file__).parent.parent / "data")


def test_inventory_row_carries_item_description():
    # Pick any catalog item that has a description.
    item = next(i for i in DATA.items.values() if getattr(i, "description", ""))
    view = inventory_view([item.id], [], {}, [], None, DATA)
    assert view.carried[0].description == item.description


def test_inventory_row_description_defaults_empty_for_stale_id():
    view = inventory_view(["no_such_item"], [], {}, [], None, DATA)
    assert view.carried[0].description == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`
Expected: FAIL — `InventoryRow` has no `description` attribute.

- [ ] **Step 3: Add the field to `InventoryRow`**

In `aose/engine/shop.py`, add to the `InventoryRow` model (after `name`):

```python
    description: str = ""        # catalog description (for the per-item detail modal)
```

- [ ] **Step 4: Populate it in `_build_row`**

In `aose/engine/shop.py`, in `_build_row`, set `description` in the returned `InventoryRow` (the stale-id `InventoryRow(id=item_id, name=item_id, count=count)` branch already defaults to `""`):

```python
    return InventoryRow(
        id=item_id,
        name=item.name,
        description=getattr(item, "description", "") or "",
        count=count,
        weight_cn=item.weight_cn,
        cost_gp=item.cost_gp,
        sell_gp=int((item.cost_gp / bundle) / 2),
        equippable=isinstance(item, (Weapon, Armor)),
        class_allowed=_class_allows(item, allowed_weapons, allowed_armor, allow_shields),
        bundle_count=bundle,
        can_refund=count >= bundle,
    )
```

- [ ] **Step 5: Run the test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/shop.py tests/test_inventory_view.py
git commit -m "feat(inventory): surface item description on InventoryRow"
```

---

## Task 4: Extract the shared per-row action macro

**Files:**
- Create: `aose/web/templates/_inv_row_actions.html`
- Modify: `aose/web/templates/_equipment_ui.html` (macro def ~40-90; add import at top)

This is a pure refactor; the existing wizard + web tests are the regression guard.

- [ ] **Step 1: Create the shared partial**

Create `aose/web/templates/_inv_row_actions.html` containing exactly the `inv_row_actions` macro currently in `_equipment_ui.html` (lines 40-90), verbatim:

```html
{# Shared per-row inventory action buttons.  Imported `with context` so the
   macro can read `inventory_view` (for the stow dropdown).  Used by both the
   equipment drawer (`_equipment_ui.html`) and the sheet's per-item modals
   (`sheet.html`).  `state` is "equipped" | "carried" | "stashed". #}
{% macro inv_row_actions(row, target_url_prefix, state) %}
    {% if state == "equipped" %}
    <form method="post" action="{{ target_url_prefix }}/unequip" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit">Unequip</button>
    </form>
    {% elif state == "carried" and row.equippable and row.class_allowed %}
    <form method="post" action="{{ target_url_prefix }}/equip" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit">Equip</button>
    </form>
    {% elif state == "carried" and row.equippable and not row.class_allowed %}
    <span class="muted small" title="Your class cannot use this item">Not usable</span>
    {% elif state == "stashed" %}
    <form method="post" action="{{ target_url_prefix }}/unstash" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit">Unstash</button>
    </form>
    {% endif %}
    {% set carried_bags = inventory_view.containers | selectattr("state", "equalto", "carried") | list %}
    {% if state == "carried" and carried_bags %}
    <form method="post" action="{{ target_url_prefix }}/stow" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <select name="instance_id">
            {% for c in carried_bags %}
            <option value="{{ c.instance_id }}">{{ c.name }}</option>
            {% endfor %}
        </select>
        <button type="submit">Stow</button>
    </form>
    {% endif %}
    {% if state in ("equipped", "carried") %}
    <form method="post" action="{{ target_url_prefix }}/stash" class="inline-form">
        <input type="hidden" name="item_id" value="{{ row.id }}">
        <button type="submit" title="Move off-person; stops contributing to encumbrance">Stash</button>
    </form>
    {% endif %}
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
{% endmacro %}
```

- [ ] **Step 2: Import the macro in `_equipment_ui.html` and delete the inline copy**

In `aose/web/templates/_equipment_ui.html`, delete the inline `{% macro inv_row_actions(...) %} ... {% endmacro %}` block (currently ~40-90). Add this import as the first line of the file (before the leading comment is fine; it must precede `inv_table`, which calls the macro):

```html
{% from "_inv_row_actions.html" import inv_row_actions with context %}
```

Leave `inv_table` and `container_table` unchanged — `inv_table` still calls `inv_row_actions(...)`, now resolved from the import.

- [ ] **Step 3: Run the wizard + web + equipment suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard.py tests/test_web.py tests/test_equipment.py tests/test_equip_attacks.py -q`
Expected: PASS — identical rendered forms; the wizard still renders only Carried + Shop. No behaviour change.

- [ ] **Step 4: Commit**

```bash
git add aose/web/templates/_inv_row_actions.html aose/web/templates/_equipment_ui.html
git commit -m "refactor(sheet): extract inv_row_actions into a shared partial"
```

---

## Task 5: Manageable ids on equipped weapons & armour

**Files:**
- Modify: `aose/sheet/view.py` (`EquippedRow` ~81-83; `_equipped` ~515-520)
- Modify: `aose/engine/attacks.py` (`AttackProfile` ~54-69; `_profile_for` ~87-170; `attack_profiles` plain loop ~219-226)
- Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_equip_attacks.py`:

```python
def test_plain_equipped_weapon_has_manageable_item_id(data):
    spec = CharacterSpec(
        name="W", abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        inventory=["sword"], equipped_weapons=["sword"],
    )
    profiles = attack_profiles(spec, data)
    sword = next(p for p in profiles if p.weapon_id == "sword")
    assert sword.manageable_item_id == "sword"
    unarmed = next(p for p in profiles if p.unarmed)
    assert unarmed.manageable_item_id is None


def test_equipped_row_carries_item_id(data):
    from aose.sheet.view import _equipped
    spec = CharacterSpec(
        name="A", abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        inventory=["plate_mail"], equipped={"armor": "plate_mail"},
    )
    rows = _equipped(spec, data)
    assert rows[0].item_id == "plate_mail"
```

> If `sword` or `plate_mail` are not valid catalog ids, substitute any plain `Weapon`/`Armor` id from `data.items` (e.g. inspect `data/equipment/weapons.yaml` / `armor.yaml`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_plain_equipped_weapon_has_manageable_item_id tests/test_equip_attacks.py::test_equipped_row_carries_item_id -q`
Expected: FAIL — `AttackProfile` / `EquippedRow` have no such field.

- [ ] **Step 3: Add `item_id` to `EquippedRow` and populate it**

In `aose/sheet/view.py`, change `EquippedRow`:

```python
class EquippedRow(BaseModel):
    slot: str
    item_name: str
    item_id: str = ""
```

and in `_equipped`:

```python
def _equipped(spec: CharacterSpec, data: GameData) -> list[EquippedRow]:
    rows: list[EquippedRow] = []
    for slot, item_id in spec.equipped.items():
        name = data.items[item_id].name if item_id in data.items else item_id
        rows.append(EquippedRow(slot=slot, item_name=name, item_id=item_id))
    return rows
```

- [ ] **Step 4: Add `manageable_item_id` to `AttackProfile`**

In `aose/engine/attacks.py`, add to the `AttackProfile` model (after `loaded_ammo_name`):

```python
    manageable_item_id: str | None = None   # plain catalog weapon id → click-to-manage; None for enchanted/unarmed
```

- [ ] **Step 5: Thread it through `_profile_for` and set it for plain weapons only**

In `aose/engine/attacks.py`, add a keyword arg to `_profile_for` (extend the signature, default `None`):

```python
def _profile_for(weapon: Weapon, spec: CharacterSpec, data: GameData,
                 count: int, eff: dict, base_thac0: int,
                 g_atk: int, g_dmg: int,
                 ammo_bonus: int = 0, ammo_conditional=None,
                 ammo_name: str | None = None, unloaded: bool = False,
                 manageable_item_id: str | None = None) -> AttackProfile:
```

and add `manageable_item_id=manageable_item_id` to the `return AttackProfile(...)` at the end of that function.

In `attack_profiles`, the **plain** weapons loop passes the id; the enchanted loop and unarmed do not. Change only the plain loop (currently ~219-226):

```python
    counts = Counter(spec.equipped_weapons)
    weapon_profiles: list[AttackProfile] = []
    for weapon_id, count in counts.items():
        item = data.items.get(weapon_id)
        if not isinstance(item, Weapon):
            continue  # equipped_weapons should only contain weapons, defensive
        weapon_profiles.append(
            _profile_for(item, spec, data, count, eff, base_thac0, g_atk, g_dmg,
                         manageable_item_id=item.id, **_ammo_args(item))
        )
```

Leave the `equipped_enchanted(...)` loop and `_unarmed_profile(...)` untouched (they keep the `None` default).

- [ ] **Step 6: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/sheet/view.py aose/engine/attacks.py tests/test_equip_attacks.py
git commit -m "feat(sheet): expose manageable item ids on equipped weapons & armour"
```

---

## Task 6: Click-to-manage Carried & Stashed items

**Files:**
- Modify: `aose/web/templates/sheet.html` (import macro near top; Carried rows ~306-308; Stashed rows ~340-342; overlay block near bottom)
- Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_equip_attacks.py`:

```python
def test_sheet_carried_and_stashed_items_are_clickable(tmp_path, data):
    from aose.characters import save_character
    client = _make_client(tmp_path)
    spec = CharacterSpec(
        name="Packrat",
        abilities={"STR": 11, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        inventory=["rope"], stashed=["torch"],
    )
    save_character("packrat", spec, client._characters_dir)
    body = client.get("/character/packrat").text

    assert 'data-modal="modal-item-carried-rope"' in body
    assert 'id="modal-item-carried-rope"' in body
    assert 'data-modal="modal-item-stashed-torch"' in body
    assert 'id="modal-item-stashed-torch"' in body
    # Carried item modal offers Stash + Drop; stashed offers Unstash.
    assert "/character/packrat/equipment/stash" in body
    assert "/character/packrat/equipment/unstash" in body
```

> Use any two valid catalog ids if `rope`/`torch` aren't present (check `data/equipment/adventuring_gear.yaml`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_sheet_carried_and_stashed_items_are_clickable -q`
Expected: FAIL — no `modal-item-*` ids in the page.

- [ ] **Step 3: Import the shared macro into `sheet.html`**

In `aose/web/templates/sheet.html`, add immediately after `{% block content %}` (line 3):

```html
{% from "_inv_row_actions.html" import inv_row_actions with context %}
```

- [ ] **Step 4: Make Carried and Stashed rows triggers**

In `aose/web/templates/sheet.html`, change the Carried plain-item row (currently ~306-308) to add the trigger (leave the gems/jewellery/spell-source/ammo rows below it untouched):

```html
            {% for row in inventory_view.carried %}
            <li class="clickable" data-modal="modal-item-carried-{{ row.id }}"><span>{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}</span><span class="q">{% if row.weight_cn is defined %}{{ row.weight_cn }}{% endif %} cn</span></li>
            {% endfor %}
```

Change the Stashed plain-item row (currently ~340-342):

```html
            {% for row in inventory_view.stashed %}
            <li class="clickable" data-modal="modal-item-stashed-{{ row.id }}"><span>{{ row.name }}{% if row.count > 1 %} ×{{ row.count }}{% endif %}</span><span class="q">—</span></li>
            {% endfor %}
```

- [ ] **Step 5: Add an `item_modal` macro and render Carried/Stashed modals**

In `aose/web/templates/sheet.html`, add a local macro just after the import from Step 3:

```html
{% macro item_modal(row, state, id_prefix, url_prefix) %}
<div class="overlay modal" id="modal-item-{{ id_prefix }}-{{ row.id }}" role="dialog" aria-label="{{ row.name }}">
  <div class="ov-head"><h3>{{ row.name }}</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    {% if row.description %}<p style="font-size:15px;margin:0 0 12px">{{ row.description }}</p>{% endif %}
    <div class="row-actions">{{ inv_row_actions(row, url_prefix, state) }}</div>
  </div>
</div>
{% endmacro %}
```

Then, in the overlay block near the bottom of the file (after the per-spell modals from Task 2), add:

```html
{# MODALS: per-item inventory management #}
{% for row in inventory_view.carried %}{{ item_modal(row, "carried", "carried", target_url_prefix) }}{% endfor %}
{% for row in inventory_view.stashed %}{{ item_modal(row, "stashed", "stashed", target_url_prefix) }}{% endfor %}
```

- [ ] **Step 6: Run the test + full web suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py tests/test_web.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/sheet.html tests/test_equip_attacks.py
git commit -m "feat(sheet): click Carried/Stashed items to read & manage them"
```

---

## Task 7: Click-to-manage Equipped items

**Files:**
- Modify: `aose/web/templates/sheet.html` (Equipped column weapon rows ~265-282; equipped armour rows ~284-289; overlay block)
- Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_equip_attacks.py`:

```python
def test_sheet_equipped_items_are_clickable(tmp_path, data):
    from aose.characters import save_character
    client = _make_client(tmp_path)
    spec = CharacterSpec(
        name="Sir Click",
        abilities={"STR": 13, "INT": 10, "WIS": 10, "DEX": 11, "CON": 12, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        inventory=["sword", "plate_mail"],
        equipped_weapons=["sword"], equipped={"armor": "plate_mail"},
    )
    save_character("sir-click", spec, client._characters_dir)
    body = client.get("/character/sir-click").text

    # Equipped weapon (plain) and equipped armour both trigger and render modals.
    assert 'data-modal="modal-item-equipped-sword"' in body
    assert 'id="modal-item-equipped-sword"' in body
    assert 'data-modal="modal-item-equipped-plate_mail"' in body
    assert 'id="modal-item-equipped-plate_mail"' in body
    # The equipped modal offers Unequip.
    assert "/character/sir-click/equipment/unequip" in body
    # Unarmed is never a trigger.
    assert 'data-modal="modal-item-equipped-unarmed"' not in body
```

> Substitute valid `Weapon`/`Armor` ids if `sword`/`plate_mail` aren't present.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py::test_sheet_equipped_items_are_clickable -q`
Expected: FAIL — no equipped `modal-item-*` ids.

- [ ] **Step 3: Make equipped weapon rows triggers (plain weapons only)**

In `aose/web/templates/sheet.html`, the Equipped-column attacks loop renders an `<li>` per attack (currently ~265-275). Add a `data-modal` attribute, gated on `atk.manageable_item_id`, by changing the opening `<li>`:

```html
            {% for atk in sheet.attacks %}
            <li{% if atk.manageable_item_id %} class="clickable" data-modal="modal-item-equipped-{{ atk.manageable_item_id }}"{% endif %}>
```

Leave the rest of the attack `<li>` body (name, tags, stats) and the conditional sub-row unchanged.

- [ ] **Step 4: Make equipped armour rows triggers**

In `aose/web/templates/sheet.html`, change the equipped armour/shield loop (currently ~284-289) to add the trigger when the row has an id:

```html
            {% for e in sheet.equipped %}
            <li{% if e.item_id %} class="clickable" data-modal="modal-item-equipped-{{ e.item_id }}"{% endif %} style="border-top:1px solid var(--hair);margin-top:4px;padding-top:4px">
              <span>{{ e.item_name }}</span>
              <span class="st">{{ e.slot | title }}</span>
            </li>
            {% endfor %}
```

- [ ] **Step 5: Render the equipped per-item modals**

In `aose/web/templates/sheet.html`, in the overlay block (right after the Carried/Stashed modal loops from Task 6), add — modals are built from the canonical `inventory_view.equipped` rows so they carry the full action context:

```html
{% for row in inventory_view.equipped %}{{ item_modal(row, "equipped", "equipped", target_url_prefix) }}{% endfor %}
```

> Triggers reference modal ids by item id; an `atk.manageable_item_id` that has no matching `inventory_view.equipped` row (shouldn't happen for plain equipped weapons, which live in `inventory`) simply opens nothing — the controller's `open()` no-ops on a missing panel.

- [ ] **Step 6: Run the test + full web suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py tests/test_web.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/web/templates/sheet.html tests/test_equip_attacks.py
git commit -m "feat(sheet): click equipped weapons & armour to manage them"
```

---

## Task 8: Add a `clickable` affordance style & update the style guide

**Files:**
- Modify: `aose/web/static/sheet.css` (above the `LEGACY / SITE-WIDE` banner)
- Modify: `docs/STYLE-GUIDE.md`

- [ ] **Step 1: Add a cursor/hover affordance for clickable rows**

In `aose/web/static/sheet.css`, **above** the `/* LEGACY / SITE-WIDE styles ... */` banner, add:

```css
/* Click-to-manage inventory rows (per-item modal triggers). */
.inv-cols li.clickable { cursor: pointer; }
.inv-cols li.clickable:hover { color: var(--stamp); }
```

(The `.spell` rows already have a pointer affordance from the existing zine styles; if they do not visibly indicate clickability, add `.spell { cursor: pointer; }` here too.)

- [ ] **Step 2: Verify the sheet still renders with no console errors**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q`
Expected: PASS. (Manual spot-check optional via the preview workflow — load a spellcaster with items, click a spell and an item, confirm the modal opens and a form submits.)

- [ ] **Step 3: Revise the style-guide note about stateful spell ops**

In `docs/STYLE-GUIDE.md`, update the two places that assert stateful ops live only in the drawer:

- §4 "Conventions" → the "Everything with info is clickable" bullet: append that spell rows and plain inventory rows now open a **management** modal (cast/restore/clear for spells; equip/stash/drop/sell for items), with the drawer retained for bulk/creation work (memorise/forget/learn, shop, grants).
- §5 "Templated detail modal" paragraph → replace the sentence *"Stateful spell ops live in the spells drawer, not the detail modal (keeps the modal static)."* with: *"Per-spell and per-item modals are rendered server-side (one per row) and carry their own cast/restore/clear or equip/stash/drop forms. The drawer keeps the bulk operations (memorise/forget/learn, shop, grants)."*

- [ ] **Step 4: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known trailing `PermissionError` on `pytest-current` per CLAUDE.md).

- [ ] **Step 5: Commit**

```bash
git add aose/web/static/sheet.css docs/STYLE-GUIDE.md
git commit -m "docs(sheet): clickable-row affordance + style-guide update for per-item management"
```

---

## Self-Review

**Spec coverage:**
- Per-spell modal cast/restore/clear → Tasks 1 (view) + 2 (modal). ✓
- Reversed memorisation as a distinct, named, castable row → Task 1 (`(level, spell_id, reversed)` key, `display_name`, slot lists) + Task 2 (renders `display_name`, reversed-row modal id `…-r`). ✓
- Plain inventory rows (Equipped / Carried / Stashed) click-to-manage → Tasks 6 (carried/stashed) + 7 (equipped). ✓
- Equipped weapons in scope (user chose "All equipped items too") → Task 5 (`manageable_item_id`) + Task 7. ✓
- Description in the modal → Task 3 (`InventoryRow.description`) + Tasks 6/7 (`item_modal` renders it); spell description already on `SpellbookRow`. ✓
- Shared action forms (one source for drawer + modals) → Task 4 (extract `inv_row_actions`). ✓
- Drawers retained for bulk/creation → unchanged; only triggers/modals added. ✓
- Invariants: closed-modal `pointer-events:none` is inherited from the existing `.overlay.modal` CSS rule (every new modal uses that class — no new rule needed); one-open-at-a-time + Esc/scrim/× handled by the unchanged controller; print degradation unchanged (overlays already hidden in `@media print`). ✓
- Style-guide note revised → Task 8. ✓
- Wizard still Carried + Shop only → guarded by `tests/test_wizard.py` in Task 4. ✓

**Placeholder scan:** No TBD/TODO. The only conditional instructions are the "substitute a valid catalog id" notes, which give an explicit lookup location — acceptable because exact seed ids must be confirmed against YAML at implementation time.

**Type consistency:** `SpellbookRow.display_name/reversed/ready_slots/spent_slots`, `InventoryRow.description`, `EquippedRow.item_id`, `AttackProfile.manageable_item_id` are defined once (Tasks 1/3/5) and consumed with the same names in the templates (Tasks 2/6/7). Modal id scheme `modal-item-{state}-{id}` and `modal-spell-{class_id}-{spell_id}-{n|r}` is used identically by triggers and panels. The macro `inv_row_actions(row, target_url_prefix, state)` keeps its original 3-arg signature; `item_modal(row, state, id_prefix, url_prefix)` passes `url_prefix` through to it. ✓
