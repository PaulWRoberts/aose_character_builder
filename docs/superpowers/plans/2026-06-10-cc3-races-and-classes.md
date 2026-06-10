# CC3 Races & Classes + Feature-Choice Mechanic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import Carcass Crawler 3's Beast Master, Dragonborn, Mutoid, Mycelian, and Tiefling as demihuman classes (race-as-class) and split-mode races, and add the cross-cutting "feature choice" mechanic (pick/roll N options at creation) with its automations: AC bonuses, synthetic unarmed attacks, situational save bonuses, level-scaling, and use-limited innate abilities.

**Architecture:** A new `FeatureChoice`/`ChoiceOption` model lets a race/class declare "pick N from this table". Selections live on `CharacterSpec.feature_choices`. Chosen options are feature-shaped, so they flow through the existing `aose/engine/features.py` pipeline (`all_modifiers`, `feature_weapons`) with no per-option code. A new `aose/engine/innate.py` collects daily-use abilities (the mental-power-pool pattern). The wizard's `class_setup` step gains a "Features" picker; the sheet renders only chosen options and adds an innate-abilities block with a spell expander on the feature modal.

**Tech Stack:** Python 3, Pydantic v2, FastAPI, Jinja2, pytest. Run app: `.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`. Run tests: `.venv\Scripts\python.exe -m pytest tests/ -q`.

**Conventions reminder:** No migrations needed (app is local-only). Engine modules are pure and cycle-free. Class/race bonuses are data (`GrantedModifier`), never referenced by id in engine code. Race and race-as-class are independent stat blocks — never assume one mirrors the other.

---

## Phase 1 — Models

### Task 1: `FeatureChoice` / `ChoiceOption` / `DailyUses` models

**Files:**
- Create: `aose/models/choice.py`
- Test: `tests/test_feature_choices.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_choices.py
import pytest
from pydantic import ValidationError

from aose.models.choice import ChoiceOption, DailyUses, FeatureChoice
from aose.models import GrantedModifier


def test_choice_option_minimal():
    opt = ChoiceOption(id="scales", name="Scales")
    assert opt.text == ""
    assert opt.granted_modifiers == []
    assert opt.daily_uses is None
    assert opt.spell_id is None


def test_choice_option_full():
    opt = ChoiceOption(
        id="magic_missile", name="Magic Missile",
        text="Cast magic missile once/day.",
        granted_modifiers=[GrantedModifier(target="ac", op="add", value=2)],
        daily_uses=DailyUses(per_day=1),
        spell_id="magic_user_magic_missile",
    )
    assert opt.daily_uses.per_day == 1
    assert opt.daily_uses.scales_with_level is False
    assert opt.spell_id == "magic_user_magic_missile"


def test_daily_uses_scales():
    du = DailyUses(scales_with_level=True)
    assert du.per_day == 1
    assert du.scales_with_level is True


def test_feature_choice_defaults():
    grp = FeatureChoice(id="mutations", name="Mutations", pick=2,
                        options=[ChoiceOption(id="a", name="A"),
                                 ChoiceOption(id="b", name="B")])
    assert grp.pick == 2
    assert grp.roll_dice is None
    assert grp.cosmetic is False


def test_feature_choice_rejects_unknown_field():
    with pytest.raises(ValidationError):
        FeatureChoice(id="x", name="X", options=[], allow_duplicates=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_choices.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.models.choice`.

- [ ] **Step 3: Write minimal implementation**

```python
# aose/models/choice.py
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .modifier import GrantedModifier


class DailyUses(BaseModel):
    """A per-day usage limit on an innate ability (feature or chosen option).

    ``per_day`` is the flat number of uses; when ``scales_with_level`` is True the
    maximum equals the granting class's level instead (Mycelian fungal spores:
    once/day per level). Collected and tracked by ``aose/engine/innate.py``.
    """
    model_config = ConfigDict(extra="forbid")

    per_day: int = 1
    scales_with_level: bool = False


class ChoiceOption(BaseModel):
    """One selectable option in a ``FeatureChoice`` group. Deliberately
    feature-shaped (``mechanical`` + ``granted_modifiers`` + ``daily_uses``) so a
    chosen option reuses every existing feature-automation path. ``spell_id``
    references a real ``Spell`` for the sheet's feature-modal spell expander.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str = ""
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
    daily_uses: DailyUses | None = None
    spell_id: str | None = None


class FeatureChoice(BaseModel):
    """A "pick (or roll) N from this table" group on a Race/CharClass. Selection
    is always *distinct* (no option appears twice) — there is no duplicates flag
    because no CC3 table allows them.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str = ""
    pick: int = 1
    roll_dice: str | None = None     # e.g. "d8" / "d10" for the Roll button
    cosmetic: bool = False           # purely flavor (Fiendish Appearance)
    options: list[ChoiceOption]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_choices.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/models/choice.py tests/test_feature_choices.py
git commit -m "feat(models): FeatureChoice/ChoiceOption/DailyUses models"
```

---

### Task 2: Wire choices/daily-uses into Race, CharClass, CharacterSpec, and exports

**Files:**
- Modify: `aose/models/character_class.py` (`ClassFeature`, `CharClass`)
- Modify: `aose/models/race.py` (`RaceFeature`, `Race`)
- Modify: `aose/models/character.py` (`CharacterSpec`)
- Modify: `aose/models/__init__.py`
- Test: `tests/test_feature_choices.py` (extend)

- [ ] **Step 1: Add the failing test**

Append to `tests/test_feature_choices.py`:

```python
from aose.models import (
    CharacterSpec, CharClass, ClassEntry, ClassFeature, Race, RaceFeature, Ability,
    FeatureChoice, ChoiceOption, DailyUses,
)


def test_class_feature_daily_uses_and_spell():
    f = ClassFeature(id="breath", name="Breath Weapon", text="...",
                     daily_uses=DailyUses(per_day=3))
    assert f.daily_uses.per_day == 3
    assert f.spell_id is None


def test_class_carries_feature_choices():
    c = CharClass(
        id="x", name="X", prime_requisites=[Ability.STR], hit_die="1d6",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        feature_choices=[FeatureChoice(id="g", name="G", options=[
            ChoiceOption(id="o", name="O")])],
    )
    assert c.feature_choices[0].id == "g"


def test_race_feature_daily_uses():
    f = RaceFeature(id="spores", name="Fungal Spores", text="...",
                    daily_uses=DailyUses(scales_with_level=True))
    assert f.daily_uses.scales_with_level is True


def test_spec_feature_choices_and_innate_defaults():
    spec = CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        classes=[ClassEntry(class_id="fighter")], alignment="neutral",
    )
    assert spec.feature_choices == {}
    assert spec.innate_uses == {}
    spec2 = spec.model_copy(update={"feature_choices": {"mutations": ["scales"]}})
    assert spec2.feature_choices["mutations"] == ["scales"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_choices.py -q`
Expected: FAIL — `TypeError`/`ValidationError` (unknown fields `daily_uses`, `feature_choices`, `innate_uses`).

- [ ] **Step 3: Implement — `character_class.py`**

In `aose/models/character_class.py`, add the import and fields. Change the import block at the top:

```python
from .modifier import GrantedModifier
from .choice import DailyUses, FeatureChoice
```

In `ClassFeature`, add two fields after `granted_modifiers`:

```python
class ClassFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    gained_at_level: int = 1
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
    # Innate per-day ability (breath weapon, fungal spores). Tracked by innate.py.
    daily_uses: DailyUses | None = None
    # References a real Spell for the sheet feature-modal spell expander.
    spell_id: str | None = None
```

In `CharClass`, add after `features`:

```python
    features: list[ClassFeature] = Field(default_factory=list)
    # "Pick/roll N at creation" groups (CC3). Chosen options live on
    # CharacterSpec.feature_choices and flow through aose/engine/features.py.
    feature_choices: list[FeatureChoice] = Field(default_factory=list)
```

- [ ] **Step 4: Implement — `race.py`**

In `aose/models/race.py`, add the import and fields:

```python
from .modifier import GrantedModifier
from .choice import DailyUses, FeatureChoice
```

In `RaceFeature`:

```python
class RaceFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    text: str
    mechanical: dict[str, Any] | None = None
    granted_modifiers: list[GrantedModifier] = Field(default_factory=list)
    daily_uses: DailyUses | None = None
    spell_id: str | None = None
```

In `Race`, add after `features`:

```python
    features: list[RaceFeature] = Field(default_factory=list)
    feature_choices: list[FeatureChoice] = Field(default_factory=list)
```

- [ ] **Step 5: Implement — `character.py`**

In `CharacterSpec` (`aose/models/character.py`), add two fields just after `weapon_specialisations`:

```python
    weapon_proficiencies: list[str] = Field(default_factory=list)
    weapon_specialisations: list[str] = Field(default_factory=list)
    # CC3 feature choices: group id -> chosen option ids (distinct).
    feature_choices: dict[str, list[str]] = Field(default_factory=dict)
    # Innate daily-use ability id -> uses spent today (reset on rest).
    innate_uses: dict[str, int] = Field(default_factory=dict)
    ruleset: RuleSet = Field(default_factory=RuleSet)
```

- [ ] **Step 6: Implement — `__init__.py` exports**

In `aose/models/__init__.py`, add the import after the `character_class` import block:

```python
from .choice import ChoiceOption, DailyUses, FeatureChoice
```

And add to `__all__` (after `"ClassFeature",`):

```python
    "ChoiceOption",
    "DailyUses",
    "FeatureChoice",
```

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_choices.py -q`
Expected: PASS (9 passed).

- [ ] **Step 8: Run full suite (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (the trailing `pytest-current` PermissionError is the known Windows quirk — ignore it).

- [ ] **Step 9: Commit**

```bash
git add aose/models/
git commit -m "feat(models): feature_choices + daily_uses/spell_id on features + spec fields"
```

---

## Phase 2 — Engine: choice resolution in `features.py`

### Task 3: Resolve chosen options into the feature pipeline

**Files:**
- Modify: `aose/engine/features.py`
- Test: `tests/test_choice_resolution.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_choice_resolution.py
import pytest

from aose.data.loader import GameData
from aose.engine.features import all_modifiers, feature_weapons, iter_reached, selected_options
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ClassFeature,
    ChoiceOption, DailyUses, FeatureChoice, GrantedModifier,
)
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def _data_with_test_class():
    data = GameData.load(DATA_DIR)
    test_cls = CharClass(
        id="ztest", name="ZTest", prime_requisites=[Ability.STR], hit_die="1d6",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        feature_choices=[FeatureChoice(id="grp", name="Grp", pick=2, options=[
            ChoiceOption(id="scales", name="Scales",
                         granted_modifiers=[GrantedModifier(target="ac", op="add", value=2)]),
            ChoiceOption(id="claw", name="Claw",
                         mechanical={"weapon": {"name": "Claw", "damage": "1d6", "melee": True}}),
            ChoiceOption(id="none", name="None"),
        ])],
    )
    data.classes["ztest"] = test_cls
    return data


def _spec(chosen):
    return CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        classes=[ClassEntry(class_id="ztest", level=1)], alignment="neutral",
        feature_choices={"grp": chosen},
    )


def test_chosen_option_grants_modifier():
    data = _data_with_test_class()
    mods = all_modifiers(_spec(["scales", "claw"]), data)
    assert any(m.target == "ac" and m.op == "add" and m.value == 2 for m in mods)


def test_unchosen_option_contributes_nothing():
    data = _data_with_test_class()
    mods = all_modifiers(_spec(["none", "claw"]), data)
    assert not any(m.target == "ac" and m.value == 2 for m in mods)


def test_chosen_option_emits_feature_weapon():
    data = _data_with_test_class()
    weapons = feature_weapons(_spec(["scales", "claw"]), data)
    names = [d["name"] for _id, d in weapons]
    assert "Claw" in names


