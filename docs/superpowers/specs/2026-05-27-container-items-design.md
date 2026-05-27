# Container Items — Design

**Date:** 2026-05-27
**Status:** Approved
**Implements:** Container-item support for the AOSE Character Builder.

## Goal

Let a character own containers (backpack, sacks, saddle bags, Bag of Holding)
that hold other items. Items inside a container cannot be equipped.
Containers have a capacity limit (or unlimited) and a weight multiplier
that lets some containers wholly or partially suppress the weight of their
contents.

## Decisions

| Question | Decision |
|---|---|
| Container identity | Per-instance. Each container gets a `uuid4` `instance_id`; two of the same catalog id are independent. |
| Weight suppression | Multiplier `0.0–1.0` per container. `1.0` is normal; `0.06` for a Bag of Holding (10 000 cn × 0.06 = 600 cn at full); `0.0` is pure flavor case (no real OSE item, but supported). |
| Nesting | Not allowed. A container's `contents` only holds non-container items. |
| Stash + contents | Contents follow the container's state. Stashing a backpack stashes everything inside; carried containers' contents count for weight (with multiplier). |
| Capacity overrun | Hard block. The `stow` helper raises `ContainerFull`; the HTTP layer returns 400 with the message. |
| Drop / Sell / Refund | Drop takes contents with it (no refund). Sell and Refund require an empty container — raise `ContainerNotEmpty` otherwise. |
| UI | Inline rows in the existing inventory table, with a collapse button per container. Explicit Take-Out / Stow-In actions AND drag-and-drop. Page reload after each move in V1. |
| Take-Out destination | Item joins inventory if container is carried; joins stashed list if container is stashed. Player can unstash the container first to retrieve "into hand". |
| Stow source | Only from carried loose inventory. To stow a stashed item, unstash it first. |
| Capacity metric | Raw contents weight (multiplier doesn't grant infinite capacity — capacity is physical volume). |

## Data Model

### New `Container` catalog variant (`aose/models/item.py`)

```python
class Container(ItemBase):
    item_type: Literal["container"]
    capacity_cn: int | None = None     # None → unlimited
    weight_multiplier: float = 1.0     # 0.0..1.0; multiplies contents' weight when carried
```

`Container` is added to the `Item = Annotated[Union[...], Field(discriminator="item_type")]` union and re-exported from `aose/models/__init__.py`.

### New `ContainerInstance` runtime model (`aose/models/character.py`)

```python
class ContainerInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str                                   # uuid4 hex
    catalog_id: str                                    # references a Container item
    state: Literal["carried", "stashed"]
    contents: list[str] = Field(default_factory=list)  # catalog ids
```

### `CharacterSpec` gains one field

```python
containers: list[ContainerInstance] = Field(default_factory=list)
```

### Invariants

Enforced by helpers; no Pydantic validator on the spec (would force every read to be valid; we want write-time rules instead).

1. A container's `state` is `"carried"` or `"stashed"` — never `"equipped"`.
2. A catalog id whose `item_type == "container"` never appears in `inventory` or `stashed`. Buying a container creates a `ContainerInstance`; it does not append to `inventory`.
3. A catalog id present in some `container.contents` is not also in `inventory` or `stashed` (no double counting).
4. `Container` items are never `equip`-targets (rejected at the engine layer).

### Migration

Existing saved characters lack the `containers` field. Pydantic's `default_factory=list` populates an empty list on load — no migration script.

## Engine API

### `aose/engine/shop.py` — new helpers

```python
def new_container_instance(catalog_id: str, data: GameData,
                           state: Literal["carried", "stashed"] = "carried"
                           ) -> ContainerInstance
```
Validates that `data.items[catalog_id]` is a `Container`. Generates a fresh `uuid4().hex`.

```python
def buy_container(containers: list[ContainerInstance], gold: int,
                  catalog_id: str, data: GameData
                  ) -> tuple[list[ContainerInstance], int]
```
Like `buy()` but appends a `ContainerInstance` and deducts cost. Raises `InsufficientGold` / `UnknownItem` consistent with `buy()`.

```python
def add_free_container(containers: list[ContainerInstance],
                       catalog_id: str, data: GameData
                       ) -> list[ContainerInstance]
```

```python
def stow(inventory: list[str], stashed: list[str],
         containers: list[ContainerInstance],
         equipped: dict[str, str], equipped_weapons: list[str],
         instance_id: str, item_id: str, data: GameData
         ) -> tuple[list[str], list[str], list[ContainerInstance]]
```
Move one copy of `item_id` from `inventory` (only — not `stashed`, per decision) into `containers[instance].contents`. Raises:
- `UnknownContainer` if `instance_id` not found
- `ValueError("not in inventory")` if `item_id` not in `inventory`
- `ValueError("containers cannot be stowed")` if `item_id` is itself a Container catalog item
- `ValueError("item is equipped")` if equipping this id would prevent stowing (must unequip first)
- `ContainerFull` if raw used weight would exceed `capacity_cn`

```python
def take_out(inventory: list[str], stashed: list[str],
             containers: list[ContainerInstance],
             instance_id: str, item_id: str
             ) -> tuple[list[str], list[str], list[ContainerInstance]]
```
Removes one copy from contents. Adds to `inventory` if the container's state is `carried`, to `stashed` if `stashed`.

```python
def stash_container(containers: list[ContainerInstance],
                    instance_id: str
                    ) -> list[ContainerInstance]
def unstash_container(containers: list[ContainerInstance],
                      instance_id: str
                      ) -> list[ContainerInstance]
```
Flip the `state` field. Contents follow implicitly.

```python
def remove_container(containers: list[ContainerInstance], gold: int,
                     instance_id: str, mode: str, data: GameData
                     ) -> tuple[list[ContainerInstance], int]
```
- `mode="drop"`: removes the instance entirely (contents gone with it). Returns `(new_containers, gold)`.
- `mode="sell"` / `"refund"`: raises `ContainerNotEmpty` if `contents` is non-empty; otherwise removes and refunds.

### New exceptions

```python
class ContainerFull(ValueError): ...
class ContainerNotEmpty(ValueError): ...
class UnknownContainer(ValueError): ...
```

### New view model — `ContainerView`

```python
class ContainerView(BaseModel):
    instance_id: str
    catalog_id: str
    name: str
    state: Literal["carried", "stashed"]
    capacity_cn: int | None
    used_cn: int                # sum of raw weight of contents
    weight_multiplier: float
    own_weight_cn: int
    effective_weight_cn: int    # own + int(multiplier * used_cn) — only meaningful when carried
    contents: list[InventoryRow]
```

### `InventoryView` extension

```python
class InventoryView(BaseModel):
    equipped: list[InventoryRow]
    carried: list[InventoryRow]   # loose carried, NOT in any container
    stashed: list[InventoryRow]   # loose stashed, NOT in any container
    containers: list[ContainerView]   # both carried + stashed instances; template splits by state
```

### `inventory_view()` signature

```python
def inventory_view(inventory: list[str], stashed: list[str],
                   equipped: dict[str, str], equipped_weapons: list[str],
                   containers: list[ContainerInstance],
                   data: GameData) -> InventoryView
```

### `aose/engine/encumbrance.py` — `carried_weight_cn`

```python
def carried_weight_cn(spec, data) -> int:
    total = sum(weight of each id in spec.inventory)
    for c in spec.containers:
        if c.state != "carried":
            continue
        catalog = data.items.get(c.catalog_id)
        if catalog is None:
            continue
        total += catalog.weight_cn
        raw = sum(data.items[x].weight_cn for x in c.contents if x in data.items)
        total += int(catalog.weight_multiplier * raw)   # floor, OSE convention
    return total
```

Stashed containers contribute zero (parallel to stashed loose items).

### `aose/engine/equip.py` guard

`equip()` already rejects items not in `inventory`; since items inside containers aren't in `inventory` (invariant 3), they naturally can't be equipped. Add one explicit check at the top for clarity:

```python
if isinstance(data.items.get(item_id), Container):
    raise ValueError("containers are not equippable")
```

## HTTP Routes

Mirrored on sheet (`/character/{id}/equipment/…`) and wizard (`/wizard/{id}/equipment/…`).

| Method | Path suffix | Body | Engine call |
|---|---|---|---|
| POST | `/buy` | `item_id` | Augmented: if catalog is `Container` → `buy_container`, else existing `buy` |
| POST | `/add` | `item_id` | Same augmentation |
| POST | `/stow` | `instance_id`, `item_id`, `from_state` | `stow()` |
| POST | `/take-out` | `instance_id`, `item_id` | `take_out()` |
| POST | `/stash-container` | `instance_id` | `stash_container()` |
| POST | `/unstash-container` | `instance_id` | `unstash_container()` |
| POST | `/remove-container` | `instance_id`, `mode` | `remove_container()` — 400 if non-empty for sell/refund |
| POST | `/move` | `source`, `target`, `item_id`, `instance_id?` | Unified DnD dispatcher |

`/move` dispatch table (`source` × `target`):

| Source | Target | Action |
|---|---|---|
| `carried` | `equipped` | `equip` |
| `equipped` | `carried` | `unequip` |
| `carried` | `stashed` | move id from inventory → stashed list |
| `stashed` | `carried` | reverse |
| `carried` | `container:<id>` | `stow` (engine helper is narrow: source must be inventory) |
| `equipped` | `container:<id>` | Two-step: `unequip` → `stow` |
| `stashed` | `container:<id>` | Two-step: move id from stashed list → inventory, then `stow` |
| `container:<X>` | `carried` | `take_out` (lands in inventory because container is carried) |
| `container:<X>` | `stashed` | `take_out` if container is stashed; otherwise `take_out` → move from inventory to stashed list |
| `container:<X>` | `container:<Y>` | `take_out` from X then `stow` into Y |
| `container_row:<X>` | `stashed` section | `stash_container` |
| `container_row:<X>` | `carried` section | `unstash_container` |

Invalid combinations return 400. All other 4xx semantics match existing routes (400 on user errors, 404 for missing character).

## UI Rendering

### Inventory table

Containers and their contents share the existing `<table class="inventory-table">` in the Carried and Stashed sections of `_equipment_ui.html`. Contents are rendered as child rows immediately after their container, indented via a `container-child` class.

Container row:

```html
<tr class="container-row" data-instance-id="{{ c.instance_id }}" data-state="{{ c.state }}">
  <td>
    <button class="container-toggle" aria-expanded="true" aria-controls="cnt-{{ c.instance_id }}">▾</button>
    <strong>{{ c.name }}</strong>
    <span class="capacity-badge{% if c.capacity_cn and c.used_cn >= c.capacity_cn %} capacity-full{% endif %}">
      {{ c.used_cn }} / {{ c.capacity_cn or "∞" }} cn
    </span>
  </td>
  <td class="num">—</td>
  <td class="num">{{ c.effective_weight_cn }} cn</td>
  <td>
    {# Stash/Unstash, Drop (always), Sell+Refund disabled when contents non-empty #}
  </td>
</tr>
```

Loose carried rows that have at least one carried container available get a Stow control:

```html
<form method="post" action="…/stow" class="inline-form">
  <input type="hidden" name="item_id" value="{{ row.id }}">
  <input type="hidden" name="from_state" value="carried">
  <select name="instance_id">
    {% for c in carried_containers %}
      <option value="{{ c.instance_id }}">{{ c.name }}</option>
    {% endfor %}
  </select>
  <button type="submit">Stow</button>
</form>
```

### Drag-and-drop

One new file `aose/web/static/inventory_dnd.js` (~150 lines vanilla JS). Each draggable row carries `draggable="true"` and `data-source`; drop targets carry `data-target`. On `drop`, JS reads the attributes and POSTs to `/equipment/move` with the right payload. On success → `window.location.reload()` (V1 simplicity; partial DOM updates are a follow-up).

Drop targets: section headers (`<h4 class="inv-section-head">`) for Equipped / Carried / Stashed, container rows themselves (drop = stow into that container).

### CSS additions (`aose/web/static/sheet.css`)

- `.container-row` highlight band
- `.container-child` indent (padding-left)
- `.container-toggle` chevron, rotates on collapse
- `.container-collapsed` hides child rows
- `.capacity-badge` muted pill; `.capacity-full` red variant
- `.drag-over` highlight on drop targets

### Print path

Print-only block in `sheet.html` adds a container summary:
```
Backpack (320/400 cn): Long Sword, Torch ×2
Stashed:
  Saddle Bags (200/300 cn): Rope, Iron Spikes ×6
```

### Buttons remain alongside DnD

Accessibility: every drag op has a button or form-based equivalent.

## Seed Data — `data/equipment/containers.yaml`

```yaml
- id: backpack
  name: Backpack
  category: containers
  item_type: container
  cost_gp: 5
  weight_cn: 80
  capacity_cn: 400
  weight_multiplier: 1.0

- id: sack_small
  name: Sack, Small
  category: containers
  item_type: container
  cost_gp: 1
  weight_cn: 5
  capacity_cn: 200
  weight_multiplier: 1.0

- id: sack_large
  name: Sack, Large
  category: containers
  item_type: container
  cost_gp: 2
  weight_cn: 20
  capacity_cn: 600
  weight_multiplier: 1.0

- id: saddle_bags
  name: Saddle Bags
  category: containers
  item_type: container
  cost_gp: 4
  weight_cn: 50
  capacity_cn: 300
  weight_multiplier: 1.0

- id: bag_of_holding
  name: Bag of Holding
  category: miscellaneous_magic_items
  item_type: container
  cost_gp: 0
  weight_cn: 0
  capacity_cn: 10000
  weight_multiplier: 0.06
```

`_category_label` title-cases category ids, so `containers` → "Containers" and `miscellaneous_magic_items` → "Miscellaneous Magic Items" automatically.

## Tests — new `tests/test_containers.py`

### Engine (pure)

- `Container` catalog item parses from YAML and is reachable as `data.items["backpack"]`
- `new_container_instance` generates a unique id on each call
- `buy_container` deducts gold and appends an instance
- `add_free_container` appends without deducting gold
- `stow` moves an item from inventory → contents
- `stow` raises `ContainerFull` when raw weight would exceed `capacity_cn`
- `stow` raises when item is equipped
- `stow` raises when item is itself a container (no nesting)
- `stow` raises `UnknownContainer` for a bad instance id
- `take_out` returns item to inventory when container is carried
- `take_out` returns item to stashed list when container is stashed
- `stash_container` flips state; carried weight excludes contents afterwards
- `unstash_container` reverses
- `weight_multiplier = 1.0` → contents contribute full weight (carried)
- `weight_multiplier = 0.5` → contents contribute half (floored)
- `weight_multiplier = 0.0` → contents contribute zero (still own_weight applies)
- Bag of Holding at full capacity: 600 cn effective (0.06 × 10000)
- Capacity uses raw weight, not multiplier-adjusted (Bag of Holding can hold 10 000 cn, not infinite)
- `remove_container` `mode="drop"`: instance + contents gone, no gold change
- `remove_container` `mode="sell"` on non-empty: raises `ContainerNotEmpty`
- `remove_container` `mode="refund"` on non-empty: raises
- `remove_container` `mode="sell"` on empty: returns cost // 2 refund
- `equip()` raises when target is a Container catalog item

### Sheet integration

- `inventory_view` returns containers split by state in the resulting structure
- `carried_weight_cn` includes carried container own-weight + multiplier × contents
- Stashed container yields zero weight contribution
- Sheet `effective_weight_cn` matches the OSE Bag-of-Holding-at-full rule (600 cn)

### HTTP (sheet + wizard)

- Buy a container creates an instance (not an inventory entry)
- Stow / take-out endpoints round-trip and persist
- Stash-container endpoint flips state
- Drop endpoint on non-empty container wipes contents
- Sell endpoint on non-empty returns 400
- `/equipment/move` happy paths:
  - `carried → equipped` ⇒ equipped
  - `carried → container:X` ⇒ stowed
  - `container:X → carried` ⇒ taken out to inventory
  - `container_row:X → stashed` section ⇒ container stashed
- `/equipment/move` invalid combo returns 400
- Sheet HTML renders container row, content rows, and capacity badge
- Sheet HTML renders the new "Miscellaneous Magic Items" shop section with Bag of Holding

## Out of Scope (deferred)

- Container nesting (explicitly ruled out by design).
- Per-instance customisation of non-containers (would need the broader instance-id refactor, approach B).
- Partial-DOM updates instead of full page reload on move.
- Magic-only flagging (Bag of Holding currently appears in the shop with `cost_gp: 0`; if GM-grant-only is wanted later, add a `magic_only` field and gate the Buy button).
- Bag of Holding "size of objects" rule (10' × 5' × 3'): there's no volume model for items in the engine; capacity is purely coin-weight-based.
