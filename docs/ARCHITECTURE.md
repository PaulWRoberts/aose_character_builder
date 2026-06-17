# AOSE Character Builder — architecture reference

The living design of each subsystem: where it lives, the key models, and the
hard-won invariants. This is the deep reference; [CLAUDE.md](../CLAUDE.md) is the
quick orientation and [CHANGELOG.md](CHANGELOG.md) is the dated landing ledger.
Full per-feature designs live in `docs/superpowers/{specs,plans}/`.

The engine modules are **pure derivations** and deliberately **cycle-free**. The
import DAG is roughly: `models → loader → magic → features → {armor_class,
saves, attacks}`, with `currency`, `valuables`, `encumbrance`, `ammo`,
`enchant`, `spells`, `spell_sources`, `secondary_skills`, `sources` hanging off
models/loader only.

---

## The modifier pipeline (the core abstraction)

Almost every numeric bonus in the app — magic items, class/race features, WIS
saves — flows through one shared pipeline.

- **`Modifier`** (`aose/models/modifier.py`) — `target` / `op`
  (`add`|`set`|`set_min`|`set_max`) / `value`, plus `condition: str | None` and
  `source: str` (feature/item name, for hover). Target families seen so far:
  `ac`, `thac0`, `attack`, `damage`, `save:<cat>`, `save:vs:<thing>`, `initiative`
  (inert — consumed only by `engine/initiative.py`), and ability targets.
- **`apply_modifiers`** (`aose/engine/magic.py`) applies ops in the fixed order
  `set → add → set_min → set_max`. This is the literal evaluation core.
- **`active_modifiers`** (magic.py) collects modifiers from equipped magic items;
  **`feature_modifiers`** (`aose/engine/features.py`) collects them from class
  features (gated by `gained_at_level`) and race features (all) — **except for a
  race-as-class character** (`is_race_as_class`: single class whose `race_locked`
  equals `race_id`), whose linked race is skipped entirely. Their union is
  **`all_modifiers`**, the single thing every consumer reads.
- **Consumers** (`armor_class`, `saves`, `attacks`) read `all_modifiers`. Saves
  apply `save:*` with a floor of 2; THAC0 applies `thac0` mods.
- **Conditions are inert-but-carried**: a modifier with a condition a consumer
  can't evaluate is *kept* in the data but *excluded* from the headline number,
  never inflating it. Known conditions are evaluated; unknown ones surface as
  breakdown lines (see next section). `unarmored` AC bonuses drop when armour is
  worn; `ranged`/`melee` attack/damage mods filter per weapon.

### `GrantedModifier` + `Scaling` (data-driven feature bonuses)

`GrantedModifier` (modifier.py) declares a modifier a class/race feature grants:
same `target`/`op`/`condition` grammar, plus exactly one of `value` (flat) or
`scale` (a `Scaling` with `by: level | ability:X` and a banded
`table: dict[int, int]`). `ClassFeature` and `RaceFeature` each carry
`granted_modifiers: list[GrantedModifier]`. `features.py` resolves them
(`_band_lookup` = greatest key ≤ input, 0 below the lowest band; level-scaling is
class-only). **No engine code references any class or race id** — all of it is
data. Examples encoded: barbarian Agile Fighting (`ac add unarmored`, level-
scaled), halfling Missile Attack Bonus (`attack +1 ranged`), dwarf/halfling/
duergar/gnome CON-scaled save resilience, Kineticist level-AC (a level-scaled
`ac set` granted modifier — the old `ClassLevelData.armor_class` column was
retired onto this path).

**`mechanical.requires_rule` — per-feature visibility gating:** a feature whose
`mechanical` dict carries `requires_rule: <flag>` is hidden from the sheet
when the named `RuleSet` flag is `False`. This is enforced in
`_feature_visible()` (view.py), called by both `_race_features` and
`_class_features`. Used for halfling's "Initiative Bonus (Optional Rule)" — shown
only when `individual_initiative` is on — while human's "Decisiveness" (no
`requires_rule`) always appears.

**`engine/initiative.py` — display-only breakdown:** `initiative_detail(spec,
data)` assembles `InitiativeDetail{base, total, lines, has_conditional}` from
the DEX initiative modifier (`ability_mods.initiative_modifier`) plus any
`initiative`-target grants in `all_modifiers`. It is only rendered when
`RuleSet.individual_initiative` is set; none of the core derivations (AC, saves,
attacks) import it. The `CharacterSheet` carries `initiative_modifier`,
`initiative_lines`, and `initiative_has_conditional` for the Combat box INIT
field and its breakdown modal.

**Generic `mechanical` keys beyond `granted_modifiers`:** `features.py` also
exposes collectors that read arbitrary `mechanical` dict keys off reached
features via `iter_reached` (the canonical "which features apply" generator —
class features gated by `gained_at_level`, chosen options, and race features /
chosen race options suppressed for race-as-class): `feature_weapons` reads
`mechanical["weapon"]` descriptors to produce synthetic always-on
`AttackProfile`s (the gargantua's thrown rock, Mutoid claws, Mycelian fists —
declared as `name`/`damage`/`melee`/`ranged`/etc. in the feature YAML; a
`damage_per_level_die` key resolves to `"{level}{die}"` at render time);
`open_doors_category_bonus` sums `mechanical["str_category_bonus"]` for the STR
ability table bump (gargantua Open Doors). Both follow the same race-as-class
guard, so a character who is race *and* class never double-counts.

**Feature choices (`FeatureChoice` / `ChoiceOption`):** A Race or CharClass can
declare `feature_choices: list[FeatureChoice]`, each being a "pick N (or roll)"
group. Selections live on `CharacterSpec.feature_choices: dict[str, list[str]]`
(group id → chosen option ids). Chosen `ChoiceOption`s are feature-shaped
(`mechanical`, `granted_modifiers`, `daily_uses`, `spell_id`), so they flow
through `iter_reached` / `feature_modifiers` / `feature_weapons` with no
per-option engine code. Engine: `aose/engine/feature_choices.py`
`roll_choice`/`validate_choice`/`effective_pick`. Selected features render on the sheet alongside
normal class/race features.

