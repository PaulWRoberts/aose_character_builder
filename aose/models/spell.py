from pydantic import BaseModel, ConfigDict, Field


class Spell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    level: int
    classes: list[str] = Field(default_factory=list)
    range: str
    duration: str
    description: str
    reversible: bool = False
    reverse_name: str | None = None
