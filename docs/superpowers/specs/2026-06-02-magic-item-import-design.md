# Magic Item Compendium — bulk YAML import (Phase 2)

**Date:** 2026-06-02
**Status:** Design approved, ready for plan
**Depends on:** `2026-06-02-magic-item-enchantments-design.md` (Phase 1 must be
merged — this phase is pure data against the Phase-1 models).
**Execution:** Deferred to a separate session. Pure data entry; no model/engine
changes. If a source item cannot be expressed by the Phase-1 models, **stop and
flag it** rather than inventing a model change here.

## Goal

Translate every markdown source in `import/markdown/` into YAML game data, with
**full descriptions**, against the Phase-1 models. Replace the placeholder
equipment data (`magic_items.yaml`, `adventuring_gear.yaml`, `containers.yaml`);
keep `weapons.yaml`, `armor.yaml`, `weapon_qualities.yaml` (real base catalog,
extended in Phase 1 with `groups`/`ac_bonus`).

## Sources → targets

| Source markdown | Target YAML | Model |
|---|---|---|
| `items/advanced-fantasy_adventuring-gear.md` | `adventuring_gear.yaml` (+ `containers.yaml`) | `AdventuringGear` / `Container`, with `description` |
| `magic-items/...magic-swords.md` | `enchantments.yaml` | `Enchantment` (`kind: weapon`, `applies_to: include [sword]`) |
| `magic-items/...magic-weapons.md` | `enchantments.yaml` | `Enchantment` (`kind: weapon`, per weapon type; generic uses `exclude: [sword]`) |
| `magic-items/...magic-armour-and-shields.md` | `enchantments.yaml` | `Enchantment` (`kind: armor`/`shield`) |
| `magic-items/...magic-potions.md` | `magic_items.yaml` | `MagicItem` (description-only; not equippable) |
| `magic-items/...magic-rings.md` | `magic_items.yaml` | `MagicItem` (equippable; passive `modifiers` where they apply, else description + charges) |
| `magic-items/...magic-rods-staves-wands.md` | `magic_items.yaml` | `MagicItem` (charged; `charge_dice` per type: rods 1d10, staves 3d10, wands 2d10) |
| `magic-items/...miscellaneous-magic-items.md` (~131 items) | `magic_items.yaml` | `MagicItem` (mostly description-only; passive `modifiers` for the few stat items) |

## Translation rules

### Enchantments (combat files)

- One `Enchantment` per distinct magical property, **not** per base type. The
  base type is chosen at acquisition; `name_template` uses `{base}`.
- `magic_bonus` = the enchantment bonus (negative for cursed); applies to to-hit
  & damage (weapons) or AC (armour/shield).
- `conditional_bonus: {vs, bonus}` for "+N vs <creature type>" lines — `bonus`
  is the **additional** amount on top of `magic_bonus`.
- Passive side-effects → `modifiers` (e.g. Luck Blade `save:all +1`; Sword of
  Defender `ac`; Holy Avenger `save:spells +4`). Activated/conditional powers
  (Flaming, Dancing, Vorpal, Energy Drain, Wishes, Frost Brand protections) →
  **`description` only**; charged ones also set `charge_dice`/`max_charges`.
- `applies_to`:
  - Sword chart entries → `include: [sword]`.
  - Weapon chart entries → `include: [<weapon-type>]` (axe, mace, spear,
    trident, war_hammer, dagger, crossbow, bow, sling, staff, javelin, arrow…).
    A generic "+1/+2/+3 any weapon" (if authored) uses
    `include: [any_weapon], exclude: [sword]`.
  - Weapon-type-locked specials (Quickness→short sword, Dwarven
    Thrower→war hammer, Buckle→dagger) → `include: [<base_id>]`.
  - Armour chart: `Armour +N` → `kind: armor, include: [any_armour]`;
    `Shield +N` → `kind: shield, include: [any_shield]`; cursed armour AC
    penalty → negative `magic_bonus`; cursed "AC 9 [10]" → `modifiers: [{target:
    ac, op: set, value: 9}]`.
- `cursed: true` on cursed entries (display flag only).
- The base weapons/armours referenced by `include` must exist in
  `weapons.yaml`/`armor.yaml` with the right `groups`. Add any missing base types
  (e.g. `short_sword`, `two_handed_sword`, `war_hammer`, `trident`, `javelin`,
  `arrow`, `sling`, `bow`) with book-accurate stats while importing — flag if a
  base's stats aren't derivable from the source.

### Magic items (potions / rings / rods-staves-wands / misc)

- Each becomes a `MagicItem` with `item_type: magic`, `magic: true`, `cost_gp:
  0`, `description` = the full book text.
- `equippable: true` only for worn/held items whose effect is continuous while
  worn (rings, cloaks, bracers, boots, amulets, gauntlets, girdles, periapts…).
- **Passive `modifiers`** only where an equipped item continuously changes a
  modelled derived stat:
  - Ring of Protection → `ac +1`, `save:all +1`.
  - Gauntlets of Ogre Power → `ability:STR set 18`, `carry_capacity +1000`.
  - Girdle of Giant Strength → `thac0 set_max …` (+ damage note).
  - Bracers of Armour → `ac set <value>` (set-base-AC); Medallion → `ac set 6`;
    Bracers of Defencelessness (cursed) → `ac set 9`.
  - Cloak of Defence/Protection, Ring of Protection 5' radius → `ac`/`save`.
  - Periapt/Medallion of save bonuses → `save:*` targets.
  - Ring of Weakness (cursed) → `ability:STR set 3`.
- Everything else (activated: invisibility, charm, teleport, summon, flying,
  regeneration heals, spell-granting books, crystal balls…) → **description
  only**. Heals are play-state, not `max_hp`. Spell items are activated, not
  passive — no spell modifiers.
- Charged items (rods/staves/wands, charged rings/misc) → `charge_dice` per the
  type defaults (rods 1d10, staves 3d10, wands 2d10) unless the item overrides.
- Categories: keep meaningful `category` values (`magic_potions`, `magic_rings`,
  `magic_rods_staves_wands`, `miscellaneous_magic_items`) for sheet grouping.

### Adventuring gear

- Re-import `adventuring_gear.yaml` from the gear markdown **with descriptions**;
  preserve ids already referenced elsewhere in the app/tests where present (flag
  any rename that would break references). Reconcile container entries
  (Backpack, Sacks) with `containers.yaml` / the `Container` model
  (`capacity_cn`, coins-held → cn).

## Out of scope

- d% random-treasure generation tables (GM tooling — not character data).
- Acquisition-time random choices (Dragon Slayer's dragon type, Arrow of
  Slaying's foe) — left to the item `description` / instance `note`.
- Any model/engine change. If the source needs one, **stop and flag** for a
  follow-up to the Phase-1 spec.

## Verification

- `GameData.load` parses all files with no validation errors.
- Spot-check: a sword enchantment composes onto bastard sword **and** lightsaber;
  a generic weapon `+1` does **not** appear for swords; a ring with passive
  modifiers changes AC/saves on the sheet when equipped.
- Per the project rule, **verify encoded rules against the source markdown / PDF**
  before finalising (numbers, charges, save types).
- Full test suite green.