*Level-banded pick count:* `FeatureChoice.pick_by_level: dict[int, int]` gives
the number of picks at each level band (e.g. `{1:1, 5:2, 10:3}`). `effective_pick(group,
level)` returns the right count; at creation (wizard) level is always 1.
Groups with `pick_by_level` feed the **unspent-capacity** mechanism below.

*Rule gating:* `FeatureChoice.requires_rule: str` hides a group unless
`spec.ruleset.<field>` is True. `ChoiceOption.excluded_when_rule: str` hides a
single option (Weapon specialist hides when `weapon_proficiency` is on).
All gating flows through the single chokepoint `_active_choice_groups` (wizard)
and the equivalent filter in `_level_choice_extras` (sheet).

*Parameterised options:* `ChoiceOption.param: OptionParam` declares a player-chosen
free value. `kind="text"` stores the value in `CharacterSpec.choice_params: dict[str,str]`
keyed by option id; `feature_modifiers` substitutes it into any `{param}` in a
modifier's `condition` (Slayer: `"vs {param}"` → `"vs dragons"`).
`kind="weapon"` writes the value directly into `spec.weapon_specialisations`
(Weapon specialist).

**Wizard feature-choices flow:** `class_setup` step shows a picker (roll-first
for groups with `roll_dice`; manual checkbox grid for groups without, like Combat
Talents). `POST /{id}/feature-choices/roll?group_id=X` rolls one table; Strict Mode
locks after the first roll; non-strict allows re-roll and manual override via
`POST /{id}/feature-choices` which calls `_apply_feature_overrides` (reads
`param_<option_id>` fields for parameterised options). Cascading clear in
`_apply_rule_changes` removes `feature_choices["combat_talents"]`,
`choice_params`, and any talent-granted `weapon_specialisations` when
`combat_talents` is toggled off.

**Unspent-capacity mechanism (`aose/engine/level_choices.py`):** A subsystem-agnostic
`Capacity(kind, group_id, label, earned, spent)` model tracks how many selections
a character has earned vs. spent for any pick-granting subsystem. Two providers:
`proficiency_capacity(spec, data)` (weapon-proficiency slots from THAC0 progression)
and `talent_capacities(spec, data)` (one entry per level-banded group whose rule is
active). `all_capacities` aggregates both and returns only those with `remaining > 0`.
The sheet exposes these as `level_choices`, with matching pickers rendered by
`_levelup_choices.html` (proficiency: `POST /character/{id}/proficiency/add`;
talent: `POST /character/{id}/talent/add`). The level-up modal shows a reminder
note when any capacity is outstanding. `CharacterSheet.proficiency_weapon_options`
and `talent_options` carry the selectable choices for the pickers.

**Weapon specialisation gate:** `attacks.py:_profile_for` checks `spec.ruleset.weapon_proficiency OR spec.ruleset.combat_talents` for `is_specialised`. Under proficiency the weapon must also appear in `weapon_proficiencies`; under combat talents (Weapon specialist) it need not — the two subsystems are mutually exclusive via the `excluded_when_rule` gate.

**Race vs race-as-class are distinct stat blocks that share only a name.** A
race-as-class character is defined wholly by its `race_locked` `CharClass`; the
linked `Race` contributes *nothing* (no features, no feature-grants, no ability
modifiers — see `is_race_as_class` in features.py / `_race_features` in view.py).
The `Race` is read only in split mode. Consequently a grant a demihuman has in
*both* modes (Light Sensitivity, Defensive Bonus, Missile Bonus, …) is authored
on **both** the race file (split mode) *and* the race-locked class file
(race-as-class) — duplication is intentional, and the class's own `features:`
list is the source of truth for which grants a race-as-class receives. A feature
the class omits (e.g. Resilience / Magic Resistance, which are race-only Advanced
abilities) therefore does **not** apply to the race-as-class.

### Conditional / situational breakdowns

When a conditioned modifier can't fold into a headline, it surfaces as a
breakdown line. Three parallel implementations, all the same shape (registry of
condition → display note, with underscore fallback):

- **AC** — `armor_class.py`: shared `_compute_ac` helper feeds both
  `armor_class()` and `armor_class_detail() -> ACBreakdown` (`ACModLine`s).
  Headline excludes anything not `unarmored`. `_AC_CONDITION_NOTES`
  (`bright_light`, `large_attacker`). Sheet: `ac_lines` + `ac_has_conditional`,
  `★` opens `modal-ac`. Data: Light Sensitivity (`ac -1 bright_light`, drow/
  duergar/svirfneblin), Defensive Bonus (`ac +2 large_attacker`, gnome/
  svirfneblin/halfling).
- **Attack** — `attacks.py`: `attack_modifiers_detail() -> AttackBreakdown`
  (`AttackModLine`s; unconditional global mods first, then situational;
  `ranged`/`melee` excluded as those are per-weapon). `_ATTACK_CONDITION_NOTES`
  (`bright_light`, `mounted`). Sheet: `attack_lines` + `attack_has_conditional`,
  `★` opens the retitled `modal-matrix` ("Attack"), to-hit matrix gated to
  descending AC. Data: Light Sensitivity (`attack -2 bright_light`, on **both** the
  race file and the race-locked class file — race and race-as-class are separate
  self-contained stat blocks; see the `GrantedModifier` section), Knight Mounted
  Combat
  (`attack +1 mounted`). Per-weapon conditional bonuses (Sword +1, Giant Slayer)
  are separate: `Weapon.conditional_bonus` → `ConditionalAttack`, own row.
