"""Cycle-free builders for inline detail cards (spells & items).

Imports only ``aose.models`` so both ``aose/engine/shop.py`` and
``aose/sheet/view.py`` can use it without an import cycle.
"""
from pydantic import BaseModel, ConfigDict

from aose.models import (
    AdventuringGear, Ammunition, Animal, AnimalArmor, Armor, Container,
    MagicItem, Poison, Spell, Vehicle, Weapon,
)


class StatLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class DetailCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stats: list[StatLine] = []
    description: str | None = None


def spell_card(spell: Spell, *, reversed: bool = False) -> DetailCard:
    stats = [
        StatLine(label="Level", value=str(spell.level)),
        StatLine(label="Range", value=spell.range),
        StatLine(label="Duration", value=spell.duration),
    ]
    if spell.reversible:
        rn = spell.reverse_name or "—"
        stats.append(StatLine(label="Reversible", value=f"Yes — {rn}"))
    return DetailCard(stats=stats, description=spell.description)


def _format_qualities(weapon) -> str:
    """Human-readable quality list: bare ids title-cased, params inlined."""
    parts: list[str] = []
    for q in weapon.qualities:
        name = q.id.replace("_", " ").title()
        if q.id == "missile" and q.param:
            parts.append(f"{name} ({q.param[0]}/{q.param[1]}/{q.param[2]} ft)")
        elif q.id == "versatile" and q.param:
            parts.append(f"{name} ({q.param})")
        else:
            parts.append(name)
    return ", ".join(parts)


def _cost_weight(item) -> list[StatLine]:
    out: list[StatLine] = []
    if item.cost_gp:
        out.append(StatLine(label="Cost", value=f"{int(item.cost_gp)} gp"))
    if item.weight_cn:
        out.append(StatLine(label="Weight", value=f"{item.weight_cn} cn"))
    return out


def item_card(item) -> DetailCard:
    stats: list[StatLine] = []

    if isinstance(item, Weapon):
        stats.append(StatLine(label="Type", value="Weapon"))
        stats.append(StatLine(label="Damage",
                              value=item.damage.default if item.deals_damage else "—"))
        if item.two_handed_damage:
            stats.append(StatLine(label="Damage (2H)", value=item.two_handed_damage))
        if item.ranged and item.range_short:
            stats.append(StatLine(
                label="Range",
                value=f"{item.range_short}/{item.range_medium}/{item.range_long} ft"))
        stats.append(StatLine(label="Hands", value=str(item.hands)))
        if item.qualities:
            stats.append(StatLine(label="Qualities", value=_format_qualities(item)))
        if item.magic_bonus:
            stats.append(StatLine(label="Magic", value=f"+{item.magic_bonus}"))
        if item.conditional_bonus:
            cb = item.conditional_bonus
            stats.append(StatLine(label="Bonus", value=f"+{cb.bonus} vs {cb.vs}"))
        stats += _cost_weight(item)

    elif isinstance(item, Armor):
        if item.is_shield:
            stats.append(StatLine(label="Type", value="Shield"))
            stats.append(StatLine(label="AC Bonus", value=f"+{item.ac_bonus}"))
        else:
            stats.append(StatLine(label="Type", value="Armour"))
            stats.append(StatLine(
                label="AC",
                value=f"{item.ac_descending} [{19 - item.ac_descending}]"))
        if item.magic_bonus:
            stats.append(StatLine(label="Magic", value=f"+{item.magic_bonus}"))
        stats += _cost_weight(item)

    elif isinstance(item, Container):
        stats.append(StatLine(label="Type", value="Container"))
        cap = item.capacity_cn
        stats.append(StatLine(
            label="Capacity", value=f"{cap} cn" if cap else "Unlimited"))
        stats += _cost_weight(item)

    elif isinstance(item, MagicItem):
        stats.append(StatLine(label="Type", value="Magic Item"))
        if item.max_charges is not None:
            stats.append(StatLine(label="Charges", value=str(item.max_charges)))
        stats += _cost_weight(item)

    elif isinstance(item, Ammunition):
        stats.append(StatLine(label="Type", value="Ammunition"))
        if item.groups:
            stats.append(StatLine(label="Groups", value=", ".join(item.groups)))
        if item.bundle_count > 1:
            stats.append(StatLine(label="Bundle", value=str(item.bundle_count)))
        stats += _cost_weight(item)

    elif isinstance(item, Poison):
        stats.append(StatLine(label="Type", value="Poison"))
        if item.onset:
            stats.append(StatLine(label="Onset", value=item.onset))
        if item.effect:
            stats.append(StatLine(label="Effect", value=item.effect))
        stats += _cost_weight(item)

    elif isinstance(item, Animal):
        stats.append(StatLine(label="Type", value="Animal"))
        stats.append(StatLine(label="AC", value=f"{item.ac} [{19 - item.ac}]"))
        stats.append(StatLine(label="HD", value=item.hd))
        if item.attacks:
            stats.append(StatLine(
                label="Attacks",
                value=", ".join(
                    (f"{a.note} " if a.note else "")
                    + (f"{a.count}× " if a.count > 1 else "")
                    + f"{a.name} ({a.damage})"
                    for a in item.attacks)))
        stats.append(StatLine(label="Move", value=item.movement))
        if item.max_load_unencumbered_cn:
            stats.append(StatLine(
                label="Max Load",
                value=f"{item.max_load_unencumbered_cn} / "
                      f"{item.max_load_encumbered_cn} cn"))
        stats.append(StatLine(label="Morale", value=str(item.morale)))
        stats += _cost_weight(item)

    elif isinstance(item, Vehicle):
        stats.append(StatLine(label="Type", value="Vehicle"))
        stats.append(StatLine(label="AC", value=f"{item.ac} [{19 - item.ac}]"))
        stats.append(StatLine(label="Hull Points", value=item.hull_points))
        cargo = f"{item.cargo_capacity_cn} cn"
        if item.cargo_capacity_extra_cn:
            cargo += f" ({item.cargo_capacity_extra_cn} with extra animals)"
        stats.append(StatLine(label="Cargo", value=cargo))
        if item.required_animals:
            stats.append(StatLine(label="Animals", value=item.required_animals))
        if item.required_crew:
            stats.append(StatLine(label="Crew", value=item.required_crew))
        if item.max_mercenaries:
            stats.append(StatLine(label="Mercenaries", value=str(item.max_mercenaries)))
        stats += _cost_weight(item)

    elif isinstance(item, AnimalArmor):
        stats.append(StatLine(label="Type", value="Animal Armour"))
        stats.append(StatLine(label="AC", value=f"{item.sets_ac} [{19 - item.sets_ac}]"))
        if item.fits:
            stats.append(StatLine(label="Fits", value=", ".join(item.fits)))
        stats += _cost_weight(item)

    else:  # AdventuringGear and anything else
        stats.append(StatLine(label="Type", value="Gear"))
        if isinstance(item, AdventuringGear) and item.bundle_count > 1:
            stats.append(StatLine(label="Bundle", value=str(item.bundle_count)))
        stats += _cost_weight(item)

    return DetailCard(stats=stats, description=item.description or None)
