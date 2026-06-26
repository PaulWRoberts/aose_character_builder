from pathlib import Path
from aose.data.loader import GameData
from aose.engine import enchant
from aose.models import ItemInstance, Weapon, Armor

DATA = GameData.load(Path("data"))


def test_resolve_plain_returns_catalog_item():
    inst = ItemInstance(instance_id="i1", catalog_id="sword")
    assert enchant.resolve(inst, DATA) is DATA.items["sword"]


def test_resolve_enchanted_weapon_composes_synthetic():
    # sword_plus_1 applies specifically to swords
    inst = ItemInstance(instance_id="e1", catalog_id="sword",
                        enchantment_id="sword_plus_1")
    out = enchant.resolve(inst, DATA)
    assert isinstance(out, Weapon) and out.magic and out.magic_bonus == 1
    assert out.base_weapon == "sword"


def test_resolve_enchanted_armor_composes_synthetic():
    # armour_plus_1 applies to armour
    inst = ItemInstance(instance_id="e2", catalog_id="chain_mail",
                        enchantment_id="armour_plus_1")
    out = enchant.resolve(inst, DATA)
    assert isinstance(out, Armor) and out.magic and out.base_armor == "chain_mail"


def test_new_enchanted_instance_is_an_item_instance():
    # generic_plus_1 applies to any weapon except swords; use battle_axe
    inst = enchant.new_enchanted_instance("battle_axe", "generic_plus_1", DATA)
    assert isinstance(inst, ItemInstance)
    assert inst.catalog_id == "battle_axe" and inst.enchantment_id == "generic_plus_1"
    assert inst.equip is None


def test_enchant_has_no_list_equip():
    assert not hasattr(enchant, "equip")
    assert not hasattr(enchant, "unequip")
