from typing import Literal

from pydantic import BaseModel, ConfigDict


class WeaponQuality(BaseModel):
    """A weapon quality definition (Blunt, Brace, Charge, …) — referenceable
    in-game.  Not an ``Item``; loaded into ``GameData.qualities``.

    ``param`` declares whether weapons carry a value for this quality:
    ``ranges`` (the [short, medium, long] of ``missile``), ``damage`` (the
    two-handed die of ``versatile``), or ``none``."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    param: Literal["none", "ranges", "damage"] = "none"