- **Saves** — `saves.py`: `saving_throws_detail() -> dict[str, SaveBreakdown]`
  (each carries `base` from class progression, `modified` headline = unconditional
  mods only floored at 2, and `lines: list[SaveModLine]`). `saving_throws()`
  delegates to it. Condition notes: `magical` → "magical effects only", `poison`
  → "poison only (not death magic)", `paralysis` → "paralysis only (not
  petrification)". Sheet `SheetSave` carries `base`/`modified`/`lines`; rows are
  clickable per-save modals.

### Situational "vs X" save bonuses (`save:vs:*`)

A distinct target family `save:vs:<thing>` (e.g. `save:vs:fire`). Collected via
the same `all_modifiers` pipeline but handled separately:
`situational_save_bonuses() -> list[SituationalSaveBonus]` (groups by
source+value, collects `things`; display registry `_VS_DISPLAY` with underscore
fallback). **Never** folded into a headline or a per-category modal — shown only
as smaller-font footnotes under the saving throws (`SheetSituationalSave`,
`.save-note`), also on the print sheet. Data: druid Energy Resistance
(`fire`/`lightning` +2), svirfneblin Illusion Resistance (`illusion` +2),
kineticist Mental Defence (`mental_powers` +2), knight Strength of Will
(`charm`/`hold` +4, `illusion` +2, at level 3).

---

## Abilities, magic items & charges

- **Magic items are data-driven.** `MagicItem` is an `Item` union variant
  (`item_type: magic`, `equippable`, `modifiers`, `max_charges`/`charge_dice`);
  `ItemBase` carries `description` + a cross-cutting `magic` flag. Per-instance
  state on `CharacterSpec.magic_items` (mirrors `ContainerInstance`); modifiers
  apply only when `equipped`.
- **`aose/engine/magic.py`** is the cycle-free core (imports only models + loader
  + dice): `apply_modifiers`, `active_modifiers`, `effective_abilities`,
  `carry_capacity_bonus`, `needs_instance`, plus instance/charge helpers
  (`new_magic_instance`, `add_free_magic_item`, `equip_magic`/`unequip_magic`,
  `use_charge`/`reset_charges`, `remove_magic`, `set_magic_note`).
- **Effective abilities** flow everywhere: AC over effective DEX, attacks use
  effective abilities, HP recomputes from effective CON. A `*` marks modified
  abilities on the sheet.
- **`RolledModifier`** (modifier.py) + `MagicItem.rolled_modifiers`: dice rolled
  at acquisition time and baked into `extra_modifiers` — e.g. Bracers of Armour
  (AC `8 − 1d4`).
- **Native magic weapons/armour** stay `Weapon`/`Armor` with a `magic_bonus`
  field (Armor also `weight_multiplier` for half-weight enchanted armour). A
  synthetic always-first **Unarmed** profile (1d2, STR) leads the attack list.
- Acquisition is **Add-only** (GM grant, no Buy/gold). Escape hatch: free-text
  `note` + homebrew `extra_modifiers`. No magic-item drag-and-drop.
- Seed: `data/equipment/magic_items.yaml` (auto-loaded by the equipment glob —
  there is no `ITEM_FILES` list).

### Enchantment composition

Magic weapons/armour/ammo are **composed**, not hand-authored. An `Enchantment`
registry (`data/enchantments.yaml` → `GameData.enchantments`) is independent of
any base; a per-character `EnchantedInstance` pairs `base_id` + `enchantment_id`.
`aose/engine/enchant.py` resolves the pair to a synthetic `Weapon`/`Armor` on the
fly. Tag-based matching (`groups`, `Armor.ac_bonus`, kind wildcards
`any_weapon`/`any_armour`/`any_shield`/`any_ammunition`) means a new base is
adopted by every compatible enchantment with no YAML changes. Shield `ac_bonus`
is a data field, not a constant.

---

## Attacks & ammunition

- **Weapon qualities are the source of truth for weapon mechanics.** `Weapon.qualities: list[QualityRef]` — authored in YAML as bare ids (`melee`, `two_handed`) or one-key parametric dicts (`{missile: [s,m,l]}`, `{versatile: "die"}`). Computed properties (`melee`, `ranged`, `hands`, `versatile`, `range_*`, `two_handed_damage`, `deals_damage`) are derived from qualities; nothing is stored. The loader validates every quality ref against the `WeaponQuality` registry (`_validate_weapon_qualities`). No-damage weapons (`net`, `blowgun`) have `damage.default == ""`. Under the variable-damage rule, a `{versatile: "die"}` weapon emits a second `(Two-handed)` attack profile in `attacks.py`.
- **`aose/engine/attacks.py`** uses effective abilities, `magic_bonus`, global
  `attack`/`damage` mods, the conditional variant, and the synthetic Unarmed
  profile. A second synthetic profile category — **feature weapons** — is emitted
  by `_feature_weapon_profile` for each descriptor in `feature_weapons(spec,
  data)`: always proficient, no manage link, no catalog entry; ranged ⇒ DEX to
  hit + flat damage, melee ⇒ STR to hit and damage. The gargantua's thrown rock
  is the first example (range 50/100/150 ft, 1d6, ranged/blunt).
- **Ammo is *not* a weapon.** `Ammunition` item variant (`item_type:
  ammunition`, `groups`, `bundle_count`, **`weight_cn: 0` always** — the missile
  weapon's listed weight already includes ammo, so ammo never touches
  `encumbrance.py`). Buyable table in `data/equipment/ammunition.yaml`.
- Launchers carry `Weapon.accepts_ammo` (non-empty ⇔ needs ammo; bows `[arrow]`,
  crossbow `[crossbow_bolt]`, sling `[sling_stone]`, blowgun `[blowgun_dart]`;
  thrown weapons stay empty).
- Per-character `CharacterSpec.ammo: list[AmmoStack]` (`{instance_id, base_id,
  enchantment_id, count}`, stacks combine on `(base_id, enchantment_id)`; counts
  adjusted manually — no auto-shooting) + `loaded_ammo: dict[weapon_key,
  instance_id]` (weapon_key = resolved weapon `.id`, i.e. catalog id or
  `ench:<instance_id>`).
