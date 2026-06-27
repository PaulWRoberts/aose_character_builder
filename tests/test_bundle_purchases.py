"""Bundle purchase / per-unit sell / whole-stack refund coverage."""
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


from aose.engine.shop import shop_categories, inventory_view


def test_shop_item_exposes_bundle_count():
    cats = shop_categories(_fake_data())
    items = {i.id: i for c in cats for i in c.items}
    assert items["torch"].bundle_count == 6
    assert items["crowbar"].bundle_count == 1


def test_inventory_row_per_unit_sell_and_refund_flags():
    view = inventory_view(["torch"] * 6, [], {}, [], _fake_data())
    torch_row = next(r for r in view.carried if r.id == "torch")
    assert torch_row.bundle_count == 6
    assert torch_row.sell_gp == 0          # int((1/6)/2)
    assert torch_row.can_refund is True    # 6 >= 6


def test_inventory_row_cannot_refund_partial_stack():
    view = inventory_view(["torch"] * 5, [], {}, [], _fake_data())
    torch_row = next(r for r in view.carried if r.id == "torch")
    assert torch_row.can_refund is False   # 5 < 6
