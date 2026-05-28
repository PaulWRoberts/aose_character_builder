import random
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
from aose.engine.dice import roll_3d6_in_order, roll_4d6_drop_lowest_in_order, roll_hp
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.proficiency import proficiency_groups, starting_proficiency_count
from aose.engine.shop import (
    InsufficientGold,
    REMOVE_MODES,
    UnknownItem,
    add_free as shop_add_free,
    add_free_container,
    buy as shop_buy,
    buy_container,
    inventory_view,
    remove as shop_remove,
    remove_from_stash as shop_remove_from_stash,
    roll_starting_gold,
    shop_categories,
    stash as shop_stash,
    unstash as shop_unstash,
)
from aose.models import Ability, CharacterSpec, ClassEntry, ContainerInstance, RuleSet
from aose.web.settings_routes import (
    CHOICE_GROUPS,
    IMPLEMENTED_CHOICE_GROUPS,
    IMPLEMENTED_RULES,
    RULE_GROUPS,
    RULE_LABELS,
    parse_ruleset_from_form,
)

router = APIRouter(prefix="/wizard")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STEP_LABELS = {
    "rules": "Rules",
    "abilities": "Abilities",
    "race": "Race",
    "class": "Class",
    "alignment": "Alignment",
    "skill": "Secondary Skill",
    "proficiencies": "Proficiencies",
    "hp": "Hit Points",
    "equipment": "Equipment",
    "review": "Review",
}


def _ruleset_of(draft: dict[str, Any]) -> RuleSet:
    return RuleSet(**draft.get("ruleset", {}))


def _wizard_steps(draft: dict[str, Any]) -> list[str]:
    """Build the ordered list of wizard steps that apply to *this* draft.

    Steps gated by optional rules are inserted only when the rule is active.
    When ``separate_race_class`` is off, the race step is folded into the
    class step (race-as-class mode), so it drops out of the breadcrumb.
    """
    rs = _ruleset_of(draft)
    steps = ["rules", "abilities"]
    if rs.separate_race_class:
        steps.append("race")
    steps += ["class", "alignment"]
    if rs.secondary_skills:
        steps.append("skill")
    if rs.weapon_proficiency:
        steps.append("proficiencies")
    steps += ["hp", "equipment", "review"]
    return steps
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


def _has_class_pick(draft: dict[str, Any]) -> bool:
    return "class_id" in draft or "class_ids" in draft


def _has_hp(draft: dict[str, Any]) -> bool:
    return "hp_roll" in draft or "hp_rolls" in draft


def _class_ids(draft: dict[str, Any]) -> list[str]:
    """Return the picked class ids regardless of single/multi-class storage."""
    if "class_ids" in draft:
        return list(draft["class_ids"])
    if "class_id" in draft:
        return [draft["class_id"]]
    return []


# ── Downstream-clear helpers (used when the user navigates back and changes
# an earlier choice — keeps the draft from carrying stale data) ───────────

def _clear_after_abilities(draft: dict[str, Any]) -> None:
    for k in ("race_id", "class_id", "class_ids", "hp_roll", "hp_rolls",
             "proficiencies"):
        draft.pop(k, None)


def _clear_after_race(draft: dict[str, Any]) -> None:
    for k in ("class_id", "class_ids", "hp_roll", "hp_rolls", "proficiencies"):
        draft.pop(k, None)


def _clear_after_class(draft: dict[str, Any]) -> None:
    for k in ("hp_roll", "hp_rolls", "proficiencies"):
        draft.pop(k, None)


