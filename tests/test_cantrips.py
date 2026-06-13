from pathlib import Path

from aose.models import RuleSet, ClassEntry


def test_cantrip_flags_default_off():
    rs = RuleSet()
    assert rs.cantrips is False
    assert rs.read_magic_cantrip is False


def test_cantrip_flags_settable():
    rs = RuleSet(cantrips=True, read_magic_cantrip=True)
    assert rs.cantrips is True
    assert rs.read_magic_cantrip is True


DATA_DIR = Path(__file__).resolve().parents[1] / "data"

CANTRIP_IDS = {
    "cantrip_book_leaf", "cantrip_cleaning_brush", "cantrip_coloured_flame",
    "cantrip_floating_trinket", "cantrip_magic_quill", "cantrip_open_close_portal",
    "cantrip_rune", "cantrip_sense_magic", "cantrip_smoke_rings", "cantrip_spark",
    "cantrip_vanish", "cantrip_wizard_flame",
}


def test_cantrip_spells_load_at_level_zero():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    for sid in CANTRIP_IDS:
        spell = data.spells[sid]
        assert spell.level == 0
        assert spell.source == "carcass_crawler_5"
        assert "magic_user" in spell.spell_lists
        assert "illusionist" in spell.spell_lists


def test_read_magic_cantrip_loads():
    from aose.data.loader import GameData
    data = GameData.load(DATA_DIR)
    rm = data.spells["read_magic_cantrip"]
    assert rm.level == 0
    assert rm.source == "carcass_crawler_5"
    assert set(rm.spell_lists) == {"magic_user", "illusionist"}


def test_cantrip_count_bands():
    from aose.engine import spells
    assert spells.cantrip_count(1) == 2
    assert spells.cantrip_count(2) == 2
    assert spells.cantrip_count(3) == 3
    assert spells.cantrip_count(4) == 3
    assert spells.cantrip_count(5) == 4
    assert spells.cantrip_count(14) == 4


def test_is_dedicated_arcane():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    assert spells.is_dedicated_arcane(data.classes["magic_user"], data) is True
    assert spells.is_dedicated_arcane(data.classes["illusionist"], data) is True
    # divine caster
    assert spells.is_dedicated_arcane(data.classes["cleric"], data) is False
    # non-caster
    assert spells.is_dedicated_arcane(data.classes["fighter"], data) is False
    # scroll-only arcane (no slots at L1)
    assert spells.is_dedicated_arcane(data.classes["mage"], data) is False
    # arcane but first casts at L2
    assert spells.is_dedicated_arcane(data.classes["arcane_bard"], data) is False


def test_level_zero_injected_only_when_rule_and_dedicated():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    e1 = ClassEntry(class_id="magic_user", level=1)
    rs_on = RuleSet(cantrips=True)
    rs_off = RuleSet()

    # Off / no args -> unchanged base behaviour
    assert spells.memorizable_slots(e1, cls) == {1: 1}
    assert spells.accessible_levels(e1, cls) == {1}
    assert spells.memorizable_slots(e1, cls, data, rs_off) == {1: 1}

    # On -> level-0 cap = 2 at level 1
    assert spells.memorizable_slots(e1, cls, data, rs_on) == {0: 2, 1: 1}
    assert 0 in spells.accessible_levels(e1, cls, data, rs_on)

    # Cantrip cap scales with level
    e5 = ClassEntry(class_id="magic_user", level=5)
    assert spells.memorizable_slots(e5, cls, data, rs_on)[0] == 4


def test_level_zero_not_injected_for_non_dedicated():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    rs_on = RuleSet(cantrips=True)
    e = ClassEntry(class_id="cleric", level=1)
    cls = data.classes["cleric"]
    assert 0 not in spells.memorizable_slots(e, cls, data, rs_on)


def test_beginning_cantrip_count():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    mu = ClassEntry(class_id="magic_user", level=1)
    assert spells.beginning_cantrip_count(mu, data.classes["magic_user"], data,
                                          RuleSet(cantrips=True)) == 2
    assert spells.beginning_cantrip_count(mu, data.classes["magic_user"], data,
                                          RuleSet()) == 0
    cl = ClassEntry(class_id="cleric", level=1)
    assert spells.beginning_cantrip_count(cl, data.classes["cleric"], data,
                                          RuleSet(cantrips=True)) == 0


