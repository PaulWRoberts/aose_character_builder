"""Model location tests — updated for the unified ItemInstance model."""
from aose.models import ItemInstance, MagicItemInstance
from aose.models.storage import StorageLocation


def test_item_instance_defaults_to_carried():
    i = ItemInstance(instance_id="i1", catalog_id="sword")
    assert i.location == StorageLocation(kind="carried")


def test_magic_item_instance_defaults_to_carried():
    m = MagicItemInstance(instance_id="m1", catalog_id="ring_protection_plus_1")
    assert m.location == StorageLocation(kind="carried")


def test_item_instance_accepts_explicit_location():
    loc = StorageLocation(kind="animal", id="mule1")
    i = ItemInstance(instance_id="i1", catalog_id="arrow", count=20, location=loc)
    assert i.location == loc


def test_item_instance_validate_without_location_coerces_to_carried():
    i = ItemInstance.model_validate({"instance_id": "a1", "catalog_id": "arrow", "count": 5})
    assert i.location == StorageLocation(kind="carried")


def test_item_instance_enchanted_fields():
    i = ItemInstance(instance_id="e1", catalog_id="sword", enchantment_id="generic_plus_1")
    assert i.enchantment_id == "generic_plus_1"
    assert i.equip is None
