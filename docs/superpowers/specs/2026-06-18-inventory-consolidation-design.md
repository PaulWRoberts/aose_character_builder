# Inventory Consolidation — design

**Date:** 2026-06-18
**Status:** Approved design — ready for implementation plan(s).
**Slug:** `inventory-consolidation`

Consolidate the inventory UI and data model so the **top-level inventory concepts
shown in the UI map 1:1 to the storage locations in data**: **Carried**, **Stashed**,
and **each animal, vehicle, and retainer**. Coins and treasure stop being PC-global
scalars and become **location-aware stackable items** that migrate between top-levels
and into containers. The standalone coin tracker and money-change UI are removed in
favour of per-stack controls. Shop purchases spend only on-person coins, lowest
denomination first, with no implicit conversion.

This touches the model (`character.py`, `valuable.py`), several engines (`currency`,
`valuables`, `shop`, `encumbrance`, plus a new movement engine), the inventory view
builder, and the shared equipment UI partial. It is deliberately scoped to
coins/treasure/containers/movement — **loose items keep their existing `list[str]`
storage**.

---

## Background — what exists today

- **Loose items**: `inventory: list[str]` (= on-person/Carried), `stashed: list[str]`,
  `AnimalInstance.contents`, `VehicleInstance.contents`, `ContainerInstance.contents`.
  A loose item's location *is* the list it sits in — it stores no location field.
- **Equipped**: `equipped: dict[str,str]` (slots `armor`/`main_hand`/`off_hand`),
  rendered today as its own top-level alongside Carried/Stashed.
- **Coins**: five `int` fields on `CharacterSpec` (`platinum`/`gold`/`electrum`/
  `silver`/`copper`); `gold` is the shop-spendable balance. `currency.py` owns
  value/weight/convert. All coins weigh (1cn each) and all count toward encumbrance.
- **Treasure**: `gems: list[GemStack]`, `jewellery: list[JewelleryPiece]` — PC-global,
  no location. `valuables.py` owns add/adjust/sell; weight reaches encumbrance via
  `treasure_weight_cn` (gems 1cn, jewellery 10cn).
- **Containers**: `ContainerInstance` with `state: carried|stashed` **and**
  `location: person|animal|vehicle` + `location_id`. `contents` are loose ids.
- **Retainers**: `retainers: list[Retainer]`, each wrapping a full `CharacterSpec`
  (its own inventory/equipped/coins/treasure/containers). Already rendered as full
  sub-sheets via `build_sheet` recursion; PC↔retainer item transfer exists.

## Goals

1. UI top-levels = data top-levels: Carried, Stashed, each animal/vehicle/retainer,
   each rendered by one shared macro.
2. Equipped is a **subsection of** Carried (and of animals/retainers), not a top-level.
3. Coins, gems, and jewellery become **location-aware stackable items** that move
   between any top-level and into containers.
4. Containers expand inline within their top-level and show rolled-up contents weight.
5. Remove the standalone coin tracker, the gold +/- grant, and the money-change form;
   keep a read-only total wealth/treasure readout; convert is a per-stack control.
6. Shop spends only **loose on-person (Carried) coins**, lowest denomination first,
   no implicit conversion (with one sanctioned gp-change exception).

## Non-goals

- No nesting of containers (a container cannot hold another container).
- No rewrite of loose-item storage (`list[str]` stays).
- No retainer-card revamp — retainer inventories render inline *and* on their card
  (duplicative, accepted as temporary).
- No data migrations beyond courtesy coercion validators (app is undeployed).

---

## Data model

### `StorageLocation` (new, `aose/models/character.py`)

```python
class StorageLocation(BaseModel):
    kind: Literal["carried", "stashed", "animal", "vehicle", "container"]
    id: str | None = None   # instance_id for animal/vehicle/container; None for carried/stashed
```

