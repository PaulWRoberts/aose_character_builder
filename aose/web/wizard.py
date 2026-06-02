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
from aose.engine.ability_mods import (
    ability_modifier,
    ability_warnings,
    apply_ability_adjustments,
    apply_racial_modifiers,
)
from aose.engine.alignment import allowed_alignments as _allowed_alignments
from aose.engine import spells as spell_engine
from aose.engine.dice import roll_3d6_in_order, roll_first_level_hp, roll_hp
from aose.engine.equip import equip as _equip, unequip as _unequip
from aose.engine.magic import (
    add_free_magic_item,
    equip_magic as _equip_magic,
    needs_instance,
    remove_magic as _remove_magic,
    reset_charges as _reset_charges,
    set_magic_note as _set_magic_note,
    unequip_magic as _unequip_magic,
    use_charge as _use_charge,
)
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    category_for_classes,
    shields_allowed,
    specialisation_allowed,
    total_proficiency_slots,
)
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
    remove_container as shop_remove_container,
    remove_from_stash as shop_remove_from_stash,
    roll_starting_gold,
    shop_categories,
    stash as shop_stash,
    stash_container as shop_stash_container,
    stow as shop_stow,
    take_out as shop_take_out,
    unstash as shop_unstash,
    unstash_container as shop_unstash_container,
)
from aose.models import (
    Ability,
    CharacterSpec,
    ClassEntry,
    ContainerInstance,
    MagicItemInstance,
    RuleSet,
)
from aose.sheet.view import magic_items_view
from aose.web.move_dispatch import dispatch_move
from aose.web.settings_routes import (
    ADVANCED_OPTIONS_GROUP,
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
    "adjust": "Ability Adjustments",
    "class_setup": "Class Setup",
    "identity": "Identity & Background",
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
    steps += ["class", "adjust", "class_setup", "identity", "equipment", "review"]
    return steps
ABILITY_ORDER = [Ability.STR, Ability.INT, Ability.WIS, Ability.DEX, Ability.CON, Ability.CHA]
ALIGNMENT_LABELS = {"law": "Lawful", "neutral": "Neutral", "chaos": "Chaotic"}

# Multiple Classes optional rule: a character may be of up to three classes.
MAX_CLASSES = 3


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


def _casts_at_level_1(cls) -> bool:
    """True if the class has a spell list and at least one spell slot at L1."""
    row = cls.progression.get(1)
    return bool(cls.spell_lists) and bool(row and row.spell_slots)


# ── Downstream-clear helpers (used when the user navigates back and changes
# an earlier choice — keeps the draft from carrying stale data) ───────────

def _clear_after_abilities(draft: dict[str, Any]) -> None:
    for k in ("race_id", "class_id", "class_ids", "ability_adjustments",
              "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done"):
        draft.pop(k, None)


def _clear_after_race(draft: dict[str, Any]) -> None:
    for k in ("class_id", "class_ids", "ability_adjustments",
              "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done"):
        draft.pop(k, None)


def _clear_after_class(draft: dict[str, Any]) -> None:
    # A class change can invalidate the chosen alignment (e.g. picking paladin
    # after choosing chaos). name and secondary_skill don't depend on class.
    for k in ("ability_adjustments", "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done", "alignment"):
        draft.pop(k, None)


def _class_setup_complete(draft: dict[str, Any]) -> bool:
    """The consolidated Class Setup step is complete when HP is rolled AND
    weapon proficiencies are chosen (if the rule is on) AND starting spells are
    chosen (if any picked class casts at L1)."""
    rs = _ruleset_of(draft)
    if not _has_hp(draft):
        return False
    if rs.weapon_proficiency and "proficiencies" not in draft:
        return False
    if draft.get("spellcasting") and not draft.get("spells_done"):
        return False
    return True


def _identity_complete(draft: dict[str, Any]) -> bool:
    """Identity is complete once name and alignment are set (and the secondary
    skill, when that rule is on)."""
    if not draft.get("name"):
        return False
    if "alignment" not in draft:
        return False
    if _ruleset_of(draft).secondary_skills and "secondary_skill" not in draft:
        return False
    return True


def _next_incomplete_step(draft: dict[str, Any]) -> str:
    # The rules step is "complete" once it has rolled abilities — at /new we
    # seed only the ruleset, so a draft without abilities is mid-rules step.
    if "abilities" not in draft:
        return "rules"
    if not draft.get("abilities_confirmed"):
        return "abilities"
    rs = _ruleset_of(draft)
    # In race-as-class mode, race_id is assigned by the class POST handler,
    # so we don't have a standalone race step to send the user to.
    if rs.separate_race_class and "race_id" not in draft:
        return "race"
    if not _has_class_pick(draft):
        return "class"
    if "ability_adjustments" not in draft:
        return "adjust"
    if not _class_setup_complete(draft):
        return "class_setup"
    if not _identity_complete(draft):
        return "identity"
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


def _seed_draft_abilities(draft: dict[str, Any]) -> None:
    """Roll 3d6 in order and store the six scores on the draft.

    Abilities are always 3d6 down the line — there are no alternate methods,
    and the roll is locked once the draft exists.
    """
    values = roll_3d6_in_order()
    draft["abilities"] = dict(zip([a.value for a in ABILITY_ORDER], values))


@router.get("/new")
async def new_wizard(request: Request):
    draft_id = new_draft_id()
    ruleset = load_settings(request.app.state.settings_path)
    # Abilities are rolled once here and locked. The rules step never changes
    # them — _apply_rule_changes only re-seeds if the draft somehow lacks them.
    draft: dict[str, Any] = {"ruleset": ruleset.model_dump()}
    _seed_draft_abilities(draft)
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
        "advanced_options_group": ADVANCED_OPTIONS_GROUP,
    })
    return templates.TemplateResponse(request, "wizard.html", ctx)


