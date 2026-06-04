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


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------
from pathlib import Path
from fastapi.testclient import TestClient
from aose.characters import load_character, save_character
from aose.web.app import create_app

DATA_DIR = Path(__file__).parent.parent / "data"


def _make_client(tmp_path):
    characters_dir = tmp_path / "characters"
    drafts_dir = tmp_path / "drafts"
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir()
    app = create_app(
        data_dir=DATA_DIR, characters_dir=characters_dir,
        drafts_dir=drafts_dir, examples_dir=examples_dir,
        settings_path=tmp_path / "settings.json",
    )
    client = TestClient(app, follow_redirects=False)
    client._characters_dir = characters_dir
    return client


def test_coins_add_route(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec(), client._characters_dir)
    r = client.post("/character/c1/coins/add", data={"denom": "sp", "amount": "25"})
    assert r.status_code == 303
    assert load_character("c1", client._characters_dir).silver == 25


def test_coins_add_clamps_at_zero(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec(silver=10), client._characters_dir)
    client.post("/character/c1/coins/add", data={"denom": "sp", "amount": "-50"})
    assert load_character("c1", client._characters_dir).silver == 0


def test_coins_convert_route(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec(platinum=2), client._characters_dir)
    client.post("/character/c1/coins/convert",
                data={"from_denom": "pp", "to_denom": "gp", "count": "2"})
    s = load_character("c1", client._characters_dir)
    assert (s.platinum, s.gold) == (0, 10)


def test_coins_convert_bad_request(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec(gold=1), client._characters_dir)
    r = client.post("/character/c1/coins/convert",
                    data={"from_denom": "gp", "to_denom": "sp", "count": "99"})
    assert r.status_code == 400
