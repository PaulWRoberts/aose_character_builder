"""Initiative modifier breakdown for the individual-initiative optional rule.

Display-only: the sheet renders this only when ``ruleset.individual_initiative``
is set. Cycle-free — imports ability_mods, magic, and features; none import this.
"""
from pydantic import BaseModel

from aose.data.loader import GameData
from aose.models import Ability, CharacterSpec
from aose.engine.ability_mods import initiative_modifier
from aose.engine.features import all_modifiers
from aose.engine.magic import effective_abilities


class InitiativeLine(BaseModel):
    source: str          # "Dexterity", feature/item name
    bonus: int
    conditional: bool
    note: str            # condition note ("" when unconditional)


class InitiativeDetail(BaseModel):
    base: int                       # DEX initiative modifier
    total: int                      # base + unconditional bonuses
    lines: list[InitiativeLine]
    has_conditional: bool


def initiative_detail(spec: CharacterSpec, data: GameData) -> InitiativeDetail:
    eff = effective_abilities(spec, data)
    base = initiative_modifier(eff[Ability.DEX])
    lines = [InitiativeLine(source="Dexterity", bonus=base,
                            conditional=False, note="")]
    total = base
    for m in all_modifiers(spec, data):
        if m.target != "initiative":
            continue
        conditional = m.condition is not None
        lines.append(InitiativeLine(
            source=m.source or "Bonus",
            bonus=m.value,
            conditional=conditional,
            note=(m.condition.replace("_", " ") if conditional else ""),
        ))
        if not conditional:
            total += m.value
    return InitiativeDetail(
        base=base, total=total, lines=lines,
        has_conditional=any(l.conditional for l in lines),
    )
