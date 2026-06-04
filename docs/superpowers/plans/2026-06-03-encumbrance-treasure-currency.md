# Faithful Encumbrance, Treasure Weight & Multi-Coin Currency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make encumbrance match the two AOSE options (Basic & Detailed), give coins/gems/jewellery/treasure their book weights, and add a multi-denomination coin purse (pp/gp/ep/sp/cp) with conversion.

**Architecture:** A new cycle-free `aose/engine/currency.py` owns denominations, value, coin-count (weight), and conversion. `valuables.py` gains a weight helper. `encumbrance.py` is rewritten around two clear weight helpers (`treasure_weight_cn`, `equipment_weight_cn`) and the two real AOSE movement tables, dropping the old `(armour × band)` table and dead demihuman scaling. The sheet view + Jinja templates expose the purse (add/convert), the carrying-treasure toggle, and the corrected tables. `gold` stays as the gp/shop-spendable balance; four new count fields sit alongside it (no migration — app isn't deployed).

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest tests/ -q` (PowerShell; the trailing pytest-current PermissionError is a known Windows quirk — ignore).

**Spec:** `docs/superpowers/specs/2026-06-03-encumbrance-treasure-currency-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `aose/models/character.py` | `CharacterSpec` gains `platinum/electrum/silver/copper` counts + `carrying_treasure` flag | Modify |
| `aose/engine/currency.py` | Denominations, value totals, coin-count weight, `convert` | Create |
| `aose/engine/valuables.py` | `valuables_weight_cn` | Modify |
| `aose/engine/encumbrance.py` | Treasure/equipment weight helpers + two AOSE movement tables | Rewrite |
| `aose/sheet/view.py` | Expose purse, treasure value/weight, carrying-treasure, reworked `EncumbranceTable` | Modify |
| `aose/web/routes.py` | `/coins/add`, `/coins/convert`, `/carrying-treasure` | Modify |
| `aose/web/templates/sheet/*.html` | Coin purse (add/convert), tables, toggle, valuables weight | Modify |
| `tests/test_currency.py` | Currency engine + routes | Create |
| `tests/test_encumbrance.py` | Rewritten for the new model | Rewrite |
| `tests/test_valuables.py` | Add weight tests | Modify |

**Key shared constants/signatures (referenced across tasks):**

```python
# aose/engine/currency.py
DENOMINATIONS = ("pp", "gp", "ep", "sp", "cp")
RATES = {"pp": 500, "gp": 100, "ep": 50, "sp": 10, "cp": 1}   # cp-equivalents
_ATTR = {"pp": "platinum", "gp": "gold", "ep": "electrum", "sp": "silver", "cp": "copper"}

# aose/engine/encumbrance.py
MAX_LOAD = 1600
TREASURE_CATEGORIES = {"magic_potions", "magic_rods_staves_wands", "scrolls"}
_DETAILED_MOVE = [120, 90, 60, 30, 0]          # band 0..4
_BAND_UPPER = [400, 600, 800, 1600]            # band 4 == over MAX_LOAD
_BASIC_TABLE = {
    ("none", False): 120, ("none", True): 90,
    ("leather", False): 90, ("leather", True): 60,
    ("metal", False): 60, ("metal", True): 30,
}
```

---

## Task 1: Currency model fields

**Files:**
- Modify: `aose/models/character.py` (near `gold: int = 0`, ~line 159)
- Test: `tests/test_currency.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_currency.py
from aose.models import CharacterSpec, ClassEntry


def _spec(**kw):
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_coin_fields_default_zero():
    s = _spec()
    assert (s.platinum, s.gold, s.electrum, s.silver, s.copper) == (0, 0, 0, 0, 0)


def test_carrying_treasure_defaults_false():
    assert _spec().carrying_treasure is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: FAIL — `CharacterSpec` rejects `platinum` (extra="forbid") / no attribute.

- [ ] **Step 3: Add the fields**

In `aose/models/character.py`, replace `gold: int = 0` with:

```python
    gold: int = 0            # gp — the shop-spendable balance
    platinum: int = 0        # pp
    electrum: int = 0        # ep
    silver: int = 0          # sp
    copper: int = 0          # cp
    # Basic-encumbrance referee toggle: carrying a significant amount of
    # treasure (drops the movement rate one step). Detailed mode ignores it.
    carrying_treasure: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/models/character.py tests/test_currency.py
git commit -m "feat: add coin denomination fields + carrying_treasure flag"
```

---

## Task 2: Currency engine

**Files:**
- Create: `aose/engine/currency.py`
- Test: `tests/test_currency.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_currency.py  (append)
import pytest
from aose.engine import currency
from aose.engine.currency import CurrencyError


def test_total_value_gp_sums_denominations():
    s = _spec(platinum=1, gold=2, electrum=2, silver=10, copper=100)
    # 1pp=5gp, 2ep=1gp, 10sp=1gp, 100cp=1gp -> 5+2+1+1+1 = 10 gp
    assert currency.total_value_gp(s) == 10


def test_coin_count_is_total_coins():
    s = _spec(platinum=1, gold=2, electrum=2, silver=10, copper=100)
    assert currency.coin_count(s) == 1 + 2 + 2 + 10 + 100


def test_convert_pp_to_gp_exact():
    s = _spec(platinum=3, gold=1)
    changes = currency.convert(s, "pp", "gp", 2)        # 2pp -> 10gp
    assert changes == {"platinum": 1, "gold": 11}


def test_convert_gp_to_sp_multiplies():
    s = _spec(gold=5)
    changes = currency.convert(s, "gp", "sp", 2)        # 2gp -> 20sp
    assert changes == {"gold": 3, "silver": 20}


def test_convert_rejects_non_whole_result():
    s = _spec(copper=50)
    with pytest.raises(CurrencyError):
        currency.convert(s, "cp", "gp", 50)             # 50cp != whole gp


def test_convert_rejects_insufficient_coins():
    s = _spec(gold=1)
    with pytest.raises(CurrencyError):
        currency.convert(s, "gp", "sp", 2)


def test_convert_rejects_same_denom_and_bad_count():
    s = _spec(gold=5)
    with pytest.raises(CurrencyError):
        currency.convert(s, "gp", "gp", 1)
    with pytest.raises(CurrencyError):
        currency.convert(s, "gp", "sp", 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: FAIL — `No module named aose.engine.currency`.

- [ ] **Step 3: Implement the engine**

```python
# aose/engine/currency.py
"""Multi-coin currency — the cycle-free core for the character's purse.

Five denominations (pp/gp/ep/sp/cp). ``gold`` (gp) stays the shop-spendable
balance; the others are held coins contributing value + weight (1 cn each).
Values are computed in a copper base to avoid floats. ``convert`` makes change
at the official AOSE rates and refuses non-whole-coin results. Pure functions:
``convert`` returns the changed field values; the caller applies them. Imports
only models; nothing imports it back.
"""
from __future__ import annotations

from aose.models import CharacterSpec

DENOMINATIONS = ("pp", "gp", "ep", "sp", "cp")
RATES = {"pp": 500, "gp": 100, "ep": 50, "sp": 10, "cp": 1}   # cp-equivalents
_ATTR = {"pp": "platinum", "gp": "gold", "ep": "electrum",
         "sp": "silver", "cp": "copper"}


class CurrencyError(ValueError):
    """Currency validation / conversion errors (routes map to HTTP 400)."""


def total_value_cp(spec: CharacterSpec) -> int:
    return sum(getattr(spec, _ATTR[d]) * RATES[d] for d in DENOMINATIONS)


def total_value_gp(spec: CharacterSpec) -> int:
    """Whole-gp worth of the purse (floors any sub-gp remainder)."""
    return total_value_cp(spec) // RATES["gp"]


def coin_count(spec: CharacterSpec) -> int:
    """Total number of coins — the encumbrance weight (1 cn per coin)."""
    return sum(getattr(spec, _ATTR[d]) for d in DENOMINATIONS)


def convert(spec: CharacterSpec, frm: str, to: str, count: int) -> dict[str, int]:
    """Convert ``count`` coins of ``frm`` into ``to`` at official rates.

    Returns ``{attr_name: new_count}`` for the two affected denominations.
    Raises ``CurrencyError`` on unknown/identical denom, non-positive count,
    insufficient source coins, or a result that isn't a whole number of ``to``.
    """
    if frm not in RATES or to not in RATES:
        raise CurrencyError(f"unknown denomination: {frm!r} / {to!r}")
    if frm == to:
        raise CurrencyError("cannot convert a coin to itself")
    if count <= 0:
        raise CurrencyError("convert count must be positive")
    have = getattr(spec, _ATTR[frm])
    if have < count:
        raise CurrencyError(f"only {have} {frm} available, need {count}")
    value_cp = count * RATES[frm]
    if value_cp % RATES[to] != 0:
        raise CurrencyError(
            f"{count}{frm} does not convert to a whole number of {to}")
    gained = value_cp // RATES[to]
    return {
        _ATTR[frm]: have - count,
        _ATTR[to]: getattr(spec, _ATTR[to]) + gained,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/currency.py tests/test_currency.py
git commit -m "feat: currency engine (value, coin-count weight, convert)"
```

---

## Task 3: Currency routes

**Files:**
- Modify: `aose/web/routes.py` (after `grant_gold`, ~line 268)
- Test: `tests/test_currency.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_currency.py  (append)
from pathlib import Path
from fastapi.testclient import TestClient
from aose.characters import save_character
from aose.data.loader import GameData
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _client(tmp_path):
    app = create_app(characters_dir=tmp_path, data_dir=DATA_DIR)
    return TestClient(app), app


def test_coins_add_route(tmp_path):
    client, app = _client(tmp_path)
    cid = "c1"
    save_character(cid, _spec(), app.state.characters_dir)
    r = client.post(f"/character/{cid}/coins/add",
                    data={"denom": "sp", "amount": "25"}, follow_redirects=False)
    assert r.status_code == 303
    from aose.characters import load_character
    s = load_character(cid, app.state.characters_dir)
    assert s.silver == 25


def test_coins_add_clamps_at_zero(tmp_path):
    client, app = _client(tmp_path)
    cid = "c1"
    save_character(cid, _spec(silver=10), app.state.characters_dir)
    client.post(f"/character/{cid}/coins/add", data={"denom": "sp", "amount": "-50"})
    from aose.characters import load_character
    assert load_character(cid, app.state.characters_dir).silver == 0


def test_coins_convert_route(tmp_path):
    client, app = _client(tmp_path)
    cid = "c1"
    save_character(cid, _spec(platinum=2), app.state.characters_dir)
    client.post(f"/character/{cid}/coins/convert",
                data={"from_denom": "pp", "to_denom": "gp", "count": "2"})
    from aose.characters import load_character
    s = load_character(cid, app.state.characters_dir)
    assert (s.platinum, s.gold) == (0, 10)


def test_coins_convert_bad_request(tmp_path):
    client, app = _client(tmp_path)
    cid = "c1"
    save_character(cid, _spec(gold=1), app.state.characters_dir)
    r = client.post(f"/character/{cid}/coins/convert",
                    data={"from_denom": "gp", "to_denom": "sp", "count": "99"})
    assert r.status_code == 400
```

> Check `create_app` / `load_character` signatures against an existing route test (e.g. `tests/test_valuables_routes.py`) and mirror them exactly — adjust the fixture above if the project's helper signatures differ.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: FAIL — 404 (routes not defined).

- [ ] **Step 3: Add the routes**

In `aose/web/routes.py`, add near the imports (top of file, with the other engine imports):

```python
from aose.engine import currency
from aose.engine.currency import CurrencyError
```

After the `grant_gold` route (~line 268):

```python
@router.post("/character/{character_id}/coins/add")
async def add_coins(request: Request, character_id: str,
                    denom: str = Form(...), amount: int = Form(...)):
    """Add or subtract coins of one denomination, clamped at zero."""
    spec = _load_spec_or_404(request, character_id)
    if denom not in currency.RATES:
        raise HTTPException(400, f"unknown denomination {denom!r}")
    attr = currency._ATTR[denom]
    setattr(spec, attr, max(0, getattr(spec, attr) + amount))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/coins/convert")
async def convert_coins(request: Request, character_id: str,
                        from_denom: str = Form(...), to_denom: str = Form(...),
                        count: int = Form(...)):
    """Make change between two denominations at official rates."""
    spec = _load_spec_or_404(request, character_id)
    try:
        changes = currency.convert(spec, from_denom, to_denom, count)
    except CurrencyError as e:
        raise HTTPException(400, str(e))
    for attr, value in changes.items():
        setattr(spec, attr, value)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_currency.py
git commit -m "feat: /coins/add and /coins/convert routes"
```

---

## Task 4: Gem & jewellery weight

**Files:**
- Modify: `aose/engine/valuables.py` (append helper; update docstrings)
- Test: `tests/test_valuables.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_valuables.py  (append; reuse the file's existing spec helpers)
from aose.engine.valuables import valuables_weight_cn
from aose.models import GemStack, JewelleryPiece


def test_valuables_weight_gems_one_each_jewellery_ten_each():
    spec = _spec(  # use this file's existing spec builder
        gems=[GemStack(instance_id="g1", value=100, count=3)],
        jewellery=[JewelleryPiece(instance_id="j1", value=800),
                   JewelleryPiece(instance_id="j2", value=400, damaged=True)],
    )
    # 3 gems * 1 + 2 pieces * 10 = 23 (damaged does not change weight)
    assert valuables_weight_cn(spec) == 23
```

> If `tests/test_valuables.py` has no `_spec` helper, construct a `CharacterSpec` inline as in Task 1.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -q`
Expected: FAIL — `cannot import name 'valuables_weight_cn'`.

- [ ] **Step 3: Implement**

In `aose/engine/valuables.py`, append:

```python
def valuables_weight_cn(spec: CharacterSpec) -> int:
    """Encumbrance weight of owned gems + jewellery: 1 cn per gem,
    10 cn per jewellery piece (a piece's damaged state does not affect
    weight)."""
    return sum(g.count for g in spec.gems) + 10 * len(spec.jewellery)
```

Update the module docstring and the two model docstrings in
`aose/models/valuable.py`: remove "Weightless" — gems weigh 1 cn each,
jewellery 10 cn each (per the AOSE treasure-encumbrance table).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_valuables.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/valuables.py aose/models/valuable.py tests/test_valuables.py
git commit -m "feat: gem (1 cn) and jewellery (10 cn) encumbrance weight"
```

---

## Task 5: Treasure weight helper in encumbrance

**Files:**
- Modify: `aose/engine/encumbrance.py` (add helpers near top)
- Test: `tests/test_encumbrance.py` (append; full rewrite comes in Task 9)

This adds `treasure_item_weight` (per the AOSE table, derived from category +
id-prefix so the 66 richly-commented magic-item YAML entries are left
untouched) and `treasure_weight_cn`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_encumbrance.py  (append)
from aose.engine.encumbrance import treasure_weight_cn
from aose.models import GemStack, JewelleryPiece, MagicItemInstance, SpellSource


def test_treasure_weight_coins_gems_jewellery(data):
    spec = _spec()
    spec.gold = 50            # 50 coins
    spec.silver = 30          # 30 coins
    spec.gems = [GemStack(instance_id="g", value=100, count=5)]      # 5 cn
    spec.jewellery = [JewelleryPiece(instance_id="j", value=900)]    # 10 cn
    assert treasure_weight_cn(spec, data) == 50 + 30 + 5 + 10


def test_treasure_weight_potion_and_scroll(data):
    spec = _spec()
    # A potion (magic_potions -> 10 cn). Use any potion id present in data.
    spec.magic_items = [MagicItemInstance(
        instance_id="m", catalog_id="potion_clairvoyance")]
    spec.spell_sources = [SpellSource(
        instance_id="s", kind="scroll", caster_type="arcane", entries=[])]
    assert treasure_weight_cn(spec, data) == 10 + 1
```

> Confirm `MagicItemInstance` / `SpellSource` constructor fields against
> `aose/models/character.py` and adjust the kwargs if needed.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py::test_treasure_weight_coins_gems_jewellery -q`
Expected: FAIL — `cannot import name 'treasure_weight_cn'`.

- [ ] **Step 3: Implement**

At the top of `aose/engine/encumbrance.py`, add the constants and helpers:

```python
MAX_LOAD = 1600
TREASURE_CATEGORIES = {"magic_potions", "magic_rods_staves_wands", "scrolls"}


def treasure_item_weight(item) -> int:
    """AOSE treasure-encumbrance weight for a carried magic item / scroll.
    Potions 10, wands 10, rods 20, staves 40, protection scrolls 1; anything
    else 0.  Derived from category (+ id prefix for rods/staves/wands) so the
    commented catalog YAML needs no per-item weight edits."""
    cat = getattr(item, "category", "")
    if cat == "magic_potions":
        return 10
    if cat == "scrolls":
        return 1
    if cat == "magic_rods_staves_wands":
        iid = getattr(item, "id", "")
        if iid.startswith("staff"):
            return 40
        if iid.startswith("rod"):
            return 20
        if iid.startswith("wand"):
            return 10
    return 0


def treasure_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Weight of tracked treasure: coins (1 cn each) + gems (1) + jewellery
    (10) + carried treasure magic items (potions/rods/staves/wands) + scrolls
    held as spell sources (1 cn each).  Used to enforce the 1,600 cap in basic
    mode and as part of the detailed-mode total."""
    from aose.engine import currency, valuables

    total = currency.coin_count(spec) + valuables.valuables_weight_cn(spec)
    for mi in spec.magic_items:
        item = data.items.get(mi.catalog_id)
        if item is not None:
            total += treasure_item_weight(item)
    total += sum(1 for s in spec.spell_sources if s.kind == "scroll")
    return total
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k treasure_weight -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "feat: treasure_weight_cn per AOSE treasure-encumbrance table"
```

---

## Task 6: Equipment weight helper (detailed mode)

**Files:**
- Modify: `aose/engine/encumbrance.py`
- Test: `tests/test_encumbrance.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_encumbrance.py  (append)
from aose.engine.encumbrance import equipment_weight_cn
from aose.models import MagicItemInstance


def test_equipment_weapon_armour_by_weight(data):
    # Long Sword 60 cn + Chain Mail 400 cn; no adventuring gear -> no flat 80
    spec = _spec(inventory=["sword", "chain_mail"],
                 equipped={"armor": "chain_mail"})
    assert equipment_weight_cn(spec, data) == 60 + 400


def test_equipment_flat_80_for_adventuring_gear(data):
    # A torch is AdventuringGear (item_type "gear") -> flat 80, its own 20 cn
    # is ignored. Gear's individual weights never contribute (book RAW).
    spec = _spec(inventory=["sword", "torch", "torch"])
    assert equipment_weight_cn(spec, data) == 60 + 80


def test_equipment_no_gear_no_flat_80(data):
    assert equipment_weight_cn(_spec(inventory=["sword"]), data) == 60


def test_non_treasure_magic_item_does_not_trigger_flat_80(data):
    # A ring is a MagicItem (magic_rings), NOT adventuring gear: it contributes
    # only its own weight (0 here) and must not pull in the flat 80.
    spec = _spec()
    spec.magic_items = [MagicItemInstance(
        instance_id="m", catalog_id="ring_control_animals")]
    assert equipment_weight_cn(spec, data) == 0
```

> Confirm `MagicItemInstance` constructor fields against
> `aose/models/character.py`; `ring_control_animals` is a real `magic_rings`
> id in `data/equipment/magic_items.yaml`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k equipment_ -q`
Expected: FAIL — `cannot import name 'equipment_weight_cn'`.

- [ ] **Step 3: Implement**

Add to `aose/engine/encumbrance.py`:

```python
def equipment_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Detailed-mode equipment weight (everything that isn't tracked treasure):

      * carried weapons + armour by listed weight (enchanted armour keeps its
        weight_multiplier);
      * non-treasure magic items (rings, misc) and other carried items (poison,
        etc.) by their own weight;
      * a flat 80 cn when the character carries ANY miscellaneous adventuring
        gear — AdventuringGear items or carried containers (backpacks, sacks).
        Gear's individual weights are never tracked (book RAW); the flat 80 is
        the whole of it.

    Treasure (coins/gems/jewellery/scrolls/potions/rods/staves/wands) is NOT
    counted here — it lives in treasure_weight_cn and contributes directly."""
    from aose.models import Weapon, Armor, AdventuringGear
    from aose.engine.enchant import resolve_instance

    total = 0
    has_gear = False
    for item_id in spec.inventory:
        item = data.items.get(item_id)
        if item is None:
            continue
        if isinstance(item, Armor):
            total += int(item.weight_cn * item.weight_multiplier)
        elif isinstance(item, Weapon):
            total += item.weight_cn
        elif isinstance(item, AdventuringGear):
            has_gear = True          # weight ignored — folded into the flat 80
        else:
            total += item.weight_cn  # poison, ammunition (0 cn), etc.

    # Enchanted weapons & armour count by weight too.
    for inst in spec.enchanted:
        resolved = resolve_instance(inst, data)
        if isinstance(resolved, Armor):
            total += int(resolved.weight_cn * resolved.weight_multiplier)
        elif isinstance(resolved, Weapon):
            total += resolved.weight_cn

    # Non-treasure magic items (rings, misc) by their own weight. Treasure-type
    # magic items (potions/rods/staves/wands) are weighed in treasure_weight_cn,
    # so skip them here to avoid double counting and to keep them OUT of the
    # flat-80 abstraction.
    for mi in spec.magic_items:
        item = data.items.get(mi.catalog_id)
        if item is not None and item.category not in TREASURE_CATEGORIES:
            total += item.weight_cn

    # Carried containers (backpacks, sacks) are adventuring gear → flat 80.
    if any(c.state == "carried" for c in spec.containers):
        has_gear = True

    if has_gear:
        total += 80
    return total
```

> Note: AdventuringGear `weight_cn` values in `data/equipment/*.yaml` are now
> vestigial for encumbrance (the flat 80 replaces them). Leave them as-is —
> they're harmless and may still inform inventory display. Do NOT mass-zero
> them in this plan.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k equipment_ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "feat: detailed-mode equipment weight (armour/weapons + flat-80 gear)"
```

---

## Task 7: Rewrite carried weight, bands, and movement

**Files:**
- Modify: `aose/engine/encumbrance.py` (replace `_TABLE_HUMAN`, `_scale`,
  `weight_band`, `carried_weight_cn`, `banding_weight_cn`, `effective_movement`)
- Test: `tests/test_encumbrance.py`

This is the core rewrite. Remove the old `(armour × band)` table, the
`_scale` demihuman helper, and the `_HUMAN_BASE`/`_BAND_LABELS` bits tied to
the old model. Replace with the AOSE tables.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_encumbrance.py  (append)
from aose.engine.encumbrance import (
    weight_band, carried_weight_cn, effective_movement,
)


def test_weight_band_thresholds():
    assert weight_band(0) == 0
    assert weight_band(400) == 0
    assert weight_band(401) == 1
    assert weight_band(600) == 1
    assert weight_band(800) == 2
    assert weight_band(1600) == 3
    assert weight_band(1601) == 4


def test_carried_weight_is_treasure_plus_equipment(data):
    spec = _spec(inventory=["sword"])     # 60 equipment, no gear
    spec.gold = 100                       # 100 treasure
    assert carried_weight_cn(spec, data) == 160


def test_detailed_movement_bands(data):
    # Unarmoured human; total weight purely from coins.
    def move(coins):
        s = _spec(encumbrance="detailed")
        s.gold = coins
        return effective_movement(s, data)
    assert move(400) == 120
    assert move(600) == 90
    assert move(800) == 60
    assert move(1600) == 30
    assert move(1601) == 0


def test_detailed_includes_armour_weight(data):
    # Chain mail 400 + 1 coin -> band 1 (>400) -> 90'
    s = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"},
              encumbrance="detailed")
    s.gold = 1
    assert effective_movement(s, data) == 90
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k "weight_band or detailed_movement or carried_weight_is" -q`
Expected: FAIL — thresholds wrong / `carried_weight_cn` still old shape.

- [ ] **Step 3: Implement**

In `aose/engine/encumbrance.py`:

1. Delete `_HUMAN_BASE`, `_BAND_LABELS`, `_TABLE_HUMAN`, and `_scale`.
2. Add/replace:

```python
_BAND_UPPER = [400, 600, 800, 1600]            # band 4 == over MAX_LOAD
_BAND_LABELS = ["≤ 400", "401–600", "601–800", "801–1600", "> 1600"]
_DETAILED_MOVE = [120, 90, 60, 30, 0]          # feet/turn per band


def weight_band(weight_cn: int) -> int:
    """Return 0–4 for the AOSE detailed band. Band 4 == over the 1,600 cap."""
    for i, upper in enumerate(_BAND_UPPER):
        if weight_cn <= upper:
            return i
    return 4


def band_label(band: int) -> str:
    return _BAND_LABELS[band]
```

3. Replace `carried_weight_cn` with the total (treasure + equipment):

```python
def carried_weight_cn(spec: CharacterSpec, data: GameData) -> int:
    """Total tracked weight in coins = treasure + detailed-mode equipment.
    Used for the detailed band and as the sheet's carried-weight figure."""
    return treasure_weight_cn(spec, data) + equipment_weight_cn(spec, data)
```

4. Keep `banding_weight_cn` but it now wraps the new `carried_weight_cn`
   (subtract the magic carry-capacity bonus, floor at 0) — leave its body
   unchanged since it already calls `carried_weight_cn`.

5. Replace `effective_movement` (basic branch filled in Task 8; detailed here):

```python
def effective_movement(spec: CharacterSpec, data: GameData) -> int:
    """Exploration movement (feet/turn) after encumbrance."""
    base = data.races[spec.race_id].base_movement
    mode = spec.ruleset.encumbrance
    if mode == "none":
        return base
    if mode == "basic":
        return _basic_movement(spec, data)
    band = weight_band(banding_weight_cn(spec, data))
    return _DETAILED_MOVE[band]
```

6. Add a placeholder `_basic_movement` so the module imports (completed in
   Task 8):

```python
def _basic_movement(spec: CharacterSpec, data: GameData) -> int:
    raise NotImplementedError  # implemented in Task 8
```

> Note: AOSE movement tables are absolute, so the demihuman `base/120`
> scaling is intentionally gone. `base` is now used only in `none` mode and
> for the sheet's "unencumbered" reference.

- [ ] **Step 4: Run to verify the detailed tests pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k "weight_band or detailed_movement or carried_weight_is or detailed_includes" -q`
Expected: PASS (basic-mode tests still fail / error — fixed in Task 8).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "feat: AOSE detailed bands + total carried weight; drop old table/scaling"
```

---

## Task 8: Basic-mode movement table

**Files:**
- Modify: `aose/engine/encumbrance.py` (`_basic_movement`)
- Test: `tests/test_encumbrance.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_encumbrance.py  (append)
def test_basic_unarmoured(data):
    s = _spec(encumbrance="basic")
    assert effective_movement(s, data) == 120
    s.carrying_treasure = True
    assert effective_movement(s, data) == 90


def test_basic_light_armour(data):
    s = _spec(inventory=["leather_armor"], equipped={"armor": "leather_armor"},
              encumbrance="basic")
    assert effective_movement(s, data) == 90
    s.carrying_treasure = True
    assert effective_movement(s, data) == 60


def test_basic_heavy_armour(data):
    s = _spec(inventory=["chain_mail"], equipped={"armor": "chain_mail"},
              encumbrance="basic")
    assert effective_movement(s, data) == 60
    s.carrying_treasure = True
    assert effective_movement(s, data) == 30


def test_basic_over_max_load_is_immobile(data):
    s = _spec(encumbrance="basic")
    s.gold = 1601            # treasure alone exceeds the 1,600 cap
    assert effective_movement(s, data) == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k basic_ -q`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: Implement**

Replace the `_basic_movement` placeholder with:

```python
_BASIC_TABLE = {
    ("none", False): 120, ("none", True): 90,
    ("leather", False): 90, ("leather", True): 60,
    ("metal", False): 60, ("metal", True): 30,
}


def _basic_movement(spec: CharacterSpec, data: GameData) -> int:
    """Basic encumbrance: armour worn × carrying-treasure toggle. Equipment
    weight is untracked; only the 1,600 treasure cap can immobilise."""
    if treasure_weight_cn(spec, data) > MAX_LOAD:
        return 0
    armor_cls = armor_movement_class(spec, data)
    return _BASIC_TABLE[(armor_cls, spec.carrying_treasure)]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k basic_ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "feat: AOSE basic-mode movement (armour x carrying-treasure)"
```

---

## Task 9: Rework EncumbranceTable for the sheet

**Files:**
- Modify: `aose/engine/encumbrance.py` (`ThresholdRow`, `EncumbranceTable`,
  `encumbrance_table`)
- Test: `tests/test_encumbrance.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_encumbrance.py  (append)
from aose.engine.encumbrance import encumbrance_table


def test_encumbrance_table_none_mode(data):
    assert encumbrance_table(_spec(encumbrance="none"), data) is None


def test_basic_table_shape_and_current(data):
    s = _spec(inventory=["leather_armor"], equipped={"armor": "leather_armor"},
              encumbrance="basic")
    s.carrying_treasure = True
    t = encumbrance_table(s, data)
    assert t.mode == "basic"
    assert t.columns == ["Without Treasure", "Carrying Treasure"]
    assert [r.label for r in t.rows] == ["Unarmoured", "Light armour", "Heavy armour"]
    assert t.current_col == 1
    light = next(r for r in t.rows if r.label == "Light armour")
    assert light.movements == [90, 60]
    assert light.is_current_row is True


def test_detailed_table_shape_and_current(data):
    s = _spec(encumbrance="detailed")
    s.gold = 500                                   # band 1 (401–600)
    t = encumbrance_table(s, data)
    assert t.mode == "detailed"
    assert t.columns == ["Movement"]
    assert len(t.rows) == 4                        # the four mobile bands
    assert [r.movements[0] for r in t.rows] == [120, 90, 60, 30]
    current = [r for r in t.rows if r.is_current_row]
    assert len(current) == 1 and current[0].movements[0] == 90
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k "table" -q`
Expected: FAIL — old `EncumbranceTable` shape / fields.

- [ ] **Step 3: Implement**

Replace the `ThresholdRow` / `EncumbranceTable` / `encumbrance_table`
definitions at the bottom of `aose/engine/encumbrance.py`:

```python
class ThresholdRow(BaseModel):
    label: str                # armour name (basic) or band label (detailed)
    movements: list[int]      # basic: [no_treasure, carrying]; detailed: [rate]
    is_current_row: bool


class EncumbranceTable(BaseModel):
    mode: Literal["basic", "detailed"]
    columns: list[str]        # header labels for `movements`
    rows: list[ThresholdRow]
    current_col: int | None   # basic: active treasure column; detailed: None


_BASIC_ROWS = [("Unarmoured", "none"), ("Light armour", "leather"),
               ("Heavy armour", "metal")]


def encumbrance_table(spec: CharacterSpec, data: GameData) -> EncumbranceTable | None:
    """Movement table for the sheet, or None when encumbrance is off.
    Basic = 3 armour rows × 2 treasure columns; detailed = the four mobile
    weight bands (the >1,600 immobile band is omitted from the display)."""
    mode = spec.ruleset.encumbrance
    if mode == "none":
        return None

    if mode == "basic":
        current_cls = armor_movement_class(spec, data)
        rows = [
            ThresholdRow(
                label=name,
                movements=[_BASIC_TABLE[(cls, False)], _BASIC_TABLE[(cls, True)]],
                is_current_row=(cls == current_cls),
            )
            for name, cls in _BASIC_ROWS
        ]
        return EncumbranceTable(
            mode="basic",
            columns=["Without Treasure", "Carrying Treasure"],
            rows=rows,
            current_col=(1 if spec.carrying_treasure else 0),
        )

    current_band = weight_band(banding_weight_cn(spec, data))
    rows = [
        ThresholdRow(label=band_label(b), movements=[_DETAILED_MOVE[b]],
                     is_current_row=(b == current_band))
        for b in range(4)              # mobile bands only
    ]
    return EncumbranceTable(mode="detailed", columns=["Movement"],
                            rows=rows, current_col=None)
```

> If `current_band == 4` (immobile) no row is flagged current — the sheet
> shows the immobile state via the 0' movement figure + cap warning (Task 11).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k "table" -q`
Expected: PASS

- [ ] **Step 5: Rewrite the stale parts of the test file & run the whole module**

Remove/replace the old-model tests in `tests/test_encumbrance.py` that
assumed `(armour × band)` movement, the `401–800/801–1200/1201–1600` bands,
or per-item `carried_weight_cn` summing of gear (gear now folds into the flat
80). Keep `armor_movement_class`, `none`-mode, and unknown-item tests.

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add aose/engine/encumbrance.py tests/test_encumbrance.py
git commit -m "feat: reworked EncumbranceTable (basic 3x2 / detailed bands)"
```

---

## Task 10: Sheet view wiring

**Files:**
- Modify: `aose/sheet/view.py` (`CharacterSheet` fields + `build_sheet`,
  `ENCUMBRANCE_DESCRIPTIONS`)
- Test: `tests/test_encumbrance.py` or `tests/test_sheet*.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_encumbrance.py  (append)
from aose.sheet.view import build_sheet


def test_sheet_exposes_purse_and_treasure(data):
    s = _spec(encumbrance="basic")
    s.gold = 5
    s.silver = 30
    s.gems = [GemStack(instance_id="g", value=100, count=2)]
    sheet = build_sheet(s, data)
    assert sheet.coins == {"pp": 0, "gp": 5, "ep": 0, "sp": 30, "cp": 0}
    assert sheet.treasure_value_gp == 8          # 5gp + 30sp(=3gp) + ... gems excluded
    assert sheet.treasure_weight_cn == 5 + 30 + 2
    assert sheet.carrying_treasure is False
    assert sheet.max_load == 1600
```

> `treasure_value_gp` reflects **coins only** (`currency.total_value_gp`). Gem
> & jewellery value stays in the existing `valuables.total_value`. Adjust the
> assertion if you decide to fold valuables into a single figure — keep them
> separate per the spec.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k sheet_exposes -q`
Expected: FAIL — `CharacterSheet` has no `coins` / `treasure_value_gp` / etc.

- [ ] **Step 3: Implement**

In `aose/sheet/view.py`:

1. Import: `from aose.engine import currency` and
   `from aose.engine.encumbrance import treasure_weight_cn`.
2. Add fields to `CharacterSheet`:

```python
    coins: dict[str, int] = Field(default_factory=dict)   # {"pp":..,"gp":..,...}
    treasure_value_gp: int = 0                             # coin value in gp
    treasure_weight_cn: int = 0
    carrying_treasure: bool = False
    max_load: int = 1600
```

3. In `build_sheet`, populate them:

```python
        coins={
            "pp": spec.platinum, "gp": spec.gold, "ep": spec.electrum,
            "sp": spec.silver, "cp": spec.copper,
        },
        treasure_value_gp=currency.total_value_gp(spec),
        treasure_weight_cn=treasure_weight_cn(spec, data),
        carrying_treasure=spec.carrying_treasure,
        max_load=__import__("aose.engine.encumbrance", fromlist=["MAX_LOAD"]).MAX_LOAD,
```

   (Prefer a clean top-level `from aose.engine.encumbrance import MAX_LOAD`
   import instead of the `__import__` form above.)

4. Update `ENCUMBRANCE_DESCRIPTIONS`:

```python
ENCUMBRANCE_DESCRIPTIONS = {
    "none": "Encumbrance is ignored entirely.",
    "basic": ("Movement is set by armour worn and whether you carry significant "
              "treasure. Only treasure weight is tracked, against the 1,600 cn cap."),
    "detailed": ("Movement is set by total weight: armour and weapons by listed "
                 "weight, miscellaneous gear as a flat 80 cn, plus all treasure."),
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_encumbrance.py -k sheet_exposes -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_encumbrance.py
git commit -m "feat: sheet exposes coin purse, treasure value/weight, carrying-treasure"
```

---

## Task 11: Carrying-treasure toggle route

**Files:**
- Modify: `aose/web/routes.py`
- Test: `tests/test_currency.py` or `tests/test_encumbrance.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_currency.py  (append; reuse the _client fixture from Task 3)
def test_carrying_treasure_toggle(tmp_path):
    client, app = _client(tmp_path)
    cid = "c1"
    save_character(cid, _spec(), app.state.characters_dir)
    client.post(f"/character/{cid}/carrying-treasure", data={"value": "true"})
    from aose.characters import load_character
    assert load_character(cid, app.state.characters_dir).carrying_treasure is True
    client.post(f"/character/{cid}/carrying-treasure", data={"value": "false"})
    assert load_character(cid, app.state.characters_dir).carrying_treasure is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -k carrying_treasure -q`
Expected: FAIL — 404.

- [ ] **Step 3: Add the route**

In `aose/web/routes.py`, after the coins routes:

```python
@router.post("/character/{character_id}/carrying-treasure")
async def set_carrying_treasure(request: Request, character_id: str,
                                value: str = Form(...)):
    """Flip the basic-encumbrance carrying-treasure toggle."""
    spec = _load_spec_or_404(request, character_id)
    spec.carrying_treasure = value.lower() in ("true", "1", "on", "yes")
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -k carrying_treasure -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_currency.py
git commit -m "feat: /carrying-treasure toggle route"
```

---

## Task 12: Sheet templates (purse, tables, toggle, valuables weight)

**Files:**
- Modify: the sheet template(s) under `aose/web/templates/sheet/` that render
  the movement/encumbrance block, the gold control, and the valuables section
- Test: manual + an HTML smoke assertion

First locate the relevant partials:

```bash
grep -rln "gold\|movement\|encumbrance\|valuables\|Gems" aose/web/templates/sheet
```

- [ ] **Step 1: Write a failing render smoke test**

```python
# tests/test_currency.py  (append)
def test_sheet_page_renders_purse_and_convert(tmp_path):
    client, app = _client(tmp_path)
    cid = "c1"
    save_character(cid, _spec(gold=5), app.state.characters_dir)
    html = client.get(f"/character/{cid}").text
    assert "coins/add" in html          # add control present
    assert "coins/convert" in html      # convert control present
    assert "carrying-treasure" in html or "Carrying Treasure" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -k page_renders -q`
Expected: FAIL — markers absent.

- [ ] **Step 3: Implement the template changes**

Replace the single gold control with a **coin purse** block. Add controls
(forms POST to the Task 3/11 routes; mirror the existing gold form's CSRF-free
style and the `valuables` section's add/sell button idiom):

- A row per denomination showing the count, with an add/subtract form
  (`POST .../coins/add` with hidden `denom` + an `amount` input).
- A convert form: `from_denom` select, `to_denom` select, `count` input,
  `POST .../coins/convert`.
- Show `treasure_value_gp` (coins) and the existing `valuables.total_value`
  (gems/jewellery) as separate figures.

In the movement/encumbrance block, iterate the new `encumbrance_table`:

```jinja
{% set t = sheet.encumbrance_table %}
{% if t %}
<table class="enc-table enc-{{ t.mode }}">
  <thead><tr><th></th>{% for c in t.columns %}<th>{{ c }}</th>{% endfor %}</tr></thead>
  <tbody>
  {% for row in t.rows %}
    <tr{% if row.is_current_row %} class="current-row"{% endif %}>
      <th>{{ row.label }}</th>
      {% for mv in row.movements %}
        <td{% if row.is_current_row and (t.mode == 'detailed' or loop.index0 == t.current_col) %} class="current-cell"{% endif %}>{{ mv }}'</td>
      {% endfor %}
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
```

Add the treasure-weight-vs-cap line in both modes:

```jinja
<p class="enc-load">Treasure: {{ sheet.treasure_weight_cn }} / {{ sheet.max_load }} cn
  {% if sheet.treasure_weight_cn > sheet.max_load %}<strong>(over max load — cannot move)</strong>{% endif %}
</p>
```

Add the basic-mode carrying-treasure toggle (only when `sheet.encumbrance_mode == 'basic'`):

```jinja
<form method="post" action="/character/{{ character_id }}/carrying-treasure">
  <input type="hidden" name="value" value="{{ 'false' if sheet.carrying_treasure else 'true' }}">
  <button type="submit">{{ 'Carrying treasure ✓' if sheet.carrying_treasure else 'Not carrying treasure' }}</button>
</form>
```

In the valuables section, surface gem/jewellery weight (1 cn/gem, 10 cn/piece)
near the total-value display.

> Match the template's existing `character_id` variable name — grep an
> existing sheet form to confirm how the id is referenced in this project's
> templates.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_currency.py -k page_renders -q`
Expected: PASS

- [ ] **Step 5: Manual smoke check**

Run the app, open a character, confirm: purse shows all five denominations;
add + convert work; basic mode shows the 3×2 table with the active cell
highlighted and the carrying-treasure toggle; detailed mode shows the four
bands with the active band highlighted; treasure/cap line renders.

```powershell
.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload
```

- [ ] **Step 6: Commit**

```bash
git add aose/web/templates/sheet tests/test_currency.py
git commit -m "feat: sheet UI for coin purse, convert, encumbrance tables, toggle"
```

---

## Task 13: Full regression & cleanup

**Files:**
- Any test files referencing the old encumbrance shape or `gold`-only purse

- [ ] **Step 1: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the trailing pytest-current PermissionError Windows quirk).

- [ ] **Step 2: Fix any fallout**

Likely spots: tests asserting old band thresholds (`401–800` etc.), the old
`(armour × band)` `EncumbranceTable` fields (`armor_classes`,
`movement_per_armor`), or `carried_weight_cn` summing gear per-item. Update
them to the new model. Any wizard/sheet template test asserting the old gold
control may need the purse markers.

- [ ] **Step 3: Confirm the CLAUDE.md "no pending rule" invariant still holds**

The encumbrance change doesn't add a `RuleSet` flag, so the settings-page
regression test should be unaffected — but run it explicitly:

Run: `.venv\Scripts\python.exe -m pytest tests/ -k "settings or pending or rule" -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: align suite with AOSE encumbrance/treasure/currency model"
```

---

## Self-Review notes

- **Spec coverage:** Part A → Tasks 1–3, 11 (carrying-treasure is Part C/D but
  the toggle field/route ride along); Part B → Tasks 4, 5; Part C → Tasks
  5–9; Part D → Tasks 10, 12. ✅
- **Currency value display:** coins use `total_value_gp`; gems/jewellery keep
  `valuables.total_value`. Kept separate per spec.
- **Deviation noted:** treasure-item weights are computed in
  `treasure_item_weight` (engine) rather than written into 66 commented YAML
  entries — same faithful result, avoids destroying catalog documentation.
  Flagged for the executor; revert to data-driven only if the user prefers.
- **Type consistency:** `EncumbranceTable` fields (`mode`, `columns`, `rows`,
  `current_col`) and `ThresholdRow` fields (`label`, `movements`,
  `is_current_row`) are used identically in Task 9 and the Task 12 template.
- **Removed symbols:** `_TABLE_HUMAN`, `_scale`, `_HUMAN_BASE`,
  `ArmorMovementClass` usages in the old table — grep after Task 7 to ensure
  no stale imports remain (`grep -rn "_TABLE_HUMAN\|_scale\|movement_per_armor\|armor_classes" aose tests`).
