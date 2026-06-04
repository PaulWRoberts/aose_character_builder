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
