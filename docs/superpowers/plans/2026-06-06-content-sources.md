# Content Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class content-source concept (name, publisher, core flag), tag all existing data, and let the rules/settings pages filter sources so disabled content disappears from the wizard, shop, spell selection, and enchantment acquisition.

**Architecture:** A `Source` model + `data/sources.yaml` registry loaded into `GameData.sources`. Every content model gains a `source: str` field defaulting to `ose_classic_fantasy`; only Advanced entries are tagged explicitly. `RuleSet.disabled_sources` drives a tiny `source_enabled()` helper applied wherever selectable content is built. The rules and settings pages share `_ruleset_fields.html`, so a single Sources fieldset serves both.

**Tech Stack:** Python 3.14, Pydantic v2, FastAPI, Jinja2, PyYAML, pytest. Windows/PowerShell venv: run tests with `.venv\Scripts\python.exe -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-06-content-sources-design.md`

---

## Reference data (used by Tasks 4–7)

These exact id lists were derived by matching the user's Advanced Fantasy lists against the current data.

**Advanced races** (`data/races/`, 9 files): `drow, duergar, dwarf, elf, gnome, half_elf, half_orc, halfling, svirfneblin`
(only `human` stays Classic.)

**Advanced classes** (`data/classes/`, 15 files): `acrobat, assassin, barbarian, bard, drow, druid, duergar, gnome, half_elf, half_orc, illusionist, knight, paladin, ranger, svirfneblin`
(`cleric, fighter, magic_user, thief` and the race-as-class `dwarf, elf, halfling` stay Classic.)

**Advanced spell lists** (`data/spell_lists.yaml`): `druid, illusionist` (Classic: `magic_user, cleric`).

**Advanced magic items** (`data/equipment/magic_items.yaml`, 114 ids):
```
alchemists_beaker amulet_of_protection_against_possession apparatus_of_the_crab arrow_of_location bag_of_transformation book_of_foul_corruption book_of_infinite_spells book_of_sublime_holiness boots_of_dancing bracers_of_armour bracers_of_defencelessness brooch_of_shielding candle_of_invocation chime_of_opening chime_of_ravening cloak_of_defence cloak_of_flight cloak_of_poison cloak_of_the_manta_ray crystal_hypnosis_ball cube_of_force cube_of_frost_resistance decanter_of_endless_water deck_of_many_things drums_of_thunder dust_of_appearance dust_of_disappearance dust_of_sneezing_and_choking eyes_of_charming eyes_of_minuscule_sight eyes_of_petrification eyes_of_the_eagle feather_token figurine_of_wondrous_power folding_boat gem_of_brightness gem_of_monster_attraction gem_of_pristine_faceting gem_of_seeing gloves_of_dexterity gloves_of_swimming_and_climbing horn_of_cave_ins horn_of_frothing horn_of_the_tritons horn_of_valhalla horseshoes_of_a_zephyr horseshoes_of_speed incense_of_meditation incense_of_obsession instant_fortress ioun_stones iron_flask jug_of_endless_liquids libram_of_arcane_power loadstone luckstone lyre_of_building marvellous_pigments medallion_of_thought_projection mirror_of_mental_prowess mirror_of_opposition necklace_of_adaptation necklace_of_fireballs necklace_of_strangulation net_of_aquatic_snaring net_of_snaring oil_of_insubstantiality oil_of_slipperiness pearl_of_power pearl_of_wisdom periapt_of_foul_rotting periapt_of_health periapt_of_proof_against_poison periapt_of_wound_closure phylactery_of_betrayal phylactery_of_faithfulness phylactery_of_longevity pipes_of_the_sewers portable_hole purse_of_plentiful_coin restorative_ointment robe_of_blending robe_of_eyes robe_of_powerlessness robe_of_scintillating_colours robe_of_the_archmagi robe_of_useful_items rod_absorption rod_captivation rod_immovable rod_lordly_might rod_parrying rod_resurrection rod_striking rope_of_entanglement rope_of_strangulation rug_of_suffocation saw_of_felling scarab_of_chaos scarab_of_death scarab_of_rage spade_of_mighty_digging sphere_of_annihilation staff_dispelling staff_of_the_healer staff_of_the_woodlands staff_swarming_insects sweet_water talisman_of_the_sphere vacuous_grimoire wand_magic_missiles wand_radiance wand_summoning well_of_many_worlds
```

**Advanced enchantments** (`data/enchantments.yaml`, 36 ids):
```
short_sword_of_quickness sword_minus_1_berserker sword_plus_1_vs_reptiles sword_plus_1_vs_shapechangers sword_dragon_slayer sword_frost_brand sword_giant_slayer luck_blade sword_sharpness sword_sun_blade sword_wounding sword_dancing sword_nine_lives_stealer sword_venger sword_vorpal sword_defender sword_holy_avenger arrow_slaying crossbow_distance crossbow_speed crossbow_accuracy dagger_buckle dagger_throwing dagger_venomous dagger_biter javelin_of_lightning javelin_of_seeking mace_disrupting sling_bullet_impact spear_backbiter staff_growing trident_yearning trident_fish_command trident_submission trident_warning war_hammer_thunderbolts
```

Everything not listed above keeps the default `ose_classic_fantasy`. Mundane equipment, `scrolls.yaml`, and the generic `+1/+2/+3` and unlisted enchantments are Classic by default — no edits.

---

## Task 1: Source model + registry loading

**Files:**
- Create: `aose/models/source.py`
- Modify: `aose/models/__init__.py`
- Create: `data/sources.yaml`
- Modify: `aose/data/loader.py`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_sources_loaded(data):
    classic = data.sources["ose_classic_fantasy"]
    assert classic.name == "Old School Essentials Classic Fantasy"
    assert classic.publisher == "Necrotic Gnome"
    assert classic.core is True
    advanced = data.sources["ose_advanced_fantasy"]
    assert advanced.name == "Old School Essentials Advanced Fantasy"
    assert advanced.core is True


