from typing import Literal

from pydantic import BaseModel, ConfigDict


class SpellList(BaseModel):
    """A spell pool / tradition (e.g. magic_user, druid).  Its ``caster_type``
    decides whether classes casting from it are arcane (spellbook, limited
    known) or divine (knows the whole list, prays daily).  Classes reference a
    list by id via ``CharClass.spell_lists``; spells via ``Spell.spell_lists``.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    caster_type: Literal["arcane", "divine", "mental"]
    source: str = "ose_classic_fantasy"
    description: str | None = None
