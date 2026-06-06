# Inline Detail Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make spell rows (Manage Spells drawer) and item rows (inventory drawer: Equipped/Carried/Stashed + Documents-tab embedded spells) expand in place to show structured details, collapsing on a second click — the drawer never closes.

**Architecture:** One cycle-free builder module (`aose/engine/detail.py`) produces a unified `DetailCard` (stat lines + description) for any spell or item. Each affected row view model gains a `detail: DetailCard | None`. One Jinja macro renders any `DetailCard`; one generalized vanilla-JS toggle expands/collapses a `colspan` detail `<tr>` inserted after each row (reusing the existing container-collapse pattern). No new overlay surfaces.

**Tech Stack:** Python 3 + Pydantic v2, FastAPI + Jinja2, vanilla JS, pytest. Windows venv: all Python/pytest commands use `.venv\Scripts\python.exe`.

---

## Spec

`docs/superpowers/specs/2026-06-05-inline-detail-cards-design.md`

## File Structure

| File | Responsibility | Create/Modify |
|---|---|---|
| `aose/engine/detail.py` | `StatLine`, `DetailCard` value types + `spell_card()` / `item_card()` builders. Imports only `aose.models` (cycle-free). | Create |
| `aose/engine/shop.py` | `InventoryRow` gains `detail`; `_make_row` populates it via `item_card`. | Modify |
| `aose/sheet/view.py` | `SpellEntryView`, `SlotView`, `SpellSourceEntryView` gain `detail`; builders populate via `spell_card`. | Modify |
| `aose/web/templates/_detail_card.html` | `detail_card(card)` macro — the shared structured renderer. | Create |
| `aose/web/templates/sheet.html` | Manage Spells drawer: detail rows after memorised-slot + known rows. | Modify |
| `aose/web/templates/_equipment_ui.html` | `inv_table` rows + Documents-tab rows get detail rows. | Modify |
| `aose/web/static/inventory.js` | Add generalized row-detail toggle beside the container toggle. | Modify |
| `aose/web/static/sheet.css` | `.detail-card` / `.detail-stats` / `.detail-desc` / `.row-detail` zine styles (above legacy banner). | Modify |
| `tests/test_detail_cards.py` | Unit tests for `spell_card` / `item_card`. | Create |
| `tests/test_inventory_view.py` | Assert `InventoryRow.detail` populated. | Modify |
| `tests/test_spellbook_view.py` | (kept) — spell detail assertions go in a new file to avoid coupling. | — |
| `tests/test_detail_views.py` | Assert `SpellEntryView`/`SlotView`/`SpellSourceEntryView` carry `detail`. | Create |
| `tests/test_sheet.py` | Smoke test: detail rows render with `data-detail-for` + `collapsed`. | Modify |

---

## Task 1: `DetailCard` value types + `spell_card` builder

**Files:**
- Create: `aose/engine/detail.py`
- Test: `tests/test_detail_cards.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_detail_cards.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.detail import DetailCard, StatLine, spell_card

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _stat(card, label):
    return next((s.value for s in card.stats if s.label == label), None)


def test_spell_card_has_level_range_duration_and_description():
    spell = DATA.spells["cleric_cure_light_wounds"]
    card = spell_card(spell)
    assert isinstance(card, DetailCard)
    assert _stat(card, "Level") == "1"
    assert _stat(card, "Range") == spell.range
    assert _stat(card, "Duration") == spell.duration
    assert card.description == spell.description


def test_spell_card_reversible_line_uses_reverse_name():
    spell = DATA.spells["cleric_cure_light_wounds"]  # reversible
    card = spell_card(spell)
    assert _stat(card, "Reversible") == "Yes — Cause Light Wounds"


def test_spell_card_non_reversible_has_no_reversible_line():
    spell = next(s for s in DATA.spells.values() if not s.reversible)
    card = spell_card(spell)
    assert _stat(card, "Reversible") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_cards.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aose.engine.detail'`.

- [ ] **Step 3: Write minimal implementation**

Create `aose/engine/detail.py`:

