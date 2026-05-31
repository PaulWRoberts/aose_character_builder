from pydantic import BaseModel, ConfigDict


class WeaponQuality(BaseModel):
    """A weapon quality definition (Blunt, Brace, Charge, …) — referenceable
    in-game.  Not an ``Item``; loaded into ``GameData.qualities``."""
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
