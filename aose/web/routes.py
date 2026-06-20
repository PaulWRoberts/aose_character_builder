import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from aose.web.templating import make_templates

from aose.characters.storage import delete_character, list_character_ids, load_character, save_character, slugify, unique_character_id
from aose.models import CharacterSpec
from aose.engine import currency as _currency, dice, hp, spells as spell_engine
from aose.engine.currency import CurrencyError
from aose.engine.equip import WieldError, equip as _equip, unequip as _unequip
from aose.engine.enchant import _kind_of_instance as _enchanted_kind
from aose.engine.energy_drain import energy_drain as _energy_drain
from aose.engine.leveling import (
    grant_xp as _grant_xp,
    level_up as _level_up,
    roll_pending_hp as _roll_pending_hp,
    confirm_level_up as _confirm_level_up,
    cancel_pending_level_up as _cancel_pending_level_up,
)
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
    InsufficientFunds,
    InsufficientGold,
    UnknownItem,
    add_free as shop_add_free,
    add_free_container,
    buy_container,
    buy_item as shop_buy_item,
    inventory_view as shop_inventory_view,
    sell_container as shop_sell_container,
    sell_from_stash as shop_sell_from_stash,
    sell_item as shop_sell_item,
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
from aose.engine.features import one_handed_two_handed_weapons as _1h2h
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    base_weapon_id,
    shields_allowed,
    specialisation_allowed,
    two_weapon_eligible,
)
from aose.engine.level_choices import proficiency_capacity, talent_capacities
from aose.engine import spell_sources as spell_source_engine
from aose.engine.spell_sources import SpellSourceError
from aose.engine import valuables as valuables_engine
from aose.engine.valuables import ValuableError
from aose.engine import possessions as possessions_engine
from aose.engine.possessions import PossessionError
from aose.engine import companions as companions_engine
from aose.engine.companions import AnimalOverloaded, VehicleOverloaded
from aose.engine.sources import content_enabled
from aose.engine.innate import (
    InnateError, reset_innate, restore_innate, spend_innate,
)
from aose.models import Ability, Ammunition, Weapon
from aose.sheet.view import build_sheet, spell_source_add_options

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ---------------------------------------------------------------------------
# Carried-gp shims: bridge the old single-int gold API until all call sites
# are migrated to the CoinStack model.  Both helpers operate on the "carried"
# gp stack only — the shop-spendable balance.
# ---------------------------------------------------------------------------
from aose.models import CoinStack as _CoinStack
from aose.models.storage import StorageLocation as _SL
from pydantic import ValidationError as _ValidationError


def _loc(kind: str | None, id_: str | None) -> _SL:
    """Build a StorageLocation from form fields, mapping an invalid/empty kind to
    an HTTP 400 instead of letting Pydantic's ValidationError bubble up as a 500."""
    try:
        return _SL(kind=kind, id=id_)  # type: ignore[arg-type]
    except _ValidationError:
        raise HTTPException(400, f"invalid storage location {kind!r}")


def _get_gold(spec) -> int:
    """Return the count of carried gp (0 if none)."""
    for s in spec.coins:
        if s.denom == "gp" and s.location.kind == "carried":
            return s.count
    return 0


def _set_gold(spec, amount: int) -> None:
    """Replace (or create) the carried gp stack with ``amount``.
    Passing 0 removes the stack entirely."""
    carried = _SL(kind="carried")
    spec.coins = [s for s in spec.coins
                  if not (s.denom == "gp" and s.location == carried)]
    if amount > 0:
        spec.coins.append(_CoinStack(denom="gp", count=amount))
STATIC_DIR = Path(__file__).parent / "static"

templates = make_templates(str(TEMPLATES_DIR))

# Read print CSS once at import time so routes don't hit the filesystem per request.
_PRINT_CSS = (STATIC_DIR / "print.css").read_text(encoding="utf-8")


def _enchant_choices(game_data, ruleset=None):
    """Picker data: each enchantment with its compatible base items, sorted by kind then id."""
    from aose.engine.enchant import compatible_bases
    out = []
    for ench in sorted(game_data.enchantments.values(), key=lambda e: (e.kind, e.id)):
        if ruleset is not None and not content_enabled(ench.source, "magic_items", ruleset):
            continue
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
    characters = _character_summaries(request.state.characters_dir)
    return templates.TemplateResponse(
        request, "index.html", {"characters": characters}
    )


# ── Character sheet ────────────────────────────────────────────────────────