```python
"""Cycle-free builders for inline detail cards (spells & items).

Imports only ``aose.models`` so both ``aose/engine/shop.py`` and
``aose/sheet/view.py`` can use it without an import cycle.
"""
from pydantic import BaseModel, ConfigDict

from aose.models import (
    AdventuringGear, Ammunition, Armor, Container, MagicItem, Poison, Spell, Weapon,
)


class StatLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class DetailCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stats: list[StatLine] = []
    description: str | None = None


def spell_card(spell: Spell, *, reversed: bool = False) -> DetailCard:
    stats = [
        StatLine(label="Level", value=str(spell.level)),
        StatLine(label="Range", value=spell.range),
        StatLine(label="Duration", value=spell.duration),
    ]
    if spell.reversible:
        rn = spell.reverse_name or "—"
        stats.append(StatLine(label="Reversible", value=f"Yes — {rn}"))
    return DetailCard(stats=stats, description=spell.description)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_cards.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/detail.py tests/test_detail_cards.py
git commit -m "Add DetailCard value types and spell_card builder"
```

---

## Task 2: `item_card` builder

**Files:**
- Modify: `aose/engine/detail.py`
- Test: `tests/test_detail_cards.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_detail_cards.py`:

```python
from aose.engine.detail import item_card
from aose.models import Armor, Weapon


def test_item_card_weapon_has_damage_and_description():
    weapon = next(i for i in DATA.items.values() if isinstance(i, Weapon))
    card = item_card(weapon)
    assert _stat(card, "Type") == "Weapon"
    assert _stat(card, "Damage") == weapon.damage.default
    assert _stat(card, "Cost") == f"{int(weapon.cost_gp)} gp"
    assert card.description == (weapon.description or None)


def test_item_card_ranged_weapon_has_range_line():
    weapon = next(
        (i for i in DATA.items.values()
         if isinstance(i, Weapon) and i.ranged and i.range_short),
        None,
    )
    if weapon is None:
        return  # no ranged weapon in data — nothing to assert
    card = item_card(weapon)
    expected = f"{weapon.range_short}/{weapon.range_medium}/{weapon.range_long} ft"
    assert _stat(card, "Range") == expected


def test_item_card_body_armor_shows_ac():
    armor = next(
        i for i in DATA.items.values()
        if isinstance(i, Armor) and not i.is_shield
    )
    card = item_card(armor)
    assert _stat(card, "Type") == "Armour"
    assert _stat(card, "AC") == f"{armor.ac_descending} [{19 - armor.ac_descending}]"


def test_item_card_shield_shows_ac_bonus():
    shield = next(
        (i for i in DATA.items.values() if isinstance(i, Armor) and i.is_shield),
        None,
    )
    if shield is None:
        return
    card = item_card(shield)
    assert _stat(card, "Type") == "Shield"
    assert _stat(card, "AC Bonus") == f"+{shield.ac_bonus}"


def test_item_card_unknown_type_falls_back_to_cost_and_description():
    gear = next(i for i in DATA.items.values() if i.item_type == "gear")
    card = item_card(gear)
    assert _stat(card, "Cost") == f"{int(gear.cost_gp)} gp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_cards.py -q`
Expected: FAIL — `ImportError: cannot import name 'item_card'`.

- [ ] **Step 3: Write minimal implementation**

Append to `aose/engine/detail.py`:

```python
def _cost_weight(item) -> list[StatLine]:
    out: list[StatLine] = []
    if item.cost_gp:
        out.append(StatLine(label="Cost", value=f"{int(item.cost_gp)} gp"))
    if item.weight_cn:
        out.append(StatLine(label="Weight", value=f"{item.weight_cn} cn"))
    return out


def item_card(item) -> DetailCard:
    stats: list[StatLine] = []

    if isinstance(item, Weapon):
        stats.append(StatLine(label="Type", value="Weapon"))
        stats.append(StatLine(label="Damage", value=item.damage.default))
        if item.damage.variable_two_handed:
            stats.append(StatLine(
                label="Damage (2H)", value=item.damage.variable_two_handed))
        if item.ranged and item.range_short:
            stats.append(StatLine(
                label="Range",
                value=f"{item.range_short}/{item.range_medium}/{item.range_long} ft"))
        stats.append(StatLine(label="Hands", value=str(item.hands)))
        if item.qualities:
            stats.append(StatLine(label="Qualities", value=", ".join(item.qualities)))
        if item.magic_bonus:
            stats.append(StatLine(label="Magic", value=f"+{item.magic_bonus}"))
        if item.conditional_bonus:
            cb = item.conditional_bonus
            stats.append(StatLine(label="Bonus", value=f"+{cb.bonus} vs {cb.vs}"))
        stats += _cost_weight(item)

    elif isinstance(item, Armor):
        if item.is_shield:
            stats.append(StatLine(label="Type", value="Shield"))
            stats.append(StatLine(label="AC Bonus", value=f"+{item.ac_bonus}"))
        else:
            stats.append(StatLine(label="Type", value="Armour"))
            stats.append(StatLine(
                label="AC",
                value=f"{item.ac_descending} [{19 - item.ac_descending}]"))
        if item.magic_bonus:
            stats.append(StatLine(label="Magic", value=f"+{item.magic_bonus}"))
        stats += _cost_weight(item)

    elif isinstance(item, Container):
        stats.append(StatLine(label="Type", value="Container"))
        cap = item.capacity_cn
        stats.append(StatLine(
            label="Capacity", value=f"{cap} cn" if cap else "Unlimited"))
        stats += _cost_weight(item)

    elif isinstance(item, MagicItem):
        stats.append(StatLine(label="Type", value="Magic Item"))
        if item.max_charges is not None:
            stats.append(StatLine(label="Charges", value=str(item.max_charges)))
        stats += _cost_weight(item)

    elif isinstance(item, Ammunition):
        stats.append(StatLine(label="Type", value="Ammunition"))
        if item.groups:
            stats.append(StatLine(label="Groups", value=", ".join(item.groups)))
        if item.bundle_count > 1:
            stats.append(StatLine(label="Bundle", value=str(item.bundle_count)))
        stats += _cost_weight(item)

    elif isinstance(item, Poison):
        stats.append(StatLine(label="Type", value="Poison"))
        if item.onset:
            stats.append(StatLine(label="Onset", value=item.onset))
        if item.effect:
            stats.append(StatLine(label="Effect", value=item.effect))
        stats += _cost_weight(item)

    else:  # AdventuringGear and anything else
        stats.append(StatLine(label="Type", value="Gear"))
        if isinstance(item, AdventuringGear) and item.bundle_count > 1:
            stats.append(StatLine(label="Bundle", value=str(item.bundle_count)))
        stats += _cost_weight(item)

    return DetailCard(stats=stats, description=item.description or None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_cards.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/detail.py tests/test_detail_cards.py
git commit -m "Add item_card builder with per-type stat lines"
```

---

## Task 3: `InventoryRow.detail` populated by `inventory_view`

**Files:**
- Modify: `aose/engine/shop.py` (`InventoryRow` model ~line 39; `_make_row` ~line 138)
- Test: `tests/test_inventory_view.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_inventory_view.py`:

```python
from aose.engine.detail import DetailCard
from aose.models import Weapon


def test_inventory_row_carries_detail_card():
    weapon = next(i for i in DATA.items.values() if isinstance(i, Weapon))
    view = inventory_view([weapon.id], [], {}, [], None, DATA)
    row = view.carried[0]
    assert isinstance(row.detail, DetailCard)
    assert any(s.label == "Damage" for s in row.detail.stats)


def test_inventory_row_detail_none_for_stale_id():
    view = inventory_view(["no_such_item"], [], {}, [], None, DATA)
    assert view.carried[0].detail is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`
Expected: FAIL — `AttributeError: 'InventoryRow' object has no attribute 'detail'`.

- [ ] **Step 3: Write minimal implementation**

In `aose/engine/shop.py`, add the import near the top (with the other `aose` imports):

```python
from aose.engine.detail import DetailCard, item_card
```

Add the field to `InventoryRow` (after `can_refund`):

```python
    detail: DetailCard | None = None   # structured card for the inline expander
```

In `_make_row`, the stale-id early return already omits `detail` (defaults to
`None`) — leave it. In the main `InventoryRow(...)` construction, add:

```python
        detail=item_card(item),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/shop.py tests/test_inventory_view.py
git commit -m "Populate InventoryRow.detail with item_card"
```

---

## Task 4: Spell view models carry `detail`