def test_sources_absent_file_is_empty(tmp_path):
    # A bare data dir (no sources.yaml) loads to an empty registry.
    assert GameData.load(tmp_path).sources == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_sources_loaded -q`
Expected: FAIL (`AttributeError: 'GameData' object has no attribute 'sources'`).

- [ ] **Step 3: Create the `Source` model**

Create `aose/models/source.py`:

```python
from pydantic import BaseModel, ConfigDict


class Source(BaseModel):
    """A published content source (rulebook).  Content models reference a
    source by id via their ``source`` field; the active ``RuleSet`` may disable
    non-core sources to hide their content."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    publisher: str
    core: bool = False
```

- [ ] **Step 4: Export `Source`**

In `aose/models/__init__.py`, add the import (next to the other model imports) and the `__all__` entry:

```python
from .source import Source
```

Add `"Source",` to the `__all__` list.

- [ ] **Step 5: Create `data/sources.yaml`**

```yaml
- id: ose_classic_fantasy
  name: Old School Essentials Classic Fantasy
  publisher: Necrotic Gnome
  core: true
- id: ose_advanced_fantasy
  name: Old School Essentials Advanced Fantasy
  publisher: Necrotic Gnome
  core: true
```

- [ ] **Step 6: Load sources in `loader.py`**

In `aose/data/loader.py`, add `Source` to the `from aose.models import (...)` block. Add this loader function near `_load_spell_lists`:

```python
def _load_sources(data_dir: Path) -> dict[str, Source]:
    """Read ``sources.yaml`` (a list of mappings) into an id-keyed dict.

    Returns an empty dict when the file is absent so minimal test fixtures
    (a bare data dir) still load.
    """
    path = data_dir / "sources.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise ValueError("sources.yaml must be a YAML list of mappings")
    result: dict[str, Source] = {}
    for obj in raw:
        parsed = Source.model_validate(obj)
        result[parsed.id] = parsed
    return result
```

Add the field to the `GameData` dataclass (after `enchantments`):

```python
    sources: dict[str, Source] = field(default_factory=dict)
```

And wire it into `GameData.load(...)`:

```python
            sources=_load_sources(data_dir),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/models/source.py aose/models/__init__.py data/sources.yaml aose/data/loader.py tests/test_data_loading.py
git commit -m "feat(sources): add Source model + sources.yaml registry"
```

---

## Task 2: `source` field on content models

**Files:**
- Modify: `aose/models/item.py` (ItemBase)
- Modify: `aose/models/race.py`
- Modify: `aose/models/character_class.py`
- Modify: `aose/models/spell_list.py`
- Modify: `aose/models/enchantment.py`
- Modify: `aose/models/spell.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_content_models_default_to_classic_source():
    from aose.models import (
        AdventuringGear, CharClass, Enchantment, Race, Spell, SpellList,
    )
    from aose.models.enchantment import AppliesTo

    gear = AdventuringGear(id="x", name="X", category="c", cost_gp=1, item_type="gear")
    assert gear.source == "ose_classic_fantasy"

    race = Race(id="x", name="X")
    assert race.source == "ose_classic_fantasy"

    cls = CharClass(id="x", name="X", prime_requisites=[], hit_die="1d6",
                    weapons_allowed="all", armor_allowed="all", shields_allowed=True)
    assert cls.source == "ose_classic_fantasy"

    sl = SpellList(id="x", name="X", caster_type="arcane")
    assert sl.source == "ose_classic_fantasy"

    ench = Enchantment(id="x", name_template="{base} +1", kind="weapon",
                       applies_to=AppliesTo(include=["any_weapon"]))
    assert ench.source == "ose_classic_fantasy"

    spell = Spell(id="x", name="X", level=1, range="0", duration="0", description="d")
    assert spell.source == "ose_classic_fantasy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_content_models_default_to_classic_source -q`
Expected: FAIL (`AttributeError`/`assert ... == 'ose_classic_fantasy'`).

- [ ] **Step 3: Add the field to each model**

In `aose/models/item.py`, add to `ItemBase` (after `magic: bool = False`):

```python
    source: str = "ose_classic_fantasy"   # content source / book of origin
```

In `aose/models/race.py`, add to `Race` (after `id`/`name` block, e.g. after `name: str`):

```python
    source: str = "ose_classic_fantasy"
```

In `aose/models/character_class.py`, add to `CharClass` (after `name: str`):

```python
    source: str = "ose_classic_fantasy"
```

In `aose/models/spell_list.py`, add to `SpellList` (after `caster_type`):

```python
    source: str = "ose_classic_fantasy"
```

In `aose/models/enchantment.py`, add to `Enchantment` (after `id: str`):

```python
    source: str = "ose_classic_fantasy"
```

In `aose/models/spell.py`, change the existing `source` field. Replace:

```python
    source: str | None = None
```

with:

```python
    source: str = "ose_classic_fantasy"
```

(Remove the now-stale comment line above it about "a future selector".)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/models/item.py aose/models/race.py aose/models/character_class.py aose/models/spell_list.py aose/models/enchantment.py aose/models/spell.py tests/test_models.py
git commit -m "feat(sources): add source field to content models (default Classic)"
```

---

## Task 3: `RuleSet.disabled_sources` + `source_enabled` helper

**Files:**
- Modify: `aose/models/ruleset.py`
- Create: `aose/engine/sources.py`
- Test: `tests/test_sources_engine.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_sources_engine.py`:

```python
from aose.engine.sources import CLASSIC_SOURCE_ID, source_enabled
from aose.models import RuleSet


def test_classic_is_always_enabled():
    rs = RuleSet(disabled_sources=["ose_classic_fantasy", "ose_advanced_fantasy"])
    assert source_enabled(CLASSIC_SOURCE_ID, rs) is True


def test_unlisted_source_is_enabled_by_default():
    assert source_enabled("ose_advanced_fantasy", RuleSet()) is True


def test_disabled_source_is_not_enabled():
    rs = RuleSet(disabled_sources=["ose_advanced_fantasy"])
    assert source_enabled("ose_advanced_fantasy", rs) is False


def test_disabled_sources_defaults_empty():
    assert RuleSet().disabled_sources == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sources_engine.py -q`
Expected: FAIL (`ModuleNotFoundError: aose.engine.sources`).

- [ ] **Step 3: Add the RuleSet field**

In `aose/models/ruleset.py`, add to `RuleSet` (after `optional_staves`):

```python
    # Content sources to hide.  A source is enabled unless its id is listed
    # here; Classic Fantasy is always enabled (never offered as a toggle).
    disabled_sources: list[str] = Field(default_factory=list)
```

Update the imports at the top of the file:

```python
from pydantic import BaseModel, ConfigDict, Field
```

- [ ] **Step 4: Create the helper module**

Create `aose/engine/sources.py`:

```python
"""Source-filter helper.  Cycle-free: imports only models.