def test_selected_options_helper():
    data = _data_with_test_class()
    opts = list(selected_options(data.classes["ztest"], {"grp": ["scales"]}))
    assert [o.id for o in opts] == ["scales"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_choice_resolution.py -q`
Expected: FAIL — `ImportError: cannot import name 'iter_reached'`.

- [ ] **Step 3: Implement — refactor `features.py` onto a level-aware iterator**

In `aose/engine/features.py`, add `selected_options` and `iter_reached`, and rewrite `_reached_features`, `feature_weapons`, and `feature_modifiers` to use them. Replace the existing `_reached_features`, `feature_weapons`, and `feature_modifiers` functions with:

```python
def selected_options(owner, selections: dict[str, list[str]]):
    """Yield the chosen ``ChoiceOption``s for a race/class given the character's
    selection map (group id -> chosen option ids). Unknown ids are skipped."""
    for group in getattr(owner, "feature_choices", []):
        chosen = selections.get(group.id, [])
        by_id = {o.id: o for o in group.options}
        for oid in chosen:
            if oid in by_id:
                yield by_id[oid]


def iter_reached(spec: CharacterSpec, data: GameData):
    """Yield ``(feature_or_option, level_or_None, source_label)`` for everything
    that applies: reached class features + chosen class options (with the class's
    level), and — unless race-as-class — race features + chosen race options
    (level None). The single source of truth for "what applies"; every
    feature-derived collector iterates this so they all agree."""
    sel = spec.feature_choices
    for entry in spec.classes:
        cls = data.classes.get(entry.class_id)
        if cls is None:
            continue
        for feat in cls.features:
            if feat.gained_at_level <= entry.level:
                yield feat, entry.level, cls.name
        for opt in selected_options(cls, sel):
            yield opt, entry.level, cls.name
    if not is_race_as_class(spec, data):
        race = data.races.get(spec.race_id)
        if race is not None:
            for feat in race.features:
                yield feat, None, race.name
            for opt in selected_options(race, sel):
                yield opt, None, race.name


def _reached_features(spec: CharacterSpec, data: GameData):
    """Back-compat ``(feature, source_label)`` view over ``iter_reached`` for
    collectors that don't need the level (open-doors, 1h-2h)."""
    for feat, _level, src in iter_reached(spec, data):
        yield feat, src


def feature_weapons(spec: CharacterSpec, data: GameData) -> list[tuple[str, dict]]:
    """Synthetic always-available weapons declared by reached features/options via
    ``mechanical['weapon']`` (gargantua rock, mutoid claws, mycelian fist).
    A descriptor with ``damage_per_level_die`` (mycelian fist) resolves to
    ``"{level}{die}"`` against the granting class's level."""
    out: list[tuple[str, dict]] = []
    for feat, level, _src in iter_reached(spec, data):
        if not feat.mechanical:
            continue
        descriptor = feat.mechanical.get("weapon")
        if not descriptor:
            continue
        descriptor = dict(descriptor)
        die = descriptor.pop("damage_per_level_die", None)
        if die is not None and level is not None:
            descriptor["damage"] = f"{level}{die}"
        out.append((feat.id, descriptor))
    return out


def feature_modifiers(spec: CharacterSpec, data: GameData) -> list[Modifier]:
    """Concrete ``Modifier``s from every reached class/race feature and chosen
    option. Level-scaling resolves against the granting class's level (None on a
    race feature/option). For a race-as-class character the linked race
    contributes nothing — handled inside ``iter_reached``."""
    eff = effective_abilities(spec, data)
    out: list[Modifier] = []
    for feat, level, _src in iter_reached(spec, data):
        for g in feat.granted_modifiers:
            out.append(Modifier(
                target=g.target, op=g.op,
                value=resolve_value(g, level=level, eff=eff),
                condition=g.condition, source=feat.name,
            ))
    return out
```

> Note: leave `open_doors_category_bonus` and `one_handed_two_handed_weapons` untouched — they already iterate `_reached_features`, which now includes options (harmless: no option sets those keys).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_choice_resolution.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run regression suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_modifiers.py tests/test_race_as_class.py tests/test_cc3_attacks.py tests/test_derivation.py -q`
Expected: PASS (the existing gargantua-rock / race-as-class behavior is preserved by `iter_reached`).

- [ ] **Step 6: Commit**

```bash
git add aose/engine/features.py tests/test_choice_resolution.py
git commit -m "feat(engine): resolve chosen feature options through the feature pipeline"
```

---

### Task 4: Level-scaled feature-weapon damage (Mycelian fist)

**Files:**
- Test: `tests/test_choice_resolution.py` (extend)

> Implementation already landed in Task 3 (`damage_per_level_die`); this task adds the explicit level-scaling test so the behavior is pinned.

- [ ] **Step 1: Add the failing test**

Append to `tests/test_choice_resolution.py`:

```python
def test_feature_weapon_scales_with_level():
    data = GameData.load(DATA_DIR)
    from aose.models import ClassFeature
    cls = CharClass(
        id="zscale", name="ZScale", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        features=[ClassFeature(id="fist", name="Fist", text="...",
                  mechanical={"weapon": {"name": "Fist", "melee": True,
                                         "damage_per_level_die": "d4"}})],
    )
    data.classes["zscale"] = cls
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zscale", level=3)])
    weapons = dict((d["name"], d) for _id, d in feature_weapons(spec, data))
    assert weapons["Fist"]["damage"] == "3d4"
    assert "damage_per_level_die" not in weapons["Fist"]
```

- [ ] **Step 2: Run to verify pass** (implementation already exists)

Run: `.venv\Scripts\python.exe -m pytest tests/test_choice_resolution.py::test_feature_weapon_scales_with_level -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_choice_resolution.py
git commit -m "test(engine): pin level-scaled feature-weapon damage"
```

---

## Phase 3 — Engine: innate daily-use abilities

### Task 5: `aose/engine/innate.py`

**Files:**
- Create: `aose/engine/innate.py`
- Test: `tests/test_innate_abilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_innate_abilities.py
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.innate import (
    InnateError, innate_abilities, reset_innate, restore_innate, spend_innate,
)
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ClassFeature, DailyUses,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    data = GameData.load(DATA_DIR)
    data.classes["zinnate"] = CharClass(
        id="zinnate", name="ZInnate", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        features=[
            ClassFeature(id="breath", name="Breath", text="3/day",
                         daily_uses=DailyUses(per_day=3)),
            ClassFeature(id="spores", name="Spores", text="per level",
                         daily_uses=DailyUses(scales_with_level=True),
                         spell_id="magic_user_magic_missile"),
        ],
    )
    return data


def _spec(level=2, used=None):
    return CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        alignment="neutral", classes=[ClassEntry(class_id="zinnate", level=level)],
        innate_uses=used or {},
    )


def test_collects_with_resolved_max():
    abilities = {a.id: a for a in innate_abilities(_spec(level=2), _data())}
    assert abilities["breath"].max_uses == 3
    assert abilities["spores"].max_uses == 2          # scales with level=2
    assert abilities["spores"].spell_id == "magic_user_magic_missile"
    assert abilities["breath"].remaining == 3


def test_spend_and_remaining():
    data = _data()
    spec = spend_innate(_spec(level=2), "breath")
    assert spec.innate_uses["breath"] == 1
    ab = {a.id: a for a in innate_abilities(spec, data)}["breath"]
    assert ab.used == 1 and ab.remaining == 2


def test_spend_beyond_max_raises():
    data = _data()
    spec = _spec(level=2, used={"breath": 3})
    with pytest.raises(InnateError):
        spend_innate(spec, "breath")


def test_restore_and_reset():
    spec = _spec(level=2, used={"breath": 2, "spores": 1})
    spec = restore_innate(spec, "breath")
    assert spec.innate_uses["breath"] == 1
    spec = reset_innate(spec)
    assert spec.innate_uses == {}


def test_spend_unknown_ability_raises():
    with pytest.raises(InnateError):
        spend_innate(_spec(), "nope")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_innate_abilities.py -q`
Expected: FAIL — `ModuleNotFoundError: aose.engine.innate`.

- [ ] **Step 3: Implement**

```python
# aose/engine/innate.py
"""Innate daily-use abilities (CC3): breath weapons, fungal spores, and chosen
spell-granting options (Fiendish Gifts). The non-caster analogue of the mental-
power pool — a per-ability daily counter reset on rest.

Cycle-free: imports models, loader, and ``iter_reached`` from features (which
imports only models/loader/magic). Never imported by features.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from aose.data.loader import GameData
from aose.models import CharacterSpec
from aose.engine.features import iter_reached


class InnateError(Exception):
    """Raised on an invalid innate-use operation (unknown id, over/under flow)."""


@dataclass
class InnateAbility:
    id: str
    name: str
    text: str
    source: str
    spell_id: str | None
    max_uses: int
    used: int
    remaining: int


def _max_uses(daily_uses, level: int | None) -> int:
    if daily_uses.scales_with_level:
        return max(1, level or 1)
    return daily_uses.per_day


def innate_abilities(spec: CharacterSpec, data: GameData) -> list[InnateAbility]:
    """Every reached feature/option carrying ``daily_uses``, with resolved max
    uses and the character's spent count. Ordered by appearance in iter_reached."""
    out: list[InnateAbility] = []
    for feat, level, src in iter_reached(spec, data):
        du = getattr(feat, "daily_uses", None)
        if du is None:
            continue
        mx = _max_uses(du, level)
        used = min(spec.innate_uses.get(feat.id, 0), mx)
        out.append(InnateAbility(
            id=feat.id, name=feat.name, text=feat.text, source=src,
            spell_id=getattr(feat, "spell_id", None),
            max_uses=mx, used=used, remaining=max(0, mx - used),
        ))
    return out


def _ability_max(spec: CharacterSpec, data: GameData, ability_id: str) -> int:
    for ab in innate_abilities(spec, data):
        if ab.id == ability_id:
            return ab.max_uses
    raise InnateError(f"No innate ability {ability_id!r}")


def spend_innate(spec: CharacterSpec, ability_id: str,
                 data: GameData | None = None) -> CharacterSpec:
    """Increment one use; raise if already at max. ``data`` is required to know
    the max — callers on the live sheet pass the loaded GameData."""
    if data is None:
        raise InnateError("spend_innate requires GameData to resolve the max")
    mx = _ability_max(spec, data, ability_id)
    used = spec.innate_uses.get(ability_id, 0)
    if used >= mx:
        raise InnateError(f"{ability_id!r} has no uses remaining")
    new = dict(spec.innate_uses)
    new[ability_id] = used + 1
    return spec.model_copy(update={"innate_uses": new})


def restore_innate(spec: CharacterSpec, ability_id: str) -> CharacterSpec:
    """Decrement one use (floor 0); drops the key at 0."""
    used = spec.innate_uses.get(ability_id, 0)
    new = dict(spec.innate_uses)
    if used <= 1:
        new.pop(ability_id, None)
    else:
        new[ability_id] = used - 1
    return spec.model_copy(update={"innate_uses": new})


def reset_innate(spec: CharacterSpec) -> CharacterSpec:
    """Clear all innate use counters (a new day)."""
    return spec.model_copy(update={"innate_uses": {}})
```

> The test calls `spend_innate(spec, "breath")` without `data`, but the test's `_data()` is in scope — update the two spend tests to pass `data`. Adjust the test calls: `spend_innate(_spec(level=2), "breath", data)` and the over-max test to `spend_innate(spec, "breath", data)`.

- [ ] **Step 4: Fix the test calls and run to verify pass**

Edit `tests/test_innate_abilities.py`: in `test_spend_and_remaining` use `spec = spend_innate(_spec(level=2), "breath", data)`; in `test_spend_beyond_max_raises` use `spend_innate(spec, "breath", data)`; in `test_spend_unknown_ability_raises` use `spend_innate(_spec(), "nope", _data())`.

Run: `.venv\Scripts\python.exe -m pytest tests/test_innate_abilities.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/innate.py tests/test_innate_abilities.py
git commit -m "feat(engine): innate daily-use abilities (collect/spend/restore/reset)"
```

---

### Task 6: Reset innate uses on rest

**Files:**
- Modify: `aose/web/routes.py` (`rest_night`, `rest_full_day`)
- Test: `tests/test_rest_routes.py` (extend) — follow the existing fixtures in that file.

- [ ] **Step 1: Add the failing test**

Open `tests/test_rest_routes.py`, read its existing client/spec fixtures, and add a test that saves a character with `innate_uses={"breath": 2}`, POSTs `/character/{id}/rest/night`, reloads, and asserts `spec.innate_uses == {}`. Use the same `_make_client` / save helpers already in that file.

```python
def test_rest_night_resets_innate_uses(tmp_path):
    client, characters_dir = _make_client(tmp_path)   # match the file's helper
    spec = _basic_spec()                               # match the file's helper
    spec.innate_uses = {"breath": 2}
    save_character("hero", spec, characters_dir)
    r = client.post("/character/hero/rest/night", data={"mode": "keep"})
    assert r.status_code in (200, 303)
    reloaded = load_character("hero", characters_dir)
    assert reloaded.innate_uses == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -q -k innate`
Expected: FAIL — `innate_uses` still `{"breath": 2}`.

- [ ] **Step 3: Implement**

In `aose/web/routes.py`, add the import near the other engine imports:

```python
from aose.engine.innate import reset_innate
```

In `rest_night`, after `spec.classes = [_apply_rest_mode(e, mode) for e in spec.classes]`, add:

```python
    spec = reset_innate(spec)
```

In `rest_full_day`, after the line that rebuilds `spec.classes` with `_apply_rest_mode`, add the same `spec = reset_innate(spec)` line before `save_character(...)`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_rest_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/routes.py tests/test_rest_routes.py
git commit -m "feat(rest): reset innate daily-use counters on rest"
```

---

## Phase 4 — Sheet: chosen-option features, innate block, spell expander

### Task 7: Render chosen options as features (and only chosen ones)

**Files:**
- Modify: `aose/sheet/view.py` (`SheetFeature`, `_class_features`, `_race_features`)
- Test: `tests/test_sheet_choices.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sheet_choices.py
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.sheet.view import build_sheet
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ChoiceOption, FeatureChoice,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    data = GameData.load(DATA_DIR)
    data.classes["zsheet"] = CharClass(
        id="zsheet", name="ZSheet", prime_requisites=[Ability.STR], hit_die="1d6",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        feature_choices=[FeatureChoice(id="grp", name="Grp", pick=1, options=[
            ChoiceOption(id="picked", name="Picked Trait", text="Chosen."),
            ChoiceOption(id="other", name="Other Trait", text="Not chosen."),
        ])],
    )
    return data


def _spec():
    return CharacterSpec(
        name="T", abilities={a: 10 for a in Ability}, race_id="human",
        alignment="neutral", classes=[ClassEntry(class_id="zsheet", level=1)],
        feature_choices={"grp": ["picked"]},
    )


def test_only_chosen_option_renders_as_feature():
    sheet = build_sheet(_spec(), _data())
    names = [f.name for f in sheet.class_features]
    assert "Picked Trait" in names
    assert "Other Trait" not in names
    assert "Grp" not in names           # the picker container never renders
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_choices.py -q`
Expected: FAIL — "Picked Trait" not in features.

- [ ] **Step 3: Implement**

In `aose/sheet/view.py`:

Add `spell_detail` to `SheetFeature` (`DetailCard` is already imported at the top of `view.py`: `from aose.engine.detail import DetailCard, item_card, spell_card`):

```python
class SheetFeature(BaseModel):
    name: str
    text: str
    source: str
    spell_detail: DetailCard | None = None   # spell card for the modal expander, None when not a spell feature
```

Add `selected_options` to the existing features import near the top:

```python
from aose.engine.features import is_race_as_class, open_doors_category_bonus, selected_options
```

Add a small builder above `_race_features` (`spell_card(spell) -> DetailCard` is already imported and used by `mental_powers_view`):

```python
def _feature_row(feat, source: str, data: GameData) -> SheetFeature:
    spell_id = getattr(feat, "spell_id", None)
    detail = spell_card(data.spells[spell_id]) if spell_id in data.spells else None
    return SheetFeature(name=feat.name, text=feat.text, source=source,
                        spell_detail=detail)
```

Rewrite `_race_features` and `_class_features`:

```python
def _race_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    if is_race_as_class(spec, data):
        return []
    race = data.races[spec.race_id]
    rows = [_feature_row(f, f"Race: {race.name}", data) for f in race.features]
    rows += [_feature_row(o, f"Race: {race.name}", data)
             for o in selected_options(race, spec.feature_choices)]
    return rows


def _class_features(spec: CharacterSpec, data: GameData) -> list[SheetFeature]:
    out: list[SheetFeature] = []
    for entry in spec.classes:
        cls = data.classes[entry.class_id]
        for f in cls.features:
            if f.gained_at_level <= entry.level:
                out.append(_feature_row(f, f"Class: {cls.name}", data))
        for o in selected_options(cls, spec.feature_choices):
            out.append(_feature_row(o, f"Class: {cls.name}", data))
    return out
```

> If `spell_card` is module-private (`_spell_card`) confirm its name by grepping `def .*spell_card` in `view.py` and use the actual name.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_choices.py -q`
Expected: PASS.

- [ ] **Step 5: Run sheet regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sheet_view.py tests/test_sheet.py tests/test_race_as_class.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/sheet/view.py tests/test_sheet_choices.py
git commit -m "feat(sheet): render chosen options as features with spell-card detail"
```

---

### Task 8: Innate-abilities block + view + routes

**Files:**
- Modify: `aose/sheet/view.py` (`InnateAbilityRow` model, `innate_view`, `CharacterSheet`, `build_sheet`)
- Modify: `aose/web/routes.py` (`/innate/{spend,restore,reset}`)
- Test: `tests/test_innate_view.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_innate_view.py
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.sheet.view import build_sheet
from aose.models import (
    Ability, CharacterSpec, CharClass, ClassEntry, ClassFeature, DailyUses,
)

DATA_DIR = Path(__file__).parent.parent / "data"


def _data():
    data = GameData.load(DATA_DIR)
    data.classes["zinn"] = CharClass(
        id="zinn", name="ZInn", prime_requisites=[Ability.STR], hit_die="1d8",
        weapons_allowed="all", armor_allowed="all", shields_allowed=True,
        progression=data.classes["fighter"].progression,
        features=[ClassFeature(id="breath", name="Breath", text="3/day",
                  daily_uses=DailyUses(per_day=3),
                  spell_id="magic_user_magic_missile")],
    )
    return data


def test_innate_block_on_sheet():
    spec = CharacterSpec(name="T", abilities={a: 10 for a in Ability},
                         race_id="human", alignment="neutral",
                         classes=[ClassEntry(class_id="zinn", level=1)],
                         innate_uses={"breath": 1})
    sheet = build_sheet(spec, _data())
    assert len(sheet.innate_abilities) == 1
    row = sheet.innate_abilities[0]
    assert row.id == "breath" and row.max_uses == 3 and row.remaining == 2
    assert row.spell_detail  # magic missile card rendered
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_innate_view.py -q`
Expected: FAIL — `CharacterSheet` has no `innate_abilities`.

- [ ] **Step 3: Implement — view.py**

Add models near `MentalPowersBlock`:

```python
class InnateAbilityRow(BaseModel):
    id: str
    name: str
    text: str
    source: str
    max_uses: int
    used: int
    remaining: int
    spell_detail: DetailCard | None = None   # spell card, None when not a spell ability
```

Add the view builder (near `mental_powers_view`), importing the engine at top of file with the other engine imports (`from aose.engine.innate import innate_abilities`):

```python
def innate_view(spec: CharacterSpec, data: GameData) -> list[InnateAbilityRow]:
    rows: list[InnateAbilityRow] = []
    for ab in innate_abilities(spec, data):
        detail = spell_card(data.spells[ab.spell_id]) if ab.spell_id in data.spells else None
        rows.append(InnateAbilityRow(
            id=ab.id, name=ab.name, text=ab.text, source=ab.source,
            max_uses=ab.max_uses, used=ab.used, remaining=ab.remaining,
            spell_detail=detail,
        ))
    return rows
```

Add to `CharacterSheet` (near `mental_powers`):

```python
    innate_abilities: list[InnateAbilityRow] = Field(default_factory=list)
```

In `build_sheet(...)`, add to the constructor call (near `mental_powers=mental_powers_view(spec, data),`):

```python
        innate_abilities=innate_view(spec, data),
```

- [ ] **Step 4: Run view test to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_innate_view.py -q`
Expected: PASS.

- [ ] **Step 5: Implement — routes.py**

Add after the `/powers/reset` route in `aose/web/routes.py`:

```python
from aose.engine.innate import (
    InnateError, reset_innate, restore_innate, spend_innate,
)  # add to the existing innate import line


@router.post("/character/{character_id}/innate/spend")
async def sheet_innate_spend(request: Request, character_id: str,
                             ability_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec = spend_innate(spec, ability_id, request.app.state.game_data)
    except InnateError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/innate/restore")
async def sheet_innate_restore(request: Request, character_id: str,
                               ability_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec = restore_innate(spec, ability_id)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/innate/reset")
async def sheet_innate_reset(request: Request, character_id: str):
    spec = _load_spec_or_404(request, character_id)
    spec = reset_innate(spec)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
```

> Merge the `from aose.engine.innate import ...` into the single import added in Task 6 (don't duplicate the import line).

- [ ] **Step 6: Add a route smoke test**

Append to `tests/test_innate_view.py` a test that saves a `zinn` character via the app test client and POSTs `/character/{id}/innate/spend` with `ability_id=breath`, then reloads and asserts `innate_uses["breath"] == 1`. Model it on the client setup in `tests/test_rest_routes.py`.

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_innate_view.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/sheet/view.py aose/web/routes.py tests/test_innate_view.py
git commit -m "feat(sheet): innate-abilities block + spend/restore/reset routes"
```

---

### Task 9: Sheet templates — innate section + feature-modal spell expander

**Files:**
- Modify: `aose/web/templates/sheet.html` (feature `<li>`s, `modal-feature`, new innate section)
- Modify: `aose/web/static/sheet_overlays.js` (inject `data-spell` into the feature modal)
- Test: `tests/test_web.py` (smoke render) — add a case or extend an existing sheet-render test.

- [ ] **Step 1: Add the failing test**

In `tests/test_web.py` (follow its existing client + saved-character helpers), add a test that builds a character with an innate ability and a spell-granting chosen option, GETs `/character/{id}`, and asserts the response HTML contains the innate ability name and a `data-spell` attribute. If `test_web.py` lacks a convenient saved-character helper, add the test to `tests/test_innate_view.py` using a TestClient instead.

```python
def test_sheet_html_has_innate_and_spell_expander(client_with_innate_char):
    r = client_with_innate_char.get("/character/hero")
    assert r.status_code == 200
    assert "Innate Abilities" in r.text
    assert "data-spell" in r.text
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q -k innate`
Expected: FAIL — markers absent.

- [ ] **Step 3: Implement — feature `<li>`s carry the spell card**

First confirm the `detail_card` macro is imported at the top of `sheet.html` (grep `import.*detail_card` / `from "_detail_card.html"`); the per-item modals already use it, so the import exists. The `{% set %}` block renders the macro to an HTML string, which goes into the `data-spell` attribute the same way `data-text` already carries markdown-rendered HTML (autoescaped in, `innerHTML`-decoded by the overlay JS).

In `aose/web/templates/sheet.html`, update both feature loops (race + class):

```html
{% for f in sheet.race_features %}
{% set spell_html %}{% if f.spell_detail %}{{ detail_card(f.spell_detail) }}{% endif %}{% endset %}
<li class="info" data-modal="modal-feature" data-title="{{ f.name }}"
    data-text="{{ f.text | markdown }}"{% if f.spell_detail %} data-spell="{{ spell_html }}"{% endif %}>
  <span>{{ f.name }}</span>
  <span class="src">{{ f.source | replace("Race: ", "") }}</span>
</li>
{% endfor %}
{% for f in sheet.class_features %}
{% set spell_html %}{% if f.spell_detail %}{{ detail_card(f.spell_detail) }}{% endif %}{% endset %}
<li class="info" data-modal="modal-feature" data-title="{{ f.name }}"
    data-text="{{ f.text | markdown }}"{% if f.spell_detail %} data-spell="{{ spell_html }}"{% endif %}>
  <span>{{ f.name }}</span>
  <span class="src">{{ f.source | replace("Class: ", "") }}</span>
</li>
{% endfor %}
```

- [ ] **Step 4: Implement — feature modal gets a spell slot**

Update the `modal-feature` overlay:

```html
{# MODAL: feature / item detail #}
<div class="overlay modal" id="modal-feature" role="dialog" aria-label="Detail">
  <div class="ov-head"><h3 data-role="title">Detail</h3><button class="x" data-close>×</button></div>
  <div class="ov-body">
    <p data-role="text" style="font-size:15px;margin:0"></p>
    <details data-role="spell" style="margin-top:10px;display:none">
      <summary>Spell details</summary>
      <div data-role="spell-body" style="margin-top:6px"></div>
    </details>
  </div>
</div>
```

- [ ] **Step 5: Implement — overlay JS injects `data-spell`**

In `aose/web/static/sheet_overlays.js`, find where the feature modal is populated from `data-title` / `data-text` (the handler that reads `data-modal`). After it sets the text, add handling for the spell slot. Read the existing handler and add:

```javascript
// inside the data-modal open handler, after setting title/text:
const spellHtml = trigger.getAttribute('data-spell');
const spellEl = modal.querySelector('[data-role="spell"]');
if (spellEl) {
  if (spellHtml) {
    modal.querySelector('[data-role="spell-body"]').innerHTML = spellHtml;
    spellEl.style.display = '';
    spellEl.open = false;
  } else {
    spellEl.style.display = 'none';
    modal.querySelector('[data-role="spell-body"]').innerHTML = '';
  }
}
```

> Match the existing variable names in the file (the trigger element and `modal` reference). The working tree already has uncommitted edits to this file — keep this change additive and don't clobber them.

- [ ] **Step 6: Implement — innate section on the sheet**

In `aose/web/templates/sheet.html`, in the column that holds Mental Powers (column 3 — search for `sheet.mental_powers`), add an innate block guarded by `{% if sheet.innate_abilities %}`:

```html
{% if sheet.innate_abilities %}
<section class="group">
  <div class="bar">Innate Abilities</div>
  <div class="gbody scroll" style="max-height:240px">
    <ul class="feat-list">
      {% for ab in sheet.innate_abilities %}
      {% set ab_spell_html %}{% if ab.spell_detail %}{{ detail_card(ab.spell_detail) }}{% endif %}{% endset %}
      <li class="info" data-modal="modal-feature" data-title="{{ ab.name }}"
          data-text="{{ ab.text | markdown }}"{% if ab.spell_detail %} data-spell="{{ ab_spell_html }}"{% endif %}>
        <span>{{ ab.name }} <span class="muted small">({{ ab.remaining }}/{{ ab.max_uses }})</span></span>
        <span class="row-actions">
          <form method="post" action="/character/{{ char_id }}/innate/spend" class="inline-form">
            <input type="hidden" name="ability_id" value="{{ ab.id }}">
            <button type="submit" {% if ab.remaining == 0 %}disabled{% endif %}>Use</button>
          </form>
          <form method="post" action="/character/{{ char_id }}/innate/restore" class="inline-form">
            <input type="hidden" name="ability_id" value="{{ ab.id }}">
            <button type="submit" {% if ab.used == 0 %}disabled{% endif %}>+1</button>
          </form>
        </span>
      </li>
      {% endfor %}
    </ul>
  </div>
</section>
{% endif %}
```

> Confirm the template variable for the character id (grep `char_id` / `character_id` in `sheet.html`) and use the actual name. Confirm the column-3 open condition includes innate: search for `sheet.spellbook or sheet.mental_powers` and extend it to `... or sheet.mental_powers or sheet.innate_abilities` so the column renders for a non-caster with innate abilities.

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py tests/test_innate_view.py -q`
Expected: PASS.

- [ ] **Step 8: Manual smoke (visual)**

Start the app (`.venv\Scripts\python.exe -m uvicorn aose.web.app:app --reload`), open a character with an innate ability, click a feature with a spell — confirm the modal shows the "Spell details" expander; click "Use" — confirm the counter decrements.

- [ ] **Step 9: Commit**

```bash
git add aose/web/templates/sheet.html aose/web/static/sheet_overlays.js tests/test_web.py tests/test_innate_view.py
git commit -m "feat(sheet): innate-abilities section + feature-modal spell expander"
```

---

## Phase 5 — Wizard: feature-choice picker in Class Setup

### Task 10: `aose/engine/feature_choices.py` — roll + validate

**Files:**
- Create: `aose/engine/feature_choices.py`
- Test: `tests/test_feature_choice_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_feature_choice_engine.py
import random

import pytest

from aose.engine.feature_choices import ChoiceError, roll_choice, validate_choice
from aose.models import ChoiceOption, FeatureChoice


def _grp(pick=2):
    return FeatureChoice(id="g", name="G", pick=pick, options=[
        ChoiceOption(id="a", name="A"), ChoiceOption(id="b", name="B"),
        ChoiceOption(id="c", name="C"),
    ])


def test_roll_returns_distinct_pick_count():
    rng = random.Random(1)
    chosen = roll_choice(_grp(2), rng)
    assert len(chosen) == 2
    assert len(set(chosen)) == 2
    assert set(chosen) <= {"a", "b", "c"}


def test_roll_caps_at_option_count():
    chosen = roll_choice(_grp(pick=5), random.Random(0))
    assert len(chosen) == 3


def test_validate_ok():
    validate_choice(_grp(2), ["a", "b"])   # no raise


def test_validate_wrong_count():
    with pytest.raises(ChoiceError):
        validate_choice(_grp(2), ["a"])


def test_validate_duplicate():
    with pytest.raises(ChoiceError):
        validate_choice(_grp(2), ["a", "a"])


def test_validate_unknown_id():
    with pytest.raises(ChoiceError):
        validate_choice(_grp(2), ["a", "z"])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_choice_engine.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# aose/engine/feature_choices.py
"""Rolling and validating CC3 feature choices. Cycle-free: imports ``random``
and the choice models only."""
import random as _random

from aose.models import FeatureChoice


class ChoiceError(Exception):
    """Raised when a submitted choice is invalid (wrong count, duplicate, or an
    unknown option id)."""


def roll_choice(group: FeatureChoice, rng: _random.Random | None = None) -> list[str]:
    """Pick ``group.pick`` *distinct* option ids uniformly (re-roll duplicates is
    inherent — ``sample`` never repeats). Caps at the number of options."""
    _rng = rng or _random.Random()
    ids = [o.id for o in group.options]
    k = min(group.pick, len(ids))
    return _rng.sample(ids, k)


def validate_choice(group: FeatureChoice, chosen: list[str]) -> None:
    """Raise ``ChoiceError`` unless ``chosen`` is exactly ``pick`` distinct,
    valid option ids."""
    ids = {o.id for o in group.options}
    if len(chosen) != group.pick:
        raise ChoiceError(
            f"{group.name}: choose exactly {group.pick} (got {len(chosen)})."
        )
    if len(set(chosen)) != len(chosen):
        raise ChoiceError(f"{group.name}: choices must be distinct.")
    bad = [c for c in chosen if c not in ids]
    if bad:
        raise ChoiceError(f"{group.name}: unknown option(s) {bad}.")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_feature_choice_engine.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add aose/engine/feature_choices.py tests/test_feature_choice_engine.py
git commit -m "feat(engine): roll/validate feature choices"
```

---

### Task 11: Wizard — active-groups helper + draft wiring

**Files:**
- Modify: `aose/web/wizard.py`
- Test: `tests/test_wizard_feature_choices.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wizard_feature_choices.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aose.characters import load_draft, save_draft
from aose.models import RuleSet
from aose.web.app import create_app

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _client(tmp_path):
    app = create_app(
        data_dir=DATA_DIR,
        characters_dir=tmp_path / "characters",
        drafts_dir=tmp_path / "drafts",
        examples_dir=tmp_path / "examples",
        settings_path=tmp_path / "settings.json",
        seed_from_examples=False,
    )
    return TestClient(app), tmp_path / "drafts"


def _seed_mutoid_draft(drafts_dir, strict=True):
    """A race-as-class Mutoid draft sitting at class_setup, HP already rolled."""
    draft = {
        "ruleset": RuleSet(separate_race_class=False, weapon_proficiency=False,
                           strict_mode=strict, secondary_skills=False).model_dump(),
        "abilities": {"STR": 10, "INT": 10, "WIS": 10, "DEX": 12, "CON": 10, "CHA": 10},
        "abilities_confirmed": True,
        "race_id": "mutoid",
        "class_id": "mutoid",
        "ability_adjustments": {},
        "hp_roll": 4,
    }
    save_draft("d1", draft, drafts_dir)
    return "d1"


def test_strict_autorolls_and_locks_choices(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=True)
    r = client.get(f"/wizard/{draft_id}/class_setup")
    assert r.status_code == 200
    draft = load_draft(draft_id, drafts_dir)
    assert "mutations" in draft["feature_choices"]
    assert len(draft["feature_choices"]["mutations"]) == 2
    assert len(set(draft["feature_choices"]["mutations"])) == 2
```

> This test depends on the Mutoid content (Phase 6). If executing strictly in order, mark it `@pytest.mark.xfail(reason="content lands in Phase 6")` until Task 14, then remove the marker. Alternatively run Phase 6 before Phase 5's integration tests.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py -q`
Expected: FAIL (no `feature_choices` on draft / Mutoid not present yet).

- [ ] **Step 3: Implement — helpers + context + auto-roll**

In `aose/web/wizard.py`:

Add imports near the other engine imports:

```python
from aose.engine.feature_choices import ChoiceError, roll_choice, validate_choice
```

Add a helper to gather active groups (place near `_proficiency_context`):

```python
def _active_choice_groups(draft: dict[str, Any], data) -> list:
    """The FeatureChoice groups that apply to this draft: each picked class's
    groups, plus the race's groups in separate-race-class mode. Mirrors
    iter_reached: in race-as-class mode the race groups don't apply (the
    race-locked class carries them)."""
    rs = _ruleset_of(draft)
    groups = []
    for cid in _class_ids(draft):
        cls = data.classes.get(cid)
        if cls is not None:
            groups.extend(cls.feature_choices)
    if rs.separate_race_class:
        race = data.races.get(draft.get("race_id"))
        if race is not None:
            groups.extend(race.feature_choices)
    return groups


def _feature_choices_context(draft: dict[str, Any], data) -> dict:
    """Render rows for the Features section; auto-roll + lock under Strict Mode on
    first visit (mirrors secondary skills)."""
    groups = _active_choice_groups(draft, data)
    rs = _ruleset_of(draft)
    chosen_map = draft.get("feature_choices", {})

    # Strict: auto-roll every not-yet-chosen group on first GET, then lock.
    if rs.strict_mode and groups:
        changed = False
        for g in groups:
            if g.id not in chosen_map:
                chosen_map = dict(chosen_map)
                chosen_map[g.id] = roll_choice(g)
                changed = True
        if changed:
            draft["feature_choices"] = chosen_map
        draft["feature_choices_done"] = True   # rolled set is the locked choice

    rows = []
    for g in groups:
        chosen = set(chosen_map.get(g.id, []))
        rows.append({
            "id": g.id, "name": g.name, "text": g.text, "pick": g.pick,
            "cosmetic": g.cosmetic, "roll_dice": g.roll_dice,
            "options": [
                {"id": o.id, "name": o.name, "text": o.text,
                 "selected": o.id in chosen}
                for o in g.options
            ],
        })
    return {
        "feature_groups": rows,
        "feature_choices_locked": rs.strict_mode,
        "has_feature_choices": bool(groups),
    }
```

**Clear helpers** — in `_clear_after_abilities`, `_clear_after_race`, and `_clear_after_class`, add `"feature_choices"`, `"feature_choices_done"`, and `"_has_feature_choices"` to each tuple of keys popped, so a race/class change discards stale picks and their flags.

**Completion gate** — `_class_setup_complete(draft)` takes only `draft` (no `data`), so "are all groups chosen?" is gated on a stored flag rather than re-deriving the groups. The Strict auto-roll (in `_feature_choices_context`) and the Features POST both set `draft["feature_choices_done"] = True`; `post_class` records whether any groups exist. Make these three edits:

- In `post_class`, immediately after `_set_spellcasting_flag(draft, data)`:

```python
    draft["_has_feature_choices"] = bool(_active_choice_groups(draft, data))
```

- In `_class_setup_complete`, add this check immediately before the final `return True`:

```python
    if draft.get("_has_feature_choices") and not draft.get("feature_choices_done"):
        return False
```

- The `_feature_choices_context` body (Step 3 above) already sets `draft["feature_choices_done"] = True` inside the Strict auto-roll branch — confirm that line is present (add `if rs.strict_mode and groups: draft["feature_choices_done"] = True` at the end of the Strict block if you simplified it out).

- [ ] **Step 4: Implement — render in get_class_setup**

In `get_class_setup`, after the spell section context, add:

```python
    ctx.update(_feature_choices_context(draft, data))
    ctx["features_done"] = (not ctx["has_feature_choices"]) or bool(draft.get("feature_choices_done"))
```

And ensure `ctx["ready"] = _class_setup_complete(draft)` stays the last line (it already is) — the auto-roll inside `_feature_choices_context` runs before it. Save the draft at the end of the GET if Strict auto-roll changed it: after building `ctx`, add `save_draft(draft_id, draft, _drafts_dir(request))` (the proficiency GET path doesn't currently save; the auto-roll requires it — add a guarded save).

- [ ] **Step 5: Implement — POST /feature-choices**

Add a route near `post_proficiencies`:

```python
@router.post("/{draft_id}/feature-choices")
async def post_feature_choices(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    if _ruleset_of(draft).strict_mode:
        raise HTTPException(400, "Feature choices are locked in Strict Mode.")
    form = await request.form()
    groups = _active_choice_groups(draft, data)
    chosen_map: dict[str, list[str]] = {}
    for g in groups:
        picked = list(dict.fromkeys(form.getlist(f"choice_{g.id}")))
        try:
            validate_choice(g, picked)
        except ChoiceError as e:
            raise HTTPException(400, str(e))
        chosen_map[g.id] = picked
    draft["feature_choices"] = chosen_map
    draft["feature_choices_done"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")
```

- [ ] **Step 6: Implement — carry onto the spec**

In `_draft_to_spec`, add to the `CharacterSpec(...)` constructor:

```python
        feature_choices=dict(draft.get("feature_choices", {})),
```

- [ ] **Step 7: Run to verify pass** (after Phase 6 content exists, or with xfail removed)

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/web/wizard.py tests/test_wizard_feature_choices.py
git commit -m "feat(wizard): feature-choice section in class setup (roll/lock/validate)"
```

---

### Task 12: Wizard template — Features section

**Files:**
- Modify: `aose/web/templates/wizard/class_setup.html`
- Test: covered by Task 11 + a non-strict pick test below.

- [ ] **Step 1: Add the failing non-strict test**

Append to `tests/test_wizard_feature_choices.py`:

```python
def test_non_strict_pick_persists(tmp_path):
    client, drafts_dir = _client(tmp_path)
    draft_id = _seed_mutoid_draft(drafts_dir, strict=False)
    client.get(f"/wizard/{draft_id}/class_setup")
    r = client.post(f"/wizard/{draft_id}/feature-choices",
                    data=[("choice_mutations", "scales"), ("choice_mutations", "clawed_hand")])
    assert r.status_code in (200, 303)
    draft = load_draft(draft_id, drafts_dir)
    assert set(draft["feature_choices"]["mutations"]) == {"scales", "clawed_hand"}
    assert draft["feature_choices_done"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py::test_non_strict_pick_persists -q`
Expected: FAIL — no form renders the choices (POST has nothing to bind) / option ids absent until content + template exist.

- [ ] **Step 3: Implement — template section**

In `aose/web/templates/wizard/class_setup.html`, add a Features section between the Spells section and the Continue form:

```html
{# ── Feature Choices (CC3) ──────────────────────────────────────────────── #}
{% if has_feature_choices %}
<section class="class-setup-section">
    <h3>Features</h3>
    {% if feature_choices_locked %}
    <p class="muted small">Your features were rolled and are locked (Strict Mode).</p>
    {% for g in feature_groups %}
    <div class="feature-group">
        <h4>{{ g.name }}</h4>
        <ul>
            {% for o in g.options if o.selected %}
            <li><strong>{{ o.name }}</strong>{% if o.text %} — <span class="muted small">{{ o.text }}</span>{% endif %}</li>
            {% endfor %}
        </ul>
    </div>
    {% endfor %}
    {% else %}
    <form method="post" action="/wizard/{{ draft_id }}/feature-choices" class="step-form">
        {% for g in feature_groups %}
        <div class="feature-group" data-required="{{ g.pick }}">
            <h4>{{ g.name }}{% if g.cosmetic %} <span class="muted small">(cosmetic)</span>{% endif %}</h4>
            {% if g.text %}<p class="muted small">{{ g.text }}</p>{% endif %}
            <p class="muted small">Choose <strong>{{ g.pick }}</strong>.</p>
            <div class="card-grid" data-required="{{ g.pick }}">
                {% for o in g.options %}
                <label class="card {% if o.selected %}selected{% endif %}">
                    <input type="checkbox" name="choice_{{ g.id }}" value="{{ o.id }}"
                           class="choice-checkbox" {% if o.selected %}checked{% endif %}>
                    <div class="card-name">{{ o.name }}</div>
                    {% if o.text %}<div class="card-detail small">{{ o.text }}</div>{% endif %}
                </label>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
        <button type="submit">Save features</button>
    </form>
    <script>
        (function () {
            document.querySelectorAll('.feature-group .card-grid[data-required]').forEach(function (grid) {
                const required = parseInt(grid.dataset.required, 10);
                const boxes = Array.from(grid.querySelectorAll('.choice-checkbox'));
                function update() {
                    const checked = boxes.filter(b => b.checked).length;
                    boxes.forEach(function (b) {
                        b.disabled = !b.checked && checked >= required;
                        b.closest('.card').classList.toggle('selected', b.checked);
                    });
                }
                boxes.forEach(b => b.addEventListener('change', update));
                update();
            });
        })();
    </script>
    {% endif %}
</section>
{% endif %}
```

- [ ] **Step 4: Run to verify pass** (requires Phase 6 content)

Run: `.venv\Scripts\python.exe -m pytest tests/test_wizard_feature_choices.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/templates/wizard/class_setup.html tests/test_wizard_feature_choices.py
git commit -m "feat(wizard): Features picker template in class setup"
```

---

## Phase 6 — Content (`source: carcass_crawler_3`)

> Feature `text` below is concise/paraphrased from the CC3 source the user provided; transcribe the full book wording from that document when authoring. Progression numbers are exact from the extract's tables. After each file, run the loader test in Task 15 to validate.

### Task 13: Class files — Beast Master, Dragonborn, Mutoid

**Files:**
- Create: `data/classes/beast_master.yaml`, `data/classes/dragonborn.yaml`, `data/classes/mutoid.yaml`
- Test: Task 15 loader test.

- [ ] **Step 1: Create `data/classes/beast_master.yaml`**

```yaml
id: beast_master
name: Beast Master
source: carcass_crawler_3
prime_requisites:
- STR
- WIS
max_level: 14
hit_die: 1d6
name_level: 9
hp_after_name_level: 2
weapons_allowed: all
armor_allowed:
- leather
- chainmail
shields_allowed: true
progression:
  1: {xp_required: 0, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 16}}
  2: {xp_required: 1800, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 16}}
  3: {xp_required: 3600, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 16}}
  4: {xp_required: 7250, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 16}}
  5: {xp_required: 15000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 14}}
  6: {xp_required: 30000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 14}}
  7: {xp_required: 60000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 14}}
  8: {xp_required: 120000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 14}}
  9: {xp_required: 240000, thac0: 14, saves: {death: 7, wands: 8, paralysis: 8, breath: 11, spells: 12}}
  10: {xp_required: 360000, thac0: 14, saves: {death: 7, wands: 8, paralysis: 8, breath: 11, spells: 12}}
  11: {xp_required: 480000, thac0: 14, saves: {death: 7, wands: 8, paralysis: 8, breath: 11, spells: 12}}
  12: {xp_required: 600000, thac0: 14, saves: {death: 7, wands: 8, paralysis: 8, breath: 11, spells: 12}}
  13: {xp_required: 720000, thac0: 12, saves: {death: 5, wands: 6, paralysis: 6, breath: 9, spells: 10}}
  14: {xp_required: 840000, thac0: 12, saves: {death: 5, wands: 6, paralysis: 6, breath: 9, spells: 10}}
