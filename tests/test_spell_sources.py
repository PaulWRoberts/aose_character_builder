from pathlib import Path

import pytest

from aose.data.loader import GameData
from aose.engine import spell_sources as ss

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return GameData.load(DATA_DIR)


def test_new_spell_source_validates_caster_type(data):
    src = ss.new_spell_source("scroll", "arcane",
                              ["magic_user_magic_missile", "magic_user_sleep"], data)
    assert src.kind == "scroll"
    assert src.caster_type == "arcane"
    assert [e.spell_id for e in src.entries] == ["magic_user_magic_missile", "magic_user_sleep"]
    assert len(src.instance_id) == 32  # uuid4 hex


def test_new_spell_source_spellbook_forces_arcane(data):
    src = ss.new_spell_source("spellbook", "divine", ["magic_user_sleep"], data)
    assert src.caster_type == "arcane"


def test_new_spell_source_rejects_off_type_spell(data):
    # faerie_fire is a divine spell; cannot go in an arcane document.
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane", ["faerie_fire"], data)


def test_new_spell_source_rejects_duplicates(data):
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane",
                            ["magic_user_sleep", "magic_user_sleep"], data)


def test_new_spell_source_rejects_unknown_spell(data):
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane", ["nope_not_a_spell"], data)


def test_new_spell_source_list_id_constraint(data):
    # list_id pins membership to one list (used by the spellbook UI).
    src = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data,
                              list_id="magic_user")
    assert src.entries[0].spell_id == "magic_user_sleep"
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("spellbook", "arcane", ["faerie_fire"], data,
                            list_id="magic_user")


def test_add_and_remove(data):
    sources = ss.add_spell_source([], "scroll", "arcane",
                                  ["magic_user_magic_missile"], data, name="A")
    assert len(sources) == 1
    iid = sources[0].instance_id
    sources = ss.remove_spell_source(sources, iid)
    assert sources == []
    with pytest.raises(ss.SpellSourceError):
        ss.remove_spell_source(sources, "missing")
