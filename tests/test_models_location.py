from aose.models import MagicItemInstance, EnchantedInstance, AmmoStack
from aose.models.storage import StorageLocation


def test_instances_default_to_carried():
    m = MagicItemInstance(instance_id="m1", catalog_id="ring_protection_plus_1")
    e = EnchantedInstance(instance_id="e1", base_id="sword", enchantment_id="generic_plus_1")
    a = AmmoStack(instance_id="a1", base_id="arrow", count=20)
    assert m.location == StorageLocation(kind="carried")
    assert e.location == StorageLocation(kind="carried")
    assert a.location == StorageLocation(kind="carried")


def test_instance_accepts_explicit_location():
    loc = StorageLocation(kind="animal", id="mule1")
    a = AmmoStack(instance_id="a1", base_id="arrow", count=20, location=loc)
    assert a.location == loc


def test_legacy_save_without_location_coerces_to_carried():
    # Old saves never wrote `location`; Pydantic must accept the absence.
    a = AmmoStack.model_validate({"instance_id": "a1", "base_id": "arrow", "count": 5})
    assert a.location == StorageLocation(kind="carried")