def _next_incomplete_step(draft: dict[str, Any]) -> str:
    # The rules step is "complete" once it has rolled abilities — at /new we
    # seed only the ruleset, so a draft without abilities is mid-rules step.
    if "abilities" not in draft:
        return "rules"
    if "name" not in draft:
        return "abilities"
    rs = _ruleset_of(draft)
    # In race-as-class mode, race_id is assigned by the class POST handler,
    # so we don't have a standalone race step to send the user to.
    if rs.separate_race_class and "race_id" not in draft:
        return "race"
    if not _has_class_pick(draft):
        return "class"
    if "alignment" not in draft:
        return "alignment"
    if rs.secondary_skills and "secondary_skill" not in draft:
        return "skill"
    if rs.weapon_proficiency and "proficiencies" not in draft:
        return "proficiencies"
    if not _has_hp(draft):
        return "hp"
    if "gold" not in draft:
        return "equipment"
    return "review"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _base_context(request: Request, draft_id: str, draft: dict, current_step: str) -> dict:
    """Build the template context, including per-step state (done/current/todo)
    so the breadcrumb can render completed steps as back-navigation links."""
    steps = _wizard_steps(draft)
    current_index = steps.index(current_step)
    next_incomplete = _next_incomplete_step(draft)
    try:
        next_idx = steps.index(next_incomplete)
    except ValueError:
        next_idx = len(steps)  # ruleset changed; treat all as done

    step_states: list[dict] = []
    for i, step in enumerate(steps):
        if step == current_step:
            state = "current"
        elif i < next_idx:
            state = "done"
        else:
            state = "todo"
        step_states.append({
            "id": step,
            "label": STEP_LABELS[step],
            "state": state,
        })

    return {
        "draft_id": draft_id,
        "draft": draft,
        "current_step": current_step,
        "current_step_index": current_index,
        "wizard_steps": steps,
        "step_labels": STEP_LABELS,
        "step_states": step_states,
    }


def _gate(draft: dict, required_step: str, draft_id: str) -> RedirectResponse | None:
    """Redirect to the next incomplete step if the user is past their progress
    — or has wandered into a step that the active ruleset doesn't include."""
    steps = _wizard_steps(draft)
    if required_step not in steps:
        # Rule turned off after the user landed here; bounce them forward.
        return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
    next_step = _next_incomplete_step(draft)
    if steps.index(required_step) > steps.index(next_step):
        return _redirect(f"/wizard/{draft_id}/{next_step}")
    return None


def _roll_ability_values(method: str) -> list[int]:
    """Return six ability-score values rolled by the chosen generation method.

    For arrange mode we still roll 3d6 — the only difference from in-order is
    that the user may reassign the rolls between abilities in the UI.
    """
    if method == "4d6_drop_lowest":
        return roll_4d6_drop_lowest_in_order()
    return roll_3d6_in_order()  # 3d6_in_order and 3d6_arrange both start here


def _seed_draft_abilities(draft: dict[str, Any], ruleset: RuleSet) -> None:
    """Populate (or replace) draft['abilities'] and the arrange pool for a re-roll."""
    method = ruleset.ability_roll_method
    values = _roll_ability_values(method)
    draft["abilities"] = dict(zip([a.value for a in ABILITY_ORDER], values))
    if method == "3d6_arrange":
        draft["abilities_pool"] = sorted(values, reverse=True)
    else:
        draft.pop("abilities_pool", None)


@router.get("/new")
async def new_wizard(request: Request):
    draft_id = new_draft_id()
    ruleset = load_settings(request.app.state.settings_path)
    # Seed abilities up-front using the *default* method.  If the user then
    # changes ability_roll_method on the rules step, the POST handler re-rolls
    # via _apply_rule_changes.  Keeping the roll here means tests and other
    # callers that inspect ``draft["abilities"]`` after ``/wizard/new`` keep
    # working unchanged.
    draft: dict[str, Any] = {"ruleset": ruleset.model_dump()}
    _seed_draft_abilities(draft, ruleset)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/rules")


# ── Per-character ruleset (always the first step) ─────────────────────────

