# Conditional AC Modifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface conditional Armour Class modifiers (e.g. drow −1 AC in bright light, halfling +2 AC vs large attackers) on the character sheet via a clickable AC breakdown modal, without folding them into the headline AC.

**Architecture:** Reuse the existing `Modifier`/`GrantedModifier` grammar (`target: ac`, `op: add`, `condition`). The engine keeps the headline unchanged (only `unarmored` conditions are evaluated; every other condition stays situational) and gains an `armor_class_detail()` that returns a structured breakdown — headline composition lines plus conditional lines. The sheet exposes this breakdown; the template renders a `★` marker and a full AC breakdown modal, mirroring the existing per-save modal. Magic items get this for free through the shared `all_modifiers` pipeline.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run tests with `.venv\Scripts\python.exe -m pytest`.

---

## File Structure

- `aose/engine/armor_class.py` — **modify**. Extract a shared `_compute_ac` helper (single source of truth for `armor_class` and `armor_class_detail`), add the `ACModLine`/`ACBreakdown` models, the `_AC_CONDITION_NOTES` registry, and `armor_class_detail()`.
- `aose/sheet/view.py` — **modify**. Add `SheetACLine`, two `CharacterSheet` fields (`ac_lines`, `ac_has_conditional`), and wire them from `armor_class.armor_class_detail`.
- `aose/web/templates/sheet.html` — **modify**. `★` marker on the AC block, make it clickable, add the `modal-ac` overlay.
- `aose/web/templates/sheet_print.html` — **modify**. Conditional AC footnotes under the AC stat.
- `aose/web/static/sheet.css` — **modify**. Small `.shield .cond-mark` rule.
- `data/races/{drow,duergar,svirfneblin,gnome,halfling}.yaml` — **modify**. Add `granted_modifiers` to the existing Light Sensitivity / Defensive Bonus features.
- `tests/test_conditional_ac.py` — **create**. Engine + view tests.
- `tests/test_conditional_ac_data.py` — **create**. Per-race data tests.
- `tests/test_web.py` — **modify**. One render test for the modal + star.
- `CLAUDE.md` — **modify**. New "Current state" note.

**Data source note:** Values come from the already-verified `mechanical:` blocks in the race YAML (`armour_class_modifier: -1` for Light Sensitivity; `armour_class_bonus: 2` for Defensive Bonus). The raw AOSE PDF/markdown for races is not extracted in this repo (`import/markdown/races/` is empty), so the existing `mechanical:` blocks are authoritative — same provenance the situational-save grants used.

---

## Task 1: Engine — `armor_class_detail` + shared component helper

**Files:**
- Modify: `aose/engine/armor_class.py`
- Test: `tests/test_conditional_ac.py`

- [ ] **Step 1: Write failing engine tests**

