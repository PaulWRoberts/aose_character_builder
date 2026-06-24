from pathlib import Path
import random
from aose.data.loader import GameData
from aose.engine import retainers
from aose.models import CharacterSpec, RuleSet

DATA = GameData.load(Path("data"))


def _pc(level=5, cha=13):
    return CharacterSpec(
        name="Boss", abilities={"STR": 12, "INT": 10, "WIS": 10, "DEX": 10,
                                "CON": 10, "CHA": cha},
        race_id="human", classes=[{"class_id": "fighter", "level": level}],
        alignment="neutral")


def test_generate_fighter_retainer():
    pc = _pc(level=3, cha=13)
    ret = retainers.generate_retainer(
        name="Sten", class_ids=["fighter"], level=2, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(1))
    assert ret.spec.classes[0].class_id == "fighter"
    assert ret.spec.classes[0].level == 2
    assert len(ret.spec.classes[0].hp_rolls) == 2     # one per level
    assert all(v == 10 for k, v in ret.spec.abilities.items()
               if k not in ("STR",))                  # baseline 10 except bumps
    assert ret.spec.inventory                         # quick-equipment kit applied
    assert ret.loyalty == 9                            # human CHA13 base 8, +1 human = 9
    assert ret.spec.ruleset == pc.ruleset             # inherited snapshot


def test_generate_meets_class_requirements():
    pc = _pc()
    # a class with an ability requirement raises that score to the minimum
    cls = next(c for c in DATA.classes.values() if c.ability_requirements)
    req_ab, req_val = next(iter(cls.ability_requirements.items()))
    ret = retainers.generate_retainer(
        name="Req", class_ids=[cls.id], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(2))
    assert ret.spec.abilities[req_ab.value] >= req_val


def test_normal_human_retainer_level_one():
    pc = _pc()
    ret = retainers.generate_retainer(
        name="Boy", class_ids=["normal_human"], level=1, race_id="human",
        alignment="neutral", hiring_spec=pc, data=DATA, rng=random.Random(3))
    assert ret.spec.classes[0].class_id == "normal_human"


def _human_pc(ruleset):
    return CharacterSpec(
        name="PC",
        abilities={"STR": 12, "INT": 12, "WIS": 10, "DEX": 12, "CON": 10, "CHA": 12},
        race_id="human",
        classes=[{"class_id": "fighter", "level": 3}],
        alignment="neutral",
        ruleset=ruleset,
    )


def test_human_benefits_applied_in_advanced():
    rs = RuleSet(separate_race_class=True, human_racial_abilities=True)
    base = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs), data=DATA,
        rng=random.Random(1))
    rs2 = RuleSet(separate_race_class=True, human_racial_abilities=False)
    plain = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs2), data=DATA,
        rng=random.Random(1))
    human = DATA.races["human"]
    if human.optional_ability_modifiers:
        assert base.spec.abilities != plain.spec.abilities


def test_human_benefits_ignored_in_basic():
    rs = RuleSet(separate_race_class=False, human_racial_abilities=True)
    ret = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs), data=DATA,
        rng=random.Random(1))
    # Basic mode applies no racial modifiers at all; a fighter's only floor is
    # its ability requirements, so non-requirement scores stay at baseline 10.
    assert ret.spec.abilities["CHA"] == 10


def test_retainer_is_single_class_even_with_multiclassing():
    rs = RuleSet(multiclassing=True, separate_race_class=True)
    ret = retainers.generate_retainer(
        name="H", class_ids=["fighter"], level=1, race_id="human",
        alignment="neutral", hiring_spec=_human_pc(rs), data=DATA)
    assert len(ret.spec.classes) == 1
