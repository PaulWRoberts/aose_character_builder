"""Assemble the read-model for the sheet's Companions & Holdings section.

Pure view assembly: derives display stats (AC from armour or natural, THAC0 and
saves via monster_stats) and resolves contents into inventory rows. Reuses
shop.InventoryRow / detail.item_card; imports only models + engine helpers.
"""
from __future__ import annotations

from pydantic import BaseModel

from aose.data.loader import GameData
from aose.engine import companions, monster_stats as ms
from aose.engine.detail import DetailCard, item_card
from aose.engine.shop import InventoryRow
from aose.models import Animal, AnimalArmor, CharacterSpec, Vehicle
from aose.models.storage import StorageLocation


class AnimalCard(BaseModel):
    instance_id: str
    catalog_id: str
    name: str            # label or species name
    species: str
    ac_descending: int
    ac_ascending: int
    thac0: int
    attack_bonus: int
    saves: dict[str, int]
    hp_current: int
    hp_max: int
    movement: str
    morale: int
    traits: list[str]
    armor_id: str | None
    armor_options: list[tuple[str, str]]    # (id, name) of owned fitting armour
    load_used: int
    load_capacity: int | None
    contents: list[InventoryRow]
    magic_note: str
    detail: DetailCard


class VehicleCard(BaseModel):
    instance_id: str
    catalog_id: str
    name: str
    kind: str            # species/type name
    ac_descending: int
    ac_ascending: int
    hull_current: int
    hull_max: int
    cargo_used: int
    cargo_capacity: int
    extra_animals: bool
    has_extra: bool
    required_animals: str | None    # display text, e.g. "1 draft horse or 2 mules"
    contents: list[InventoryRow]
    detail: DetailCard


class RetainerCard(BaseModel):
    id: str
    name: str
    descriptor: str          # "Human Fighter 1" or "0-level Normal Human"
    is_normal_human: bool
    ac_descending: int
    ac_ascending: int
    hp_current: int
    hp_max: int
    thac0: int
    saves: dict[str, int]
    equipped: dict[str, str]     # slot -> item name (display)
    loyalty: int
    role: str
    inventory: list[InventoryRow]
    xp: int


class CompanionsBlock(BaseModel):
    animals: list[AnimalCard] = []
    vehicles: list[VehicleCard] = []
    retainers: list[RetainerCard] = []
    max_retainers: int = 0


def _content_rows(spec, loc, data: GameData) -> list[InventoryRow]:
    from aose.engine.storage import items_at
    from aose.sheet.view import _instance_row
    rows = [_instance_row(inst, data) for inst in items_at(spec, loc)]
    rows.sort(key=lambda r: r.name)
    return rows


def _armor_options(catalog: Animal, spec, data: GameData) -> list[tuple[str, str]]:
    from aose.models.storage import StorageLocation
    carried = StorageLocation(kind="carried")
    carried_ids = {i.catalog_id for i in spec.items if i.location == carried}
    out = []
    for aid in catalog.armor_fits:
        if aid in carried_ids and aid in data.items:
            out.append((aid, data.items[aid].name))
    return out


def companions_block(spec: CharacterSpec, data: GameData) -> CompanionsBlock | None:
    if not spec.animals and not spec.vehicles:
        return None

    animal_cards: list[AnimalCard] = []
    for inst in spec.animals:
        catalog = data.items.get(inst.catalog_id)
        if not isinstance(catalog, Animal):
            continue
        ac = catalog.ac
        if inst.armor_id and isinstance(data.items.get(inst.armor_id), AnimalArmor):
            ac = data.items[inst.armor_id].sets_ac
        atk = ms.attack_for_hd(catalog.hd, data)
        animal_cards.append(AnimalCard(
            instance_id=inst.instance_id, catalog_id=inst.catalog_id,
            name=inst.name or catalog.name, species=catalog.name,
            ac_descending=ac, ac_ascending=ms.ascending_ac(ac),
            thac0=atk.thac0, attack_bonus=atk.attack_bonus,
            saves=ms.saves_for_hd(catalog.save_as_hd, data),
            hp_current=max(0, catalog.hp - inst.hp_damage), hp_max=catalog.hp,
            movement=catalog.movement, morale=catalog.morale,
            traits=catalog.traits, armor_id=inst.armor_id,
            armor_options=_armor_options(catalog, spec, data),
            load_used=companions.animal_load_cn(spec, inst, data),
            load_capacity=companions.animal_capacity(inst, data),
            contents=_content_rows(spec,
                                   StorageLocation(kind="animal", id=inst.instance_id),
                                   data),
            magic_note=inst.magic_note, detail=item_card(catalog),
        ))

    vehicle_cards: list[VehicleCard] = []
    for inst in spec.vehicles:
        catalog = data.items.get(inst.catalog_id)
        if not isinstance(catalog, Vehicle):
            continue
        vehicle_cards.append(VehicleCard(
            instance_id=inst.instance_id, catalog_id=inst.catalog_id,
            name=inst.name or catalog.name, kind=catalog.name,
            ac_descending=catalog.ac, ac_ascending=ms.ascending_ac(catalog.ac),
            hull_current=max(0, inst.hull_max - inst.hull_damage),
            hull_max=inst.hull_max,
            cargo_used=companions.vehicle_load_cn(spec, inst, data),
            cargo_capacity=companions.vehicle_capacity(inst, data),
            extra_animals=inst.extra_animals,
            has_extra=catalog.cargo_capacity_extra_cn is not None,
            required_animals=catalog.required_animals,
            contents=_content_rows(spec,
                                   StorageLocation(kind="vehicle", id=inst.instance_id),
                                   data),
            detail=item_card(catalog),
        ))

    return CompanionsBlock(animals=animal_cards, vehicles=vehicle_cards)
