# Ammunition — loading, counts, and magic-ammo bonus conferral

**Date:** 2026-06-02
**Status:** Design approved, ready for plan
**Relationship to Phase 2 import:** This feature is a **prerequisite** for encoding
the magic-ammunition entries (Arrows +1/+2, Arrow +1 Slaying, Crossbow Bolts
+1/+2, Sling Bullet +1 Impact) from
`import/markdown/magic-items/advanced-fantasy_magic-magic-weapons.md`. The
"ammo as base weapons" idea in `2026-06-02-magic-item-import-design.md`
(Tasks 1 & 5) is **dropped** and replaced by this model. The import plan will be
revised to depend on this work.

## Problem

Ammunition (arrows, crossbow bolts, sling stones) is currently unmodelled.
Ammo is **not** a weapon: it has no damage, no weapon qualities. It is loaded
into a ranged *launcher* (bow / crossbow / sling) and consumed. Magic ammo
(e.g. *Arrows +1*) confers its magical bonus to the launcher it is loaded in.
The Phase-1 magic-item spec deferred this with an explicit "stop and flag" —
this is that follow-up.

## Goals

1. A purchasable mundane-ammo catalog (from the book's Ammunition table), so
   characters can buy ammo.
2. Per-character ammo **stacks with counts**; identical ammo **combines**; counts
   are **manually adjustable** (no automatic per-shot "shooting").
3. **Loading** one ammo stack into a ranged launcher; a launcher with nothing
   loaded is **flagged "Unloaded"** on the sheet.
4. **Magic ammo via enchantment composition** (consistent with magic
   weapons/armour): a base ammo + an `Enchantment` of `kind: ammunition`.
5. A loaded magic ammo **confers its `magic_bonus` (and `conditional_bonus`)** to
   the launcher's attack line, **additively** with the launcher's own bonus
   (a +1 arrow in a +1 bow = +2 to-hit and damage).

## Non-goals (YAGNI)

- Rate of fire / shots-per-round.
- Automatic decrement on attack ("shooting"). Counts change only via the manual
  `+`/`−` adjust control.
- Recovering spent ammo after combat.
- Silver-as-a-mechanical-material (silver remains a base id/name + description,
  exactly as `silver_dagger` is today; "silver bypasses immunity" stays
  narrative).
- Partial-bundle pricing (a purchase always grants a whole `bundle_count`).
- Ammo encumbrance. **By design ammo has zero weight**: the listed weight of a
  missile weapon already includes its ammunition and container.
- Data migration (the app is single-user, not deployed; new fields default
  empty — see the project "no migrations" rule).

## Encumbrance note (from the source)

> The listed weight of missile weapons already includes the weight of the
> ammunition and its container.

Therefore every `Ammunition` entry has `weight_cn: 0` and ammo is never counted
by `aose/engine/encumbrance.py`.

## Source: the mundane Ammunition table

| Ammunition | Cost (gp) | Bundle |
|---|---:|---|
| Arrows (quiver of 20) | 5 | 20 |
| Crossbow bolts (case of 30) | 10 | 30 |
| Silver tipped arrow (1) | 5 | 1 |
| Sling stones | Free (0) | 20 |

## Data model

### New `Ammunition` item variant (`aose/models/item.py`)

```python
class Ammunition(ItemBase):
    item_type: Literal["ammunition"]
    groups: list[str] = Field(default_factory=list)  # match tags (e.g. [arrow])
    bundle_count: int = 1                              # units granted per purchase
    # weight_cn defaults to 0 (ItemBase default); ammo never weighs in.
```

Added to the `Item` discriminated union. No `damage`/`qualities`/`hands`.

### `Weapon` gains `accepts_ammo`

```python
accepts_ammo: list[str] = Field(default_factory=list)
```

The ammo groups a launcher fires. **Non-empty ⇔ "needs ammo loaded."**
- `short_bow`, `long_bow` → `[arrow]`
- `crossbow` → `[crossbow_bolt]`
- `sling` → `[sling_stone]`
- Thrown weapons (dagger, spear, **javelin**, hand_axe, etc.) keep it empty and
  are never flagged unloaded.

`aose/engine/enchant.py::resolve_weapon` must copy `accepts_ammo` onto the
synthetic weapon so an enchanted +1 bow still accepts arrows.

### `Enchantment.kind` extends to `"ammunition"`

`kind: Literal["weapon", "armor", "shield", "ammunition"]`. Ammo enchantments
match a base ammo by group/id token or the new `any_ammunition` wildcard. They
carry `magic_bonus` and optionally `conditional_bonus` (the fields already
modelled); activated/charged ammo powers go in `description`.

### Per-character state (`aose/models/character.py`)

```python
class AmmoStack(BaseModel):
    instance_id: str
    base_id: str
    enchantment_id: str | None = None
    count: int = 0
```

```python
# on CharacterSpec:
ammo: list[AmmoStack] = []
loaded_ammo: dict[str, str] = {}   # weapon_key -> AmmoStack.instance_id
```

- Stacks **combine** when `(base_id, enchantment_id)` match (counts sum).
- `weapon_key` is the plain weapon id (mundane launcher) **or** the
  `EnchantedInstance.instance_id` (an enchanted launcher), matching the attack
  row's identity so loading works for both.

## Engine — `aose/engine/ammo.py` (new, cycle-free)

Imports only models, loader, dice, and `enchant` (for matching/name). All
mutators return a **new** list/dict (the established style in `enchant.py`,
`magic.py`), raising typed errors on bad ids.

- `accepts(weapon, ammo_base) -> bool` — true when any `ammo_base.groups`/id ∈
  `weapon.accepts_ammo`.
- `compatible_ammo(weapon, spec, data) -> list[AmmoStack]` — stacks loadable into
  the launcher.
- `buy_ammo(stacks, gold, base_id, data) -> (stacks, gold)` — validates a mundane
  `Ammunition` base, subtracts `cost_gp`, adds `bundle_count`, combining.
  Raises on insufficient gold.
- `add_free_ammo(stacks, base_id, enchantment_id, data) -> stacks` — GM grant;
  validates base is `Ammunition` and the enchantment (if any) is `kind:
  ammunition` and compatible with the base; default `count = 1`; combining.
- `adjust_count(stacks, instance_id, delta) -> stacks` — clamp ≥ 0; **count 0
  removes the stack** (caller also clears any `loaded_ammo` pointing at it).
- `remove_ammo(stacks, instance_id) -> stacks`.
- `load(loaded, weapon_key, instance_id) -> loaded` / `unload(loaded,
  weapon_key) -> loaded`.
- `loaded_stack(weapon_key, spec, data) -> AmmoStack | None`.
- `loaded_bonus(weapon_key, spec, data) -> (int, ConditionalBonus | None)` — the
  loaded enchanted ammo's `magic_bonus`/`conditional_bonus`, else `(0, None)`.
- `is_unloaded(weapon_key, weapon, spec, data) -> bool` — `weapon.accepts_ammo`
  non-empty and no valid loaded stack (or its count is 0).
- `resolve_ammo(stack, data)` — display view: name (`base.name` +
  `enchantment.name_template`), `magic_bonus`, `conditional_bonus`.

`enchant.py`: add the ammunition nature (`_is_ammunition`), the `any_ammunition`
wildcard, and the `kind == "ammunition"` branch in `_nature_matches_kind`, so
`is_compatible`/`compatible_bases` work for ammo (e.g. `silver_arrow` +
`arrow_slaying`).

`attacks.py`: for each equipped launcher, add `loaded_bonus`'s `magic_bonus` to
to-hit and damage (additive with `weapon.magic_bonus`) and surface the loaded
ammo's name + `conditional_bonus`. An unloaded launcher renders with an
**"Unloaded"** flag and no ammo bonus.

## Data files

- **New `data/equipment/ammunition.yaml`** — mundane buyable ammo:
  `arrow` ("Arrows (quiver of 20)", 5 gp, bundle 20, `groups: [arrow]`),
  `crossbow_bolt` ("Crossbow Bolts (case of 30)", 10 gp, bundle 30,
  `groups: [crossbow_bolt]`), `silver_arrow` ("Silver-Tipped Arrow", 5 gp,
  bundle 1, `groups: [arrow]`), `sling_stone` ("Sling Stones", 0 gp, bundle 20,
  `groups: [sling_stone]`). All `weight_cn: 0`, `category: ammunition`.
- **`data/enchantments.yaml`** — ammunition enchantments (`kind: ammunition`):
  `arrows_plus_1` (+1, `[arrow]`), `arrows_plus_2` (+2, `[arrow]`),
  `arrow_slaying` (+1, `[arrow]`, description: acts as +3 & slays a GM-chosen
  foe), `crossbow_bolts_plus_1` (+1, `[crossbow_bolt]`),
  `crossbow_bolts_plus_2` (+2, `[crossbow_bolt]`), `sling_bullet_impact`
  (+1, `[sling_stone]`, description: bonus damage on a high roll).
- **`data/equipment/weapons.yaml`** — add `accepts_ammo` to the two bows,
  crossbow, and sling. (The bows also gain `groups: [bow]` for the `bow_plus_1`
  launcher enchantment — that part is unchanged from the import plan.)

## UI / routes (sheet + wizard share, mirroring the equipment routes)

- The auto-globbed `ammunition` category appears in the shop; the **wizard**
  equipment step (mundane-only) can buy and load ammo.
- **Sheet Ammunition section**: each stack shows name + count + `+`/`−` adjust +
  remove; each equipped launcher shows a **load dropdown** of compatible stacks
  and an **Unloaded** flag when empty.
- **Magic ammo is Add-only** (GM grant) on the sheet, via a base-ammo +
  ammunition-enchantment picker parallel to the existing enchanted-item picker.
- Routes: `/ammo/buy`, `/ammo/add`, `/ammo/adjust`, `/ammo/remove`,
  `/ammo/load`, `/ammo/unload`.
- Attack rows for launchers display the combined bonus + loaded ammo name (or the
  Unloaded flag).

## Verification

- `GameData.load` parses `ammunition.yaml` and the ammo enchantments with no
  errors; bows carry `accepts_ammo`.
- A +1 bow loaded with +1 arrows yields a +2 ranged attack line; a mundane bow
  with +1 arrows yields +1; an unloaded bow shows the Unloaded flag.
- `silver_arrow` is compatible with `arrow_slaying`.
- Buying a quiver adds 20 to the arrow stack and subtracts 5 gp; a second quiver
  combines into the same stack (count 40).
- Adjusting a loaded stack to 0 removes it and clears the load.
- Full test suite green.