features:
- id: animal_companions
  name: Animal Companions
  text: |-
    A beast master may forge a bond with an encountered animal (approach peacefully; the referee makes a reaction roll — 8+ succeeds). Up to one companion per level; total companion Hit Dice may not exceed the beast master's level.
  gained_at_level: 1
- id: clairvoyance
  name: Clairvoyance
  text: |-
    From 5th level, the beast master can see through the eyes of their animal companions, wherever they are, through deep concentration.
  gained_at_level: 5
- id: identify_tracks
  name: Identify Tracks
  text: |-
    A beast master can identify the tracks and spoor of animals in the wild.
  gained_at_level: 1
- id: reaction_modifier
  name: Reaction Modifier
  text: |-
    +1 bonus to reaction rolls when interacting with animals (in addition to CHA modifier).
  gained_at_level: 1
- id: speak_with_animals
  name: Speak with Animals
  text: |-
    Animals understand the basic meaning of the beast master's words. From 2nd level, the beast master also understands animal speech; from 4th level, empathic communication with animals in sight, without words.
  gained_at_level: 1
- id: after_reaching_9th_level
  name: After Reaching 9th Level
  text: |-
    A beast master may build a wilderness stronghold; animals within 5 miles become friends, warning of intruders and carrying messages.
  gained_at_level: 9
