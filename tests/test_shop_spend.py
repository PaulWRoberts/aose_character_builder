import pytest
from aose.engine import shop
from aose.models import CharacterSpec, CoinStack
from aose.models.storage import StorageLocation


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
