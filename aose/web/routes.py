from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aose.characters.storage import list_character_ids, load_character, save_character
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.leveling import level_up as _level_up
from aose.engine.shop import (
    REMOVE_MODES,
    InsufficientGold,
    UnknownItem,
    add_free as shop_add_free,
    buy as shop_buy,
    inventory_view as shop_inventory_view,
    remove as shop_remove,
    remove_from_stash as shop_remove_from_stash,
    shop_categories,
    stash as shop_stash,
    unstash as shop_unstash,
)
from aose.sheet.view import build_sheet

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
    return templates.TemplateResponse(
        request, "sheet.html", {
            "sheet": sheet,
            "character_id": character_id,
            # Equipment partial context (sheet-side: no starting-gold reroll).
            "gold": spec.gold,
            "gold_locked": True,
            "inventory_view": shop_inventory_view(
                spec.inventory, spec.stashed, spec.equipped, spec.equipped_weapons, game_data,
            ),
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
    spec.xp = max(0, spec.xp + amount)
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
    try:
        new_inventory, new_gold = shop_buy(spec.inventory, spec.gold, item_id, game_data)
    except (UnknownItem, InsufficientGold) as e:
        raise HTTPException(400, str(e))
    spec.inventory = new_inventory
    spec.gold = new_gold
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/add")
async def equipment_add(request: Request, character_id: str,
                        item_id: str = Form(...)):
    """Add an item to inventory without spending gold — covers GM-given gear,
    found loot, and similar off-ledger acquisitions."""
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory = shop_add_free(spec.inventory, item_id, request.app.state.game_data)
    except UnknownItem as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.app.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/equip")
async def equipment_equip(request: Request, character_id: str,
                          item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.equipped, spec.equipped_weapons = _equip(
            spec.inventory, spec.equipped, spec.equipped_weapons,
            item_id, request.app.state.game_data,
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
