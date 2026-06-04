# Character Sheet Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the approved OSR-zine sheet (`docs/redesign/character-sheet-prototype-3.html`) into the live app, replacing the current `sheet.html` / `sheet.css` and refactoring the shared `_equipment_ui.html` into a tabbed drawer, preserving every route and the wizard's use of the partial.

**Architecture:** Mostly template + CSS work driven by the existing `CharacterSheet` view model. Three small TDD'd engine/view additions (unarmoured AC, overland movement, a spellbook-by-level view helper). New on-screen interactions are a single vanilla-JS overlay controller (`sheet_overlays.js`). The shared inventory partial gains tabs whose advanced sections are gated on context presence (so the wizard, which passes none of that context, shows only Carried + Shop). The separate print route (`sheet_print.html`) is untouched.

**Tech stack:** FastAPI + Jinja2, Pydantic v2 view models, vanilla JS, plain CSS. Fonts Oswald + Bitter (self-hosted woff2). Tests: pytest. Spec: `docs/superpowers/specs/2026-06-04-character-sheet-redesign-design.md`.

**Canonical markup/CSS source:** `docs/redesign/character-sheet-prototype-3.html`. Template tasks port regions from it verbatim and replace its hard-coded sample data with the Jinja bindings given in each task. When a task says "port the X region," copy that region's HTML/CSS from prototype-3 and apply the listed substitutions.

---

## Running & verifying

- Tests: `.venv\Scripts\python.exe -m pytest tests/ -q` (ignore the trailing pytest-9 tempdir PermissionError).
- App (for live preview): add a launch config (Task 0) and use the preview tools, OR run
  `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload` and open `/character/thorin` (non-caster) and a caster example.
- After each template task: (a) `GET /character/<id>` returns 200, (b) eyeball in preview, (c) run the focused web tests.

## File structure

- **Modify** `aose/engine/armor_class.py` — add `use_armor`/`use_shield` kwargs + `unarmored_ac`.
- **Modify** `aose/sheet/view.py` — add `unarmored_ac_descending/ascending`, `movement_overland` to `CharacterSheet`; add `spellbook_view` + row/group models.
- **Replace** `aose/web/static/sheet.css` — zine design system (from prototype-3 `<style>`).
- **Create** `aose/web/static/sheet_overlays.js` — overlay controller (from prototype-3 `<script>`).
- **Create** `aose/web/static/fonts/` — self-hosted Oswald + Bitter woff2 + `@font-face` in CSS.
- **Replace** `aose/web/templates/sheet.html` — grouped zine layout + overlay containers.
- **Refactor** `aose/web/templates/_equipment_ui.html` — tabbed drawer body, gated tabs.
- **Modify** `aose/web/routes.py` — pass `valuables_view`, `spell_sources_view`, existing `spell_source_add_options` into the equipment partial context; pass `spellbook_view` to the sheet.
- **Modify** `tests/test_web.py` — update text assertions; add caster/non-caster spell-group tests.
- **No change** `aose/web/templates/sheet_print.html`, `aose/web/wizard.py` routes (verify only).

---

## Phase A — Engine & view additions (TDD)

### Task A1: Unarmoured AC

**Files:**
- Modify: `aose/engine/armor_class.py`
- Test: `tests/test_equip_attacks.py` (append) or new `tests/test_unarmored_ac.py`

- [ ] **Step 1: Write the failing test** (`tests/test_unarmored_ac.py`)

```python
from pathlib import Path
from aose.data.loader import GameData
from aose.engine.armor_class import armor_class, unarmored_ac
from aose.models import CharacterSpec, ClassEntry

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _spec(**kw):
    base = dict(
        name="T", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 13, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_unarmored_ac_is_base_minus_dex():
    # DEX 13 → +1; unarmoured descending = 9 - 1 = 8, ascending = 11.
    spec = _spec()
    assert unarmored_ac(spec, DATA) == (8, 11)


def test_unarmored_ignores_worn_armour_but_armored_does_not():
    spec = _spec(equipped={"armor": "chain_mail"})
    desc_armored, _ = armor_class(spec, DATA)
    desc_unarmored, _ = unarmored_ac(spec, DATA)
    assert desc_unarmored == 8           # armour ignored
    assert desc_armored < desc_unarmored  # chainmail improves (lowers) descending AC
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_unarmored_ac.py -q`
Expected: FAIL (`cannot import name 'unarmored_ac'`).

- [ ] **Step 3: Implement** — in `armor_class.py`, add keyword flags and the helper.

