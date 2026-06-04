from aose.models import CharacterSpec, ClassEntry


def _spec(**kw):
    base = dict(
        name="Tester",
        abilities={"STR": 12, "INT": 12, "WIS": 11, "DEX": 12, "CON": 12, "CHA": 10},
        race_id="human",
        classes=[ClassEntry(class_id="fighter", level=1, hp_rolls=[6])],
        alignment="law",
    )
    base.update(kw)
    return CharacterSpec(**base)


def test_coin_fields_default_zero():
    s = _spec()
    assert (s.platinum, s.gold, s.electrum, s.silver, s.copper) == (0, 0, 0, 0, 0)


def test_carrying_treasure_defaults_false():
    assert _spec().carrying_treasure is False
