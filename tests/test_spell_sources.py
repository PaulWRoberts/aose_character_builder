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
    # Spell books still reject duplicates; scrolls now allow them (see
    # test_scroll_allows_duplicate_spells).
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("spellbook", "arcane",
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


_EIGHT_MU = [
    "magic_user_charm_person", "magic_user_detect_magic", "magic_user_floating_disc",
    "magic_user_hold_portal", "magic_user_light", "magic_user_magic_missile",
    "magic_user_protection_from_evil", "magic_user_read_languages",
]


def test_scroll_capped_at_seven_spells(data):
    # The AOSE Magic Scrolls table tops out at 7 spells per scroll.
    src = ss.new_spell_source("scroll", "arcane", _EIGHT_MU[:7], data)
    assert len(src.entries) == 7
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "arcane", _EIGHT_MU, data)  # 8 -> too many


def test_spellbook_not_capped_at_seven(data):
    # Spell books hold any number of spells; only scrolls are capped.
    src = ss.new_spell_source("spellbook", "arcane", _EIGHT_MU, data)
    assert len(src.entries) == 8


def test_arcane_scroll_accepts_spells_from_any_arcane_list(data):
    # A scroll spans a whole magic type, not one list — no list_id gating.
    src = ss.new_spell_source("scroll", "arcane",
                              ["magic_user_sleep", "illusionist_light"], data)
    assert len(src.entries) == 2


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

from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry, RuleSet


def _mu_spec(advanced=False, sources=None):
    return CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="magic_user", level=1)],
        alignment="neutral", ruleset=RuleSet(advanced_spell_books=advanced),
        spell_sources=sources or [],
    )


def _cleric_spec(sources=None, languages=None):
    return CharacterSpec(
        name="Cl", abilities={"STR": 10, "INT": 10, "WIS": 13, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[ClassEntry(class_id="cleric", level=1)],
        alignment="neutral", ruleset=RuleSet(),
        languages=list(languages or []),
        spell_sources=sources or [],
    )


def test_arcane_scroll_blocked_until_unlocked(data):
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = _mu_spec()
    assert ss.scroll_cast_block_reason(scroll, spec, data) == "needs Read Magic"
    assert ss.can_cast_scroll(scroll, spec, data) is False
    scroll.unlocked = True
    assert ss.scroll_cast_block_reason(scroll, spec, data) is None
    assert ss.can_cast_scroll(scroll, spec, data) is True


def test_divine_scroll_gated_by_language(data):
    common = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data,
                                 language="Common")
    exotic = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data,
                                 language="dragon")
    spec = _cleric_spec()  # knows Common (native), not Dragon
    assert ss.can_cast_scroll(common, spec, data) is True
    assert ss.scroll_cast_block_reason(exotic, spec, data) == "can't read dragon"
    spec_dragon = _cleric_spec(languages=["dragon"])
    assert ss.can_cast_scroll(exotic, spec_dragon, data) is True


def test_wrong_caster_type_blocked(data):
    divine_scroll = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data)
    assert ss.scroll_cast_block_reason(divine_scroll, _mu_spec(), data) == "not a divine caster"
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    assert ss.scroll_cast_block_reason(book, _mu_spec(), data) == "not a scroll"


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
    arcane_scroll.unlocked = True   # deciphered, so type-match is the question
    divine_scroll = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data)
    spec = _mu_spec()
    assert ss.can_cast_scroll(arcane_scroll, spec, data) is True
    assert ss.can_cast_scroll(divine_scroll, spec, data) is False
    # spell books are never castable
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], data)
    assert ss.can_cast_scroll(book, spec, data) is False


# ── read_scroll (decipher with Read Magic) ───────────────────────────────────

def _mu_with_read_magic_memorized(data):
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_read_magic"])
    cls = data.classes["magic_user"]
    e = se.assign_slot(e, cls, data, level=1, spell_id="magic_user_read_magic")
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = CharacterSpec(
        name="Mu", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[e], alignment="neutral", ruleset=RuleSet(),
        spell_sources=[scroll],
    )
    return spec, scroll.instance_id


def test_read_scroll_burns_slot_and_unlocks(data):
    spec, iid = _mu_with_read_magic_memorized(data)
    assert ss.ready_read_magic_slot(spec, data) == (0, 0)
    classes, sources = ss.read_scroll(spec, data, iid)
    assert classes[0].slots[0].spent is True          # the Read Magic cast is burned
    assert sources[0].unlocked is True


def test_read_scroll_requires_memorized_read_magic(data):
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], data)
    spec = _mu_spec(sources=[scroll])                  # no Read Magic memorized
    assert ss.ready_read_magic_slot(spec, data) is None
    with pytest.raises(ss.SpellSourceError):
        ss.read_scroll(spec, data, scroll.instance_id)


def test_read_scroll_rejects_divine_and_already_unlocked(data):
    divine = ss.new_spell_source("scroll", "divine", ["cleric_cure_light_wounds"], data)
    spec, iid = _mu_with_read_magic_memorized(data)
    spec.spell_sources = [*spec.spell_sources, divine]
    with pytest.raises(ss.SpellSourceError):
        ss.read_scroll(spec, data, divine.instance_id)         # divine needs no reading
    classes, sources = ss.read_scroll(spec, data, iid)
    spec.classes, spec.spell_sources = classes, sources
    with pytest.raises(ss.SpellSourceError):
        ss.read_scroll(spec, data, iid)                        # already unlocked


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


def test_scroll_allows_duplicate_spells(data):
    src = ss.new_spell_source("scroll", "divine",
                              ["cleric_cure_light_wounds"] * 3, data, language="Common")
    assert [e.spell_id for e in src.entries] == ["cleric_cure_light_wounds"] * 3
    assert src.language == "Common"


def test_spellbook_still_rejects_duplicates(data):
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("spellbook", "arcane",
                            ["magic_user_sleep", "magic_user_sleep"], data)


def test_scroll_cap_counts_duplicates(data):
    # 8 charges (even all-same) still exceeds the 7 cap.
    with pytest.raises(ss.SpellSourceError):
        ss.new_spell_source("scroll", "divine",
                            ["cleric_cure_light_wounds"] * 8, data)


def test_spell_source_new_fields_default(data):
    src = ss.new_spell_source("scroll", "divine", ["faerie_fire"], data)
    assert src.language == "Common"
    assert src.unlocked is False


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