@router.get("/character/{character_id}", response_class=HTMLResponse)
async def character_sheet(request: Request, character_id: str):
    try:
        spec = load_character(character_id, request.state.characters_dir)
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
            "gold": _get_gold(spec),
            "gold_locked": True,
            "inventory_view": shop_inventory_view(
                spec.inventory, spec.stashed, spec.equipped,
                spec.containers, game_data,
                allowed_weapons=allowed_weapon_ids(classes, game_data, spec.ruleset),
                allowed_armor=allowed_armor_ids(classes, game_data),
                allow_shields=shields_allowed(classes),
                two_weapon=spec.ruleset.two_weapon_fighting,
                eligible=two_weapon_eligible(classes),
                gargantua_1h_2h=_1h2h(spec, game_data),
            ),
            "magic_items_view": [v for v in sheet.magic_items
                                 if v.instance_id not in {e.instance_id for e in spec.enchanted}],
            "enchanted_rows": [v for v in sheet.magic_items
                               if v.instance_id in {e.instance_id for e in spec.enchanted}],
            "magic_acquisition": True,
            "enchant_choices": _enchant_choices(game_data, spec.ruleset),
            "shop": shop_categories(game_data, spec.ruleset),
            "remove_modes": REMOVE_MODES,
            "target_url_prefix": f"/character/{character_id}/equipment",
            "ammo_rows": sheet.ammo,
            "ammo_load_options": sheet.ammo_load_options,
            "ammo_url_prefix": f"/character/{character_id}",
            "show_gold_reroll": False,
            "show_gold_grant": True,
            "gold_grant_url": f"/character/{character_id}/gold",
            "coins": sheet.coins,
            "coins_url_prefix": f"/character/{character_id}",
            "inv_move_groups": sheet.inventory_groups,
            "inv_move_url": f"/character/{character_id}/inventory/move-item",
            "spell_source_add_options": spell_source_add_options(game_data),
            # Equipment drawer tabs: Documents + Treasure (gated on presence)
            "spell_sources": sheet.spell_sources,
            "valuables": sheet.valuables,
        },
    )


# ── Delete character ───────────────────────────────────────────────────────

@router.post("/character/{character_id}/delete")
async def character_delete(request: Request, character_id: str):
    delete_character(character_id, request.state.characters_dir)
    return RedirectResponse("/", status_code=303)


# ── Print preview (browser print / Save as PDF) ────────────────────────────