A character's :class:`RuleSet` may disable content sources; this module decides
whether a given source id is currently active.  Classic Fantasy is the baseline
and can never be disabled.
"""
from aose.models import RuleSet

CLASSIC_SOURCE_ID = "ose_classic_fantasy"


def source_enabled(source_id: str, ruleset: RuleSet) -> bool:
    """Whether content from ``source_id`` is available under ``ruleset``."""
    if source_id == CLASSIC_SOURCE_ID:
        return True
    return source_id not in ruleset.disabled_sources
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sources_engine.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/models/ruleset.py aose/engine/sources.py tests/test_sources_engine.py
git commit -m "feat(sources): RuleSet.disabled_sources + source_enabled helper"
```

---

## Task 4: Tag Advanced races

**Files:**
- Modify: `data/races/{drow,duergar,dwarf,elf,gnome,half_elf,half_orc,halfling,svirfneblin}.yaml`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_race_sources(data):
    assert data.races["human"].source == "ose_classic_fantasy"
    for rid in ("drow", "duergar", "dwarf", "elf", "gnome", "half_elf",
                "half_orc", "halfling", "svirfneblin"):
        assert data.races[rid].source == "ose_advanced_fantasy", rid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_race_sources -q`
Expected: FAIL (races default to `ose_classic_fantasy`).

- [ ] **Step 3: Tag each Advanced race file**

In each of the 9 files listed above, add a top-level line immediately after the `name:` line:

```yaml
source: ose_advanced_fantasy
```

Example for `data/races/elf.yaml` — the first lines become:

```yaml
id: elf
name: Elf
source: ose_advanced_fantasy
ability_requirements:
  INT: 9
```

Do **not** edit `data/races/human.yaml`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_race_sources -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/races/ tests/test_data_loading.py
git commit -m "data(sources): tag Advanced Fantasy races"
```

---

## Task 5: Tag Advanced classes

**Files:**
- Modify: `data/classes/{acrobat,assassin,barbarian,bard,drow,druid,duergar,gnome,half_elf,half_orc,illusionist,knight,paladin,ranger,svirfneblin}.yaml`
- Test: `tests/test_data_loading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_class_sources(data):
    for cid in ("cleric", "fighter", "magic_user", "thief",
                "dwarf", "elf", "halfling"):
        assert data.classes[cid].source == "ose_classic_fantasy", cid
    for cid in ("acrobat", "assassin", "barbarian", "bard", "drow", "druid",
                "duergar", "gnome", "half_elf", "half_orc", "illusionist",
                "knight", "paladin", "ranger", "svirfneblin"):
        assert data.classes[cid].source == "ose_advanced_fantasy", cid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_class_sources -q`
Expected: FAIL.

- [ ] **Step 3: Tag each Advanced class file**

In each of the 15 files listed above, add a top-level line immediately after the `name:` line:

```yaml
source: ose_advanced_fantasy
```

Example for `data/classes/druid.yaml`:

```yaml
id: druid
name: Druid
source: ose_advanced_fantasy
prime_requisites:
- WIS
```

Do **not** edit `cleric.yaml`, `fighter.yaml`, `magic_user.yaml`, `thief.yaml`, `dwarf.yaml`, `elf.yaml`, `halfling.yaml`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_class_sources -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/classes/ tests/test_data_loading.py
git commit -m "data(sources): tag Advanced Fantasy classes"
```

---

## Task 6: Tag Advanced spell lists + normalize per-spell source

**Files:**
- Modify: `data/spell_lists.yaml`
- Modify: `data/spells/advanced_fantasy_magic_user_spells.yaml`
- Modify: `data/spells/advanced_fantasy_cleric_spells.yaml`
- Modify: `data/spells/advanced_fantasy_druid_spells.yaml`
- Modify: `data/spells/advanced_fantasy_illusionist_spells.yaml`
- Test: `tests/test_data_loading.py`

All 212 spells are single-list, so each spell file maps to exactly one list: magic_user/cleric → Classic, druid/illusionist → Advanced.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
def test_spell_list_sources(data):
    assert data.spell_lists["magic_user"].source == "ose_classic_fantasy"
    assert data.spell_lists["cleric"].source == "ose_classic_fantasy"
    assert data.spell_lists["druid"].source == "ose_advanced_fantasy"
    assert data.spell_lists["illusionist"].source == "ose_advanced_fantasy"


def test_spell_sources_match_their_list(data):
    for spell in data.spells.values():
        lists = set(spell.spell_lists)
        expected = ("ose_classic_fantasy"
                    if lists & {"magic_user", "cleric"}
                    else "ose_advanced_fantasy")
        assert spell.source == expected, spell.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_spell_list_sources tests/test_data_loading.py::test_spell_sources_match_their_list -q`
Expected: FAIL.

- [ ] **Step 3: Tag the two Advanced spell lists**

In `data/spell_lists.yaml`, add `source: ose_advanced_fantasy` to the `druid` and `illusionist` entries (leave `magic_user` and `cleric` untouched). The `druid` entry becomes:

```yaml
- id: druid
  name: Druid
  caster_type: divine
  source: ose_advanced_fantasy
  description: Divine spells granted by nature; the whole list is known.
```

and `illusionist`:

```yaml
- id: illusionist
  name: Illusionist
  caster_type: arcane
  source: ose_advanced_fantasy
  description: Arcane illusion spells learned through study and recorded in a spell book.
```

- [ ] **Step 4: Normalize per-spell source via in-place replace**

Each spell file currently repeats the line `  source: "ose-advanced-fantasy"` once per spell. Replace that exact line in every file with the correct source id. Run this from the project root:

```bash
.venv/Scripts/python.exe - << 'PY'
import pathlib
mapping = {
    "advanced_fantasy_magic_user_spells.yaml": "ose_classic_fantasy",
    "advanced_fantasy_cleric_spells.yaml":     "ose_classic_fantasy",
    "advanced_fantasy_druid_spells.yaml":      "ose_advanced_fantasy",
    "advanced_fantasy_illusionist_spells.yaml":"ose_advanced_fantasy",
}
base = pathlib.Path("data/spells")
for fname, src in mapping.items():
    p = base / fname
    text = p.read_text(encoding="utf-8")
    new = text.replace('  source: "ose-advanced-fantasy"', f"  source: {src}")
    assert new != text, f"no source lines replaced in {fname}"
    p.write_text(new, encoding="utf-8")
    print(f"{fname}: -> {src}")
PY
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data/spell_lists.yaml data/spells/ tests/test_data_loading.py
git commit -m "data(sources): tag Advanced spell lists; normalize per-spell source"
```

---

## Task 7: Tag Advanced magic items + enchantments

**Files:**
- Modify: `data/equipment/magic_items.yaml`
- Modify: `data/enchantments.yaml`
- Test: `tests/test_data_loading.py`

Both files are YAML lists whose entries start with `- id: <id>` at column 0, with fields indented two spaces. We insert a `  source: ose_advanced_fantasy` line directly after each matched id line, preserving all existing formatting and descriptions.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data_loading.py`:

```python
ADVANCED_MAGIC_ITEM_IDS = {
    "alchemists_beaker", "amulet_of_protection_against_possession",
    "apparatus_of_the_crab", "arrow_of_location", "bag_of_transformation",
    "book_of_foul_corruption", "book_of_infinite_spells",
    "book_of_sublime_holiness", "boots_of_dancing", "bracers_of_armour",
    "bracers_of_defencelessness", "brooch_of_shielding", "candle_of_invocation",
    "chime_of_opening", "chime_of_ravening", "cloak_of_defence",
    "cloak_of_flight", "cloak_of_poison", "cloak_of_the_manta_ray",
    "crystal_hypnosis_ball", "cube_of_force", "cube_of_frost_resistance",
    "decanter_of_endless_water", "deck_of_many_things", "drums_of_thunder",
    "dust_of_appearance", "dust_of_disappearance", "dust_of_sneezing_and_choking",
    "eyes_of_charming", "eyes_of_minuscule_sight", "eyes_of_petrification",
    "eyes_of_the_eagle", "feather_token", "figurine_of_wondrous_power",
    "folding_boat", "gem_of_brightness", "gem_of_monster_attraction",
    "gem_of_pristine_faceting", "gem_of_seeing", "gloves_of_dexterity",
    "gloves_of_swimming_and_climbing", "horn_of_cave_ins", "horn_of_frothing",
    "horn_of_the_tritons", "horn_of_valhalla", "horseshoes_of_a_zephyr",
    "horseshoes_of_speed", "incense_of_meditation", "incense_of_obsession",
    "instant_fortress", "ioun_stones", "iron_flask", "jug_of_endless_liquids",
    "libram_of_arcane_power", "loadstone", "luckstone", "lyre_of_building",
    "marvellous_pigments", "medallion_of_thought_projection",
    "mirror_of_mental_prowess", "mirror_of_opposition", "necklace_of_adaptation",
    "necklace_of_fireballs", "necklace_of_strangulation", "net_of_aquatic_snaring",
    "net_of_snaring", "oil_of_insubstantiality", "oil_of_slipperiness",
    "pearl_of_power", "pearl_of_wisdom", "periapt_of_foul_rotting",
    "periapt_of_health", "periapt_of_proof_against_poison",
    "periapt_of_wound_closure", "phylactery_of_betrayal",
    "phylactery_of_faithfulness", "phylactery_of_longevity", "pipes_of_the_sewers",
    "portable_hole", "purse_of_plentiful_coin", "restorative_ointment",
    "robe_of_blending", "robe_of_eyes", "robe_of_powerlessness",
    "robe_of_scintillating_colours", "robe_of_the_archmagi", "robe_of_useful_items",
    "rod_absorption", "rod_captivation", "rod_immovable", "rod_lordly_might",
    "rod_parrying", "rod_resurrection", "rod_striking", "rope_of_entanglement",
    "rope_of_strangulation", "rug_of_suffocation", "saw_of_felling",
    "scarab_of_chaos", "scarab_of_death", "scarab_of_rage", "spade_of_mighty_digging",
    "sphere_of_annihilation", "staff_dispelling", "staff_of_the_healer",
    "staff_of_the_woodlands", "staff_swarming_insects", "sweet_water",
    "talisman_of_the_sphere", "vacuous_grimoire", "wand_magic_missiles",
    "wand_radiance", "wand_summoning", "well_of_many_worlds",
}

ADVANCED_ENCHANTMENT_IDS = {
    "short_sword_of_quickness", "sword_minus_1_berserker", "sword_plus_1_vs_reptiles",
    "sword_plus_1_vs_shapechangers", "sword_dragon_slayer", "sword_frost_brand",
    "sword_giant_slayer", "luck_blade", "sword_sharpness", "sword_sun_blade",
    "sword_wounding", "sword_dancing", "sword_nine_lives_stealer", "sword_venger",
    "sword_vorpal", "sword_defender", "sword_holy_avenger", "arrow_slaying",
    "crossbow_distance", "crossbow_speed", "crossbow_accuracy", "dagger_buckle",
    "dagger_throwing", "dagger_venomous", "dagger_biter", "javelin_of_lightning",
    "javelin_of_seeking", "mace_disrupting", "sling_bullet_impact", "spear_backbiter",
    "staff_growing", "trident_yearning", "trident_fish_command", "trident_submission",
    "trident_warning", "war_hammer_thunderbolts",
}


def test_magic_item_sources(data):
    assert len(ADVANCED_MAGIC_ITEM_IDS) == 114
    for iid, item in data.items.items():
        if iid in ADVANCED_MAGIC_ITEM_IDS:
            assert item.source == "ose_advanced_fantasy", iid
        else:
            assert item.source == "ose_classic_fantasy", iid


def test_enchantment_sources(data):
    assert len(ADVANCED_ENCHANTMENT_IDS) == 36
    for eid, ench in data.enchantments.items():
        if eid in ADVANCED_ENCHANTMENT_IDS:
            assert ench.source == "ose_advanced_fantasy", eid
        else:
            assert ench.source == "ose_classic_fantasy", eid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py::test_magic_item_sources tests/test_data_loading.py::test_enchantment_sources -q`
Expected: FAIL.

- [ ] **Step 3: Insert source lines via script**

Run this from the project root. It imports the id sets from the test module to stay DRY, then inserts a source line after each matched `- id:` line:

```bash
.venv/Scripts/python.exe - << 'PY'
import pathlib, sys
sys.path.insert(0, "tests")
from test_data_loading import ADVANCED_MAGIC_ITEM_IDS, ADVANCED_ENCHANTMENT_IDS

def tag(path, ids):
    p = pathlib.Path(path)
    out, inserted = [], set()
    for line in p.read_text(encoding="utf-8").splitlines(keepends=True):
        out.append(line)
        stripped = line.rstrip("\n")
        if stripped.startswith("- id: "):
            iid = stripped[len("- id: "):].strip().strip('"').strip("'")
            if iid in ids:
                nl = "\n" if line.endswith("\n") else ""
                out.append(f"  source: ose_advanced_fantasy{nl}")
                inserted.add(iid)
    missing = ids - inserted
    assert not missing, f"{path}: ids not found: {sorted(missing)}"
    p.write_text("".join(out), encoding="utf-8")
    print(f"{path}: tagged {len(inserted)}")

tag("data/equipment/magic_items.yaml", ADVANCED_MAGIC_ITEM_IDS)
tag("data/enchantments.yaml", ADVANCED_ENCHANTMENT_IDS)
PY
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_data_loading.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/equipment/magic_items.yaml data/enchantments.yaml tests/test_data_loading.py
git commit -m "data(sources): tag Advanced magic items + enchantments"
```

---

## Task 8: Gate wizard race + class lists by source

**Files:**
- Modify: `aose/web/wizard.py` (`get_race` ~559, `get_class` ~645)
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings.py`:

```python
def _new_draft_with_sources(client, drafts_dir, disabled):
    """Start a draft and set its ruleset's disabled_sources directly."""
    from aose.characters import load_draft, save_draft
    r = client.get("/wizard/new")
    draft_id = r.headers["location"].split("/")[2]
    draft = load_draft(draft_id, drafts_dir)
    draft["abilities"] = {"STR": 13, "INT": 13, "WIS": 13, "DEX": 13, "CON": 13, "CHA": 13}
    draft["ruleset"]["disabled_sources"] = disabled
    save_draft(draft_id, draft, drafts_dir)
    return draft_id