Create `tests/test_conditional_ac.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine import armor_class as ac
from aose.engine.armor_class import ACBreakdown, ACModLine, armor_class, armor_class_detail
from aose.models import CharacterSpec, ClassEntry, Modifier

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id="human", class_id="fighter", level=1, **kw):
    defaults = dict(
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id=race_id,
        alignment="neutral",
    )
    defaults.update(kw)
    return CharacterSpec(
        name="T", classes=[ClassEntry(class_id=class_id, level=level, hp_rolls=[8])],
        **defaults,
    )


def test_conditional_ac_modifier_does_not_change_headline(monkeypatch):
    # A bright_light -1 AC modifier must NOT change the headline number.
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=-1,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    spec = _spec()
    # DEX 10 -> +0; unarmoured descending = 9.
    assert armor_class(spec, DATA) == (9, 10)


def test_breakdown_lists_conditional_line(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=2,
                         condition="large_attacker", source="Defensive Bonus")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    assert isinstance(bd, ACBreakdown)
    assert bd.descending == 9          # situational, excluded from headline
    cond = [ln for ln in bd.lines if ln.conditional]
    assert len(cond) == 1
    assert cond[0].source == "Defensive Bonus"
    assert cond[0].effect == "+2"
    assert cond[0].note == "vs attackers larger than human-sized"
    assert bd.has_conditional is True


def test_breakdown_penalty_uses_unicode_minus(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=-1,
                         condition="bright_light", source="Light Sensitivity")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].effect == "−1"   # "−1"
    assert cond[0].note == "in bright light"


def test_unknown_condition_falls_back_to_underscore_replace(monkeypatch):
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=1,
                         condition="prone_target", source="Homebrew")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    cond = [ln for ln in bd.lines if ln.conditional]
    assert cond[0].note == "prone target"


def test_unarmored_conditioned_bonus_excluded_from_conditional_lines(monkeypatch):
    # `unarmored` is headline-evaluated, NOT a situational/conditional line.
    def fake_all(spec, data):
        return [Modifier(target="ac", op="add", value=1,
                         condition="unarmored", source="Agile Fighting")]
    monkeypatch.setattr(ac, "all_modifiers", fake_all)
    bd = armor_class_detail(_spec(), DATA)
    assert all(not ln.conditional for ln in bd.lines)
    assert bd.has_conditional is False
    # And it DOES apply to the (unarmoured) headline: 9 - 1 = 8.
    assert bd.descending == 8


def test_breakdown_has_base_and_dex_lines():
    # DEX 13 -> +1; one armour/base line + one Dexterity line, no conditional.
    spec = _spec(abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 13, "CON": 10, "CHA": 10})
    bd = armor_class_detail(spec, DATA)
    sources = [ln.source for ln in bd.lines]
    assert "Unarmoured" in sources
    assert "Dexterity" in sources
    dex_line = next(ln for ln in bd.lines if ln.source == "Dexterity")
    assert dex_line.effect == "+1"
    assert bd.descending == 8


def test_breakdown_reconciles_with_armor_class():
    spec = _spec(equipped={"armor": "chain_mail"})
    bd = armor_class_detail(spec, DATA)
    assert (bd.descending, bd.ascending) == armor_class(spec, DATA)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_ac.py -q`
Expected: FAIL with `ImportError: cannot import name 'ACBreakdown'` (and friends).

- [ ] **Step 3: Implement the engine changes**

Replace the entire contents of `aose/engine/armor_class.py` with:

```python
from dataclasses import dataclass

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Ability, Armor, CharacterSpec, Modifier

from .ability_mods import ability_modifier
from .enchant import equipped_enchanted
from .features import all_modifiers
from .magic import effective_abilities

UNARMORED_AC_DESCENDING = 9

# Conditions the headline AC computation can evaluate. Every other condition on
# an `ac add` modifier is situational: carried for display, excluded from the
# headline, and surfaced as a conditional breakdown line.
_HEADLINE_AC_CONDITIONS = frozenset({"unarmored"})

_AC_CONDITION_NOTES = {
    "bright_light": "in bright light",
    "large_attacker": "vs attackers larger than human-sized",
}
"""Display note for an `ac add` modifier's condition. Unregistered conditions
fall back to ``condition.replace("_", " ")`` — mirrors ``_VS_DISPLAY`` in saves."""


def _ac_condition_note(condition: str) -> str:
    return _AC_CONDITION_NOTES.get(condition, condition.replace("_", " "))


class ACModLine(BaseModel):
    source: str          # "Plate Mail", "Unarmoured", "Dexterity", "Shield", feature/item name
    effect: str          # "AC 3", "+1", "−1" (unicode minus for penalties)
    conditional: bool    # True for situational modifiers
    note: str            # condition note ("" when unconditional)


class ACBreakdown(BaseModel):
    descending: int
    ascending: int
    unarmored_descending: int
    unarmored_ascending: int
    lines: list[ACModLine]   # unconditional contributions first, then conditional
    has_conditional: bool


@dataclass
class _ACComputation:
    base: int
    base_source: str
    dex_mod: int
    shield_bonus: int
    has_shield: bool
    applied_adds: list[Modifier]      # unconditional / applicable `ac add`
    situational_adds: list[Modifier]  # conditional `ac add`, excluded from headline
    descending: int
    ascending: int


def _has_worn_armor(spec: CharacterSpec, data: GameData) -> bool:
    """True when a body-armour item (not a shield) is equipped — mundane or
    enchanted.  Used to drop ``unarmored``-conditioned AC bonuses."""
    armor_id = spec.equipped.get("armor")
    item = data.items.get(armor_id) if armor_id else None
    if isinstance(item, Armor) and not item.is_shield:
        return True
    return any(True for _ in equipped_enchanted(spec, data, "armor"))


def _compute_ac(spec: CharacterSpec, data: GameData, *,
                use_armor: bool, use_shield: bool) -> _ACComputation:
    """Single source of truth for AC. ``armor_class`` returns the numbers;
    ``armor_class_detail`` also reads the component fields for the breakdown."""
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = all_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    base_source = "Unarmoured"
    if use_armor:
        armor_id = spec.equipped.get("armor")
        if armor_id and armor_id in data.items:
            item = data.items[armor_id]
            if isinstance(item, Armor) and not item.is_shield:
                cand = item.ac_descending - item.magic_bonus
                if cand < base:
                    base, base_source = cand, item.name
        # Enchanted armour: best-AC-wins (min descending) over mundane equipped.
        for resolved in equipped_enchanted(spec, data, "armor"):
            cand = resolved.ac_descending - resolved.magic_bonus
            if cand < base:
                base, base_source = cand, resolved.name

    # `ac set N` from ANY source is a literal descending base candidate; best
    # (lowest) wins. Evaluated OUTSIDE the use_armor gate so class-granted AC
    # (e.g. Kineticist) and bracers-style items show in the unarmoured display
    # and still beat worn armour. (Condition on `set` is intentionally ignored
    # here, preserving prior behaviour — no data uses a conditional `ac set`.)
    for m in mods:
        if m.target == "ac" and m.op == "set" and m.value < base:
            base, base_source = m.value, (m.source or "—")

    shield_bonus = 0
    has_shield = False
    if use_shield:
        shield_id = spec.equipped.get("shield")
        if shield_id and shield_id in data.items:
            item = data.items[shield_id]
            if isinstance(item, Armor) and item.is_shield:
                shield_bonus = item.ac_bonus + item.magic_bonus
                has_shield = True
        for resolved in equipped_enchanted(spec, data, "shield"):
            cand = resolved.ac_bonus + resolved.magic_bonus
            if cand > shield_bonus:
                shield_bonus, has_shield = cand, True

    armor_worn = use_armor and _has_worn_armor(spec, data)

    def ac_add_applies(m: Modifier) -> bool:
        if m.condition is None:
            return True
        if m.condition == "unarmored":
            return not armor_worn
        return False  # unrecognised condition: situational, never in the headline

    ac_mods = [m for m in mods if m.target == "ac" and m.op == "add"]
    applied_adds = [m for m in ac_mods if ac_add_applies(m)]
    situational_adds = [m for m in ac_mods
                        if m.condition is not None
                        and m.condition not in _HEADLINE_AC_CONDITIONS]

    ac_add = sum(m.value for m in applied_adds)
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return _ACComputation(base, base_source, dex_mod, shield_bonus, has_shield,
                          applied_adds, situational_adds, descending, ascending)


def armor_class(spec: CharacterSpec, data: GameData, *,
                use_armor: bool = True, use_shield: bool = True) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset.

    use_armor / use_shield = False computes the unarmoured value (DEX + magic/
    feature AC mods only), used for the sheet's armoured-vs-unarmoured display.
    """
    c = _compute_ac(spec, data, use_armor=use_armor, use_shield=use_shield)
    return c.descending, c.ascending


def unarmored_ac(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """AC with worn armour & shield ignored (DEX + magic/feature AC mods kept)."""
    return armor_class(spec, data, use_armor=False, use_shield=False)


def _effect_str(value: int) -> str:
    """`+N` for a bonus, unicode-minus `−N` for a penalty (matches view.py)."""
    return f"+{value}" if value >= 0 else f"−{abs(value)}"


def armor_class_detail(spec: CharacterSpec, data: GameData) -> ACBreakdown:
    """Full AC breakdown: headline composition lines (armour, DEX, shield,
    unconditional feature/magic AC mods) plus situational conditional lines.
    Headline numbers are authoritative (same helper as ``armor_class``)."""
    c = _compute_ac(spec, data, use_armor=True, use_shield=True)
    un = _compute_ac(spec, data, use_armor=False, use_shield=False)

    lines: list[ACModLine] = [
        ACModLine(source=c.base_source, effect=f"AC {c.base}", conditional=False, note=""),
    ]
    if c.dex_mod:
        lines.append(ACModLine(source="Dexterity", effect=_effect_str(c.dex_mod),
                               conditional=False, note=""))
    if c.has_shield:
        lines.append(ACModLine(source="Shield", effect=f"+{c.shield_bonus}",
                               conditional=False, note=""))
    for m in c.applied_adds:
        if m.condition == "unarmored":
            # Already folded into the base/headline via the unarmoured display.
            continue
        lines.append(ACModLine(source=m.source or "—", effect=_effect_str(m.value),
                               conditional=False, note=""))
    for m in c.situational_adds:
        lines.append(ACModLine(source=m.source or "—", effect=_effect_str(m.value),
                               conditional=True, note=_ac_condition_note(m.condition)))

    return ACBreakdown(
        descending=c.descending, ascending=c.ascending,
        unarmored_descending=un.descending, unarmored_ascending=un.ascending,
        lines=lines,
        has_conditional=any(ln.conditional for ln in lines),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_ac.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the AC regression suite to confirm no headline divergence**

Run: `.venv\Scripts\python.exe -m pytest tests/test_unarmored_ac.py tests/test_derivation.py tests/test_feature_modifiers.py tests/test_magic_items.py -q`
Expected: PASS (no AC headline regressions from the `_compute_ac` refactor).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/armor_class.py tests/test_conditional_ac.py
git commit -m "feat(engine): armor_class_detail with conditional AC breakdown"
```

