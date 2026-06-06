from pathlib import Path

from aose.data.loader import GameData
from aose.engine import spells as se
from aose.engine.detail import DetailCard
from aose.models import CharacterSpec, ClassEntry, SpellSource, SpellSourceEntry
from aose.sheet.view import spells_view, spell_sources_view

DATA = GameData.load(Path(__file__).parent.parent / "data")

MM = "magic_user_magic_missile"


def _caster():
    e = ClassEntry(class_id="magic_user", level=3, hp_rolls=[4, 3, 2],
                   spellbook=[MM])
    spec = CharacterSpec(
        name="M",
        abilities={"STR": 9, "INT": 16, "WIS": 9, "DEX": 12, "CON": 10, "CHA": 9},
        race_id="human", classes=[e], alignment="neutral",
    )
    cls = DATA.classes["magic_user"]
    spec.classes = [se.assign_slot(e, cls, DATA, level=1, spell_id=MM)]
    return spec


def test_known_spell_entry_has_detail():
    block = spells_view(_caster(), DATA)[0]
    assert block.known
    assert isinstance(block.known[0].detail, DetailCard)
    assert any(s.label == "Range" for s in block.known[0].detail.stats)


def test_memorised_slot_has_detail():
    block = spells_view(_caster(), DATA)[0]
    slot = next(g for g in block.slot_groups if g.slots).slots[0]
    assert isinstance(slot.detail, DetailCard)


def test_spell_source_entry_has_detail():
    spec = _caster()
    spec.spell_sources = [SpellSource(
        instance_id="src1", kind="scroll", caster_type="arcane",
        entries=[SpellSourceEntry(spell_id=MM)],
    )]
    src = spell_sources_view(spec, DATA)[0]
    assert isinstance(src.entries[0].detail, DetailCard)
    assert src.entries[0].detail.description == DATA.spells[MM].description
