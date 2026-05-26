from aose.characters.storage import slugify, unique_character_id


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