def test_race_step_hides_advanced_when_disabled(client, tmp_path):
    draft_id = _new_draft_with_sources(client, tmp_path / "drafts", ["ose_advanced_fantasy"])
    r = client.get(f"/wizard/{draft_id}/race")
    assert 'value="human"' in r.text
    assert 'value="elf"' not in r.text


def test_race_step_shows_advanced_when_enabled(client, tmp_path):
    draft_id = _new_draft_with_sources(client, tmp_path / "drafts", [])
    r = client.get(f"/wizard/{draft_id}/race")
    assert 'value="elf"' in r.text


def test_class_step_hides_advanced_when_disabled(client, tmp_path):
    # Basic creation so the class step renders without a race pick.
    from aose.characters import load_draft, save_draft
    draft_id = _new_draft_with_sources(client, tmp_path / "drafts", ["ose_advanced_fantasy"])
    draft = load_draft(draft_id, tmp_path / "drafts")
    draft["ruleset"]["separate_race_class"] = False
    save_draft(draft_id, draft, tmp_path / "drafts")
    r = client.get(f"/wizard/{draft_id}/class")
    assert 'value="fighter"' in r.text
    assert 'value="druid"' not in r.text
```

(The race/class card markup uses `value="<id>"` on the radio/submit inputs; confirm by inspecting the rendered page if an assertion mismatches.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py::test_race_step_hides_advanced_when_disabled -q`
Expected: FAIL (Advanced races still rendered).

