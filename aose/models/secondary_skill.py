from pydantic import BaseModel, ConfigDict, Field


class SecondarySkillEntry(BaseModel):
    """One row of the Secondary Skills table.  ``weight`` is the number of d100
    faces the row spans (its share of the distribution).  Exactly one entry in a
    table carries ``roll_twice`` — the "roll for two skills" outcome, which is
    expanded to two distinct trades at roll time."""
    model_config = ConfigDict(extra="forbid")

    name: str
    weight: int = Field(ge=1)
    roll_twice: bool = False