- Magic ammo is enchantment composition (`arrows_plus_1/2`, `arrow_slaying`,
  etc.). `aose/engine/ammo.py` owns stacks/loading/bonus. Loaded ammo's
  `magic_bonus` adds **additively** with the weapon's own bonus (+1 arrow in +1
  bow = +2); an empty launcher is flagged `unloaded`.
- **Quality-based weapon allowance** — `CharClass.weapon_qualities_allowed: list[str]`
  grants a class permission to use any weapon that carries a matching quality id.
  `aose/engine/proficiency.py` expands `allowed_weapon_ids` to include every
  catalog weapon whose qualities include any listed id. Cleric and Acolyte carry
  `weapon_qualities_allowed: [blunt]`, which automatically covers all current and
  future blunt weapons (club, mace, flail, blackjack, etc.) without enumerating
  individual ids.

---

## Spells, spell books & mental powers

- **`SpellList` registry** (`aose/models/spell_list.py`, `data/spell_lists.yaml`:
  id → `caster_type` arcane|divine|mental) is the single home for the
  known-vs-prepared distinction. A class derives behaviour from the list(s) in
  `CharClass.spell_lists` — no per-class flag.
- **`ClassEntry`** carries `spellbook` (known; arcane *and* mental reuse it as the
  "chosen subset"), `slots: list[SpellSlot]` (prepared daily — spell + reversed +
  spent), and `powers_used` (mental daily-use counter; pool = `2 × level`).
- **`aose/engine/spells.py`** (cycle-free): `caster_type_of` (raises on mixed/
  unknown lists), `accessible_levels`, `memorizable_slots`, `known_spells`
  (arcane=spellbook, divine=full accessible list, mental=all on-list not yet
  known), `learnable_spells`, `beginning_spell_count`, the `learn`/`forget`/
  `prepare`/`unprepare` mutators, slot ops (`assign_slot`/`cast_slot`/etc.), and
  the power-pool ops (`power_pool`/`spend_power`/`restore_power`/`reset_powers`).
- **Standard vs advanced books** = the `advanced_spell_books` rule. Off: book
  capped at memorizable, free learn-on-level-up. On: INT beginning spells,
  uncapped book, copy-only (no free adds).
- **Cantrips (CC5, `cantrips` rule)** are level-0 arcane spells for *dedicated
  arcane casters* (`spells.is_dedicated_arcane`: arcane caster type + a L1 spell
  slot at level 1). They ride the normal spellbook/slots — `memorizable_slots` /
  `accessible_levels` inject `{0: cantrip_count(level)}` (2/3/4 by level) when
  passed `data`+`ruleset`, so the sheet renders a "Cantrips" group and
  prepare/cast reuse the spell path. Cantrips obey the active book rule: standard
  = free learn, book cap = memorise cap = the cantrip table; advanced = copy-only
  from books/scrolls, uncapped book; the memorise cap stays 2/3/4 in both. The
  dependent `read_magic_cantrip` rule hides the L1 read magic
  (`DEMOTED_READ_MAGIC_IDS`) and auto-grants a level-0 `read_magic_cantrip`
  (beyond the cap) to dedicated arcane casters. Spells:
  `data/spells/carcass_crawler_5_cantrips.yaml`. Source rules wired in
  `SOURCE_RULES["carcass_crawler_5"]`.
- **Arcane reversed** is fixed at memorize time; **divine reversed** is a cast-
  time button only (not stored).
- **Spell books & scrolls** — owned documents as a per-instance `SpellSource`
  (`kind` spellbook|scroll, `caster_type`, `entries` each with a `copy_failed`
  flag) on `CharacterSpec.spell_sources`. `aose/engine/spell_sources.py`:
  create/add/remove, `cast_from_scroll` (expends one; empties → dropped; gated by
  caster-type match), `copy_spell` (Advanced rule; rolls 1d100 vs
  `copy_chance_for_int(effective INT)`; **failure is recorded on the source
  entry, never the character** — same spell stays copyable from another source).
  Sheet-only, Add-only. Protection scrolls live as `MagicItem` catalog data in
  `data/equipment/scrolls.yaml`.
- **Rest** (`/rest/night`, `/rest/full-day`) calls `reset_powers` + slot restore;
  full-day adds 1d3 healing; rest blocked when dead.

### Mental powers caster type

`mental` is a third caster type. No slot levels — a daily-use pool counter.
`spells_view`/`spellbook_view` skip mental; a separate `mental_powers_view` →
`MentalPowersBlock` drives the Mental Powers section (pool pips, Use/Restore/
Reset, known-power list). Routes `/powers/{learn,forget,spend,restore,reset}`.
Kineticist is the only mental class (`data/classes/kineticist.yaml`, source
`carcass_crawler_1`, all on `data/spells/carcass_crawler_kineticist_powers.yaml`).

### Innate daily-use abilities (`aose/engine/innate.py`)

Non-caster analogue of the mental-power pool. A `ClassFeature` or `RaceFeature`
(or chosen `ChoiceOption`) carries `daily_uses: DailyUses` (`per_day: int` and/or
`scales_with_level: bool`). `innate_abilities(spec, data)` iterates `iter_reached`
and collects every feature with `daily_uses`, resolving the max against the
granting class's level. `CharacterSpec.innate_uses: dict[str, int]` tracks
uses-spent; `spend_innate`/`restore_innate`/`reset_innate` mutate it.
Routes `/character/{id}/innate/{spend,restore,reset}` mirror the powers routes.
`rest_night` and `rest_full_day` call `reset_innate`. The sheet renders an
"Innate Abilities" block (column 3, alongside Mental Powers) styled like the
spellbook: each ability is a pip row (ready/spent) that opens a dedicated
`modal-innate-{id}` overlay carrying the Use/Restore forms (plus a spell-detail
expander when `spell_id` is set). The actions **must** live in that standalone
modal, not inline in the row — the global overlay click handler intercepts any
click inside a `[data-modal]` trigger with `preventDefault`, so an inline Use
button would never submit.

