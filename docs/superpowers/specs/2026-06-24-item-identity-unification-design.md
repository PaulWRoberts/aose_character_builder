# Item Identity Unification — Design

**Date:** 2026-06-24
**Status:** Approved (design); revised 2026-06-25 to fold plain/enchanted/ammo into one instance type
**Branch:** feat/item-identity-unification

## Problem

Equipping a weapon/armour on a retainer, then moving the carried item to another
inventory, leaves the item **both** equipped on the retainer **and** present at
the destination — a dupe (the retainer's AC/attacks still count the gone item).

The proximate cause is in `move_item` ([storage.py:196](../../../aose/engine/storage.py)):
the equipped-slot cleanup is hardcoded to the PC world — it only fires when
`src.kind == "carried"` and only touches `spec.equipped`/`spec.inventory`. A
retainer's own inventory is exposed as a single `kind="retainer"` location, so
the branch never runs, and even if it did it would patch the wrong spec.

But that is a symptom. The **root cause is an identity gap**: loose catalog items
are bare `str` ids in positional lists (`inventory`, `stashed`, every container/
animal/vehicle `contents`), so they have no per-instance identity. "Equipped" and
"loaded ammo" therefore live in **side tables** (`equipped: dict[str,str]`,
`loaded_ammo: dict[str,str]`) keyed by catalog id, and *every* removal/move path
must remember to patch those tables in lockstep. They drift. The
2026-06-23 unified-movement spec explicitly listed *"No flat-pointer rewrite of
catalog-item storage … loose catalog items stay identity-less strings"* as a
**non-goal** — this design closes that deferral.

The engine mints an instance only when forced to (scrolls, magic items,
enchanted gear, ammo, gems), and even then it mints *different types* for what is
the same kind of thing: a plain sword is a bare `str`, a +1 sword is an
`EnchantedInstance`, and arrows are an `AmmoStack`. That lazy, type-split boundary
is the recurring source of item bugs: many representations, many mental models,
side tables and parallel code paths that fall out of sync.

## North-star invariant

**Every owned thing is an instance with identity.** It carries an `instance_id`
and a `location`; stackables additionally carry a `count`; equippables carry
their equip-state *as a field on the instance*. A plain item, an enchanted item,
and a stack of ammo are **one type** differing only by data (an optional
`enchantment_id`, a `count`), never by class. There are no side tables keyed by
catalog id, and no positional lists. One move path and one equip path operate on
instances regardless of owner (PC or retainer), kind, or enchantment.

## Goals

- Give **loose catalog items** real instance identity (`ItemInstance`): id +
  location (+ count for stackables, + equip-state for equippables).
- **Unify plain, enchanted, and ammo into the one `ItemInstance` type.** The item
  *type* is a reference (`catalog_id`); whether it is enchanted is an optional
  *field* (`enchantment_id`), not a different class. Delete `EnchantedInstance`,
  `AmmoStack`, and the separate `spec.enchanted` / `spec.ammo` lists.
- Make **equipped** and **loaded-ammo** and **armour-tailored** *instance state*,
  deleting the `equipped` / `loaded_ammo` side tables and the `armor_tailored`
  spec field.
- Give **coin stacks** an `instance_id` so every stack moves by id through one
  vocabulary.
- Collapse loose storage to **one flat `items` list with location-as-field**,
  retiring the positional `inventory`/`stashed` lists and the `contents`
  sub-lists on containers/animals/vehicles.
- Define **stackable** formally (durable vs consumable) and make **move / sell /
  drop / use** uniform across every stackable.
- Route **PC↔retainer transfer** through the one move vocabulary, deleting the
  bespoke `transfer_to_retainer` / `transfer_to_pc`.
- Fix the reported dupe **structurally** (it falls out of the invariants), with a
  regression test that reproduces it.

## Non-goals

- **No single polymorphic collection for *everything*.** Plain, enchanted, and
  ammo merge into `ItemInstance` (they share the same base+optional-enchantment+
  count shape). But `magic_items`, `gems`, `jewellery`, `spell_sources`, `coins`,
  `containers`, `animals`, `vehicles` stay their own typed lists — they carry
  genuinely different state (charges with a toggle-equip mechanic; spell entries;
  value/label; carrier capacity) and do not fit the catalog+enchantment+count
  contract. Unification is "one type per shared shape", not "one physical list".
  (Approach A from brainstorming; the "one collection for all" Approach B was
  rejected as a big-bang rewrite.)
- **No change to the two real equip mechanics.** Slotted (weapons/armour/shields
  → `armor`/`main_hand`/`off_hand`) and toggled (magic items → worn bool) are
  both genuine game concepts; we make both *instance state*, we do not merge them
  into one. (This is why `MagicItemInstance` stays separate: its equip is a
  toggle, not a slot.)
- **No nesting.** A container still cannot live inside a container.
- **No new per-shot ammo consumption.** "Use" on a consumable is an explicit
  drop-1 button, not automatic.
- **No denormalised type data.** The instance references its type by `catalog_id`;
  the type's attributes (weight, damage, cost) stay in the catalog (`GameData`),
  never copied onto the instance.
- **No migration tooling.** App is not deployed (project convention). A
  best-effort load-time coercion of old saves is provided as a courtesy only.

## Decisions (from brainstorming)

1. **Shared contract, typed lists per shape** (Approach A). Every owned thing
   shares `instance_id + location (+ count) (+ equip-state)`. The catalog-item
   shape (plain, enchanted, ammo) collapses into **one** `ItemInstance` type and
   **one** `spec.items` list; the other instance shapes keep their own lists.
2. **Type by reference, enchantment by field.** An item's *type* is `catalog_id`
   (a reference into `GameData.items`). Whether it is enchanted is an optional
   `enchantment_id` field on the same instance — `None` for a plain sword,
   `"generic_plus_1"` for a +1 sword. Resolving an instance to its effective
   `Weapon`/`Armor`/`Ammunition` is one function: no enchantment → the catalog
   item; else compose the synthetic item from base + enchantment. No code branches
   on "is this enchanted" by *type*; it reads the field.
3. **Stackable vs equippable.** Stackables (coins, gems, ammo, bulk consumables)
   are one instance with `count`. Equippables (weapons, armour, shields) are
   always per-instance, `count == 1`, and **never** stack. Stackability and
   equippability derive from the **resolved catalog item type**, not an instance
   flag (data-not-code) — enchantment does not change it (a +1 sword is still
   equippable; +1 arrows are still stackable).
4. **Two stackable categories.** *Durable* = exactly {coins, gems}. *Consumable*
   = ammo + all bulk gear (torches, rations, spikes, oil, …). The only
   behavioural difference is the **"use"** button (consumables only).
5. **Equip is instance state.** Slotted things carry `equip = slot | None`;
   magic items keep `equipped: bool`. `CharacterSpec.equipped` is **deleted**.
6. **Quantity vocabulary.** Every quantity-removing action on a stackable — move,
   sell, drop — takes a `count`, rendered as a number box defaulting to the full
   current count and clamped to `1..count`. Consumables also get **use** (= drop
   1). The box appears per action only where that action exists for the type.
7. **Auto-merge.** At most **one stack per (merge-key, location)**. Any operation
   that lands a stackable into a location with a matching stack has the resident
   absorb the incoming count; the incoming instance is discarded. Splitting is
   only by moving a partial count to a *different* location. Merge-keys: coins →
   `denom`; gems → `value + label`; every `ItemInstance` stackable →
   `(catalog_id, enchantment_id)`. (This subsumes the old ammo merge-key
   `base_id + enchantment_id` and the consumable-gear key `catalog_id` —
   `enchantment_id` is just `None` for unenchanted gear.)
8. **One move path, retainers included.** `move_thing` is the single front door;
   `transfer_to_retainer`/`transfer_to_pc` are deleted; give/take is a move with
   `kind="retainer"` as src/dest, identical to container/carrier moves.
9. **Storage locations are uniform; their differences are parameters, not code
   variations.** Every location behaves identically (hold instances, weigh them,
   place-or-merge stackables) and differs only by a small policy descriptor:
   *capacity cap*, *encumbrance contribution* (which character's load it adds to,
   or weightless), *equip-allowed* (and *of what* — wield vs wear), and
   *equip-eligibility source* (the class allowances of the character it sits on,
   or "all"). Adding a new kind of location is filling in parameters, never
   adding a branch.

## Architecture

### Models (`aose/models/character.py`, `storage.py`)

**New `ItemInstance`** — the single catalog-item instance (plain, enchanted, or
stacked):

```
instance_id: str            # uuid4 hex
catalog_id: str             # references a Weapon / Armor / gear / Ammunition item (the "type")
location: StorageLocation   # carried/stashed/container/animal/vehicle/retainer
enchantment_id: str | None = None   # None = plain; else references an Enchantment
count: int = 1              # >1 only for stackables; equippables always 1
equip: Literal["armor","main_hand","off_hand"] | None = None  # equippables only
tailored: bool = True       # inert unless tailorable body armour
loaded_ammo_id: str | None = None   # launcher weapons only; an ItemInstance (ammo) id
charges_max: int | None = None      # carried over from EnchantedInstance (charged enchantments)
charges_remaining: int | None = None
extra_modifiers: list[Modifier] = []   # escape hatch (from EnchantedInstance)
note: str = ""                          # escape hatch
```

- `CharacterSpec.inventory: list[str]` and `stashed: list[str]` → **one**
  `items: list[ItemInstance]`. Carried-vs-stashed is `location.kind`.
- **`EnchantedInstance` is deleted.** An enchanted weapon/armour is an
  `ItemInstance` with `enchantment_id` set; it slots, moves, and weighs exactly
  like a plain one. Its old fields (`equipped` bool, `charges_*`,
  `extra_modifiers`, `note`) move onto `ItemInstance` (equip becomes the slot
  field; the rest become optional). `CharacterSpec.enchanted` is removed.
- **`AmmoStack` is deleted.** A stack of ammo is an `ItemInstance` whose
  `catalog_id` references an `Ammunition` item, with `count > 1` and optional
  `enchantment_id` (magic ammo). `CharacterSpec.ammo` is removed.
- `ContainerInstance.contents` / `AnimalInstance.contents` /
  `VehicleInstance.contents` (`list[str]`) → **removed**. An item in a container
  is an `ItemInstance` with `location = container:<id>` — exactly how a magic
  item in a container already works.
- `CharacterSpec.equipped: dict[str,str]` → **removed**; the slot is read from
  each `ItemInstance.equip`.
- `CharacterSpec.loaded_ammo: dict[str,str]` → **removed**; loaded ammo is
  `ItemInstance.loaded_ammo_id` on the launcher (pointing at an ammo
  `ItemInstance`).
- `CharacterSpec.armor_tailored: bool` → **removed**; `ItemInstance.tailored` on
  the worn armour.
- `MagicItemInstance.equipped: bool` — **unchanged** (toggle mechanic; stays its
  own list).
- `CoinStack` gains `instance_id: str`. The `(denom, location)` uniqueness
  invariant stays (it is just the coin merge-key).

Models stay "dumb": invariants that need a catalog lookup (equippable ⇒ count 1;
equip only on equippables; stackable ⇒ no equip; `enchantment_id` resolvable for
the base's kind) are enforced in the engine, not the model.

### Resolution — one function (`enchant.py`)

`resolve(inst, data) -> Weapon | Armor | Ammunition | GearItem | None`:

- `inst.enchantment_id is None` → return `data.items[inst.catalog_id]` directly;
- else compose the synthetic item from the base catalog item + the `Enchantment`
  (today's `resolve_instance`), now taking an `ItemInstance` instead of an
  `EnchantedInstance`.

Every reader (attacks, AC, encumbrance, ammo, magic) resolves through this one
function and then works on the resulting catalog item — no `isinstance(...
EnchantedInstance)` branches, no parallel "enchanted vs plain" code paths.

### Engine — one equip path (`equip.py`)

- `equip(spec, instance_id, slot, *, data, ruleset_flags...)` and
  `unequip(spec, instance_id)` operate on **instances** of whichever spec owns
  them. They look the instance up in the single `spec.items` list and set/clear
  its `equip` field. No `equipped` dict, and no second list to scan — folding
  `enchanted` into `items` removes the dual-loop / `isinstance` lookup the
  pre-merge design needed.
- The old `equipped_ref` catalog_id-vs-instance_id split (and much of
  `resolve_slot`) goes away: the equipped item in a slot is found by scanning
  `items` for `equip == slot`, and resolved via the one resolver.
- Wield-budget validation (`validate_wield`) iterates the owner spec's instances
  whose `equip in {main_hand, off_hand}` — identical code for PC and retainer.
- **Invariant: `equip is not None ⇒ the instance sits in a location whose policy
  permits equipping`** — canonically a character's own carried bucket
  (`location.kind == "carried"` within that character's world). Enforced at the
  single equip/move chokepoint by reading the location's policy descriptor (below),
  not by a `kind` branch. Equipping is rejected where the policy forbids it;
  moving an equipped instance into such a location clears its `equip` first.
- **Eligibility** (which weapons/armour the wearer's class may use) comes from the
  policy descriptor's *equip-eligibility source* — the owning character's class
  allowances for a PC/retainer carried bucket, `"all"` elsewhere — so the PC and a
  retainer run the identical gate with different parameters.
- Loaded-ammo and tailoring follow the instance: moving/unequipping the launcher
  clears `loaded_ammo_id`; the armour's `tailored` rides with the instance across
  re-equips for free (it is the instance's own field now).

### The uniform location policy descriptor

There is **one** description of how a storage location behaves, extending today's
view-only `OwnerCaps` (`aose/engine/shop.py`) into the engine's single source of
truth for per-location policy:

| parameter | meaning | examples |
|---|---|---|
| `capacity_cn` | hard cap, or `None` for uncapped | container `capacity_cn`; animal `max_load`; vehicle `cargo`; carried/stashed/retainer `None` |
| `encumbers` | whose load this adds to (a character) or weightless | carried → that character; stashed → weightless; carrier/container → resolved through their own rule |
| `equip_allowed` | may instances here be equipped, and of what kind | carried → wield+wear; animal → wear (barding) only; stashed/vehicle/container → none |
| `equip_eligibility` | class allowance gate for equipping here | PC/retainer carried → that character's class allowances; else `"all"` |

`move_thing`, `_check_capacity`, and `equip`/`unequip` all **read this descriptor**
instead of switching on `location.kind`. The descriptor is resolved once per
location from the carrier/character behind it. Today's per-kind `_check_capacity`
`if/elif` collapses into "read `capacity_cn`, compare". OwnerCaps' view flags
(`has_equipped`, `can_wield`, `can_stash`, `bucket_label`) become a *projection* of
this same descriptor, so the view and the engine cannot disagree about a
location's powers.

*(Animal barding stays the `AnimalInstance.armor_id` field this pass — it is the
one `equip_allowed=wear` location whose worn slot is not yet an `ItemInstance`.
The descriptor model accommodates promoting it later; doing so now is out of
scope and not required for the dupe fix.)*

### Engine — one move path (`storage.py`)

`move_thing(spec, category, ref_id, dest, *, count=None, src=None, data=None)`
remains the front door; every category reduces to the same primitives:

1. **locate** the instance by id (in the PC world or any retainer world);
2. **capacity-check** the destination (`_check_capacity`, unchanged);
3. **place-or-merge** at the destination — for stackables, find the resident
   stack by `(merge-key, dest)` and absorb `count`, else create/re-point a stack
   carrying the remaining/whole count; for equippables, re-point `location`;
4. **leaving-carried cleanup** — if the instance leaves `carried`, clear `equip`
   and `loaded_ammo_id`; if a launcher leaves, unload it; if a full ammo stack
   moves, unload any launcher pointing at it.

- **Cross-world moves (PC↔retainer)** move the instance between the two specs'
  `items` (or typed) lists, resetting `location` to carried in the destination
  world. Same-world moves re-point `location`. This is exactly today's
  `move_instance` pattern, now used for loose items too.
- **`split_stack(spec, instance_id, n, dest)`** is the shared primitive behind
  move/sell/drop of a partial count: it removes `n` from the source (pruning an
  emptied stack) and applies the place-or-merge at `dest` (or, for sell/drop, to
  the sink). One implementation replaces the divergent coin/gem/ammo splitters.
- **`transfer_to_retainer` / `transfer_to_pc` deleted**; the give/take routes
  become thin wrappers over `move_thing` (or are dropped in favour of the
  existing move UI).
- `move_targets` and `loose_list`/`containers_collection`/`_carrier`/`_retainer`
  resolvers stay, adjusted for the flat `items` list (location-filtered instead
  of positional). Ammo, formerly its own collection, is now part of `items`.

### Engine — sell / drop / use (`shop.py`, `storage.py`)

- **Sell** a stackable: `split_stack` off `count` (default full, clamp
  `1..count`), credit half-price (or refund) to the PC's carried coins, prune an
  emptied source. One path; gems and consumable gear (incl. ammo) share it.
- **Drop** a stackable: `split_stack` off `count` to a discard sink (the
  instance/quantity is removed from the world). Equippables drop whole.
- **Use** (consumables only): `drop(count=1)` — a dedicated shortcut, no number
  entry.

### Derivations (encumbrance, attacks, AC, ammo, quick_equipment, retainers)

- **Encumbrance** (`encumbrance.py`, `location_load_cn`): sum `items` by
  `location` and `count` (resolved catalog `weight_cn × count`) instead of
  iterating a positional list; equipped items still weigh (they are carried). Ammo
  weight now flows through this same sum (it is an `ItemInstance`).
  Magic/coins/gems already filter by location — unchanged.
- **Attacks / AC / equip queries** read the equipped instance via
  `equip == slot`, then `resolve(...)`. A small helper
  `equipped_in(spec, slot) -> instance | None` centralises the lookup.
- **Ammo** loaded-launcher reads `ItemInstance.loaded_ammo_id` (pointing at an
  ammo `ItemInstance`) instead of the `loaded_ammo` dict; the magic-ammo bonus is
  read by resolving that ammo instance's `enchantment_id`.
- **quick_equipment** / kit application builds `ItemInstance`s (with ids)
  directly, including ammo stacks (no separate `AmmoStack` construction).
- **retainers**: transfer helpers removed (use `move_thing`); generation/kit
  already routes through `quick_equipment`, so retainer items are instances with
  ids like the PC's — same equip/move/resolve code throughout.

### View + templates (`sheet/view.py`, inventory templates)

- Inventory grouping buckets the flat `items` list by `location` (as it already
  does for magic/coins/gems). Equipped items render in the equipped block via
  `equip`; everything else under its location group/container. Enchanted items and
  ammo are no longer separate render branches — they are `ItemInstance`s with an
  `enchantment_id` / `count` and render through the one item row.
- The shared action macros (`_actions.html`, from the 2026-06-23 work) gain the
  **count box** on move/sell/drop for stackables (default full, clamp `1..count`)
  and the **use** button for consumables. One affordance, every stackable.

### Routes (`routes.py`)

- `POST /inventory/move` (single front door) unchanged in shape; now also the
  path for give/take (dest/src `kind="retainer"`).
- Sell/drop routes take an optional `count`; a new use action posts drop-1.
- `retainer/give` + `retainer/take` become wrappers over `move_thing` (or are
  removed if the move UI fully covers them — decided at plan time by grepping
  call sites).
- Equip/unequip routes (PC, retainer, enchanted) collapse onto the single
  instance-based `equip`/`unequip`. The separate "enchanted equip" route is gone
  (enchanted is just an `ItemInstance`).

### Load-time coercion (courtesy, no migration tooling)

A data-aware coercion (in the loader, where `GameData` is available — see plan
Task 4) on the raw dict, before `CharacterSpec` validation:

- wraps `inventory`/`stashed` strings into `ItemInstance`s
  (`location = carried/stashed`, `count` by collapsing duplicates for stackables,
  per-instance for equippables);
- drains each container/animal/vehicle `contents` into `items` with the matching
  `location`;
- **folds the old `enchanted` list into `items`** — each becomes an `ItemInstance`
  with `catalog_id = base_id`, `enchantment_id` set, `equip`/`tailored`/charges
  carried over;
- **folds the old `ammo` list into `items`** — each becomes an `ItemInstance`
  with `catalog_id = base_id`, `count`, optional `enchantment_id`;
- converts the `equipped` dict into `equip` on the matching instances (reconciling
  the old doubly-tracked enchanted weapon — `equipped` bool *and* a `spec.equipped`
  slot id — into the single `equip` slot, keeping which hand);
- converts `loaded_ammo` → `loaded_ammo_id` (now pointing at the migrated ammo
  `ItemInstance`); `armor_tailored` → `tailored` on the worn armour;
- assigns `instance_id` to coin stacks.

Old saves load unchanged; no separate migration step.

## Data flow

```
spec ─► build_inventory_groups(spec, data)
          items (plain · enchanted · ammo, all one type) + coins/gems/jewellery/magic
          all bucketed by StorageLocation (top-level + per container)
          equipped block ← items where .equip is set / magic .equipped
                    ▼
       sheet templates → per-item modal → _actions.html macros
          Move ▾ (count box for stackables) · Sell ▾ (count) · Drop (count)
          · Use (consumables) · Equip/Unequip (equippables)
                    ▼
       POST /inventory/move | /sell | /drop | /use | /equip | /unequip
          → storage.move_thing / shop / equip  (all instance-based, owner-agnostic)
          → resolve(inst, data) for stats; invariants enforced once:
            equipped⇒carried; ≤1 stack per (catalog_id, enchantment_id, location)
```

## Phasing (cohesive spec → phased plan)

Each phase keeps the suite green before the next.

1. **Model + coercion + primitives.** Add the unified `ItemInstance`
   (`enchantment_id`, `count`, `equip`, `tailored`, `loaded_ammo_id`, charges),
   flat `items`; delete `EnchantedInstance`/`AmmoStack` and `spec.enchanted`/
   `spec.ammo`; `instance_id` on coins. Add the loader coercion. Reshape
   `storage.py` resolvers + `equip.py` onto instances; add the one `resolve`;
   add `split_stack`; lift the location policy descriptor into the engine and
   route `_check_capacity` + equip-allowed/eligibility through it; enforce the
   invariants. Green: `test_storage*`, `test_equip`, `test_retainer_transfer`.
2. **Derivations.** encumbrance, attacks, AC, ammo, quick_equipment, retainers
   read instances through the one resolver. Delete `transfer_to_*`. Green:
   engine suite.
3. **View + templates + UI.** bucket `items` by location; count box + use button
   in the shared macros; equip block via `equip`. Green: web/view tests.
4. **Delete dead side tables.** Remove `spec.equipped`, `loaded_ammo`,
   `armor_tailored`, `spec.enchanted`, `spec.ammo`, the `contents` sub-lists, and
   the transfer routes; sweep call sites by grep. Update `ARCHITECTURE.md`
   (storage shapes, equip, encumbrance) in place + a `CHANGELOG.md` row.

## Testing

- **Reported dupe (regression):** equip a weapon on a retainer → move it to the
  PC → assert the retainer slot is clear, the instance is unequipped, and exactly
  one copy exists in the world.
- **Equip-as-state:** equipping sets `equip`; moving an equipped instance off
  carried clears `equip`; equipping a stashed/in-container instance is rejected;
  PC and retainer use the same path; a +1 weapon (enchanted `ItemInstance`)
  equips through the identical path as a plain one.
- **One type, one resolver:** a plain item resolves to its catalog item; an
  `ItemInstance` with `enchantment_id` resolves to the composed synthetic item;
  attacks/AC read both through the same call.
- **Auto-merge:** moving a stackable into a location with a matching
  `(catalog_id, enchantment_id)` stack yields exactly one stack (resident absorbs;
  incoming id gone); +1 arrows do **not** merge with plain arrows; equippables
  never merge.
- **Split-by-move:** partial move leaves a remainder at source and one stack at
  dest; full move prunes the source.
- **Quantity actions:** sell/drop clamp `count` to `1..count` and default to
  full; "use" drops exactly 1 and only exists for consumables; durables (coins,
  gems) expose no "use".
- **Loaded ammo / tailoring follow the instance:** moving/unequipping a launcher
  clears its load; tailoring survives re-equip on the same armour instance.
- **Coercion:** an old save (string inventory, `equipped` dict, `loaded_ammo`,
  `armor_tailored`, `contents`, separate `enchanted` + `ammo` lists) loads into
  the new shape with weights, equip, enchantment, and load preserved.
- **Regression:** full suite green; encumbrance totals unchanged for an
  unmodified character; print sheet lists all groups; settings page shows no
  "pending" badge.

## Risks / open implementation notes

- **Blast radius.** This touches models, loader, ~10 engine modules, the sheet
  view, and many templates. Phasing keeps each step green, but the model change is
  inherently atomic (the flat `items` list breaks every positional reader at
  once, and deleting `enchanted`/`ammo` breaks every enchanted/ammo reader);
  Phase 1 must land model + all `storage`/`equip`/`resolve` readers together.
- **Coercion fidelity.** Collapsing duplicate strings into counted stacks must use
  the same stackable/equippable classification the runtime uses, or weights/counts
  drift on load. Share one `is_stackable(catalog_item)` helper between coercion and
  engine. Folding `enchanted`/`ammo` must preserve `enchantment_id`, charges,
  counts, and which-hand equip.
- **Merge-key correctness.** Every `ItemInstance` stackable merges by
  `(catalog_id, enchantment_id)`; coins by `denom`; gems by `value+label`. A wrong
  key either fragments or wrongly fuses stacks — in particular enchanted vs plain
  of the same base must stay distinct.
- **Enchanted equip migration.** Enchanted weapons were doubly tracked (an
  `equipped` bool *and* a `spec.equipped` slot id). The coercion must reconcile
  both into the single `equip` slot without losing which hand.
- **Field bloat on plain items.** The unified `ItemInstance` carries optional
  enchantment/charge/escape-hatch fields that are inert for plain gear. This is
  the accepted cost of one type; defaults keep saves small and construction cheap.
- **Call-site sweep on deletion.** Removing `spec.equipped`/`loaded_ammo`/
  `contents`/`enchanted`/`ammo`/`transfer_*` 404s or AttributeErrors any missed
  reader; grep exhaustively before deleting (Phase 4).