**Files:**
- Modify: `aose/sheet/view.py` (`SpellEntryView` ~line 134, `SlotView` ~line 142, `SpellSourceEntryView` ~line 171; builders `_spell_entry` ~623, `spells_view` slot loop ~652, `spell_sources_view` ~814)
- Test: `tests/test_detail_views.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_detail_views.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spells as se
from aose.engine.detail import DetailCard
from aose.models import CharacterSpec, ClassEntry, SpellSource, SpellSourceEntry
from aose.sheet.view import spells_view, spell_sources_view

DATA = GameData.load(Path(__file__).parent.parent / "data")

MM = "magic_user_magic_missile"


def _caster():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM])
    spec = CharacterSpec(
        name="M",
        abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    cls = DATA.classes["magic_user"]
    spec.classes = [se.assign_slot(e, cls, DATA, level=1, spell_id=MM)]
    return spec


def test_known_spell_entry_has_detail():
    block = spells_view(_caster(), DATA)[0]
    assert block.known
    assert isinstance(block.known[0].detail, DetailCard)
    assert any(s.label == "Range" for s in block.known[0].detail.stats)


def test_memorised_slot_has_detail():
    block = spells_view(_caster(), DATA)[0]
    slot = next(g for g in block.slot_groups if g.slots).slots[0]
    assert isinstance(slot.detail, DetailCard)


def test_spell_source_entry_has_detail():
    spec = _caster()
    spec.spell_sources = [SpellSource(
        instance_id="src1", kind="scroll", caster_type="arcane",
        entries=[SpellSourceEntry(spell_id=MM)],
    )]
    src = spell_sources_view(spec, DATA)[0]
    assert isinstance(src.entries[0].detail, DetailCard)
    assert src.entries[0].detail.description == DATA.spells[MM].description
```

> Confirmed: `SpellSource` / `SpellSourceEntry` live in
> `aose/models/character.py` and are re-exported from `aose.models`.
> `SpellSourceEntry` has fields `spell_id` + `copy_failed`; `SpellSource` has
> `instance_id`, `kind`, `caster_type`, `entries`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_views.py -q`
Expected: FAIL — `AttributeError: 'SpellEntryView' object has no attribute 'detail'`.

- [ ] **Step 3: Write minimal implementation**

In `aose/sheet/view.py`, add the import (with the other engine imports near the top):

```python
from aose.engine.detail import DetailCard, spell_card
```

Add `detail` fields:

```python
class SpellEntryView(BaseModel):
    id: str
    name: str
    level: int
    description: str
    reversible: bool
    detail: DetailCard | None = None
```

```python
class SlotView(BaseModel):
    index: int
    spell_id: str
    name: str
    display_name: str
    level: int
    reversible: bool
    reversed: bool
    spent: bool
    detail: DetailCard | None = None
```

```python
class SpellSourceEntryView(BaseModel):
    spell_id: str
    name: str
    level: int
    copy_failed: bool
    can_cast: bool
    can_copy: bool
    detail: DetailCard | None = None
```

Populate in `_spell_entry`:

```python
def _spell_entry(spell) -> SpellEntryView:
    return SpellEntryView(
        id=spell.id, name=spell.name, level=spell.level,
        description=spell.description, reversible=spell.reversible,
        detail=spell_card(spell),
    )
```

In `spells_view`, the `SlotView(...)` construction — add the `detail` kwarg
(the spell is `data.spells[slot.spell_id]`):

```python
                SlotView(
                    index=i,
                    spell_id=slot.spell_id,
                    name=data.spells[slot.spell_id].name,
                    display_name=_slot_display_name(data.spells[slot.spell_id], slot.reversed),
                    level=slot.level,
                    reversible=data.spells[slot.spell_id].reversible,
                    reversed=slot.reversed,
                    spent=slot.spent,
                    detail=spell_card(data.spells[slot.spell_id], reversed=slot.reversed),
                )