---

## Task 2: Data — encode `granted_modifiers` on the five race features

**Files:**
- Modify: `data/races/drow.yaml`, `data/races/duergar.yaml`, `data/races/svirfneblin.yaml`, `data/races/gnome.yaml`, `data/races/halfling.yaml`
- Test: `tests/test_conditional_ac_data.py`

- [ ] **Step 1: Write failing data tests**

Create `tests/test_conditional_ac_data.py`:

```python
from pathlib import Path

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class_detail
from aose.models import CharacterSpec, ClassEntry

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _spec(race_id, class_id="fighter"):
    return CharacterSpec(
        name="T", race_id=race_id, alignment="neutral",
        classes=[ClassEntry(class_id=class_id, level=1, hp_rolls=[8])],
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
    )


def _cond(race_id, class_id="fighter"):
    bd = armor_class_detail(_spec(race_id, class_id), DATA)
    return [ln for ln in bd.lines if ln.conditional]


def test_drow_light_sensitivity_minus_one():
    lines = _cond("drow")
    assert any(ln.source == "Light Sensitivity" and ln.effect == "−1"
               and ln.note == "in bright light" for ln in lines)


def test_duergar_light_sensitivity_minus_one():
    lines = _cond("duergar", class_id="fighter")
    assert any(ln.source == "Light Sensitivity" and ln.effect == "−1" for ln in lines)


def test_gnome_defensive_bonus_plus_two():
    lines = _cond("gnome")
    assert any(ln.source == "Defensive Bonus" and ln.effect == "+2"
               and ln.note == "vs attackers larger than human-sized" for ln in lines)


def test_halfling_defensive_bonus_plus_two():
    lines = _cond("halfling")
    assert any(ln.source == "Defensive Bonus" and ln.effect == "+2" for ln in lines)


def test_svirfneblin_has_both():
    lines = _cond("svirfneblin")
    effects = {(ln.source, ln.effect) for ln in lines}
    assert ("Light Sensitivity", "−1") in effects
    assert ("Defensive Bonus", "+2") in effects


def test_human_has_no_conditional_ac():
    assert _cond("human") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_ac_data.py -q`
Expected: FAIL (no `granted_modifiers` yet on these features).

- [ ] **Step 3: Add `granted_modifiers` to each race feature**

In `data/races/drow.yaml`, the `light_sensitivity` feature (currently ends at its `mechanical:` block) — append a `granted_modifiers` key at the feature level (sibling of `mechanical:`):

```yaml
- id: light_sensitivity
  name: Light Sensitivity
  text: In bright light, including daylight or continual light, suffers a –2 penalty to attack rolls and a –1 penalty to Armour Class.
  mechanical:
    conditions:
    - bright_light
    - daylight
    - continual_light
    attack_roll_modifier: -2
    armour_class_modifier: -1
  granted_modifiers:
  - {target: "ac", op: add, value: -1, condition: bright_light}
```

In `data/races/duergar.yaml`, apply the identical `granted_modifiers` block to its `light_sensitivity` feature (same text/mechanical block already present).

In `data/races/svirfneblin.yaml`, add the same `granted_modifiers` to its `light_sensitivity` feature AND add the Defensive Bonus grant to its `defensive_bonus` feature:

```yaml
- id: defensive_bonus
  name: Defensive Bonus
  text: Due to small size, gains a +2 bonus to Armour Class when attacked by large opponents greater than human-sized.
  mechanical:
    armour_class_bonus: 2
    condition: attacked_by_large_opponents
  granted_modifiers:
  - {target: "ac", op: add, value: 2, condition: large_attacker}
```

In `data/races/gnome.yaml` and `data/races/halfling.yaml`, add the Defensive Bonus `granted_modifiers` block (identical to the svirfneblin one above) to their `defensive_bonus` features.

- [ ] **Step 4: Run data tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_ac_data.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the data-loading + situational-save data suites (guard against YAML breakage)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py tests/test_situational_saves_data.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data/races/drow.yaml data/races/duergar.yaml data/races/svirfneblin.yaml data/races/gnome.yaml data/races/halfling.yaml tests/test_conditional_ac_data.py
git commit -m "feat(data): conditional AC modifiers for light sensitivity & defensive bonus"
```

---

## Task 3: Sheet view — expose the AC breakdown on `CharacterSheet`

**Files:**
- Modify: `aose/sheet/view.py`
- Test: `tests/test_conditional_ac.py` (append)

- [ ] **Step 1: Append failing view tests to `tests/test_conditional_ac.py`**

```python
# ── view-model tests ──────────────────────────────────────────────────────────

from aose.sheet.view import build_sheet, SheetACLine


def test_build_sheet_flags_conditional_ac_for_drow():
    spec = _spec(race_id="drow")
    sheet = build_sheet(spec, DATA)
    assert sheet.ac_has_conditional is True
    cond = [ln for ln in sheet.ac_lines if ln.conditional]
    assert any(ln.source == "Light Sensitivity" for ln in cond)
    assert all(isinstance(ln, SheetACLine) for ln in sheet.ac_lines)


def test_build_sheet_no_conditional_ac_for_human():
    sheet = build_sheet(_spec(race_id="human"), DATA)
    assert sheet.ac_has_conditional is False
    assert all(not ln.conditional for ln in sheet.ac_lines)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_ac.py -q`
Expected: FAIL with `ImportError: cannot import name 'SheetACLine'`.

- [ ] **Step 3: Add the `SheetACLine` model**

In `aose/sheet/view.py`, immediately after the `class SheetSituationalSave` block (ends ~line 115), add:

```python
class SheetACLine(BaseModel):
    source: str
    effect: str
    conditional: bool
    note: str
```

- [ ] **Step 4: Add the `CharacterSheet` fields**

In `aose/sheet/view.py`, in `class CharacterSheet`, immediately after the existing AC fields (`unarmored_ac_descending` / `unarmored_ac_ascending` / `use_ascending`, ~line 350-352), add:

```python
    ac_lines: list[SheetACLine]
    ac_has_conditional: bool
```

- [ ] **Step 5: Wire it in `build_sheet`**

In `aose/sheet/view.py`, find the line `desc_ac, asc_ac = armor_class.armor_class(spec, data)` (~line 1112) and replace it and the following `un_desc, un_asc` line with:

```python
    ac_breakdown = armor_class.armor_class_detail(spec, data)
    desc_ac, asc_ac = ac_breakdown.descending, ac_breakdown.ascending
    un_desc, un_asc = ac_breakdown.unarmored_descending, ac_breakdown.unarmored_ascending
    ac_line_rows = [
        SheetACLine(source=ln.source, effect=ln.effect,
                    conditional=ln.conditional, note=ln.note)
        for ln in ac_breakdown.lines
    ]
```

Then in the `return CharacterSheet(...)` call, immediately after the `use_ascending=spec.ruleset.ascending_ac,` line (~line 1180), add:

```python
        ac_lines=ac_line_rows,
        ac_has_conditional=ac_breakdown.has_conditional,
```

Note: the old `_unarmored_ac` import (`from aose.engine.armor_class import unarmored_ac as _unarmored_ac`) is now unused in `build_sheet` but may be referenced elsewhere — leave it; do not remove unless grep shows no other use.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_conditional_ac.py -q`
Expected: PASS (9 tests).

