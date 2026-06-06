from pathlib import Path

from aose.data.loader import GameData
from aose.engine.shop import inventory_view

DATA = GameData.load(Path(__file__).parent.parent / "data")


def test_inventory_row_carries_item_description():
    # Pick any catalog item that has a description.
    item = next(i for i in DATA.items.values() if getattr(i, "description", ""))
    view = inventory_view([item.id], [], {}, [], None, DATA)
    assert view.carried[0].description == item.description


def test_inventory_row_description_defaults_empty_for_stale_id():
    view = inventory_view(["no_such_item"], [], {}, [], None, DATA)
    assert view.carried[0].description == ""


from aose.engine.detail import DetailCard  # noqa: E402
from aose.models import Weapon  # noqa: E402


def test_inventory_row_carries_detail_card():
    weapon = next(i for i in DATA.items.values() if isinstance(i, Weapon))
    view = inventory_view([weapon.id], [], {}, [], None, DATA)
    row = view.carried[0]
    assert isinstance(row.detail, DetailCard)
    assert any(s.label == "Damage" for s in row.detail.stats)


def test_inventory_row_detail_none_for_stale_id():
    view = inventory_view(["no_such_item"], [], {}, [], None, DATA)
    assert view.carried[0].detail is None