```

- [ ] **Step 2: Create `data/classes/dragonborn.yaml`**

```yaml
id: dragonborn
name: Dragonborn
source: carcass_crawler_3
prime_requisites:
- STR
ability_requirements:
  CON: 9
  INT: 9
max_level: 10
hit_die: 1d8
name_level: 9
hp_after_name_level: 2
weapons_allowed: all
armor_allowed: all
shields_allowed: true
race_locked: dragonborn
languages:
- common
- dragon
progression:
  1: {xp_required: 0, thac0: 19, saves: {death: 12, wands: 13, paralysis: 14, breath: 13, spells: 16}}
  2: {xp_required: 3000, thac0: 19, saves: {death: 12, wands: 13, paralysis: 14, breath: 13, spells: 16}}
  3: {xp_required: 6000, thac0: 19, saves: {death: 12, wands: 13, paralysis: 14, breath: 13, spells: 16}}
  4: {xp_required: 12000, thac0: 17, saves: {death: 10, wands: 11, paralysis: 12, breath: 11, spells: 14}}
  5: {xp_required: 24000, thac0: 17, saves: {death: 10, wands: 11, paralysis: 12, breath: 11, spells: 14}}
  6: {xp_required: 45000, thac0: 17, saves: {death: 10, wands: 11, paralysis: 12, breath: 11, spells: 14}}
  7: {xp_required: 95000, thac0: 14, saves: {death: 8, wands: 9, paralysis: 10, breath: 8, spells: 12}}
  8: {xp_required: 175000, thac0: 14, saves: {death: 8, wands: 9, paralysis: 10, breath: 8, spells: 12}}
  9: {xp_required: 350000, thac0: 14, saves: {death: 8, wands: 9, paralysis: 10, breath: 8, spells: 12}}
  10: {xp_required: 500000, thac0: 12, saves: {death: 6, wands: 7, paralysis: 8, breath: 6, spells: 10}}
