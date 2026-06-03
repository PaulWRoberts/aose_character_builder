# Magic Item Compendium — Bulk YAML Import (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate every markdown source in `import/markdown/{items,magic-items}/` into book-faithful YAML game data — with full descriptions — against the **already-merged Phase-1 models**, adding no model or engine code.

**Architecture:** Pure data entry. Three target files grow or are (re)created under `data/`: `enchantments.yaml` (combat enchantments → `Enchantment`), `data/equipment/magic_items.yaml` (potions/rings/rods/staves/wands/misc → `MagicItem`), and `data/equipment/adventuring_gear.yaml` + `containers.yaml` (re-imported with descriptions). A few base `Weapon`/`Armor` entries gain `groups` tags or are newly added so enchantments compose onto them. Verification is by tests that `GameData.load` the real `data/` dir and spot-check shapes, values, and composition.

**Tech Stack:** Python 3.14, Pydantic v2, PyYAML, pytest. Models: `aose/models/{enchantment,item,modifier}.py`. Engine (read-only here): `aose/engine/enchant.py`, `aose/engine/magic.py`. Loader: `aose/data/loader.py` (`equipment/*.yaml` is auto-globbed except `weapon_qualities.yaml`; `enchantments.yaml` is loaded from the data-dir root).

---

## Pre-flight: read these before starting

- Spec: `docs/superpowers/specs/2026-06-02-magic-item-import-design.md` (the contract).
- Phase-1 spec for model semantics: `docs/superpowers/specs/2026-06-02-magic-item-enchantments-design.md`.
- Models: `aose/models/enchantment.py`, `aose/models/item.py`, `aose/models/modifier.py`.
- Source markdown: `import/markdown/items/advanced-fantasy_adventuring-gear.md`,
  `import/markdown/magic-items/*.md`.

**Transcription rule (not a placeholder):** Where a step says *"`description:` = the full book text from source §<Heading>"*, copy the prose verbatim from the named markdown section into the YAML `description:` field as a YAML block scalar (`description: |-`). The markdown is the authoritative text; reproducing 3,600 lines of it inside this plan would only risk drift. The plan specifies every **mechanical** field (ids, bonuses, charges, modifiers, `applies_to`); the descriptions are mechanical transcription.

