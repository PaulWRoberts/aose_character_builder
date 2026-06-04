from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aose.characters.storage import list_character_ids, load_character, save_character
from aose.engine import dice, hp, spells as spell_engine
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.energy_drain import energy_drain as _energy_drain
from aose.engine.leveling import grant_xp as _grant_xp, level_up as _level_up
from aose.engine.enchant import (
    IncompatibleBase,
    NoCharges as _EnchNoCharges,
    UnknownEnchantment,
    add_free_enchanted as _add_free_enchanted,
    equip as _equip_enchanted,
    remove as _remove_enchanted,
    reset_charges as _reset_ench_charges,
    set_note as _set_enchanted_note,
    unequip as _unequip_enchanted,
    use_charge as _use_ench_charge,
)
from aose.engine.magic import (
    NoCharges,
    NotEquippable,
    UnknownMagicItem,
    add_free_magic_item,
    effective_abilities,
    equip_magic as _equip_magic,
    needs_instance,
    remove_magic as _remove_magic,
    reset_charges as _reset_charges,
    set_magic_note as _set_magic_note,
    set_temp_ability_modifier as _set_temp_ability_modifier,
    unequip_magic as _unequip_magic,
    use_charge as _use_charge,
)
from aose.engine.shop import (
    REMOVE_MODES,
    InsufficientGold,
    UnknownItem,
    add_free as shop_add_free,
    add_free_container,
    buy as shop_buy,
    buy_container,
    inventory_view as shop_inventory_view,
    remove as shop_remove,
    remove_container as shop_remove_container,
    remove_from_stash as shop_remove_from_stash,
    shop_categories,
    stash as shop_stash,
    stash_container as shop_stash_container,
    stow as shop_stow,
    take_out as shop_take_out,
    unstash as shop_unstash,
    unstash_container as shop_unstash_container,
)
from aose.engine.ammo import (
    add_free_ammo as _add_free_ammo,
    adjust_count as _adjust_ammo,
    buy_ammo as _buy_ammo,
    load as _load_ammo,
    remove_ammo as _remove_ammo,
    unload as _unload_ammo,
    InsufficientGold as _AmmoInsufficientGold,
    IncompatibleAmmo as _IncompatibleAmmo,
    UnknownAmmo as _UnknownAmmo,
)
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    shields_allowed,
)
from aose.engine import spell_sources as spell_source_engine
from aose.engine.spell_sources import SpellSourceError
from aose.engine import valuables as valuables_engine
from aose.engine.valuables import ValuableError
from aose.engine import possessions as possessions_engine
from aose.engine.possessions import PossessionError
from aose.models import Ability, Ammunition
from aose.sheet.view import build_sheet, spell_source_add_options

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Read print CSS once at import time so routes don't hit the filesystem per request.
_PRINT_CSS = (STATIC_DIR / "print.css").read_text(encoding="utf-8")


def _enchant_choices(game_data):
    """Picker data: each enchantment with its compatible base items, sorted by kind then id."""
    from aose.engine.enchant import compatible_bases
    out = []
    for ench in sorted(game_data.enchantments.values(), key=lambda e: (e.kind, e.id)):
        bases = compatible_bases(ench, game_data)
        if not bases:
            continue
        out.append({
            "id": ench.id,
            "name_template": ench.name_template,
            "kind": ench.kind,
            "bases": [{"id": b.id, "name": b.name} for b in bases],
        })
    return out


def _character_summaries(characters_dir: Path):
    summaries = []
    for cid in list_character_ids(characters_dir):
        try:
            spec = load_character(cid, characters_dir)
        except Exception:
            continue
        summaries.append({"id": cid, "name": spec.name, "race_id": spec.race_id})
    return summaries


# ── Index ──────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    characters = _character_summaries(request.app.state.characters_dir)
    return templates.TemplateResponse(
        request, "index.html", {"characters": characters}
    )


# ── Character sheet ────────────────────────────────────────────────────────