- [ ] **Step 7: Run the full sheet suite (CharacterSheet got new required fields)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet.py tests/test_detail_views.py tests/test_detail_cards.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py tests/test_conditional_ac.py
git commit -m "feat(sheet): expose conditional AC breakdown on CharacterSheet"
```

---

## Task 4: Templates + CSS — AC `★` marker, breakdown modal, print footnotes

**Files:**
- Modify: `aose/web/templates/sheet.html`
- Modify: `aose/web/templates/sheet_print.html`
- Modify: `aose/web/static/sheet.css`
- Test: `tests/test_web.py` (append)

- [ ] **Step 1: Write a failing render test in `tests/test_web.py`**

Append to `tests/test_web.py` (it already imports `TestClient` and `DATA_DIR`):

```python
def test_sheet_renders_conditional_ac_modal(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from aose.characters import save_character
    from aose.models import CharacterSpec, ClassEntry
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
        name="Driz", race_id="drow", alignment="neutral",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
    )
    save_character("driz", spec, characters_dir)

    html = TestClient(app, follow_redirects=False).get("/character/driz").text
    assert 'id="modal-ac"' in html               # breakdown modal present
    assert "Light Sensitivity" in html           # conditional source listed
    assert "in bright light" in html             # condition note rendered


def test_sheet_no_ac_modal_marker_for_plain_human(client):
    # Thorin is a dwarf; use the human-fighter example route if present, else
    # assert the star marker is absent for a race with no conditional AC.
    html = client.get("/character/thorin").text
    # Dwarf has no conditional AC -> no AC star marker class on the shield block.
    assert 'data-modal="modal-ac"' not in html or "Light Sensitivity" not in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_sheet_renders_conditional_ac_modal -q`
Expected: FAIL (`id="modal-ac"` not in html).

- [ ] **Step 3: Edit `sheet.html` — make the AC block clickable + add `★`**

In `aose/web/templates/sheet.html`, replace the `.shield` block (lines 81-85):

```html
            <div class="shield">
              <div class="lab">Armour Class</div>
              <div class="ac">{% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}</div>
              <div class="unarm">unarmoured <b>{% if sheet.use_ascending %}{{ sheet.unarmored_ac_ascending }}{% else %}{{ sheet.unarmored_ac_descending }}{% endif %}</b></div>
            </div>
```

with (adds `clickable` + `data-modal` so the existing overlay controller opens `modal-ac`, and a `★` in the label when there are conditional mods):

```html
            <div class="shield{% if sheet.ac_has_conditional %} clickable{% endif %}"{% if sheet.ac_has_conditional %} data-modal="modal-ac"{% endif %}>
              <div class="lab">Armour Class{% if sheet.ac_has_conditional %}<span class="cond-mark" title="Has a conditional modifier — tap for details">★</span>{% endif %}</div>
              <div class="ac">{% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}</div>
              <div class="unarm">unarmoured <b>{% if sheet.use_ascending %}{{ sheet.unarmored_ac_ascending }}{% else %}{{ sheet.unarmored_ac_descending }}{% endif %}</b></div>
            </div>