### Carcass Crawler 2 / 4 / 5 content (`source: carcass_crawler_{2,4,5}`)

Pure-data import (no new mechanics — same shape as the CC1 duals). **Classes:**
Wood Elf (CC2, 10-level race-as-class, `spell_lists: [druid]` from L1, missile
`attack +1 ranged`, detect-secret-doors / ghoul-immunity / hiding text), Halfling
Hearthsinger (CC4, 8-level, `race_locked: halfling`, no caster, Foster-Friendship /
Lore / Read-Languages skill tables as feature text, Defensive Bonus `ac +2
large_attacker`), Halfling Reeve (CC4, 8-level, `race_locked: halfling`,
`allowed_alignments: [law]`, `spell_lists: [druid]` from L4, Goblin Slayer /
Wolf Hunter as conditional `attack`/`damage +1` grants — surfaced in the
conditional-attack breakdown), Arcane Bard (CC4, 14-level, **not** race-locked,
`spell_lists: [magic_user]` from L2, CS/HN/PP/RL skill tables), Ratling (CC5,
8-level race-as-class, semi-martial, skill tables, Prehensile Tail / Rat Affinity
text), Changeling (CC5, 10-level race-as-class, Back-Stab + Shape-Stealing text,
BE/HN/HS/MS skill tables). **Races:** Wood Elf (–1 CHA +1 WIS), Ratling (–1 CHA
+1 DEX), Changeling (–1 CON +1 CHA) — split-mode duals carrying their own grants.
New language: `dryad` (Wood Elf). The percentage/d6 skill tables are **feature
text only** (no skills engine), matching the acrobat/thief precedent.

### Carcass Crawler 3 content (`source: carcass_crawler_3`)

**Classes:** Beast Master (14-level, no race-lock, animal companion / speak-with-
animals), Dragonborn (10-level, breath weapon ×3/day, Scales +1 AC, `feature_choices:
draconic_bloodline` — pick/roll 1 from 5 colour options, each granting a
`save:vs:<type>` bonus), Mutoid (8-level race-as-class, `feature_choices: mutations`
— pick/roll 2 from 8, some granting synthetic weapons, one granting +2 AC),
Mycelian (6-level race-as-class, no armour, natural AC table via level-scaled `ac
set`, `fists` with `damage_per_level_die: d4`, `fungal_spores` with
`scales_with_level: true`), Tiefling (10-level race-as-class, `feature_choices:
fiendish_gifts` — pick/roll 2 from 10 innate spell-grants with `daily_uses`,
`feature_choices: fiendish_appearance` — 2 cosmetic-only flavour traits). **Races:**
Dragonborn, Mutoid, Mycelian, Tiefling — mirrors of the race-as-class content for
`separate_race_class` mode; no new languages beyond `deepcommon` (already present).

### Carcass Crawler 1 content (`source: carcass_crawler_1`)

**Classes:** Acolyte (scroll-only divine, `spell_lists: [cleric]`, no slots),
Mage (scroll-only arcane, `spell_lists: [magic_user]`, no slots, +2 AC
`granted_modifier`), Gargantua / Goblin / Hephaestan (race-as-class via
`race_locked`). **Races (Advanced):** Gargantua (–1 INT +1 STR, Resilience,
classes Assassin/Barbarian/Cleric*/Fighter/Thief), Goblin (+1 DEX –1 STR,
infravision 60', Resilience, Defensive Bonus, classes Acrobat/Assassin/
Cleric*/Fighter/Magic-user/Thief), Hephaestan (–1 STR +1 CHA, Listening /
Neuropressure only per races.md, classes Acrobat/Assassin/Cleric*/Fighter/
Illusionist/Magic-user/Thief). New languages: `hephaestan`, `language_of_wolves`.

---

## Inventory, containers & encumbrance

- **Inventory shapes** — `inventory: list[str]` (duplicates count toward size);
  `equipped: dict[str, str]` — slots `armor` (body armour), `main_hand` (weapon),
  `off_hand` (shield or off-hand weapon). `equipped_weapons: list[str]` is retired;
  all held items go through named slots. A weapon is equippable into `main_hand` when
  a copy exists in inventory and the slot is empty (or into `off_hand` with the
  `two_weapon_fighting` rule on, the character is `two_weapon_eligible`, and the
  weapon passes `off_hand_eligible`). Hand budget: each item costs 1 or 2 hands
  (`hand_cost`); total cannot exceed 2. Gargantua's `one_handed_two_handed_melee`
  feature flag reduces two-handed melee weapons to 1 hand. Equipped items live
  *inside* `inventory` — weight is counted once. `armor_tailored: bool = True` on
  `CharacterSpec` tracks whether the equipped tailorable armour (full plate) is
  fitted to the wearer — if False, `armor_class.py` uses
  `Armor.untailored_ac_descending` instead. `stashed: list[str]` is off-person
  (no weight). Sheet renders Equipped / Carried / Stashed.
- **Containers** — `Container` catalog variant (`item_type: container`,
  `capacity_cn`, `weight_multiplier`) + per-instance `ContainerInstance`
  (`instance_id`, `catalog_id`, `state`, `contents`) on `CharacterSpec.containers`.
  Items inside aren't in `inventory`/`stashed`; they follow the container's
  carried/stashed state. Carried containers contribute `own_weight +
  int(multiplier × raw_contents)` — a Bag of Holding (×0.06) at 10 000 cn weighs
  600 cn. Capacity uses raw weight. No nesting. Helpers in `shop.py` (`stow`/
  `take_out`/`stash_container`/etc.). Dispatch is by `isinstance(item, Container)`,
  so the file location of a container item is transparent to routes. UI: inline
  collapsible rows, button/dropdown-only (drag-and-drop was removed 2026-06-02).