@router.get("/character/{character_id}", response_class=HTMLResponse)
async def character_sheet(request: Request, character_id: str):
    try:
        spec = load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")
    game_data = request.app.state.game_data
    sheet = build_sheet(spec, game_data)
    classes = [game_data.classes[e.class_id] for e in spec.classes
               if e.class_id in game_data.classes]
    return templates.TemplateResponse(
        request, "sheet.html", {
            "sheet": sheet,
            "character_id": character_id,
            # Equipment partial context (sheet-side: no starting-gold reroll).
            "gold": spec.gold,
            "gold_locked": True,
            "inventory_view": shop_inventory_view(
                spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons,
                spec.containers, game_data,
                allowed_weapons=allowed_weapon_ids(classes, game_data, spec.ruleset),
                allowed_armor=allowed_armor_ids(classes, game_data),
                allow_shields=shields_allowed(classes),
            ),
            "magic_items_view": [v for v in sheet.magic_items
                                 if v.instance_id not in {e.instance_id for e in spec.enchanted}],
            "enchanted_rows": [v for v in sheet.magic_items
                               if v.instance_id in {e.instance_id for e in spec.enchanted}],
            "magic_acquisition": True,
            "enchant_choices": _enchant_choices(game_data),
            "shop": shop_categories(game_data),
            "remove_modes": REMOVE_MODES,
            "target_url_prefix": f"/character/{character_id}/equipment",
            "ammo_rows": sheet.ammo,
            "ammo_load_options": sheet.ammo_load_options,
            "ammo_url_prefix": f"/character/{character_id}",
            "show_gold_reroll": False,
            "show_gold_grant": True,
            "gold_grant_url": f"/character/{character_id}/gold",
            "rest_heal_roll": dice.roll("1d3"),
            "spell_source_add_options": spell_source_add_options(game_data),
        },
    )


# ── Print preview (browser print / Save as PDF) ────────────────────────────

@router.get("/character/{character_id}/print", response_class=HTMLResponse)
async def character_print(request: Request, character_id: str):
    """Return a standalone print-optimised HTML page.

    The page has ``onload="window.print()"`` so opening it in a browser
    immediately triggers the print dialog — choose *Save as PDF* there.
    """
    try:
        spec = load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")
    sheet = build_sheet(spec, request.app.state.game_data)
    html = templates.get_template("sheet_print.html").render(
        sheet=sheet, print_css=_PRINT_CSS, auto_print=True
    )
    return HTMLResponse(content=html)


# ── Server-side PDF (WeasyPrint, needs GTK3 on Windows) ───────────────────

@router.get("/character/{character_id}/pdf")
async def character_pdf(request: Request, character_id: str):
    """Download a server-generated PDF via WeasyPrint.

    Requires GTK3 native libraries on Windows — see ``aose/web/pdf.py`` for
    installation instructions.  Falls back gracefully with a 503 if
    WeasyPrint is unavailable.
    """
    from aose.web.pdf import import_error, is_available, render_pdf

    try:
        spec = load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")

    if not is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Server-side PDF is unavailable: WeasyPrint could not load GTK3 "
                f"native libraries ({import_error()}). "
                f"Use /character/{character_id}/print instead and choose "
                "'Save as PDF' in your browser's print dialog, OR install the "
                "GTK3 runtime from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"
            ),
        )

    sheet = build_sheet(spec, request.app.state.game_data)
    html = templates.get_template("sheet_print.html").render(
        sheet=sheet, print_css=_PRINT_CSS, auto_print=False
    )
    pdf_bytes = render_pdf(html)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{character_id}.pdf"'},
    )


# ── Advancement: grant XP and level up ────────────────────────────────────

def _load_spec_or_404(request: Request, character_id: str):
    try:
        return load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")


@router.post("/character/{character_id}/xp")
async def grant_xp(request: Request, character_id: str, amount: int = Form(...)):
    """Add or subtract XP.  Total XP is clamped at zero — leveling down is
    not modelled, so reducing XP below a class's threshold doesn't strip the
    level (the user can edit the JSON if they really need to)."""
    spec = _load_spec_or_404(request, character_id)
    _grant_xp(spec, request.app.state.game_data, amount)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gold")
async def grant_gold(request: Request, character_id: str, amount: int = Form(...)):
    """Add or subtract gold.  Clamped at zero — negative balances aren't a
    thing in OSE, even if the GM claws back some treasure."""
    spec = _load_spec_or_404(request, character_id)
    spec.gold = max(0, spec.gold + amount)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/damage")
