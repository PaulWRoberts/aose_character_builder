"""Carcass Crawler 3 expanded equipment content."""
from pathlib import Path

import pytest

from aose.data.loader import GameData

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def data():
    return GameData.load(DATA_DIR)


def test_source_registered(data):
    assert "carcass_crawler_3" in data.sources
    assert data.sources["carcass_crawler_3"].core is False
