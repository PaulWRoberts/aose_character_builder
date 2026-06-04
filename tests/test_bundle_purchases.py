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


from aose.engine.shop import remove, remove_from_stash


def test_sell_one_bundle_unit_uses_per_unit_price():
    # torch: cost 1 / bundle 6 -> per-unit 0.166, half 0.083 -> 0 (worthless)
    inv, gold, _eq, _wp = remove(["torch"] * 6, 0, "torch", "sell", _fake_data())
    assert inv == ["torch"] * 5      # only one unit removed
    assert gold == 0                 # worthless


def test_sell_single_item_half_price():
    inv, gold, _eq, _wp = remove(["crowbar"], 0, "crowbar", "sell", _fake_data())
    assert inv == []
    assert gold == 5                 # 10 // 2


def test_refund_removes_full_stack_and_returns_full_cost():
    inv, gold, _eq, _wp = remove(["torch"] * 6, 0, "torch", "refund", _fake_data())
    assert inv == []                 # whole stack of 6 removed
    assert gold == 1                 # full bundle price back


def test_refund_requires_full_stack():
    with pytest.raises(ValueError, match="full stack"):
        remove(["torch"] * 5, 0, "torch", "refund", _fake_data())


def test_drop_one_unit_no_refund():
    inv, gold, _eq, _wp = remove(["torch"] * 6, 0, "torch", "drop", _fake_data())
    assert inv == ["torch"] * 5
    assert gold == 0


def test_stash_refund_removes_full_stack():
    stashed, gold = remove_from_stash(["torch"] * 6, 0, "torch", "refund", _fake_data())
    assert stashed == []
    assert gold == 1