features:
- id: breath_weapon
  name: Breath Weapon
  text: |-
    Up to 3 times per day, exhale a breath weapon. All in the area take damage equal to half the dragonborn's current hit points (round up); save versus breath for half. Shape and damage type depend on Draconic Bloodline.
  gained_at_level: 1
  daily_uses:
    per_day: 3
- id: scales
  name: Scales
  text: |-
    A dragonborn's scaly skin grants a natural +1 bonus to Armour Class.
  gained_at_level: 1
  granted_modifiers:
  - {target: ac, op: add, value: 1}
- id: draconic_resistance
  name: Draconic Resistance
  text: |-
    +2 bonus to saving throws against the damage type of the dragonborn's breath weapon (see Draconic Bloodline).
  gained_at_level: 1
- id: dragon_affecting_magic
  name: Dragon-Affecting Magic
  text: |-
    Dragonborn are affected by magic that specifically targets dragons (e.g. a sword +1, +3 vs dragons).
  gained_at_level: 1
- id: dragon_affinity
  name: Dragon Affinity
  text: |-
    +1 bonus to reaction rolls when encountering dragons.
  gained_at_level: 1
- id: after_reaching_9th_level
  name: After Reaching 9th Level
  text: |-
    A dragonborn may create a stronghold that attracts dragonborn of the same clan. A dragonborn ruler may only hire dragonborn mercenaries; specialists and retainers of any race may be hired.
  gained_at_level: 9
