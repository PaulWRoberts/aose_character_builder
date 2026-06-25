from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spell_sources as ss
from aose.engine import spells as se
from aose.models import CharacterSpec, ClassEntry, RuleSet
from aose.sheet.view import spell_sources_view, spell_source_add_options

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _mu(sources):
    e = ClassEntry(class_id="magic_user", level=1, spellbook=["magic_user_read_magic"])
    e = se.assign_slot(e, DATA.classes["magic_user"], DATA, level=1,
                       spell_id="magic_user_read_magic")
    return CharacterSpec(
        name="M", abilities={"STR": 10, "INT": 13, "WIS": 10, "DEX": 10, "CON": 10, "CHA": 10},
        race_id="human", classes=[e], alignment="neutral", ruleset=RuleSet(),
        spell_sources=sources,
    )


def test_view_exposes_read_and_unlocked():
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], DATA)
    rows = spell_sources_view(_mu([scroll]), DATA)
    v = rows[0]
    assert v.unlocked is False
    assert v.can_read is True          # Read Magic memorized
    assert v.entries[0].can_cast is False   # not deciphered yet


def test_spellbook_can_be_deciphered_in_view():
    """An arcane spell book (another's grimoire) is also unreadable until
    deciphered with Read Magic — the view offers the Decipher action."""
    book = ss.new_spell_source("spellbook", "arcane", ["magic_user_sleep"], DATA)
    rows = spell_sources_view(_mu([book]), DATA)
    assert rows[0].can_read is True


def test_scroll_copy_requires_decipher_in_view():
    """Bug 4: copying from an arcane scroll appears only once the scroll is
    deciphered (Advanced rule, spell on the PC's class list)."""
    rs = RuleSet(advanced_spell_books=True)
    scroll = ss.new_spell_source("scroll", "arcane", ["magic_user_sleep"], DATA)
    spec = _mu([scroll])
    spec.ruleset = rs
    assert spell_sources_view(spec, DATA)[0].entries[0].can_copy is False
    scroll.unlocked = True
    assert spell_sources_view(spec, DATA)[0].entries[0].can_copy is True


def test_add_options_lists_languages():
    opts = spell_source_add_options(DATA, RuleSet())
    ids = [l.id for l in opts.languages]
    assert "common" in ids


def test_add_options_hides_cantrips_when_rule_off():
    """Bug 1: level-0 cantrips are not scribe options unless the Cantrips rule
    is on; they appear once it is."""
    off = spell_source_add_options(DATA, RuleSet(cantrips=False))
    on = spell_source_add_options(DATA, RuleSet(cantrips=True))
    off_ids = {e.id for e in off.arcane_spells}
    on_ids = {e.id for e in on.arcane_spells}
    assert not any(i.startswith("cantrip_") for i in off_ids)
    assert any(i.startswith("cantrip_") for i in on_ids)


def test_add_options_hides_disabled_content():
    """Bug 1: spells whose only list belongs to a disabled source are not
    offered (illusionist lives in ose_advanced_fantasy)."""
    enabled = spell_source_add_options(DATA, RuleSet())
    disabled = spell_source_add_options(
        DATA, RuleSet(disabled_content=["ose_advanced_fantasy:classes"]))
    assert any(g.list_id == "illusionist" for g in enabled.arcane_lists)
    assert not any(g.list_id == "illusionist" for g in disabled.arcane_lists)
    assert "illusionist_light" not in {e.id for e in disabled.arcane_spells}


def test_add_options_advanced_flag_tracks_ruleset():
    """Bug 3: the spellbook option is only useful (castable/copyable) under the
    Advanced Spell Book rule."""
    assert spell_source_add_options(DATA, RuleSet(advanced_spell_books=True)).advanced
    assert not spell_source_add_options(
        DATA, RuleSet(advanced_spell_books=False)).advanced