async def hp_damage(request: Request, character_id: str, amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.damage_taken = hp.apply_damage(spec, data, amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/heal")
async def hp_heal(request: Request, character_id: str, amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.damage_taken = hp.apply_healing(spec, data, amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/set")
async def hp_set(request: Request, character_id: str, value: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    spec.damage_taken = hp.set_current_hp(spec, data, value)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/abilities/temp-modifier")
async def abilities_temp_modifier(request: Request, character_id: str,
                                  ability: str = Form(...), value: int = Form(...)):
    """Set (or clear, when value is 0) a temporary modifier on one ability.
    Replaces any prior modifier for that ability; never touches the real score."""
    from aose.models import Ability
    spec = _load_spec_or_404(request, character_id)
    try:
        ab = Ability(ability)
    except ValueError:
        raise HTTPException(400, f"Unknown ability {ability!r}")
    spec.temp_ability_modifiers = _set_temp_ability_modifier(
        spec.temp_ability_modifiers, ab, value,
    )
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/level-up/{class_id}")
async def level_up_class(request: Request, character_id: str, class_id: str):
    """Advance one class by a single level, rolling its hit die for the
    new HP.  Returns 400 if the character can't level (cap reached or XP
    short of the next threshold)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _level_up(spec, request.app.state.game_data, class_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/energy-drain")
async def energy_drain_route(request: Request, character_id: str,
                             levels: int = Form(...),
                             xp_mode: str = Form("new_min")):
    """Permanently drain experience levels LIFO (GM action). Removes the
    matching Hit Dice and now-inaccessible spells, resets XP per ``xp_mode``,
    and kills the character if the loss would drop them below level 1.
    Returns 400 on invalid input (levels < 1, unknown xp_mode, or midpoint
    with more than one level)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _energy_drain(spec, request.app.state.game_data, levels, xp_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Equipment management on the live sheet ────────────────────────────────

@router.post("/character/{character_id}/equipment/buy")
async def equipment_buy(request: Request, character_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Ammunition):
            spec.ammo, spec.gold = _buy_ammo(spec.ammo, spec.gold, item_id, game_data)
        elif isinstance(item, Container):
            spec.containers, spec.gold = buy_container(
                spec.containers, spec.gold, item_id, game_data,
            )
        else:
            new_inventory, new_gold = shop_buy(spec.inventory, spec.gold, item_id, game_data)
            spec.inventory = new_inventory
            spec.gold = new_gold
    except (UnknownItem, InsufficientGold, _AmmoInsufficientGold, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/add")
async def equipment_add(request: Request, character_id: str,
                        item_id: str = Form(...)):
    """Add an item to inventory without spending gold — covers GM-given gear,
    found loot, and similar off-ledger acquisitions."""
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Ammunition):
            spec.ammo = _add_free_ammo(spec.ammo, item_id, None, game_data)
        elif needs_instance(item):
            spec.magic_items = add_free_magic_item(spec.magic_items, item_id, game_data)
        elif isinstance(item, Container):
            spec.containers = add_free_container(spec.containers, item_id, game_data)
        else:
            spec.inventory = shop_add_free(spec.inventory, item_id, game_data)
    except (UnknownItem, UnknownMagicItem, _UnknownAmmo, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/equip")
async def equipment_equip(request: Request, character_id: str,
                          item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    try:
        spec.equipped, spec.equipped_weapons = _equip(
            spec.inventory, spec.equipped, spec.equipped_weapons,
            item_id, data,
            allowed_weapons=allowed_weapon_ids(classes, data, spec.ruleset),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip")
async def equipment_unequip(request: Request, character_id: str,
                            item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.equipped, spec.equipped_weapons = _unequip(
            spec.equipped, spec.equipped_weapons,
            item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove")
async def equipment_remove(request: Request, character_id: str,
                           item_id: str = Form(...),
                           mode: str = Form(...),
                           from_state: str = Form("carried")):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    try:
        if from_state == "stashed":
            spec.stashed, spec.gold = shop_remove_from_stash(
                spec.stashed, spec.gold, item_id, mode, game_data,
            )
        else:
            spec.inventory, spec.gold, spec.equipped, spec.equipped_weapons = shop_remove(
                spec.inventory, spec.gold, item_id, mode, game_data,
                spec.equipped, spec.equipped_weapons,
            )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/stash")
async def equipment_stash(request: Request, character_id: str,
                          item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons = shop_stash(
            spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons,
            item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unstash")
async def equipment_unstash(request: Request, character_id: str,
                            item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed = shop_unstash(
            spec.inventory, spec.stashed, item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/stow")
async def equipment_stow(request: Request, character_id: str,
                         instance_id: str = Form(...),
                         item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.containers = shop_stow(
            spec.inventory, spec.stashed, spec.containers,
            spec.equipped, spec.equipped_weapons,
            instance_id, item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/take-out")
async def equipment_take_out(request: Request, character_id: str,
                             instance_id: str = Form(...),
                             item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.containers = shop_take_out(
            spec.inventory, spec.stashed, spec.containers,
            instance_id, item_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/stash-container")
async def equipment_stash_container(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers = shop_stash_container(spec.containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unstash-container")
async def equipment_unstash_container(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers = shop_unstash_container(spec.containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-container")
async def equipment_remove_container(request: Request, character_id: str,
                                     instance_id: str = Form(...),
                                     mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers, spec.gold = shop_remove_container(
            spec.containers, spec.gold, instance_id, mode,
            request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Magic item actions ─────────────────────────────────────────────────────

@router.post("/character/{character_id}/equipment/equip-magic")
async def equipment_equip_magic(request: Request, character_id: str,
                                instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _equip_magic(spec.magic_items, instance_id, request.app.state.game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-magic")
async def equipment_unequip_magic(request: Request, character_id: str,
                                  instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _unequip_magic(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/use-charge")
async def equipment_use_charge(request: Request, character_id: str,
                               instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _use_charge(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/reset-charges")
async def equipment_reset_charges(request: Request, character_id: str,
                                  instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _reset_charges(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-magic")
async def equipment_remove_magic(request: Request, character_id: str,
                                 instance_id: str = Form(...),
                                 mode: str = Form("drop")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items, spec.gold = _remove_magic(
            spec.magic_items, spec.gold, instance_id, mode, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/magic-note")
async def equipment_magic_note(request: Request, character_id: str,
                               instance_id: str = Form(...),
                               note: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _set_magic_note(spec.magic_items, instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Enchanted item actions (sheet-only) ────────────────────────────────────

@router.post("/character/{character_id}/equipment/add-enchanted")
async def equipment_add_enchanted(request: Request, character_id: str,
                                  base_id: str = Form(...),
                                  enchantment_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _add_free_enchanted(
            spec.enchanted, base_id, enchantment_id, request.app.state.game_data)
    except (UnknownEnchantment, IncompatibleBase, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/equip-enchanted")
async def equipment_equip_enchanted(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _equip_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-enchanted")
async def equipment_unequip_enchanted(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _unequip_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted/use-charge")
async def equipment_enchanted_use_charge(request: Request, character_id: str,
                                         instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _use_ench_charge(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted/reset-charges")
async def equipment_enchanted_reset_charges(request: Request, character_id: str,
                                            instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _reset_ench_charges(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-enchanted")
async def equipment_remove_enchanted(request: Request, character_id: str,
                                     instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _remove_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted-note")
async def equipment_enchanted_note(request: Request, character_id: str,
                                   instance_id: str = Form(...),
                                   note: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _set_enchanted_note(spec.enchanted, instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Spell management on the live sheet ─────────────────────────────────────

def _find_class_entry(spec, class_id: str) -> int:
    for i, e in enumerate(spec.classes):
        if e.class_id == class_id:
            return i
    raise HTTPException(400, f"Character has no class {class_id!r}")


@router.post("/character/{character_id}/spells/learn")
async def sheet_spell_learn(request: Request, character_id: str,
                            class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.learn(
            spec.classes[idx], data.classes[class_id], data, spec.ruleset, spell_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/forget")
async def sheet_spell_forget(request: Request, character_id: str,
                             class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.forget(spec.classes[idx], spell_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/assign")
async def sheet_spell_assign(request: Request, character_id: str,
                             class_id: str = Form(...), level: int = Form(...),
                             spell_id: str = Form(...), reversed: str = Form("false")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    rev = reversed.lower() in ("true", "1", "on", "yes")
    try:
        spec.classes[idx] = spell_engine.assign_slot(
            spec.classes[idx], data.classes[class_id], data, level, spell_id, rev,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/cast")
async def sheet_spell_cast(request: Request, character_id: str,
                           class_id: str = Form(...), slot_index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.cast_slot(spec.classes[idx], slot_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/restore")
async def sheet_spell_restore(request: Request, character_id: str,
                              class_id: str = Form(...), slot_index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.restore_slot(spec.classes[idx], slot_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/clear")
async def sheet_spell_clear(request: Request, character_id: str,
                            class_id: str = Form(...), slot_index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.clear_slot(spec.classes[idx], slot_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Spell books & scrolls on the live sheet ────────────────────────────────

@router.post("/character/{character_id}/spell-sources/add")
async def sheet_spell_source_add(request: Request, character_id: str):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    form = await request.form()
    kind = form.get("kind", "scroll")
    caster_type = form.get("caster_type", "arcane")
    name = form.get("name", "")
    list_id = form.get("list_id", "") or None
    spell_ids = form.getlist("spell_ids")
    try:
        spec.spell_sources = spell_source_engine.add_spell_source(
            spec.spell_sources, kind, caster_type, spell_ids, data,
            name=name, list_id=list_id,
        )
    except (SpellSourceError, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spell-sources/remove")
async def sheet_spell_source_remove(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.spell_sources = spell_source_engine.remove_spell_source(
            spec.spell_sources, instance_id)
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spell-sources/cast")
async def sheet_spell_source_cast(request: Request, character_id: str,
                                  instance_id: str = Form(...),
                                  spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    source = next((s for s in spec.spell_sources if s.instance_id == instance_id), None)
    if source is None:
        raise HTTPException(400, f"No spell document with id {instance_id!r}")
    if not spell_source_engine.can_cast_scroll(source, spec, data):
        raise HTTPException(400, "This character cannot cast from that scroll")
    try:
        spec.spell_sources = spell_source_engine.cast_from_scroll(
            spec.spell_sources, instance_id, spell_id)
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spell-sources/copy")
async def sheet_spell_source_copy(request: Request, character_id: str,
                                  instance_id: str = Form(...),
                                  class_id: str = Form(...),
                                  spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    eff_int = effective_abilities(spec, data)[Ability.INT]
    try:
        entry, sources, _success = spell_source_engine.copy_spell(
            spec.classes[idx], data.classes[class_id], data, spec.ruleset,
            eff_int, spec.spell_sources, instance_id, spell_id,
        )
    except SpellSourceError as e:
        raise HTTPException(400, str(e))
    spec.classes[idx] = entry
    spec.spell_sources = sources
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Rest ──────────────────────────────────────────────────────────────────

def _apply_rest_mode(entry, mode: str):
    """Apply a rest spell-option to one class entry.

    restore → un-spend the existing loadout; clear → drop it; keep → unchanged.
    Non-casters have no slots, so every mode is a no-op for them."""
    if mode == "restore":
        return spell_engine.restore_all_slots(entry)
    if mode == "clear":
        return spell_engine.clear_all_slots(entry)
    if mode == "keep":
        return entry
    raise HTTPException(400, f"Unknown rest mode {mode!r}")


@router.post("/character/{character_id}/rest/night")
async def rest_night(request: Request, character_id: str, mode: str = Form("restore")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    if hp.is_dead(spec, data):
        raise HTTPException(400, "A dead character cannot rest")
    spec.classes = [_apply_rest_mode(e, mode) for e in spec.classes]
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/rest/full-day")
async def rest_full_day(request: Request, character_id: str,
                        mode: str = Form("restore"), heal_amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    if hp.is_dead(spec, data):
        raise HTTPException(400, "A dead character cannot rest")
    spec.classes = [_apply_rest_mode(e, mode) for e in spec.classes]
    try:
        spec.damage_taken = hp.apply_healing(spec, data, heal_amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Ammunition management on the live sheet ───────────────────────────────

@router.post("/character/{character_id}/ammo/add")
async def ammo_add(request: Request, character_id: str,
                   base_id: str = Form(...), enchantment_id: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.ammo = _add_free_ammo(spec.ammo, base_id,
                                   enchantment_id or None, request.app.state.game_data)
    except (_UnknownAmmo, _IncompatibleAmmo, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/adjust")
async def ammo_adjust(request: Request, character_id: str,
                      instance_id: str = Form(...), delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.ammo = _adjust_ammo(spec.ammo, instance_id, delta)
    except _UnknownAmmo as e:
        raise HTTPException(400, str(e))
    # drop any load pointing at a now-removed stack
    live = {s.instance_id for s in spec.ammo}
    spec.loaded_ammo = {k: v for k, v in spec.loaded_ammo.items() if v in live}
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/remove")
async def ammo_remove(request: Request, character_id: str,
                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.ammo = _remove_ammo(spec.ammo, instance_id)
    except _UnknownAmmo as e:
        raise HTTPException(400, str(e))
    live = {s.instance_id for s in spec.ammo}
    spec.loaded_ammo = {k: v for k, v in spec.loaded_ammo.items() if v in live}
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/load")
async def ammo_load(request: Request, character_id: str,
                    weapon_key: str = Form(...), instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec.loaded_ammo = _load_ammo(spec.loaded_ammo, weapon_key, instance_id)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/unload")
async def ammo_unload(request: Request, character_id: str,
                      weapon_key: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec.loaded_ammo = _unload_ammo(spec.loaded_ammo, weapon_key)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


def _truthy(value: str) -> bool:
    return str(value).lower() in ("1", "true", "on", "yes")


@router.post("/character/{character_id}/gems/add")
async def sheet_gem_add(request: Request, character_id: str):
    # Read form manually: the template sends two "value" fields (dropdown + custom
    # number).  Take the last non-empty one so the custom box overrides the dropdown
    # when filled, and the dropdown wins when the custom box is left blank.
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    raw_values = [v for v in form.getlist("value") if str(v).strip()]
    try:
        value = int(raw_values[-1]) if raw_values else 0
        count = int(form.get("count", 1) or 1)
        label = str(form.get("label", "") or "")
        spec.gems = valuables_engine.add_gem(spec.gems, value, count, label)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/adjust")
async def sheet_gem_adjust(request: Request, character_id: str,
                           instance_id: str = Form(...), delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.adjust_gem_count(spec.gems, instance_id, delta)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/sell")
async def sheet_gem_sell(request: Request, character_id: str,
                         instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems, spec.gold = valuables_engine.sell_gem(
            spec.gems, spec.gold, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/sell-all")
async def sheet_gem_sell_all(request: Request, character_id: str,
                             instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems, spec.gold = valuables_engine.sell_gem_all(
            spec.gems, spec.gold, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/remove")
async def sheet_gem_remove(request: Request, character_id: str,
                           instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.remove_gem(spec.gems, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/add")
async def sheet_jewellery_add(request: Request, character_id: str,
                              mode: str = Form("set"), value: int = Form(0),
                              damaged: str = Form(""), label: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    if mode == "random":
        value = valuables_engine.roll_jewellery_value()
    try:
        spec.jewellery = valuables_engine.add_jewellery(
            spec.jewellery, value, _truthy(damaged), label)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/toggle-damaged")
async def sheet_jewellery_toggle_damaged(request: Request, character_id: str,
                                         instance_id: str = Form(...),
                                         damaged: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery = valuables_engine.set_jewellery_damaged(
            spec.jewellery, instance_id, _truthy(damaged))
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/sell")
async def sheet_jewellery_sell(request: Request, character_id: str,
                               instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery, spec.gold = valuables_engine.sell_jewellery(
            spec.jewellery, spec.gold, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/remove")
async def sheet_jewellery_remove(request: Request, character_id: str,
                                 instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery = valuables_engine.remove_jewellery(
            spec.jewellery, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/possessions/add")
async def sheet_possession_add(request: Request, character_id: str,
                               text: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    spec.other_possessions = possessions_engine.add_possession(
        spec.other_possessions, text)
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/possessions/remove")
async def sheet_possession_remove(request: Request, character_id: str,
                                  index: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.other_possessions = possessions_engine.remove_possession(
            spec.other_possessions, index)
    except PossessionError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/notes/set")
async def sheet_notes_set(request: Request, character_id: str,
                          notes: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    spec.notes = notes
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