**Pointer model.** A value-stack inside a container stores only `kind="container",
id=<container_id>`; the container owns its own bucket, so resolving a stack's
top-level means resolving its container's location. This mirrors how loose items
already work (an id inside `ContainerInstance.contents`; the container owns the
bucket) and means **moving a container moves its contents for free** — no cascade
rewrites, no denormalized bucket that can drift out of sync.

**Asymmetry, enforced by validator:**
- A **container's own** `location.kind` ∈ {carried, stashed, animal, vehicle} —
  never `container` (this is the no-nesting rule).
- A **value-stack's** `location.kind` may be any of the five.

Equality/identity: two `StorageLocation`s are the same slot iff `(kind, id)` match.
This is the merge key for stacks.

### `CoinStack` (new, replaces the five int fields)

```python
class CoinStack(BaseModel):
    denom: Literal["pp", "gp", "ep", "sp", "cp"]
    count: int
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
```

- `CharacterSpec.coins: list[CoinStack]` replaces `platinum/gold/electrum/silver/copper`.
- **Invariant:** at most one stack per `(denom, location)` — stacks are addressable
  by denom+location, no `instance_id` needed. Empty (`count == 0`) stacks are pruned.
- **Coercion validator** (`model_validator(mode="before")`): old saves with the int
  fields produce carried stacks for each non-zero denom, then the int keys are dropped
  (keeps loadable under `extra="forbid"`).

### `GemStack` / `JewelleryPiece` (`aose/models/valuable.py`)

Each gains `location: StorageLocation` (default carried). Coercion validator defaults
missing `location` to carried for old saves.

- `GemStack` merge key becomes `(value, label, location)`.
- `JewelleryPiece` stays individual (per-instance), addressed by `instance_id`.

### `ContainerInstance` refactor (`aose/models/character.py`)

Replace `state: Literal["carried","stashed"]` + `location: Literal["person","animal",
"vehicle"]` + `location_id` with a single `location: StorageLocation`. Coercion
validator maps old triples → new:

| old state | old location | new `location` |
|---|---|---|
| carried | person | `{carried}` |
| stashed | person | `{stashed}` |
| (any)   | animal  | `{animal, location_id}` |
| (any)   | vehicle | `{vehicle, location_id}` |

`contents` (loose ids) is unchanged.

### Loose items — unchanged

`inventory` (Carried loose), `stashed`, `AnimalInstance.contents`,
`VehicleInstance.contents`, `ContainerInstance.contents` keep `list[str]`. Their
location is implied by the list. Only value-stacks carry an explicit `StorageLocation`.

---

## Movement & conversion engine (`aose/engine/storage.py`, new)

One vocabulary for moving any payload to any `StorageLocation`, replacing the
scattered helpers (`shop.stow`/`take_out`/`stash_container`/`unstash_container`,
`companions` load/unload/move-container). Pure functions mutating the spec in place.

- `move_item(spec, item_id, dest)` — pop one loose id from its current bucket/container,
  append to `dest`'s list. Resolves the right `list[str]` for `dest` (`inventory` for
  carried, `stashed`, `AnimalInstance.contents`, `VehicleInstance.contents`,
  `ContainerInstance.contents`).
- `move_container(spec, container_id, dest)` — set the container's `location`; `dest`
  restricted to carried/stashed/animal/vehicle (validator rejects `container`).
- `move_coins(spec, denom, src, dest, count)` — decrement the `(denom, src)` stack by
  `count`, increment/create the `(denom, dest)` stack; prune empties.
- `move_valuable(spec, instance_id, dest)` — move a gem stack (split one off, or whole)
  or jewellery piece to `dest`, merging gems by key.
- `convert_coins(spec, location, frm, to, count)` — **in-place per-stack** conversion at
  one location, at AOSE rates, whole-coin enforced (lifts the validated core out of the
  old `currency.convert`; raises `CurrencyError`). Replaces the global money-change form.
- `add_coins(spec, denom, count, location)` — GM grant into a location's stack.

