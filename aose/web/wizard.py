from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aose.characters import (
    delete_draft,
    load_draft,
    load_settings,
    new_draft_id,
    save_character,
    save_draft,
    slugify,
    unique_character_id,
)
from aose.engine.ability_mods import ability_modifier
from aose.engine.dice import roll_3d6_in_order, roll_hp
from aose.models import Ability, CharacterSpec, ClassEntry, RuleSet

router = APIRouter(prefix="/wizard")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

WIZARD_STEPS = ["abilities", "race", "class", "alignment", "hp", "review"]
STEP_LABELS = {
    "abilities": "Abilities",
    "race": "Race",
    "class": "Class",
    "alignment": "Alignment",
    "hp": "Hit Points",
    "review": "Review",
}
ABILITY_ORDER = [Ability.STR, Ability.INT, Ability.WIS, Ability.DEX, Ability.CON, Ability.CHA]
ALIGNMENT_LABELS = {"law": "Lawful", "neutral": "Neutral", "chaos": "Chaotic"}


def _drafts_dir(request: Request) -> Path:
    return request.app.state.drafts_dir


def _characters_dir(request: Request) -> Path:
    return request.app.state.characters_dir


def _load(request: Request, draft_id: str) -> dict[str, Any]:
    try:
        return load_draft(draft_id, _drafts_dir(request))
    except FileNotFoundError:
        raise HTTPException(404, f"Draft '{draft_id}' not found")


def _next_incomplete_step(draft: dict[str, Any]) -> str:
    if "name" not in draft:
        return "abilities"
    if "race_id" not in draft:
        return "race"
    if "class_id" not in draft:
        return "class"
    if "alignment" not in draft:
        return "alignment"
    if "hp_roll" not in draft:
        return "hp"
    return "review"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _base_context(request: Request, draft_id: str, draft: dict, current_step: str) -> dict:
    current_index = WIZARD_STEPS.index(current_step)
    return {
        "draft_id": draft_id,
        "draft": draft,
        "current_step": current_step,
        "current_step_index": current_index,
        "wizard_steps": WIZARD_STEPS,
        "step_labels": STEP_LABELS,
    }


def _gate(draft: dict, required_step: str, draft_id: str) -> RedirectResponse | None:
    """Redirect to the next incomplete step if the user is past their progress."""
    next_step = _next_incomplete_step(draft)
    if WIZARD_STEPS.index(required_step) > WIZARD_STEPS.index(next_step):
        return _redirect(f"/wizard/{draft_id}/{next_step}")
    return None


@router.get("/new")
async def new_wizard(request: Request):
    draft_id = new_draft_id()
    abilities = dict(zip([a.value for a in ABILITY_ORDER], roll_3d6_in_order()))
    ruleset = load_settings(request.app.state.settings_path)
    save_draft(
        draft_id,
        {"abilities": abilities, "ruleset": ruleset.model_dump()},
        _drafts_dir(request),
    )
    return _redirect(f"/wizard/{draft_id}/abilities")


@router.get("/{draft_id}/abilities", response_class=HTMLResponse)
async def get_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ability_rows = [
        {
            "name": ab.value,
            "score": draft["abilities"][ab.value],
            "modifier": ability_modifier(draft["abilities"][ab.value]),
        }
        for ab in ABILITY_ORDER
    ]
    ctx = _base_context(request, draft_id, draft, "abilities")
    ctx["ability_rows"] = ability_rows
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/reroll")
async def post_reroll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    draft["abilities"] = dict(zip([a.value for a in ABILITY_ORDER], roll_3d6_in_order()))
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/abilities")


@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str, name: str = Form(...)):
    draft = _load(request, draft_id)
    if not name.strip():
        raise HTTPException(400, "Name required")
    draft["name"] = name.strip()
    # Invalidate downstream choices that may no longer be valid
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/race")


def _meets_ability_requirements(reqs: dict[Ability, int], abilities: dict[str, int]) -> bool:
    return all(abilities.get(ab.value, 0) >= score for ab, score in reqs.items())


