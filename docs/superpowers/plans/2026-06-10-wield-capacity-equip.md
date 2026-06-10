# Wield Capacity & Two-Weapon Fighting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "equipped" mean what is physically in hand — a two-hand budget with `main_hand`/`off_hand` slots replacing the flat `equipped_weapons` list, the optional two-weapon-fighting rule (−2/−4), and the gargantua one-handed-two-handed-melee exception.

**Architecture:** `CharacterSpec.equipped` becomes the single source of truth with slots `armor`/`main_hand`/`off_hand` (values are catalog ids *or* enchanted instance ids); `equipped_weapons` and the enchanted weapon/shield `equipped` bool are retired. A pure `validate_wield` gate in `engine/equip.py` enforces the 2-hand budget, the baseline one-weapon rule, off-hand eligibility, and the gargantua reduction. Penalties are applied in `engine/attacks.py`.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Spec: `docs/superpowers/specs/2026-06-10-wield-capacity-equip-design.md`.

**Running tests:** `.venv\Scripts\python.exe -m pytest tests/ -q` (the trailing `pytest-current` PermissionError on Windows is a known harmless quirk — ignore it). Single file: `.venv\Scripts\python.exe -m pytest tests/test_x.py -q`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `aose/models/ruleset.py` | RuleSet flags | Add `two_weapon_fighting` |
| `aose/models/character.py` | CharacterSpec storage | Drop `equipped_weapons`; `equipped` carries `armor`/`main_hand`/`off_hand` |
| `aose/web/settings_routes.py` | Settings flag wiring | Register the new flag |
| `data/races/gargantua.yaml`, `data/classes/gargantua.yaml` | Gargantua data | Add `one_handed_two_handed_melee` mechanical flag |
| `aose/engine/features.py` | Reached-feature helpers | Add `one_handed_two_handed_weapons` |
| `aose/engine/proficiency.py` | Class allowances/eligibility | Add `two_weapon_eligible` |
| `aose/engine/equip.py` | Equip gatekeeper | New pure helpers + slot-based `equip`/`unequip` |
| `aose/engine/shop.py` | Inventory/stash/remove | Drop `equipped_weapons` param; iterate `equipped` |
| `aose/engine/attacks.py` | Attack profiles | Iterate slots; −2/−4 penalties; suppress versatile 2H variant when off hand full |
| `aose/engine/armor_class.py` | AC | Read shield from `off_hand` |
| `aose/sheet/view.py` | Sheet assembly | Replace `equipped_weapons` reads |
| `aose/web/routes.py`, `aose/web/wizard.py` | Equip routes | Slot-based equip; enchanted equip → slots; cascade clear |
| Templates: `sheet.html`, `sheet_overlays.js`, wizard equipment | UI | Main/off-hand control, attack labels |

---

## Task 1: RuleSet `two_weapon_fighting` flag + settings wiring

**Files:**
- Modify: `aose/models/ruleset.py`
- Modify: `aose/web/settings_routes.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings.py`:

```python
def test_two_weapon_fighting_flag_is_implemented():
    from aose.models import RuleSet
    from aose.web.settings_routes import RULE_LABELS, IMPLEMENTED_RULES
    rs = RuleSet()
    assert rs.two_weapon_fighting is False
    assert "two_weapon_fighting" in RULE_LABELS
    assert "two_weapon_fighting" in IMPLEMENTED_RULES
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py::test_two_weapon_fighting_flag_is_implemented -q`
Expected: FAIL (`AttributeError`/`KeyError`).

- [ ] **Step 3: Add the flag to `RuleSet`**

In `aose/models/ruleset.py`, after `optional_staves: bool = False`:

```python
    optional_staves: bool = False
    two_weapon_fighting: bool = False
```

- [ ] **Step 4: Register in settings**

In `aose/web/settings_routes.py`:
- Add to `RULE_LABELS`: `"two_weapon_fighting": "Attacking with Two Weapons",`
- Add `"two_weapon_fighting",` to `IMPLEMENTED_RULES`.
- In `RULE_GROUPS`, add to the `"Combat"` group list:

```python
        ("two_weapon_fighting",
         "Characters with STR or DEX as a prime requisite may wield a small "
         "weapon in the off hand: −2 to the primary attack, an extra off-hand "
         "attack at −4."),
```

- [ ] **Step 5: Run the settings suite — expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS (the "every flag implemented / no pending badge" regression now covers the new flag).

- [ ] **Step 6: Commit**

```bash
git add aose/models/ruleset.py aose/web/settings_routes.py tests/test_settings.py
git commit -m "feat(rules): add two_weapon_fighting optional rule flag"
```

---

## Task 2: Gargantua one-handed-two-handed-melee data + feature helper

**Files:**
- Modify: `data/races/gargantua.yaml`, `data/classes/gargantua.yaml`
- Modify: `aose/engine/features.py`
- Test: `tests/test_feature_modifiers.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_feature_modifiers.py` (it already has a `data` fixture loading `DATA_DIR`; if not, copy the fixture from `tests/test_equip_enforcement.py`):

```python
def test_gargantua_wields_two_handed_melee_one_handed(data):
    from aose.engine.features import one_handed_two_handed_weapons
    from aose.models import CharacterSpec, ClassEntry, Ability

    spec = CharacterSpec(
        name="Krug", abilities={a: 12 for a in Ability},
        race_id="gargantua",
        classes=[ClassEntry(class_id="gargantua", level=1)],
        alignment="neutral",
    )
    assert one_handed_two_handed_weapons(spec, data) is True


def test_non_gargantua_does_not(data):
    from aose.engine.features import one_handed_two_handed_weapons
    from aose.models import CharacterSpec, ClassEntry, Ability

    spec = CharacterSpec(
        name="Bob", abilities={a: 12 for a in Ability},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1)],
        alignment="neutral",
    )
    assert one_handed_two_handed_weapons(spec, data) is False
```

