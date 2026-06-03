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


# ── cast + caster-type predicates ────────────────────────────────────────────

from aose.models import CharacterSpec, ClassEntry, RuleSet


def _mu_spec(advanced=False, sources=None):
    return CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral", ruleset=RuleSet(advanced_spell_books=advanced),
        spell_sources=sources or [],
    )


def test_cast_from_scroll_consumes_one(data):
    sources = ss.add_spell_source([], "scroll", "arcane",
                                  ["magic_user_magic_missile", "magic_user_sleep"], data)
    iid = sources[0].instance_id
    sources = ss.cast_from_scroll(sources, iid, "magic_user_magic_missile")
    assert len(sources) == 1
    assert [e.spell_id for e in sources[0].entries] == ["magic_user_sleep"]


def test_cast_last_spell_removes_scroll(data):
    sources = ss.add_spell_source([], "scroll", "arcane", ["magic_user_sleep"], data)
    iid = sources[0].instance_id
    sources = ss.cast_from_scroll(sources, iid, "magic_user_sleep")
    assert sources == []


def test_cast_rejects_non_scroll_and_missing(data):
    sources = ss.add_spell_source([], "spellbook", "arcane", ["magic_user_sleep"], data)
    iid = sources[0].instance_id
    with pytest.raises(ss.SpellSourceError):
        ss.cast_from_scroll(sources, iid, "magic_user_sleep")          # not a scroll
    scroll = ss.add_spell_source([], "scroll", "arcane", ["magic_user_sleep"], data)
    with pytest.raises(ss.SpellSourceError):
        ss.cast_from_scroll(scroll, scroll[0].instance_id, "magic_user_magic_missile")  # absent


def test_can_cast_scroll_matches_caster_type(data):
    arcane_scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    divine_scroll = ss.new_spell_source("scroll", "divine", ["faerie_fire"], data)
    spec = _mu_spec()
    assert ss.can_cast_scroll(arcane_scroll, spec, data) is True
    assert ss.can_cast_scroll(divine_scroll, spec, data) is False
    # spell books are never castable
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    assert ss.can_cast_scroll(book, spec, data) is False


# ── copy_spell ────────────────────────────────────────────────────────────────

class _FixedRng:
    """Stand-in for random.Random whose 1d100 always returns ``value``."""
    def __init__(self, value):
        self.value = value
    def randint(self, a, b):
        return self.value


def test_copy_success_adds_to_spellbook(data):
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_magic_missile"], data)
    entry = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    new_entry, new_sources, ok = ss.copy_spell(
        entry, cls, data, RuleSet(advanced_spell_books=True), int_score=13,
        sources=[src], instance_id=src.instance_id,
        spell_id="magic_user_magic_missile", rng=_FixedRng(1),   # 1 <= 70 -> success
    )
    assert ok is True
    assert new_entry.spellbook == ["magic_user_magic_missile"]
    # source entry is not failed, source not consumed
    assert new_sources[0].entries[0].copy_failed is False


def test_copy_failure_burns_only_this_source(data):
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_magic_missile"], data)
    entry = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    new_entry, new_sources, ok = ss.copy_spell(
        entry, cls, data, RuleSet(advanced_spell_books=True), int_score=13,
        sources=[src], instance_id=src.instance_id,
        spell_id="magic_user_magic_missile", rng=_FixedRng(100),  # 100 > 70 -> fail
    )
    assert ok is False
    assert new_entry.spellbook == []
    assert new_sources[0].entries[0].copy_failed is True
    # retry from the SAME source is now rejected
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(new_entry, cls, data, RuleSet(advanced_spell_books=True),
                      int_score=13, sources=new_sources, instance_id=src.instance_id,
                      spell_id="magic_user_magic_missile", rng=_FixedRng(1))


def test_copy_same_spell_from_a_second_source(data):
    failed = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    failed.entries[0].copy_failed = True
    other = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    entry = ClassEntry(class_id="magic_user", level=1, spellbook=[])
    cls = data.classes["magic_user"]
    new_entry, _src, ok = ss.copy_spell(
        entry, cls, data, RuleSet(advanced_spell_books=True), int_score=18,
        sources=[failed, other], instance_id=other.instance_id,
        spell_id="magic_user_sleep", rng=_FixedRng(1),
    )
    assert ok is True
    assert new_entry.spellbook == ["magic_user_sleep"]


def test_copy_requires_advanced_rule(data):
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    entry = ClassEntry(class_id="magic_user", level=1)
    cls = data.classes["magic_user"]
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(entry, cls, data, RuleSet(advanced_spell_books=False),
                      int_score=13, sources=[src], instance_id=src.instance_id,
                      spell_id="magic_user_sleep", rng=_FixedRng(1))


def test_copy_rejects_divine_source_and_known_and_uncastable(data):
    cls = data.classes["magic_user"]
    rs = RuleSet(advanced_spell_books=True)
    # divine source
    div = ss.new_spell_source("scroll", "divine", ["faerie_fire"], data)
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(ClassEntry(class_id="magic_user", level=1), cls, data, rs,
                      13, [div], div.instance_id, "faerie_fire", rng=_FixedRng(1))
    # already known
    src = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    known = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_sleep"])
    with pytest.raises(ss.SpellSourceError):
        ss.copy_spell(known, cls, data, rs, 13, [src], src.instance_id,
                      "magic_user_sleep", rng=_FixedRng(1))