def test_read_magic_demotion_hides_l1_and_grants_cantrip():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, read_magic_cantrip=True)
    e = ClassEntry(class_id="magic_user", level=1,
                   spellbook=["magic_user_read_magic", "magic_user_magic_missile"])
    known = {s.id for s in spells.known_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" not in known
    assert "read_magic_cantrip" in known          # auto-granted
    assert "magic_user_magic_missile" in known

    learnable = {s.id for s in spells.learnable_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" not in learnable
    assert "read_magic_cantrip" not in learnable   # already auto-known


def test_read_magic_not_demoted_when_rule_off():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True)  # read_magic_cantrip OFF
    e = ClassEntry(class_id="magic_user", level=1,
                   spellbook=["magic_user_read_magic"])
    known = {s.id for s in spells.known_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" in known
    assert "read_magic_cantrip" not in known
    learnable = {s.id for s in spells.learnable_spells(e, cls, data, rs)}
    assert "magic_user_read_magic" not in learnable  # already in book
    assert "read_magic_cantrip" in learnable          # a learnable cantrip


def test_learn_cantrips_standard_obeys_cap():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True)  # standard spell books
    e = ClassEntry(class_id="magic_user", level=1)
    e = spells.learn(e, cls, data, rs, "cantrip_spark")
    e = spells.learn(e, cls, data, rs, "cantrip_vanish")
    assert e.spellbook == ["cantrip_spark", "cantrip_vanish"]
    # Third cantrip exceeds the level-1 cap of 2 -> rejected
    try:
        spells.learn(e, cls, data, rs, "cantrip_rune")
        assert False, "expected SpellError for exceeding cantrip cap"
    except spells.SpellError:
        pass


def test_learn_cantrips_advanced_is_copy_only():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, advanced_spell_books=True)
    e = ClassEntry(class_id="magic_user", level=1)
    try:
        spells.learn(e, cls, data, rs, "cantrip_spark")
        assert False, "expected SpellError: cantrips are copy-only under advanced"
    except spells.SpellError:
        pass


def test_assign_cantrip_slot_and_memorise_cap():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True)
    e = ClassEntry(class_id="magic_user", level=1,
                   spellbook=["cantrip_spark", "cantrip_vanish"])
    e = spells.assign_slot(e, cls, data, 0, "cantrip_spark", ruleset=rs)
    e = spells.assign_slot(e, cls, data, 0, "cantrip_vanish", ruleset=rs)
    assert len([s for s in e.slots if s.level == 0]) == 2
    # No third level-0 slot (cap 2)
    try:
        spells.assign_slot(e, cls, data, 0, "cantrip_spark", ruleset=rs)
        assert False, "expected SpellError: level-0 cap reached"
    except spells.SpellError:
        pass


def test_assign_auto_granted_read_magic_cantrip_is_memorisable():
    from aose.data.loader import GameData
    from aose.engine import spells
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, read_magic_cantrip=True)
    e = ClassEntry(class_id="magic_user", level=1)  # not in spellbook, auto-known
    e = spells.assign_slot(e, cls, data, 0, "read_magic_cantrip", ruleset=rs)
    assert any(s.spell_id == "read_magic_cantrip" for s in e.slots)


def test_cantrip_copyable_from_source_under_advanced():
    import random
    from aose.data.loader import GameData
    from aose.engine import spell_sources as ss
    data = GameData.load(DATA_DIR)
    cls = data.classes["magic_user"]
    rs = RuleSet(cantrips=True, advanced_spell_books=True)
    e = ClassEntry(class_id="magic_user", level=1)
    sources = ss.add_spell_source([], "spellbook", "arcane", ["cantrip_spark"], data)
    inst = sources[0].instance_id
    copyable = ss.copyable_spell_ids(sources[0], e, cls, data, rs)
    assert "cantrip_spark" in copyable
    # Force a success (INT 18 + roll 1) and confirm it lands in the spellbook.
    new_e, _src, ok = ss.copy_spell(e, cls, data, rs, 18, sources, inst,
                                    "cantrip_spark", rng=random.Random(0))
    assert ok is True
    assert "cantrip_spark" in new_e.spellbook


def test_optional_rule_labels_include_cantrips():
    from aose.sheet.view import OPTIONAL_RULE_LABELS
    assert "cantrips" in OPTIONAL_RULE_LABELS
    assert "read_magic_cantrip" in OPTIONAL_RULE_LABELS


def test_spells_view_shows_cantrip_group():
    from aose.data.loader import GameData
    from aose.sheet.view import spells_view
    from aose.models import CharacterSpec, ClassEntry, RuleSet
    data = GameData.load(DATA_DIR)
    spec = CharacterSpec(
        name="Zed", abilities={"STR": 9, "DEX": 9, "CON": 9, "INT": 12, "WIS": 9, "CHA": 9},
        race_id="human", alignment="neutral",
        classes=[ClassEntry(class_id="magic_user", level=1,
                            spellbook=["cantrip_spark"])],
        ruleset=RuleSet(cantrips=True),
    )
    block = next(b for b in spells_view(spec, data) if b.class_id == "magic_user")
    levels = {g.level for g in block.slot_groups}
    assert 0 in levels
    g0 = next(g for g in block.slot_groups if g.level == 0)
    assert g0.cap == 2
    assert "cantrip_spark" in {s.id for s in block.known}
