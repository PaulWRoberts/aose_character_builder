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
