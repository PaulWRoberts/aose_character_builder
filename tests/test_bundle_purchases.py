"""Bundle purchase / per-unit sell / whole-stack refund coverage."""
import pytest

from aose.data.loader import GameData
from aose.models import AdventuringGear


def test_adventuring_gear_has_bundle_count_default_one():
    g = AdventuringGear(
        id="crowbar", name="Crowbar", category="adventuring_gear",
        item_type="gear", cost_gp=10,
    )
    assert g.bundle_count == 1


def test_adventuring_gear_accepts_bundle_count():
    g = AdventuringGear(
        id="torch", name="Torch", category="adventuring_gear",
        item_type="gear", cost_gp=1, bundle_count=6,
    )
    assert g.bundle_count == 6


from aose.engine.shop import buy, add_free
from aose.models import Container


def _fake_data():
    """Tiny GameData stand-in: one bundle gear item, one single gear item."""
    return GameData(items={
        "torch": AdventuringGear(
            id="torch", name="Torch", category="adventuring_gear",
            item_type="gear", cost_gp=1, bundle_count=6,
        ),
        "crowbar": AdventuringGear(
            id="crowbar", name="Crowbar", category="adventuring_gear",
            item_type="gear", cost_gp=10,  # bundle_count defaults to 1
        ),
    })


def test_buy_bundle_adds_bundle_count_units_one_charge():
    inv, gold = buy([], 10, "torch", _fake_data())
    assert inv == ["torch"] * 6
    assert gold == 9  # one 1 gp charge for the whole stack


def test_buy_single_item_unchanged():
    inv, gold = buy([], 10, "crowbar", _fake_data())
    assert inv == ["crowbar"]
    assert gold == 0


def test_add_free_bundle_adds_exactly_one():
    inv = add_free([], "torch", _fake_data())
    assert inv == ["torch"]