@router.get("/{draft_id}/race", response_class=HTMLResponse)
async def get_race(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "race", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    abilities = draft["abilities"]
    races = []
    for race in sorted(data.races.values(), key=lambda r: r.name):
        races.append({
            "id": race.id,
            "name": race.name,
            "infravision": race.infravision,
            "base_movement": race.base_movement,
            "requirements": {ab.value: v for ab, v in race.ability_requirements.items()},
            "languages": race.languages,
            "meets_requirements": _meets_ability_requirements(race.ability_requirements, abilities),
            "selected": draft.get("race_id") == race.id,
        })
    ctx = _base_context(request, draft_id, draft, "race")
    ctx["races"] = races
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/race")
async def post_race(request: Request, draft_id: str, race_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    if race_id not in data.races:
        raise HTTPException(400, f"Unknown race '{race_id}'")
    race = data.races[race_id]
    if not _meets_ability_requirements(race.ability_requirements, draft["abilities"]):
        raise HTTPException(400, f"Abilities do not meet {race.name} requirements")
    if draft.get("race_id") != race_id:
        # Race changed — class might no longer be valid; clear it
        draft.pop("class_id", None)
    draft["race_id"] = race_id
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class")


def _class_allowed_for_race(class_id: str, race) -> bool:
    if not race.allowed_classes:
        return True
    return class_id in race.allowed_classes


@router.get("/{draft_id}/class", response_class=HTMLResponse)
async def get_class(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "class", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    race = data.races[draft["race_id"]]
    abilities = draft["abilities"]
    classes = []
    for cls in sorted(data.classes.values(), key=lambda c: c.name):
        if cls.race_locked:
            continue  # race-as-class entries hidden in split mode (default)
        allowed_by_race = _class_allowed_for_race(cls.id, race)
        meets_abilities = _meets_ability_requirements(cls.ability_requirements, abilities)
        level_cap = race.class_level_caps.get(cls.id)
        classes.append({
            "id": cls.id,
            "name": cls.name,
            "hit_die": cls.hit_die,
            "prime_requisites": [a.value for a in cls.prime_requisites],
            "level_cap": level_cap,
            "allowed_by_race": allowed_by_race,
            "meets_abilities": meets_abilities,
            "available": allowed_by_race and meets_abilities,
            "selected": draft.get("class_id") == cls.id,
        })
    ctx = _base_context(request, draft_id, draft, "class")
    ctx["classes"] = classes
    ctx["race_name"] = race.name
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/class")
async def post_class(request: Request, draft_id: str, class_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    if class_id not in data.classes:
        raise HTTPException(400, f"Unknown class '{class_id}'")
    cls = data.classes[class_id]
    race = data.races[draft["race_id"]]
    if not _class_allowed_for_race(class_id, race):
        raise HTTPException(400, f"{race.name} cannot be a {cls.name}")
    if not _meets_ability_requirements(cls.ability_requirements, draft["abilities"]):
        raise HTTPException(400, f"Abilities do not meet {cls.name} requirements")
    if draft.get("class_id") != class_id:
        draft.pop("hp_roll", None)
    draft["class_id"] = class_id
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/alignment")


@router.get("/{draft_id}/alignment", response_class=HTMLResponse)
async def get_alignment(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "alignment", draft_id)
    if redirect:
        return redirect
    ctx = _base_context(request, draft_id, draft, "alignment")
    ctx["alignments"] = [
        {"id": "law", "label": "Lawful"},
        {"id": "neutral", "label": "Neutral"},
        {"id": "chaos", "label": "Chaotic"},
    ]
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/alignment")
async def post_alignment(request: Request, draft_id: str, alignment: str = Form(...)):
    if alignment not in ("law", "neutral", "chaos"):
        raise HTTPException(400, "Invalid alignment")
    draft = _load(request, draft_id)
    draft["alignment"] = alignment
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/hp")


@router.get("/{draft_id}/hp", response_class=HTMLResponse)
async def get_hp(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "hp", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    cls = data.classes[draft["class_id"]]
    ruleset = RuleSet(**draft.get("ruleset", {}))

    # Max HP at L1 is deterministic — auto-populate so the user just clicks Next.
    if ruleset.max_hp_at_l1 and "hp_roll" not in draft:
        draft["hp_roll"] = roll_hp(cls.hit_die, take_max=True)
        save_draft(draft_id, draft, _drafts_dir(request))

    con_mod = ability_modifier(draft["abilities"]["CON"])
    total = None
    if "hp_roll" in draft:
        total = max(1, draft["hp_roll"] + con_mod)
    ctx = _base_context(request, draft_id, draft, "hp")
    ctx.update({
        "class_name": cls.name,
        "hit_die": cls.hit_die,
        "con_mod": con_mod,
        "total_hp": total,
        "max_hp_rule": ruleset.max_hp_at_l1,
        "reroll_rule": ruleset.reroll_1s_2s_hp_l1,
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    cls = data.classes[draft["class_id"]]
    ruleset = RuleSet(**draft.get("ruleset", {}))
    draft["hp_roll"] = roll_hp(
        cls.hit_die,
        take_max=ruleset.max_hp_at_l1,
        min_die=3 if ruleset.reroll_1s_2s_hp_l1 else 1,
    )
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/hp")


@router.post("/{draft_id}/hp")
async def post_hp(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if "hp_roll" not in draft:
        raise HTTPException(400, "Roll HP first")
    return _redirect(f"/wizard/{draft_id}/review")


def _draft_to_spec(draft: dict[str, Any]) -> CharacterSpec:
    ruleset = RuleSet(**draft.get("ruleset", {}))
    return CharacterSpec(
        name=draft["name"],
        abilities=draft["abilities"],
        race_id=draft["race_id"],
        classes=[ClassEntry(
            class_id=draft["class_id"],
            level=1,
            hp_rolls=[draft["hp_roll"]],
        )],
        alignment=draft["alignment"],
        ruleset=ruleset,
    )


@router.get("/{draft_id}/review", response_class=HTMLResponse)
async def get_review(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "review", draft_id)
    if redirect:
        return redirect
    from aose.sheet.view import build_sheet
    spec = _draft_to_spec(draft)
    sheet = build_sheet(spec, request.app.state.game_data)
    ctx = _base_context(request, draft_id, draft, "review")
    ctx["sheet"] = sheet
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/finalize")
async def post_finalize(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft)
    characters_dir = _characters_dir(request)
    char_id = unique_character_id(slugify(spec.name), characters_dir)
    save_character(char_id, spec, characters_dir)
    delete_draft(draft_id, _drafts_dir(request))
    return _redirect(f"/character/{char_id}")


@router.post("/{draft_id}/cancel")
async def post_cancel(request: Request, draft_id: str):
    delete_draft(draft_id, _drafts_dir(request))
    return _redirect("/")