```python
def armor_class(spec: CharacterSpec, data: GameData, *,
                use_armor: bool = True, use_shield: bool = True) -> tuple[int, int]:
    """Return (descending_ac, ascending_ac). Sheet renders one based on ruleset.

    use_armor / use_shield = False computes the unarmoured value (DEX + magic AC mods
    only), used for the sheet's armoured-vs-unarmoured display.
    """
    eff = effective_abilities(spec, data)
    dex_mod = ability_modifier(eff[Ability.DEX])
    mods = active_modifiers(spec, data)

    base = UNARMORED_AC_DESCENDING
    if use_armor:
        armor_id = spec.equipped.get("armor")
        if armor_id and armor_id in data.items:
            item = data.items[armor_id]
            if isinstance(item, Armor) and not item.is_shield:
                base = item.ac_descending - item.magic_bonus
        for resolved in equipped_enchanted(spec, data, "armor"):
            base = min(base, resolved.ac_descending - resolved.magic_bonus)
        for m in mods:
            if m.target == "ac" and m.op == "set":
                base = min(base, m.value)

    shield_bonus = 0
    if use_shield:
        shield_id = spec.equipped.get("shield")
        if shield_id and shield_id in data.items:
            item = data.items[shield_id]
            if isinstance(item, Armor) and item.is_shield:
                shield_bonus = item.ac_bonus + item.magic_bonus
        for resolved in equipped_enchanted(spec, data, "shield"):
            shield_bonus = max(shield_bonus, resolved.ac_bonus + resolved.magic_bonus)

    ac_add = sum(m.value for m in mods if m.target == "ac" and m.op == "add")
    descending = base - dex_mod - shield_bonus - ac_add
    ascending = 19 - descending
    return descending, ascending


def unarmored_ac(spec: CharacterSpec, data: GameData) -> tuple[int, int]:
    """AC with worn armour & shield ignored (DEX + magic AC mods kept)."""
    return armor_class(spec, data, use_armor=False, use_shield=False)
```