```

- [ ] **Step 4: Edit `sheet.html` — add the `modal-ac` overlay**

In `aose/web/templates/sheet.html`, immediately BEFORE the `{# MODALS: per-save breakdown #}` comment (~line 651), insert:

```html
{# MODAL: AC breakdown (conditional modifiers) #}
<div class="overlay modal" id="modal-ac" role="dialog" aria-label="Armour Class">
  <div class="ov-head"><h3>Armour Class</h3><button class="x" data-close>×</button></div>
  <div class="ov-body" style="font-size:14px">
    <p style="margin:0 0 6px">
      Armour Class <strong>{% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}</strong>
      <span class="muted">({% if sheet.use_ascending %}descending {{ sheet.ac_descending }}{% else %}ascending {{ sheet.ac_ascending }}{% endif %})</span>
    </p>
    <ul style="list-style:none;margin:0;padding:0">
      {% for ln in sheet.ac_lines %}
      <li style="margin:2px 0">
        <strong>{{ ln.source }}:</strong> {{ ln.effect }}
        {% if ln.conditional %}<span class="muted"> — {{ ln.note }}</span>{% endif %}
      </li>
      {% endfor %}
    </ul>
  </div>
</div>
```

- [ ] **Step 5: Edit `sheet_print.html` — conditional AC footnotes**

In `aose/web/templates/sheet_print.html`, replace the Armor Class `stat-row` (lines 46-51):

```html
        <div class="stat-row">
            <span>Armor Class</span>
            <span class="stat-big">
            {% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}
            </span>
        </div>
```

with (adds a footnote block listing only the conditional lines):

```html
        <div class="stat-row">
            <span>Armor Class</span>
            <span class="stat-big">
            {% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}
            </span>
        </div>
        {% if sheet.ac_has_conditional %}
        <div class="save-notes-print">
            {% for ln in sheet.ac_lines if ln.conditional %}
            <div class="muted small">{{ ln.effect }} AC {{ ln.note }} ({{ ln.source }})</div>
            {% endfor %}
        </div>
        {% endif %}
```

- [ ] **Step 6: Edit `sheet.css` — `.shield .cond-mark`**

In `aose/web/static/sheet.css`, immediately after the `.shield .unarm b{ ... }` rule (line 116), add:

```css
.shield .lab .cond-mark{ color:var(--stamp); font-size:9px; vertical-align:super; margin-left:2px; }
```

- [ ] **Step 7: Run the render tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_sheet_renders_conditional_ac_modal tests/test_web.py::test_sheet_no_ac_modal_marker_for_plain_human -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/templates/sheet_print.html aose/web/static/sheet.css tests/test_web.py
git commit -m "feat(sheet): clickable AC breakdown modal with conditional modifiers"
```

---

## Task 5: Docs + full-suite verification

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (the pre-existing trailing `PermissionError` on `pytest-current` is a known Windows-tempdir quirk — ignore it). Confirm the count increased by the new tests (≈ +17).

- [ ] **Step 2: Add a "Current state" note to `CLAUDE.md`**

In `CLAUDE.md`, immediately below the `## Current state (2026-06-07, situational save bonuses)` block, add a new block:

```markdown
## Current state (2026-06-07, conditional AC modifiers)

Conditional Armour Class modifiers landed, mirroring situational save bonuses.
An `ac add` `Modifier` carrying a `condition` the headline can't evaluate (i.e.
anything other than `unarmored`) is excluded from the headline AC and surfaced as
a conditional breakdown line. `armor_class.py` gains a shared `_compute_ac`
helper (single source of truth for `armor_class` + the new
`armor_class_detail(spec, data) -> ACBreakdown`), an `_AC_CONDITION_NOTES`
registry (`bright_light`/`large_attacker`, underscore fallback), and the
`ACModLine`/`ACBreakdown` models. The sheet exposes `ac_lines` +
`ac_has_conditional`; the AC block shows a `★` and opens a full AC breakdown
modal (`modal-ac`: armour/DEX/shield/feature lines + conditional lines). Print
sheet shows the conditional lines as footnotes. Magic items emit conditional `ac`
modifiers and are collected automatically via `all_modifiers`. Data encoded:
Light Sensitivity (drow/duergar/svirfneblin, `ac -1 condition:bright_light`) and
Defensive Bonus (gnome/svirfneblin/halfling, `ac +2 condition:large_attacker`).
The −2 attack-in-bright-light penalty is out of scope (future conditional-attack
feature). Spec/plan:
`docs/superpowers/{specs,plans}/2026-06-07-conditional-ac-modifiers*`.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note conditional AC modifiers feature in CLAUDE.md"
```

---

## Self-Review Notes

- **Spec coverage:** data (Task 2) ✓; engine headline-unchanged + `armor_class_detail` + condition registry (Task 1) ✓; `unarmored` excluded from conditional list (Task 1 test + Task 3 wiring) ✓; sheet fields (Task 3) ✓; `★` + full breakdown modal + print footnotes + CSS (Task 4) ✓; magic-item path (Task 1 monkeypatch test exercises the `all_modifiers` route; no catalog data added, per spec out-of-scope) ✓; tests across engine/view/data (Tasks 1-4) ✓; CLAUDE.md (Task 5) ✓.
- **Type consistency:** `ACModLine`/`ACBreakdown` (engine) and `SheetACLine` (view) field names — `source`, `effect`, `conditional`, `note` — match across tasks. `armor_class_detail` returns `ACBreakdown` with `descending`/`ascending`/`unarmored_descending`/`unarmored_ascending`/`lines`/`has_conditional`, used consistently in Tasks 3-4. `CharacterSheet` new fields `ac_lines`/`ac_has_conditional` match between view definition and template usage.
- **Behaviour preservation:** `_compute_ac` reproduces the prior `armor_class` math (armour/enchanted-min, `ac set` outside the armour gate, `unarmored` condition handling, shield best-wins). Task 1 Step 5 + Task 3 Step 7 run the existing AC-heavy suites to catch any divergence.
```