feature_choices:
- id: draconic_bloodline
  name: Draconic Bloodline
  text: Roll d10 (or choose) to determine your draconic affinity — breath shape, damage type, and scale colour.
  pick: 1
  roll_dice: d10
  options:
  - id: black
    name: Black (Acid)
    text: "Acid breath in a line (5' wide, 30' long). +2 vs acid."
    granted_modifiers:
    - {target: "save:vs:acid", op: add, value: 2}
  - id: blue
    name: Blue (Lightning)
    text: "Lightning breath in a line (5' wide, 30' long). +2 vs lightning."
    granted_modifiers:
    - {target: "save:vs:lightning", op: add, value: 2}
  - id: green
    name: Green (Poison)
    text: "Poison breath in a cloud (10' wide, 15' long). +2 vs poison."
    granted_modifiers:
    - {target: "save:vs:poison", op: add, value: 2}
  - id: red
    name: Red (Fire)
    text: "Fire breath in a cone (15' wide at the far end, 20' long). +2 vs fire."
    granted_modifiers:
    - {target: "save:vs:fire", op: add, value: 2}
  - id: white
    name: White (Cold)
    text: "Cold breath in a cone (15' wide at the far end, 20' long). +2 vs cold."
    granted_modifiers:
    - {target: "save:vs:cold", op: add, value: 2}
```

- [ ] **Step 3: Create `data/classes/mutoid.yaml`**

```yaml
id: mutoid
name: Mutoid
source: carcass_crawler_3
prime_requisites:
- DEX
max_level: 8
hit_die: 1d6
name_level: 9
hp_after_name_level: 0
weapons_allowed: all
armor_allowed:
- leather
shields_allowed: true
race_locked: mutoid
progression:
  1: {xp_required: 0, thac0: 19, saves: {death: 10, wands: 11, paralysis: 12, breath: 13, spells: 14}}
  2: {xp_required: 1750, thac0: 19, saves: {death: 10, wands: 11, paralysis: 12, breath: 13, spells: 14}}
  3: {xp_required: 3500, thac0: 19, saves: {death: 10, wands: 11, paralysis: 12, breath: 13, spells: 14}}
  4: {xp_required: 7000, thac0: 19, saves: {death: 10, wands: 11, paralysis: 12, breath: 13, spells: 14}}
  5: {xp_required: 14000, thac0: 17, saves: {death: 8, wands: 9, paralysis: 10, breath: 11, spells: 12}}
  6: {xp_required: 30000, thac0: 17, saves: {death: 8, wands: 9, paralysis: 10, breath: 11, spells: 12}}
  7: {xp_required: 60000, thac0: 17, saves: {death: 8, wands: 9, paralysis: 10, breath: 11, spells: 12}}
  8: {xp_required: 120000, thac0: 17, saves: {death: 8, wands: 9, paralysis: 10, breath: 11, spells: 12}}
features:
- id: combat
  name: Combat
  text: |-
    Mutoids can use shields, but their need for stealth prevents armour heavier than leather. They may use any one-handed melee weapon and all missile weapons.
  gained_at_level: 1
- id: back_stab
  name: Back-Stab
  text: |-
    Attacking an unaware opponent from behind grants +4 to hit and doubles damage dealt.
  gained_at_level: 1
- id: mutoid_skills
  name: Mutoid Skills
  text: |-
    Mutoids use the skills Hide in Shadows, Mimicry, Move Silently, and Pick Pockets (percentage chances by level — see the Carcass Crawler 3 table). All rolled on d% (roll ≤ chance succeeds).
  gained_at_level: 1
- id: after_reaching_8th_level
  name: After Reaching 8th Level
  text: |-
    A mutoid can establish a secret lair, attracting 2d6 apprentices (1st level mutoids) who serve with some reliability.
  gained_at_level: 8
feature_choices:
- id: mutations
  name: Mutations
  text: Roll twice (or choose two) on the d8 Mutations table. Two attack mutations may both be used each round.
  pick: 2
  roll_dice: d8
  options:
  - id: beast_ears
    name: Beast Ears
    text: "3-in-6 chance to hear noises."
  - id: beast_eyes
    name: Beast Eyes
    text: "Infravision to 60'."
  - id: clawed_hand
    name: Clawed Hand
    text: "Unarmed attack for 1d6 damage."
    mechanical:
      weapon: {name: Clawed Hand, damage: 1d6, melee: true}
  - id: gills
    name: Gills
    text: "Breathe underwater."
  - id: pincer
    name: Pincer
    text: "Unarmed attack for 1d3 damage; the pincer locks on, dealing 1d3/round (save versus paralysis to escape)."
    mechanical:
      weapon: {name: Pincer, damage: 1d3, melee: true}
  - id: scales
    name: Scales
    text: "+2 bonus to Armour Class."
    granted_modifiers:
    - {target: ac, op: add, value: 2}
  - id: spring_legs
    name: Spring Legs
    text: "Jump up to 30' forward and gain +1 to attack; with an impaling weapon this counts as a charge (double damage)."
  - id: sticky_tongue
    name: Sticky Tongue
    text: "Grab an object up to 15' away; usable as a melee bite attack for 1d3 damage."
    mechanical:
      weapon: {name: Sticky Tongue, damage: 1d3, melee: true}
```

- [ ] **Step 4: Commit**

```bash
git add data/classes/beast_master.yaml data/classes/dragonborn.yaml data/classes/mutoid.yaml
git commit -m "feat(content): CC3 Beast Master, Dragonborn, Mutoid classes"
```

---

### Task 14: Class files — Mycelian, Tiefling

**Files:**
- Create: `data/classes/mycelian.yaml`, `data/classes/tiefling.yaml`

- [ ] **Step 1: Create `data/classes/mycelian.yaml`**

```yaml
id: mycelian
name: Mycelian
source: carcass_crawler_3
prime_requisites:
- STR
ability_requirements:
  CON: 9
max_level: 6
hit_die: 1d8
name_level: 9
hp_after_name_level: 0
weapons_allowed: all
armor_allowed: []
shields_allowed: true
race_locked: mycelian
languages:
- common
- deepcommon
progression:
  1: {xp_required: 0, thac0: 19, saves: {death: 9, wands: 11, paralysis: 9, breath: 13, spells: 12}}
  2: {xp_required: 3000, thac0: 19, saves: {death: 9, wands: 11, paralysis: 9, breath: 13, spells: 12}}
  3: {xp_required: 6000, thac0: 19, saves: {death: 9, wands: 11, paralysis: 9, breath: 13, spells: 12}}
  4: {xp_required: 12000, thac0: 17, saves: {death: 7, wands: 9, paralysis: 7, breath: 11, spells: 10}}
  5: {xp_required: 24000, thac0: 17, saves: {death: 7, wands: 9, paralysis: 7, breath: 11, spells: 10}}
  6: {xp_required: 45000, thac0: 17, saves: {death: 7, wands: 9, paralysis: 7, breath: 11, spells: 10}}
features:
- id: combat
  name: Combat
  text: |-
    Mycelians have naturally tough skin and do not wear armour. They may use shields and any kind of weapon.
  gained_at_level: 1
- id: natural_armour
  name: Natural Armour Class
  text: |-
    A mycelian's tough skin grants a natural Armour Class that improves with level: 6 [13] at L1, 5 [14] at L2, 4 [15] at L3, 3 [16] from L4. A shield's bonus applies on top.
  gained_at_level: 1
  granted_modifiers:
  - target: ac
    op: set
    scale:
      by: level
      table: {1: 6, 2: 5, 3: 4, 4: 3}
- id: fists
  name: Fists
  text: |-
    A mycelian may make one melee attack per round with its club-like fists, dealing 1d4 damage per level.
  gained_at_level: 1
  mechanical:
    weapon: {name: Fists, melee: true, damage_per_level_die: d4}
- id: fungal_spores
  name: Fungal Spores
  text: |-
    Once per day per level, spray spores at a single living target within 20'. Pacifying spores: save versus poison or be passive for 1 round/level. From 4th level, hallucinogenic spores (save versus poison or terrifying visions for 1 turn).
  gained_at_level: 1
  daily_uses:
    scales_with_level: true
- id: infravision
  name: Infravision
  text: |-
    Mycelians have infravision to 60'.
  gained_at_level: 1
  mechanical:
    infravision_feet: 60
- id: light_sensitivity
  name: Light Sensitivity
  text: |-
    In bright light (daylight, continual light), mycelians suffer −2 to attack rolls and −1 to Armour Class.
  gained_at_level: 1
  granted_modifiers:
  - {target: ac, op: add, value: -1, condition: bright_light}
  - {target: attack, op: add, value: -2, condition: bright_light}
- id: telepathic_communication
  name: Telepathic Communication
  text: |-
    Mouthless mycelians communicate telepathically with any sentient creature within 120' that they can perceive, in any language they know.
  gained_at_level: 1