(Note: the `set`/`add` AC mods stay inside `use_armor`/global as written above — a `set`
candidate like Bracers is an armour-substitute so it belongs under `use_armor`; `ac add`
like Ring of Protection always applies. This matches the spec's "unarmoured keeps magic AC
mods".)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_unarmored_ac.py -q`
Expected: PASS.

- [ ] **Step 5: Regression** — `.venv\Scripts\python.exe -m pytest tests/test_equip_attacks.py tests/test_magic_items.py -q` (existing `armor_class` callers unaffected). Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/engine/armor_class.py tests/test_unarmored_ac.py
git commit -m "feat(engine): unarmored_ac helper for sheet armoured/unarmoured display"
```

---

### Task A2: Sheet fields — unarmoured AC + overland movement

**Files:**
- Modify: `aose/sheet/view.py` (`CharacterSheet` model + `build_sheet`)
- Test: `tests/test_sheet.py` (append)

- [ ] **Step 1: Write the failing test** (`tests/test_sheet.py`)

```python
def test_sheet_exposes_unarmored_and_overland(example_thorin_sheet):
    sheet = example_thorin_sheet  # adapt to the fixture/builder used in this file
    assert sheet.unarmored_ac_descending >= sheet.ac_descending  # armour only helps
    assert sheet.movement_overland == sheet.movement_base // 5
```

(If `tests/test_sheet.py` has no such fixture, build the sheet inline as other tests in
that file do: `build_sheet(load_character("thorin", EXAMPLES_DIR), DATA)`.)

- [ ] **Step 2: Run to verify it fails** — `pytest tests/test_sheet.py -q` → FAIL (attr missing).

- [ ] **Step 3: Implement** — add fields to `CharacterSheet` (near the AC fields):

```python
    unarmored_ac_descending: int
    unarmored_ac_ascending: int
    movement_overland: int           # miles/day = exploration // 5
```

In `build_sheet`, import `unarmored_ac` and populate:

```python
    from aose.engine.armor_class import armor_class as _ac, unarmored_ac as _unarmored
    desc_ac, asc_ac = _ac(spec, data)
    un_desc, un_asc = _unarmored(spec, data)
    ...
        unarmored_ac_descending=un_desc,
        unarmored_ac_ascending=un_asc,
        movement_overland=effective_movement(spec, data) // 5,
```

(Replace the existing `armor_class.armor_class(spec, data)` call with the aliased import, or keep the existing call and add the unarmoured call — either is fine; keep it DRY.)

- [ ] **Step 4: Run to verify it passes** — `pytest tests/test_sheet.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet.py
git commit -m "feat(sheet): expose unarmored AC + overland movement"
```

---

### Task A3: `spellbook_view` — spellbook by level with cast pips

**Files:**
- Modify: `aose/sheet/view.py` (add models + function)
- Test: `tests/test_spells.py` or new `tests/test_spellbook_view.py`

**Shape:** one block per casting class; arcane lists the **book** spells (from
`known_spells`) grouped by level, divine lists the full accessible list grouped by level;
each row carries `ready`/`spent` cast counts derived from `ClassEntry.slots` grouped by
`spell_id`.

- [ ] **Step 1: Write the failing test** — construct a magic-user with 2 memorised Magic
Missile (one spent) and assert the row.

```python
from pathlib import Path
from aose.data.loader import GameData
from aose.sheet.view import spellbook_view
from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _mu():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=["magic_missile", "sleep", "shield"])
    spec = CharacterSpec(
        name="M", abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    cls = DATA.classes["magic_user"]
    e2 = se.prepare(e, cls, DATA, "magic_missile", level=1)
    e2 = se.prepare(e2, cls, DATA, "magic_missile", level=1)   # memorise twice
    e2 = se.cast_slot(e2, 0)                                   # spend one copy
    spec.classes = [e2]
    return spec


def test_spellbook_view_groups_by_level_with_cast_counts():
    spec = _mu()
    blocks = spellbook_view(spec, DATA)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.caster_type == "arcane"
    lvl1 = next(g for g in block.levels if g.level == 1)
    mm = next(r for r in lvl1.rows if r.spell_id == "magic_missile")
    assert (mm.ready, mm.spent) == (1, 1)      # 2 memorised, 1 cast
    assert mm.known is True
    sh = next(r for r in lvl1.rows if r.spell_id == "shield")
    assert (sh.ready, sh.spent) == (0, 0) and sh.known is True   # known, not memorised
```

(Verify the real `spells` engine API names while implementing — `prepare`/`cast_slot`
exist per CLAUDE.md/`aose/engine/spells.py`; adjust call names if they differ. The
assertions on `ready`/`spent`/`known` are the contract.)

- [ ] **Step 2: Run to verify it fails** — `pytest tests/test_spellbook_view.py -q` → FAIL.

- [ ] **Step 3: Implement** — add to `aose/sheet/view.py`:

```python
class SpellbookRow(BaseModel):
    spell_id: str
    name: str
    level: int
    reversible: bool
    description: str
    known: bool          # in book (arcane) / on accessible list (divine)
    ready: int           # memorised copies with casts remaining
    spent: int           # memorised copies already cast


class SpellbookLevelGroup(BaseModel):
    level: int
    cap: int             # memorizable slots at this level
    used: int            # filled slots at this level
    rows: list[SpellbookRow]


class SpellbookBlock(BaseModel):
    class_id: str
    class_name: str
    caster_type: str         # arcane | divine
    levels: list[SpellbookLevelGroup]


def spellbook_view(spec: CharacterSpec, data: GameData) -> list[SpellbookBlock]:
    out: list[SpellbookBlock] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype is None:
            continue
        caps = spell_engine.memorizable_slots(entry, cls)         # {level: cap}
        known = spell_engine.known_spells(entry, cls, data)        # book (arcane) / list (divine)
        known_ids = {s.id for s in known}
        # tally memorised copies per (level, spell_id)
        ready: dict[tuple[int, str], int] = {}
        spent: dict[tuple[int, str], int] = {}
        used_by_level: dict[int, int] = {}
        for slot in entry.slots:
            if slot.spell_id is None:
                continue
            key = (slot.level, slot.spell_id)
            (spent if slot.spent else ready)[key] = (spent if slot.spent else ready).get(key, 0) + 1
            used_by_level[slot.level] = used_by_level.get(slot.level, 0) + 1
        levels: list[SpellbookLevelGroup] = []
        for level in sorted(caps):
            rows: list[SpellbookRow] = []
            # spells to list at this level: known spells of that level, plus any memorised
            # spell ids not in the known set (defensive)
            level_known = [s for s in known if s.level == level]
            extra_ids = {sid for (lv, sid) in {**ready, **spent} if lv == level} - {s.id for s in level_known}
            spells = level_known + [data.spells[i] for i in sorted(extra_ids) if i in data.spells]
            for s in spells:
                rows.append(SpellbookRow(
                    spell_id=s.id, name=s.name, level=s.level, reversible=s.reversible,
                    description=s.description, known=s.id in known_ids,
                    ready=ready.get((level, s.id), 0), spent=spent.get((level, s.id), 0),
                ))
            levels.append(SpellbookLevelGroup(
                level=level, cap=caps[level], used=used_by_level.get(level, 0), rows=rows,
            ))
        out.append(SpellbookBlock(
            class_id=entry.class_id, class_name=cls.name, caster_type=ctype, levels=levels,
        ))
    return out
```

- [ ] **Step 4: Run to verify it passes** — `pytest tests/test_spellbook_view.py -q` → PASS.

- [ ] **Step 5: Wire into build_sheet** — add `spellbook: list[SpellbookBlock] = Field(default_factory=list)` to `CharacterSheet`, and `spellbook=spellbook_view(spec, data),` in `build_sheet`. Keep the existing `spells` field (still used by the management drawer / divine list) — do not delete it yet.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_spellbook_view.py
git commit -m "feat(sheet): spellbook_view — book by level with cast-pip counts"
```

---

## Phase B — Static assets

### Task 0 (prereq): app preview launch config

**Files:** Modify `.claude/launch.json`

- [ ] Add an app config so the live sheet can be screenshotted:

```json
{ "name": "aose-app", "runtimeExecutable": ".venv/Scripts/python.exe",
  "runtimeArgs": ["-m", "uvicorn", "aose.web.app:app", "--port", "8138"], "port": 8138 }
```

- [ ] Verify: `preview_start("aose-app")`, open `/character/thorin`, screenshot shows the *current* sheet (baseline). Commit the launch config.

### Task B1: Self-host fonts + new `sheet.css`

**Files:**
- Create: `aose/web/static/fonts/oswald-*.woff2`, `bitter-*.woff2`
- Replace: `aose/web/static/sheet.css`

- [ ] **Step 1:** Download Oswald (500/600/700) + Bitter (400/600/700, italic 400) woff2 into `aose/web/static/fonts/`. (If offline, fall back to a system stack `'Arial Narrow'`/`Georgia` and leave a TODO — fonts are cosmetic, not blocking.)

- [ ] **Step 2:** Port the entire `<style>` block from `docs/redesign/character-sheet-prototype-3.html` into `aose/web/static/sheet.css`, replacing the prototype's Google-Fonts assumption with `@font-face` rules pointing at the self-hosted woff2. **Preserve** the existing non-sheet CSS that other pages rely on: keep the `.wizard*`, `.card*`, `.radio-*`, `.settings*`, `.review-*`, `.flash*`, `.button`, `.field` (wizard) rules from the *current* `sheet.css` — append them below the new zine system, or namespace the new system so it does not collide. (Index/settings/wizard templates still load `sheet.css` via `base.html`.)

- [ ] **Step 3 (verify):** No automated test. Defer visual verification to Phase C (the templates that use these classes don't exist yet). Run the full suite to confirm nothing imports/parses CSS (it doesn't): `pytest tests/ -q` → PASS.

- [ ] **Step 4: Commit** `git add aose/web/static/sheet.css aose/web/static/fonts/ && git commit -m "feat(sheet): zine design-system CSS + self-hosted fonts"`

### Task B2: Overlay controller JS

**Files:** Create `aose/web/static/sheet_overlays.js`

- [ ] **Step 1:** Copy the `<script>` IIFE from prototype-3 into `sheet_overlays.js` verbatim (it is self-contained; no edits needed).
- [ ] **Step 2 (verify):** loaded in Phase C via `<script src="/static/sheet_overlays.js" defer>` in `sheet.html`. No test now.
- [ ] **Step 3: Commit** `git add aose/web/static/sheet_overlays.js && git commit -m "feat(sheet): overlay controller (drawer/modal/popover, single-open)"`

---

## Phase C — Templates (port region-by-region)

> Each task ports a region's markup from prototype-3 into `sheet.html`, substituting the
> listed Jinja bindings. After each task: `GET /character/thorin` → 200, screenshot in
> preview (`aose-app` config), run `pytest tests/test_web.py -q` (update assertions only in
> Task E1 — until then some text asserts may fail; that's expected and tracked).

### Task C1: Skeleton — base.html, identity band, layout grid, overlay containers

**Files:** Modify `aose/web/templates/sheet.html`, `aose/web/templates/base.html`

- [ ] **Step 1:** In `sheet.html`, replace the whole `{% block content %}` with: the prototype-3 `<article class="sheet">` shell — identity band + `.layout` grid with the six group shells (empty `.gbody` placeholders, e.g. `<!-- C2 -->`) + the full-width inventory group shell + footer, then the `#scrim` + all overlay containers (ported as-is; their forms get real actions in Task C8). Add `<script src="/static/sheet_overlays.js" defer></script>` before `{% endblock %}`. Keep the existing `.sheet-actions` print/back bar (Print / Download PDF / Back) above the article.
- [ ] **Identity bindings (display-only — no edit triggers):**
  - name `<h1>{{ sheet.name }}</h1>`
  - tags: `{% if not sheet.race_as_class %}<span class="pill"><b>{{ sheet.race_name }}</b></span>{% endif %}`, `<span class="pill">{{ sheet.class_summary }}</span>`, `<span class="pill"><b>{{ sheet.alignment }}</b></span>`
  - Do NOT port the `pop-identity` popover (no backend route).
  - XP tracks: loop `sheet.advancement` → `cls = "{{ adv.name }} L{{ adv.current_level }}"`, bar width `{% if not adv.at_max %}{{ (adv.current_xp / adv.next_threshold * 100)|round }}%{% else %}100%{% endif %}`, num `{{ adv.current_xp }} / {{ adv.next_threshold or '—' }}`.
- [ ] **Step 2 (verify):** route 200; preview shows identity band + empty group frames; no JS console errors (overlay containers present but unopened).
- [ ] **Step 3: Commit** `git commit -am "feat(sheet): new zine skeleton — identity, layout, overlays"`

### Task C2: Combat group

**Files:** Modify `aose/web/templates/sheet.html` (combat `.gbody`)

- [ ] Port the Combat group body. Bindings:
  - HP: `<span class="box big">{{ sheet.current_hp }}<span ...> / {{ sheet.max_hp }}</span></span>`; whole field `data-pop="pop-hp"`. If `sheet.is_dead`, add a `Dead` state marker (port the dead styling — add a small `.is-dead` line).
  - AC shield: armoured = `{% if sheet.use_ascending %}{{ sheet.ac_ascending }}{% else %}{{ sheet.ac_descending }}{% endif %}`; unarmoured line = `{% if sheet.use_ascending %}{{ sheet.unarmored_ac_ascending }}{% else %}{{ sheet.unarmored_ac_descending }}{% endif %}`.
  - THAC0/attack box: `{% if sheet.use_ascending %}+{{ sheet.attack_bonus }}{% else %}{{ sheet.thac0 }}{% endif %}`, tab label `{{ 'ATTACK' if sheet.use_ascending else 'THAC0' }}`, `data-modal="modal-matrix"`.
  - Move: EX `{{ sheet.movement_base }}′`, EN `{{ sheet.movement_encounter }}′`, OV `{{ sheet.movement_overland }}`mi. If `movement_base == 0`, show the over-encumbered note (port from current sheet line 193-195).
- [ ] Verify route 200 + preview. Commit `git commit -am "feat(sheet): combat group"`.

### Task C3: Abilities & Saves group

- [ ] Port. Abilities loop `sheet.abilities`: `ab` = `{{ ab.ability }}`, `sc` = `{{ ab.score }}{% if ab.modified %}<span class="star">✦</span>{% endif %}`, `md` = `{{ "%+d"|format(ab.modifier) }}`, `tmp` = `tmp {{ "%+d"|format(ab.temp_delta) }}` with `data-pop="pop-temp" data-ability="{{ ab.ability }}"`. Keep the modified-breakdown as the popover or a small caption.
- [ ] Saves loop `sheet.saves`: drop-cap = first letter of `s.label`, `nm` = `{{ s.label }}`, `tg` = `{{ s.target }}`.
- [ ] Verify + commit `git commit -am "feat(sheet): abilities & saves group"`.

### Task C4: Class & Race Features + Weapon Proficiencies group

- [ ] Features chips: loop `sheet.race_features` then `sheet.class_features` → `<button class="chip" data-modal="modal-feature" data-title="{{ f.name }}" data-text="{{ f.text }}">{{ f.name }} <span class="src">{{ f.source }}</span></button>`.
- [ ] Proficiencies subhead — only `{% if sheet.weapon_proficiency_active %}`. Chips from `sheet.proficiencies.weapons` → `data-title`/`data-text` describing specialised vs plain; **no damage**. Meta line `{{ sheet.proficiencies.slots_spent }}/{{ sheet.proficiencies.slots_total }} slots · non-prof −{{ -sheet.proficiencies.penalty }}`. Keep the weapon-qualities `<details>` reference if `sheet.weapon_qualities_reference` (port into this group or the item modal).
- [ ] Verify + commit `git commit -am "feat(sheet): features + proficiencies group"`.

### Task C5: Languages, Notes & Secondary Skills group

- [ ] Languages: `{{ sheet.languages | join(", ") if sheet.languages else "—" }}` + broken-speech note `{% if sheet.broken_speech %}`.
- [ ] Secondary skill: `{% if sheet.secondary_skill %}` → `{{ sheet.secondary_skill }}`.
- [ ] Notes: `<div class="notes-body" data-modal="modal-notes">{{ sheet.notes }}</div>` + a `print-only` paragraph (port from current sheet lines 754-756).
- [ ] Verify + commit `git commit -am "feat(sheet): languages/notes/skills group"`.

### Task C6: Spells group (caster-only)

**Uses `sheet.spellbook` (Task A3).**

- [ ] Wrap the whole group in `{% if sheet.spellbook %}`.
- [ ] For each `block in sheet.spellbook`: bar `Spells — {{ block.caster_type|title }}` + Manage button `data-drawer="drawer-spells"`. For each `lvl in block.levels`: `lvl-head` = `Level {{ lvl.level }}` + `{{ lvl.used }}/{{ lvl.cap }} slots` (arcane also shows `book · {{ lvl.rows|selectattr('known')|list|length }}`). For each `row in lvl.rows`:
  - `<div class="spell{% if row.ready == 0 and row.spent > 0 %} allspent{% endif %}" data-modal="modal-spell" data-title="{{ row.name }}" data-text="{{ row.description }}">`
  - name `<span class="snm">{{ row.name }}</span>`
  - pips: emit `row.ready` × `<i class="pip"></i>` then `row.spent` × `<i class="pip spent"></i>`; if `row.ready == 0 and row.spent == 0` emit `{% if row.known %}<span class="known-tag">known</span>{% endif %}`.
  - For divine blocks (`block.caster_type == "divine"`), only emit rows where `row.ready or row.spent` (memorised only); the full list lives in the drawer.
- [ ] Include the cast legend (port). Verify with a caster example character (see Task E1 for which example; if none, the non-caster Thorin simply renders no Spells group — confirm that). Commit `git commit -am "feat(sheet): spells group (arcane by level + divine)"`.

### Task C7: Inventory, Currency & Treasure group (resting summary)

- [ ] Bar meta: `{% if sheet.carried_weight_cn is not none %}{{ sheet.carried_weight_cn }} / {{ sheet.max_load }} cn{% if sheet.current_weight_band %} · {{ sheet.current_weight_band }}{% endif %}{% endif %}`; Thresholds button `data-modal="modal-encumbrance"` (only when `sheet.encumbrance_table`); Manage button `data-drawer="drawer-equip"`. Carrying-treasure toggle (basic mode) lives in the encumbrance modal — port the form there.
- [ ] Coins row: loop `[("pp","PP"),("gp","GP"),("ep","EP"),("sp","SP"),("cp","CP")]` → `sheet.coins[denom]`. Treasure chip `{{ sheet.treasure_value_gp }} gp` `data-pop="pop-coins"`. **No spendable-gold line.**
- [ ] **Equipped column** = weapons from `sheet.attacks` + equipped armour/worn-magic:
  - For `atk in sheet.attacks`: name `{{ atk.name }}{% if atk.count>1 %} ×{{ atk.count }}{% endif %}` + badges (`magic` if name implies / `spec` if `atk.specialised` / `non-prof` if not `atk.proficient` / `Unloaded` if `atk.unloaded` / `[{{ atk.loaded_ammo_name }}]`); stat `{{ "%+d"|format(atk.to_hit_ascending) }} · {{ atk.damage }} · {% if atk.range_ft %}{{ atk.range_ft[0] }}/{{ atk.range_ft[1] }}/{{ atk.range_ft[2] }}′{% else %}—{% endif %}`. Emit `atk.conditional` as a sub-line. **This is the to-hit-bonus fix** (`to_hit_ascending`, never adjusted THAC0).
  - Equipped armour/shield: from `sheet.equipped` rows (slot armor/shield) → `AC` contribution text, or simply list name + slot.
  - Worn magic: `magic_items_view` rows with `equipped` true → name + `modifier_summary` chips, clickable (`data-modal="modal-feature"` with description).
- [ ] **Carried column**: `inventory_view.carried` rows + containers (collapsed summary line) + gems/jewellery from `sheet.valuables` (with `gem`/`jewel` tags) + spell-sources from `sheet.spell_sources` (`book`/`scroll` tags) + ammo from `sheet.ammo`. Each info-bearing row clickable.
- [ ] **Stashed column**: `inventory_view.stashed` + `+ add…` `data-drawer="drawer-equip"`. Keep the existing `print-only` full inventory block (port from current sheet lines 818-875).
- [ ] Verify + commit `git commit -am "feat(sheet): inventory/currency/treasure group + equipped weapon stats"`.

### Task C8: Overlays wired to real routes

**Files:** Modify `sheet.html` (overlay form actions)

- [ ] Replace each ported overlay's placeholder form with the real action + hidden fields from the *current* `sheet.html` / `_equipment_ui.html`:
  - `pop-hp` → `/character/{{ character_id }}/hp/{damage,heal,set}`.
  - `pop-temp` → `/character/{{ character_id }}/abilities/temp-modifier` (hidden `ability` filled by JS-set `data-ability`; for the prototype's static popover, render one form and set the hidden input via the controller, OR render one form per ability — simplest: keep a single form and add a tiny JS line to copy `data-ability` into the hidden input on open; document it).
  - `pop-coins` → `/character/{{ character_id }}/coins/add` + `/coins/convert` (port the loop from `_equipment_ui.html` lines 29-71).
  - `pop-identity` → **OMIT.** Confirmed: no name/alignment edit route exists and the current sheet does not allow editing them. Render identity (name, alignment) **display-only** in Task C1 — drop the `data-pop="pop-identity"` triggers and the `pop-identity` popover. (Identity editing is a possible future enhancement, out of scope for this redesign — adding it would require new routes.)
  - `modal-advance` → loop `sheet.advancement` with level-up `/level-up/{{ adv.class_id }}`, grant `/xp`, energy-drain `/energy-drain` (port from current sheet lines 235-283).
  - `modal-matrix` → static derived table; compute rows in the template from `sheet.thac0` (descending) or note ascending. Acceptable to render `AC 9..0 → {{ sheet.thac0 - ac }}`.
  - `modal-encumbrance` → port the threshold table from current sheet lines 197-231 using `sheet.encumbrance_table` + carrying-treasure toggle.
  - `modal-notes` → `/notes/set`. `modal-rest` → `/rest/night` + `/rest/full-day` (port loadout + heal from current sheet lines 765-801).
  - `modal-feature` / `modal-spell` → detail display + (spell) the memorise/cast/clear/restore forms keyed by `class_id`/`spell_id` (port from current spells section). For the spell modal, the prep buttons post to `/spells/assign|cast|clear|restore|forget` — but these need slot indices. Decision: the **detail modal shows description only**, and all stateful spell ops happen in the **spells drawer** (Task D-equivalent for spells, already a section). This keeps the modal templated/static. Implement the spells drawer body with the real forms (port from current sheet lines 396-510), grouped by level, with memorise/cast/restore/clear/forget.
- [ ] `drawer-spells` body: port the current sheet's Spells management forms (assign/cast/restore/clear/forget/learn) and the spell-sources add form, restyled. Divine shows the full memorizable list (`block.rows` where not known→ memorisable).
- [ ] Verify every overlay opens and every form has a valid `action`. Grep for `# TODO` / empty `action=""`. Commit `git commit -am "feat(sheet): wire overlays to existing routes"`.

---

## Phase D — Shared partial refactor (drawer body)

### Task D1: `_equipment_ui.html` → tabbed, gated

**Files:** Modify `aose/web/templates/_equipment_ui.html`, `aose/web/routes.py`

- [ ] **Step 1 (routes.py):** add to the sheet route's `_equipment_ui` context: `valuables=sheet.valuables`, `spell_sources=sheet.spell_sources`, `spell_source_add_options` (already passed). The wizard passes none of these (already true).
- [ ] **Step 2:** Wrap the partial body in the prototype-3 tab structure. Tabs and gates:
  - **Carried** (always): the existing inventory tables (equipped/carried/stashed/containers/ammo) — keep all current macros & forms verbatim, just inside `data-pane="inv"`.
  - **Magic** `{% if magic_acquisition %}`: the magic-items + enchanted + add-enchanted blocks (already gated by `magic_acquisition`).
  - **Documents** `{% if spell_sources is defined %}`: move the spell-books-&-scrolls list + add form from `sheet.html` (current lines 513-601) into here.
  - **Treasure** `{% if valuables is defined %}`: move the gems & jewellery management from `sheet.html` (current lines 604-726) into here.
  - **Shop** (always): the existing shop + search.
  - Render the tab buttons conditionally so the wizard (only Carried + Shop contexts) shows just those two tabs. Port the tab-show JS from prototype-3 (or rely on `sheet_overlays.js` `.tabs` handler — the partial is inside the drawer which loads that script).
- [ ] **Step 3 (verify wizard):** `pytest tests/test_wizard.py -q` PASS; preview the wizard equipment step (`/wizard/...`) — only Carried + Shop tabs, no errors.
- [ ] **Step 4 (verify sheet):** open the equipment drawer — all 5 tabs; Documents shows spell sources, Treasure shows gems/jewellery, with working forms.
- [ ] **Step 5:** Remove the now-migrated spell-sources / gems-jewellery sections from `sheet.html` (they live in the drawer now). Keep `spell_source_add.js` include where the form now lives.
- [ ] **Commit** `git commit -am "refactor(equipment): tabbed drawer body; fold docs+treasure; wizard shows carried+shop"`.

---

## Phase E — Regression, print, cleanup

### Task E1: Update & extend web tests

**Files:** Modify `tests/test_web.py`

- [ ] Update `test_sheet_renders` text assertions to the new markup (HP `8 / 8` likely still present; `THAC0`, feature names survive; adjust any header text that changed).
- [ ] Update `test_sheet_renders_valuables_section`: `"Gems &amp; Jewellery"` header is gone from the resting sheet — assert the gem/jewellery data appears in the inventory/treasure markup instead (e.g. `"ruby"`, `"necklace"` still in body), and/or assert the Treasure value. 
- [ ] **Add** `test_noncaster_has_no_spells_group` (Thorin → `assert "Spells —" not in body`) and `test_caster_has_spells_group` (a magic-user/elf example → `assert "Spells —" in body`). If no caster example exists under `examples/`, build one inline like `test_sheet_renders_valuables_section` does.
- [ ] Run `pytest tests/test_web.py -q` → PASS.
- [ ] Commit `git commit -am "test(web): update sheet assertions; cover caster/non-caster spell group"`.

### Task E2: Print reconciliation

- [ ] Confirm `sheet_print.html` is a separate template/route and renders unchanged: `pytest tests/ -q -k print` and open `/character/thorin/print`.
- [ ] Ensure the new `sheet.css` `@media print` block expands group bodies (`overflow:visible; max-height:none`) and hides chrome/overlays (already in prototype-3). Quick visual via browser print preview optional.
- [ ] Commit if changed.

### Task E3: Full regression + cleanup + finish

- [ ] Remove dead CSS rules from `sheet.css` that no longer have markup (old `.section`, `.stat-row`, `.attacks-table`, `.spell-block`, `.valuable`, etc.) — only after confirming no other template uses them (grep across `templates/`).
- [ ] Run the **full** suite: `.venv\Scripts\python.exe -m pytest tests/ -q` → all green (ignore the known tempdir PermissionError).
- [ ] Preview pass: non-caster (Thorin) + a caster + open every overlay; check console for errors via `preview_console_logs`.
- [ ] Update `CLAUDE.md` "Current state" with a one-paragraph note on the redesign landing, and update `project_sheet_redesign.md` memory to "shipped".
- [ ] Final commit `git commit -am "chore(sheet): remove dead styles; finish zine redesign"`. Then use `superpowers:finishing-a-development-branch`.

---

## Self-review notes

- **Spec coverage:** identity/combat/abilities/saves/features/proficiencies/spells/inventory/
  currency/treasure/languages/notes/skills → Tasks C1-C7. Overlays/routes → C8, D1. Per-weapon
  bonus fix → C7. Unarmoured AC + EX/EN/OV → A1/A2/C2. Spell three-state model → A3/C6/C8.
  Wizard-partial preservation → D1. Test regression → E1. Print → E2.
- **Risk:** the spell prep controls (slot indices) are kept in the drawer, not the templated
  detail modal — this is a deliberate simplification so the modal stays static/templated.
- **Resolved:** no identity (name/alignment) edit route exists and the current sheet doesn't
  edit them — identity is rendered display-only; editing is out of scope (future enhancement).