```

In `spell_sources_view`, the `SpellSourceEntryView(...)` construction — add:

```python
                detail=spell_card(spell) if spell else None,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_detail_views.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError — known Windows quirk).

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_detail_views.py
git commit -m "Carry DetailCard on spell entry / slot / source-entry views"
```

---

## Task 5: `detail_card` macro

**Files:**
- Create: `aose/web/templates/_detail_card.html`

- [ ] **Step 1: Create the macro**

Create `aose/web/templates/_detail_card.html`:

```jinja
{# Shared structured detail renderer for inline row expanders.
   `card` is a DetailCard view model: { stats: [{label, value}], description }.
   Render only — no triggers/markup for the toggle (that lives in the row). #}
{% macro detail_card(card) %}
{% if card %}
<div class="detail-card">
  {% if card.stats %}
  <dl class="detail-stats">
    {% for s in card.stats %}
    <div><dt>{{ s.label }}</dt><dd>{{ s.value }}</dd></div>
    {% endfor %}
  </dl>
  {% endif %}
  {% if card.description %}<p class="detail-desc">{{ card.description }}</p>{% endif %}
</div>
{% endif %}
{% endmacro %}
```

- [ ] **Step 2: Commit**

```bash
git add aose/web/templates/_detail_card.html
git commit -m "Add detail_card Jinja macro"
```

---

## Task 6: CSS for the detail card + collapse

**Files:**
- Modify: `aose/web/static/sheet.css` (add **above** the `LEGACY / SITE-WIDE` banner)

- [ ] **Step 1: Locate the legacy banner**

Run: `.venv\Scripts\python.exe -c "import re,io; t=open('aose/web/static/sheet.css',encoding='utf-8').read(); i=t.find('LEGACY'); print(i, t[i-80:i+40])"`
Expected: prints the byte offset of the `LEGACY / SITE-WIDE` banner — insert the new rules just before that comment block.

- [ ] **Step 2: Add the zine rules**

Insert immediately above the legacy banner comment:

```css
/* ── Inline row detail cards (drawer expanders) ── */
.row-detail.collapsed { display: none; }
.row-detail > td { padding: 0; background: var(--box-sunk); }
.detail-card {
  padding: 8px 12px;
  border-top: 1px solid var(--hair);
  font-family: var(--body);
}
.detail-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 2px 12px;
  margin: 0 0 6px;
}
.detail-stats > div { display: flex; gap: 6px; align-items: baseline; }
.detail-stats dt {
  font-family: var(--display);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-size: 10px;
  color: var(--gray);
  margin: 0;
}
.detail-stats dd {
  margin: 0;
  font-size: 13px;
  color: var(--ink);
  font-variant-numeric: lining-nums tabular-nums;
}
.detail-desc { margin: 0; font-size: 13px; white-space: pre-wrap; color: var(--ink-2); }
[data-detail-toggle] { cursor: pointer; }
```

- [ ] **Step 3: Commit**

```bash
git add aose/web/static/sheet.css
git commit -m "Style inline detail cards (zine)"
```

---

## Task 7: Generalized JS toggle

**Files:**
- Modify: `aose/web/static/inventory.js`

- [ ] **Step 1: Add the row-detail toggle**

Append to `aose/web/static/inventory.js` (after the existing container IIFE):

```javascript
/* Inline row-detail toggle.
 *
 * A trigger row carries data-detail-toggle="<uid>"; its detail row carries
 * data-detail-for="<uid>" and starts with class .collapsed. Clicking the
 * trigger toggles .collapsed and flips aria-expanded. Clicks that originate
 * inside a form/button/a/select are ignored so the row's own controls (cast,
 * memorise, equip, buy, etc.) keep working. Independent toggles — no sibling
 * auto-collapse. */