@router.get("/character/{character_id}/print", response_class=HTMLResponse)
async def character_print(request: Request, character_id: str):
    """Return a standalone print-optimised HTML page.

    The page has ``onload="window.print()"`` so opening it in a browser
    immediately triggers the print dialog — choose *Save as PDF* there.
    """
    try:
        spec = load_character(character_id, request.state.characters_dir)
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
        spec = load_character(character_id, request.state.characters_dir)
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
        return load_character(character_id, request.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")


# ── Character export ───────────────────────────────────────────────────────

@router.get("/character/{character_id}/export")
async def character_export(request: Request, character_id: str):
    """Download character as JSON."""
    spec = _load_spec_or_404(request, character_id)
    headers = {"Content-Disposition": f'attachment; filename="{character_id}.json"'}
    return Response(
        content=json.dumps(spec.model_dump(mode="json"), indent=2),
        media_type="application/json",
        headers=headers,
    )


# ── Character import ──────────────────────────────────────────────────────

@router.post("/import")
async def character_import(request: Request, file: UploadFile = File(...)):
    """Upload and import a character from a JSON file."""
    raw = await file.read()
    try:
        spec = CharacterSpec.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid character file: {exc}")
    characters_dir = request.state.characters_dir
    cid = unique_character_id(slugify(spec.name), characters_dir)
    save_character(cid, spec, characters_dir)
    return RedirectResponse(url=f"/character/{cid}", status_code=303)


@router.post("/character/{character_id}/xp")
async def grant_xp(request: Request, character_id: str, amount: int = Form(...)):
    """Add or subtract XP.  Total XP is clamped at zero — leveling down is
    not modelled, so reducing XP below a class's threshold doesn't strip the
    level (the user can edit the JSON if they really need to)."""
    spec = _load_spec_or_404(request, character_id)
    _grant_xp(spec, request.app.state.game_data, amount)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gold")
async def grant_gold(request: Request, character_id: str, amount: int = Form(...)):
    """Add or subtract gold.  Clamped at zero — negative balances aren't a
    thing in OSE, even if the GM claws back some treasure."""
    spec = _load_spec_or_404(request, character_id)
    _set_gold(spec, max(0, _get_gold(spec) + amount))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/coins/add")
async def add_coins(request: Request, character_id: str):
    """Add coins of one denomination at a location, clamped at zero."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    denom = form.get("denom", "")
    if denom not in _currency.RATES:
        raise HTTPException(400, f"unknown denomination {denom!r}")
    loc_kind = form.get("loc_kind", "carried") or "carried"
    loc_id = form.get("loc_id") or None
    try:
        count = int(form.get("count", 0))
    except (ValueError, TypeError):
        raise HTTPException(400, "count must be an integer")
    loc = _loc(loc_kind, loc_id)
    if count > 0:
        _storage.add_coins(spec, denom, count, loc)
    elif count < 0:
        # Clamped removal: remove as many as available, never below 0
        remove_count = min(-count, sum(
            s.count for s in spec.coins if s.denom == denom and s.location == loc
        ))
        if remove_count > 0:
            _storage._take_coins(spec, denom, remove_count, loc)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/coins/convert")
async def convert_coins(request: Request, character_id: str):
    """Make change between two denominations at a specific location."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    loc_kind = form.get("loc_kind", "carried") or "carried"
    loc_id = form.get("loc_id") or None
    frm = form.get("frm") or form.get("from_denom", "")
    to = form.get("to") or form.get("to_denom", "")
    try:
        count = int(form.get("count", 0))
    except (ValueError, TypeError):
        raise HTTPException(400, "count must be an integer")
    loc = _loc(loc_kind, loc_id)
    try:
        _storage.convert_coins(spec, loc, frm, to, count)
    except (CurrencyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/move-item")
async def inventory_move_item(request: Request, character_id: str):
    """Move one copy of an item from src location to dest location."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    src = _loc(form.get("src_kind", "carried"), form.get("src_id") or None)
    dest = _loc(form.get("dest_kind", "carried"), form.get("dest_id") or None)
    try:
        _storage.move_item(spec, form["item_id"], src, dest)
    except (KeyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/move-container")
async def inventory_move_container(request: Request, character_id: str):
    """Re-home a container instance to a new location."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    dest = _loc(form.get("dest_kind", "carried"), form.get("dest_id") or None)
    try:
        _storage.move_container(spec, form["container_id"], dest)
    except (KeyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/move-coins")
async def inventory_move_coins(request: Request, character_id: str):
    """Move some coins of one denomination from src to dest."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    denom = form.get("denom", "")
    src = _loc(form.get("src_kind", "carried"), form.get("src_id") or None)
    dest = _loc(form.get("dest_kind", "stashed"), form.get("dest_id") or None)
    try:
        count = int(form.get("count", 0))
    except (ValueError, TypeError):
        raise HTTPException(400, "count must be an integer")
    try:
        _storage.move_coins(spec, denom, src, dest, count)
    except _storage.StorageError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/inventory/move-valuable")
async def inventory_move_valuable(request: Request, character_id: str):
    """Move a gem stack or jewellery piece to a new location."""
    from aose.engine import storage as _storage
    spec = _load_spec_or_404(request, character_id)
    form = await request.form()
    dest = _loc(form.get("dest_kind", "carried"), form.get("dest_id") or None)
    try:
        _storage.move_valuable(spec, form["instance_id"], dest)
    except (KeyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/carrying-treasure")
async def set_carrying_treasure(request: Request, character_id: str,
                                value: str = Form(...)):
    """Flip the basic-encumbrance carrying-treasure toggle."""
    spec = _load_spec_or_404(request, character_id)
    spec.carrying_treasure = value.lower() in ("true", "1", "on", "yes")
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/tailored")
async def set_armor_tailored(request: Request, character_id: str,
                             value: str = Form(...)):
    """Flip whether the equipped tailorable body armour is fitted to the wearer."""
    spec = _load_spec_or_404(request, character_id)
    spec.armor_tailored = value.lower() in ("true", "1", "on", "yes")
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/damage")
async def hp_damage(request: Request, character_id: str, amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.damage_taken = hp.apply_damage(spec, data, amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/heal")
async def hp_heal(request: Request, character_id: str, amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.damage_taken = hp.apply_healing(spec, data, amount)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/hp/set")
async def hp_set(request: Request, character_id: str, value: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    spec.damage_taken = hp.set_current_hp(spec, data, value)
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/proficiency/add")
async def add_proficiency(request: Request, character_id: str,
                          weapon_id: str = Form(...),
                          specialise: bool = Form(False)):
    data = request.app.state.game_data
    spec = _load_spec_or_404(request, character_id)
    cap = proficiency_capacity(spec, data)
    if cap is None or cap.remaining <= 0:
        raise HTTPException(400, "No weapon-proficiency slots remaining.")
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    allowed = allowed_weapon_ids(classes, data, spec.ruleset)
    item = data.items.get(weapon_id)
    if not isinstance(item, Weapon) or base_weapon_id(item) != weapon_id:
        raise HTTPException(400, "Pick a base weapon type.")
    if allowed != "all" and weapon_id not in allowed:
        raise HTTPException(400, "Weapon not allowed for this class.")
    if specialise:
        if not specialisation_allowed(classes):
            raise HTTPException(400, "This class cannot specialise.")
        if cap.remaining < 2 and weapon_id not in spec.weapon_proficiencies:
            raise HTTPException(400, "Specialising a new weapon needs 2 slots.")
    if weapon_id not in spec.weapon_proficiencies:
        spec.weapon_proficiencies.append(weapon_id)
    if specialise and weapon_id not in spec.weapon_specialisations:
        spec.weapon_specialisations.append(weapon_id)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/talent/add")
async def add_talent(request: Request, character_id: str,
                     group_id: str = Form(...), option_id: str = Form(...),
                     param: str = Form("")):
    data = request.app.state.game_data
    spec = _load_spec_or_404(request, character_id)
    caps = {c.group_id: c for c in talent_capacities(spec, data)}
    cap = caps.get(group_id)
    if cap is None or cap.remaining <= 0:
        raise HTTPException(400, "No talent selections remaining.")
    group = next(
        (g for e in spec.classes if (cls := data.classes.get(e.class_id))
         for g in cls.feature_choices if g.id == group_id),
        None,
    )
    if group is None:
        raise HTTPException(400, "Unknown talent group.")
    opt = next((o for o in group.options if o.id == option_id), None)
    if opt is None:
        raise HTTPException(400, "Unknown talent.")
    if opt.excluded_when_rule and getattr(spec.ruleset, opt.excluded_when_rule, False):
        raise HTTPException(400, "That talent is unavailable under the current rules.")
    chosen = list(spec.feature_choices.get(group_id, []))
    if option_id in chosen:
        raise HTTPException(400, "Talent already taken.")
    raw = (param or "").strip()
    if opt.param is not None and not raw:
        raise HTTPException(400, f"{opt.name}: choose {opt.param.label}.")
    chosen.append(option_id)
    spec.feature_choices[group_id] = chosen
    if opt.param is not None:
        if opt.param.kind == "weapon":
            if raw not in spec.weapon_specialisations:
                spec.weapon_specialisations.append(raw)
        else:
            spec.choice_params[option_id] = raw
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/level-up/{class_id}/roll")
async def level_up_roll(request: Request, character_id: str, class_id: str):
    """Roll the new level's hit die into ``spec.pending_level_up[class_id]``
    without advancing the class.  400 if the roll is rejected (XP short, at
    max, at/beyond name level, or Strict-Mode lock)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _roll_pending_hp(spec, request.app.state.game_data, class_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}#modal-levelup-{class_id}", status_code=303)


@router.post("/character/{character_id}/level-up/{class_id}/confirm")
async def level_up_confirm(request: Request, character_id: str, class_id: str):
    """Commit a pending level-up: apply the pending HP roll (sub-name-level)
    or just bump the level (at/beyond name level)."""
    spec = _load_spec_or_404(request, character_id)
    try:
        _confirm_level_up(spec, request.app.state.game_data, class_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/level-up/{class_id}/cancel")
async def level_up_cancel(request: Request, character_id: str, class_id: str):
    """Idempotently clear any pending HP roll for this class."""
    spec = _load_spec_or_404(request, character_id)
    _cancel_pending_level_up(spec, class_id)
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Equipment management on the live sheet ────────────────────────────────

@router.post("/character/{character_id}/equipment/buy")
async def equipment_buy(request: Request, character_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    game_data = request.app.state.game_data
    item = game_data.items.get(item_id)
    from aose.models import Animal, Container, Vehicle
    try:
        if isinstance(item, Ammunition):
            spec.ammo, new_gold = _buy_ammo(spec.ammo, _get_gold(spec), item_id, game_data)
            _set_gold(spec, new_gold)
        elif isinstance(item, Container):
            spec.containers, new_gold = buy_container(
                spec.containers, _get_gold(spec), item_id, game_data,
            )
            _set_gold(spec, new_gold)
        elif isinstance(item, Animal):
            # Animals are roster instances, not carried inventory.
            spec.animals, new_gold = companions_engine.buy_animal(
                spec.animals, _get_gold(spec), item_id, game_data,
            )
            _set_gold(spec, new_gold)
        elif isinstance(item, Vehicle):
            # Vehicles are roster instances; hull_max resolves at purchase.
            spec.vehicles, new_gold = companions_engine.buy_vehicle(
                spec.vehicles, _get_gold(spec), item_id, game_data,
            )
            _set_gold(spec, new_gold)
        else:
            shop_buy_item(spec, item_id, game_data)
    except (UnknownItem, InsufficientFunds, InsufficientGold, _AmmoInsufficientGold, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/equip")
async def equipment_equip(request: Request, character_id: str,
                          item_id: str = Form(...),
                          slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
    try:
        spec.equipped = _equip(
            item_id,
            inventory=spec.inventory, equipped=spec.equipped,
            enchanted=spec.enchanted, data=data,
            slot=slot,
            two_weapon=spec.ruleset.two_weapon_fighting,
            eligible=two_weapon_eligible(classes),
            gargantua_1h_2h=_1h2h(spec, data),
            allowed_weapons=allowed_weapon_ids(classes, data, spec.ruleset),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
        )
    except (ValueError, WieldError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip")
async def equipment_unequip(request: Request, character_id: str,
                            item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.equipped = _unequip(item_id, equipped=spec.equipped)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
            shop_sell_from_stash(spec, item_id, mode, game_data)
        else:
            shop_sell_item(spec, item_id, mode, game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/stash")
async def equipment_stash(request: Request, character_id: str,
                          item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.equipped = shop_stash(
            spec.inventory, spec.stashed, spec.equipped,
            item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/stow")
async def equipment_stow(request: Request, character_id: str,
                         instance_id: str = Form(...),
                         item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.inventory, spec.stashed, spec.containers = shop_stow(
            spec.inventory, spec.stashed, spec.containers,
            spec.equipped,
            instance_id, item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/stash-container")
async def equipment_stash_container(request: Request, character_id: str,
                                    instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers = shop_stash_container(spec.containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unstash-container")
async def equipment_unstash_container(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.containers = shop_unstash_container(spec.containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-container")
async def equipment_remove_container(request: Request, character_id: str,
                                     instance_id: str = Form(...),
                                     mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        shop_sell_container(spec, instance_id, mode, request.app.state.game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-magic")
async def equipment_unequip_magic(request: Request, character_id: str,
                                  instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _unequip_magic(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/use-charge")
async def equipment_use_charge(request: Request, character_id: str,
                               instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _use_charge(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/reset-charges")
async def equipment_reset_charges(request: Request, character_id: str,
                                  instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items = _reset_charges(spec.magic_items, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-magic")
async def equipment_remove_magic(request: Request, character_id: str,
                                 instance_id: str = Form(...),
                                 mode: str = Form("drop")):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.magic_items, new_gold = _remove_magic(
            spec.magic_items, _get_gold(spec), instance_id, mode, request.app.state.game_data,
        )
        _set_gold(spec, new_gold)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/equip-enchanted")
async def equipment_equip_enchanted(request: Request, character_id: str,
                                    instance_id: str = Form(...),
                                    slot: str | None = Form(None)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    inst = next((i for i in spec.enchanted if i.instance_id == instance_id), None)
    if inst is None:
        raise HTTPException(400, f"No enchanted instance {instance_id!r}")
    kind = _enchanted_kind(inst, data)
    try:
        if kind == "armor":
            spec.enchanted = _equip_enchanted(spec.enchanted, instance_id)
        else:
            classes = [data.classes[e.class_id] for e in spec.classes if e.class_id in data.classes]
            spec.equipped = _equip(
                instance_id,
                inventory=spec.inventory, equipped=spec.equipped,
                enchanted=spec.enchanted, data=data,
                slot=slot,
                two_weapon=spec.ruleset.two_weapon_fighting,
                eligible=two_weapon_eligible(classes),
                gargantua_1h_2h=_1h2h(spec, data),
                allow_shields=shields_allowed(classes),
            )
    except (ValueError, WieldError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/unequip-enchanted")
async def equipment_unequip_enchanted(request: Request, character_id: str,
                                      instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    inst = next((i for i in spec.enchanted if i.instance_id == instance_id), None)
    if inst is None:
        raise HTTPException(400, f"No enchanted instance {instance_id!r}")
    kind = _enchanted_kind(inst, data)
    try:
        if kind == "armor":
            spec.enchanted = _unequip_enchanted(spec.enchanted, instance_id)
        else:
            spec.equipped = _unequip(instance_id, equipped=spec.equipped)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted/use-charge")
async def equipment_enchanted_use_charge(request: Request, character_id: str,
                                         instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _use_ench_charge(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/enchanted/reset-charges")
async def equipment_enchanted_reset_charges(request: Request, character_id: str,
                                            instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _reset_ench_charges(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/equipment/remove-enchanted")
async def equipment_remove_enchanted(request: Request, character_id: str,
                                     instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.enchanted = _remove_enchanted(spec.enchanted, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
            ruleset=spec.ruleset,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Mental powers on the live sheet ────────────────────────────────────────

@router.post("/character/{character_id}/powers/learn")
async def sheet_power_learn(request: Request, character_id: str,
                            class_id: str = Form(...), power_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.learn(
            spec.classes[idx], data.classes[class_id], data, spec.ruleset, power_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/powers/forget")
async def sheet_power_forget(request: Request, character_id: str,
                             class_id: str = Form(...), power_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = spell_engine.forget(spec.classes[idx], power_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


def _power_pool_op(request: Request, character_id: str, class_id: str, op):
    spec = _load_spec_or_404(request, character_id)
    idx = _find_class_entry(spec, class_id)
    try:
        spec.classes[idx] = op(spec.classes[idx])
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/powers/spend")
async def sheet_power_spend(request: Request, character_id: str,
                            class_id: str = Form(...)):
    return _power_pool_op(request, character_id, class_id, spell_engine.spend_power)


@router.post("/character/{character_id}/powers/restore")
async def sheet_power_restore(request: Request, character_id: str,
                              class_id: str = Form(...)):
    return _power_pool_op(request, character_id, class_id, spell_engine.restore_power)


@router.post("/character/{character_id}/powers/reset")
async def sheet_power_reset(request: Request, character_id: str,
                            class_id: str = Form(...)):
    return _power_pool_op(request, character_id, class_id, spell_engine.reset_powers)


# ── Innate daily-use abilities ─────────────────────────────────────────────

@router.post("/character/{character_id}/innate/spend")
async def sheet_innate_spend(request: Request, character_id: str,
                             ability_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec = spend_innate(spec, ability_id, request.app.state.game_data)
    except InnateError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/innate/restore")
async def sheet_innate_restore(request: Request, character_id: str,
                               ability_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec = restore_innate(spec, ability_id)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/innate/reset")
async def sheet_innate_reset(request: Request, character_id: str):
    spec = _load_spec_or_404(request, character_id)
    spec = reset_innate(spec)
    save_character(character_id, spec, request.state.characters_dir)
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
    # list_id pins membership to one list — only meaningful for a spellbook. A
    # scroll spans a whole magic type (arcane/divine), so its hidden list <select>
    # value must be ignored; honouring it wrongly rejects off-list spells.
    list_id = (form.get("list_id", "") or None) if kind == "spellbook" else None
    spell_ids = form.getlist("spell_ids")
    try:
        spec.spell_sources = spell_source_engine.add_spell_source(
            spec.spell_sources, kind, caster_type, spell_ids, data,
            name=name, list_id=list_id,
        )
    except (SpellSourceError, ValueError) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Rest ──────────────────────────────────────────────────────────────────

def _apply_rest_mode(entry, mode: str):
    """Apply a rest spell-option to one class entry, and refresh the mental-power
    daily pool (a new day).  Non-casters/non-mental: pool reset is a no-op."""
    entry = spell_engine.reset_powers(entry)
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
    spec = reset_innate(spec)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/rest/full-day/roll")
async def rest_full_day_roll(request: Request, character_id: str):
    spec = _load_spec_or_404(request, character_id)
    if hp.is_dead(spec, request.app.state.game_data):
        raise HTTPException(400, "A dead character cannot rest")
    if spec.ruleset.strict_mode and spec.pending_rest_heal is not None:
        raise HTTPException(400, "Healing roll is already locked (Strict Mode)")
    spec.pending_rest_heal = dice.roll("1d3")
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}#modal-rest", status_code=303)


@router.post("/character/{character_id}/rest/full-day")
async def rest_full_day(request: Request, character_id: str,
                        mode: str = Form("restore")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    if hp.is_dead(spec, data):
        raise HTTPException(400, "A dead character cannot rest")
    if spec.pending_rest_heal is None:
        raise HTTPException(400, "Roll the healing die first")
    spec.classes = [_apply_rest_mode(e, mode) for e in spec.classes]
    spec = reset_innate(spec)
    try:
        spec.damage_taken = hp.apply_healing(spec, data, spec.pending_rest_heal)
    except ValueError as e:
        raise HTTPException(400, str(e))
    spec.pending_rest_heal = None
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/load")
async def ammo_load(request: Request, character_id: str,
                    weapon_key: str = Form(...), instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec.loaded_ammo = _load_ammo(spec.loaded_ammo, weapon_key, instance_id)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/ammo/unload")
async def ammo_unload(request: Request, character_id: str,
                      weapon_key: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    spec.loaded_ammo = _unload_ammo(spec.loaded_ammo, weapon_key)
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/adjust")
async def sheet_gem_adjust(request: Request, character_id: str,
                           instance_id: str = Form(...), delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.adjust_gem_count(spec.gems, instance_id, delta)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/sell")
async def sheet_gem_sell(request: Request, character_id: str,
                         instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems, new_gold = valuables_engine.sell_gem(
            spec.gems, _get_gold(spec), instance_id)
        _set_gold(spec, new_gold)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/sell-all")
async def sheet_gem_sell_all(request: Request, character_id: str,
                             instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems, new_gold = valuables_engine.sell_gem_all(
            spec.gems, _get_gold(spec), instance_id)
        _set_gold(spec, new_gold)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/gems/remove")
async def sheet_gem_remove(request: Request, character_id: str,
                           instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.gems = valuables_engine.remove_gem(spec.gems, instance_id)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/jewellery/sell")
async def sheet_jewellery_sell(request: Request, character_id: str,
                               instance_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    try:
        spec.jewellery, new_gold = valuables_engine.sell_jewellery(
            spec.jewellery, _get_gold(spec), instance_id)
        _set_gold(spec, new_gold)
    except ValuableError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/possessions/add")
async def sheet_possession_add(request: Request, character_id: str,
                               text: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    spec.other_possessions = possessions_engine.add_possession(
        spec.other_possessions, text)
    save_character(character_id, spec, request.state.characters_dir)
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
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/notes/set")
async def sheet_notes_set(request: Request, character_id: str,
                          notes: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    spec.notes = notes
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Companions & Holdings: animals ─────────────────────────────────────────

@router.post("/character/{character_id}/animal/buy")
async def animal_buy(request: Request, character_id: str, item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.animals, new_gold = companions_engine.buy_animal(
            spec.animals, _get_gold(spec), item_id, data)
        _set_gold(spec, new_gold)
    except (ValueError,) as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/remove")
async def animal_remove(request: Request, character_id: str,
                        instance_id: str = Form(...), mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.animals, new_gold = companions_engine.remove_animal(
            spec.animals, _get_gold(spec), instance_id, mode, data)
        _set_gold(spec, new_gold)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/rename")
async def animal_rename(request: Request, character_id: str, instance_id: str,
                        name: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    for i, a in enumerate(spec.animals):
        if a.instance_id == instance_id:
            spec.animals[i] = a.model_copy(update={"name": name})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/hp")
async def animal_hp(request: Request, character_id: str, instance_id: str,
                    delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for i, a in enumerate(spec.animals):
        if a.instance_id == instance_id:
            catalog = data.items.get(a.catalog_id)
            cap = catalog.hp if catalog else 0
            new_dmg = min(max(0, a.hp_damage - delta), cap)
            spec.animals[i] = a.model_copy(update={"hp_damage": new_dmg})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/armor")
async def animal_armor(request: Request, character_id: str, instance_id: str,
                       armor_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        if armor_id == "":
            spec.inventory, spec.animals = companions_engine.clear_armor(
                spec.inventory, spec.animals, instance_id, data)
        else:
            spec.inventory, spec.animals = companions_engine.assign_armor(
                spec.inventory, spec.animals, instance_id, armor_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/load")
async def animal_load(request: Request, character_id: str, instance_id: str,
                      item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.animals = companions_engine.load_onto_animal(
            spec.inventory, spec.animals, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/animal/{instance_id}/unload")
async def animal_unload(request: Request, character_id: str, instance_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.animals = companions_engine.unload_from_animal(
            spec.inventory, spec.animals, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Companions & Holdings: vehicles ────────────────────────────────────────

@router.post("/character/{character_id}/vehicle/buy")
async def vehicle_buy(request: Request, character_id: str, item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.vehicles, new_gold = companions_engine.buy_vehicle(
            spec.vehicles, _get_gold(spec), item_id, data)
        _set_gold(spec, new_gold)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/remove")
async def vehicle_remove(request: Request, character_id: str,
                         instance_id: str = Form(...), mode: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.vehicles, new_gold = companions_engine.remove_vehicle(
            spec.vehicles, _get_gold(spec), instance_id, mode, data)
        _set_gold(spec, new_gold)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/rename")
async def vehicle_rename(request: Request, character_id: str, instance_id: str,
                         name: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    for i, v in enumerate(spec.vehicles):
        if v.instance_id == instance_id:
            spec.vehicles[i] = v.model_copy(update={"name": name})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/hull")
async def vehicle_hull(request: Request, character_id: str, instance_id: str,
                       delta: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    for i, v in enumerate(spec.vehicles):
        if v.instance_id == instance_id:
            new_dmg = min(max(0, v.hull_damage - delta), v.hull_max)
            spec.vehicles[i] = v.model_copy(update={"hull_damage": new_dmg})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/extra-animals")
async def vehicle_extra_animals(request: Request, character_id: str,
                                instance_id: str, on: bool = Form(False)):
    spec = _load_spec_or_404(request, character_id)
    for i, v in enumerate(spec.vehicles):
        if v.instance_id == instance_id:
            spec.vehicles[i] = v.model_copy(update={"extra_animals": on})
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/load")
async def vehicle_load(request: Request, character_id: str, instance_id: str,
                       item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.vehicles = companions_engine.load_onto_vehicle(
            spec.inventory, spec.vehicles, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/vehicle/{instance_id}/unload")
async def vehicle_unload(request: Request, character_id: str, instance_id: str,
                         item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        spec.inventory, spec.vehicles = companions_engine.unload_from_vehicle(
            spec.inventory, spec.vehicles, instance_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


# ── Retainer routes ────────────────────────────────────────────────────────

from aose.engine import retainers as retainers_engine


@router.post("/character/{character_id}/retainer/add")
async def retainer_add(request: Request, character_id: str,
                       name: str = Form(...), class_id: str = Form(...),
                       level: int = Form(1), race_id: str = Form("human"),
                       alignment: str = Form("neutral")):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    pc_level = max((e.level for e in spec.classes), default=1)
    if class_id != "normal_human" and level > pc_level:
        raise HTTPException(400, "A retainer may not exceed your level")
    try:
        ret = retainers_engine.generate_retainer(
            name=name, class_ids=[class_id], level=level, race_id=race_id,
            alignment=alignment, hiring_spec=spec, data=data)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    spec.retainers.append(ret)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/remove")
async def retainer_remove(request: Request, character_id: str, retainer_id: str):
    spec = _load_spec_or_404(request, character_id)
    spec.retainers = [r for r in spec.retainers if r.id != retainer_id]
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/loyalty")
async def retainer_loyalty(request: Request, character_id: str, retainer_id: str,
                           value: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    for r in spec.retainers:
        if r.id == retainer_id:
            r.loyalty = value
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/role")
async def retainer_role(request: Request, character_id: str, retainer_id: str,
                        role: str = Form("")):
    spec = _load_spec_or_404(request, character_id)
    for r in spec.retainers:
        if r.id == retainer_id:
            r.role = role
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/xp")
async def retainer_xp(request: Request, character_id: str, retainer_id: str,
                      amount: int = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for r in spec.retainers:
        if r.id == retainer_id:
            retainers_engine.grant_retainer_xp(r, data, amount)
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/levelup")
async def retainer_levelup(request: Request, character_id: str, retainer_id: str,
                           class_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for r in spec.retainers:
        if r.id == retainer_id:
            try:
                _level_up(r.spec, data, class_id)
            except ValueError as e:
                raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/promote")
async def retainer_promote(request: Request, character_id: str, retainer_id: str,
                           class_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    for r in spec.retainers:
        if r.id == retainer_id:
            try:
                retainers_engine.promote_normal_human(r, class_id, data)
            except ValueError as e:
                raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/give")
async def retainer_give(request: Request, character_id: str, retainer_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        retainers_engine.transfer_to_retainer(spec, retainer_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)


@router.post("/character/{character_id}/retainer/{retainer_id}/take")
async def retainer_take(request: Request, character_id: str, retainer_id: str,
                        item_id: str = Form(...)):
    spec = _load_spec_or_404(request, character_id)
    data = request.app.state.game_data
    try:
        retainers_engine.transfer_to_pc(spec, retainer_id, item_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_character(character_id, spec, request.state.characters_dir)
    return RedirectResponse(f"/character/{character_id}", status_code=303)