**Running tests (Windows, venv not auto-activated):**
```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
Baseline before starting: **834 passing** (835 collected incl. one xfail/skip). The trailing `PermissionError` on `pytest-current` is a known Windows pytest-9 tempdir quirk — ignore it.

## Flagged modeling decisions (resolved here; revisit if the user objects)

The spec says *"if a source item cannot be expressed by the Phase-1 models, stop and flag it."* None of the items below need a model change, but each involved a judgement call. They are resolved as stated and called out again at their task:

1. **Enchanted ammunition** (Arrow/Arrows +N, Crossbow Bolts +N, Sling Bullet, Javelin specials). Modeled as `Enchantment`s on new base ammo "weapons" (`arrow`, `crossbow_bolt`, `sling_bullet`; `javelin` already exists). Quantity ("2d6 arrows") and acquisition-random foe (Arrow of Slaying) live in the `description`/instance `note` per spec "out of scope." The base ammo items are minimal ranged `Weapon`s; their non-combat stats (cost/weight) are **flagged** — no PDF is in the repo to verify against, so book-typical values are used.
2. **Random-at-acquisition passive modifiers** (Bracers of Armour `AC 8−1d4`, Cloak of Defence `1d8→+1/+2/+3`, Gloves of Dexterity DEX step, Periapt of Proof poison bonus). The catalog `Modifier` cannot hold a die roll. Resolution: encode the **most common / lowest** fixed value as the default modifier and state the real rule in `description`; the GM overrides per-instance via `MagicItemInstance.extra_modifiers` (Phase-1 escape hatch). Gloves of Dexterity and Periapt of Proof Against Poison are left **description-only** (their step function / save-type nuance doesn't map cleanly) with a note to use `extra_modifiers`.
3. **Sword +3, Defender.** Spec suggested an `ac` modifier, but the power is a per-round *choice* to move the +3 from attack to AC — a passive `ac +3` would double-count with `magic_bonus: 3`. Resolved: `magic_bonus: 3` only; the AC-transfer option is described. (Deviation from the spec's literal `ac` hint, by design.)
4. **No PDF in repo.** The project rule "verify rules against the PDF" cannot be satisfied for values absent from the markdown (some gear/ammo weights). Those are taken from standard AOSE values and **flagged** in-line; the human reviewer should confirm against their book at review time.
5. **`generic_plus_1`** (any_weapon, exclude sword) is **kept** though the book chart has only per-type weapon bonuses — three real-data tests depend on its id. It coexists as a convenience generic.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `data/equipment/weapons.yaml` | Modify | Add `groups: [bow]` to bows; add base ammo `arrow`/`crossbow_bolt`/`sling_bullet` |
| `data/enchantments.yaml` | Replace contents (keep tested ids) | All sword/weapon/armour/shield enchantments from the three combat files |
| `data/equipment/magic_items.yaml` | Create | All potions, rings, rods/staves/wands, miscellaneous items (`MagicItem`) |
| `data/equipment/adventuring_gear.yaml` | Rewrite | Gear from the gear markdown, **with descriptions**, ids preserved |
| `data/equipment/containers.yaml` | Modify | Reconcile Backpack/Sacks with gear markdown; add `description`; Bag of Holding gets `magic: true` + description |
| `tests/test_magic_item_import.py` | Create | Load-and-spot-check tests for every task |

**Tested seed ids that MUST survive** (real-data tests reference them — do not rename or drop): `generic_plus_1`, `sword_plus_1`, `sword_plus_1_vs_undead`, `luck_blade`, `armour_plus_1`, `shield_plus_1`, `trident_fish_command`. Base items referenced by tests: `torch`, `sword`, `short_sword`, `battle_axe`, `chain_mail`, `shield`, `backpack`. `trident_fish_command.charge_dice` may change value (a test only asserts it is non-null).

---

## Task 1: Base weapon tags + ammunition bases

Enchantments match bases by id / `groups` tag / kind-wildcard (`aose/engine/enchant.py::matches`). The weapon chart references `bow` and ammunition types that don't yet exist as tags/bases.

**Files:**
- Modify: `data/equipment/weapons.yaml`
- Create: `tests/test_magic_item_import.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_magic_item_import.py`:
```python
"""Phase-2 bulk magic-item import: load-and-spot-check against real data."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.models import Armor, MagicItem, Weapon

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_bows_carry_bow_group(data):
    assert "bow" in data.items["short_bow"].groups
    assert "bow" in data.items["long_bow"].groups


def test_ammo_bases_exist_and_are_ranged(data):
    for ammo_id in ("arrow", "crossbow_bolt", "sling_bullet"):
        ammo = data.items[ammo_id]
        assert isinstance(ammo, Weapon)
        assert ammo.ranged is True and ammo.melee is False
```

- [ ] **Step 2: Run it, verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py -q`
Expected: FAIL — `KeyError: 'arrow'` (and `bow` not in groups).

- [ ] **Step 3: Add `bow` group to the two bows**

In `data/equipment/weapons.yaml`, under `short_bow` and `long_bow`, add a `groups` key (after `qualities`):
```yaml
# short_bow:
  qualities: [missile, two_handed]
  groups: [bow]
# long_bow:
  qualities: [missile, two_handed]
  groups: [bow]
```

- [ ] **Step 4: Append the three ammunition bases**

Append to `data/equipment/weapons.yaml`. **FLAG:** cost/weight are book-typical (arrows 5 gp/20, bolts 10 gp/30, bullets ~negligible); confirm against the book. Damage matches the launching weapon's 1d6 line.
```yaml
- id: arrow
  item_type: weapon
  name: Arrow
  category: weapons
  cost_gp: 0.25
  weight_cn: 1
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  melee: false
  ranged: true
  qualities: [missile]
  groups: [arrow]

- id: crossbow_bolt
  item_type: weapon
  name: Crossbow Bolt
  category: weapons
  cost_gp: 0.33
  weight_cn: 1
  damage: { default: "1d6", variable: "1d6" }
  hands: 1
  melee: false
  ranged: true
  qualities: [missile]
  groups: [crossbow_bolt]

- id: sling_bullet
  item_type: weapon
  name: Sling Bullet
  category: weapons
  cost_gp: 0.05
  weight_cn: 1
  damage: { default: "1d6", variable: "1d4" }
  hands: 1
  melee: false
  ranged: true
  qualities: [blunt, missile]
  groups: [sling_bullet]
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_magic_item_import.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full suite (nothing regressed)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: 836 passing (834 baseline + 2 new).

- [ ] **Step 7: Commit**
```powershell
git add data/equipment/weapons.yaml tests/test_magic_item_import.py
git commit -m "feat(data): bow group + ammunition base weapons for enchantment matching"
```

---

## Task 2: Adventuring gear + containers re-import (with descriptions)

Re-import `adventuring_gear.yaml` from `import/markdown/items/advanced-fantasy_adventuring-gear.md` **with descriptions**, preserving existing ids that are referenced elsewhere. Reconcile container entries with `containers.yaml`.

**Source:** `import/markdown/items/advanced-fantasy_adventuring-gear.md` (table + `### Descriptions` + `### Other Equipment`).

**Id reconciliation** — keep these existing ids (referenced or already present): `crowbar, flask_of_oil, holy_water_vial, iron_rations, standard_rations, lantern, mirror_small, rope_50ft, stakes_and_mallet, thieves_tools, tinder_box, torch, waterskin, wine_skin, bedroll, candle`. Add new ids from the markdown table not yet present: `garlic, grappling_hook, hammer_small, holy_symbol, iron_spikes, pole_10ft, wolfsbane`. (`bedroll`/`candle` are not in the markdown table but are kept — they're harmless and avoid a needless delete; they get no new description.)

**Weights:** keep existing `weight_cn` values for kept ids. **FLAG** — the markdown gives only cost, not weight; new items use book-typical weights (`garlic` 0, `grappling_hook` 80, `hammer_small` 10, `holy_symbol` 10, `iron_spikes` 10, `pole_10ft` 100, `wolfsbane` 0). Confirm against the book.

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

Edit `data/equipment/containers.yaml`: add `description: |-` (transcribed) to `backpack`, `sack_small`, `sack_large` (the gear markdown gives Backpack "Holds up to 400 coins", Sack large "600 coins", Sack small "200 coins"). Leave `saddle_bags` as-is (add a short description). For `bag_of_holding`, add `magic: true` and `description: |-` (transcribe from the misc markdown §Bag of Holding in Task 6). Keep all existing `capacity_cn`/`weight_multiplier`/`cost_gp` values. Example:
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
| `sword_defender` | 3 | — | — | — | — | `[sword]` (see Flagged Decision #3 — AC option is description-only) |
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

## Task 5: Weapon (non-sword) enchantments

**Source:** `import/markdown/magic-items/advanced-fantasy_magic-magic-weapons.md`.
**Target:** append to `data/enchantments.yaml` (keep `trident_fish_command`, fix its `charge_dice` to `1d4+16`).

All `kind: weapon`, per-weapon-type `include`. Ammunition uses the bases from Task 1. Same conditional/modifier/charge/cursed rules as Task 4.

**Enumeration:**

| id | magic_bonus | conditional / charges | cursed | include |
|---|---|---|---|---|
| `arrow_slaying` | 1 | desc only (acts +3 & slays chosen foe) | — | `[arrow]` |
| `arrows_plus_1` | 1 | — | — | `[arrow]` |
| `arrows_plus_2` | 2 | — | — | `[arrow]` |
| `axe_plus_1` | 1 | — | — | `[axe]` |
| `axe_plus_2` | 2 | — | — | `[axe]` |
| `bow_plus_1` | 1 | — | — | `[bow]` |
| `crossbow_distance` | 1 | desc | — | `[crossbow]` |
| `crossbow_speed` | 1 | desc | — | `[crossbow]` |
| `crossbow_accuracy` | 2 | desc | — | `[crossbow]` |
| `crossbow_bolts_plus_1` | 1 | — | — | `[crossbow_bolt]` |
| `crossbow_bolts_plus_2` | 2 | — | — | `[crossbow_bolt]` |
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
| `sling_bullet_impact` | 1 | desc | — | `[sling_bullet]` |
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
    assert e["arrows_plus_1"].applies_to.include == ["arrow"]


def test_weapon_enchantment_composes_on_base(data):
    from aose.engine.enchant import new_enchanted_instance, resolve_instance
    inst = new_enchanted_instance("battle_axe", "axe_plus_1", data)
    resolved = resolve_instance(inst, data)
    assert resolved.magic_bonus == 1
    assert resolved.base_weapon == "battle_axe"
```

- [ ] **Step 2: Run, verify failure** → FAIL (`KeyError: 'axe_plus_2'`).
- [ ] **Step 3: Apply edits** — fix `trident_fish_command.charge_dice` → `"1d4+16"`; append all weapon entries.
- [ ] **Step 4: Run the test, verify pass.**
- [ ] **Step 5: Full suite** — green (check `test_enchanted_equip_charge_note_remove_roundtrip`, which uses `trident_fish_command`, still passes — it only reads `charges_remaining`, not the dice string).
- [ ] **Step 6: Commit**
```powershell
git add data/enchantments.yaml tests/test_magic_item_import.py
git commit -m "feat(data): magic (non-sword) weapon enchantments incl. ammunition"
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

## Task 9: Miscellaneous magic items (`MagicItem`; passive modifiers for stat items)

**Source:** `import/markdown/magic-items/advanced-fantasy_miscellaneous-magic-items.md` (~131 items across four `Miscellaneous Magic Items I–IV` tables + per-item `## <heading>` sections).
**Target:** append to `data/equipment/magic_items.yaml`.

`category: miscellaneous_magic_items`, `cost_gp: 0`, `magic: true`. **Most are description-only.** `equippable: true` for worn/held-continuous items (cloaks, boots, bracers, gauntlets, girdles, gloves, helms, medallions, periapts, robes, amulets, brooches, necklaces, rings-not-in-rings-file, ioun stones, scarabs worn, etc.); `equippable: false` for activated tools/consumables/devices (beakers, bags, crystal balls, horns, dust, figurines, decanters, etc.). Charged items get `charge_dice`/`max_charges` as the text states.

**Transcription:** every item in the four tables becomes one `MagicItem` whose `description:` is its `## <heading>` section verbatim. The id is the snake_case of the name (e.g. `Apparatus of the Crab` → `apparatus_of_the_crab`). **Bag of Holding is already a `Container` in `containers.yaml`** (handled in Task 2) — do **not** duplicate it here.

**Passive-modifier stat items** (the only misc items with `modifiers`; values verified against the extracted source text):

| id | equippable | modifiers | flag |
|---|---|---|---|
| `gauntlets_of_ogre_power` | true | `[{target: "ability:STR", op: set, value: 18}, {target: carry_capacity, op: add, value: 1000}]` | — |
| `girdle_of_giant_strength` | true | `[{target: thac0, op: set_max, value: 12}]` | damage 2d8 noted in desc |
| `bracers_of_armour` | true | `[{target: ac, op: set, value: 6}]` | **FLAG** AC is `8−1d4` (4–7); default 6, GM tunes via `extra_modifiers` |
| `bracers_of_defencelessness` | true | `[{target: ac, op: set, value: 9}]` | cursed (noted in desc) |
| `cloak_of_defence` | true | `[{target: ac, op: add, value: 1}, {target: "save:all", op: add, value: 1}]` | **FLAG** bonus `1d8`→+1/+2/+3; default +1, GM tunes |
| `luckstone` | true | `[{target: "save:all", op: add, value: 1}]` | — |

**Charged misc items** (examples — set per text): `scarab_of_protection` → `charge_dice: "2d6"`; `necklace_of_fireballs`, `wand`-like horns etc. per their own counts. Items with a fixed count use `max_charges`.

**Description-only with a homebrew-modifier note** (Flagged Decision #2 — too random/conditional to encode): `gloves_of_dexterity`, `periapt_of_proof_against_poison`, `robe_of_the_archmagi`, `ioun_stones`, `medallion_of_esp_30`/`_90`, `periapt_of_health`. Add a trailing note line in their `description` like: *"(GM: apply continuous stat effects via the item's extra_modifiers.)"*

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


def test_misc_count_and_descriptions(data):
    misc = [i for i in data.items.values()
            if isinstance(i, MagicItem) and i.category == "miscellaneous_magic_items"]
    # ~130 (131 table rows minus Bag of Holding, which is a Container)
    assert len(misc) >= 128
    assert all(i.description for i in misc)
    assert all(i.cost_gp == 0 and i.magic for i in misc)
```

- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Append all misc entries** (every row of tables I–IV except Bag of Holding), with the modifiers above on the six stat items. Example stat item:
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
Expected: all green; new total ≈ 834 baseline + ~20 import tests. Ignore the trailing `pytest-current` PermissionError.

- [ ] **Step 4: Source-faithfulness review (project rule)**
Re-read each `## <heading>` against its YAML entry for: bonus signs, charge dice, save types, and `applies_to` tags. Fix any discrepancy. Confirm the **Flagged decisions** are acceptable; if any is not, stop and raise it rather than inventing a model change.

- [ ] **Step 5: Update CLAUDE.md "Current state"**
Add a short bullet noting Phase 2 (bulk magic-item import) landed, with the new file list and test count, mirroring the existing Phase-1 bullet style.

- [ ] **Step 6: Commit**
```powershell
git add tests/test_magic_item_import.py CLAUDE.md
git commit -m "test(data): end-to-end magic-item compendium verification; doc Phase 2"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** gear+containers (Task 2) ✓; swords→enchantments (Task 4) ✓; weapons→enchantments incl. ammunition & missing bases (Tasks 1, 5) ✓; armour/shields→enchantments incl. cursed AC-9 (Task 3) ✓; potions (Task 6) ✓; rings incl. passive modifiers (Task 7) ✓; rods/staves/wands with per-type charge defaults (Task 8) ✓; misc incl. the named passive-modifier stat items + Bag-of-Holding reconcile (Tasks 2, 9) ✓; categories preserved for sheet grouping ✓; "verify against source" (Task 10 Step 4) ✓; `GameData.load` clean + composition + ring-AC spot-checks (Task 10) ✓.

**Out-of-scope honoured:** no d% treasure tables; acquisition-random choices pushed to description/`note`/`extra_modifiers`; no model/engine changes (all flagged items expressible under Phase-1 models).

**Type consistency:** `Enchantment` fields (`name_template`, `kind`, `applies_to.{include,exclude}`, `magic_bonus`, `conditional_bonus.{vs,bonus}`, `modifiers`, `charge_dice`, `max_charges`, `cursed`, `description`) and `MagicItem` fields (`item_type: magic`, `equippable`, `modifiers`, `max_charges`, `charge_dice`, `magic`, `cost_gp`, `description`) match `aose/models/{enchantment,item}.py`. `Modifier` shape `{target, op, value}` with `op ∈ add|set|set_min|set_max` matches `aose/models/modifier.py`. Preserved seed ids verified against the three real-data tests that pin them.