**Retainer destinations.** "Move to retainer X" is not a `StorageLocation` kind —
retainers are separate specs. Routes detect a retainer destination and call the
existing transfer path, extended to coins/treasure/containers: append into the
retainer's own `inventory`/`coins`/`gems`/`jewellery`/`containers` (all land in the
retainer's `carried`). Symmetric take-back already exists for items.

Encumbrance and shop spend ignore anything not resolving to `carried`.

---

## Currency, encumbrance & wealth

### `currency.py` (reworked to be location-aware)

- `total_value_cp` / `total_value_gp` / `coin_count` take an optional location filter.
  `coin_count(spec, carried_only=True)` is the encumbrance weight (carried coins, 1cn
  each). `total_value_*` over **all PC buckets** feeds the wealth readout.
- The `convert` core moves to `storage.convert_coins` (per-location). `currency.py`
  keeps `DENOMINATIONS`/`RATES`/value helpers.

### `encumbrance.py`

- Counts **only the Carried bucket**, with each item counted exactly once:
  - carried **loose** items (direct), carried **loose** coins (1cn each), carried
    **loose** gems/jewellery (1cn / 10cn) — i.e. value-stacks whose `location.kind == "carried"`;
  - carried **containers**: own weight + `weight_multiplier × raw_contents`, where
    `raw_contents` is the raw weight of *everything inside* — loose items **and** the
    coin/treasure stacks located in that container. Coins/treasure in a carried
    container are therefore weighed via the container (and get its multiplier), never
    again on the direct line.
  - Stashed and on-carrier weigh nothing for the PC.
- `treasure_weight_cn` becomes carried-only (gems/jewellery whose resolved bucket is
  carried). The Basic-mode `carrying_treasure` toggle stays, now scoped to carried
  treasure.

### Wealth readout

`total_wealth_gp(spec)` = carried+stashed+animal+vehicle coin value + gem value +
effective jewellery value, **excluding retainers**. Rendered read-only where the coin
tracker used to be.

---

## Shop spend engine (`aose/engine/shop.py`)

`spend(spec, cost_gp) -> None` (raises `InsufficientFunds`), operating on **loose
Carried coin stacks only** (coins whose `location.kind == "carried"`; coins inside a
carried container are *not* auto-spent — pull them out first).

### Algorithm

Cost is always whole gp (no item costs < 1gp). Denominations are each an integer
multiple of the next-lower (`cp 1, sp 10, ep 50, gp 100, pp 500`).

1. If total carried-loose coin value (cp) < `cost_cp` → `InsufficientFunds`.
2. **Exact, lowest-first:** process denominations low→high; for each, spend the
   maximum coins of that denom such that the remaining cost stays exactly payable by
   the higher denominations still available. Yields the agreed behaviour:
   `2gp` against `2gp + 102cp` → spend `100cp + 1gp` (keep `2cp + 1gp`);
   `3gp` against `2gp + 250cp` → spend `200cp + 1gp` (keep `50cp + 1gp`).
3. **Change exception:** if no exact payment exists, pay with the smallest larger-coin
   selection that overshoots and **refund the difference as a carried gp stack**.
   (Because prices are whole gp and pp/gp are whole-gp multiples, change is always
   whole gp.)

The payment removes coins from carried stacks (pruning empties) and adds any change to
the carried gp stack. `buy()` calls `spend` instead of decrementing `gold`. Selling /
refunding and GM grants add to the carried gp stack. Wizard starting gold creates a
carried gp stack; the equipment-step buy path uses `spend`.

---

## UI reorganization (`_equipment_ui.html` + view builder)

The "Carried" pane of the shared equipment partial becomes a stack of collapsible
**top-level inventory groups**, each rendered by one reusable macro:

| Top-level | Subsections |
|---|---|
| **Carried** | Equipped (PC slots) · Loose · Coins · Treasure · Containers |
| **Stashed** | Loose · Coins · Treasure · Containers |
| **each Animal** | Equipped (barding) · Loose · Coins · Treasure · Containers |
| **each Vehicle** | Loose · Coins · Treasure · Containers |
| **each Retainer** | Equipped · Loose · Coins · Treasure · Containers (via `build_sheet` recursion, same macro) |