- [ ] **Step 3: Filter the race list**

In `aose/web/wizard.py`, add the import near the other engine imports at the top:

```python
from aose.engine.sources import source_enabled
```

In `get_race`, change the loop header (line ~559) from:

```python
    for race in sorted(data.races.values(), key=lambda r: r.name):
```

to:

```python
    ruleset = _ruleset_of(draft)
    for race in sorted(data.races.values(), key=lambda r: r.name):
        if not source_enabled(race.source, ruleset):
            continue
```

- [ ] **Step 4: Filter the class list**

In `get_class`, the loop already computes `ruleset = _ruleset_of(draft)` earlier (line ~633). In the loop (line ~645), add a source guard right after the existing race-as-class `continue`:

```python
        if not source_enabled(cls.source, ruleset):
            continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py tests/test_settings.py
git commit -m "feat(sources): filter wizard race/class lists by enabled source"
```

---

## Task 9: Gate spell selection by source

**Files:**
- Modify: `aose/web/wizard.py` (`_caster_entries` ~1263)
- Test: `tests/test_spells.py` or `tests/test_spell_routes.py`

A spell is available only when at least one of its spell lists belongs to an enabled source. In practice an Advanced class (illusionist/druid) is already hidden when Advanced is off, so this guard primarily protects Classic casters who could otherwise pick from a disabled list (none today) and future-proofs the candidate builder.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_spells.py`:

```python
def test_caster_candidates_respect_disabled_source():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.web.wizard import _caster_entries

    data = GameData.load(Path(__file__).parent.parent / "data")
    # Illusionist casts from the Advanced 'illusionist' list. With Advanced
    # disabled, its candidate list must be empty.
    draft = {
        "abilities": {"INT": 13, "WIS": 13},
        "class_id": "illusionist",
        "ruleset": {"disabled_sources": ["ose_advanced_fantasy"],
                    "separate_race_class": True},
    }
    rows = _caster_entries(draft, data)
    for row in rows:
        if row["class_id"] == "illusionist":
            assert row["candidates"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py::test_caster_candidates_respect_disabled_source -q`
Expected: FAIL (candidates still populated).

- [ ] **Step 3: Filter spell candidates by list source**

In `aose/web/wizard.py`, inside `_caster_entries`, replace the `candidates = sorted(...)` comprehension (line ~1263) with a version that also checks each spell's lists against enabled sources:

```python
        enabled_lists = {
            lid for lid in cls.spell_lists
            if lid in data.spell_lists
            and source_enabled(data.spell_lists[lid].source, ruleset)
        }
        candidates = sorted(
            (s for s in data.spells.values()
             if set(s.spell_lists) & enabled_lists
             and s.level in spell_engine.accessible_levels(entry, cls)),
            key=lambda s: (s.level, s.name),
        )
```

(`ruleset` is already defined at the top of `_caster_entries`. `source_enabled` was imported in Task 8.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_spells.py tests/test_spell_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add aose/web/wizard.py tests/test_spells.py
git commit -m "feat(sources): filter spell candidates by enabled list source"
```

---

## Task 10: Gate shop + enchantment picker by source

**Files:**
- Modify: `aose/engine/shop.py` (`shop_categories` ~89)
- Modify: `aose/web/routes.py` (`_enchant_choices` ~102; shop call ~172)
- Modify: `aose/web/wizard.py` (shop call ~1391)
- Test: `tests/test_equipment.py`, `tests/test_enchantments.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_equipment.py`:

```python
def test_shop_categories_filters_by_source():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.engine.shop import shop_categories
    from aose.models import RuleSet

    data = GameData.load(Path(__file__).parent.parent / "data")
    rs = RuleSet(disabled_sources=["ose_advanced_fantasy"])
    all_ids = {i.id for cat in shop_categories(data) for i in cat.items}
    filtered_ids = {i.id for cat in shop_categories(data, rs) for i in cat.items}
    # A known Advanced magic item drops out; a mundane Classic item stays.
    assert "luckstone" in all_ids
    assert "luckstone" not in filtered_ids
    assert "backpack" in filtered_ids  # mundane gear is Classic
```

Add to `tests/test_enchantments.py`:

```python
def test_enchant_choices_filter_by_source():
    from pathlib import Path
    from aose.data.loader import GameData
    from aose.models import RuleSet
    from aose.web.routes import _enchant_choices

    data = GameData.load(Path(__file__).parent.parent / "data")
    rs = RuleSet(disabled_sources=["ose_advanced_fantasy"])
    all_ids = {c["id"] for c in _enchant_choices(data)}
    filtered_ids = {c["id"] for c in _enchant_choices(data, rs)}
    assert "sword_frost_brand" in all_ids       # Advanced
    assert "sword_frost_brand" not in filtered_ids
    assert "sword_plus_1" in filtered_ids       # generic, Classic
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py::test_shop_categories_filters_by_source tests/test_enchantments.py::test_enchant_choices_filter_by_source -q`
Expected: FAIL (`shop_categories()`/`_enchant_choices()` take no ruleset arg).

- [ ] **Step 3: Add an optional ruleset filter to `shop_categories`**

In `aose/engine/shop.py`, add the import at the top of the file:

```python
from aose.engine.sources import source_enabled
```

Change the signature and the item loop:

```python
def shop_categories(data: GameData, ruleset: "RuleSet | None" = None) -> list[ShopCategory]:
    """Group every item in ``data.items`` by its ``category`` field, sorted
    alphabetically.  Within a category, items are sorted by cost then name so
    the cheap stuff is at the top.  When ``ruleset`` is given, items from a
    disabled source are omitted."""
    by_cat: dict[str, list[Item]] = {}
    for item in data.items.values():
        if ruleset is not None and not source_enabled(item.source, ruleset):
            continue
        by_cat.setdefault(item.category, []).append(item)
```

Add the `RuleSet` import for the annotation (top of file, with the other model imports):

```python
from aose.models import RuleSet
```

(If `shop.py` imports models lazily to avoid cycles, instead use a string annotation only and skip the top-level import — the `"RuleSet | None"` string already avoids a runtime need. Verify no circular import by running the test; `aose.engine.sources` imports only `aose.models`, which is safe.)

- [ ] **Step 4: Add an optional ruleset filter to `_enchant_choices`**

In `aose/web/routes.py`, add the import near the top:

```python
from aose.engine.sources import source_enabled
```

Change `_enchant_choices` (line ~102):

```python
def _enchant_choices(game_data, ruleset=None):
    """Picker data: each enchantment with its compatible base items, sorted by kind then id."""
    from aose.engine.enchant import compatible_bases
    out = []
    for ench in sorted(game_data.enchantments.values(), key=lambda e: (e.kind, e.id)):
        if ruleset is not None and not source_enabled(ench.source, ruleset):
            continue
        bases = compatible_bases(ench, game_data)
        if not bases:
            continue
        ...
```

- [ ] **Step 5: Pass the ruleset at the call sites**

In `aose/web/routes.py` (sheet context, line ~171-172), change:

```python
            "enchant_choices": _enchant_choices(game_data),
            "shop": shop_categories(game_data),
```

to:

```python
            "enchant_choices": _enchant_choices(game_data, spec.ruleset),
            "shop": shop_categories(game_data, spec.ruleset),
```

In `aose/web/wizard.py` (equipment context, line ~1391), change:

```python
        "shop": shop_categories(game_data),
```

to:

```python
        "shop": shop_categories(game_data, _ruleset_of(draft)),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_equipment.py tests/test_enchantments.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add aose/engine/shop.py aose/web/routes.py aose/web/wizard.py tests/test_equipment.py tests/test_enchantments.py
git commit -m "feat(sources): filter shop + enchantment picker by enabled source"
```

---

## Task 11: Sources filter UI on rules + settings pages

**Files:**
- Modify: `aose/web/settings_routes.py` (`parse_ruleset_from_form`, `get_settings`)
- Modify: `aose/web/wizard.py` (`get_rules`, `post_rules`)
- Modify: `aose/web/templates/_ruleset_fields.html`
- Test: `tests/test_settings.py`

Form contract: each source renders a checkbox named `source_<id>`. Classic renders checked+disabled (disabled inputs are not posted, so the parser must treat Classic as always-enabled). `disabled_sources = [id for id in source_ids if id != classic and "source_<id>" not in form]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_settings.py`:

```python
def test_parser_disables_unchecked_sources():
    rs = parse_ruleset_from_form(
        _Form({"creation_method": "advanced"}),
        source_ids=["ose_classic_fantasy", "ose_advanced_fantasy"],
    )
    # Advanced not checked -> disabled; Classic never disabled.
    assert rs.disabled_sources == ["ose_advanced_fantasy"]


def test_parser_keeps_checked_sources_enabled():
    rs = parse_ruleset_from_form(
        _Form({"creation_method": "advanced", "source_ose_advanced_fantasy": "on"}),
        source_ids=["ose_classic_fantasy", "ose_advanced_fantasy"],
    )
    assert rs.disabled_sources == []


def test_parser_never_disables_classic():
    rs = parse_ruleset_from_form(
        _Form({}),  # nothing checked
        source_ids=["ose_classic_fantasy", "ose_advanced_fantasy"],
    )
    assert "ose_classic_fantasy" not in rs.disabled_sources


def test_parser_without_source_ids_disables_nothing():
    # Backward-compatible default for existing callers.
    rs = parse_ruleset_from_form(_Form({"creation_method": "advanced"}))
    assert rs.disabled_sources == []


def test_settings_page_renders_sources_section(client):
    r = client.get("/settings")
    assert "Content Sources" in r.text
    assert "Necrotic Gnome" in r.text
    assert 'name="source_ose_advanced_fantasy"' in r.text
    # Classic checkbox is present but disabled (locked on).
    import re
    assert re.search(r'name="source_ose_classic_fantasy"[^>]*\bdisabled\b', r.text)


def test_post_settings_persists_disabled_source(client):
    r = client.post("/settings", data={"creation_method": "advanced"})  # Advanced unchecked
    assert r.status_code == 303
    rs = load_settings(client._settings_path)
    assert rs.disabled_sources == ["ose_advanced_fantasy"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py::test_parser_disables_unchecked_sources tests/test_settings.py::test_settings_page_renders_sources_section -q`
Expected: FAIL.

- [ ] **Step 3: Extend `parse_ruleset_from_form`**

In `aose/web/settings_routes.py`, add a module constant near the top:

```python
from aose.engine.sources import CLASSIC_SOURCE_ID
```

Change the signature and append source parsing before the `return`:

```python
def parse_ruleset_from_form(form, source_ids=None) -> RuleSet:
    ...
    # (existing bools / choices logic unchanged) ...

    disabled_sources = []
    for sid in (source_ids or []):
        if sid == CLASSIC_SOURCE_ID:
            continue
        if f"source_{sid}" not in form:
            disabled_sources.append(sid)

    return RuleSet(**bools, **choices, disabled_sources=disabled_sources)
```

- [ ] **Step 4: Pass `sources` + `source_ids` from the settings route**

In `get_settings`, read game data and add `sources` to the context:

```python
@router.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    ruleset = load_settings(_settings_path(request))
    saved = request.query_params.get("saved") == "1"
    sources = sorted(
        request.app.state.game_data.sources.values(),
        key=lambda s: (not s.core, s.name),
    )
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "ruleset": ruleset,
            "rule_groups": RULE_GROUPS,
            "choice_groups": CHOICE_GROUPS,
            "rule_labels": RULE_LABELS,
            "implemented_rules": IMPLEMENTED_RULES,
            "implemented_choice_groups": IMPLEMENTED_CHOICE_GROUPS,
            "advanced_options_group": ADVANCED_OPTIONS_GROUP,
            "sources": sources,
            "classic_source_id": CLASSIC_SOURCE_ID,
            "saved": saved,
        },
    )
```

In `post_settings`, pass `source_ids`:

```python
@router.post("/settings")
async def post_settings(request: Request):
    form = await request.form()
    source_ids = list(request.app.state.game_data.sources)
    new_ruleset = parse_ruleset_from_form(form, source_ids=source_ids)
    save_settings(_settings_path(request), new_ruleset)
    return RedirectResponse("/settings?saved=1", status_code=303)
```

- [ ] **Step 5: Pass `sources` + `source_ids` from the wizard rules route**

In `aose/web/wizard.py`, import the constant near the top:

```python
from aose.engine.sources import CLASSIC_SOURCE_ID
```

In `get_rules`, add to the `ctx.update({...})`:

```python
        "sources": sorted(
            request.app.state.game_data.sources.values(),
            key=lambda s: (not s.core, s.name),
        ),
        "classic_source_id": CLASSIC_SOURCE_ID,
```

In `post_rules`, change:

```python
    new_rs = parse_ruleset_from_form(form)
```

to:

```python
    source_ids = list(request.app.state.game_data.sources)
    new_rs = parse_ruleset_from_form(form, source_ids=source_ids)
```

- [ ] **Step 6: Add the Sources fieldset to the shared partial**

In `aose/web/templates/_ruleset_fields.html`, add this block immediately after the creation-method `<fieldset>` (before the `{% for group_name, fields in rule_groups %}` loop). The `sources` / `classic_source_id` keys are now in both pages' contexts:

```html
{% if sources %}
<fieldset class="rule-group">
    <legend>Content Sources</legend>
    {% for src in sources %}
    <label class="rule">
        <input type="checkbox" name="source_{{ src.id }}"
               {% if src.id == classic_source_id %}checked disabled{% elif src.id not in ruleset['disabled_sources'] %}checked{% endif %}>
        <span class="rule-body">
            <span class="rule-name">
                {{ src.name }}
                {% if src.core %}<span class="rule-core" title="Core source">core</span>{% endif %}
            </span>
            <span class="rule-desc">{{ src.publisher }}</span>
        </span>
    </label>
    {% endfor %}
</fieldset>
{% endif %}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add aose/web/settings_routes.py aose/web/wizard.py aose/web/templates/_ruleset_fields.html tests/test_settings.py
git commit -m "feat(sources): Sources filter UI on rules + settings pages"
```

---

## Task 12: Mid-wizard source-change cascade

**Files:**
- Modify: `aose/web/wizard.py` (`_apply_rule_changes` ~385, `post_rules` ~431)
- Test: `tests/test_settings.py`

When the picked race or any picked class becomes orphaned by a newly disabled source, clear it (cascading downstream). Wizard inventory is mundane-only (all Classic) and enchantments are sheet-only, so race + class clears fully cover the wizard's gated picks; clearing a class also clears its spellbooks via `_clear_after_race`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings.py`:

```python
def test_disabling_source_clears_orphaned_race(client, tmp_path):
    from aose.characters import load_draft, save_draft
    drafts = tmp_path / "drafts"
    draft_id = _new_draft_with_sources(client, drafts, [])
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "elf"})
    # Re-post the rules step with Advanced now disabled (Advanced creation kept).
    client.post(f"/wizard/{draft_id}/rules", data={"creation_method": "advanced"})
    draft = load_draft(draft_id, drafts)
    assert "race_id" not in draft


def test_disabling_source_keeps_classic_race(client, tmp_path):
    from aose.characters import load_draft
    drafts = tmp_path / "drafts"
    draft_id = _new_draft_with_sources(client, drafts, [])
    client.post(f"/wizard/{draft_id}/race", data={"race_id": "human"})
    client.post(f"/wizard/{draft_id}/rules", data={"creation_method": "advanced"})
    draft = load_draft(draft_id, drafts)
    assert draft.get("race_id") == "human"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py::test_disabling_source_clears_orphaned_race -q`
Expected: FAIL (`race_id` still "elf").

- [ ] **Step 3: Pass game data into `_apply_rule_changes` and add source clears**

In `aose/web/wizard.py`, change the `_apply_rule_changes` signature to accept `data`:

```python
def _apply_rule_changes(draft: dict[str, Any], old_rs: RuleSet, new_rs: RuleSet, data) -> None:
```

At the end of the function (after the existing `if not new_rs.multiclassing ...` block), add:

```python
    if new_rs.disabled_sources != old_rs.disabled_sources:
        race_id = draft.get("race_id")
        if race_id in data.races and not source_enabled(
            data.races[race_id].source, new_rs
        ):
            _clear_after_abilities(draft)
            return
        for cid in _class_ids(draft):
            if cid in data.classes and not source_enabled(
                data.classes[cid].source, new_rs
            ):
                _clear_after_race(draft)
                break
```

(`source_enabled` was imported in Task 8; `_class_ids` and the `_clear_after_*` helpers already exist.)

- [ ] **Step 4: Update the `post_rules` call site**

In `post_rules` (line ~440), change:

```python
    _apply_rule_changes(draft, old_rs, new_rs)
```

to:

```python
    _apply_rule_changes(draft, old_rs, new_rs, request.app.state.game_data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add aose/web/wizard.py tests/test_settings.py
git commit -m "feat(sources): clear orphaned race/class when a source is disabled mid-wizard"
```

---

## Task 13: Full suite + final commit

- [ ] **Step 1: Run the whole test suite**

Run: `.venv\Scripts\python.exe -m pytest tests/ -q`
Expected: PASS (ignore the known trailing `PermissionError` on `pytest-current`, a Windows-tempdir quirk).

- [ ] **Step 2: Fix any regressions**

If any pre-existing test broke (e.g. a settings-page assertion that counted fieldsets, or a `shop_categories`/`_enchant_choices` caller), update it to account for the new Sources section / optional ruleset argument. Re-run until green.

- [ ] **Step 3: Update CLAUDE.md current-state note**

Add a short "Current state (2026-06-06, content sources)" entry to `CLAUDE.md` summarizing: `Source` model + `data/sources.yaml`; `source` field default Classic on all content models; `RuleSet.disabled_sources` + `aose/engine/sources.py`; filter UI in `_ruleset_fields.html`; gating in wizard race/class/spells, shop, enchantment picker; mid-wizard cascade. Reference the spec/plan paths.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(sources): note content-sources feature in CLAUDE.md"
```

---

## Self-review notes

- **Spec coverage:** Source model + registry (T1), `source` on all content models (T2), `disabled_sources` + helper (T3), Advanced tagging of races/classes/spell-lists/spells/items/enchantments (T4–T7), gating in wizard pickers (T8), spells (T9), shop + enchantment picker (T10), filter UI on both pages (T11), mid-wizard cascade (T12), edge case (Human-only) is covered implicitly — `human` stays Classic (T4) and the race loop never empties. All spec sections map to a task.
- **No migrations:** `disabled_sources` defaults to `[]`; existing `settings.json` and drafts load unchanged (verified by `test_parser_without_source_ids_disables_nothing` and the absent-file loader test).
- **Type consistency:** `source_enabled(source_id, ruleset)` and `CLASSIC_SOURCE_ID` are used identically across T8–T12; `shop_categories(data, ruleset=None)` and `_enchant_choices(game_data, ruleset=None)` keep backward-compatible defaults so no caller breaks unprepared.
