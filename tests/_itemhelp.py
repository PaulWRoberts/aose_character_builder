"""Test helper: coerce legacy inventory/stashed/equipped kwargs into the
unified ``items`` list of ItemInstances.

The item-identity refactor replaced ``inventory``/``stashed``/``equipped`` on
CharacterSpec with a single ``items: list[ItemInstance]``.  Many tests built
specs with the old kwargs; this helper translates them in place so those test
constructors keep working with minimal edits.
"""
from aose.models import ItemInstance
from aose.models.storage import StorageLocation

_counter = [0]


def _iid(prefix: str) -> str:
    _counter[0] += 1
    return f"t_{prefix}_{_counter[0]}"


def coerce_equipment(kwargs: dict) -> None:
    """Pop legacy ``inventory`` / ``stashed`` / ``equipped`` from ``kwargs`` and
    merge them into ``kwargs['items']`` as ItemInstances.  Equipped catalog ids
    that also appear in inventory share one instance (with ``equip`` set).
    Mutates ``kwargs`` in place."""
    if not any(k in kwargs for k in ("inventory", "stashed", "equipped")):
        return
    inventory = list(kwargs.pop("inventory", []) or [])
    stashed = list(kwargs.pop("stashed", []) or [])
    equipped = dict(kwargs.pop("equipped", {}) or {})
    items = list(kwargs.get("items", []) or [])

    # Equipped slots: consume one matching carried catalog id if present.
    catalog_to_slot: dict[str, str] = {}
    for slot, cid in equipped.items():
        catalog_to_slot.setdefault(cid, slot)

    for cid in inventory:
        slot = None
        if cid in catalog_to_slot:
            slot = catalog_to_slot.pop(cid)
        items.append(ItemInstance(instance_id=_iid(cid), catalog_id=cid, equip=slot))

    # Equipped ids not in inventory: add them equipped anyway.
    for cid, slot in catalog_to_slot.items():
        items.append(ItemInstance(instance_id=_iid(cid), catalog_id=cid, equip=slot))

    for cid in stashed:
        items.append(ItemInstance(instance_id=_iid(cid), catalog_id=cid,
                                  location=StorageLocation(kind="stashed")))

    kwargs["items"] = items