All top-levels render inline in the one inventory section. Retainer groups duplicate
the retainer card for now (accepted).

### Per-row controls

- **Item / container / value-stack** → a **Move** dropdown: Carried, Stashed, each
  Animal/Vehicle/Retainer, and — within the current top-level — *into* each container
  / *out of* container. One POST per move (`/inventory/move-*`).
- **Coin stack** → Move + **Convert** (to another denom, in place) + add/remove.
- **Treasure** → Move + existing sell / adjust / mark-damaged.
- **Container** → expand inline; header shows `used/capacity` and rolled-up effective
  weight; children (loose items + coin/treasure stacks) each carry take-out/move.

### Removed

The standalone coin tracker, the `show_gold_grant` gold +/- block, and the
money-change form. A read-only **total wealth** line takes the tracker's place. Coin
add/convert live per-stack.

### View builder (`aose/sheet/view.py` + inventory view)

The inventory view model becomes a list of **TopLevelGroup**s, each with `equipped`,
`loose`, `coins`, `treasure`, `containers` view sections and resolved per-row Move
destination lists. Coin/treasure rows resolve their location for rendering and for the
Move control's option list.

---

## Routes (`aose/web/routes.py`)

New/`reshaped` POST endpoints under `/character/{id}` (and wizard equivalents where
relevant). Standard `_load_spec_or_404 → mutate → save_character → 303` pattern:

- `/inventory/move-item`, `/inventory/move-container`, `/inventory/move-coins`,
  `/inventory/move-valuable` — payload + `dest_kind`/`dest_id` (or `retainer:<id>`).
- `/coins/convert` — reshaped to per-stack (`location` + `frm`/`to`/`count`).
- `/coins/add` — reshaped to per-location grant.
- Retired: the old global gold-grant, the global `/coins/convert`, container
  `stash-container`/`unstash-container`/`stow`/`take-out` (folded into move-*).

Existing buy/sell/refund routes keep their URLs; their engine calls swap to `spend` /
carried-gp helpers.

---

## Testing

- **Model coercion**: old int-coin saves → carried CoinStacks; old container
  `state`+`location` → `StorageLocation`; missing gem/jewellery location → carried.
- **Movement**: every payload type to every destination kind, including into/out of
  containers and to/from retainers; container move carries contents (pointer model).
- **Convert**: per-location whole-coin enforcement; `CurrencyError` cases.
- **Encumbrance**: carried-only weight; stashed/on-carrier excluded; carried-container
  contents counted; treasure carried-only.
- **Wealth**: total across PC buckets excludes retainers.
- **Shop spend**: the two worked examples; insufficient funds; the gp-change exception;
  loose-carried-only (coins in a carried container are not spent).
- **Regression**: existing companion/retainer transfer, container, valuables, and
  currency tests updated to the new shapes.

## Docs to update on landing

- `docs/CHANGELOG.md` — one row (date, feature, branch, slug).
- `docs/ARCHITECTURE.md` — edit the **Inventory/containers/encumbrance** and
  **Currency, treasure & valuables** sections in place (StorageLocation pointer model,
  location-aware coins/treasure, movement engine, carried-only encumbrance, shop spend).
- `CLAUDE.md` — update the **Storage shapes** bullets (coins/treasure now located;
  `ContainerInstance.location` is a `StorageLocation`; five int coin fields retired).

## Decomposition

Sized for sequential plans (each ends green):

- **Plan 1 — Model + movement/currency engines** (`StorageLocation`, `CoinStack`,
  located gems/jewellery, container refactor, coercion validators, `storage.py`,
  currency/encumbrance/wealth rework). Engine + model tests, no UI.
- **Plan 2 — Shop spend** (`spend` algorithm + change exception; buy/sell/refund and
  wizard wiring onto carried coins).
- **Plan 3 — UI + routes** (top-level group macro, per-row Move/Convert, container
  inline expansion, removal of coin tracker/money-change, wealth readout, move routes,
  print sheet).
