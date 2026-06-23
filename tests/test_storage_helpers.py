from pathlib import Path

from aose.characters.storage import slugify, unique_character_id
from aose.data.loader import GameData
from aose.engine import storage
from aose.models import CharacterSpec, ClassEntry, CoinStack, GemStack, ContainerInstance
from aose.models.storage import StorageLocation

DATA = GameData.load(Path("data"))


def _spec(**kw):
    base = dict(
        name="Loader",
        abilities={"STR": 10, "INT": 10, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[8])],
        alignment="neutral",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_slugify_basic():
    assert slugify("Thorin Oakenshield") == "thorin-oakenshield"


def test_slugify_strips_punctuation():
    assert slugify("Bilbo, the Brave!") == "bilbo-the-brave"


def test_slugify_collapses_separators():
    assert slugify("foo___bar  baz") == "foo-bar-baz"


def test_slugify_empty_returns_fallback():
    assert slugify("!!!") == "character"
    assert slugify("") == "character"


def test_unique_id_no_collision(tmp_path):
    assert unique_character_id("thorin", tmp_path) == "thorin"


def test_unique_id_appends_counter(tmp_path):
    (tmp_path / "thorin.json").write_text("{}")
    assert unique_character_id("thorin", tmp_path) == "thorin-2"


def test_unique_id_skips_existing_counters(tmp_path):
    (tmp_path / "thorin.json").write_text("{}")
    (tmp_path / "thorin-2.json").write_text("{}")
    (tmp_path / "thorin-3.json").write_text("{}")
    assert unique_character_id("thorin", tmp_path) == "thorin-4"


# ── location_load_cn ─────────────────────────────────────────────────────────

def test_location_load_cn_sums_loose_and_coins_at_a_container():
    here = StorageLocation(kind="container", id="c1")
    sword_cn = DATA.items["sword"].weight_cn
    spec = _spec(
        containers=[ContainerInstance(instance_id="c1", catalog_id="backpack",
                                      location=StorageLocation(kind="carried"),
                                      contents=["sword"])],
        coins=[CoinStack(denom="gp", count=7, location=here)],
        gems=[GemStack(instance_id="g1", value=50, count=3, label="", location=here)],
    )
    # sword weight + 7 coins (1cn) + 3 gems (1cn)
    assert storage.location_load_cn(spec, here, DATA) == sword_cn + 7 + 3


def test_location_load_cn_is_zero_for_empty_location():
    loc = StorageLocation(kind="animal", id="zzz")
    assert storage.location_load_cn(_spec(), loc, DATA) == 0
