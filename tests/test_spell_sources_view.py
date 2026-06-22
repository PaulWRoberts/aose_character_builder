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


def test_add_options_lists_languages():
    opts = spell_source_add_options(DATA)
    ids = [l.id for l in opts.languages]
    assert "common" in ids
