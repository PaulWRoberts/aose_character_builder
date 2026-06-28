import pytest
from aose.models import CharacterSpec, ClassEntry, ItemInstance, CoinStack
from aose.models.storage import StorageLocation

CARRIED = StorageLocation(kind="carried")


def _spec(**kw):
    base = dict(
        name="Hero",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_item_instance_defaults():
    ii = ItemInstance(instance_id="i1", catalog_id="sword")
    assert ii.location == CARRIED
    assert ii.count == 1
    assert ii.equip is None
    assert ii.enchantment_id is None
    assert ii.tailored is True
    assert ii.loaded_ammo_id is None


def test_spec_has_items_list_and_no_legacy_fields():
    spec = _spec(items=[ItemInstance(instance_id="i1", catalog_id="sword", equip="main_hand")])
    assert spec.items[0].equip == "main_hand"
    # Legacy fields are gone (extra="forbid" rejects them).
    for legacy in ("inventory", "stashed", "equipped", "loaded_ammo", "armor_tailored",
                   "enchanted", "ammo"):
        with pytest.raises(Exception):
            _spec(**{legacy: [] if legacy in ("inventory", "stashed", "enchanted", "ammo")
                     else {}})


def test_item_instance_carries_enchantment_and_count():
    # An enchanted weapon and a stack of ammo are ItemInstances — one type.
    plus1 = ItemInstance(instance_id="e1", catalog_id="sword",
                         enchantment_id="generic_plus_1", equip="main_hand")
    assert plus1.enchantment_id == "generic_plus_1" and plus1.equip == "main_hand"
    arrows = ItemInstance(instance_id="a1", catalog_id="arrow", count=20)
    assert arrows.count == 20 and arrows.enchantment_id is None


def test_enchanted_instance_and_ammo_stack_are_gone():
    import aose.models as m
    assert not hasattr(m, "EnchantedInstance")
    assert not hasattr(m, "AmmoStack")


def test_coin_stack_has_instance_id():
    c = CoinStack(instance_id="c1", denom="gp", count=10)
    assert c.instance_id == "c1"


