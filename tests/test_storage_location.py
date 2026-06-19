import pytest
from pydantic import ValidationError
from aose.models.storage import StorageLocation, CoinStack


def test_storage_location_defaults_to_carried_with_no_id():
    loc = StorageLocation(kind="carried")
    assert loc.kind == "carried"
    assert loc.id is None


def test_storage_location_container_carries_an_id():
    loc = StorageLocation(kind="container", id="abc123")
    assert loc.id == "abc123"


def test_storage_locations_equal_by_kind_and_id():
    assert StorageLocation(kind="animal", id="x") == StorageLocation(kind="animal", id="x")
    assert StorageLocation(kind="animal", id="x") != StorageLocation(kind="animal", id="y")


def test_coin_stack_defaults_to_carried():
    s = CoinStack(denom="gp", count=5)
    assert s.location == StorageLocation(kind="carried")
    assert (s.denom, s.count) == ("gp", 5)


def test_coin_stack_rejects_unknown_denom():
    with pytest.raises(ValidationError):
        CoinStack(denom="zp", count=1)


# ---------------------------------------------------------------------------
# Task 2: Located gems & jewellery
# ---------------------------------------------------------------------------
from aose.models import GemStack, JewelleryPiece
from aose.models.storage import StorageLocation


def test_gem_stack_defaults_to_carried_location():
    g = GemStack(instance_id="g1", value=100)
    assert g.location == StorageLocation(kind="carried")


def test_gem_stack_accepts_explicit_location():
    g = GemStack(instance_id="g1", value=100, location=StorageLocation(kind="vehicle", id="v1"))
    assert g.location.kind == "vehicle"


def test_jewellery_defaults_to_carried_location():
    j = JewelleryPiece(instance_id="j1", value=300)
    assert j.location == StorageLocation(kind="carried")


# ---------------------------------------------------------------------------
# Task 3: CharacterSpec.coins replaces the five int fields
# ---------------------------------------------------------------------------
from aose.models import CharacterSpec, CoinStack


def _minimal_spec_dict(**extra):
    base = dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10,
                             "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral",
    )
    base.update(extra)
    return base


def test_legacy_int_coins_coerced_to_carried_stacks():
    spec = CharacterSpec.model_validate(
        _minimal_spec_dict(gold=12, silver=3, platinum=0)
    )
    by_denom = {s.denom: s for s in spec.coins}
    assert by_denom["gp"].count == 12
    assert by_denom["gp"].location.kind == "carried"
    assert by_denom["sp"].count == 3
    assert "pp" not in by_denom            # zero denominations dropped
    # legacy attributes are gone
    assert not hasattr(spec, "gold")


def test_new_spec_defaults_to_empty_coins():
    spec = CharacterSpec.model_validate(_minimal_spec_dict())
    assert spec.coins == []


# ---------------------------------------------------------------------------
# Task 4: ContainerInstance.location as StorageLocation
# ---------------------------------------------------------------------------
from aose.models import ContainerInstance


def test_container_new_shape_uses_storage_location():
    c = ContainerInstance(instance_id="c1", catalog_id="backpack",
                          location=StorageLocation(kind="stashed"))
    assert c.location.kind == "stashed"


def test_container_legacy_state_location_coerced():
    # old shape: state + location(person/animal/vehicle) + location_id
    c = ContainerInstance.model_validate({
        "instance_id": "c1", "catalog_id": "backpack",
        "state": "stashed", "location": "person", "location_id": None,
        "contents": ["torch"],
    })
    assert c.location == StorageLocation(kind="stashed")
    assert c.contents == ["torch"]


def test_container_legacy_on_animal_coerced():
    c = ContainerInstance.model_validate({
        "instance_id": "c1", "catalog_id": "saddlebags",
        "state": "carried", "location": "animal", "location_id": "a1",
    })
    assert c.location == StorageLocation(kind="animal", id="a1")


def test_container_rejects_nested_container_location():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ContainerInstance(instance_id="c1", catalog_id="backpack",
                          location=StorageLocation(kind="container", id="c2"))
