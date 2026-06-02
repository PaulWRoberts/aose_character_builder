from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aose.characters.storage import list_character_ids, load_character, save_character
from aose.engine import hp, spells as spell_engine
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.leveling import grant_xp as _grant_xp, level_up as _level_up
from aose.engine.magic import (
    NoCharges,
    NotEquippable,
    UnknownMagicItem,
    add_free_magic_item,
    equip_magic as _equip_magic,
    needs_instance,
    remove_magic as _remove_magic,
    reset_charges as _reset_charges,
    set_magic_note as _set_magic_note,
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
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    shields_allowed,
)
from aose.sheet.view import build_sheet
from aose.web.move_dispatch import dispatch_move

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Read print CSS once at import time so routes don't hit the filesystem per request.
_PRINT_CSS = (STATIC_DIR / "print.css").read_text(encoding="utf-8")


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
                allowed_weapons=allowed_weapon_ids(classes, game_data),
                allowed_armor=allowed_armor_ids(classes, game_data),
                allow_shields=shields_allowed(classes),
            ),
            "magic_items_view": sheet.magic_items,
            "shop": shop_categories(game_data),
            "remove_modes": REMOVE_MODES,
            "target_url_prefix": f"/character/{character_id}/equipment",
            "show_gold_reroll": False,
            "show_gold_grant": True,
            "gold_grant_url": f"/character/{character_id}/gold",
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


# ── Equipment management on the live sheet ────────────────────────────────

@router.post("/character/{character_id}/equipment/buy")
async def equipment_buy(request: Request, character_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            spec.containers, spec.gold = buy_container(
                spec.containers, spec.gold, item_id, game_data,
            )
        else:
            new_inventory, new_gold = shop_buy(spec.inventory, spec.gold, item_id, game_data)
            spec.inventory = new_inventory
            spec.gold = new_gold
    except (UnknownItem, InsufficientGold, ValueError) as e:
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
        if needs_instance(item):
            spec.magic_items = add_free_magic_item(spec.magic_items, item_id, game_data)
        elif isinstance(item, Container):
            spec.containers = add_free_container(spec.containers, item_id, game_data)
        else:
            spec.inventory = shop_add_free(spec.inventory, item_id, game_data)
    except (UnknownItem, UnknownMagicItem, ValueError) as e:
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
            allowed_weapons=allowed_weapon_ids(classes, data),
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


@router.post("/character/{character_id}/equipment/move")
async def equipment_move(request: Request, character_id: str,
                         source: str = Form(...),
                         target: str = Form(...),
                         item_id: str = Form(""),
                         instance_id: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    classes = [game_data.classes[e.class_id] for e in spec.classes
               if e.class_id in game_data.classes]
    try:
        dispatch_move(spec, source, target, item_id, instance_id, game_data,
                      allowed_weapons=allowed_weapon_ids(classes, game_data),
                      allowed_armor=allowed_armor_ids(classes, game_data),
                      allow_shields=shields_allowed(classes))
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


@router.post("/character/{character_id}/spells/prepare")
async def sheet_spell_prepare(request: Request, character_id: str,
                              class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.prepare(
            spec.classes[idx], data.classes[class_id], data, spell_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/spells/unprepare")
async def sheet_spell_unprepare(request: Request, character_id: str,
                                class_id: str = Form(...), spell_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.unprepare(spec.classes[idx], spell_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