def _apply_rule_changes(draft: dict[str, Any], old_rs: RuleSet, new_rs: RuleSet) -> None:
    """Save the new ruleset on the draft and apply targeted clears for any
    rule changes that would invalidate downstream choices.

    Cascading clears (most disruptive first):

    * abilities not yet rolled (safety) → re-seed abilities + clear from race down.
    * separate_race_class toggle → clear race + class + below (the race-as-class
      flow restructures both steps).
    * lift_demihuman_restrictions toggle → clear class + below (mirrors a race
      change, so an on→off flip can't leave a now-illegal class/level pick).
    * reroll_1s_2s_hp_l1 change → clear hp_roll(s) only.
    * weapon_proficiency change → clear proficiencies only.
    * multiclassing turned OFF while a combo is picked → clear class + below.
    """
    draft["ruleset"] = new_rs.model_dump()

    if "abilities" not in draft:
        # Safety re-seed only — abilities are normally rolled at draft creation.
        _seed_draft_abilities(draft)
        _clear_after_abilities(draft)
        return

    if new_rs.separate_race_class != old_rs.separate_race_class:
        _clear_after_abilities(draft)
        return

    if new_rs.lift_demihuman_restrictions != old_rs.lift_demihuman_restrictions:
        _clear_after_race(draft)

    if new_rs.reroll_1s_2s_hp_l1 != old_rs.reroll_1s_2s_hp_l1:
        draft.pop("hp_roll", None)
        draft.pop("hp_rolls", None)

    if new_rs.human_racial_abilities != old_rs.human_racial_abilities:
        # Blessed eligibility AND post-racial scores changed; clear the HP roll
        # and any ability adjustments computed off the old post-racial baseline.
        draft.pop("hp_roll", None)
        draft.pop("hp_rolls", None)
        draft.pop("ability_adjustments", None)

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
    ctx.update(ability_warnings(draft["abilities"]))  # subpar, rock_bottom
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    # Name moved to the Identity step; confirming abilities is now the step's
    # completion marker. Abilities themselves are locked at draft creation.
    draft["abilities_confirmed"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    # Route via _next_incomplete_step so race-as-class drafts skip /race.
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


def _meets_ability_requirements(reqs: dict[Ability, int], abilities: dict[str, int]) -> bool:
    return all(abilities.get(ab.value, 0) >= score for ab, score in reqs.items())


def _post_racial_abilities(draft: dict[str, Any], data) -> dict[str, int]:
    """Rolled base plus racial modifiers (Advanced only, once a race is chosen).

    In Basic / race-as-class mode, or before a race is picked, this is the
    rolled base unchanged. When the human_racial_abilities rule is on, the
    race's optional modifiers (Human +1 CHA / +1 CON) are folded in too.
    Modifiers are clamped to [3, 18]. This is the input and baseline for the
    ability-adjustment step and the class requirement check.
    """
    base = draft["abilities"]
    rs = _ruleset_of(draft)
    if not rs.separate_race_class or "race_id" not in draft:
        return dict(base)
    return apply_racial_modifiers(
        base, data.races[draft["race_id"]],
        include_optional=rs.human_racial_abilities,
    )


def _creation_abilities(draft: dict[str, Any], data) -> dict[str, int]:
    """Post-racial scores with the player's ability adjustments applied — the
    creation-final scores stored on the character. Used by HP, finalize, review."""
    return apply_ability_adjustments(
        _post_racial_abilities(draft, data),
        draft.get("ability_adjustments", {}),
    )


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
        effective = apply_racial_modifiers(abilities, race)
        ability_changes = [
            {
                "name": ab.value,
                "rolled": abilities[ab.value],
                "delta": delta,
                "effective": effective[ab.value],
            }
            for ab, delta in race.ability_modifiers.items()
        ]
        races.append({
            "id": race.id,
            "name": race.name,
            "infravision": race.infravision,
            "base_movement": race.base_movement,
            "requirements": {ab.value: v for ab, v in race.ability_requirements.items()},
            "languages": race.languages,
            "ability_changes": ability_changes,
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

    With ``lift_demihuman_restrictions`` on, any race may pick any class.
    Otherwise an empty ``allowed_classes`` is treated as "no restriction"
    (the human-style default), and a populated list is enforced.
    """
    if ruleset.lift_demihuman_restrictions:
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
    abilities = _post_racial_abilities(draft, data)
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
                if not ruleset.lift_demihuman_restrictions
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
            "selected": cls.id in _class_ids(draft),
        })

    # Free-form multi-classing: when the rule is on (split mode only) the user
    # may pick up to MAX_CLASSES classes, each subject to the same ability /
    # race gating as a single pick.
    multiclass_enabled = ruleset.multiclassing and ruleset.separate_race_class

    ctx = _base_context(request, draft_id, draft, "class")
    ctx["classes"] = classes
    ctx["multiclass_enabled"] = multiclass_enabled
    ctx["max_classes"] = MAX_CLASSES
    ctx["selected_count"] = len(_class_ids(draft))
    ctx["race_name"] = race_name
    ctx["race_as_class_mode"] = not ruleset.separate_race_class
    return templates.TemplateResponse(request, "wizard.html", ctx)


def _set_spellcasting_flag(draft: dict[str, Any], data) -> None:
    """Cache whether any picked class casts at L1 so the draft-only step
    helpers (_wizard_steps / _next_incomplete_step) can gate the spells step."""
    draft["spellcasting"] = any(
        _casts_at_level_1(data.classes[cid]) for cid in _class_ids(draft)
    )


@router.post("/{draft_id}/class")
async def post_class(request: Request, draft_id: str):
    """Accept one class, or — with the Multiclassing rule on — up to
    ``MAX_CLASSES`` classes (free-form).  The class id(s) arrive as one or more
    ``class_id`` form fields; a single field may also be comma-joined
    (``"fighter,magic_user"``) for convenience.  Each picked class must meet its
    own ability requirements and the race's class allowance."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)

    form = await request.form()
    ids: list[str] = []
    for raw in form.getlist("class_id"):
        ids.extend(x.strip() for x in str(raw).split(",") if x.strip())
    ids = list(dict.fromkeys(ids))  # dedupe, preserve order

    if not ids:
        raise HTTPException(400, "No class selected")
    for cid in ids:
        if cid not in data.classes:
            raise HTTPException(400, f"Unknown class '{cid}'")

    is_multi = len(ids) > 1
    if is_multi:
        if not ruleset.multiclassing:
            raise HTTPException(400, "Multi-class picks require the Multiclassing rule.")
        if not ruleset.separate_race_class:
            # Race-as-class + multi-class isn't modelled; reject defensively.
            raise HTTPException(
                400, "Multi-class with Race-as-Class is not supported in this build.",
            )
        if len(ids) > MAX_CLASSES:
            raise HTTPException(400, f"A character may have at most {MAX_CLASSES} classes.")

    # Per-class gating (ability requirements + race allowance / race-as-class).
    effective = _post_racial_abilities(draft, data)
    for cid in ids:
        cls = data.classes[cid]
        if not _meets_ability_requirements(cls.ability_requirements, effective):
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

    # Reject alignment-incompatible multi-class combos up front so the player
    # never reaches an unsatisfiable Identity page. (Single-class is never empty.)
    if not _allowed_alignments([data.classes[c] for c in ids]):
        raise HTTPException(
            400, "These classes have incompatible alignment requirements."
        )

    # Race-as-class (single only): derive the race from the picked class.
    if not ruleset.separate_race_class:
        cls = data.classes[ids[0]]
        derived_race_id = cls.race_locked or "human"
        if derived_race_id not in data.races:
            raise HTTPException(500, f"Race '{derived_race_id}' missing from data/races/.")
        draft["race_id"] = derived_race_id

    # Clear downstream choices if the class set changed.
    if _class_ids(draft) != ids:
        _clear_after_class(draft)
    if is_multi:
        draft.pop("class_id", None)
        draft["class_ids"] = ids
    else:
        draft.pop("class_ids", None)
        draft["class_id"] = ids[0]
    _set_spellcasting_flag(draft, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


def _adjust_context(draft: dict[str, Any], data) -> dict:
    """Per-ability rows for the adjust step: post-racial score, raisable /
    lowerable marks, floor, and any previously stored allocation."""
    from aose.engine.ability_mods import _ability_floor, adjustable_abilities

    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    post_racial = _post_racial_abilities(draft, data)
    adj = adjustable_abilities(classes)
    stored = draft.get("ability_adjustments", {})
    rows = []
    for ab in ABILITY_ORDER:
        name = ab.value
        delta = stored.get(name, 0)
        rows.append({
            "name": name,
            "score": post_racial[name],
            "raisable": name in adj["raisable"],
            "lowerable": name in adj["lowerable"],
            "floor": _ability_floor(name, classes) if name in adj["lowerable"] else None,
            "raise_val": delta if delta > 0 else 0,
            "lower_val": -delta if delta < 0 else 0,
        })
    return {"adjust_rows": rows}


@router.get("/{draft_id}/adjust", response_class=HTMLResponse)
async def get_adjust(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "adjust", draft_id)
    if redirect:
        return redirect
    ctx = _base_context(request, draft_id, draft, "adjust")
    ctx.update(_adjust_context(draft, request.app.state.game_data))
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/adjust")
async def post_adjust(request: Request, draft_id: str):
    from aose.engine.ability_mods import AdjustmentError, validate_ability_adjustments

    draft = _load(request, draft_id)
    data = request.app.state.game_data
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    post_racial = _post_racial_abilities(draft, data)

    form = await request.form()
    adjustments: dict[str, int] = {}
    for ab in ABILITY_ORDER:
        name = ab.value
        try:
            up = int(form.get(f"raise_{name}", 0) or 0)
            down = int(form.get(f"lower_{name}", 0) or 0)
        except ValueError:
            raise HTTPException(400, f"Invalid number for {name}")
        if up < 0 or down < 0:
            raise HTTPException(400, "Adjustment amounts must be non-negative.")
        delta = up - down
        if delta:
            adjustments[name] = delta

    try:
        validate_ability_adjustments(post_racial, classes, adjustments)
    except AdjustmentError as e:
        raise HTTPException(400, str(e))

    draft["ability_adjustments"] = adjustments
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Secondary skill helpers (reused by identity routes) ────────────────────

def _available_skills(request: Request) -> list[str]:
    return request.app.state.game_data.secondary_skills


def _roll_skill(request: Request) -> str | None:
    skills = _available_skills(request)
    if not skills:
        return None
    return random.choice(skills)


# ── Identity & Background (name + alignment + optional skill, after class setup)

def _identity_alignment_options(draft: dict[str, Any], data) -> list[dict]:
    """Alignment radio options filtered to the legal set for the picked class(es)."""
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    allowed = _allowed_alignments(classes)
    return [
        {"id": a, "label": ALIGNMENT_LABELS[a]}
        for a in ("law", "neutral", "chaos")
        if a in allowed
    ]


def _languages_context(draft: dict[str, Any], data) -> dict:
    """Languages section state for the Identity page: native list (from race),
    the alignment tongue for the *current* draft alignment (if chosen yet), the
    INT-gated additional pickers, and the broken-speech note."""
    from aose.engine.languages import (
        additional_language_count,
        alignment_language,
        available_additional,
        broken_speech,
        native_languages,
    )

    race = data.races[draft["race_id"]]
    final_int = _creation_abilities(draft, data)["INT"]
    native = native_languages(race)

    already = set(native)
    align_tongue = None
    alignment = draft.get("alignment")
    if alignment in data.languages.alignment:
        align_tongue = alignment_language(alignment, data.languages)
        already.add(align_tongue)

    chosen = draft.get("languages", [])
    options = available_additional(data.languages, already)
    return {
        "native_languages": native,
        "alignment_language": align_tongue,
        "language_slots": additional_language_count(final_int),
        "language_options": options,
        "chosen_languages": chosen,
        "broken_speech": broken_speech(final_int),
    }


@router.get("/{draft_id}/identity", response_class=HTMLResponse)
async def get_identity(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "identity", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    rs = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "identity")
    ctx["alignments"] = _identity_alignment_options(draft, data)
    ctx["show_skill"] = rs.secondary_skills
    if rs.secondary_skills:
        skills = _available_skills(request)
        if not skills:
            raise HTTPException(
                500,
                "Secondary Skills rule is active but data/secondary_skills.yaml is empty.",
            )
        if "secondary_skill" not in draft:
            draft["secondary_skill"] = random.choice(skills)
            save_draft(draft_id, draft, _drafts_dir(request))
        ctx["skills"] = skills
        ctx["current_skill"] = draft.get("secondary_skill")
    ctx.update(_languages_context(draft, data))
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/identity/skill-reroll")
async def post_identity_skill_reroll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    skill = _roll_skill(request)
    if skill is None:
        raise HTTPException(500, "No secondary skills configured.")
    draft["secondary_skill"] = skill
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/identity")


@router.post("/{draft_id}/identity")
async def post_identity(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    rs = _ruleset_of(draft)
    form = await request.form()

    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")

    alignment = form.get("alignment")
    allowed = {o["id"] for o in _identity_alignment_options(draft, data)}
    if alignment not in allowed:
        raise HTTPException(400, "Invalid alignment for the chosen class(es).")

    if rs.secondary_skills:
        secondary_skill = form.get("secondary_skill")
        if secondary_skill not in _available_skills(request):
            raise HTTPException(400, f"Unknown skill: {secondary_skill!r}")
        draft["secondary_skill"] = secondary_skill

    from aose.engine.languages import LanguageError, validate_languages

    chosen_languages = list(dict.fromkeys(form.getlist("language")))
    race = data.races[draft["race_id"]]
    final_int = _creation_abilities(draft, data)["INT"]
    try:
        validate_languages(
            chosen_languages, race, alignment, final_int, data.languages,
        )
    except LanguageError as e:
        raise HTTPException(400, str(e))

    draft["name"] = name
    draft["alignment"] = alignment
    draft["languages"] = chosen_languages
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Weapon proficiencies (optional, gated by ruleset.weapon_proficiency) ──

def _proficiency_context(draft: dict[str, Any], data) -> dict:
    """Slots, weapon options (filtered to class allowances), and specialise
    flag for the proficiency step."""
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]                 # creation = level 1
    required = total_proficiency_slots(pairs)
    allow_special = specialisation_allowed(classes)
    allowed = allowed_weapon_ids(classes, data)
    from aose.models import Weapon
    weapons = sorted(
        (i for i in data.items.values() if isinstance(i, Weapon)),
        key=lambda w: w.name,
    )
    if allowed != "all":
        weapons = [w for w in weapons if w.id in allowed]
    label = " / ".join(c.name for c in classes) if classes else ""
    chosen = draft.get("proficiencies", {}) or {}
    chosen_weapons = set(chosen.get("weapons", []))
    chosen_special = set(chosen.get("specialisations", []))
    rows = [
        {
            "id": w.id,
            "name": w.name,
            "qualities": ", ".join(w.qualities),
            "selected": w.id in chosen_weapons,
            "specialised": w.id in chosen_special,
        }
        for w in weapons
    ]
    return {
        "class_name": label,
        "required": required,
        "weapons": rows,
        "allow_specialise": allow_special,
    }



@router.post("/{draft_id}/proficiencies")
async def post_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    weapons = list(dict.fromkeys(form.getlist("weapon")))
    specialisations = list(dict.fromkeys(form.getlist("specialise")))

    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]
    required = total_proficiency_slots(pairs)
    allowed = allowed_weapon_ids(classes, data)
    allow_special = specialisation_allowed(classes)

    if allowed != "all":
        bad = [w for w in weapons if w not in allowed]
        if bad:
            raise HTTPException(400, f"Weapon(s) not allowed for this class: {bad}")
    if specialisations and not allow_special:
        raise HTTPException(400, "This class cannot specialise.")
    if any(s not in weapons for s in specialisations):
        raise HTTPException(400, "Can only specialise a weapon you are proficient with.")

    spent = len(weapons) + len(specialisations)
    if spent != required:
        raise HTTPException(
            400,
            f"Must spend exactly {required} proficiency slot(s) at creation; "
            f"spent {spent} (each weapon = 1, each specialisation = +1).",
        )

    draft["proficiencies"] = {"weapons": weapons, "specialisations": specialisations}
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")


def _multiclass_total_hp(rolls: list[int], con_mod: int) -> int:
    """Multi-class L1 HP: floor(avg of class rolls) + CON mod, min 1."""
    if not rolls:
        return 0
    return max(1, sum(rolls) // len(rolls) + con_mod)


def _hp_context(draft: dict[str, Any], data) -> dict:
    """Per-class HP rolls + total for the Class Setup HP section. Rolls are
    None until the locked roll happens."""
    ruleset = _ruleset_of(draft)
    con_mod = ability_modifier(_creation_abilities(draft, data)["CON"])
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]
    is_multi = len(ids) > 1

    rolls_for_template: list[dict] = []
    total = None
    if is_multi:
        existing = draft.get("hp_rolls", [None] * len(ids))
        for cls, roll_val in zip(classes, existing):
            rolls_for_template.append({
                "class_name": cls.name, "hit_die": cls.hit_die, "roll": roll_val,
            })
        if existing and all(r is not None for r in existing):
            total = _multiclass_total_hp(existing, con_mod)
    else:
        rolls_for_template.append({
            "class_name": classes[0].name, "hit_die": classes[0].hit_die,
            "roll": draft.get("hp_roll"),
        })
        if "hp_roll" in draft:
            total = max(1, draft["hp_roll"] + con_mod)

    blessed = (draft.get("race_id") == "human" and ruleset.human_racial_abilities)
    return {
        "is_multi": is_multi,
        "hp_class_name": " / ".join(c.name for c in classes),
        "hit_die": classes[0].hit_die,
        "con_mod": con_mod,
        "rolls": rolls_for_template,
        "total_hp": total,
        "reroll_rule": ruleset.reroll_1s_2s_hp_l1,
        "blessed": blessed,
        "hp_done": (total is not None),
    }


@router.get("/{draft_id}/class_setup", response_class=HTMLResponse)
async def get_class_setup(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "class_setup", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "class_setup")
    ctx.update(_hp_context(draft, data))
    # Proficiency section (only when the rule is on).
    ctx["show_proficiencies"] = ruleset.weapon_proficiency
    if ruleset.weapon_proficiency:
        ctx.update(_proficiency_context(draft, data))
        ctx["proficiencies_done"] = "proficiencies" in draft
    else:
        ctx["proficiencies_done"] = True
    # Spell section (only when a picked class casts at L1).
    ctx["show_spells"] = bool(draft.get("spellcasting"))
    if draft.get("spellcasting"):
        ctx["caster_classes"] = _caster_entries(draft, data)
        ctx["spells_done"] = bool(draft.get("spells_done"))
    else:
        ctx["spells_done"] = True
    ctx["ready"] = _class_setup_complete(draft)
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if _has_hp(draft):
        # HP is rolled once and locked (like abilities and gold). To change it
        # the player cancels and starts over.
        raise HTTPException(400, "Hit points are already rolled and locked.")
    data = request.app.state.game_data
    ruleset = _ruleset_of(draft)
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]

    blessed = (draft.get("race_id") == "human" and ruleset.human_racial_abilities)
    min_die = 3 if ruleset.reroll_1s_2s_hp_l1 else 1
    rolls = roll_first_level_hp(
        [c.hit_die for c in classes], blessed=blessed, min_die=min_die,
    )

    if len(ids) == 1:
        draft["hp_roll"] = rolls[0]
        draft.pop("hp_rolls", None)
    else:
        draft["hp_rolls"] = rolls
        draft.pop("hp_roll", None)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")


@router.post("/{draft_id}/hp")
async def post_hp(request: Request, draft_id: str):
    """Single 'Continue' action for the Class Setup page. Advances only when
    every applicable section is complete; otherwise bounces back to the page
    via _next_incomplete_step."""
    draft = _load(request, draft_id)
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Spells (optional step; only when a picked class casts at L1) ───────────

def _caster_entries(draft: dict[str, Any], data) -> list[dict]:
    """Per-casting-class rendering rows for the spells step."""
    abilities = draft["abilities"]
    ruleset = _ruleset_of(draft)
    int_score = abilities.get("INT", 10)
    books = draft.get("spellbooks", {})
    rows: list[dict] = []
    for cid in _class_ids(draft):
        cls = data.classes[cid]
        if not _casts_at_level_1(cls):
            continue
        entry = ClassEntry(class_id=cid, level=1, spellbook=books.get(cid, []))
        ctype = spell_engine.caster_type_of(cls, data)
        candidates = sorted(
            (s for s in data.spells.values()
             if set(s.spell_lists) & set(cls.spell_lists)
             and s.level in spell_engine.accessible_levels(entry, cls)),
            key=lambda s: (s.level, s.name),
        )
        rows.append({
            "class_id": cid,
            "class_name": cls.name,
            "caster_type": ctype,
            "required": (spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
                         if ctype == "arcane" else 0),
            "advanced": ruleset.advanced_spell_books,
            "candidates": [{"id": s.id, "name": s.name, "level": s.level,
                            "description": s.description,
                            "selected": s.id in books.get(cid, [])}
                           for s in candidates],
        })
    return rows



@router.post("/{draft_id}/spells")
async def post_spells(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    int_score = draft["abilities"].get("INT", 10)
    ruleset = _ruleset_of(draft)
    books: dict[str, list[str]] = dict(draft.get("spellbooks", {}))

    for cid in _class_ids(draft):
        cls = data.classes[cid]
        if not _casts_at_level_1(cls):
            continue
        entry = ClassEntry(class_id=cid, level=1)
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype != "arcane":
            # Divine casters know their whole list; there is no spellbook to
            # build, so nothing is chosen here.
            books[cid] = []
            continue
        chosen = form.getlist(f"spell_{cid}")
        chosen = list(dict.fromkeys(chosen))
        required = spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
        if len(chosen) != required:
            raise HTTPException(
                400, f"{cls.name} must choose exactly {required} starting spell(s); "
                     f"got {len(chosen)}."
            )
        accessible = spell_engine.accessible_levels(entry, cls)
        for sid in chosen:
            spell = data.spells.get(sid)
            if spell is None or not (set(spell.spell_lists) & set(cls.spell_lists)) \
                    or spell.level not in accessible:
                raise HTTPException(400, f"{sid!r} is not a valid {cls.name} starting spell.")
        books[cid] = chosen

    draft["spellbooks"] = books
    draft["spells_done"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Equipment (always-on step right before Review) ────────────────────────

def _draft_magic(draft: dict[str, Any]) -> list[MagicItemInstance]:
    return [MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])]


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
    classes = [game_data.classes[cid] for cid in _class_ids(draft)
               if cid in game_data.classes]
    return {
        "gold": draft.get("gold", 0),
        "gold_locked": draft.get("gold_locked", False),
        "inventory_view": inventory_view(
            inventory, stashed, equipped, equipped_weapons, containers, game_data,
            allowed_weapons=allowed_weapon_ids(classes, game_data),
            allowed_armor=allowed_armor_ids(classes, game_data),
            allow_shields=shields_allowed(classes),
        ),
        "magic_items_view": magic_items_view(
            _draft_magic(draft), list(inventory), game_data,
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
        if needs_instance(item):
            magic_items = add_free_magic_item(_draft_magic(draft), item_id, data)
            draft["magic_items"] = [m.model_dump() for m in magic_items]
        elif isinstance(item, Container):
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
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    try:
        new_eq, new_weapons = _equip(
            draft.get("inventory", []),
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            item_id, data,
            allowed_weapons=allowed_weapon_ids(classes, data),
            allowed_armor=allowed_armor_ids(classes, data),
            allow_shields=shields_allowed(classes),
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


@router.post("/{draft_id}/equipment/stow")
async def equipment_stow(request: Request, draft_id: str,
                         instance_id: str = Form(...),
                         item_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_inv, new_stashed, new_containers = shop_stow(
            draft.get("inventory", []),
            draft.get("stashed", []),
            containers,
            draft.get("equipped", {}),
            draft.get("equipped_weapons", []),
            instance_id, item_id, request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = new_inv
    draft["stashed"] = new_stashed
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/take-out")
async def equipment_take_out(request: Request, draft_id: str,
                             instance_id: str = Form(...),
                             item_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_inv, new_stashed, new_containers = shop_take_out(
            draft.get("inventory", []),
            draft.get("stashed", []),
            containers, instance_id, item_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = new_inv
    draft["stashed"] = new_stashed
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/stash-container")
async def equipment_stash_container(request: Request, draft_id: str,
                                    instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_containers = shop_stash_container(containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/unstash-container")
async def equipment_unstash_container(request: Request, draft_id: str,
                                      instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_containers = shop_unstash_container(containers, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in new_containers]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/remove-container")
async def equipment_remove_container(request: Request, draft_id: str,
                                     instance_id: str = Form(...),
                                     mode: str = Form(...)):
    draft = _load(request, draft_id)
    containers = [ContainerInstance.model_validate(c)
                  for c in draft.get("containers", [])]
    try:
        new_containers, new_gold = shop_remove_container(
            containers, draft.get("gold", 0), instance_id, mode,
            request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in new_containers]
    draft["gold"] = new_gold
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/equip-magic")
async def wiz_equip_magic(request: Request, draft_id: str, instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    try:
        items = _equip_magic(_draft_magic(draft), instance_id, request.app.state.game_data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/unequip-magic")
async def wiz_unequip_magic(request: Request, draft_id: str, instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    try:
        items = _unequip_magic(_draft_magic(draft), instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/use-charge")
async def wiz_use_charge(request: Request, draft_id: str, instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    try:
        items = _use_charge(_draft_magic(draft), instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/reset-charges")
async def wiz_reset_charges(request: Request, draft_id: str, instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    try:
        items = _reset_charges(_draft_magic(draft), instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/remove-magic")
async def wiz_remove_magic(request: Request, draft_id: str,
                           instance_id: str = Form(...), mode: str = Form("drop")):
    draft = _load(request, draft_id)
    try:
        items, gold = _remove_magic(
            _draft_magic(draft), draft.get("gold", 0), instance_id, mode,
            request.app.state.game_data,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    draft["gold"] = gold
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/magic-note")
async def wiz_magic_note(request: Request, draft_id: str,
                         instance_id: str = Form(...), note: str = Form("")):
    draft = _load(request, draft_id)
    try:
        items = _set_magic_note(_draft_magic(draft), instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["magic_items"] = [m.model_dump() for m in items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/move")
async def equipment_move(request: Request, draft_id: str,
                         source: str = Form(...),
                         target: str = Form(...),
                         item_id: str = Form(""),
                         instance_id: str = Form("")):
    draft = _load(request, draft_id)
    game_data = request.app.state.game_data

    class _DraftShim:
        pass

    shim = _DraftShim()
    shim.inventory = draft.get("inventory", [])
    shim.stashed = draft.get("stashed", [])
    shim.equipped = draft.get("equipped", {})
    shim.equipped_weapons = draft.get("equipped_weapons", [])
    shim.containers = [ContainerInstance.model_validate(c)
                       for c in draft.get("containers", [])]
    classes = [game_data.classes[cid] for cid in _class_ids(draft)
               if cid in game_data.classes]
    try:
        dispatch_move(shim, source, target, item_id, instance_id, game_data,
                      allowed_weapons=allowed_weapon_ids(classes, game_data),
                      allowed_armor=allowed_armor_ids(classes, game_data),
                      allow_shields=shields_allowed(classes))
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["inventory"] = shim.inventory
    draft["stashed"] = shim.stashed
    draft["equipped"] = shim.equipped
    draft["equipped_weapons"] = shim.equipped_weapons
    draft["containers"] = [c.model_dump() for c in shim.containers]
    save_draft(draft_id, draft, request.app.state.drafts_dir)
    return RedirectResponse(f"/wizard/{draft_id}/equipment", status_code=303)


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


def _draft_to_spec(draft: dict[str, Any], data) -> CharacterSpec:
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

    books = draft.get("spellbooks", {})
    classes = [
        ClassEntry(class_id=cid, level=1, hp_rolls=[hp_rolls[i]],
                   spellbook=list(books.get(cid, [])))
        for i, cid in enumerate(ids)
    ]
    return CharacterSpec(
        name=draft["name"],
        abilities=_creation_abilities(draft, data),
        race_id=draft["race_id"],
        classes=classes,
        alignment=draft["alignment"],
        secondary_skill=draft.get("secondary_skill"),
        languages=list(draft.get("languages", [])),
        weapon_proficiencies=list((draft.get("proficiencies") or {}).get("weapons", [])),
        weapon_specialisations=list((draft.get("proficiencies") or {}).get("specialisations", [])),
        gold=draft.get("gold", 0),
        inventory=list(draft.get("inventory", [])),
        stashed=list(draft.get("stashed", [])),
        equipped=dict(draft.get("equipped", {})),
        equipped_weapons=list(draft.get("equipped_weapons", [])),
        containers=[
            ContainerInstance.model_validate(c) for c in draft.get("containers", [])
        ],
        magic_items=[
            MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])
        ],
        ruleset=ruleset,
    )


@router.get("/{draft_id}/review", response_class=HTMLResponse)
async def get_review(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "review", draft_id)
    if redirect:
        return redirect
    from aose.sheet.view import build_sheet
    spec = _draft_to_spec(draft, request.app.state.game_data)
    sheet = build_sheet(spec, request.app.state.game_data)
    ctx = _base_context(request, draft_id, draft, "review")
    ctx["sheet"] = sheet
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/finalize")
async def post_finalize(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    characters_dir = _characters_dir(request)
    char_id = unique_character_id(slugify(spec.name), characters_dir)
    save_character(char_id, spec, characters_dir)
    delete_draft(draft_id, _drafts_dir(request))
    return _redirect(f"/character/{char_id}")


@router.post("/{draft_id}/cancel")
async def post_cancel(request: Request, draft_id: str):
    delete_draft(draft_id, _drafts_dir(request))
    return _redirect("/")
