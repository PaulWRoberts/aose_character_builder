from pathlib import Path

from aose.data.loader import GameData
from aose.engine import saves

_DATA_DIR = Path(__file__).parent.parent / "data"
DATA = GameData.load(_DATA_DIR)


def _druid(level=1):
    from aose.models import CharacterSpec, ClassEntry
    return CharacterSpec(
        name="D", classes=[ClassEntry(class_id="druid", level=level)],
        abilities={"STR": 9, "INT": 9, "WIS": 13, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human", alignment="neutral",
    )


def test_druid_energy_resistance_groups_fire_and_lightning():
    result = saves.situational_save_bonuses(_druid(), DATA)
    energy = [b for b in result if b.source == "Energy Resistance"]
    assert len(energy) == 1
    assert energy[0].bonus == 2
    assert energy[0].things == ["fire", "lightning"]


def test_svirfneblin_illusion_resistance():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="S", classes=[ClassEntry(class_id="fighter", level=1)],
        race_id="svirfneblin",
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
        alignment="law",
    )
    result = saves.situational_save_bonuses(spec, DATA)
    illusion = [b for b in result if b.source == "Illusion Resistance"]
    assert len(illusion) == 1
    assert illusion[0].bonus == 2
    assert illusion[0].things == ["illusions"]


def test_kineticist_mental_defence():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="K", classes=[ClassEntry(class_id="kineticist", level=1)],
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human", alignment="neutral",
    )
    result = saves.situational_save_bonuses(spec, DATA)
    mental = [b for b in result if b.source == "Mental Defence"]
    assert len(mental) == 1
    assert mental[0].bonus == 2
    assert mental[0].things == ["mental powers"]


def test_knight_strength_of_will_at_level3():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="K", classes=[ClassEntry(class_id="knight", level=3)],
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human", alignment="law",
    )
    result = saves.situational_save_bonuses(spec, DATA)
    will = [b for b in result if b.source == "Strength of Will"]
    will4 = [b for b in will if b.bonus == 4]
    will2 = [b for b in will if b.bonus == 2]
    assert len(will4) == 1
    assert will4[0].things == ["charm", "hold"]
    assert len(will2) == 1
    assert will2[0].things == ["illusions"]


def test_knight_strength_of_will_not_at_level1():
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="K", classes=[ClassEntry(class_id="knight", level=1)],
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human", alignment="law",
    )
    result = saves.situational_save_bonuses(spec, DATA)
    will = [b for b in result if b.source == "Strength of Will"]
    assert will == []  # gained_at_level 3


def test_situational_bonus_never_changes_a_headline():
    # WIS 9 → zero WIS modifier, isolating the check to save:vs:* leakage only.
    from aose.models import CharacterSpec, ClassEntry
    spec = CharacterSpec(
        name="D", classes=[ClassEntry(class_id="druid", level=1)],
        abilities={"STR": 9, "INT": 9, "WIS": 9, "DEX": 9, "CON": 9, "CHA": 9},
        race_id="human", alignment="neutral",
    )
    detail = saves.saving_throws_detail(spec, DATA)
    cls = DATA.classes["druid"]
    prog = cls.progression[1].saves
    for name, val in prog.items():
        assert detail[name].modified == val, f"{name} headline changed"
        assert all("vs " not in ln.note for ln in detail[name].lines)


