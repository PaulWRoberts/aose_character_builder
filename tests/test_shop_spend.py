import uuid
from pathlib import Path
import pytest
from aose.engine import shop
from aose.models import CharacterSpec, CoinStack, ClassEntry, ItemInstance
from aose.models.storage import StorageLocation
from aose.data.loader import GameData

_SHOP_DATA = GameData.load(Path(__file__).parent.parent / "data")


def _spec(coins):
    return CharacterSpec.model_validate(dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10,
                             "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral", coins=coins,
    ))


def _carried(spec):
    return {c.denom: c.count for c in spec.coins if c.location.kind == "carried"}


def test_spend_example_102cp_2gp_buy_2gp():
    spec = _spec([CoinStack(denom="cp", count=102), CoinStack(denom="gp", count=2)])
    shop.spend(spec, 2)
    assert _carried(spec) == {"cp": 2, "gp": 1}


def test_spend_example_250cp_2gp_buy_3gp():
    spec = _spec([CoinStack(denom="cp", count=250), CoinStack(denom="gp", count=2)])
    shop.spend(spec, 3)
    assert _carried(spec) == {"cp": 50, "gp": 1}


def test_spend_insufficient_raises():
    spec = _spec([CoinStack(denom="gp", count=1)])
    with pytest.raises(shop.InsufficientFunds):
        shop.spend(spec, 5)


def test_spend_change_exception_pays_pp_returns_gp():
    spec = _spec([CoinStack(denom="pp", count=1)])
    shop.spend(spec, 1)
    assert _carried(spec) == {"gp": 4}


def test_spend_ignores_non_carried_coins():
    spec = _spec([
        CoinStack(denom="gp", count=1),
        CoinStack(denom="gp", count=99, location=StorageLocation(kind="stashed")),
    ])
    with pytest.raises(shop.InsufficientFunds):
        shop.spend(spec, 5)


def test_spend_exact_prefers_low_denomination():
    spec = _spec([CoinStack(denom="sp", count=50), CoinStack(denom="gp", count=5)])
    shop.spend(spec, 5)
    c = _carried(spec)
    # should spend sp first (500cp) not gp (500cp same)
    assert c.get("sp", 0) == 0
    assert c.get("gp", 0) == 5


# ── sell_instance tests ─────────────────────────────────────────────────────

def _full_spec(**kw):
    base = dict(name="H", abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10,
                "CON": 10, "CHA": 10}, race_id="human",
                classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
                alignment="neutral")
    base.update(kw)
    return CharacterSpec(**base)


def _two_maces_spec():
    ids = [uuid.uuid4().hex, uuid.uuid4().hex]
    spec = _full_spec(items=[
        ItemInstance(instance_id=ids[0], catalog_id="mace", count=1,
                     location=StorageLocation(kind="carried")),
        ItemInstance(instance_id=ids[1], catalog_id="mace", count=1,
                     location=StorageLocation(kind="carried")),
    ])
    return spec, ids


def test_sell_instance_removes_only_that_instance():
    spec, ids = _two_maces_spec()
    shop.sell_instance(spec, ids[0], "drop", _SHOP_DATA)
    remaining = [i.instance_id for i in spec.items]
    assert ids[0] not in remaining and ids[1] in remaining


def test_sell_instance_refund_credits_carried_gp():
    spec, ids = _two_maces_spec()
    before = sum(s.count for s in spec.coins
                 if s.denom == "gp" and s.location.kind == "carried")
    shop.sell_instance(spec, ids[0], "refund", _SHOP_DATA)
    after = sum(s.count for s in spec.coins
                if s.denom == "gp" and s.location.kind == "carried")
    assert after > before
