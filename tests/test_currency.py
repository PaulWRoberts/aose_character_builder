import pytest
from aose.engine import currency
from aose.engine.currency import CurrencyError
from aose.models import CharacterSpec, CoinStack
from aose.models.storage import StorageLocation


def _spec(coins):
    return CharacterSpec.model_validate(dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10,
                             "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral", coins=coins,
    ))


def test_total_value_gp_sums_all_locations():
    spec = _spec([
        CoinStack(denom="gp", count=5),
        CoinStack(denom="sp", count=10, location=StorageLocation(kind="stashed")),
    ])
    assert currency.total_value_gp(spec) == 6   # 5gp + 100cp = 6gp


def test_coin_count_carried_only_is_the_encumbrance_weight():
    spec = _spec([
        CoinStack(denom="gp", count=5),                                            # carried
        CoinStack(denom="gp", count=99, location=StorageLocation(kind="stashed")), # off-person
    ])
    assert currency.coin_count(spec, carried_only=True) == 5
    assert currency.coin_count(spec) == 104


def test_carried_coins_returns_only_carried_kind():
    spec = _spec([
        CoinStack(denom="gp", count=5),
        CoinStack(denom="cp", count=7, location=StorageLocation(kind="container", id="c1")),
    ])
    carried = currency.carried_coins(spec)
    assert {c.denom for c in carried} == {"gp"}


def test_convert_amount_whole_coin_enforced():
    assert currency.convert_amount("gp", "sp", 2) == 20      # 2gp -> 20sp
    with pytest.raises(CurrencyError):
        currency.convert_amount("cp", "sp", 5)               # 5cp != whole sp


def test_convert_amount_same_denom_raises():
    with pytest.raises(CurrencyError):
        currency.convert_amount("gp", "gp", 1)


def test_convert_amount_zero_count_raises():
    with pytest.raises(CurrencyError):
        currency.convert_amount("gp", "sp", 0)


def test_legacy_coin_fields_coerce_on_spec_construction():
    # Ensure old saves still load: kwargs like gold=10 coerce via the model validator
    spec = CharacterSpec.model_validate(dict(
        name="T", abilities={"STR": 10, "DEX": 10, "CON": 10,
                             "INT": 10, "WIS": 10, "CHA": 10},
        race_id="human", classes=[{"class_id": "fighter", "level": 1}],
        alignment="neutral",
        gold=5, silver=30,
    ))
    by_denom = {s.denom: s for s in spec.coins}
    assert by_denom["gp"].count == 5
    assert by_denom["sp"].count == 30
    assert currency.total_value_gp(spec) == 8  # 5gp + 30sp(3gp) = 8gp


# ---------------------------------------------------------------------------
# Route tests (updated for new located-coins API)
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


def _spec_with_coins(coins=None):
    return CharacterSpec.model_validate(dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 1, "hp_rolls": [6]}],
        alignment="law",
        coins=coins or [],
    ))


def test_coins_add_route(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec_with_coins(), client._characters_dir)
    r = client.post("/character/c1/coins/add",
                    data={"denom": "sp", "loc_kind": "carried", "loc_id": "", "count": "25"})
    assert r.status_code == 303
    loaded = load_character("c1", client._characters_dir)
    by_denom = {s.denom: s.count for s in loaded.coins}
    assert by_denom.get("sp", 0) == 25


def test_coins_convert_route(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec_with_coins([CoinStack(denom="pp", count=2)]),
                   client._characters_dir)
    client.post("/character/c1/coins/convert",
                data={"loc_kind": "carried", "loc_id": "",
                      "frm": "pp", "to": "gp", "count": "2"})
    s = load_character("c1", client._characters_dir)
    by_denom = {c.denom: c.count for c in s.coins}
    assert by_denom.get("pp", 0) == 0 and by_denom.get("gp", 0) == 10


def test_coins_convert_bad_request(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec_with_coins([CoinStack(denom="gp", count=1)]),
                   client._characters_dir)
    r = client.post("/character/c1/coins/convert",
                    data={"loc_kind": "carried", "loc_id": "",
                          "frm": "gp", "to": "sp", "count": "99"})
    assert r.status_code == 400


def test_carrying_treasure_toggle(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec_with_coins(), client._characters_dir)
    client.post("/character/c1/carrying-treasure", data={"value": "true"})
    assert load_character("c1", client._characters_dir).carrying_treasure is True
    client.post("/character/c1/carrying-treasure", data={"value": "false"})
    assert load_character("c1", client._characters_dir).carrying_treasure is False


def test_sheet_page_renders_coin_ui(tmp_path):
    client = _make_client(tmp_path)
    save_character("c1", _spec_with_coins([CoinStack(denom="gp", count=5)]),
                   client._characters_dir)
    html = client.get("/character/c1").text
    assert "coins/add" in html or "coin" in html.lower()
