from aose.models import CharacterSpec, ClassEntry


def _spec(**kw):
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_coin_fields_default_zero():
    s = _spec()
    assert (s.platinum, s.gold, s.electrum, s.silver, s.copper) == (0, 0, 0, 0, 0)


def test_carrying_treasure_defaults_false():
    assert _spec().carrying_treasure is False


import pytest
from aose.engine import currency
from aose.engine.currency import CurrencyError


def test_total_value_gp_sums_denominations():
    s = _spec(platinum=1, gold=2, electrum=2, silver=10, copper=100)
    # 1pp=5gp, 2ep=1gp, 10sp=1gp, 100cp=1gp -> 5+2+1+1+1 = 10 gp
    assert currency.total_value_gp(s) == 10


def test_coin_count_is_total_coins():
    s = _spec(platinum=1, gold=2, electrum=2, silver=10, copper=100)
    assert currency.coin_count(s) == 1 + 2 + 2 + 10 + 100


def test_convert_pp_to_gp_exact():
    s = _spec(platinum=3, gold=1)
    changes = currency.convert(s, "pp", "gp", 2)        # 2pp -> 10gp
    assert changes == {"platinum": 1, "gold": 11}


def test_convert_gp_to_sp_multiplies():
    s = _spec(gold=5)
    changes = currency.convert(s, "gp", "sp", 2)        # 2gp -> 20sp
    assert changes == {"gold": 3, "silver": 20}


def test_convert_rejects_non_whole_result():
    s = _spec(copper=50)
    with pytest.raises(CurrencyError):
        currency.convert(s, "cp", "gp", 50)             # 50cp != whole gp


def test_convert_rejects_insufficient_coins():
    s = _spec(gold=1)
    with pytest.raises(CurrencyError):
        currency.convert(s, "gp", "sp", 2)


def test_convert_rejects_same_denom_and_bad_count():
    s = _spec(gold=5)
    with pytest.raises(CurrencyError):
        currency.convert(s, "gp", "gp", 1)
    with pytest.raises(CurrencyError):
        currency.convert(s, "gp", "sp", 0)