- id: growth
  name: Growth
  text: |-
    A mycelian is 4' tall at 1st level, gaining 1' per level to a maximum of 9' at 6th level.
  gained_at_level: 1
- id: rest_and_sustenance
  name: Rest and Sustenance
  text: |-
    Mycelians do not eat or sleep; they require 8 hours per day in contact with moist earth or lose 1 hit point per day until they do.
  gained_at_level: 1
- id: after_reaching_6th_level
  name: After Reaching 6th Level
  text: |-
    A mycelian may found a subterranean stronghold, ruling over mycelians who gather there. A mycelian liege can reanimate humanoid corpses as fungal zombies under its control.
  gained_at_level: 6
```

- [ ] **Step 2: Create `data/classes/tiefling.yaml`**

```yaml
id: tiefling
name: Tiefling
source: carcass_crawler_3
prime_requisites:
- CHA
- DEX
ability_requirements:
  INT: 9
max_level: 10
hit_die: 1d6
name_level: 9
hp_after_name_level: 2
weapons_allowed: all
armor_allowed:
- leather
- chainmail
shields_allowed: true
race_locked: tiefling
progression:
  1: {xp_required: 0, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 14}}
  2: {xp_required: 2500, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 14}}
  3: {xp_required: 5000, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 14}}
  4: {xp_required: 10000, thac0: 19, saves: {death: 11, wands: 12, paralysis: 12, breath: 15, spells: 14}}
  5: {xp_required: 20000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 12}}
  6: {xp_required: 30000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 12}}
  7: {xp_required: 60000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 12}}
  8: {xp_required: 120000, thac0: 17, saves: {death: 9, wands: 10, paralysis: 10, breath: 13, spells: 12}}
  9: {xp_required: 240000, thac0: 14, saves: {death: 7, wands: 8, paralysis: 8, breath: 11, spells: 10}}
  10: {xp_required: 360000, thac0: 14, saves: {death: 7, wands: 8, paralysis: 8, breath: 11, spells: 10}}
features:
- id: combat
  name: Combat
  text: |-
    Tieflings can use leather armour or chainmail, shields, and all weapons.
  gained_at_level: 1
- id: holy_water_vulnerability
  name: Holy Water Vulnerability
  text: |-
    A tiefling's fiendish heritage makes them vulnerable to damage by holy water.
  gained_at_level: 1
- id: infravision
  name: Infravision
  text: |-
    Tieflings have infravision to 60'.
  gained_at_level: 1
  mechanical:
    infravision_feet: 60
- id: tiefling_skills
  name: Tiefling Skills
  text: |-
    Tieflings use the skills Beguile, Hear Noise, Hide in Shadows, and Move Silently (chances by level — see the Carcass Crawler 3 table). All except Hear Noise are rolled on d%; Hear Noise on 1d6.
  gained_at_level: 1
- id: after_reaching_9th_level
  name: After Reaching 9th Level
  text: |-
    A tiefling can establish a den, attracting 2d6 apprentices (1st level thieves or tieflings) who serve with some reliability.
  gained_at_level: 9
feature_choices:
- id: fiendish_gifts
  name: Fiendish Gifts
  text: Roll twice (or choose two) on the d10 Fiendish Gifts table — innate magical traits.
  pick: 2
  roll_dice: d10
  options:
  - id: darkness
    name: Darkness
    text: "Cast darkness once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_light
  - id: detect_invisible
    name: Detect Invisible
    text: "Cast detect invisible once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_detect_invisible
  - id: detect_magic
    name: Detect Magic
    text: "Cast detect magic once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_detect_magic
  - id: magic_missile
    name: Magic Missile
    text: "Cast magic missile once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_magic_missile
  - id: mirror_image
    name: Mirror Image
    text: "Cast mirror image once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_mirror_image
  - id: ventriloquism
    name: Ventriloquism
    text: "Cast ventriloquism once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_ventriloquism
  - id: cold_resistance
    name: Cold Resistance
    text: "Take half damage from cold."
  - id: fire_resistance
    name: Fire Resistance
    text: "Take half damage from fire."
  - id: save_paralysis
    name: Resist Paralysis
    text: "+2 bonus to saves versus paralysis."
    granted_modifiers:
    - {target: "save:paralysis", op: add, value: 2}
  - id: save_poison
    name: Resist Poison
    text: "+2 bonus to saves versus poison."
    granted_modifiers:
    - {target: "save:death", op: add, value: 2, condition: poison}
- id: fiendish_appearance
  name: Fiendish Appearance
  text: Roll twice (or choose two) on the d10 Fiendish Appearance table — cosmetic traits.
  pick: 2
  roll_dice: d10
  cosmetic: true
  options:
  - id: digits
    name: Unusual Digits
    text: "3 or 6 digits on each hand."
  - id: dark_eyes
    name: Dark Eyes
    text: "Black or red eyes, no whites or pupils."
  - id: fangs
    name: Fangs
    text: "Fangs or needle-like teeth."
  - id: furred
    name: Furred or Feathered
    text: "Furry or feathered skin."
  - id: forked_tongue
    name: Forked Tongue
    text: "A forked tongue."
  - id: hooves
    name: Hooves
    text: "Goat-like hooves."
  - id: tail
    name: Tail
    text: "A long, thin tail."
  - id: scaly_skin
    name: Scaly Skin
    text: "Scaly or ridged skin."
  - id: tinted_skin
    name: Tinted Skin
    text: "Skin tinted red, green, or blue."
  - id: horns
    name: Horns
    text: "Small horns on the forehead or temples."
```

- [ ] **Step 3: Commit**

```bash
git add data/classes/mycelian.yaml data/classes/tiefling.yaml
git commit -m "feat(content): CC3 Mycelian (level-scaled) and Tiefling classes"
```

---

### Task 15: Race files + content loader test

**Files:**
- Create: `data/races/dragonborn.yaml`, `data/races/mutoid.yaml`, `data/races/mycelian.yaml`, `data/races/tiefling.yaml`
- Test: `tests/test_cc3_races_classes.py`

- [ ] **Step 1: Write the failing loader test**

```python
# tests/test_cc3_races_classes.py
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


CC3_CLASSES = ["beast_master", "dragonborn", "mutoid", "mycelian", "tiefling"]
CC3_RACES = ["dragonborn", "mutoid", "mycelian", "tiefling"]


def test_classes_loaded(data):
    for cid in CC3_CLASSES:
        assert cid in data.classes, cid
        assert data.classes[cid].source == "carcass_crawler_3"


def test_races_loaded(data):
    for rid in CC3_RACES:
        assert rid in data.races, rid
        assert data.races[rid].source == "carcass_crawler_3"


def test_race_as_class_links(data):
    for cid in ["dragonborn", "mutoid", "mycelian", "tiefling"]:
        assert data.classes[cid].race_locked == cid


def test_choice_spell_ids_resolve(data):
    for owner in list(data.classes.values()) + list(data.races.values()):
        for grp in owner.feature_choices:
            for opt in grp.options:
                if opt.spell_id is not None:
                    assert opt.spell_id in data.spells, opt.spell_id


def test_mutoid_has_distinct_pick_two(data):
    grp = {g.id: g for g in data.classes["mutoid"].feature_choices}["mutations"]
    assert grp.pick == 2
    assert len(grp.options) == 8


def test_tiefling_cosmetic_group(data):
    groups = {g.id: g for g in data.classes["tiefling"].feature_choices}
    assert groups["fiendish_appearance"].cosmetic is True
    assert groups["fiendish_gifts"].cosmetic is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_races_classes.py -q`
Expected: FAIL — races not present yet.

- [ ] **Step 3: Create `data/races/dragonborn.yaml`**

```yaml
id: dragonborn
name: Dragonborn
source: carcass_crawler_3
ability_requirements:
  CON: 9
  INT: 9
languages:
- common
- dragon
allowed_classes:
- assassin
- cleric
- fighter
- knight
- illusionist
- paladin
- magic_user
- thief
class_level_caps:
  assassin: 7
  cleric: 8
  fighter: 10
  knight: 10
  illusionist: 6
  paladin: 8
  magic_user: 8
  thief: 6
features:
- id: breath_weapon
  name: Breath Weapon
  text: |-
    Once per day, exhale a breath weapon. All in the area take damage equal to half the dragonborn's current hit points (round up); save versus breath for half. Shape and damage type depend on Draconic Bloodline.
  daily_uses:
    per_day: 1
- id: draconic_resistance
  name: Draconic Resistance
  text: |-
    +2 bonus to saving throws against the damage type of the dragonborn's breath weapon (see Draconic Bloodline).
- id: dragon_affecting_magic
  name: Dragon-Affecting Magic
  text: |-
    Dragonborn are affected by magic that specifically targets dragons (e.g. a sword +1, +3 vs dragons).
feature_choices:
- id: draconic_bloodline
  name: Draconic Bloodline
  text: Roll d10 (or choose) to determine your draconic affinity — breath shape, damage type, and scale colour.
  pick: 1
  roll_dice: d10
  options:
  - id: black
    name: Black (Acid)
    text: "Acid breath in a line (5' wide, 30' long). +2 vs acid."
    granted_modifiers:
    - {target: "save:vs:acid", op: add, value: 2}
  - id: blue
    name: Blue (Lightning)
    text: "Lightning breath in a line (5' wide, 30' long). +2 vs lightning."
    granted_modifiers:
    - {target: "save:vs:lightning", op: add, value: 2}
  - id: green
    name: Green (Poison)
    text: "Poison breath in a cloud (10' wide, 15' long). +2 vs poison."
    granted_modifiers:
    - {target: "save:vs:poison", op: add, value: 2}
  - id: red
    name: Red (Fire)
    text: "Fire breath in a cone (15' wide at the far end, 20' long). +2 vs fire."
    granted_modifiers:
    - {target: "save:vs:fire", op: add, value: 2}
  - id: white
    name: White (Cold)
    text: "Cold breath in a cone (15' wide at the far end, 20' long). +2 vs cold."
    granted_modifiers:
    - {target: "save:vs:cold", op: add, value: 2}
```

- [ ] **Step 4: Create `data/races/mutoid.yaml`**

```yaml
id: mutoid
name: Mutoid
source: carcass_crawler_3
languages:
- common
allowed_classes:
- assassin
- cleric
- fighter
- illusionist
- thief
class_level_caps:
  assassin: 5
  cleric: 6
  fighter: 7
  illusionist: 6
  thief: 9
features:
- id: mutoid_appearance
  name: Mutoid Appearance
  text: |-
    Mutoids have mismatched body parts from many creatures; each individual is unique and is often shunned by other species.
feature_choices:
- id: mutations
  name: Mutations
  text: Roll twice (or choose two) on the d8 Mutations table. Two attack mutations may both be used each round.
  pick: 2
  roll_dice: d8
  options:
  - id: beast_ears
    name: Beast Ears
    text: "3-in-6 chance to hear noises."
  - id: beast_eyes
    name: Beast Eyes
    text: "Infravision to 60'."
  - id: clawed_hand
    name: Clawed Hand
    text: "Unarmed attack for 1d6 damage."
    mechanical:
      weapon: {name: Clawed Hand, damage: 1d6, melee: true}
  - id: gills
    name: Gills
    text: "Breathe underwater."
  - id: pincer
    name: Pincer
    text: "Unarmed attack for 1d3 damage; the pincer locks on, dealing 1d3/round (save versus paralysis to escape)."
    mechanical:
      weapon: {name: Pincer, damage: 1d3, melee: true}
  - id: scales
    name: Scales
    text: "+2 bonus to Armour Class."
    granted_modifiers:
    - {target: ac, op: add, value: 2}
  - id: spring_legs
    name: Spring Legs
    text: "Jump up to 30' forward and gain +1 to attack; with an impaling weapon this counts as a charge (double damage)."
  - id: sticky_tongue
    name: Sticky Tongue
    text: "Grab an object up to 15' away; usable as a melee bite attack for 1d3 damage."
    mechanical:
      weapon: {name: Sticky Tongue, damage: 1d3, melee: true}