@router.get("/{draft_id}/rules", response_class=HTMLResponse)
async def get_rules(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ruleset = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "rules")
    ctx.update({
        "ruleset": ruleset.model_dump(),
        "rule_groups": RULE_GROUPS,
        "choice_groups": CHOICE_GROUPS,
        "rule_labels": RULE_LABELS,
        "implemented_rules": IMPLEMENTED_RULES,
        "implemented_choice_groups": IMPLEMENTED_CHOICE_GROUPS,
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)


def _apply_rule_changes(draft: dict[str, Any], old_rs: RuleSet, new_rs: RuleSet) -> None:
    """Save the new ruleset on the draft and apply targeted clears for any
    rule changes that would invalidate downstream choices.

    Cascading clears (most disruptive first):

    * ability_roll_method change OR abilities not yet rolled  → re-seed
      abilities + clear everything from race down.
    * separate_race_class toggle → clear race + class + below (the race-as-class
      flow restructures both steps).
    * max_hp_at_l1 or reroll_1s_2s_hp_l1 change → clear hp_roll(s) only.
    * weapon_proficiency change → clear proficiencies only.
    * multiclassing turned OFF while a combo is picked → clear class + below.
    """
    draft["ruleset"] = new_rs.model_dump()

    if (new_rs.ability_roll_method != old_rs.ability_roll_method
            or "abilities" not in draft):
        _seed_draft_abilities(draft, new_rs)
        _clear_after_abilities(draft)
        return

    if new_rs.separate_race_class != old_rs.separate_race_class:
        _clear_after_abilities(draft)
        return

    if (new_rs.max_hp_at_l1 != old_rs.max_hp_at_l1
            or new_rs.reroll_1s_2s_hp_l1 != old_rs.reroll_1s_2s_hp_l1):
        draft.pop("hp_roll", None)
        draft.pop("hp_rolls", None)

    if new_rs.weapon_proficiency != old_rs.weapon_proficiency:
        draft.pop("proficiencies", None)

    if not new_rs.multiclassing and "class_ids" in draft:
        _clear_after_race(draft)


@router.post("/{draft_id}/rules")
async def post_rules(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    form = await request.form()
    new_rs = parse_ruleset_from_form(form)
    old_rs = _ruleset_of(draft)
    _apply_rule_changes(draft, old_rs, new_rs)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


_METHOD_LABELS = {
    "3d6_in_order": "Roll 3d6 in order",
    "3d6_arrange": "Roll 3d6 and assign to taste",
    "4d6_drop_lowest": "Roll 4d6, drop the lowest, in order",
}


@router.get("/{draft_id}/abilities", response_class=HTMLResponse)
async def get_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ruleset = _ruleset_of(draft)
    method = ruleset.ability_roll_method
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
    ctx["arrange_mode"] = method == "3d6_arrange"
    ctx["pool"] = draft.get("abilities_pool", [])
    ctx["method_label"] = _METHOD_LABELS.get(method, method)
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/reroll")
async def post_reroll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ruleset = _ruleset_of(draft)
    _seed_draft_abilities(draft, ruleset)
    # Abilities changed — race/class ability-requirement checks may no longer
    # be satisfied; clear downstream choices to keep the draft consistent.
    _clear_after_abilities(draft)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/abilities")


@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")
    draft["name"] = name

    # In arrange mode, the form also carries new STR/INT/WIS/DEX/CON/CHA values
    # that must form a permutation of the rolled pool.
    if _ruleset_of(draft).ability_roll_method == "3d6_arrange":
        assigned: dict[str, int] = {}
        for ab in ABILITY_ORDER:
            raw = form.get(ab.value)
            if raw is None:
                raise HTTPException(400, f"Missing assignment for {ab.value}")
            try:
                assigned[ab.value] = int(raw)
            except (TypeError, ValueError):
                raise HTTPException(400, f"Invalid value for {ab.value!r}: {raw!r}")
        pool = sorted(draft.get("abilities_pool", []))
        if sorted(assigned.values()) != pool:
            raise HTTPException(
                400,
                f"Ability assignment must use each rolled value exactly once "
                f"(pool was {pool}, got {sorted(assigned.values())}).",
            )
        if assigned != draft.get("abilities"):
            # The user moved values around — downstream ability-requirement
            # checks may now fail.  Clear race/class/etc. defensively.
            draft["abilities"] = assigned
            _clear_after_abilities(draft)

    save_draft(draft_id, draft, _drafts_dir(request))
    # Route via _next_incomplete_step so race-as-class drafts skip /race.
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


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
        # Race changed — class allowance, level caps, and any picked
        # multi-class combos may no longer apply.  Clear everything downstream.
        _clear_after_race(draft)
    draft["race_id"] = race_id
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class")


def _class_allowed_for_race(class_id: str, race, ruleset: RuleSet) -> bool:
    """Return whether a race may pick a class, given the active ruleset.

    With ``demihuman_class_restrictions`` off, any race may pick any class.
    Otherwise an empty ``allowed_classes`` is treated as "no restriction"
    (the human-style default), and a populated list is enforced.
    """
    if not ruleset.demihuman_class_restrictions:
        return True
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
    abilities = draft["abilities"]
    ruleset = _ruleset_of(draft)

    # In race-as-class mode the user has not picked a race yet, so race-based
    # filtering and level caps don't apply on the cards.
    if ruleset.separate_race_class:
        race = data.races[draft["race_id"]]
        race_name = race.name
    else:
        race = None
        race_name = None

    classes = []
    for cls in sorted(data.classes.values(), key=lambda c: c.name):
        # Split mode hides race-as-class entries; race-as-class mode shows
        # everything (race-locked entries become the "demihuman as class" picks).
        if ruleset.separate_race_class and cls.race_locked:
            continue

        meets_abilities = _meets_ability_requirements(cls.ability_requirements, abilities)

        if ruleset.separate_race_class:
            allowed_by_race = _class_allowed_for_race(cls.id, race, ruleset)
            level_cap = (
                race.class_level_caps.get(cls.id)
                if ruleset.demihuman_level_limits
                else None
            )
        else:
            allowed_by_race = True  # no race chosen yet
            level_cap = None         # race caps don't bind a race-as-class entry

        classes.append({
            "id": cls.id,
            "name": cls.name,
            "hit_die": cls.hit_die,
            "prime_requisites": [a.value for a in cls.prime_requisites],
            "level_cap": level_cap,
            "race_locked": cls.race_locked,
            "allowed_by_race": allowed_by_race,
            "meets_abilities": meets_abilities,
            "available": allowed_by_race and meets_abilities,
            "selected": _class_ids(draft) == [cls.id],
        })

    # Multi-class combos (only in split mode + multiclassing rule on +
    # race actually has declared combos).
    combos: list[dict] = []
    if (ruleset.multiclassing
            and ruleset.separate_race_class
            and race is not None
            and race.allowed_multiclass_combos):
        chosen = _class_ids(draft)
        for combo in race.allowed_multiclass_combos:
            combo_classes = [data.classes.get(cid) for cid in combo]
            if any(c is None for c in combo_classes):
                continue  # combo references a class not present in data
            meets_all = all(
                _meets_ability_requirements(c.ability_requirements, abilities)
                for c in combo_classes
            )
            combos.append({
                "id": ",".join(combo),  # form value carries the combo
                "name": " / ".join(c.name for c in combo_classes),
                "class_names": [c.name for c in combo_classes],
                "available": meets_all,
                "selected": sorted(chosen) == sorted(combo),
            })

    ctx = _base_context(request, draft_id, draft, "class")
    ctx["classes"] = classes
    ctx["combos"] = combos
    ctx["race_name"] = race_name
    ctx["race_as_class_mode"] = not ruleset.separate_race_class
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/class")
async def post_class(request: Request, draft_id: str, class_id: str = Form(...)):
    """Accept either a single class id (``"fighter"``) or a comma-joined combo
    (``"fighter,magic_user"``).  Combos require the Multiclassing rule and a
    matching entry in the race's allowed_multiclass_combos."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)

    ids = [x.strip() for x in class_id.split(",") if x.strip()]
    if not ids:
        raise HTTPException(400, "No class selected")
    for cid in ids:
        if cid not in data.classes:
            raise HTTPException(400, f"Unknown class '{cid}'")

    # ── Single-class branch (the common case) ───────────────────────────
    if len(ids) == 1:
        cid = ids[0]
        cls = data.classes[cid]

        if not _meets_ability_requirements(cls.ability_requirements, draft["abilities"]):
            raise HTTPException(400, f"Abilities do not meet {cls.name} requirements")

        if ruleset.separate_race_class:
            if cls.race_locked:
                raise HTTPException(
                    400,
                    f"{cls.name} is a race-as-class entry and not available with "
                    "Separate Race & Class on.",
                )
            race = data.races[draft["race_id"]]
            if not _class_allowed_for_race(cid, race, ruleset):
                raise HTTPException(400, f"{race.name} cannot be a {cls.name}")
        else:
            derived_race_id = cls.race_locked or "human"
            if derived_race_id not in data.races:
                raise HTTPException(500, f"Race '{derived_race_id}' missing from data/races/.")
            draft["race_id"] = derived_race_id

        # Swap storage from multi → single if the user changed their mind.
        if _class_ids(draft) != [cid]:
            _clear_after_class(draft)
        draft.pop("class_ids", None)
        draft["class_id"] = cid
        save_draft(draft_id, draft, _drafts_dir(request))
        return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")

    # ── Multi-class branch ──────────────────────────────────────────────
    if not ruleset.multiclassing:
        raise HTTPException(400, "Multi-class picks require the Multiclassing rule.")
    if not ruleset.separate_race_class:
        # The race-as-class + multi-class interaction (e.g. dual-classing within
        # a single race entry) isn't modelled yet; reject defensively.
        raise HTTPException(
            400,
            "Multi-class with Race-as-Class is not supported in this build.",
        )

    race = data.races[draft["race_id"]]
    allowed_sorted = [sorted(c) for c in race.allowed_multiclass_combos]
    if sorted(ids) not in allowed_sorted:
        raise HTTPException(
            400,
            f"Combination {ids} is not allowed for {race.name}.",
        )
    for cid in ids:
        cls = data.classes[cid]
        if cls.race_locked:
            raise HTTPException(
                400,
                f"Race-locked class {cls.name!r} cannot appear in a multi-class combo.",
            )
        if not _meets_ability_requirements(cls.ability_requirements, draft["abilities"]):
            raise HTTPException(400, f"Abilities do not meet {cls.name} requirements")

    if _class_ids(draft) != ids:
        _clear_after_class(draft)
    draft.pop("class_id", None)
    draft["class_ids"] = ids
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


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
    next_step = _next_incomplete_step(draft)
    return _redirect(f"/wizard/{draft_id}/{next_step}")


# ── Secondary skill (optional, gated by ruleset.secondary_skills) ─────────

def _available_skills(request: Request) -> list[str]:
    return request.app.state.game_data.secondary_skills


def _roll_skill(request: Request) -> str | None:
    skills = _available_skills(request)
    if not skills:
        return None
    return random.choice(skills)


@router.get("/{draft_id}/skill", response_class=HTMLResponse)
async def get_skill(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "skill", draft_id)
    if redirect:
        return redirect
    skills = _available_skills(request)
    if not skills:
        raise HTTPException(
            500,
            "Secondary Skills rule is active but data/secondary_skills.yaml is empty.",
        )
    # Auto-roll on first visit so the user has something to either accept,
    # re-roll, or override from the dropdown.
    if "secondary_skill" not in draft:
        draft["secondary_skill"] = random.choice(skills)
        save_draft(draft_id, draft, _drafts_dir(request))
    ctx = _base_context(request, draft_id, draft, "skill")
    ctx.update({
        "skills": skills,
        "current_skill": draft.get("secondary_skill"),
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/skill/reroll")
async def post_skill_reroll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    skill = _roll_skill(request)
    if skill is None:
        raise HTTPException(500, "No secondary skills configured.")
    draft["secondary_skill"] = skill
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/skill")


@router.post("/{draft_id}/skill")
async def post_skill(request: Request, draft_id: str, secondary_skill: str = Form(...)):
    draft = _load(request, draft_id)
    if secondary_skill not in _available_skills(request):
        raise HTTPException(400, f"Unknown skill: {secondary_skill!r}")
    draft["secondary_skill"] = secondary_skill
    save_draft(draft_id, draft, _drafts_dir(request))
    next_step = _next_incomplete_step(draft)
    return _redirect(f"/wizard/{draft_id}/{next_step}")


# ── Weapon proficiencies (optional, gated by ruleset.weapon_proficiency) ──

def _proficiency_slots_for(draft: dict[str, Any], data) -> tuple[int, str]:
    """Slot count + a class-name label for the proficiency step.

    For multi-class characters, AOSE Advanced grants the highest slot count
    among the picked classes (not the sum)."""
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]
    if len(classes) == 1:
        return starting_proficiency_count(classes[0]), classes[0].name
    best = max(starting_proficiency_count(c) for c in classes)
    label = " / ".join(c.name for c in classes)
    return best, label


@router.get("/{draft_id}/proficiencies", response_class=HTMLResponse)
async def get_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "proficiencies", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    required, class_name = _proficiency_slots_for(draft, data)
    chosen = set(draft.get("proficiencies", []))
    groups = proficiency_groups(data)
    if not groups:
        raise HTTPException(
            500,
            "Weapon Proficiency rule is active but no weapons with "
            "proficiency_group set are in the data set.",
        )
    rendered_groups = [
        {**g, "selected": g["id"] in chosen} for g in groups
    ]
    ctx = _base_context(request, draft_id, draft, "proficiencies")
    ctx.update({
        "class_name": class_name,
        "required": required,
        "groups": rendered_groups,
        "currently_chosen": sorted(chosen),
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/proficiencies")
async def post_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    form = await request.form()
    selected = form.getlist("proficiency_group")

    data = request.app.state.game_data
    required, class_name = _proficiency_slots_for(draft, data)
    valid_ids = {g["id"] for g in proficiency_groups(data)}

    unknown = [s for s in selected if s not in valid_ids]
    if unknown:
        raise HTTPException(400, f"Unknown proficiency group(s): {unknown}")
    unique = list(dict.fromkeys(selected))
    if len(unique) != required:
        raise HTTPException(
            400,
            f"{class_name} must pick exactly {required} proficiency groups; "
            f"got {len(unique)}.",
        )

    draft["proficiencies"] = unique
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/hp")


def _multiclass_total_hp(rolls: list[int], con_mod: int) -> int:
    """Multi-class L1 HP: floor(avg of class rolls) + CON mod, min 1."""
    if not rolls:
        return 0
    return max(1, sum(rolls) // len(rolls) + con_mod)


@router.get("/{draft_id}/hp", response_class=HTMLResponse)
async def get_hp(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "hp", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    con_mod = ability_modifier(draft["abilities"]["CON"])

    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]
    is_multi = len(ids) > 1

    # Max HP at L1 is deterministic — populate every class's HP on first visit.
    if ruleset.max_hp_at_l1:
        if is_multi and "hp_rolls" not in draft:
            draft["hp_rolls"] = [roll_hp(c.hit_die, take_max=True) for c in classes]
            save_draft(draft_id, draft, _drafts_dir(request))
        elif not is_multi and "hp_roll" not in draft:
            draft["hp_roll"] = roll_hp(classes[0].hit_die, take_max=True)
            save_draft(draft_id, draft, _drafts_dir(request))

    # Pre-render per-class rolls (None if not rolled yet)
    rolls_for_template: list[dict] = []
    total = None
    if is_multi:
        existing = draft.get("hp_rolls", [None] * len(ids))
        for cls, roll_val in zip(classes, existing):
            rolls_for_template.append({
                "class_name": cls.name,
                "hit_die": cls.hit_die,
                "roll": roll_val,
            })
        if all(r is not None for r in existing) and existing:
            total = _multiclass_total_hp(existing, con_mod)
    else:
        rolls_for_template.append({
            "class_name": classes[0].name,
            "hit_die": classes[0].hit_die,
            "roll": draft.get("hp_roll"),
        })
        if "hp_roll" in draft:
            total = max(1, draft["hp_roll"] + con_mod)

    ctx = _base_context(request, draft_id, draft, "hp")
    ctx.update({
        "is_multi": is_multi,
        "class_name": " / ".join(c.name for c in classes),
        "hit_die": classes[0].hit_die,  # single-class template uses this
        "con_mod": con_mod,
        "rolls": rolls_for_template,
        "total_hp": total,
        "max_hp_rule": ruleset.max_hp_at_l1,
        "reroll_rule": ruleset.reroll_1s_2s_hp_l1,
        "ready": (total is not None),
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]

    take_max = ruleset.max_hp_at_l1
    min_die = 3 if ruleset.reroll_1s_2s_hp_l1 else 1

    if len(ids) == 1:
        draft["hp_roll"] = roll_hp(classes[0].hit_die, take_max=take_max, min_die=min_die)
        draft.pop("hp_rolls", None)
    else:
        draft["hp_rolls"] = [
            roll_hp(c.hit_die, take_max=take_max, min_die=min_die) for c in classes
        ]
        draft.pop("hp_roll", None)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/hp")


@router.post("/{draft_id}/hp")
async def post_hp(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if not _has_hp(draft):
        raise HTTPException(400, "Roll HP first")
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Equipment (always-on step right before Review) ────────────────────────

def _equipment_context(draft: dict[str, Any], game_data) -> dict:
    """Build the rendering context for the equipment partial — shared between
    the wizard equipment step and the live character sheet."""
    inventory = draft.get("inventory", [])
    stashed = draft.get("stashed", [])
    equipped = draft.get("equipped", {})
    equipped_weapons = draft.get("equipped_weapons", [])
    containers = [
        ContainerInstance.model_validate(c) for c in draft.get("containers", [])
    ]
    return {
        "gold": draft.get("gold", 0),
        "gold_locked": draft.get("gold_locked", False),
        "inventory_view": inventory_view(
            inventory, stashed, equipped, equipped_weapons, containers, game_data,
        ),
        "shop": shop_categories(game_data),
        "remove_modes": REMOVE_MODES,
    }


@router.get("/{draft_id}/equipment", response_class=HTMLResponse)
async def get_equipment(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "equipment", draft_id)
    if redirect:
        return redirect
    # First visit: roll starting gold.  Subsequent visits keep whatever the
    # user has (rolled, re-rolled, or partially spent).
    if "gold" not in draft:
        draft["gold"] = roll_starting_gold()
        draft.setdefault("inventory", [])
        draft.setdefault("gold_locked", False)
        save_draft(draft_id, draft, _drafts_dir(request))
    ctx = _base_context(request, draft_id, draft, "equipment")
    ctx.update(_equipment_context(draft, request.app.state.game_data))
    ctx["target_url_prefix"] = f"/wizard/{draft_id}/equipment"
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/equipment/reroll-gold")
async def post_equipment_reroll_gold(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if draft.get("gold_locked"):
        raise HTTPException(400, "Starting gold is locked — a purchase has already been made.")
    draft["gold"] = roll_starting_gold()
    draft.setdefault("inventory", [])
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/buy")
async def post_equipment_buy(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    item = data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            containers_raw = draft.get("containers", [])
            containers = [ContainerInstance.model_validate(c) for c in containers_raw]
            new_containers, new_gold = buy_container(
                containers, draft.get("gold", 0), item_id, data,
            )
            draft["containers"] = [c.model_dump() for c in new_containers]
            draft["gold"] = new_gold
        else:
            new_inventory, new_gold = shop_buy(
                draft.get("inventory", []), draft.get("gold", 0), item_id, data,
            )
            draft["inventory"] = new_inventory
            draft["gold"] = new_gold
        draft["gold_locked"] = True  # first purchase locks the starting-gold roll
    except (UnknownItem, InsufficientGold, ValueError) as e:
        raise HTTPException(400, str(e))
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/add")
async def post_equipment_add(request: Request, draft_id: str, item_id: str = Form(...)):
    """Add an item to inventory without paying — keeps the starting-gold roll
    unlocked since no purchase happened."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    item = data.items.get(item_id)
    from aose.models import Container
    try:
        if isinstance(item, Container):
            containers_raw = draft.get("containers", [])
            containers = [ContainerInstance.model_validate(c) for c in containers_raw]
            new_containers = add_free_container(containers, item_id, data)
            draft["containers"] = [c.model_dump() for c in new_containers]
        else:
            draft["inventory"] = shop_add_free(draft.get("inventory", []), item_id, data)
    except (UnknownItem, ValueError) as e:
        raise HTTPException(400, str(e))
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/equip")
async def post_equipment_equip(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    try:
        new_eq, new_weapons = _equip(
            draft.get("inventory", []),
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            item_id, data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["equipped"] = new_eq
    draft["equipped_weapons"] = new_weapons
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/unequip")
async def post_equipment_unequip(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    try:
        new_eq, new_weapons = _unequip(
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            item_id, data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["equipped"] = new_eq
    draft["equipped_weapons"] = new_weapons
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/stash")
async def post_equipment_stash(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    try:
        new_inv, new_stashed, new_eq, new_weapons = shop_stash(
            draft.get("inventory", []),
            draft.get("stashed", []),
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            item_id, data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = new_inv
    draft["stashed"] = new_stashed
    draft["equipped"] = new_eq
    draft["equipped_weapons"] = new_weapons
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/unstash")
async def post_equipment_unstash(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    try:
        new_inv, new_stashed = shop_unstash(
            draft.get("inventory", []), draft.get("stashed", []), item_id, data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = new_inv
    draft["stashed"] = new_stashed
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/remove")
async def post_equipment_remove(request: Request, draft_id: str,
                                item_id: str = Form(...),
                                mode: str = Form(...),
                                from_state: str = Form("carried")):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    try:
        if from_state == "stashed":
            new_stashed, new_gold = shop_remove_from_stash(
                draft.get("stashed", []), draft.get("gold", 0), item_id, mode, data,
            )
            draft["stashed"] = new_stashed
            draft["gold"] = new_gold
        else:
            new_inv, new_gold, new_eq, new_weapons = shop_remove(
                draft.get("inventory", []), draft.get("gold", 0),
                item_id, mode, data,
                draft.get("equipped", {}),
                draft.get("equipped_weapons", []),
            )
            draft["inventory"] = new_inv
            draft["gold"] = new_gold
            draft["equipped"] = new_eq
            draft["equipped_weapons"] = new_weapons
    except ValueError as e:
        raise HTTPException(400, str(e))
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment")
async def post_equipment_continue(request: Request, draft_id: str):
    """Advance from Equipment to Review.  Locks the gold roll even if the
    user didn't buy anything — they've explicitly chosen to stop shopping."""
    draft = _load(request, draft_id)
    draft.setdefault("inventory", [])
    draft.setdefault("gold_locked", True)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/review")


def _draft_to_spec(draft: dict[str, Any]) -> CharacterSpec:
    ruleset = RuleSet(**draft.get("ruleset", {}))
    ids = _class_ids(draft)
    if "hp_rolls" in draft:
        hp_rolls = draft["hp_rolls"]
    else:
        hp_rolls = [draft["hp_roll"]]  # single-class storage

    if len(ids) != len(hp_rolls):
        raise RuntimeError(
            f"Draft inconsistency: {len(ids)} class(es) vs {len(hp_rolls)} HP roll(s)"
        )

    classes = [
        ClassEntry(class_id=cid, level=1, hp_rolls=[hp_rolls[i]])
        for i, cid in enumerate(ids)
    ]
    return CharacterSpec(
        name=draft["name"],
        abilities=draft["abilities"],
        race_id=draft["race_id"],
        classes=classes,
        alignment=draft["alignment"],
        secondary_skill=draft.get("secondary_skill"),
        chosen_proficiencies=list(draft.get("proficiencies", [])),
        gold=draft.get("gold", 0),
        inventory=list(draft.get("inventory", [])),
        stashed=list(draft.get("stashed", [])),
        equipped=dict(draft.get("equipped", {})),
        equipped_weapons=list(draft.get("equipped_weapons", [])),
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
