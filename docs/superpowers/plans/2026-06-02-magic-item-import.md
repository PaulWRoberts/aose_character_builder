# Magic Item Compendium — Bulk YAML Import (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate every markdown source in `import/markdown/{items,magic-items}/` into book-faithful YAML game data — with full descriptions — against the already-merged Phase-1 models, adding only one small model+engine extension (rolled-at-acquisition modifiers).

**Architecture:** Almost entirely pure data entry. Three target files grow or are (re)created under `data/`: `enchantments.yaml` (combat enchantments → `Enchantment`), `data/equipment/magic_items.yaml` (potions/rings/rods/staves/wands/misc → `MagicItem`), and `data/equipment/adventuring_gear.yaml` + `containers.yaml` (re-imported with descriptions). The **one** code change is a `RolledModifier` value type that lets a `MagicItem` declare a modifier whose value is rolled when the instance is acquired (Bracers of Armour: AC 8 − 1d4) — Task 1. Verification is by tests that `GameData.load` the real `data/` dir and spot-check shapes, values, and composition.

**Tech Stack:** Python 3.14, Pydantic v2, PyYAML, pytest. Models: `aose/models/{enchantment,item,modifier}.py`. Engine: `aose/engine/{enchant,magic}.py`. Loader: `aose/data/loader.py` (`equipment/*.yaml` is auto-globbed except `weapon_qualities.yaml`; `enchantments.yaml` is loaded from the data-dir root).

---

## Depends on: the merged ammunition feature

The ammunition feature (9-task plan) is **merged on `main`**. It already provides everything the old "ammo as base weapons" idea was for, so this plan does **not** recreate any of it:

- `data/equipment/ammunition.yaml` — `arrow`, `crossbow_bolt`, `silver_arrow`, `sling_stone` (`Ammunition` items, **not** weapons).
- `data/enchantments.yaml` ammo enchantments (`kind: ammunition`): `arrows_plus_1`, `arrows_plus_2`, `arrow_slaying`, `crossbow_bolts_plus_1`, `crossbow_bolts_plus_2`, `sling_bullet_impact`. **Do not re-add these.**
- Launcher `accepts_ammo` + `groups: [bow]` on both bows already in `data/equipment/weapons.yaml`.

**Javelin is a missile weapon, not ammunition** — `javelin_of_lightning` / `javelin_of_seeking` are in scope here (Task 5), composed onto the `javelin` base weapon.

## Pre-flight: read these before starting

- Spec: `docs/superpowers/specs/2026-06-02-magic-item-import-design.md` (the contract).
- Phase-1 spec for model semantics: `docs/superpowers/specs/2026-06-02-magic-item-enchantments-design.md`.
- Models: `aose/models/enchantment.py`, `aose/models/item.py`, `aose/models/modifier.py`.
- Engine: `aose/engine/magic.py` (`new_magic_instance`), `aose/engine/enchant.py`.
- Source markdown: `import/markdown/items/advanced-fantasy_adventuring-gear.md`,
  `import/markdown/magic-items/*.md`.

**Transcription rule (not a placeholder):** Where a step says *"`description:` = the full book text from source §<Heading>"*, copy the prose verbatim from the named markdown section into the YAML `description:` field as a YAML block scalar (`description: |-`). The markdown is the authoritative text; reproducing thousands of lines of it inside this plan would only risk drift. The plan specifies every **mechanical** field (ids, bonuses, charges, modifiers, `applies_to`); the descriptions are mechanical transcription.

**The source markdown is authoritative.** There is no PDF in the repo and none is needed — the `.md` files are the source of truth. Where a numeric value is genuinely **absent from the markdown** (a few gear weights — the gear table lists only cost), the plan uses book-typical AOSE values and says so at the point of use; if an exact value matters to you, supply it, otherwise the book-typical value stands.

**Running tests (Windows, venv not auto-activated):**
```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
Baseline before starting: **863 passing** (the ammunition feature is merged). The trailing `PermissionError` on `pytest-current` is a known Windows pytest-9 tempdir quirk — ignore it.

## Flagged modeling decisions (resolved here; revisit if the user objects)

The spec says *"if a source item cannot be expressed by the Phase-1 models, stop and flag it."* Each item below involved a judgement call. They are resolved as stated and called out again at their task:

1. **Enchanted ammunition** — handled by the merged ammunition feature (see "Depends on" above). Not touched by this plan.
2. **Random-at-acquisition passive modifiers.**
   - **Bracers of Armour** (`AC 8 − 1d4`) **rolls at acquisition** via the new `rolled_modifiers` mechanism (Task 1): the catalog declares `rolled_modifiers: [{target: ac, op: set, dice: "1d4+3"}]` (the roller supports `NdX+C` but not `C−NdX`; `1d4+3` yields the same uniform set {4,5,6,7} as `8 − 1d4`), and `new_magic_instance` rolls a concrete per-instance `extra_modifier`.
   - **Gloves of Dexterity** and **Periapt of Proof Against Poison** are left **description-only** (their step/save-type effect doesn't map cleanly) with a leading `# TODO:` YAML comment to model the effect in a future pass (per user). The GM can still apply effects via `MagicItemInstance.extra_modifiers`.
   - **Cloak of Defence** (`1d8` → +1/+2/+3) stays description-only with a fixed `+1 ac`/`+1 save:all` default modifier and a note: the actual bonus is a non-linear step table (not a single die), so it is not auto-rolled; GM tunes via `extra_modifiers`.
3. **Sword +3, Defender.** The +3 is a per-round *choice* to shift the bonus from attack to AC; a passive `ac +3` would double-count with `magic_bonus: 3`. Resolved: `magic_bonus: 3` only; the AC-transfer option is description-only. (User-confirmed.)
4. **`generic_plus_1`** (any_weapon, exclude sword) is **kept** though the book chart has only per-type weapon bonuses — three real-data tests depend on its id. It coexists as a convenience generic.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `aose/models/modifier.py` | Modify | Add `RolledModifier` value type (Task 1) |
| `aose/models/item.py` | Modify | `MagicItem.rolled_modifiers: list[RolledModifier]` (Task 1) |
| `aose/models/__init__.py` | Modify | Export `RolledModifier` (Task 1) |
| `aose/engine/magic.py` | Modify | Roll `rolled_modifiers` into `extra_modifiers` in `new_magic_instance` (Task 1) |
| `data/enchantments.yaml` | Append (keep tested + ammo ids) | Sword / weapon / armour / shield enchantments from the combat files |
| `data/equipment/magic_items.yaml` | Create | Potions, rings, rods/staves/wands, miscellaneous items (`MagicItem`) |
| `data/equipment/adventuring_gear.yaml` | Rewrite | Gear from the gear markdown, **with descriptions**, ids preserved |
| `data/equipment/containers.yaml` | Modify | Reconcile Backpack/Sacks with gear markdown; add `description`; Bag of Holding gets `magic: true` + description |
| `tests/test_magic_item_import.py` | Create | Load-and-spot-check tests for every task |