(Confirm `data.classes["gargantua"]` is `race_locked == "gargantua"` so `_reached_features` reads the class, not the race — it is, per `data/classes/gargantua.yaml`.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k gargantua_wields -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add the mechanical flag to both gargantua files**

In `data/races/gargantua.yaml`, in the `combat` feature's `mechanical:` block (currently only `armour_requires_tailoring: true`):

```yaml
  mechanical:
    armour_requires_tailoring: true
    one_handed_two_handed_melee: true
```

Apply the identical edit to the matching `combat` feature in `data/classes/gargantua.yaml` (the class is the active stat block for the race-as-class; the race copy keeps the two files consistent).

- [ ] **Step 4: Add the feature helper**

In `aose/engine/features.py`, after `open_doors_category_bonus`:

```python
def one_handed_two_handed_weapons(spec: CharacterSpec, data: GameData) -> bool:
    """True when a reached feature grants wielding two-handed *melee* weapons in
    one hand (gargantua). Reads ``mechanical['one_handed_two_handed_melee']``."""
    for feat, _src in _reached_features(spec, data):
        if feat.mechanical and feat.mechanical.get("one_handed_two_handed_melee"):
            return True
    return False
```

- [ ] **Step 5: Run the tests — expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py -k gargantua -q`
Expected: PASS. Also run `tests/test_data_loading.py -q` to confirm the YAML still loads.

- [ ] **Step 6: Commit**

```bash
git add data/races/gargantua.yaml data/classes/gargantua.yaml aose/engine/features.py tests/test_feature_modifiers.py
git commit -m "feat(gargantua): one_handed_two_handed_melee feature flag + helper"
```

---

## Task 3: Two-weapon eligibility helper

**Files:**
- Modify: `aose/engine/proficiency.py`
- Test: `tests/test_equip_enforcement.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_equip_enforcement.py`:

```python
def test_two_weapon_eligible_by_prime_requisite(data):
    from aose.engine.proficiency import two_weapon_eligible
    # Fighter: STR prime requisite -> eligible.
    assert two_weapon_eligible([data.classes["fighter"]]) is True
    # Magic-user: INT prime requisite -> not eligible.
    assert two_weapon_eligible([data.classes["magic_user"]]) is False


def test_two_weapon_eligible_multiclass_any_qualifies(data):
    from aose.engine.proficiency import two_weapon_eligible
    assert two_weapon_eligible(
        [data.classes["magic_user"], data.classes["fighter"]]
    ) is True
```

(Verify the prime requisites: `data.classes["fighter"].prime_requisites` includes `Ability.STR`; `magic_user` is `INT`. Adjust the assertion if a class's data differs.)

- [ ] **Step 2: Run it — expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -k two_weapon_eligible -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add the helper**

In `aose/engine/proficiency.py`, add (import `Ability` from `aose.models` if not already imported):

```python
def two_weapon_eligible(classes) -> bool:
    """A character may fight with two weapons when ANY of their classes lists
    STR or DEX as a prime requisite (Attacking with Two Weapons, optional)."""
    from aose.models import Ability
    wanted = {Ability.STR, Ability.DEX}
    return any(wanted & set(cls.prime_requisites) for cls in classes)
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_enforcement.py -k two_weapon_eligible -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/proficiency.py tests/test_equip_enforcement.py
git commit -m "feat(equip): two_weapon_eligible prime-requisite helper"
```

---

## Task 4: Pure wield helpers (`hand_cost`, `off_hand_eligible`, `resolve_slot`, `validate_wield`)

These are **additive** — the old `equip`/`unequip` stay until Task 5, so the suite stays green.

**Files:**
- Modify: `aose/engine/equip.py`
- Test: `tests/test_wield.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wield.py`:

```python
"""Pure wield-capacity helpers."""
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.equip import (
    hand_cost, off_hand_eligible, resolve_slot, validate_wield, WieldError,
)

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def W(data, wid):
    return data.items[wid]


def test_hand_cost_basic(data):
    assert hand_cost(W(data, "sword"), gargantua_1h_2h=False) == 1          # 1H melee
    assert hand_cost(W(data, "two_handed_sword"), gargantua_1h_2h=False) == 2
    assert hand_cost(W(data, "shield"), gargantua_1h_2h=False) == 1
    assert hand_cost(W(data, "long_bow"), gargantua_1h_2h=False) == 2       # 2H ranged


def test_hand_cost_gargantua_reduces_two_handed_melee_only(data):
    # Battle axe is two_handed + melee -> 1 hand for a gargantua.
    assert hand_cost(W(data, "battle_axe"), gargantua_1h_2h=True) == 1
    # Long bow is two_handed but ranged -> stays 2 even for a gargantua.
    assert hand_cost(W(data, "long_bow"), gargantua_1h_2h=True) == 2


def test_off_hand_eligible(data):
    assert off_hand_eligible(W(data, "dagger")) is True
    assert off_hand_eligible(W(data, "hand_axe")) is True       # thrown melee, 30cn
    assert off_hand_eligible(W(data, "short_sword")) is True
    assert off_hand_eligible(W(data, "club")) is False          # 50cn, too heavy
    assert off_hand_eligible(W(data, "two_handed_sword")) is False  # two_handed
    assert off_hand_eligible(W(data, "spear")) is False         # brace
    assert off_hand_eligible(W(data, "bastard_sword")) is False # versatile
    assert off_hand_eligible(W(data, "long_bow")) is False      # no melee quality


def test_resolve_slot_catalog_and_missing(data):
    assert resolve_slot("sword", data, []) is W(data, "sword")
    assert resolve_slot(None, data, []) is None
    assert resolve_slot("nonsense", data, []) is None


def test_validate_wield_baseline_legal(data):
    # 1H weapon + shield, rule off.
    validate_wield({"main_hand": "sword", "off_hand": "shield"}, data, [],
                   two_weapon=False, eligible=False, gargantua_1h_2h=False)


def test_validate_wield_two_handed_blocks_shield(data):
    with pytest.raises(WieldError):
        validate_wield({"main_hand": "two_handed_sword", "off_hand": "shield"},
                       data, [], two_weapon=False, eligible=False,
                       gargantua_1h_2h=False)


def test_validate_wield_gargantua_two_handed_plus_shield(data):
    validate_wield({"main_hand": "battle_axe", "off_hand": "shield"}, data, [],
                   two_weapon=False, eligible=False, gargantua_1h_2h=True)


def test_validate_wield_two_weapons_requires_rule_and_eligibility(data):
    slots = {"main_hand": "sword", "off_hand": "dagger"}
    with pytest.raises(WieldError):  # rule off
        validate_wield(slots, data, [], two_weapon=False, eligible=True,
                       gargantua_1h_2h=False)
    with pytest.raises(WieldError):  # ineligible
        validate_wield(slots, data, [], two_weapon=True, eligible=False,
                       gargantua_1h_2h=False)
    # rule on + eligible + eligible off-hand -> OK
    validate_wield(slots, data, [], two_weapon=True, eligible=True,
                   gargantua_1h_2h=False)


def test_validate_wield_off_hand_must_be_eligible_weapon(data):
    with pytest.raises(WieldError):
        validate_wield({"main_hand": "sword", "off_hand": "club"}, data, [],
                       two_weapon=True, eligible=True, gargantua_1h_2h=False)


def test_validate_wield_off_hand_weapon_needs_main(data):
    with pytest.raises(WieldError):
        validate_wield({"off_hand": "dagger"}, data, [],
                       two_weapon=True, eligible=True, gargantua_1h_2h=False)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wield.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement the helpers**

In `aose/engine/equip.py`, add near the top (after imports add `from aose.engine.enchant import resolve_instance`):

```python
from aose.engine.enchant import resolve_instance

OFF_HAND_FORBIDDEN = {"two_handed", "versatile", "slow", "brace", "charge"}


class WieldError(ValueError):
    """A weapon/shield configuration that two hands cannot hold."""


def hand_cost(item, *, gargantua_1h_2h: bool) -> int:
    """Hands consumed by an in-hand item. Body armour returns 0."""
    if isinstance(item, Armor):
        return 1 if item.is_shield else 0
    if isinstance(item, Weapon):
        if "two_handed" in item.quality_ids:
            if gargantua_1h_2h and item.melee:
                return 1
            return 2
        return 1
    return 0


def off_hand_eligible(weapon: "Weapon") -> bool:
    """House rule for a 'small' off-hand weapon: <=30cn, melee, and none of the
    forbidden qualities."""
    return (
        weapon.weight_cn <= 30
        and "melee" in weapon.quality_ids
        and not (weapon.quality_ids & OFF_HAND_FORBIDDEN)
    )


def resolve_slot(value, data: GameData, enchanted):
    """Resolve a slot value to its concrete Weapon/Armor (catalog or enchanted),
    or None for an empty/stale slot."""
    if not value:
        return None
    if value in data.items:
        return data.items[value]
    for inst in enchanted:
        if inst.instance_id == value:
            return resolve_instance(inst, data)
    return None


def validate_wield(equipped: dict, data: GameData, enchanted, *,
                   two_weapon: bool, eligible: bool,
                   gargantua_1h_2h: bool) -> None:
    """Raise WieldError unless the hand slots form a legal configuration.
    Class allowances are checked separately by ``equip``; this gate is purely
    the hand budget + baseline one-weapon rule + two-weapon-fighting rules."""
    main = resolve_slot(equipped.get("main_hand"), data, enchanted)
    off = resolve_slot(equipped.get("off_hand"), data, enchanted)

    if main is not None and not isinstance(main, Weapon):
        raise WieldError("Only a weapon may be held in the main hand")

    used = (hand_cost(main, gargantua_1h_2h=gargantua_1h_2h) if main else 0)
    used += (hand_cost(off, gargantua_1h_2h=gargantua_1h_2h) if off else 0)
    if used > 2:
        raise WieldError("Both hands are full")

    if isinstance(off, Weapon):
        if not two_weapon:
            raise WieldError("Two-weapon fighting is not enabled")
        if not eligible:
            raise WieldError("This character is not eligible to fight with two weapons")
        if main is None:
            raise WieldError("Equip a main-hand weapon before an off-hand weapon")
        if not off_hand_eligible(off):
            raise WieldError(f"{off.name!r} is not a valid off-hand weapon")
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wield.py -q`
Expected: PASS.

- [ ] **Step 5: Confirm no cycle / suite still green**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (helpers are additive). If an import cycle appears (`equip` ← `enchant`), confirm `enchant.py` does not import `equip` (it doesn't).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/equip.py tests/test_wield.py
git commit -m "feat(equip): pure wield helpers (hand_cost, off_hand_eligible, validate_wield)"
```

---

## Task 5: Cutover — slot model replaces `equipped_weapons`

This is the coordinated change. The suite goes **red mid-task** and must be **green by the final step**. Work in the listed order.

**Files:**
- Modify: `aose/models/character.py`, `aose/engine/equip.py`, `aose/engine/shop.py`,
  `aose/engine/attacks.py`, `aose/engine/armor_class.py`, `aose/engine/encumbrance.py`,
  `aose/sheet/view.py`, `aose/web/routes.py`, `aose/web/wizard.py`
- Test: `tests/test_equip_enforcement.py`, `tests/test_equip_attacks.py`, `tests/test_encumbrance.py`, others as the suite reveals

- [ ] **Step 1: Model — drop `equipped_weapons`**

In `aose/models/character.py`, delete the `equipped_weapons` field and its comment (lines ~198-199). Update the `equipped` comment to:

```python
    # slot -> id, for worn/held gear. Slots: "armor" (body), "main_hand",
    # "off_hand" (a shield OR an off-hand weapon). Hand-slot values may be a
    # catalog item id or an enchanted instance id. equip() enforces the wield
    # budget; see aose/engine/equip.py.
    equipped: dict[str, str] = Field(default_factory=dict)
```

(No migration validator — dev mode, per spec.)

- [ ] **Step 2: Engine — rewrite `equip`/`unequip`**

Replace the `equip` and `unequip` functions in `aose/engine/equip.py` with slot-based versions. `equip` now returns just the new `equipped` dict:

```python
def equip(item_id: str, *, inventory: list[str], equipped: dict[str, str],
          enchanted, data: GameData,
          slot: str | None = None,
          two_weapon: bool = False, eligible: bool = False,
          gargantua_1h_2h: bool = False,
          allowed_weapons: "set[str] | str" = "all",
          allowed_armor: "set[str] | str" = "all",
          allow_shields: bool = True) -> dict[str, str]:
    """Equip one item into a slot. ``item_id`` is a catalog id (must be owned in
    ``inventory``) or an enchanted instance id (must exist in ``enchanted``).
    Body armour always goes to ``armor``; shields/weapons go to ``slot`` (default
    ``main_hand`` for weapons, ``off_hand`` for shields). Returns the new
    ``equipped`` dict. Raises ValueError/WieldError on any illegality."""
    item = resolve_slot(item_id, data, enchanted)
    if item is None:
        raise ValueError(f"Unknown or unowned item {item_id!r}")

    is_catalog = item_id in data.items
    if is_catalog:
        owned = _count(inventory, item_id)
        if owned == 0:
            raise ValueError(f"{item.name!r} is not in inventory")

    new_eq = dict(equipped)

    if isinstance(item, Armor) and not item.is_shield:
        if allowed_armor != "all" and base_armor_id(item) not in allowed_armor:
            raise ValueError(f"This class cannot use {item.name!r}")
        new_eq["armor"] = item_id
        return new_eq

    if isinstance(item, Armor) and item.is_shield:
        if not allow_shields:
            raise ValueError("This class cannot use a shield")
        target = "off_hand"
    elif isinstance(item, Weapon):
        if allowed_weapons != "all" and base_weapon_id(item) not in allowed_weapons:
            raise ValueError(f"This class cannot use {item.name!r}")
        target = slot or "main_hand"
    else:
        raise ValueError(f"{item.name!r} is not equippable")

    if target not in ("main_hand", "off_hand"):
        raise ValueError(f"Invalid hand slot {target!r}")

    # Ownership: don't equip more catalog copies than owned across both hands.
    if is_catalog:
        in_hands = sum(1 for s in ("main_hand", "off_hand")
                       if s != target and new_eq.get(s) == item_id)
        if in_hands >= owned:
            raise ValueError(f"All {owned} copies of {item.name!r} already equipped")

    new_eq[target] = item_id
    validate_wield(new_eq, data, enchanted, two_weapon=two_weapon,
                   eligible=eligible, gargantua_1h_2h=gargantua_1h_2h)
    return new_eq


def unequip(item_id: str, *, equipped: dict[str, str]) -> dict[str, str]:
    """Clear whichever slot holds ``item_id``. Raises ValueError if not equipped."""
    new_eq = dict(equipped)
    for slot, val in list(new_eq.items()):
        if val == item_id:
            del new_eq[slot]
            return new_eq
    raise ValueError(f"{item_id!r} is not equipped")
```

Update `equipped_count` (drop the `equipped_weapons` arg):

```python
def equipped_count(equipped: dict[str, str], item_id: str) -> int:
    return sum(1 for v in equipped.values() if v == item_id)
```

- [ ] **Step 3: Rewrite `tests/test_equip_enforcement.py` equip() calls**

The old positional signature is gone. Update the equip enforcement tests to the new keyword API, e.g.:

```python
def test_equip_rejects_disallowed_weapon(data):
    allowed = allowed_weapon_ids([data.classes["cleric"]], data)
    with pytest.raises(ValueError, match="cannot use"):
        equip("sword", inventory=["sword"], equipped={}, enchanted=[], data=data,
              allowed_weapons=allowed)


def test_equip_allows_allowed_weapon(data):
    allowed = allowed_weapon_ids([data.classes["cleric"]], data)
    eq = equip("mace", inventory=["mace"], equipped={}, enchanted=[], data=data,
               allowed_weapons=allowed)
    assert eq["main_hand"] == "mace"


def test_equip_rejects_disallowed_armor(data):
    allowed = allowed_armor_ids([data.classes["thief"]], data)
    with pytest.raises(ValueError, match="cannot use"):
        equip("plate_mail", inventory=["plate_mail"], equipped={}, enchanted=[],
              data=data, allowed_armor=allowed)


def test_equip_rejects_shield_when_not_allowed(data):
    with pytest.raises(ValueError, match="shield"):
        equip("shield", inventory=["shield"], equipped={}, enchanted=[], data=data,
              allow_shields=False)


def test_equip_unrestricted_by_default(data):
    eq = equip("sword", inventory=["sword"], equipped={}, enchanted=[], data=data)
    assert eq["main_hand"] == "sword"
```

Also update the `inventory_view` tests in this file to drop the `equipped_weapons` positional arg (see Step 4).

- [ ] **Step 4: Shop — drop the `equipped_weapons` parameter**

In `aose/engine/shop.py`, since equipped weapons now live in the `equipped` dict, remove the `equipped_weapons` parameter from `inventory_view`, `inventory_rows`, `stash`, `remove`, and the `equipped.values()` checks already cover hands:

- `inventory_view(...)`: drop `equipped_weapons` param; build `equipped_count` from `equipped.values()` only:

```python
    equipped_count: Counter[str] = Counter()
    for v in equipped.values():
        equipped_count[v] += 1
```

- `inventory_rows(...)`: drop the `equipped_weapons` param and pass only `equipped` through to `inventory_view`.
- `stash(...)`: change signature to `stash(inventory, stashed, equipped, item_id, data)` returning `(inventory, stashed, equipped)`; delete the `new_weapons` block; keep the slot-freeing loop over `new_eq`.
- `remove(...)`: drop the `equipped_weapons` param and return `(inventory, gold, equipped)`; in the slot-freeing loop drop `new_weapons`, compute `eq_uses = sum(1 for v in new_eq.values() if v == item_id)`, and only delete from `new_eq`.
- `stow(...)`: change the equipped check to `if item_id in equipped.values():` (drop `equipped_weapons`); drop that param.

- [ ] **Step 5: Attacks — iterate slots (no penalties yet)**

In `aose/engine/attacks.py`, replace the `counts = Counter(spec.equipped_weapons)` loop and the separate `equipped_enchanted(spec, data, "weapon")` loop with a single slot iteration (import `resolve_slot` from `aose.engine.equip`):

```python
    from aose.engine.equip import resolve_slot
    for slot_name in ("main_hand", "off_hand"):
        val = spec.equipped.get(slot_name)
        item = resolve_slot(val, data, spec.enchanted)
        if not isinstance(item, Weapon):
            continue  # empty slot or shield
        g_atk, g_dmg = _atk_dmg(mods, melee=item.melee, ranged=item.ranged)
        manageable = item.id if val in data.items else None
        base = _profile_for(item, spec, data, 1, eff, base_thac0, g_atk, g_dmg,
                            manageable_item_id=manageable, **_ammo_args(item))
        weapon_profiles.append(base)
        variant = _two_handed_variant(base, item, spec)
        if variant is not None:
            weapon_profiles.append(variant)
```

(Penalties and the off-hand variant suppression land in Task 6. The feature-weapon and unarmed handling is unchanged.)

- [ ] **Step 6: AC — read shield from `off_hand`**

In `aose/engine/armor_class.py`, replace the shield block in `_compute_ac` (the `shield_id = spec.equipped.get("shield")` + `equipped_enchanted(spec, data, "shield")` section) with a single resolve of the off-hand slot:

```python
    shield_bonus = 0
    has_shield = False
    if use_shield:
        from aose.engine.equip import resolve_slot
        off = resolve_slot(spec.equipped.get("off_hand"), data, spec.enchanted)
        if isinstance(off, Armor) and off.is_shield:
            shield_bonus = off.ac_bonus + off.magic_bonus
            has_shield = True
```

- [ ] **Step 7: view.py + encumbrance docstring**

In `aose/sheet/view.py` (~line 693), replace `set(spec.inventory) | set(spec.equipped_weapons)` with:

```python
    for wid in set(spec.inventory) | set(spec.equipped.values()):
```

In `aose/engine/encumbrance.py`, update the docstring line that mentions `equipped`/`equipped_weapons` double-counting to drop `equipped_weapons` (no code change).

- [ ] **Step 8: Routes — sheet equip/unequip/remove/stash + inventory_view**

In `aose/web/routes.py`:

- The sheet `inventory_view` call (~line 162): drop the `spec.equipped_weapons` argument:

```python
            "inventory_view": shop_inventory_view(
                spec.inventory, spec.stashed, spec.equipped,
                spec.containers, game_data,
                allowed_weapons=allowed_weapon_ids(classes, game_data, spec.ruleset),
                allowed_armor=allowed_armor_ids(classes, game_data),
                allow_shields=shields_allowed(classes),
            ),
```

- `equipment_equip`: accept an optional `slot` form field and pass the new wield context. Add a small helper at module level for the gargantua/eligibility flags:

```python
from aose.engine.features import one_handed_two_handed_weapons
from aose.engine.proficiency import two_weapon_eligible

@router.post("/character/{character_id}/equipment/equip")
async def equipment_equip(request: Request, character_id: str,
                          item_id: str = Form(...),
                          slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    try:
        spec.equipped = _equip(
            item_id, inventory=spec.inventory, equipped=spec.equipped,
            enchanted=spec.enchanted, data=data, slot=slot,
            two_weapon=spec.ruleset.two_weapon_fighting,
            eligible=two_weapon_eligible(classes),
            gargantua_1h_2h=one_handed_two_handed_weapons(spec, data),
            allowed_weapons=allowed_weapon_ids(classes, data, spec.ruleset),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- `equipment_unequip`: `spec.equipped = _unequip(item_id, equipped=spec.equipped)`.
- `equipment_remove` (carried branch): `spec.inventory, spec.gold, spec.equipped = shop_remove(spec.inventory, spec.gold, item_id, mode, game_data, spec.equipped)`.
- `equipment_stash`: `spec.inventory, spec.stashed, spec.equipped = shop_stash(spec.inventory, spec.stashed, spec.equipped, item_id, request.app.state.game_data)`.
- `equipment_stow`: drop the `equipped_weapons` argument in the `shop_stow` call.

- [ ] **Step 9: Routes — enchanted weapon/shield equip → slots**

Rewrite `equipment_equip_enchanted` / `equipment_unequip_enchanted` so weapon/shield instances go through the slot equip (armour keeps the bool path). Add a helper:

```python
from aose.engine.enchant import _kind_of_instance  # weapon/armor/shield/ammunition

@router.post("/character/{character_id}/equipment/equip-enchanted")
async def equipment_equip_enchanted(request: Request, character_id: str,
                                    instance_id: str = Form(...),
                                    slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    kind = next((_kind_of_instance(i, data) for i in spec.enchanted
                 if i.instance_id == instance_id), None)
    try:
        if kind in ("weapon", "shield"):
            spec.equipped = _equip(
                instance_id, inventory=spec.inventory, equipped=spec.equipped,
                enchanted=spec.enchanted, data=data, slot=slot,
                two_weapon=spec.ruleset.two_weapon_fighting,
                eligible=two_weapon_eligible(classes),
                gargantua_1h_2h=one_handed_two_handed_weapons(spec, data),
                allowed_weapons=allowed_weapon_ids(classes, data, spec.ruleset),
                allowed_armor=allowed_armor_ids(classes, data),
                allow_shields=shields_allowed(classes),
            )
        else:
            spec.enchanted = _equip_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-enchanted")
async def equipment_unequip_enchanted(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    kind = next((_kind_of_instance(i, data) for i in spec.enchanted
                 if i.instance_id == instance_id), None)
    try:
        if kind in ("weapon", "shield"):
            spec.equipped = _unequip(instance_id, equipped=spec.equipped)
        else:
            spec.enchanted = _unequip_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

(`equipped_enchanted(spec, data, "armor")` in `armor_class.py` still reads the bool for body armour — leave it. `equipped_enchanted(..., "weapon"/"shield")` is no longer consulted by AC/attacks; the bool just stays False for slot-resident instances.)

- [ ] **Step 10: Wizard — equip/unequip/stash/remove/stow + inventory_view**

In `aose/web/wizard.py`, apply the parallel changes for the draft flow. Drafts store the same `equipped` dict; `enchanted` is typically empty in the wizard, so pass `enchanted=[]`. Compute `classes` as already done in each handler.

- Equipment-step render (~line 1419, 1458): drop `equipped_weapons = draft.get(...)`; the `inventory_view(...)` call drops the `equipped_weapons` positional arg; the ammo `load_options` loop (~1439) iterates `set(draft.get("equipped", {}).values())` instead of `equipped_weapons`.
- equip handler (~1566): 

```python
        new_eq = _equip(
            item_id,
            inventory=draft.get("inventory", []),
            equipped=draft.get("equipped", {}),
            enchanted=[], data=data, slot=form.get("slot"),
            two_weapon=_ruleset_of(draft).two_weapon_fighting,
            eligible=two_weapon_eligible(classes),
            gargantua_1h_2h=one_handed_two_handed_weapons_for_draft(draft, data),
            allowed_weapons=allowed_weapon_ids(classes, data, _ruleset_of(draft)),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["equipped"] = new_eq
```

  (Drop `draft["equipped_weapons"] = ...`. For the gargantua flag in the wizard, build a throwaway spec from the draft as other wizard code does, or add a small helper `one_handed_two_handed_weapons_for_draft` that checks whether the draft's race/class id is `gargantua`. Simplest: `gargantua_1h_2h = draft.get("race_id") == "gargantua" or "gargantua" in _class_ids(draft)`.)
- unequip handler (~1588): `new_eq = _unequip(item_id, equipped=draft.get("equipped", {}))`; set `draft["equipped"] = new_eq`; drop the `equipped_weapons` line.
- stash handler (~1607): `new_inv, new_stashed, new_eq = shop_stash(draft.get("inventory", []), draft.get("stashed", []), draft.get("equipped", {}), item_id, data)`; drop the `equipped_weapons` line.
- stow handler (~1652): drop the `equipped_weapons` arg.
- remove handler (~1878): `new_inv, new_gold, new_eq = shop_remove(..., draft.get("equipped", {}))`; drop the `equipped_weapons` arg/line.
- Any `CharacterSpec(... equipped_weapons=...)` construction (~1937): delete that kwarg.

- [ ] **Step 11: Sweep for stragglers**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q` and also search the tree:

Run: search for `equipped_weapons` across `aose/` and `tests/` (Grep). Every remaining hit must be removed or rewritten. Update `tests/test_equip_attacks.py`, `tests/test_encumbrance.py`, `tests/test_sheet*.py`, `tests/test_web.py`, and any draft/storage tests that set `equipped_weapons` — replace with `equipped={"main_hand": "...", "off_hand": "..."}`.

- [ ] **Step 12: Full suite green**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known `pytest-current` PermissionError).

- [ ] **Step 13: Commit**

```bash
git add -A
git commit -m "refactor(equip): replace equipped_weapons with main_hand/off_hand slots"
```

---

## Task 6: Two-weapon penalties + versatile-variant suppression

**Files:**
- Modify: `aose/engine/attacks.py`
- Test: `tests/test_equip_attacks.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_equip_attacks.py` (use the file's existing fixtures/spec builders; mirror their style):

```python
def test_dual_wield_applies_minus_2_and_minus_4(data):
    from aose.engine.attacks import attack_profiles
    spec = _fighter_spec(data)  # STR/DEX eligible; helper in this file
    spec.ruleset.two_weapon_fighting = True
    spec.inventory = ["sword", "dagger"]
    spec.equipped = {"main_hand": "sword", "off_hand": "dagger"}
    profs = {p.name: p for p in attack_profiles(spec, data)}
    sword = profs["Sword"]
    dagger = profs["Dagger"]
    # Ascending: lower is worse. Compare against the same weapon solo.
    solo = _fighter_spec(data)
    solo.inventory = ["sword"]
    solo.equipped = {"main_hand": "sword"}
    sword_solo = {p.name: p for p in attack_profiles(solo, data)}["Sword"]
    assert sword.to_hit_ascending == sword_solo.to_hit_ascending - 2
    assert sword.hand == "main"
    assert dagger.hand == "off"
    # Off-hand dagger is 2 worse than main-hand dagger would be (−4 vs −2).
    assert dagger.to_hit_ascending == sword.to_hit_ascending - 2


def test_no_penalty_without_dual_wield(data):
    from aose.engine.attacks import attack_profiles
    spec = _fighter_spec(data)
    spec.inventory = ["sword", "shield"]
    spec.equipped = {"main_hand": "sword", "off_hand": "shield"}
    sword = {p.name: p for p in attack_profiles(spec, data)}["Sword"]
    solo = _fighter_spec(data)
    solo.inventory = ["sword"]
    solo.equipped = {"main_hand": "sword"}
    sword_solo = {p.name: p for p in attack_profiles(solo, data)}["Sword"]
    assert sword.to_hit_ascending == sword_solo.to_hit_ascending
    assert sword.hand is None


def test_versatile_two_handed_variant_suppressed_with_shield(data):
    from aose.engine.attacks import attack_profiles
    spec = _fighter_spec(data)
    spec.ruleset.variable_weapon_damage = True
    spec.inventory = ["bastard_sword", "shield"]
    spec.equipped = {"main_hand": "bastard_sword", "off_hand": "shield"}
    names = [p.name for p in attack_profiles(spec, data)]
    assert "Bastard Sword (Two-handed)" not in names
```

(If `_fighter_spec` doesn't exist in the file, add a small builder that returns a fighter `CharacterSpec` at level 1; fighters are STR-prime so eligible.)

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -k "dual_wield or versatile_two_handed_variant_suppressed or no_penalty_without" -q`
Expected: FAIL (`hand` attribute missing / variant present).

- [ ] **Step 3: Add the `hand` field + penalty + suppression**

In `aose/engine/attacks.py`:

- Add to `AttackProfile`: `hand: str | None = None   # "main" / "off" when dual-wielding`.
- Add a `dual_penalty: int = 0` parameter to `_profile_for` and fold it into the to-hit math (negative = worse, like `prof_pen`):

```python
    def hit_thac0(extra: int) -> int:
        return base_thac0 - atk_mod - prof_pen - spec_hit - extra - g_atk - dual_penalty

    def hit_asc(extra: int) -> int:
        return base_attack + atk_mod + prof_pen + spec_hit + extra + g_atk + dual_penalty
```

- In `attack_profiles`, before the slot loop compute dual-wield state:

```python
    from aose.engine.equip import resolve_slot
    main_w = resolve_slot(spec.equipped.get("main_hand"), data, spec.enchanted)
    off_w = resolve_slot(spec.equipped.get("off_hand"), data, spec.enchanted)
    dual = isinstance(main_w, Weapon) and isinstance(off_w, Weapon)
    off_hand_free = off_w is None
```

- In the slot loop, set the penalty + hand label + variant gate:

```python
        dual_penalty = 0
        hand = None
        if dual:
            if slot_name == "main_hand":
                dual_penalty, hand = -2, "main"
            else:
                dual_penalty, hand = -4, "off"
        base = _profile_for(item, spec, data, 1, eff, base_thac0, g_atk, g_dmg,
                            manageable_item_id=manageable, dual_penalty=dual_penalty,
                            **_ammo_args(item))
        base = base.model_copy(update={"hand": hand})
        weapon_profiles.append(base)
        if off_hand_free:
            variant = _two_handed_variant(base, item, spec)
            if variant is not None:
                weapon_profiles.append(variant)
```

(The versatile two-handed variant only appears when the off hand is free — i.e. no shield and no off-hand weapon. `off_hand_free` is the gate.)

- [ ] **Step 4: Run — expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py -q`
Expected: PASS. Then full suite: `.venv\Scripts\python.exe -m pytest tests/ -q`.

- [ ] **Step 5: Commit**

```bash
git add aose/engine/attacks.py tests/test_equip_attacks.py
git commit -m "feat(attacks): two-weapon −2/−4 penalties + off-hand labels; suppress versatile 2H variant when off hand full"
```

---

## Task 7: UI — equip controls, attack labels, slot picker

**Files:**
- Modify: `aose/web/templates/sheet.html`, `aose/web/static/sheet_overlays.js`, wizard equipment template (find via `Glob aose/web/templates/**/*equipment*` or the `inventory` partial used by both sheet and wizard)
- Test: `tests/test_web.py` / `tests/test_inventory_view.py` (route-level smoke)

> The working tree already has uncommitted edits in `routes.py`, `sheet_overlays.js`, `sheet.html` from prior work. Before editing, view the current state of each (`git diff`) so you build on it rather than clobbering it.

- [ ] **Step 1: Surface off-hand state from `inventory_view`**

Add fields to `InventoryRow` in `aose/engine/shop.py` so the template knows when to show the off-hand control:

```python
    can_off_hand: bool = False     # rule on + eligible + weapon passes off-hand test
    off_hand_blocked: bool = False # can_off_hand but the off hand is already full
```

Populate them in `inventory_view`. Thread two new params (`two_weapon`, `eligible`, `gargantua_1h_2h`) into `inventory_view` and `_build_row` and compute, for each weapon row:

```python
    # in inventory_view, after resolving slots:
    off_full = bool(equipped.get("off_hand"))
    # in _build_row for a Weapon:
    from aose.engine.equip import off_hand_eligible
    can_off = (two_weapon and eligible and isinstance(item, Weapon)
               and off_hand_eligible(item))
    # off_hand_blocked = can_off and off_full
```

Update the sheet and wizard `inventory_view(...)` calls to pass `two_weapon=spec.ruleset.two_weapon_fighting, eligible=two_weapon_eligible(classes), gargantua_1h_2h=one_handed_two_handed_weapons(spec, data)`.

- [ ] **Step 2: Write a route smoke test**

Add to `tests/test_inventory_view.py`:

```python
def test_off_hand_flags_for_eligible_dual_wielder(data):
    from aose.engine.shop import inventory_view
    view = inventory_view(
        ["sword", "dagger"], [], {"main_hand": "sword"}, None, data,
        two_weapon=True, eligible=True, gargantua_1h_2h=False,
    )
    dagger = next(r for r in view.carried if r.id == "dagger")
    assert dagger.can_off_hand is True
    assert dagger.off_hand_blocked is False
```

- [ ] **Step 3: Run — expect FAIL, then implement Step 1, then PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_inventory_view.py -k off_hand -q`

- [ ] **Step 4: Template — off-hand equip button**

In the inventory partial used for carried weapons (find the existing "Equip" control in `sheet.html` / the shared inventory include), add, next to the main Equip button, an off-hand action gated on `row.can_off_hand`, posting `slot=off_hand`:

```html
{% if row.can_off_hand %}
  <button type="submit"
          formaction="{{ target_url_prefix }}/equip"
          name="slot" value="off_hand"
          {% if row.off_hand_blocked %}disabled
            title="Off hand is full — unequip your shield or off-hand weapon first"
          {% endif %}>
    Off-hand
  </button>
{% endif %}
```

(The main Equip button keeps posting without `slot`, defaulting to `main_hand`. Match the surrounding form/markup conventions and OSR-zine tokens per `docs/STYLE-GUIDE.md`.)

- [ ] **Step 5: Template — attack-row hand labels**

Where attack profiles render (attacks block in `sheet.html`), append the hand label when present:

```html
{% if prof.hand == "main" %}<span class="atk-tag">primary −2</span>{% endif %}
{% if prof.hand == "off" %}<span class="atk-tag">off-hand −4</span>{% endif %}
```

- [ ] **Step 6: Verify in the browser**

Start the app (`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`) using the preview tools. Build a fighter, enable Two Weapons in settings, equip a sword then a dagger off-hand, and confirm: the Off-hand button appears for the dagger, becomes disabled once filled, and the attack rows show "primary −2" / "off-hand −4". Screenshot for proof.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(sheet): off-hand equip control + dual-wield attack labels"
```

---

## Task 8: Cascade clear when two-weapon rule is disabled

**Files:**
- Modify: `aose/web/wizard.py` (`_apply_rule_changes`)
- Test: `tests/test_wizard_rules_step.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_wizard_rules_step.py` (mirror the existing cascade tests' draft setup):

```python
def test_disabling_two_weapon_drops_off_hand_weapon(data):
    from aose.models import RuleSet
    from aose.web.wizard import _apply_rule_changes
    draft = {
        "abilities": {"STR": 12},
        "ruleset": RuleSet(two_weapon_fighting=True).model_dump(),
        "equipped": {"main_hand": "sword", "off_hand": "dagger"},
    }
    old = RuleSet(two_weapon_fighting=True)
    new = RuleSet(two_weapon_fighting=False)
    _apply_rule_changes(draft, old, new, data)
    assert draft["equipped"].get("off_hand") is None
    assert draft["equipped"]["main_hand"] == "sword"


def test_disabling_two_weapon_keeps_off_hand_shield(data):
    from aose.models import RuleSet
    from aose.web.wizard import _apply_rule_changes
    draft = {
        "abilities": {"STR": 12},
        "ruleset": RuleSet(two_weapon_fighting=True).model_dump(),
        "equipped": {"main_hand": "sword", "off_hand": "shield"},
    }
    _apply_rule_changes(draft, RuleSet(two_weapon_fighting=True),
                        RuleSet(two_weapon_fighting=False), data)
    assert draft["equipped"]["off_hand"] == "shield"  # a shield is unaffected
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_rules_step.py -k two_weapon -q`
Expected: FAIL.

- [ ] **Step 3: Add the cascade clause**

In `aose/web/wizard.py`, inside `_apply_rule_changes` (after the existing clauses, before the `disabled_sources` block):

```python
    if not new_rs.two_weapon_fighting and old_rs.two_weapon_fighting:
        equipped = draft.get("equipped", {})
        off = equipped.get("off_hand")
        if off and data is not None:
            item = data.items.get(off)
            from aose.models import Weapon
            if isinstance(item, Weapon):   # a shield stays; an off-hand weapon goes
                equipped.pop("off_hand", None)
                draft["equipped"] = equipped
```

- [ ] **Step 4: Run — expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_rules_step.py -k two_weapon -q`
Expected: PASS. Then full suite.

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py tests/test_wizard_rules_step.py
git commit -m "feat(wizard): drop off-hand weapon when two-weapon rule disabled"
```

---

## Task 9: Documentation

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`

- [ ] **Step 1: CHANGELOG row**

Add a one-line row to the top of `docs/CHANGELOG.md`:

```
| 2026-06-10 | Wield capacity (main_hand/off_hand slots) + two-weapon fighting + gargantua 1H 2H-melee | <branch> | 2026-06-10-wield-capacity-equip |
```

(Match the existing table's column layout.)

- [ ] **Step 2: ARCHITECTURE update**

In `docs/ARCHITECTURE.md`, edit the equipment/encumbrance (storage shapes) subsystem section in place: document that `equipped` now carries `armor`/`main_hand`/`off_hand` (values may be catalog ids or enchanted instance ids), that `equipped_weapons` is gone, that `validate_wield` in `engine/equip.py` is the wield gate, and that enchanted weapons/shields are slot-resident (the `equipped` bool is body-armour only). Note the gargantua `one_handed_two_handed_melee` flag and the `two_weapon_fighting` rule.

- [ ] **Step 3: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md
git commit -m "docs: record wield capacity + two-weapon fighting"
```

---

## Self-Review Notes (for the implementer)

- **`equipped_weapons` must be fully gone.** After Task 5, a tree-wide search for `equipped_weapons` should return zero hits in `aose/` and `tests/`.
- **Signature consistency:** `equip(item_id, *, ...) -> dict`, `unequip(item_id, *, equipped) -> dict`, `shop.stash/remove/stow/inventory_view` all drop their `equipped_weapons` parameter and tuple element. If a call site still unpacks two values from `equip`/`unequip`, it's a bug.
- **Enchanted parity:** enchanted weapons/shields equip via the same slot `equip()`; `equipped_enchanted(..., "weapon"/"shield")` is no longer read by AC/attacks (only `"armor"` remains). Don't leave a second code path reading the bool for weapons/shields.
- **Penalty sign:** `dual_penalty` is negative (−2/−4) and combined exactly like `prof_pen` (subtracted from THAC0, added to ascending). A positive value would *help* — wrong.
- **Versatile variant gate** is `off_hand_free`, not `not dual` — a shield in the off hand must also suppress it.