```

- [ ] **Step 5: Create `data/races/mycelian.yaml`**

```yaml
id: mycelian
name: Mycelian
source: carcass_crawler_3
ability_requirements:
  CON: 9
ability_modifiers:
  DEX: -1
  WIS: 1
infravision: 60
languages:
- common
- deepcommon
allowed_classes:
- assassin
- cleric
- druid
- fighter
- illusionist
- thief
class_level_caps:
  assassin: 4
  cleric: 5
  druid: 5
  fighter: 6
  illusionist: 4
  thief: 4
features:
- id: ability_modifiers
  name: Ability Modifiers
  text: −1 DEX, +1 WIS.
- id: fungal_spores
  name: Fungal Spores
  text: |-
    From 3rd level, once per day, spray spores at a single living target within 20'. The target must save versus poison or become passive for 1 round per level of the mycelian.
  daily_uses:
    per_day: 1
- id: infravision
  name: Infravision
  text: |-
    Mycelians have infravision to 60'.
  mechanical:
    infravision_feet: 60
- id: light_sensitivity
  name: Light Sensitivity
  text: |-
    In bright light (daylight, continual light), mycelians suffer −2 to attack rolls and −1 to Armour Class.
  granted_modifiers:
  - {target: ac, op: add, value: -1, condition: bright_light}
  - {target: attack, op: add, value: -2, condition: bright_light}
- id: telepathic_communication
  name: Telepathic Communication
  text: |-
    Mycelians communicate telepathically with any sentient creature within 120' that they can perceive, in any language they know.
- id: rest_and_sustenance
  name: Rest and Sustenance
  text: |-
    Mycelians do not eat or sleep; they require 8 hours per day in contact with moist earth or lose 1 hit point per day until they do.
```

> Note: the race-version Fungal Spores is "from 3rd level" — there is no per-race level gate in the data model, so it is modelled as a once/day innate ability with the level gate described in text (race features have no `gained_at_level`). This is an accepted divergence from the class version (which scales per level).

- [ ] **Step 6: Create `data/races/tiefling.yaml`**

```yaml
id: tiefling
name: Tiefling
source: carcass_crawler_3
ability_requirements:
  INT: 9
ability_modifiers:
  DEX: 1
  WIS: -1
infravision: 60
languages:
- common
allowed_classes:
- acrobat
- assassin
- bard
- fighter
- illusionist
- magic_user
- ranger
- thief
class_level_caps:
  acrobat: 10
  assassin: 10
  bard: 6
  fighter: 8
  illusionist: 10
  magic_user: 10
  ranger: 6
  thief: 10
features:
- id: ability_modifiers
  name: Ability Modifiers
  text: +1 DEX, −1 WIS.
- id: holy_water_vulnerability
  name: Holy Water Vulnerability
  text: |-
    A tiefling's fiendish heritage makes them vulnerable to damage by holy water.
- id: infravision
  name: Infravision
  text: |-
    Tieflings have infravision to 60'.
  mechanical:
    infravision_feet: 60
feature_choices:
- id: fiendish_gifts
  name: Fiendish Gifts
  text: Roll twice (or choose two) on the d10 Fiendish Gifts table — innate magical traits.
  pick: 2
  roll_dice: d10
  options:
  - id: darkness
    name: Darkness
    text: "Cast darkness once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_light
  - id: detect_invisible
    name: Detect Invisible
    text: "Cast detect invisible once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_detect_invisible
  - id: detect_magic
    name: Detect Magic
    text: "Cast detect magic once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_detect_magic
  - id: magic_missile
    name: Magic Missile
    text: "Cast magic missile once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_magic_missile
  - id: mirror_image
    name: Mirror Image
    text: "Cast mirror image once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_mirror_image
  - id: ventriloquism
    name: Ventriloquism
    text: "Cast ventriloquism once per day."
    daily_uses: {per_day: 1}
    spell_id: magic_user_ventriloquism
  - id: cold_resistance
    name: Cold Resistance
    text: "Take half damage from cold."
  - id: fire_resistance
    name: Fire Resistance
    text: "Take half damage from fire."
  - id: save_paralysis
    name: Resist Paralysis
    text: "+2 bonus to saves versus paralysis."
    granted_modifiers:
    - {target: "save:paralysis", op: add, value: 2}
  - id: save_poison
    name: Resist Poison
    text: "+2 bonus to saves versus poison."
    granted_modifiers:
    - {target: "save:death", op: add, value: 2, condition: poison}
- id: fiendish_appearance
  name: Fiendish Appearance
  text: Roll twice (or choose two) on the d10 Fiendish Appearance table — cosmetic traits.
  pick: 2
  roll_dice: d10
  cosmetic: true
  options:
  - id: digits
    name: Unusual Digits
    text: "3 or 6 digits on each hand."
  - id: dark_eyes
    name: Dark Eyes
    text: "Black or red eyes, no whites or pupils."
  - id: fangs
    name: Fangs
    text: "Fangs or needle-like teeth."
  - id: furred
    name: Furred or Feathered
    text: "Furry or feathered skin."
  - id: forked_tongue
    name: Forked Tongue
    text: "A forked tongue."
  - id: hooves
    name: Hooves
    text: "Goat-like hooves."
  - id: tail
    name: Tail
    text: "A long, thin tail."
  - id: scaly_skin
    name: Scaly Skin
    text: "Scaly or ridged skin."
  - id: tinted_skin
    name: Tinted Skin
    text: "Skin tinted red, green, or blue."
  - id: horns
    name: Horns
    text: "Small horns on the forehead or temples."
```

- [ ] **Step 7: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_races_classes.py -q`
Expected: PASS (6 passed).

- [ ] **Step 8: Run the full suite + remove any xfail from Task 11/12**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known `pytest-current` PermissionError). Remove the `@pytest.mark.xfail` from the wizard feature-choice tests now that content exists, and re-run `tests/test_wizard_feature_choices.py`.

- [ ] **Step 9: Commit**

```bash
git add data/races/dragonborn.yaml data/races/mutoid.yaml data/races/mycelian.yaml data/races/tiefling.yaml tests/test_cc3_races_classes.py
git commit -m "feat(content): CC3 Dragonborn/Mutoid/Mycelian/Tiefling races + loader tests"
```

---

### Task 16: End-to-end integration tests (creation → sheet)

**Files:**
- Test: `tests/test_cc3_integration.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_cc3_integration.py
from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine.armor_class import armor_class
from aose.engine.attacks import attack_profiles
from aose.engine.saves import situational_save_bonuses
from aose.sheet.view import build_sheet
from aose.models import Ability, CharacterSpec, ClassEntry

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def _spec(class_id, level=1, choices=None):
    return CharacterSpec(
        name="T", abilities={a: 12 for a in Ability}, race_id=class_id,
        alignment="neutral", classes=[ClassEntry(class_id=class_id, level=level)],
        feature_choices=choices or {},
    )


def test_mutoid_scales_grant_ac(data):
    spec = _spec("mutoid", choices={"mutations": ["scales", "clawed_hand"]})
    desc, _asc = armor_class(spec, data)
    base, _ = armor_class(_spec("mutoid", choices={"mutations": ["beast_ears", "gills"]}), data)
    assert desc == base - 2  # +2 AC = 2 lower descending


def test_mutoid_clawed_hand_attack(data):
    spec = _spec("mutoid", choices={"mutations": ["clawed_hand", "gills"]})
    names = [p.name for p in attack_profiles(spec, data)]
    assert "Clawed Hand" in names


def test_mycelian_natural_ac_scales(data):
    l1 = armor_class(_spec("mycelian", level=1), data)[0]
    l4 = armor_class(_spec("mycelian", level=4), data)[0]
    assert l1 == 6 and l4 == 3


def test_mycelian_fist_scales(data):
    spec = _spec("mycelian", level=3)
    fist = next(p for p in attack_profiles(spec, data) if p.name == "Fists")
    assert fist.damage.startswith("3d4")


def test_dragonborn_bloodline_resistance(data):
    spec = _spec("dragonborn", choices={"draconic_bloodline": ["red"]})
    bonuses = situational_save_bonuses(spec, data)
    things = {t.lower() for b in bonuses for t in b.things}   # display names are title-cased
    assert "fire" in things


def test_tiefling_gift_innate_on_sheet(data):
    spec = _spec("tiefling", choices={
        "fiendish_gifts": ["magic_missile", "save_poison"],
        "fiendish_appearance": ["horns", "tail"],
    })
    sheet = build_sheet(spec, data)
    innate_names = [a.name for a in sheet.innate_abilities]
    assert "Magic Missile" in innate_names
    feat_names = [f.name for f in sheet.class_features]
    assert "Resist Poison" in feat_names
    assert "Horns" in feat_names  # cosmetic still shown as a feature
```

> Verify the helper names before running: confirm `situational_save_bonuses` is the correct symbol in `aose/engine/saves.py` (grep `def situational_save_bonuses`) and that `SituationalSaveBonus.things` is the attribute name. Adjust if the codebase uses different names.

- [ ] **Step 2: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cc3_integration.py -q`
Expected: PASS (6 passed).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cc3_integration.py
git commit -m "test(cc3): creation-to-sheet integration coverage"
```

---

## Phase 7 — Docs

### Task 17: Update CHANGELOG, ARCHITECTURE, CLAUDE.md

**Files:**
- Modify: `docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`

- [ ] **Step 1: CHANGELOG row**

Add one line to the top of `docs/CHANGELOG.md` (match the existing row format), e.g.:

```
| 2026-06-10 | CC3 races/classes + feature-choice mechanic & innate abilities | feat/cc3-races-classes | 2026-06-10-cc3-races-and-classes |
```

- [ ] **Step 2: ARCHITECTURE — feature-choice + innate notes**

In `docs/ARCHITECTURE.md`, in the `GrantedModifier` + features section, add a paragraph describing the feature-choice mechanic: `FeatureChoice`/`ChoiceOption` on Race/CharClass, selections on `CharacterSpec.feature_choices`, resolved through `iter_reached` so chosen options reuse `feature_modifiers`/`feature_weapons` (with level threading for Mycelian fist scaling). Near the Mental Powers section, add an innate-abilities note: `aose/engine/innate.py`, `CharacterSpec.innate_uses`, sheet block + `/innate/*` routes, rest reset. Add a "Carcass Crawler 3 content" subsection mirroring the CC1 one (5 classes, 4 races, the choice groups, no new languages).

- [ ] **Step 3: CLAUDE.md — storage shapes**

In the Storage-shapes list of `CLAUDE.md`, add `feature_choices: dict[str, list[str]]` (group id → option ids) and `innate_uses: dict[str, int]` (daily-use counters, reset on rest).

- [ ] **Step 4: Commit**

```bash
git add docs/CHANGELOG.md docs/ARCHITECTURE.md CLAUDE.md
git commit -m "docs(cc3): record feature-choice mechanic, innate abilities, and CC3 content"
```

---

## Final verification

- [ ] Run the full suite: `.venv\Scripts\python.exe -m pytest tests/ -q` — expect all green (ignore the `pytest-current` PermissionError).
- [ ] Manual smoke: create a Mutoid (race-as-class) and a Tiefling-race Fighter through the wizard; confirm the Features section appears in Class Setup, rolls/locks under Strict, and that the resulting sheet shows only chosen options, the innate-abilities block with working Use/+1, and the spell expander on a Fiendish-Gift spell.
- [ ] Finish the branch via the `superpowers:finishing-a-development-branch` skill.