> `data/equipment/weapons.yaml` is **not** modified — all weapon group tags needed for enchantment composition already exist (bows `[bow]`, axes `[axe]`, swords `[sword]`, trident `[trident]`; every other type matches its enchantment by `id`).

**Tested seed ids that MUST survive** (real-data tests reference them — do not rename or drop): `generic_plus_1`, `sword_plus_1`, `sword_plus_1_vs_undead`, `luck_blade`, `armour_plus_1`, `shield_plus_1`, `trident_fish_command`, plus the merged ammo enchantments listed under "Depends on". Base items referenced by tests: `torch`, `sword`, `short_sword`, `battle_axe`, `chain_mail`, `shield`, `backpack`. `trident_fish_command.charge_dice` may change value (a test only asserts it is non-null).

---

## Task 1: Rolled-at-acquisition modifiers (model + engine)

The **only** code change in this plan. A `MagicItem` can declare modifiers whose values are rolled when an instance is created (Bracers of Armour). Used by Task 9.

**Files:**
- Modify: `aose/models/modifier.py`
- Modify: `aose/models/item.py`
- Modify: `aose/models/__init__.py`
- Modify: `aose/engine/magic.py`
- Create: `tests/test_magic_item_import.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_magic_item_import.py`:
```python
"""Phase-2 bulk magic-item import: load-and-spot-check against real data."""
import random
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Armor, MagicItem, Weapon

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_rolled_modifier_rolls_into_extra_modifiers():
    """A MagicItem.rolled_modifiers entry becomes a concrete per-instance
    extra_modifier with a rolled value when the instance is created."""
    from aose.engine.magic import new_magic_instance
    d = GameData()
    d.items["test_bracers"] = MagicItem(
        id="test_bracers", name="Test Bracers", category="x", item_type="magic",
        cost_gp=0, magic=True, equippable=True,
        rolled_modifiers=[{"target": "ac", "op": "set", "dice": "1d4+3"}],
    )
    inst = new_magic_instance("test_bracers", d, rng=random.Random(1))
    assert len(inst.extra_modifiers) == 1
    m = inst.extra_modifiers[0]
    assert m.target == "ac" and m.op == "set" and 4 <= m.value <= 7
```

- [ ] **Step 2: Run it, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py -q`
Expected: FAIL — `MagicItem` has no `rolled_modifiers` field (pydantic `extra="forbid"` raises).

- [ ] **Step 3: Add the `RolledModifier` value type**

In `aose/models/modifier.py`, append:
```python
class RolledModifier(BaseModel):
    """A modifier whose value is rolled when the item *instance* is created
    (e.g. Bracers of Armour: AC 8 − 1d4).  At acquisition,
    ``new_magic_instance`` rolls ``dice`` and appends a concrete
    ``Modifier{target, op, value}`` to the instance's ``extra_modifiers``.
    """
    model_config = ConfigDict(extra="forbid")

    target: str
    op: Literal["add", "set", "set_min", "set_max"]
    dice: str
```

- [ ] **Step 4: Add `MagicItem.rolled_modifiers`**

In `aose/models/item.py`, import the type and add the field to `MagicItem`:
```python
from aose.models.modifier import Modifier, RolledModifier   # adjust existing import line
```
```python
class MagicItem(ItemBase):
    item_type: Literal["magic"]
    equippable: bool = False
    modifiers: list[Modifier] = Field(default_factory=list)
    rolled_modifiers: list[RolledModifier] = Field(default_factory=list)  # rolled at acquisition
    max_charges: int | None = None     # fixed charge ceiling, OR…
    charge_dice: str | None = None     # …rolled at acquisition (e.g. "2d6")
```

- [ ] **Step 5: Export `RolledModifier`**

In `aose/models/__init__.py`, add `RolledModifier` to the modifier import line and to `__all__` (next to `Modifier`).

- [ ] **Step 6: Roll them in `new_magic_instance`**

In `aose/engine/magic.py`, in `new_magic_instance`, build the rolled extra-modifiers and pass them to the instance (`Modifier` and `roll` are already imported):
```python
    extra: list[Modifier] = [
        Modifier(target=rm.target, op=rm.op, value=roll(rm.dice, rng))
        for rm in item.rolled_modifiers
    ]
    return MagicItemInstance(
        instance_id=uuid.uuid4().hex,
        catalog_id=catalog_id,
        equipped=False,
        charges_max=charges_max,
        charges_remaining=charges_max,
        extra_modifiers=extra,
    )
```
Also extend `needs_instance` so a rolled-only item is still tracked:
```python
    return isinstance(item, MagicItem) and (
        item.equippable or item.max_charges is not None
        or item.charge_dice is not None or bool(item.rolled_modifiers)
    )
```

- [ ] **Step 7: Run the test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py -q`
Expected: PASS (1 test).

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 864 passing (863 baseline + 1). The new field is optional with an empty default — no existing data or test is affected.

- [ ] **Step 9: Commit**
```powershell
git add aose/models/modifier.py aose/models/item.py aose/models/__init__.py aose/engine/magic.py tests/test_magic_item_import.py
git commit -m "feat(magic): rolled-at-acquisition modifiers (Bracers of Armour)"
```

---

## Task 2: Adventuring gear + containers re-import (with descriptions)

Re-import `adventuring_gear.yaml` from `import/markdown/items/advanced-fantasy_adventuring-gear.md` **with descriptions**, preserving existing ids that are referenced elsewhere. Reconcile container entries with `containers.yaml`.

**Source:** `import/markdown/items/advanced-fantasy_adventuring-gear.md` (table + `### Descriptions` + `### Other Equipment`).

