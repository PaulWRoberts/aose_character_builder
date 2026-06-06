from pydantic import BaseModel, ConfigDict, Field


class Spell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    level: int
    # Spell-list IDs this spell belongs to (e.g. ["magic_user"], ["cleric",
    # "druid"]). The list ID is decoupled from class ID, so race-as-class
    # entries can reuse a list (elf -> magic_user) without re-tagging spells.
    spell_lists: list[str] = Field(default_factory=list)
    source: str = "ose_classic_fantasy"
    range: str
    duration: str
    description: str
    reversible: bool = False
    reverse_name: str | None = None
