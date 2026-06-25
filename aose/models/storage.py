from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LocationKind = Literal["carried", "stashed", "animal", "vehicle", "container", "retainer"]


class StorageLocation(BaseModel):
    """Where a value-stack (coins/gems/jewellery) or a container sits.

    Pointer model: a stack inside a container stores ``kind="container"`` +
    the container's ``instance_id``; the container owns its own bucket
    (carried/stashed/animal/vehicle), so moving the container moves its
    contents for free. ``id`` is the carrier/container instance_id; None for
    the person-level carried/stashed buckets.

    A *container's own* location may only be carried/stashed/animal/vehicle
    (never ``container`` — no nesting); this is enforced on
    ``ContainerInstance``, not here, so a value-stack can still use all five.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: LocationKind
    id: str | None = None


class CoinStack(BaseModel):
    """A stack of one coin denomination at one location. At most one stack
    per (denom, location); empty stacks are pruned by the movement engine."""
    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    denom: Literal["pp", "gp", "ep", "sp", "cp"]
    count: int
    location: StorageLocation = Field(default_factory=lambda: StorageLocation(kind="carried"))
