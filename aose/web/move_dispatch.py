"""Drag-and-drop dispatcher — shared between sheet and wizard.

The dispatcher takes a state object exposing five attributes (``inventory``,
``stashed``, ``equipped``, ``equipped_weapons``, ``containers``) plus a
GameData and translates a (source, target) pair into one or more engine
helper calls, mutating the state object in place.

Source / target conventions:
  * ``"equipped"`` / ``"carried"`` / ``"stashed"`` — section headers (loose).
  * ``"container:<instance_id>"`` — content row inside a container.
  * ``"container_row:<instance_id>"`` — the container row itself (dragging
    the whole bag).
"""
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.shop import (
    stash as shop_stash,
    stash_container as shop_stash_container,
    stow as shop_stow,
    take_out as shop_take_out,
    unstash as shop_unstash,
    unstash_container as shop_unstash_container,
)


def dispatch_move(state, source: str, target: str, item_id: str,
                  instance_id: str, game_data,
                  allowed_weapons="all", allowed_armor="all",
                  allow_shields: bool = True) -> None:
    """Mutate ``state`` per the source/target combination.

    Raises ``ValueError`` for invalid combinations.  Engine helpers may raise
    their own ValueErrors (ContainerFull, etc.); those propagate.

    ``allowed_weapons`` / ``allowed_armor`` (either the sentinel ``"all"`` or a
    set of permitted ids) and ``allow_shields`` gate the equip transition the
    same way the explicit equip routes do; defaults are unrestricted so callers
    that don't enforce stay unaffected.
    """
    # Container-row drag = stash/unstash the whole bag
    if source.startswith("container_row:"):
        bag_id = source.split(":", 1)[1]
        if target == "stashed":
            state.containers = shop_stash_container(state.containers, bag_id)
            return
        if target == "carried":
            state.containers = shop_unstash_container(state.containers, bag_id)
            return
        raise ValueError(f"Cannot move container to {target!r}")

    # Item out of a container
    if source.startswith("container:"):
        bag_id = source.split(":", 1)[1]
        if target.startswith("container:"):
            dest_id = target.split(":", 1)[1]
            state.inventory, state.stashed, state.containers = shop_take_out(
                state.inventory, state.stashed, state.containers, bag_id, item_id,
            )
            state.inventory, state.stashed, state.containers = shop_stow(
                state.inventory, state.stashed, state.containers,
                state.equipped, state.equipped_weapons,
                dest_id, item_id, game_data,
            )
            return
        if target in ("carried", "stashed"):
            state.inventory, state.stashed, state.containers = shop_take_out(
                state.inventory, state.stashed, state.containers, bag_id, item_id,
            )
            # take_out delivers to the bag's own state; if the user dragged
            # to the other state, hop the item across.
            bag_state = next(
                c.state for c in state.containers if c.instance_id == bag_id
            )
            if bag_state != target:
                if target == "stashed" and item_id in state.inventory:
                    state.inventory, state.stashed, state.equipped, state.equipped_weapons = shop_stash(
                        state.inventory, state.stashed,
                        state.equipped, state.equipped_weapons,
                        item_id, game_data,
                    )
                elif target == "carried" and item_id in state.stashed:
                    state.inventory, state.stashed = shop_unstash(
                        state.inventory, state.stashed, item_id, game_data,
                    )
            return
        raise ValueError(f"Cannot move container item to {target!r}")

    # Item into a container from a section
    if target.startswith("container:"):
        dest_id = target.split(":", 1)[1]
        if source == "equipped":
            state.equipped, state.equipped_weapons = _unequip(
                state.equipped, state.equipped_weapons, item_id, game_data,
            )
        elif source == "stashed":
            state.inventory, state.stashed = shop_unstash(
                state.inventory, state.stashed, item_id, game_data,
            )
        elif source != "carried":
            raise ValueError(f"Cannot stow from {source!r}")
        state.inventory, state.stashed, state.containers = shop_stow(
            state.inventory, state.stashed, state.containers,
            state.equipped, state.equipped_weapons,
            dest_id, item_id, game_data,
        )
        return

    # Between sections
    transitions = {
        ("carried", "equipped"): "equip",
        ("equipped", "carried"): "unequip",
        ("carried", "stashed"): "stash",
        ("stashed", "carried"): "unstash",
    }
    action = transitions.get((source, target))
    if action == "equip":
        state.equipped, state.equipped_weapons = _equip(
            state.inventory, state.equipped, state.equipped_weapons,
            item_id, game_data,
            allowed_weapons=allowed_weapons,
            allowed_armor=allowed_armor,
            allow_shields=allow_shields,
        )
    elif action == "unequip":
        state.equipped, state.equipped_weapons = _unequip(
            state.equipped, state.equipped_weapons, item_id, game_data,
        )
    elif action == "stash":
        state.inventory, state.stashed, state.equipped, state.equipped_weapons = shop_stash(
            state.inventory, state.stashed,
            state.equipped, state.equipped_weapons,
            item_id, game_data,
        )
    elif action == "unstash":
        state.inventory, state.stashed = shop_unstash(
            state.inventory, state.stashed, item_id, game_data,
        )
    else:
        raise ValueError(f"Cannot move {source!r} -> {target!r}")
