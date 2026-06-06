from pathlib import Path

from aose.data.loader import GameData
from aose.engine.detail import DetailCard, StatLine, spell_card

DATA = GameData.load(Path(__file__).parent.parent / "data")


def _stat(card, label):
    return next((s.value for s in card.stats if s.label == label), None)


def test_spell_card_has_level_range_duration_and_description():
    spell = DATA.spells["cleric_cure_light_wounds"]
    card = spell_card(spell)
    assert isinstance(card, DetailCard)
    assert _stat(card, "Level") == "1"
    assert _stat(card, "Range") == spell.range
    assert _stat(card, "Duration") == spell.duration
    assert card.description == spell.description


def test_spell_card_reversible_line_uses_reverse_name():
    spell = DATA.spells["cleric_cure_light_wounds"]  # reversible
    card = spell_card(spell)
    assert _stat(card, "Reversible") == "Yes — Cause Light Wounds"


def test_spell_card_non_reversible_has_no_reversible_line():
    spell = next(s for s in DATA.spells.values() if not s.reversible)
    card = spell_card(spell)
    assert _stat(card, "Reversible") is None


# ── item_card tests ────────────────────────────────────────────────────────

from aose.engine.detail import item_card  # noqa: E402
from aose.models import Armor, Weapon  # noqa: E402


def test_item_card_weapon_has_damage_and_description():
    weapon = next(i for i in DATA.items.values() if isinstance(i, Weapon))
    card = item_card(weapon)
    assert _stat(card, "Type") == "Weapon"
    assert _stat(card, "Damage") == weapon.damage.default
    assert _stat(card, "Cost") == f"{int(weapon.cost_gp)} gp"
    assert card.description == (weapon.description or None)


def test_item_card_ranged_weapon_has_range_line():
    weapon = next(
        (i for i in DATA.items.values()
         if isinstance(i, Weapon) and i.ranged and i.range_short),
        None,
    )
    if weapon is None:
        return  # no ranged weapon in data — nothing to assert
    card = item_card(weapon)
    expected = f"{weapon.range_short}/{weapon.range_medium}/{weapon.range_long} ft"
    assert _stat(card, "Range") == expected


def test_item_card_body_armor_shows_ac():
    armor = next(
        i for i in DATA.items.values()
        if isinstance(i, Armor) and not i.is_shield
    )
    card = item_card(armor)
    assert _stat(card, "Type") == "Armour"
    assert _stat(card, "AC") == f"{armor.ac_descending} [{19 - armor.ac_descending}]"


def test_item_card_shield_shows_ac_bonus():
    shield = next(
        (i for i in DATA.items.values() if isinstance(i, Armor) and i.is_shield),
        None,
    )
    if shield is None:
        return
    card = item_card(shield)
    assert _stat(card, "Type") == "Shield"
    assert _stat(card, "AC Bonus") == f"+{shield.ac_bonus}"


def test_item_card_unknown_type_falls_back_to_cost_and_description():
    gear = next(i for i in DATA.items.values() if i.item_type == "gear")
    card = item_card(gear)
    assert _stat(card, "Cost") == f"{int(gear.cost_gp)} gp"