**Id reconciliation** — keep these existing ids (referenced or already present): `crowbar, flask_of_oil, holy_water_vial, iron_rations, standard_rations, lantern, mirror_small, rope_50ft, stakes_and_mallet, thieves_tools, tinder_box, torch, waterskin, wine_skin, bedroll, candle`. Add new ids from the markdown table not yet present: `garlic, grappling_hook, hammer_small, holy_symbol, iron_spikes, pole_10ft, wolfsbane`. (`bedroll`/`candle` are not in the markdown table but are kept — they're harmless and avoid a needless delete; they get no new description.)

**Weights:** keep existing `weight_cn` values for kept ids. The markdown table gives only **cost**, not weight, so new items use book-typical AOSE weights (`garlic` 0, `grappling_hook` 80, `hammer_small` 10, `holy_symbol` 10, `iron_spikes` 10, `pole_10ft` 100, `wolfsbane` 0). These weights are **not in the source markdown**; if exact encumbrance matters, supply them — otherwise the book-typical values stand.

**Files:**
- Rewrite: `data/equipment/adventuring_gear.yaml`
- Modify: `data/equipment/containers.yaml`
- Test: `tests/test_magic_item_import.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_magic_item_import.py`:
```python
def test_gear_preserves_referenced_ids(data):
    for gid in ("torch", "crowbar", "lantern", "waterskin", "thieves_tools"):
        assert gid in data.items
    # torch weight unchanged from the pre-import catalog
    assert data.items["torch"].weight_cn == 20


def test_gear_has_descriptions(data):
    assert data.items["crowbar"].description
    assert "forcing doors" in data.items["crowbar"].description.lower()


def test_gear_adds_new_markdown_items(data):
    for gid in ("garlic", "grappling_hook", "holy_symbol", "wolfsbane", "pole_10ft"):
        assert gid in data.items


def test_containers_have_descriptions(data):
    bp = data.items["backpack"]
    assert "400 coins" in (bp.description or "")
    # Bag of Holding is flagged as magic now
    assert data.items["bag_of_holding"].magic is True
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py -q`
Expected: FAIL — `crowbar.description` is `None`; `garlic` missing.

- [ ] **Step 3: Rewrite `adventuring_gear.yaml`**

Rewrite the whole file. Every entry keeps `item_type: gear`, `category: adventuring_gear`, `cost_gp` from the markdown table, `weight_cn` per the reconciliation rule above, and `description: |-` transcribed from the matching `**<Item>:**` paragraph in source §Descriptions / §Other Equipment. Backpack and the two Sacks live in `containers.yaml` (Step 4), not here. Example entries (full set follows this shape — transcribe every row of the markdown table except the three containers):
```yaml
- id: crowbar
  item_type: gear
  name: Crowbar
  category: adventuring_gear
  cost_gp: 10
  weight_cn: 50
  description: |-
    2–3' long and made of solid iron. Can be used for forcing doors and
    other objects open.

- id: garlic
  item_type: gear
  name: Garlic
  category: adventuring_gear
  cost_gp: 5
  weight_cn: 0
  description: |-
    A bunch of garlic. (See the referee's notes on its uses against certain
    monsters.)

- id: holy_water_vial
  item_type: gear
  name: Holy Water, Vial
  category: adventuring_gear
  cost_gp: 25
  weight_cn: 10
  description: |-
    Water that has been blessed by a holy person… (transcribe the full
    **Holy water:** paragraph from source §Descriptions).
```
Full id/name/cost list to produce (containers excluded): `garlic`(5), `crowbar`(10), `grappling_hook`(25, name "Grappling Hook"), `hammer_small`(2, "Hammer, Small"), `holy_symbol`(25, "Holy Symbol"), `holy_water_vial`(25, "Holy Water, Vial"), `iron_spikes`(1, "Iron Spikes (12)"), `lantern`(10), `mirror_small`(5, "Mirror, Small Steel"), `flask_of_oil`(2, "Oil, Flask"), `pole_10ft`(1, "Pole, 10'"), `iron_rations`(15, "Rations, Iron (7 days)"), `standard_rations`(5, "Rations, Standard (7 days)"), `rope_50ft`(1, "Rope, 50'"), `stakes_and_mallet`(3, "Wooden Stakes (3) & Mallet"), `thieves_tools`(25, "Thieves' Tools"), `tinder_box`(3, "Tinder Box (flint & steel)"), `torch`(1, weight 20), `waterskin`(1), `wine_skin`(1, "Wine, Skin"), `wolfsbane`(10, "Wolfsbane"). Keep `bedroll`(1, weight 30) and `candle`(1, weight 0) as-is with no description.

- [ ] **Step 4: Reconcile `containers.yaml`**

Edit `data/equipment/containers.yaml`: add `description: |-` (transcribed) to `backpack`, `sack_small`, `sack_large` (the gear markdown gives Backpack "Holds up to 400 coins", Sack large "600 coins", Sack small "200 coins"). Leave `saddle_bags` as-is (add a short description). For `bag_of_holding`, add `magic: true` and `description: |-` (transcribe from the misc markdown §Bag of Holding in Task 9). Keep all existing `capacity_cn`/`weight_multiplier`/`cost_gp` values. Example:
```yaml
- id: backpack
  name: Backpack
  category: containers
  item_type: container
  cost_gp: 5
  weight_cn: 80
  capacity_cn: 400
  weight_multiplier: 1.0
  description: |-
    Has two straps and can be worn on the back, keeping the hands free.
    Holds up to 400 coins.
```

- [ ] **Step 5: Run the new tests, verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: still green (container/encumbrance tests unaffected — ids and numeric fields unchanged).

- [ ] **Step 7: Commit**
```powershell
git add data/equipment/adventuring_gear.yaml data/equipment/containers.yaml tests/test_magic_item_import.py
git commit -m "feat(data): re-import adventuring gear + containers with descriptions"
```

---

## Task 3: Armour & shield enchantments

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-armour-and-shields.md`.
**Target:** append to `data/enchantments.yaml` (keep existing `armour_plus_1` / `shield_plus_1`).

Per spec: `Armour +N` → `kind: armor, include: [any_armour]`, `magic_bonus: N`; `Shield +N` → `kind: shield, include: [any_shield]`; cursed AC penalty → negative `magic_bonus`; `Cursed … AC 9 [10]` → `modifiers: [{target: ac, op: set, value: 9}]`; `cursed: true` on cursed entries. Each gets a `description` transcribed from the relevant source paragraph (use the §Enchanted / §Cursed explanatory text + a one-line summary).

**Enumeration** (id → fields):

| id | kind | magic_bonus | modifiers | cursed | description source |
|---|---|---|---|---|---|
| `armour_plus_1` *(keep)* | armor | 1 | — | — | §Enchanted Armour and Shields |
| `armour_plus_2` | armor | 2 | — | — | §Enchanted … |
| `armour_plus_3` | armor | 3 | — | — | §Enchanted … |
| `shield_plus_1` *(keep)* | shield | 1 | — | — | §Enchanted … |
| `shield_plus_2` | shield | 2 | — | — | §Enchanted … |
| `shield_plus_3` | shield | 3 | — | — | §Enchanted … |
| `cursed_armour_minus_1` | armor | -1 | — | true | §Cursed Armour and Shields (AC penalty) |
| `cursed_armour_minus_2` | armor | -2 | — | true | §Cursed … |
| `cursed_armour_ac_9` | armor | 0 | `[{target: ac, op: set, value: 9}]` | true | §Cursed … (AC 9 [10]) |
| `cursed_shield_minus_2` | shield | -2 | — | true | §Cursed … |
| `cursed_shield_ac_9` | shield | 0 | `[{target: ac, op: set, value: 9}]` | true | §Cursed … (AC 9 [10]) |

All use `name_template: "{base} +N"` (e.g. `"{base} +2"`); cursed AC-penalty use `"{base} -1"` etc.; AC-9 cursed use `"{base} (Cursed, AC 9)"`. `include` is `[any_armour]` for armor, `[any_shield]` for shield.

**Files:** Modify `data/enchantments.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_armour_shield_enchantments(data):
    e = data.enchantments
    assert e["armour_plus_3"].kind == "armor" and e["armour_plus_3"].magic_bonus == 3
    assert e["shield_plus_2"].kind == "shield" and e["shield_plus_2"].magic_bonus == 2
    assert e["cursed_armour_minus_1"].magic_bonus == -1
    assert e["cursed_armour_minus_1"].cursed is True
    ac9 = e["cursed_armour_ac_9"]
    assert ac9.cursed is True
    assert ac9.modifiers[0].target == "ac" and ac9.modifiers[0].op == "set"
    assert ac9.modifiers[0].value == 9
```

- [ ] **Step 2: Run, verify failure**
Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py::test_armour_shield_enchantments -q` → FAIL (`KeyError: 'armour_plus_3'`).

- [ ] **Step 3: Append the enchantments**

Append the new armor/shield entries to `data/enchantments.yaml` (the two `+1` entries already exist — leave them). Example block:
```yaml
- id: armour_plus_2
  name_template: "{base} +2"
  kind: armor
  applies_to: {include: [any_armour]}
  magic_bonus: 2
  description: "+2 bonus to Armour Class. Enchanted armour weighs half as much."

- id: cursed_armour_ac_9
  name_template: "{base} (Cursed, AC 9)"
  kind: armor
  applies_to: {include: [any_armour]}
  cursed: true
  modifiers: [{target: ac, op: set, value: 9}]
  description: |-
    All tests indicate a +1 bonus, but in deadly combat the curse sets the
    wearer's base Armour Class to 9 [10] (before Dexterity). Cannot be removed
    without magic.
```

- [ ] **Step 4: Run the test, verify pass** → `pytest …::test_armour_shield_enchantments -q` PASS.
- [ ] **Step 5: Run the full suite** → green (existing `armour_plus_1`/`shield_plus_1` untouched).
- [ ] **Step 6: Commit**
```powershell
git add data/enchantments.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic armour and shield enchantments"
```

---

## Task 4: Sword enchantments

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-magic-swords.md`.
**Target:** append to `data/enchantments.yaml` (keep `sword_plus_1`, `sword_plus_1_vs_undead`, `luck_blade`, `short_sword_of_quickness`).

All `kind: weapon`. `include: [sword]` except where type-locked. `conditional_bonus.bonus` is the **additional** amount on top of `magic_bonus` (so "+1, +3 vs X" = `magic_bonus: 1, conditional_bonus: {vs: X, bonus: 2}`). Passive side-effects → `modifiers`; activated/charged powers → `description` (+ `charge_dice`/`max_charges` where the power has a finite count). Cursed → `cursed: true` + negative `magic_bonus`. `name_template` is the chart label with `{base}` substituted for "Sword" (e.g. `"{base} +1, +3 vs Undead"`).

**Enumeration:**

| id | magic_bonus | conditional_bonus | modifiers | charges | cursed | include |
|---|---|---|---|---|---|---|
| `short_sword_of_quickness` *(keep; fix bonus→2)* | 2 | — | — | — | — | `[short_sword]` |
| `sword_minus_1_berserker` | -1 | — | — | — | true | `[sword]` |
| `sword_minus_1_cursed` | -1 | — | — | — | true | `[sword]` |
| `sword_minus_2_cursed` | -2 | — | — | — | true | `[sword]` |
| `sword_plus_1` *(keep)* | 1 | — | — | — | — | `[sword]` |
| `sword_plus_1_vs_lycanthropes` | 1 | `{vs: lycanthropes, bonus: 1}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_spell_users` | 1 | `{vs: spell users, bonus: 1}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_dragons` | 1 | `{vs: dragons, bonus: 2}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_enchanted` | 1 | `{vs: enchanted creatures, bonus: 2}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_regenerating` | 1 | `{vs: regenerating creatures, bonus: 2}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_reptiles` | 1 | `{vs: reptiles, bonus: 2}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_shapechangers` | 1 | `{vs: shape changers, bonus: 2}` | — | — | — | `[sword]` |
| `sword_plus_1_vs_undead` *(keep)* | 1 | `{vs: undead, bonus: 2}` | — | — | — | `[sword]` |
| `sword_dragon_slayer` | 1 | — | — | — | — | `[sword]` |
| `sword_energy_drain` | 1 | — | — | `charge_dice: "1d4+4"` | — | `[sword]` |
| `sword_flaming` | 1 | — | — | — | — | `[sword]` |
| `sword_frost_brand` | 1 | — | — | — | — | `[sword]` |
| `sword_giant_slayer` | 1 | — | — | — | — | `[sword]` |
| `sword_light` | 1 | — | — | — | — | `[sword]` |
| `sword_locate_objects` | 1 | — | — | — | — | `[sword]` |
| `luck_blade` *(keep; add charges)* | 1 | — | `[{target: "save:all", op: add, value: 1}]` | `charge_dice: "1d4"` | — | `[sword]` |
| `sword_sharpness` | 1 | — | — | — | — | `[sword]` |
| `sword_sun_blade` | 1 | — | — | — | — | `[sword]` |
| `sword_wishes` | 1 | — | — | `charge_dice: "1d4"` | — | `[sword]` |
| `sword_wounding` | 1 | — | — | — | — | `[sword]` |
| `sword_plus_2` | 2 | — | — | — | — | `[sword]` |
| `sword_charm_person` | 2 | — | — | — | — | `[sword]` |
| `sword_dancing` | 2 | — | — | — | — | `[sword]` |
| `sword_nine_lives_stealer` | 2 | — | — | `max_charges: 9` | — | `[sword]` |
| `sword_venger` | 2 | — | — | — | — | `[sword]` |
| `sword_vorpal` | 2 | — | — | — | — | `[sword]` |
| `sword_plus_3` | 3 | — | — | — | — | `[sword]` |
| `sword_defender` | 3 | — | — | — | — | `[sword]` (Flagged Decision #3 — AC option is description-only) |
| `sword_holy_avenger` | 3 | — | `[{target: "save:spells", op: add, value: 4}]` | — | — | `[sword]` |

`description:` for each = the matching `## <heading>` section from the swords markdown (the chart-only `+N` and `vs` entries use the §Enchanted Swords / §Cursed Swords explanatory text + a one-line summary).

**Files:** Modify `data/enchantments.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_sword_enchantments(data):
    e = data.enchantments
    assert e["short_sword_of_quickness"].magic_bonus == 2          # corrected to +2
    assert e["short_sword_of_quickness"].applies_to.include == ["short_sword"]
    vsdrag = e["sword_plus_1_vs_dragons"]
    assert vsdrag.magic_bonus == 1 and vsdrag.conditional_bonus.bonus == 2
    assert e["sword_minus_1_berserker"].cursed is True
    assert e["sword_minus_1_berserker"].magic_bonus == -1
    assert e["sword_energy_drain"].charge_dice == "1d4+4"
    assert e["sword_nine_lives_stealer"].max_charges == 9
    assert e["sword_holy_avenger"].modifiers[0].target == "save:spells"
    assert e["sword_holy_avenger"].modifiers[0].value == 4
    assert e["sword_defender"].magic_bonus == 3 and e["sword_defender"].modifiers == []
    assert e["luck_blade"].charge_dice == "1d4"   # wishes added; save mod preserved
    assert e["luck_blade"].modifiers[0].target == "save:all"
```

- [ ] **Step 2: Run, verify failure** → FAIL (`short_sword_of_quickness.magic_bonus == 1` currently).
- [ ] **Step 3: Apply edits** — change `short_sword_of_quickness.magic_bonus` 1→2; add `charge_dice: "1d4"` to `luck_blade`; append all new sword entries per the table.
- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Run the full suite** — green. (Re-check `test_seed_enchantments_load` and `test_enchantments.py` real-data tests still pass; only additions + two value tweaks were made to kept ids, neither of which any test pins.)
- [ ] **Step 6: Commit**
```powershell
git add data/enchantments.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic sword enchantments"
```

---

## Task 5: Weapon (non-sword, non-ammunition) enchantments

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-magic-weapons.md`.
**Target:** append to `data/enchantments.yaml` (keep `trident_fish_command`, fix its `charge_dice` to `1d4+16`).

All `kind: weapon`, per-weapon-type `include`. Same conditional/modifier/charge/cursed rules as Task 4.

> **Ammunition enchantments are already merged** (`arrows_plus_1/2`, `arrow_slaying`, `crossbow_bolts_plus_1/2`, `sling_bullet_impact` — `kind: ammunition`). **Do not add them here.** This task covers only the *launcher* and *melee/thrown* weapon enchantments. Javelin is a missile weapon (not ammo), so its specials are in scope.

**Enumeration:**

| id | magic_bonus | conditional / charges | cursed | include |
|---|---|---|---|---|
| `axe_plus_1` | 1 | — | — | `[axe]` |
| `axe_plus_2` | 2 | — | — | `[axe]` |
| `bow_plus_1` | 1 | — | — | `[bow]` |
| `crossbow_distance` | 1 | desc | — | `[crossbow]` |
| `crossbow_speed` | 1 | desc | — | `[crossbow]` |
| `crossbow_accuracy` | 2 | desc | — | `[crossbow]` |
| `dagger_plus_1` | 1 | — | — | `[dagger]` |
| `dagger_buckle` | 1 | desc | — | `[dagger]` |
| `dagger_throwing` | 1 | desc | — | `[dagger]` |
| `dagger_venomous` | 1 | desc | — | `[dagger]` |
| `dagger_plus_2_vs_goblinoids` | 2 | `conditional_bonus: {vs: "orcs, goblins, and kobolds", bonus: 1}` | — | `[dagger]` |
| `dagger_biter` | 2 | desc | — | `[dagger]` |
| `javelin_of_lightning` | 0 | desc (consumed on hit) | — | `[javelin]` |
| `javelin_of_seeking` | 0 | desc (+6 seeking, single use) | — | `[javelin]` |
| `mace_plus_1` | 1 | — | — | `[mace]` |
| `mace_disrupting` | 1 | desc | — | `[mace]` |
| `mace_plus_2` | 2 | — | — | `[mace]` |
| `mace_plus_3` | 3 | — | — | `[mace]` |
| `sling_plus_1` | 1 | — | — | `[sling]` |
| `spear_backbiter` | -1 | desc | true | `[spear]` |
| `spear_plus_1` | 1 | — | — | `[spear]` |
| `spear_plus_2` | 2 | — | — | `[spear]` |
| `spear_plus_3` | 3 | — | — | `[spear]` |
| `staff_growing` | 1 | desc | — | `[staff]` |
| `trident_yearning` | -2 | desc | true | `[trident]` |
| `trident_fish_command` *(keep; charge_dice→1d4+16)* | 1 | `charge_dice: "1d4+16"` | — | `[trident]` |
| `trident_submission` | 1 | `charge_dice: "1d4+16"` | — | `[trident]` |
| `trident_warning` | 2 | `charge_dice: "1d6+18"` | — | `[trident]` |
| `war_hammer_plus_1` | 1 | — | — | `[war_hammer]` |
| `war_hammer_plus_2` | 2 | — | — | `[war_hammer]` |
| `war_hammer_dwarven_thrower` | 3 | desc | — | `[war_hammer]` |
| `war_hammer_thunderbolts` | 3 | desc | — | `[war_hammer]` |

`name_template` = chart label (e.g. `"{base} +1"`, `"{base} +2, +3 vs Goblinoids"`, `"{base} of Lightning"`, `"{base} +3, Dwarven Thrower"`). `description:` from the matching `## <heading>` (plain `+N` types reuse §Enchanted Weapons text + a summary line).

> The base weapons these compose onto all already match: `axe` group on battle_axe/hand_axe, `bow` group on bows, `trident` group on trident, and every other (`crossbow`, `dagger`, `javelin`, `mace`, `sling`, `spear`, `staff`, `war_hammer`) matches its `include` token by `id`. No `weapons.yaml` change is needed.

**Files:** Modify `data/enchantments.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_weapon_enchantments(data):
    e = data.enchantments
    assert e["axe_plus_2"].magic_bonus == 2 and e["axe_plus_2"].applies_to.include == ["axe"]
    assert e["war_hammer_dwarven_thrower"].magic_bonus == 3
    assert e["spear_backbiter"].cursed is True and e["spear_backbiter"].magic_bonus == -1
    cb = e["dagger_plus_2_vs_goblinoids"]
    assert cb.magic_bonus == 2 and cb.conditional_bonus.bonus == 1
    assert e["trident_fish_command"].charge_dice == "1d4+16"
    assert e["trident_warning"].charge_dice == "1d6+18"
    assert e["javelin_of_seeking"].applies_to.include == ["javelin"]


def test_weapon_enchantment_composes_on_base(data):
    from aose.engine.enchant import new_enchanted_instance, resolve_instance
    inst = new_enchanted_instance("battle_axe", "axe_plus_1", data)
    resolved = resolve_instance(inst, data)
    assert resolved.magic_bonus == 1
    assert resolved.base_weapon == "battle_axe"
```

- [ ] **Step 2: Run, verify failure** → FAIL (`KeyError: 'axe_plus_2'`).
- [ ] **Step 3: Apply edits** — fix `trident_fish_command.charge_dice` → `"1d4+16"`; append all weapon entries from the table (ammunition enchantments excluded — they already exist).
- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full suite** — green (check `test_enchanted_equip_charge_note_remove_roundtrip`, which uses `trident_fish_command`, still passes — it only reads `charges_remaining`, not the dice string).
- [ ] **Step 6: Commit**
```powershell
git add data/enchantments.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic (non-sword) weapon enchantments"
```

---

## Task 6: Potions (`MagicItem`, description-only)

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-potions.md`.
**Target:** create `data/equipment/magic_items.yaml` (this task seeds the file; later tasks append).

Each potion → `MagicItem` with `item_type: magic`, `magic: true`, `cost_gp: 0`, `category: magic_potions`, `equippable: false`, no modifiers/charges, `description: |-` from the matching `## Potion of <X>` section. (Potions are consumed/temporary — even AC/save boosts like Invulnerability are temporary, so **description-only**, no modifiers, per spec.)

**Ids** (26): `potion_clairaudience, potion_clairvoyance, potion_control_animal, potion_control_dragon, potion_control_giant, potion_control_human, potion_control_plant, potion_control_undead, potion_delusion, potion_diminution, potion_esp, potion_fire_resistance, potion_flying, potion_gaseous_form, potion_giant_strength, potion_growth, potion_healing, potion_heroism, potion_invisibility, potion_invulnerability, potion_levitation, potion_longevity, potion_poison, potion_polymorph_self, potion_speed, potion_treasure_finding`.

**Files:** Create `data/equipment/magic_items.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_potions_loaded(data):
    potions = [i for i in data.items.values()
               if isinstance(i, MagicItem) and i.category == "magic_potions"]
    assert len(potions) == 26
    heal = data.items["potion_healing"]
    assert heal.magic is True and heal.equippable is False
    assert heal.cost_gp == 0 and heal.description
    assert heal.modifiers == [] and heal.charge_dice is None
```

- [ ] **Step 2: Run, verify failure** → FAIL (`KeyError: 'potion_healing'`).
- [ ] **Step 3: Create the file** with all 26 potions. Header + example:
```yaml
# Magic items (Phase-2 import): potions, rings, rods/staves/wands, misc.
# All MagicItem variants. cost_gp: 0 (Add-only, GM grant). Descriptions are
# transcribed verbatim from import/markdown/magic-items/*.md.

- id: potion_healing
  item_type: magic
  name: Potion of Healing
  category: magic_potions
  cost_gp: 0
  magic: true
  equippable: false
  description: |-
    Has one of two effects on the character who drinks it:
    1. Healing a living subject: Restores 1d6+1 hit points of damage. This
       cannot grant more hit points than the subject's normal maximum.
    2. Curing paralysis: Paralysing effects are negated.
```

- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full suite** — green (new file is auto-globbed by the equipment loader).
- [ ] **Step 6: Commit**
```powershell
git add data/equipment/magic_items.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic potions"
```

---

## Task 7: Rings (`MagicItem`, equippable; passive modifiers where continuous)

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-rings.md`.
**Target:** append to `data/equipment/magic_items.yaml`.

`category: magic_rings`, `equippable: true` (rings are worn, continuous), `cost_gp: 0`, `magic: true`. Passive `modifiers` only where the worn effect continuously changes a modelled stat (Protection → AC + saves; Weakness → STR). Activated powers (control, invisibility, djinni, telekinesis, x-ray, water walking, regeneration heals) → description-only. Charged rings → `charge_dice`.

**Enumeration:**

| id | modifiers | charges | notes |
|---|---|---|---|
| `ring_control_animals` | — | — | desc |
| `ring_control_humans` | — | — | desc |
| `ring_control_plants` | — | — | desc |
| `ring_delusion` | — | — | desc |
| `ring_djinni_summoning` | — | — | desc (1/day) |
| `ring_fire_resistance` | — | — | desc |
| `ring_invisibility` | — | — | desc |
| `ring_protection_plus_1` | `[{target: ac, op: add, value: 1}, {target: "save:all", op: add, value: 1}]` | — | desc |
| `ring_protection_plus_1_5ft` | `[{target: ac, op: add, value: 1}, {target: "save:all", op: add, value: 1}]` | — | desc (5' radius aids allies — narrative) |
| `ring_regeneration` | — | — | desc (heal = play-state) |
| `ring_spell_storing` | — | `charge_dice: "1d6"` | desc |
| `ring_spell_turning` | — | `charge_dice: "2d6"` | desc |
| `ring_telekinesis` | — | — | desc |
| `ring_water_walking` | — | — | desc |
| `ring_weakness` | `[{target: "ability:STR", op: set, value: 3}]` | — | desc (cursed — note in text; `MagicItem` has no cursed flag) |
| `ring_wishes_1_2` | — | `charge_dice: "1d2"` | desc |
| `ring_wishes_1_3` | — | `charge_dice: "1d3"` | desc |
| `ring_wishes_2_4` | — | `charge_dice: "1d3+1"` | desc |
| `ring_xray_vision` | — | — | desc |

**Files:** Modify `data/equipment/magic_items.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_rings_loaded(data):
    prot = data.items["ring_protection_plus_1"]
    assert prot.equippable is True and prot.category == "magic_rings"
    targets = {(m.target, m.op, m.value) for m in prot.modifiers}
    assert ("ac", "add", 1) in targets
    assert ("save:all", "add", 1) in targets
    weak = data.items["ring_weakness"]
    assert weak.modifiers[0].target == "ability:STR"
    assert weak.modifiers[0].op == "set" and weak.modifiers[0].value == 3
    assert data.items["ring_spell_turning"].charge_dice == "2d6"
    assert data.items["ring_wishes_2_4"].charge_dice == "1d3+1"
```

- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Append all ring entries.** Example:
```yaml
- id: ring_protection_plus_1
  item_type: magic
  name: Ring of Protection +1
  category: magic_rings
  cost_gp: 0
  magic: true
  equippable: true
  modifiers:
    - {target: ac, op: add, value: 1}
    - {target: "save:all", op: add, value: 1}
  description: |-
    Grants a measure of protection from harm:
    Armour Class: A +1 AC bonus.
    Saving throws: A +1 bonus to all saves.
```

- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full suite — green.**
- [ ] **Step 6: Commit**
```powershell
git add data/equipment/magic_items.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic rings"
```

---

## Task 8: Rods, staves, and wands (`MagicItem`, charged)

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-rods-staves-wands.md`.
**Target:** append to `data/equipment/magic_items.yaml`.

`category: magic_rods_staves_wands`, `cost_gp: 0`, `magic: true`, `equippable: false` (held/activated, not worn-continuous). Charge defaults: **rods `charge_dice: "1d10"`, staves `"3d10"`, wands `"2d10"`**, unless the item states otherwise. Items that explicitly say "No charges / unlimited" get **no** `charge_dice`. Description-only otherwise.

**Charge overrides / exceptions:**
- `rod_immovable` — no charges.
- `rod_absorption` — `max_charges: 50`.
- `rod_cancellation` — `max_charges: 1`.
- `rod_parrying` — no charges.
- `staff_healing` — no charges (unlimited).
- `staff_snakes` — no charges.
- everything else: rods `1d10`, staves `3d10`, wands `2d10`.

**Ids** — Rods: `rod_immovable, rod_absorption, rod_cancellation, rod_captivation, rod_lordly_might, rod_parrying, rod_resurrection, rod_striking`. Staves: `staff_commanding, staff_dispelling, staff_healing, staff_power, staff_snakes, staff_striking, staff_swarming_insects, staff_of_the_healer, staff_withering, staff_wizardry, staff_of_the_woodlands`. Wands: `wand_cold, wand_enemy_detection, wand_fear, wand_fire_balls, wand_illusion, wand_lightning_bolts, wand_magic_detection, wand_magic_missiles, wand_metal_detection, wand_negation, wand_paralysation, wand_polymorph, wand_radiance, wand_secret_door_detection, wand_summoning, wand_trap_detection`.

`description:` from the matching `## <heading>` (include the Rod-of-Resurrection charge table text in its description).

**Files:** Modify `data/equipment/magic_items.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_rods_staves_wands_loaded(data):
    assert data.items["rod_striking"].charge_dice == "1d10"
    assert data.items["staff_striking"].charge_dice == "3d10"
    assert data.items["wand_fire_balls"].charge_dice == "2d10"
    assert data.items["rod_absorption"].max_charges == 50
    assert data.items["rod_absorption"].charge_dice is None
    assert data.items["rod_cancellation"].max_charges == 1
    assert data.items["rod_immovable"].charge_dice is None
    assert data.items["staff_healing"].charge_dice is None
    rsw = [i for i in data.items.values()
           if isinstance(i, MagicItem) and i.category == "magic_rods_staves_wands"]
    assert len(rsw) == 35
```

- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Append all 35 entries.** Examples:
```yaml
- id: rod_striking
  item_type: magic
  name: Rod of Striking
  category: magic_rods_staves_wands
  cost_gp: 0
  magic: true
  equippable: false
  charge_dice: "1d10"
  description: |-
    A rod which can be used as a weapon and is especially potent against
    constructs and chaotic extra-planar monsters. (transcribe full section)

- id: rod_absorption
  item_type: magic
  name: Rod of Absorption
  category: magic_rods_staves_wands
  cost_gp: 0
  magic: true
  equippable: false
  max_charges: 50
  description: |-
    Absorbs spells cast at the character… The rod has 50 charges. (full text)
```

- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full suite — green.**
- [ ] **Step 6: Commit**
```powershell
git add data/equipment/magic_items.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic rods, staves, and wands"
```

---

## Task 9: Miscellaneous magic items (`MagicItem`; passive/rolled modifiers for stat items)

**Source:** `import/markdown/magic-items/advanced-fantasy_miscellaneous-magic-items.md` (~131 items across four `Miscellaneous Magic Items I–IV` tables + per-item `## <heading>` sections).
**Target:** append to `data/equipment/magic_items.yaml`.

`category: miscellaneous_magic_items`, `cost_gp: 0`, `magic: true`. **Most are description-only.** `equippable: true` for worn/held-continuous items (cloaks, boots, bracers, gauntlets, girdles, gloves, helms, medallions, periapts, robes, amulets, brooches, necklaces, ioun stones, scarabs worn, etc.); `equippable: false` for activated tools/consumables/devices (beakers, bags, crystal balls, horns, dust, figurines, decanters, etc.). Charged items get `charge_dice`/`max_charges` as the text states.

**Transcription:** every item in the four tables becomes one `MagicItem` whose `description:` is its `## <heading>` section verbatim. The id is the snake_case of the name (e.g. `Apparatus of the Crab` → `apparatus_of_the_crab`). **Bag of Holding is already a `Container` in `containers.yaml`** (handled in Task 2) — do **not** duplicate it here.

**Fixed-modifier stat items** (continuous, non-random — values from the extracted source text):

| id | equippable | modifiers |
|---|---|---|
| `gauntlets_of_ogre_power` | true | `[{target: "ability:STR", op: set, value: 18}, {target: carry_capacity, op: add, value: 1000}]` |
| `girdle_of_giant_strength` | true | `[{target: thac0, op: set_max, value: 12}]` (damage 2d8 noted in desc) |
| `bracers_of_defencelessness` | true | `[{target: ac, op: set, value: 9}]` (cursed — noted in desc) |
| `cloak_of_defence` | true | `[{target: ac, op: add, value: 1}, {target: "save:all", op: add, value: 1}]` |
| `luckstone` | true | `[{target: "save:all", op: add, value: 1}]` |

> `cloak_of_defence`: the source gives a `1d8`-determined bonus of +1/+2/+3 (a non-linear step table, not a single die), so it is **not** auto-rolled. A fixed `+1` default is encoded and the description states the real rule; the GM raises it via `extra_modifiers`.

**Rolled-at-acquisition stat item** (uses Task 1's `rolled_modifiers`):

| id | equippable | rolled_modifiers | note |
|---|---|---|---|
| `bracers_of_armour` | true | `[{target: ac, op: set, dice: "1d4+3"}]` | AC `8 − 1d4` (uniform 4–7), rolled when acquired; catalog `modifiers` stays empty |

**Charged misc items** (examples — set per text): `scarab_of_protection` → `charge_dice: "2d6"`; necklaces/horns with a fixed count use `max_charges`.

**Description-only with a `# TODO:` comment** (Flagged Decision #2 — effect doesn't map cleanly yet; the user asked to defer modeling and leave a TODO on the data entry): `gloves_of_dexterity`, `periapt_of_proof_against_poison`. Also leave `robe_of_the_archmagi`, `ioun_stones`, `medallion_of_esp_30`/`_90`, `periapt_of_health` description-only (GM uses `extra_modifiers`); these get the same TODO line. The comment goes on the YAML entry, e.g.:
```yaml
# TODO: model the continuous DEX-step effect in a future pass (rolled_modifiers / ability:DEX).
- id: gloves_of_dexterity
  item_type: magic
  name: Gloves of Dexterity
  category: miscellaneous_magic_items
  cost_gp: 0
  magic: true
  equippable: true
  description: |-
    The wearer's Dexterity score is raised… (transcribe full section)

# TODO: model the poison-save bonus in a future pass (save:poison once that target exists).
- id: periapt_of_proof_against_poison
  item_type: magic
  name: Periapt of Proof Against Poison
  category: miscellaneous_magic_items
  cost_gp: 0
  magic: true
  equippable: true
  description: |-
    Grants a bonus to saving throws against poison… (transcribe full section)
```

**Files:** Modify `data/equipment/magic_items.yaml`; Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the failing test**
```python
def test_misc_stat_items(data):
    g = data.items["gauntlets_of_ogre_power"]
    assert g.equippable is True
    mods = {(m.target, m.op, m.value) for m in g.modifiers}
    assert ("ability:STR", "set", 18) in mods
    assert ("carry_capacity", "add", 1000) in mods
    assert data.items["girdle_of_giant_strength"].modifiers[0].target == "thac0"
    assert data.items["girdle_of_giant_strength"].modifiers[0].op == "set_max"
    assert data.items["bracers_of_defencelessness"].modifiers[0].value == 9
    assert data.items["luckstone"].modifiers[0].target == "save:all"


def test_bracers_of_armour_rolls_at_acquisition(data):
    import random
    from aose.engine.magic import new_magic_instance
    b = data.items["bracers_of_armour"]
    assert b.modifiers == []                       # no fixed catalog AC
    rm = b.rolled_modifiers[0]
    assert rm.target == "ac" and rm.op == "set"
    inst = new_magic_instance("bracers_of_armour", data, rng=random.Random(0))
    rolled = [m for m in inst.extra_modifiers if m.target == "ac"]
    assert len(rolled) == 1 and 4 <= rolled[0].value <= 7


def test_misc_count_and_descriptions(data):
    misc = [i for i in data.items.values()
            if isinstance(i, MagicItem) and i.category == "miscellaneous_magic_items"]
    # ~130 (131 table rows minus Bag of Holding, which is a Container)
    assert len(misc) >= 128
    assert all(i.description for i in misc)
    assert all(i.cost_gp == 0 and i.magic for i in misc)
```

- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Append all misc entries** (every row of tables I–IV except Bag of Holding), with the fixed modifiers on the five stat items, `rolled_modifiers` on Bracers of Armour, and the `# TODO:` description-only entries. Example fixed stat item:
```yaml
- id: gauntlets_of_ogre_power
  item_type: magic
  name: Gauntlets of Ogre Power
  category: miscellaneous_magic_items
  cost_gp: 0
  magic: true
  equippable: true
  modifiers:
    - {target: "ability:STR", op: set, value: 18}
    - {target: carry_capacity, op: add, value: 1000}
  description: |-
    A character who wears these gauntlets has a Strength score of 18… (full)
```
Bracers of Armour:
```yaml
- id: bracers_of_armour
  item_type: magic
  name: Bracers of Armour
  category: miscellaneous_magic_items
  cost_gp: 0
  magic: true
  equippable: true
  rolled_modifiers:
    - {target: ac, op: set, dice: "1d4+3"}   # AC 8 − 1d4 (uniform 4–7), rolled at acquisition
  description: |-
    When first donned, the protective power of the bracers is determined: the
    wearer's Armour Class becomes 8 − 1d4 (i.e. AC 4 to 7). (transcribe full)
```

- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full suite — green.**
- [ ] **Step 6: Commit**
```powershell
git add data/equipment/magic_items.yaml tests/test_magic_item_import.py
git commit -m "feat(data): miscellaneous magic items"
```

---

## Task 10: End-to-end verification & spec spot-checks

No new data — this task proves the whole compendium loads and behaves per the spec's "Verification" section.

**Files:** Test `tests/test_magic_item_import.py`.

- [ ] **Step 1: Write the integration test**
```python
def test_everything_loads_without_error():
    # GameData.load raises on any pydantic validation error.
    GameData.load(DATA_DIR)


def test_sword_enchantment_composes_on_bastard_sword_and_lightsaber(data):
    from aose.engine.enchant import compatible_bases
    bases = {b.id for b in compatible_bases(data.enchantments["sword_plus_1"], data)}
    assert {"bastard_sword", "lightsaber", "short_sword", "sword",
            "two_handed_sword"} <= bases


def test_generic_weapon_plus1_not_on_swords(data):
    from aose.engine.enchant import is_compatible
    assert not is_compatible(data.items["short_sword"],
                             data.enchantments["generic_plus_1"])
    assert is_compatible(data.items["battle_axe"],
                         data.enchantments["generic_plus_1"])


def test_ring_passive_modifier_changes_ac_on_sheet(tmp_path):
    # A worn Ring of Protection +1 raises AC by 1 vs unequipped.
    from aose.engine.armor_class import armor_class
    from aose.engine.magic import add_free_magic_item, equip_magic
    from aose.models import CharacterSpec, ClassEntry
    d = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="R", abilities={"STR": 12, "INT": 12, "WIS": 11,
                             "DEX": 10, "CON": 12, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter")], alignment="law",
    )
    base_ac, _ = armor_class(spec, d)
    spec.magic_items = add_free_magic_item(spec.magic_items, "ring_protection_plus_1", d)
    iid = spec.magic_items[0].instance_id
    spec.magic_items = equip_magic(spec.magic_items, iid, d)
    worn_ac, _ = armor_class(spec, d)
    assert worn_ac == base_ac - 1   # descending AC improves by 1
```
> If `CharacterSpec`/`armor_class`/`equip_magic` signatures differ, mirror the patterns in `tests/test_magic_items.py` (the Phase-1 ring tests) — do not change engine code.

- [ ] **Step 2: Run the integration tests** → `pytest tests/test_magic_item_import.py -q` PASS.
- [ ] **Step 3: Run the FULL suite**
Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: all green; new total ≈ 863 baseline + ~22 import tests. Ignore the trailing `pytest-current` PermissionError.

- [ ] **Step 4: Source-faithfulness review (project rule)**
Re-read each `## <heading>` in the source markdown against its YAML entry for: bonus signs, charge dice, save types, and `applies_to` tags. Fix any discrepancy. Confirm the **Flagged decisions** are acceptable; if any item genuinely cannot be expressed (and isn't already flagged), stop and raise it rather than inventing a model change.

- [ ] **Step 5: Update CLAUDE.md "Current state"**
Add a short bullet noting Phase 2 (bulk magic-item import) landed, with the new file list, the `rolled_modifiers` addition, and test count — mirroring the existing Phase-1 bullet style.

- [ ] **Step 6: Commit**
```powershell
git add tests/test_magic_item_import.py CLAUDE.md
git commit -m "test(data): end-to-end magic-item compendium verification; doc Phase 2"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** gear+containers (Task 2) ✓; swords→enchantments (Task 4) ✓; non-sword weapons→enchantments (Task 5) ✓; **ammunition handled by the merged ammunition feature, not duplicated** (Depends-on section) ✓; armour/shields→enchantments incl. cursed AC-9 (Task 3) ✓; potions (Task 6) ✓; rings incl. passive modifiers (Task 7) ✓; rods/staves/wands with per-type charge defaults (Task 8) ✓; misc incl. fixed-modifier stat items + Bracers rolled-at-acquisition + Bag-of-Holding reconcile (Tasks 1, 2, 9) ✓; gloves/periapt deferred with `# TODO` per user (Task 9) ✓; Sword Defender `magic_bonus 3` only (Task 4, asserted) ✓; categories preserved for sheet grouping ✓; "verify against source markdown" (Task 10 Step 4) ✓; `GameData.load` clean + composition + ring-AC spot-checks (Task 10) ✓.

**Out-of-scope honoured:** no d% treasure tables; acquisition-random choices pushed to description/`note`/`extra_modifiers` except the one rolled case (Bracers, now first-class); the only code change is the `RolledModifier` value type + its roll in `new_magic_instance`. No PDF dependency — the markdown is authoritative; genuinely-absent gear weights use book-typical values and say so.

**Type consistency:** `RolledModifier{target, op∈add|set|set_min|set_max, dice}` (new in `aose/models/modifier.py`) flows into `MagicItem.rolled_modifiers` (Task 1) and is rolled into `MagicItemInstance.extra_modifiers` as concrete `Modifier{target, op, value}` by `new_magic_instance` (Task 1), then asserted in Tasks 1 and 9. `Enchantment` fields (`name_template`, `kind`, `applies_to.{include,exclude}`, `magic_bonus`, `conditional_bonus.{vs,bonus}`, `modifiers`, `charge_dice`, `max_charges`, `cursed`, `description`) and `MagicItem` fields (`item_type: magic`, `equippable`, `modifiers`, `rolled_modifiers`, `max_charges`, `charge_dice`, `magic`, `cost_gp`, `description`) match `aose/models/{enchantment,item}.py`. `Modifier{target, op, value}` matches `aose/models/modifier.py`. Preserved seed ids verified against the real-data tests that pin them; the merged ammo enchantment ids are explicitly not re-added.