- **Stackable gear** — `AdventuringGear.bundle_count: int = 1`. `buy()` grants
  `bundle_count` units for one price; `add_free()` always grants one. Sell removes
  1 unit, returns `int((cost_gp / bundle_count) / 2)`; refund removes a full stack,
  returns `cost_gp`. Gear data is book-faithful; the encumbrance engine uses a flat
  **80 cn** for any `AdventuringGear` item, so per-item `weight_cn` is dead data
  and is not fabricated.
- **Encumbrance** (`aose/engine/encumbrance.py`) — two AOSE-faithful modes.
  **Basic** = `_BASIC_TABLE{(armour_cls, carrying_treasure)} → move` (over-1600
  treasure → immobile; `CharacterSpec.carrying_treasure` toggle). **Detailed** =
  single-axis by total weight (bands 400/600/800/1600 → 120/90/60/30/0'); total =
  `treasure_weight_cn` + `equipment_weight_cn`. Magic items band on
  `banding_weight_cn` (raw − `carry_capacity_bonus`) while displaying raw carried
  weight; enchanted armour weighs half. `EncumbranceTable` reshaped accordingly.

---

## Currency, treasure & valuables

- **Multi-coin purse** — `CharacterSpec.platinum/electrum/gold/silver/copper`
  (gp stays the shop-spendable balance). `aose/engine/currency.py` (cycle-free):
  `DENOMINATIONS`/`RATES`/`_ATTR`, `total_value_gp`, `coin_count` (weight, 1 cn
  each), `convert` (make-change, whole-coin enforced, raises `CurrencyError`).
  Routes `/coins/add`, `/coins/convert`.
- **Treasure weight** — gems 1 cn, jewellery 10 cn; carried treasure magic items
  potions 10 / wands 10 / rods 20 / staves 40 / scrolls 1, derived by category +
  id-prefix in `treasure_item_weight` (no YAML edits).
- **Gems & jewellery** — free-acquired, weightless for movement-mode purposes,
  sheet-only treasure. `GemStack` (value + count + label, stacks by value+label)
  and `JewelleryPiece` (full value + `damaged` toggle + label; damaged halves
  value, floor). `aose/engine/valuables.py` owns add/adjust/remove/sell plus
  `roll_jewellery_value` (3d6×100); `GEM_INCREMENTS` is a dropdown affordance, not
  a constraint. Selling adds to `gold`; dropping refunds nothing. Never touches
  `encumbrance.py` directly (weight comes via `treasure_weight_cn`).

---

## Identity: languages, literacy, secondary skills

- **Language registry** — `LanguageData.names: dict[str, str]` maps every id to
  its book-authoritative display name; `display_name(id, lang_data)` does registry
  lookup with a title-case fallback. `data/languages.yaml` `additional:` is a list
  of ids.
- **Granted languages** — `granted_languages(spec, data)` walks race features (all)
  and class features (level-gated) collecting `feature.mechanical["languages"]`
  ids (gnome burrowing-mammals tongue, druid's `druidic`). Granted tongues appear
  in the known list but never in the INT-pick learnable list; the wizard shows them
  under "Granted:".
- **Literacy** — `literacy(spec, data)` → `illiterate` (INT ≤ 5) / `basic`
  (6–8) / `literate` (≥ 9). `mechanical.illiterate_below_level` forces illiterate
  until that level (barbarian: `2` → illiterate at level 1 only).
- **WIS magic-save modifiers** — `wisdom_save_modifiers(spec, data)` builds
  synthetic `Modifier`s from effective WIS: unconditional on `save:spells`/
  `save:wands`; conditional (`magical`) on `save:death`/`save:paralysis`; never on
  `save:breath`.
- **Secondary skills** — `SecondarySkillEntry` (`{name, weight≥1, roll_twice}`),
  `data/secondary_skills.yaml` is the exact d100 table (loader validates the sum =
  100 and exactly one roll-twice). `aose/engine/secondary_skills.py`:
  `selectable_names` (excludes roll-twice), `roll(entries, rng)` (weighted; roll-
  twice expands to two distinct trades, never nests). `CharacterSpec.secondary_skills:
  list[str]`. Roll-first: `GET /identity` never auto-rolls; `POST
  /identity/skill-roll` performs the roll (strict locks after one press; non-strict
  allows re-roll). `POST /identity` requires the skill to be present before
  advancing; non-strict accepts a manual dropdown override.

---

## Characters, leveling & play state

- **Multi-classing** — free-form (Multiple Classes optional rule; no combo
  allowlist). Wizard offers up to 3 classes when `multiclassing` +
  `separate_race_class` are on, each gated by ability requirements +
  `demihuman_class_restrictions`. **XP is per class** (`ClassEntry.xp`, not a
  global). `grant_xp(spec, data, amount)` (`leveling.py`) splits evenly, scales
  each share by that class's prime-requisite multiplier (lowest score among
  multi-prime classes), floors, clamps ≥ 0; clawbacks split evenly without the
  multiplier. **HP** recomputes from raw rolls + effective CON: per gain-event
  `max(1, event_roll_sum / N + CON_mod)` summed as exact `Fraction`s, floored once
  (order-independent; N=1 = the old single-class formula). `hp_remainder` exposes
  the leftover. Saves/THAC0 take the best across classes.
- **Current HP** — `CharacterSpec.damage_taken` (current = `max(0, max_hp −
  damage_taken)`, dead derived from current 0). `aose/engine/hp.py`: `current_hp`/
  `is_dead`/`apply_damage`/`apply_healing`/`set_current_hp`. Routes `/hp/{damage,
  heal,set}`.

---

## Content sources & optional rules

- **Sources** — `Source` model + `data/sources.yaml` (OSE Classic Fantasy + OSE
  Advanced Fantasy + Carcass Crawler 1–5, Necrotic Gnome). A
  `source` field on `ItemBase`/`Race`/`CharClass`/`SpellList`/`Enchantment`/
  `Spell` defaults to `ose_classic_fantasy`; only non-Classic entries carry their
  own id. `CONTENT_CATEGORIES = ("classes", "equipment", "magic_items")` in
  `aose/models/ruleset.py`. `RuleSet.disabled_content: list[str]` stores
  `"{source_id}:{category}"` keys for disabled content; Classic is never added;
  legacy `disabled_sources` is coerced to `disabled_content` at load time via a
  Pydantic `model_validator(mode="before")`. `aose/engine/sources.py`:
  `CLASSIC_SOURCE_ID`, `content_enabled(source_id, category, ruleset)`,
  `source_content_categories(data)` (derives categories from loaded data — no
  per-item tagging). Gated in wizard race/class steps, spell candidates,
  `shop_categories`, `_enchant_choices`. Mid-wizard, changing `disabled_content`
  clears orphaned race/class picks via `_apply_rule_changes`.
- **Optional rules** — every flag in `RuleSet` is integrated end-to-end. The
  settings page never renders a "pending" badge (a regression test guards this).
- **Manual rolls + Strict Mode** — abilities, HP, starting gold, per-table feature
  choices, and the secondary skill each require a deliberate Roll press. Strict Mode
  (default `True`) locks each roll after one press; off = free re-rolls. A hopeless
  ability set (`subpar` or any score 3) re-enables the Roll button under strict.
  Back-nav gates: rolling abilities locks the rules step; rolling HP locks every
  step before HP (`class_setup`) — gates show a 🔒 breadcrumb state.
  `draft["hp_blessed_sets"]` (draft-only, never persisted) stores both Blessed HP
  sets so Class Setup can bold the higher.
- **Class Setup — consolidated advance** — `POST /{id}/hp` is the single "Next"
  handler. Sections present in the consolidated form declare themselves via hidden
  `<input name="section" value="...">` markers (values: `proficiencies`, `spells`,
  `features`); the handler runs `_apply_proficiencies` / `_apply_spells` /
  `_apply_feature_overrides` for each declared section, then saves and advances via
  `_next_incomplete_step`. The per-section routes (`/proficiencies`, `/spells`,
  `/feature-choices`) remain for backward-compat. Client-side `csValidate` enables
  the Next button only when all selection counts match their server-declared
  requirements (`data-required` attributes on `.prof-table` and `.card-grid`).
  `draft["_feature_choice_group_ids"]` (set at class-pick time) lets
  `_feature_choices_complete` determine completeness without threading `data` into
  `_next_incomplete_step`. `feature_choices_done` is retired.

---

## Sheet & UI

- **Zine sheet** — `aose/web/templates/sheet.html`: identity band, 3-column grid
  (combat+abilities, features+notes, spells/powers — column 3 opens for
  `sheet.spellbook or sheet.mental_powers`), full-width inventory/currency/treasure
  group, footer. Groups have inked bars + internal scroll.
- **Design system** — `aose/web/static/sheet.css` (Oswald + Bitter, self-hosted
  woff2 under `aose/web/static/fonts/`). **Read `docs/STYLE-GUIDE.md` before any
  sheet/UI work** — tokens, components, the overlay model, and hard-won invariants
  (closed-overlay `pointer-events`, variable-font self-hosting, `no-cache` static).
- **Overlay controller** — `aose/web/static/sheet_overlays.js`: single-open
  drawer/modal/popover, dismissed by Esc/scrim/close.
- **Tabbed equipment drawer** — `_equipment_ui.html`: Carried (always), Magic
  (gated `magic_acquisition`), Documents (gated `spell_sources`), Treasure (gated
  `valuables`), Shop (always). The wizard shows only Carried + Shop.
- **Print sheet** — `sheet_print.html` mirrors the live sheet; conditional AC/
  attack/save lines and situational `vs:*` bonuses appear as footnotes.
- **`build_sheet(spec, data) -> CharacterSheet`** (`aose/sheet/view.py`) assembles
  every derivation. Block models (`SpellbookBlock`, `MentalPowersBlock`,
  `ACBreakdown`, `AttackBreakdown`, `SaveBreakdown`, `EncumbranceTable`, etc.) live
  alongside it / in their engine modules.
- **Per-item modals** — every clickable entry in the inventory section (carried/
  stashed/equipped gear, containers, ammo, worn magic items) opens a dedicated
  server-rendered `overlay modal` showing properties via `detail_card(row.detail)`
  (i.e. `item_card()` stats + markdown description) and safe management actions
  (equip/unequip, stow, stash/unstash, load/unload ammo, use-charge). Destructive
  actions (drop/sell/refund) are **drawer-only** — never in a sheet modal.
- **`show_remove` boundary** — `_inv_row_actions.html` accepts `show_remove=True`
  (default). Sheet modals pass `False`; the management drawer uses the default.
- **Launcher modals** — equipped weapons that accept ammo expose a Load
  `<select>` + Unload form in their modal, keyed by `manageable_item_id` /
  `ammo_load_options` (both use the plain catalog weapon id).
- **Shop expander** — `ShopItem.detail` (populated by `item_card(i)` in
  `shop_categories`) is rendered via `detail_card` in a `row-detail` expander row
  toggled by `inventory.js` (same pattern as drawer inventory rows). Buy/add
  controls are unaffected — the toggle ignores clicks inside forms/buttons.
- **Wizard card detail surfaces** — race/class cards open a shared zine
  `#wizard-detail` overlay (`wizard.html`) whose body is built by `aose/web/book.py`
  (`class_entry`/`race_entry`/`spell_entry`) and rendered by the `book_entry` macro
  (`_book_entry.html`). Modal Select drives client-side selection (radio/checkbox
  check + grid collapse); Clear restores the grid; multiclass grid collapses at the
  cap (`data-multi`/`data-cap`). The spells step renders the same `book_entry` inline
  as per-card expanders with a Learn/Forget toggle and slot cap. Controller:
  `aose/web/static/wizard_cards.js`; styles: `wizard_cards.css` (reuses zine tokens,
  wizard-only).

---

## Hosting & auth

All auth behaviour is **off by default**. When `AOSE_AUTH` is not set (or `0`)
the app is identical to the local-only single-user build — zero behaviour
change. Auth is enabled by setting `AOSE_AUTH=1`.

- **`AuthConfig.from_env()`** (`aose/web/auth/`) returns `None` (auth off) or an
  `AuthConfig` instance (auth on). The `create_app()` factory accepts an optional
  `auth_verifier` keyword for testing; production uses `FirebaseVerifier`.
- **`WorkspaceAuthMiddleware`** is the single integration point. It resolves
  `request.state.{characters_dir, drafts_dir, settings_path}` from
  `resolve_workspace(request)`. Auth-off: mirrors the global root dirs
  (`characters/`, `drafts/`, `settings.json`). Auth-on: derives
  `users/<uid>/characters/`, `users/<uid>/drafts/`, `users/<uid>/settings.json`
  from the session cookie. All route handlers read these three state attrs and
  never touch the raw filesystem paths directly.
- **Per-user workspace** — `users/<uid>/` at the project root mirrors the root
  layout (characters/, drafts/, settings.json). Keyed by GCIP uid;
  `safe_uid(uid)` strips any path-traversal characters before the directory is
  created. First login is seeded with example characters via
  `seed_user_workspace(uid)`.
- **GCIP Google-only sign-in** — the `/login` page loads the Firebase JS SDK
  from CDN (the one exception to the server-rendered-only ethos) and triggers a
  Google OAuth pop-up. The resulting ID token is POSTed to `/auth/verify`, which
  calls `FirebaseVerifier` (wraps firebase-admin, lazy-imported to keep the
  auth-off path import-free) → `Whitelist` check → sets a signed
  `SessionMiddleware` cookie (itsdangerous).
- **Whitelist** — `whitelist.txt` at the project root (gitignored). Read fresh
  per request. Lines starting with `#` and blank lines are ignored. Every
  Google-authenticated user whose email is not listed receives a 403. This is
  the sole invite gate — no email is sent at any point, no SMTP/DNS dependency.
- **`FakeVerifier` test seam** — inject via `create_app(auth_verifier=FakeVerifier({email: uid, ...}))`.
  Tests never need firebase-admin installed; the real verifier is only imported
  when `AOSE_AUTH=1` in production.
- **Firebase emulator for offline dev** — set
  `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099` and both the Firebase JS SDK
  (frontend) and firebase-admin (backend verifier) route to the local emulator.
- **Export / import** — `GET /character/{id}/export` returns a JSON download of
  the full `CharacterSpec`. `POST /import` accepts a JSON file upload, validates
  it as a `CharacterSpec`, saves it under a new id, and redirects to the sheet.
  These routes work in both auth-on and auth-off modes and provide a self-serve
  backup / escape hatch.

---

## Companions & Holdings (Phase A)

Animals and vehicles are first-class storage locations owned by a character,
each with its own capacity that never contributes to the PC's encumbrance.

**Item variants** (`aose/models/item.py`): three new discriminated-union members —
`Animal` (hd, hp, ac, attacks, morale, load limits), `Vehicle` (hull_points,
cargo_capacity_cn, vehicle_category), and `AnimalArmor` (sets_ac, fits list).
All three are catalog items purchasable through the existing shop machinery.

**Roster instances** (`aose/models/character.py`): `AnimalInstance` and
`VehicleInstance` mirror `ContainerInstance`. Each has `instance_id`,
`catalog_id`, a mutable `name`, damage/hull fields, and a `contents: list[str]`
of loaded item ids. `ContainerInstance` gains `location` + `location_id` so a
container can be placed *on* an animal or vehicle (excluded from PC encumbrance).
`CharacterSpec` carries `animals: list[AnimalInstance]` and
`vehicles: list[VehicleInstance]`.

**Monster-stats engine** (`aose/engine/monster_stats.py`): HD string → THAC0,
attack bonus, and all five save scores. Two YAML lookup tables are loaded by
`GameData`: `data/monster_attack_matrix.yaml` (16 HD bands) and
`data/monster_saves.yaml` (9 HD bands). The engine imports only `models` and
`loader` — no cycle risk.

**Catalog data**: `data/equipment/animals.yaml` (7 animals: camel, draft/riding/
war horse, mule, hunting/war dog), `data/equipment/vehicles.yaml` (16 land and
water vehicles), `data/equipment/tack.yaml` (dog armour, horse barding,
saddle & bridle, saddle bags container).

**Companions engine** (`aose/engine/companions.py`): buy/remove animals &
vehicles (deducting/refunding gold), assign/clear animal armour, load/unload
loose gear onto a carrier (capacity-checked), move a container between person
and carrier. `encumbrance.py` and `shop.py` skip containers whose `location !=
"person"`.

**Sheet view** (`aose/sheet/companions_view.py`): `companions_block(spec, data)`
assembles `AnimalCard` and `VehicleCard` view models — derives ascending AC
(overridden by equipped armour), THAC0/attack bonus, and saves from catalog stats
— and attaches resolved `InventoryRow` contents. Returns `None` when the
character has no companions. `CharacterSheet.companions` carries this block.

**Routes**: `POST /character/{id}/animal/{buy,remove,rename,hp,armor,load,unload}`
and the parallel vehicle set (add hull, extra-animals toggle). All follow the
standard `_load_spec_or_404` → mutate → `save_character` → 303 pattern.

**Sheet UI** (`aose/web/templates/_companions.html`, included from `sheet.html`):
one `companion-card` per animal/vehicle with inline HP/hull buttons, armour
select, and a collapsible load details block. Print sheet includes a static
text block in `sheet_print.html`.