(function () {
    document.addEventListener("click", function (e) {
        if (e.target.closest("form, button, a, select")) return;
        const trigger = e.target.closest("[data-detail-toggle]");
        if (!trigger) return;
        const uid = trigger.getAttribute("data-detail-toggle");
        const detail = document.querySelector(`[data-detail-for="${uid}"]`);
        if (!detail) return;
        const open = !detail.classList.toggle("collapsed");
        trigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
})();
```

- [ ] **Step 2: Commit**

```bash
git add aose/web/static/inventory.js
git commit -m "Add generalized inline row-detail toggle"
```

> No unit test for vanilla JS in this project; behaviour is covered by the
> template smoke test (Task 11) plus manual verification (Task 12).

---

## Task 8: Wire the Manage Spells drawer

**Files:**
- Modify: `aose/web/templates/sheet.html` (`drawer-spells`, ~lines 458-523)

- [ ] **Step 1: Import the macro**

At the top of `sheet.html`, beside the existing `{% from "_inv_row_actions.html" import inv_row_actions with context %}` line, add:

```jinja
{% from "_detail_card.html" import detail_card with context %}
```

- [ ] **Step 2: Make the memorised-slot row a trigger + add its detail row**

In the drawer's "Slots filled at this level" loop (`{% for sv in grp.slots %}`),
change the opening `<tr>` to a trigger and append a detail row before
`{% endfor %}`. The `uid` is unique per class + slot index:

```jinja
          {% for sv in grp.slots %}
          {% set uid = "slot-" ~ block.class_id ~ "-" ~ sv.index %}
          <tr data-detail-toggle="{{ uid }}" aria-expanded="false">
            <td>{{ sv.display_name }}</td>
            <td class="n">
              <span class="pips" style="display:inline-flex">
                {% if sv.spent %}<i class="pip spent"></i>{% else %}<i class="pip"></i>{% endif %}
              </span>
            </td>
            <td class="n">
              {# …existing cast / restore / clear forms unchanged… #}
            </td>
          </tr>
          <tr class="row-detail collapsed" data-detail-for="{{ uid }}">
            <td colspan="3">{{ detail_card(sv.detail) }}</td>
          </tr>
          {% endfor %}
```

> Keep the three existing `<form>` blocks in the third `<td>` exactly as they
> are — only the `<tr>` attributes and the new detail row are added.

- [ ] **Step 3: Make the known-spell row a trigger + add its detail row**

In the "Known spells for memorising" loop (`{% for s in block.known %}`):

```jinja
          {% for s in block.known %}
          {% set uid = "known-" ~ block.class_id ~ "-" ~ s.id %}
          <tr data-detail-toggle="{{ uid }}" aria-expanded="false">
            <td style="{% if block.caster_type == 'arcane' %}color:var(--gray){% endif %}">{{ s.name }}</td>
            <td class="n">—</td>
            <td class="n">
              {# …existing memorise / memorise(rev) / forget forms unchanged… #}
            </td>
          </tr>
          <tr class="row-detail collapsed" data-detail-for="{{ uid }}">
            <td colspan="3">{{ detail_card(s.detail) }}</td>
          </tr>
          {% endfor %}
```

- [ ] **Step 4: Verify the app renders**

Run: `.venv\Scripts\python.exe -c "from aose.web.app import app"` (import smoke — no template error on load).
Then start the server and load a caster's sheet (see Task 12). Expected: Manage
Spells drawer rows expand/collapse on click; cast/memorise buttons still work.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/sheet.html
git commit -m "Inline detail expanders in Manage Spells drawer"
```

---

## Task 9: Wire the inventory `inv_table` rows

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html` (`inv_table` macro, ~lines 41-65)

- [ ] **Step 1: Import the macro**

At the top of `_equipment_ui.html`, beside the existing
`{% from "_inv_row_actions.html" import inv_row_actions with context %}`, add:

```jinja
{% from "_detail_card.html" import detail_card with context %}
```

- [ ] **Step 2: Add a trigger + detail row to `inv_table`**

In the `inv_table` macro body, change the row loop so each `inv-row` is a
trigger and is followed by a detail row. The `uid` combines `state` + item id
(unique across the three sections):

```jinja
    {% for row in rows %}
        {% set uid = "inv-" ~ state ~ "-" ~ row.id %}
        <tr class="inv-row" data-item-id="{{ row.id }}"
            data-detail-toggle="{{ uid }}" aria-expanded="false">
            <td>{{ row.name }}</td>
            <td class="n">{{ row.count }}</td>
            <td class="n">{{ (row.weight_cn * row.count) }}&nbsp;cn</td>
            <td class="n">{{ inv_row_actions(row, target_url_prefix, state) }}</td>
        </tr>
        {% if row.detail %}
        <tr class="row-detail collapsed" data-detail-for="{{ uid }}">
            <td colspan="4">{{ detail_card(row.detail) }}</td>
        </tr>
        {% endif %}
    {% endfor %}
```

> The `inv_row_actions` cell holds the equip/stash/drop forms — they're inside
> `<td>` … `<form>`, so the JS guard (`form, button, a, select`) prevents them
> from triggering expand.

- [ ] **Step 3: Commit**

```bash
git add aose/web/templates/_equipment_ui.html
git commit -m "Inline detail expanders on Equipped/Carried/Stashed rows"
```

---

## Task 10: Wire the Documents-tab embedded spells

**Files:**
- Modify: `aose/web/templates/_equipment_ui.html` (Documents pane, ~lines 405-428)

- [ ] **Step 1: Add a trigger + detail row to the embedded-spell loop**

In the Documents pane, the inner `{% for e in src.entries %}` renders
`<tr class="child">`. Make it a trigger and append a detail row. The `uid`
combines source instance + spell id:

```jinja
    {% for e in src.entries %}
    {% set uid = "doc-" ~ src.instance_id ~ "-" ~ e.spell_id %}
    <tr class="child" data-detail-toggle="{{ uid }}" aria-expanded="false">
      <td>{{ e.name }} <span class="tag faint">L{{ e.level }}</span>
        {% if e.copy_failed %}<span class="tag stamp">copy failed</span>{% endif %}
      </td>
      <td class="n">
        {# …existing cast / copy-to-book forms unchanged… #}
      </td>
    </tr>
    {% if e.detail %}
    <tr class="row-detail collapsed" data-detail-for="{{ uid }}">
      <td colspan="2">{{ detail_card(e.detail) }}</td>
    </tr>
    {% endif %}
    {% endfor %}
```

- [ ] **Step 2: Commit**

```bash
git add aose/web/templates/_equipment_ui.html
git commit -m "Inline detail expanders on Documents-tab spell entries"
```

---

## Task 11: Template smoke test

**Files:**
- Modify: `tests/test_sheet.py`

- [ ] **Step 1: Inspect the existing sheet-render test for the helper/fixture style**

Run: `.venv\Scripts\python.exe -c "print(open('tests/test_sheet.py',encoding='utf-8').read()[:2500])"`
Expected: shows how the suite renders the sheet template (TestClient or direct
Jinja). Mirror that pattern — reuse whatever character-building helper and
render entrypoint it already uses. Identify the function that returns the
rendered HTML string for a saved character.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_sheet.py` (adapt `render_sheet_html(...)` /
character-creation to the helpers found in Step 1 — the assertions are the
contract):

```python
def test_sheet_renders_inline_detail_rows():
    # Build/save a caster character that owns at least one inventory item,
    # then render the live sheet HTML. Reuse the existing helper from this file.
    html = render_caster_sheet_html()  # <- replace with this file's actual helper

    # Detail rows exist and are collapsed by default.
    assert 'class="row-detail collapsed"' in html
    assert 'data-detail-for=' in html
    # Triggers are present.
    assert 'data-detail-toggle=' in html
    # The structured card markup renders.
    assert 'detail-card' in html
```

- [ ] **Step 3: Run test to verify it fails (then passes)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py -q -k inline_detail`
Expected: with Tasks 8-10 already committed, this should PASS once the helper is
wired correctly. If it FAILS on a missing helper name, fix the helper reference
(not the assertions). If the chosen character is a non-caster or has no items,
adjust the fixture so both a spell row and an item row render.

- [ ] **Step 4: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing `pytest-current` PermissionError).

- [ ] **Step 5: Commit**

```bash
git add tests/test_sheet.py
git commit -m "Smoke-test inline detail rows render on the sheet"
```

---

## Task 12: Manual verification

**Files:** none (manual)

- [ ] **Step 1: Start the app**

Run: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`

- [ ] **Step 2: Verify Manage Spells drawer**

Open a spellcaster's sheet → Spells group → **Manage**. Click a memorised-slot
row and a known-spell row: each expands to a structured card (Level / Range /
Duration / [Reversible] + description) and collapses on a second click. The
cast / restore / clear / memorise / forget buttons still work (do **not**
expand the row). Multiple rows can be open at once.

- [ ] **Step 3: Verify inventory drawer**

Open the **Inventory, Currency & Treasure** group → **Manage**. On the Carried
tab, click Equipped / Carried / Stashed item rows: each expands to a structured
item card (Type / Damage or AC / Cost / Weight + description). Equip / stash /
drop / sell buttons still work.

- [ ] **Step 4: Verify Documents tab**

With a character owning a spell book or scroll, open the **Documents** tab and
click an embedded spell entry: it expands to the spell card. Cast / copy-to-book
buttons still work.

- [ ] **Step 5: Verify the drawer never closes**

Confirm expanding a row never closes the drawer and never dims the screen with a
scrim — the overlay model is untouched.

---

## Self-Review notes

- **Spec coverage:** data layer (Tasks 1-4), macro (5), CSS (6), JS (7), wiring
  spells/items/documents (8-10), tests (1-4, 11), manual (12). All scoped rows
  covered: memorised slots + known spells (Task 8), Equipped/Carried/Stashed
  (Task 9), Documents embedded spells (Task 10).
- **Out of scope (not implemented), per spec:** main-sheet modals, Magic/
  Treasure/Shop rows, learnable-spell `<select>`, drag-and-drop.
- **Import cycle:** `aose/engine/detail.py` imports only `aose.models`; both
  `shop.py` and `view.py` import *from* it — no cycle.
- **Type consistency:** `DetailCard`/`StatLine` and `spell_card`/`item_card`
  names are used identically across Tasks 1-4 and the templates.
- **Interaction guard:** the JS ignores clicks inside `form, button, a, select`,
  so every existing management control in a row keeps working.
```
