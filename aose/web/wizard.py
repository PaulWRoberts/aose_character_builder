import random
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from aose.web.templating import make_templates

from aose.web.book import class_entry, race_entry, spell_entry
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
from aose.engine.dice import (
    roll_3d6_in_order_detailed,
    roll_blessed_hp_sets,
    roll_first_level_hp,
    roll_hp,
)
from aose.engine.enchant import (
    _kind_of_instance as _enchanted_kind,
)
from aose.engine.equip import WieldError
from aose.engine.feature_choices import ChoiceError, roll_choice, validate_choice
from aose.engine.magic import (
    add_free_magic_item,
    needs_instance,
)
from aose.engine.proficiency import (
    allowed_armor_ids,
    allowed_weapon_ids,
    base_weapon_id,
    category_for_classes,
    shields_allowed,
    specialisation_allowed,
    total_proficiency_slots,
    two_weapon_eligible,
)
from aose.engine.shop import (
    ContainerView,
    InsufficientFunds,
    REMOVE_MODES,
    UnknownItem,
    add_free_item as shop_add_free_item,
    buy_item as shop_buy_item,
    roll_starting_gold,
    shop_categories,
)
from aose.models import (
    Ability,
    CharacterSpec,
    ClassEntry,
    ContainerInstance,
    ItemInstance,
    MagicItemInstance,
    RuleSet,
)
from aose.engine.sources import (
    content_enabled,
    class_available,
    race_available,
    class_allowed_for_race,
    class_level_cap,
)
from aose.web.settings_routes import (
    _content_keys,
    _ruleset_view_context,
    parse_ruleset_from_form,
)

router = APIRouter(prefix="/wizard")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = make_templates(str(TEMPLATES_DIR))

STEP_LABELS = {
    "rules": "Rules",
    "abilities": "Abilities",
    "race": "Race",
    "class": "Class",
    "adjust": "Adjustments",
    "class_setup": "HP & Skills",
    "identity": "Identity",
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
    return request.state.drafts_dir


def _characters_dir(request: Request) -> Path:
    return request.state.characters_dir


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
    """True if the class casts at L1: has a spell list and either L1 spell slots
    (arcane/divine) or L1 mental powers known."""
    row = cls.progression.get(1)
    return bool(cls.spell_lists) and bool(row and (row.spell_slots or row.powers_known))


# ── Downstream-clear helpers (used when the user navigates back and changes
# an earlier choice — keeps the draft from carrying stale data) ───────────

def _clear_after_abilities(draft: dict[str, Any]) -> None:
    for k in ("race_id", "class_id", "class_ids", "ability_adjustments",
              "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done", "languages",
              "feature_choices", "_has_feature_choices", "_feature_choice_group_ids", "_roll_group_ids"):
        draft.pop(k, None)


def _clear_after_race(draft: dict[str, Any]) -> None:
    for k in ("class_id", "class_ids", "ability_adjustments",
              "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done", "languages",
              "feature_choices", "_has_feature_choices", "_feature_choice_group_ids", "_roll_group_ids"):
        draft.pop(k, None)


def _clear_after_class(draft: dict[str, Any]) -> None:
    # A class change can invalidate the chosen alignment (e.g. picking paladin
    # after choosing chaos). name and secondary_skill don't depend on class.
    for k in ("ability_adjustments", "hp_roll", "hp_rolls", "proficiencies",
              "spellcasting", "spellbooks", "spells_done", "alignment", "languages",
              "feature_choices", "_has_feature_choices", "_feature_choice_group_ids", "_roll_group_ids"):
        draft.pop(k, None)


def _feature_choices_complete(draft: dict[str, Any]) -> bool:
    """Every required feature-choice group has a rolled (or overridden) entry."""
    group_ids = draft.get("_feature_choice_group_ids", [])
    chosen = draft.get("feature_choices", {})
    return all(gid in chosen for gid in group_ids)


def _class_setup_complete(draft: dict[str, Any]) -> bool:
    """The consolidated Class Setup step is complete when HP is rolled AND
    weapon proficiencies are chosen (if the rule is on) AND starting spells are
    chosen (if any picked class casts at L1) AND feature choices are made (if
    any picked class/race has feature_choices groups)."""
    rs = _ruleset_of(draft)
    if not _has_hp(draft):
        return False
    if rs.weapon_proficiency and "proficiencies" not in draft:
        return False
    if draft.get("spellcasting") and not draft.get("spells_done"):
        return False
    if draft.get("_has_feature_choices") and not _feature_choices_complete(draft):
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
    if "abilities" not in draft or not draft.get("abilities_confirmed"):
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

    floor_idx = _strict_floor_index(draft, steps)
    step_states: list[dict] = []
    for i, step in enumerate(steps):
        if step == current_step:
            state = "current"
        elif i < next_idx:
            state = "locked" if i < floor_idx else "done"
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


def _strict_floor_index(draft: dict[str, Any], steps: list[str]) -> int:
    """Earliest step index navigable under Strict Mode (0 when Strict is off).

    Rolling abilities locks the rules step; rolling HP locks every step before
    the HP page (``class_setup``). The floor only ever rises."""
    if not _ruleset_of(draft).strict_mode:
        return 0
    floor = 0
    if "abilities" in draft:
        floor = max(floor, steps.index("abilities"))
    if _has_hp(draft):
        floor = max(floor, steps.index("class_setup"))
    return floor


def _strict_back_gate(draft: dict[str, Any], step: str,
                      draft_id: str) -> RedirectResponse | None:
    """Redirect forward when *step* is below the Strict-Mode lock floor."""
    steps = _wizard_steps(draft)
    if step not in steps:
        return None
    if steps.index(step) < _strict_floor_index(draft, steps):
        return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")
    return None


def _seed_draft_abilities(draft: dict[str, Any]) -> None:
    """Roll 3d6 in order and store the six scores on the draft.

    Abilities are always 3d6 down the line — there are no alternate methods,
    and the roll is locked once the draft exists.

    The individual dice are stashed in ``draft["ability_dice"]`` (draft-only,
    never persisted to the character) so the abilities step can show what each
    die rolled.
    """
    names = [a.value for a in ABILITY_ORDER]
    dice = roll_3d6_in_order_detailed()
    draft["abilities"] = {name: sum(d) for name, d in zip(names, dice)}
    draft["ability_dice"] = {name: d for name, d in zip(names, dice)}


@router.get("/new")
async def new_wizard(request: Request):
    draft_id = new_draft_id()
    ruleset = load_settings(request.state.settings_path)
    # Abilities are rolled by the player on the abilities step, not here.
    draft: dict[str, Any] = {"ruleset": ruleset.model_dump()}
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/rules")


# ── Per-character ruleset (always the first step) ─────────────────────────

@router.get("/{draft_id}/rules", response_class=HTMLResponse)
async def get_rules(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "rules", draft_id)
    if blocked:
        return blocked
    ruleset = _ruleset_of(draft)
    ctx = _base_context(request, draft_id, draft, "rules")
    ctx.update(_ruleset_view_context(request, ruleset))
    return templates.TemplateResponse(request, "wizard.html", ctx)


def _apply_rule_changes(draft: dict[str, Any], old_rs: RuleSet, new_rs: RuleSet, data=None) -> None:
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

    # Equipment clears apply regardless of how far through the wizard the draft is.
    if old_rs.two_weapon_fighting and not new_rs.two_weapon_fighting and data is not None:
        from aose.models import Weapon as _W
        items = [ItemInstance.model_validate(i) for i in draft.get("items", [])]
        changed = False
        for inst in items:
            if inst.equip == "off_hand":
                base = data.items.get(inst.catalog_id)
                if isinstance(base, _W):
                    inst.equip = None
                    changed = True
        if changed:
            draft["items"] = [i.model_dump() for i in items]

    if "abilities" not in draft:
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
        draft.pop("languages", None)

    if new_rs.weapon_proficiency != old_rs.weapon_proficiency:
        draft.pop("proficiencies", None)

    if old_rs.combat_talents and not new_rs.combat_talents:
        fc = dict(draft.get("feature_choices", {}))
        removed = fc.pop("combat_talents", [])
        draft["feature_choices"] = fc
        # Drop talent-granted specialisation(s) and Slayer params.
        if "weapon_specialist" in removed:
            draft["weapon_specialisations"] = []
        draft["choice_params"] = {k: v for k, v in draft.get("choice_params", {}).items()
                                  if k not in removed}

    if old_rs.cantrips and not new_rs.cantrips and data is not None:
        books = dict(draft.get("spellbooks", {}))
        for cid, ids in books.items():
            books[cid] = [sid for sid in ids
                          if sid in data.spells and data.spells[sid].level != 0]
        draft["spellbooks"] = books

    if not new_rs.multiclassing and "class_ids" in draft:
        _clear_after_race(draft)

    if data is not None and new_rs.disabled_content != old_rs.disabled_content:
        race_id = draft.get("race_id")
        if race_id in data.races and not content_enabled(
            data.races[race_id].source, "classes", new_rs
        ):
            _clear_after_abilities(draft)
            return
        for cid in _class_ids(draft):
            if cid in data.classes and not content_enabled(
                data.classes[cid].source, "classes", new_rs
            ):
                _clear_after_race(draft)
                break


@router.post("/{draft_id}/rules")
async def post_rules(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "rules", draft_id)
    if blocked:
        return blocked
    form = await request.form()
    new_rs = parse_ruleset_from_form(form, content_keys=_content_keys(request))
    old_rs = _ruleset_of(draft)
    _apply_rule_changes(draft, old_rs, new_rs, request.app.state.game_data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


@router.post("/{draft_id}/abilities/roll")
async def post_abilities_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "abilities", draft_id)
    if blocked:
        return blocked
    if "abilities" in draft:
        warn = ability_warnings(draft["abilities"])
        hopeless = warn["subpar"] or bool(warn["rock_bottom"])
        if _ruleset_of(draft).strict_mode and not hopeless:
            raise HTTPException(400, "Ability scores are already rolled and locked.")
    _clear_after_abilities(draft)
    draft.pop("abilities_confirmed", None)
    _seed_draft_abilities(draft)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/abilities")


@router.get("/{draft_id}/abilities", response_class=HTMLResponse)
async def get_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "abilities", draft_id)
    if blocked:
        return blocked
    ctx = _base_context(request, draft_id, draft, "abilities")
    rolled = "abilities" in draft
    ctx["abilities_rolled"] = rolled
    if rolled:
        ability_dice = draft.get("ability_dice", {})
        ctx["ability_rows"] = [
            {
                "name": ab.value,
                "score": draft["abilities"][ab.value],
                "modifier": ability_modifier(draft["abilities"][ab.value]),
                "dice": ability_dice.get(ab.value),
            }
            for ab in ABILITY_ORDER
        ]
        warn = ability_warnings(draft["abilities"])
        ctx.update(warn)  # subpar, rock_bottom
        hopeless = warn["subpar"] or bool(warn["rock_bottom"])
        ctx["can_reroll"] = (not _ruleset_of(draft).strict_mode) or hopeless
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/abilities")
async def post_abilities(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "abilities", draft_id)
    if blocked:
        return blocked
    if "abilities" not in draft:
        return _redirect(f"/wizard/{draft_id}/abilities")
    draft["abilities_confirmed"] = True
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


def _ability_summary(abilities: dict[str, int]) -> list[dict[str, int | str]]:
    """Six-entry strip (name/score/modifier) for the race & class step header."""
    return [
        {
            "name": ab.value,
            "score": abilities[ab.value],
            "modifier": ability_modifier(abilities[ab.value]),
        }
        for ab in ABILITY_ORDER
    ]


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
    blocked = _strict_back_gate(draft, "race", draft_id)
    if blocked:
        return blocked
    redirect = _gate(draft, "race", draft_id)
    if redirect:
        return redirect
    data = request.app.state.game_data
    abilities = draft["abilities"]
    ruleset = _ruleset_of(draft)
    races = []
    for race in sorted(data.races.values(), key=lambda r: r.name):
        if not race_available(race, ruleset):
            continue
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
        meets = _meets_ability_requirements(race.ability_requirements, abilities)
        races.append({
            "id": race.id,
            "name": race.name,
            "infravision": race.infravision,
            "base_movement": race.base_movement,
            "requirements": {ab.value: v for ab, v in race.ability_requirements.items()},
            "languages": race.languages,
            "ability_changes": ability_changes,
            "meets_requirements": meets,
            "selected": draft.get("race_id") == race.id,
            "entry": race_entry(race),
            "select_reason": None if meets else "Ability requirements not met",
        })
    ctx = _base_context(request, draft_id, draft, "race")
    ctx["races"] = races
    ctx["ability_summary"] = _ability_summary(abilities)
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/race")
async def post_race(request: Request, draft_id: str, race_id: str = Form(...)):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "race", draft_id)
    if blocked:
        return blocked
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



@router.get("/{draft_id}/class", response_class=HTMLResponse)
async def get_class(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "class", draft_id)
    if blocked:
        return blocked
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
        if cls.id == "normal_human":   # retainer-only class; not player-choosable
            continue
        if not class_available(cls, ruleset):
            continue

        meets_abilities = _meets_ability_requirements(cls.ability_requirements, abilities)

        if ruleset.separate_race_class:
            allowed_by_race = class_allowed_for_race(cls.id, race, ruleset)
            level_cap = class_level_cap(race, cls.id, ruleset)
        else:
            allowed_by_race = True  # no race chosen yet
            level_cap = None         # race caps don't bind a race-as-class entry

        if not allowed_by_race:
            reason = f"Not available to {race_name}"
        elif not meets_abilities:
            reason = "Ability requirements not met"
        else:
            reason = None
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
            "entry": class_entry(cls),
            "select_reason": reason,
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
    ctx["ability_summary"] = _ability_summary(abilities)
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
    blocked = _strict_back_gate(draft, "class", draft_id)
    if blocked:
        return blocked
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
            if not class_allowed_for_race(cid, race, ruleset):
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
    groups = _active_choice_groups(draft, data)
    draft["_has_feature_choices"] = bool(groups)
    draft["_feature_choice_group_ids"] = [g.id for g in groups]
    # Only roll-dice groups block rolls_ready; pick-only groups are validated client-side.
    draft["_roll_group_ids"] = [g.id for g in groups if g.roll_dice]
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
        score = post_racial[name]
        raisable = name in adj["raisable"]
        lowerable = name in adj["lowerable"]
        floor = _ability_floor(name, classes) if lowerable else None

        raise_options = []
        if raisable:
            raise_options = [
                {"amount": amt, "final": score + amt}
                for amt in range(0, 18 - score + 1)
            ]
        lower_options = []
        if lowerable:
            lower_options = [
                {"amount": amt, "final": score - amt}
                for amt in range(0, score - floor + 1, 2)
            ]

        rows.append({
            "name": name,
            "score": score,
            "raisable": raisable,
            "lowerable": lowerable,
            "floor": floor,
            "raise_val": delta if delta > 0 else 0,
            "lower_val": -delta if delta < 0 else 0,
            "raise_options": raise_options,
            "lower_options": lower_options,
        })
    return {"adjust_rows": rows}


@router.get("/{draft_id}/adjust", response_class=HTMLResponse)
async def get_adjust(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    blocked = _strict_back_gate(draft, "adjust", draft_id)
    if blocked:
        return blocked
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
    blocked = _strict_back_gate(draft, "adjust", draft_id)
    if blocked:
        return blocked
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
    draft.pop("languages", None)  # final INT may have changed
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Secondary skill helpers (reused by identity routes) ────────────────────

def _available_skills(request: Request) -> list[str]:
    from aose.engine.secondary_skills import selectable_names
    return selectable_names(request.app.state.game_data.secondary_skills)


def _roll_skill(request: Request) -> list[str] | None:
    from aose.engine.secondary_skills import roll
    entries = request.app.state.game_data.secondary_skills
    if not entries:
        return None
    return roll(entries)


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


def _draft_spec_for_languages(draft: dict[str, Any], data):
    """A throwaway CharacterSpec for granted_languages lookup (race + classes).
    Returns None if the draft has no race/class chosen yet."""
    from aose.models import CharacterSpec, ClassEntry

    race_id = draft.get("race_id")
    class_ids = draft.get("class_ids") or ([draft["class_id"]] if draft.get("class_id") else [])
    if not race_id or not class_ids:
        return None
    abil = _creation_abilities(draft, data)
    return CharacterSpec(
        name=draft.get("name") or "draft",
        abilities=abil,
        race_id=race_id,
        alignment=draft.get("alignment") or "neutral",
        classes=[ClassEntry(class_id=c, level=1, hp_rolls=[1]) for c in class_ids],
    )


def _languages_context(draft: dict[str, Any], data) -> dict:
    """Languages section state for the Identity page."""
    from aose.engine.languages import (
        additional_language_count,
        alignment_language,
        available_additional,
        broken_speech,
        display_name,
        granted_languages,
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

    # Granted (class/race feature) tongues are known, never learnable.
    spec_like = _draft_spec_for_languages(draft, data)
    granted = granted_languages(spec_like, data) if spec_like else []
    already.update(granted)

    chosen = draft.get("languages", [])
    options = [
        {"id": lang_id, "name": display_name(lang_id, data.languages)}
        for lang_id in available_additional(data.languages, already)
    ]
    return {
        "native_languages": [display_name(n, data.languages) for n in native],
        "alignment_language": align_tongue,
        "granted_languages": [display_name(g, data.languages) for g in granted],
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
        ctx["skills"] = skills
        ctx["skill_locked"] = rs.strict_mode
        ctx["skill_rolled"] = "secondary_skill" in draft
        ctx["current_skills"] = draft.get("secondary_skill") or []
    ctx.update(_languages_context(draft, data))
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/identity/skill-roll")
async def post_identity_skill_roll(request: Request, draft_id: str):
    """Roll the secondary skill. First roll allowed in every mode;
    Strict Mode refuses a re-roll once the skill is set (mirrors HP/gold)."""
    draft = _load(request, draft_id)
    rs = _ruleset_of(draft)
    if rs.strict_mode and "secondary_skill" in draft:
        raise HTTPException(400, "Secondary skill is locked in Strict Mode.")
    form = await request.form()

    name = (form.get("name") or "").strip()
    if name:
        draft["name"] = name

    data = request.app.state.game_data
    alignment = form.get("alignment")
    allowed = {o["id"] for o in _identity_alignment_options(draft, data)}
    if alignment in allowed:
        draft["alignment"] = alignment

    chosen_languages = list(dict.fromkeys(form.getlist("language")))
    if chosen_languages:
        draft["languages"] = chosen_languages

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
        if "secondary_skill" not in draft:
            raise HTTPException(400, "Roll your secondary skill first.")
        if not rs.strict_mode:
            submitted = form.get("secondary_skill")
            if submitted:
                if submitted not in _available_skills(request):
                    raise HTTPException(400, f"Unknown skill: {submitted!r}")
                draft["secondary_skill"] = [submitted]  # manual collapses to one

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


# ── Feature choices (CC3 pick/roll groups) ─────────────────────────────────

def _active_choice_groups(draft: dict[str, Any], data) -> list:
    """The FeatureChoice groups that apply: each class's groups, plus the race's
    groups in separate-race-class mode. Groups gated by ``requires_rule`` are
    excluded when that rule is off. In race-as-class mode the race groups
    don't apply — the class carries them."""
    rs = _ruleset_of(draft)
    groups = []
    for cid in _class_ids(draft):
        cls = data.classes.get(cid)
        if cls is not None:
            groups.extend(cls.feature_choices)
    if rs.separate_race_class:
        race = data.races.get(draft.get("race_id"))
        if race is not None:
            groups.extend(race.feature_choices)
    groups = [g for g in groups
              if not g.requires_rule or getattr(rs, g.requires_rule, False)]
    return groups


def _feature_choices_context(draft: dict[str, Any], data) -> dict:
    """Render rows for the Features section. Rolling is an explicit player
    action (see post_feature_choice_roll); nothing is auto-rolled here."""
    from aose.engine.feature_choices import effective_pick
    from aose.models import Weapon as _W
    from aose.engine.proficiency import base_weapon_id as _bwid, allowed_weapon_ids as _awi
    groups = _active_choice_groups(draft, data)
    rs = _ruleset_of(draft)
    chosen_map = dict(draft.get("feature_choices", {}))

    # Weapon options for param inputs on Weapon specialist.
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    allowed = _awi(classes, data, rs)
    feature_weapon_options = sorted(
        (
            {"id": i.id, "name": i.name}
            for i in data.items.values()
            if isinstance(i, _W) and _bwid(i) == i.id
            and (allowed == "all" or i.id in allowed)
        ),
        key=lambda w: w["name"],
    )

    rows = []
    for g in groups:
        chosen = set(chosen_map.get(g.id, []))
        pick = effective_pick(g, 1)  # creation is always level 1
        rows.append({
            "id": g.id, "name": g.name, "text": g.text, "pick": pick,
            "cosmetic": g.cosmetic, "roll_dice": g.roll_dice,
            "rolled": g.id in chosen_map,
            "options": [
                {"id": o.id, "name": o.name, "text": o.text,
                 "selected": o.id in chosen,
                 "param": (o.param.model_dump() if o.param else None)}
                for o in g.options
                if not (o.excluded_when_rule and getattr(rs, o.excluded_when_rule, False))
            ],
        })
    return {
        "feature_groups": rows,
        "feature_choices_locked": rs.strict_mode,
        "has_feature_choices": bool(groups),
        # Pick-only groups (no roll table, e.g. Combat Talents) are a deliberate
        # selection, not a roll — Strict Mode never locks them.
        "has_pick_groups": any(not g.roll_dice for g in groups),
        "feature_weapon_options": feature_weapon_options,
    }


# ── Weapon proficiencies (optional, gated by ruleset.weapon_proficiency) ──

def _proficiency_context(draft: dict[str, Any], data) -> dict:
    """Slots, weapon options (filtered to class allowances), and specialise
    flag for the proficiency step."""
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]                 # creation = level 1
    required = total_proficiency_slots(pairs)
    allow_special = specialisation_allowed(classes)
    allowed = allowed_weapon_ids(classes, data, _ruleset_of(draft))
    from aose.models import Weapon
    # Proficiency is per base weapon type; magic variants (Sword +1, …) share
    # their base weapon's proficiency, so only offer base weapons here.
    weapons = sorted(
        (i for i in data.items.values()
         if isinstance(i, Weapon) and base_weapon_id(i) == i.id),
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
            "qualities": ", ".join(sorted(w.quality_ids)),
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



def _apply_proficiencies(draft: dict[str, Any], form, data) -> None:
    weapons = list(dict.fromkeys(form.getlist("weapon")))
    specialisations = list(dict.fromkeys(form.getlist("specialise")))
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids if cid in data.classes]
    pairs = [(c, 1) for c in classes]
    required = total_proficiency_slots(pairs)
    allowed = allowed_weapon_ids(classes, data, _ruleset_of(draft))
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


@router.post("/{draft_id}/proficiencies")
async def post_proficiencies(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    _apply_proficiencies(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")


def _apply_feature_overrides(draft: dict[str, Any], form, data) -> None:
    """Validate & merge submitted feature picks (non-strict manual override).
    Only groups present in the form are touched; others keep their rolled value."""
    from aose.engine.feature_choices import effective_pick
    rs = _ruleset_of(draft)
    groups = {g.id: g for g in _active_choice_groups(draft, data)}
    chosen_map = dict(draft.get("feature_choices", {}))
    params = dict(draft.get("choice_params", {}))
    specials = list(draft.get("weapon_specialisations", []))
    for gid, g in groups.items():
        field = form.getlist(f"choice_{gid}")
        if not field:
            continue
        # Strict Mode locks rolls: a roll-table group can't be hand-edited once
        # set. Pick-only groups (no roll table) stay editable in every mode.
        if rs.strict_mode and g.roll_dice:
            continue
        picked = list(dict.fromkeys(field))
        try:
            validate_choice(g, picked, pick=effective_pick(g, 1))
        except ChoiceError as e:
            raise HTTPException(400, str(e))
        chosen_map[gid] = picked
        for opt in g.options:
            if opt.id not in picked or opt.param is None:
                continue
            raw = (form.get(f"param_{opt.id}") or "").strip()
            if not raw:
                raise HTTPException(400, f"{opt.name}: choose {opt.param.label}.")
            if opt.param.kind == "weapon":
                if raw not in specials:
                    specials.append(raw)
            else:
                params[opt.id] = raw
    draft["feature_choices"] = chosen_map
    draft["choice_params"] = params
    draft["weapon_specialisations"] = specials


@router.post("/{draft_id}/feature-choices")
async def post_feature_choices(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    if _ruleset_of(draft).strict_mode:
        raise HTTPException(400, "Feature choices are locked in Strict Mode.")
    form = await request.form()
    _apply_feature_overrides(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/class_setup")


@router.post("/{draft_id}/feature-choices/roll")
async def post_feature_choice_roll(request: Request, draft_id: str):
    """Roll a single feature-choice table. First roll allowed in every mode;
    Strict Mode refuses a re-roll once the group is set (mirrors HP/gold)."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    group_id = form.get("group_id")
    groups = {g.id: g for g in _active_choice_groups(draft, data)}
    if group_id not in groups:
        raise HTTPException(400, f"Unknown feature group '{group_id}'")
    chosen = dict(draft.get("feature_choices", {}))
    if _ruleset_of(draft).strict_mode and group_id in chosen:
        raise HTTPException(400, "Feature is already rolled and locked (Strict Mode).")
    chosen[group_id] = roll_choice(groups[group_id])
    draft["feature_choices"] = chosen
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
    blessed_sets = None
    raw_sets = draft.get("hp_blessed_sets")
    if raw_sets and len(raw_sets) == 2:
        totals = [sum(s) for s in raw_sets]
        higher_idx = 0 if totals[0] >= totals[1] else 1
        blessed_sets = [
            {"rolls": s, "total": t, "higher": (i == higher_idx)}
            for i, (s, t) in enumerate(zip(raw_sets, totals))
        ]
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
        "blessed_sets": blessed_sets,
        "can_reroll_hp": not ruleset.strict_mode,
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
    # Feature choices (CC3 pick/roll groups).
    choice_ctx = _feature_choices_context(draft, data)
    ctx.update(choice_ctx)
    ctx["features_done"] = _feature_choices_complete(draft)
    # Pick-only groups (no roll_dice) are validated client-side; only groups
    # that require a server-side roll block rolls_ready.
    roll_group_ids = draft.get("_roll_group_ids", [])
    chosen = draft.get("feature_choices", {})
    ctx["rolls_ready"] = (
        ctx["hp_done"]
        and all(gid in chosen for gid in roll_group_ids)
    )
    ctx["ready"] = _class_setup_complete(draft)
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/hp/roll")
async def post_hp_roll(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    ruleset = _ruleset_of(draft)
    if _has_hp(draft) and ruleset.strict_mode:
        raise HTTPException(400, "Hit points are already rolled and locked.")
    data = request.app.state.game_data
    ids = _class_ids(draft)
    classes = [data.classes[cid] for cid in ids]
    hit_dice = [c.hit_die for c in classes]

    blessed = (draft.get("race_id") == "human" and ruleset.human_racial_abilities)
    min_die = 3 if ruleset.reroll_1s_2s_hp_l1 else 1

    if blessed:
        set_a, set_b = roll_blessed_hp_sets(hit_dice, min_die=min_die)
        rolls = set_a if sum(set_a) >= sum(set_b) else set_b
        draft["hp_blessed_sets"] = [set_a, set_b]
    else:
        rolls = roll_first_level_hp(hit_dice, blessed=False, min_die=min_die)
        draft.pop("hp_blessed_sets", None)

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
    """Single 'Next' action for Class Setup. Sections declared via hidden
    ``section`` markers are validated and saved here; sections saved earlier
    via their own routes are left untouched. Advances only when every
    applicable section is complete."""
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    sections = set(form.getlist("section"))
    if "proficiencies" in sections:
        _apply_proficiencies(draft, form, data)
    if "spells" in sections:
        _apply_spells(draft, form, data)
    if "features" in sections:
        # _apply_feature_overrides itself leaves rolled groups locked under
        # Strict Mode; pick-only groups (Combat Talents) remain editable.
        _apply_feature_overrides(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
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
        enabled_lists = {
            lid for lid in cls.spell_lists
            if lid in data.spell_lists
            and content_enabled(data.spell_lists[lid].source, "classes", ruleset)
        }
        accessible = spell_engine.accessible_levels(entry, cls)
        demoted = (spell_engine.DEMOTED_READ_MAGIC_IDS
                   if spell_engine._read_magic_demoted(cls, data, ruleset) else set())
        candidates = sorted(
            (s for s in data.spells.values()
             if set(s.spell_lists) & enabled_lists
             and (ctype == "mental" or s.level in accessible)
             and s.id not in demoted),
            key=lambda s: (s.level, s.name),
        )
        is_dedicated = (ctype == "arcane"
                        and spell_engine.is_dedicated_arcane(cls, data))
        cantrip_required = (spell_engine.beginning_cantrip_count(entry, cls, data, ruleset)
                            if is_dedicated else 0)
        cantrip_candidates = []
        if cantrip_required:
            hide = set()
            if ruleset.read_magic_cantrip:
                hide = spell_engine.DEMOTED_READ_MAGIC_IDS | {spell_engine.READ_MAGIC_CANTRIP_ID}
            cantrip_candidates = [
                {"id": s.id, "name": s.name, "level": s.level,
                 "description": s.description,
                 "entry": spell_entry(s),
                 "selected": s.id in books.get(cid, [])}
                for s in sorted(
                    (sp for sp in data.spells.values()
                     if sp.level == 0 and set(sp.spell_lists) & enabled_lists
                     and sp.id not in hide),
                    key=lambda sp: sp.name,
                )
            ]
        rows.append({
            "class_id": cid,
            "class_name": cls.name,
            "caster_type": ctype,
            "required": (spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
                         if ctype in ("arcane", "mental") else 0),
            "advanced": ruleset.advanced_spell_books,
            "candidates": [{"id": s.id, "name": s.name, "level": s.level,
                            "description": s.description,
                            "entry": spell_entry(s),
                            "selected": s.id in books.get(cid, [])}
                           for s in candidates],
            "cantrip_required": cantrip_required,
            "cantrip_candidates": cantrip_candidates,
        })
    return rows



def _apply_spells(draft: dict[str, Any], form, data) -> None:
    int_score = draft["abilities"].get("INT", 10)
    ruleset = _ruleset_of(draft)
    books: dict[str, list[str]] = dict(draft.get("spellbooks", {}))
    for cid in _class_ids(draft):
        cls = data.classes[cid]
        if not _casts_at_level_1(cls):
            continue
        entry = ClassEntry(class_id=cid, level=1)
        ctype = spell_engine.caster_type_of(cls, data)
        if ctype == "divine":
            books[cid] = []
            continue
        chosen = list(dict.fromkeys(form.getlist(f"spell_{cid}")))
        required = spell_engine.beginning_spell_count(entry, cls, int_score, ruleset)
        noun = "power" if ctype == "mental" else "starting spell"
        if len(chosen) != required:
            raise HTTPException(
                400, f"{cls.name} must choose exactly {required} {noun}(s); "
                     f"got {len(chosen)}."
            )
        accessible = spell_engine.accessible_levels(entry, cls)
        demoted = (spell_engine.DEMOTED_READ_MAGIC_IDS
                   if spell_engine._read_magic_demoted(cls, data, ruleset) else set())
        for sid in chosen:
            spell = data.spells.get(sid)
            on_list = spell is not None and bool(set(spell.spell_lists) & set(cls.spell_lists))
            if not on_list or (ctype == "arcane" and spell.level not in accessible):
                raise HTTPException(400, f"{sid!r} is not a valid {cls.name} {noun}.")
            if sid in demoted:
                raise HTTPException(400, f"{sid!r} is replaced by the Read Magic Cantrip rule.")

        # Cantrips (CC5): a separate pick, merged into the same spell book.
        cantrips_chosen: list[str] = []
        if ctype == "arcane" and spell_engine.is_dedicated_arcane(cls, data):
            cantrip_required = spell_engine.beginning_cantrip_count(entry, cls, data, ruleset)
            cantrips_chosen = list(dict.fromkeys(form.getlist(f"cantrip_{cid}")))
            if len(cantrips_chosen) != cantrip_required:
                raise HTTPException(
                    400, f"{cls.name} must choose exactly {cantrip_required} cantrip(s); "
                         f"got {len(cantrips_chosen)}."
                )
            for sid in cantrips_chosen:
                spell = data.spells.get(sid)
                on_list = spell is not None and bool(set(spell.spell_lists) & set(cls.spell_lists))
                if not on_list or spell.level != 0:
                    raise HTTPException(400, f"{sid!r} is not a valid {cls.name} cantrip.")
        books[cid] = [*chosen, *cantrips_chosen]
    draft["spellbooks"] = books
    draft["spells_done"] = True


@router.post("/{draft_id}/spells")
async def post_spells(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    form = await request.form()
    _apply_spells(draft, form, data)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/{_next_incomplete_step(draft)}")


# ── Equipment (always-on step right before Review) ────────────────────────

def _draft_magic(draft: dict[str, Any]) -> list[MagicItemInstance]:
    return [MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])]


def _equipment_context(draft: dict[str, Any], game_data) -> dict:
    """Build the rendering context for the equipment partial — shared between
    the wizard equipment step and the live character sheet."""
    draft_id = draft.get("_draft_id", "")

    # Build inventory_groups for the box (carried + stashed only; no carriers/retainers).
    from aose.sheet.view import build_inventory_groups as _big, AmmoOption
    from aose.engine import storage as _storage
    from aose.engine.ammo import accepts, resolve_ammo
    from aose.models import Ammunition as _Ammunition, Weapon as _Weapon
    load_options: dict = {}
    inventory_groups = []
    _move_targets: list = [
        {"kind": "carried", "id": None, "label": "Carried"},
        {"kind": "stashed", "id": None, "label": "Stashed"},
    ]
    try:
        _spec = _draft_to_spec(draft, game_data)
        inventory_groups = [
            g for g in _big(_spec, game_data)
            if g.kind in ("carried", "stashed")
        ]
        _move_targets = _storage.move_targets(_spec, game_data)

        # Build ammo load-options for equipped launchers (keyed by weapon instance_id)
        for inst in _spec.items:
            if inst.equip not in ("main_hand", "off_hand"):
                continue
            weapon = game_data.items.get(inst.catalog_id)
            if not isinstance(weapon, _Weapon) or not weapon.accepts_ammo:
                continue
            opts = []
            for ammo_inst in _spec.items:
                base = game_data.items.get(ammo_inst.catalog_id)
                if isinstance(base, _Ammunition) and accepts(weapon, base):
                    v = resolve_ammo(ammo_inst, game_data)
                    opts.append(AmmoOption(instance_id=ammo_inst.instance_id,
                                           name=v["name"], count=ammo_inst.count))
            if opts:
                load_options[inst.instance_id] = opts
    except Exception:
        pass

    return {
        "gold": draft.get("gold", 0),
        "gold_locked": draft.get("gold_locked", False),
        "magic_acquisition": False,
        "enchant_choices": [],
        "shop": shop_categories(game_data, _ruleset_of(draft)),
        "remove_modes": REMOVE_MODES,
        "ammo_load_options": load_options,
        "move_targets": _move_targets,
        "inv_move_url": f"/wizard/{draft_id}/inventory/move",
        "inventory_groups": inventory_groups,
    }


@router.get("/{draft_id}/equipment", response_class=HTMLResponse)
async def get_equipment(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    redirect = _gate(draft, "equipment", draft_id)
    if redirect:
        return redirect
    ctx = _base_context(request, draft_id, draft, "equipment")
    ctx.update(_equipment_context(draft, request.app.state.game_data))
    ctx["gold_rolled"] = "gold" in draft
    ctx["target_url_prefix"] = f"/wizard/{draft_id}/equipment"
    ctx["ammo_url_prefix"] = f"/wizard/{draft_id}"
    return templates.TemplateResponse(request, "wizard.html", ctx)


@router.post("/{draft_id}/equipment/roll-gold")
async def post_equipment_roll_gold(request: Request, draft_id: str):
    draft = _load(request, draft_id)
    if draft.get("gold_locked"):
        raise HTTPException(400, "Starting gold is already rolled and locked.")
    draft["gold"] = roll_starting_gold()
    # Strict locks immediately; otherwise the first purchase locks it (buy route).
    draft["gold_locked"] = _ruleset_of(draft).strict_mode
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/buy")
async def post_equipment_buy(request: Request, draft_id: str, item_id: str = Form(...)):
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    try:
        spec = _draft_to_spec(draft, data)
        shop_buy_item(spec, item_id, data)
        draft["items"] = [i.model_dump() for i in spec.items]
        draft["containers"] = [c.model_dump() for c in spec.containers]
        from aose.models.storage import StorageLocation as _SL
        _carried = _SL(kind="carried")
        draft["gold"] = sum(c.count for c in spec.coins
                            if c.denom == "gp" and c.location == _carried)
        draft["gold_locked"] = True  # first purchase locks the starting-gold roll
    except (UnknownItem, InsufficientFunds, ValueError) as e:
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
    try:
        if needs_instance(item):
            magic_items = add_free_magic_item(_draft_magic(draft), item_id, data)
            draft["magic_items"] = [m.model_dump() for m in magic_items]
        else:
            spec = _draft_to_spec(draft, data)
            shop_add_free_item(spec, item_id, data)
            draft["items"] = [i.model_dump() for i in spec.items]
            draft["containers"] = [c.model_dump() for c in spec.containers]
    except (UnknownItem, ValueError) as e:
        raise HTTPException(400, str(e))
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/equip")
async def wiz_inventory_equip(request: Request, draft_id: str,
                              category: str = Form(...), instance_id: str = Form(...),
                              slot: str | None = Form(None)):
    from aose.engine import inventory_actions as _ia
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    classes = [data.classes[cid] for cid in _class_ids(draft) if cid in data.classes]
    ruleset = _ruleset_of(draft)
    spec = _draft_to_spec(draft, data)
    try:
        _ia.equip_thing(spec, category, instance_id, data=data, slot=slot,
                        two_weapon=ruleset.two_weapon_fighting,
                        eligible=two_weapon_eligible(classes),
                        allowed_weapons=allowed_weapon_ids(classes, data, ruleset),
                        allowed_armor=allowed_armor_ids(classes, data),
                        allow_shields=shields_allowed(classes))
    except (ValueError, WieldError) as e:
        raise HTTPException(400, str(e))
    draft["items"] = [i.model_dump() for i in spec.items]
    draft["magic_items"] = [m.model_dump() for m in spec.magic_items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/unequip")
async def wiz_inventory_unequip(request: Request, draft_id: str,
                                category: str = Form(...), instance_id: str = Form(...)):
    from aose.engine import inventory_actions as _ia
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    try:
        _ia.unequip_thing(spec, category, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["items"] = [i.model_dump() for i in spec.items]
    draft["magic_items"] = [m.model_dump() for m in spec.magic_items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/sell")
async def wiz_inventory_sell(request: Request, draft_id: str,
                             category: str = Form(...), instance_id: str = Form(...),
                             mode: str = Form(...), count: int | None = Form(None)):
    from aose.engine import inventory_actions as _ia
    from aose.models.storage import StorageLocation as _SLrm
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    spec = _draft_to_spec(draft, data)
    try:
        _ia.sell_thing(spec, category, instance_id, mode, data, count=count)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _carried_rm = _SLrm(kind="carried")
    draft["items"] = [i.model_dump() for i in spec.items]
    draft["magic_items"] = [m.model_dump() for m in spec.magic_items]
    draft["gold"] = sum(c.count for c in spec.coins
                        if c.denom == "gp" and c.location == _carried_rm)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/consume")
async def wiz_inventory_consume(request: Request, draft_id: str,
                                category: str = Form("item"),
                                instance_id: str = Form(...)):
    from aose.engine import storage as _storage
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    spec = _draft_to_spec(draft, data)
    try:
        _storage.consume_item(spec, instance_id)
    except _storage.StorageError as e:
        raise HTTPException(400, str(e))
    draft["items"] = [i.model_dump() for i in spec.items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/charge")
async def wiz_inventory_charge(request: Request, draft_id: str,
                               category: str = Form(...), instance_id: str = Form(...),
                               op: str = Form("use")):
    from aose.engine import inventory_actions as _ia
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    try:
        if op == "reset":
            _ia.reset_charges_thing(spec, category, instance_id)
        else:
            _ia.use_charge_thing(spec, category, instance_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["items"] = [i.model_dump() for i in spec.items]
    draft["magic_items"] = [m.model_dump() for m in spec.magic_items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/note")
async def wiz_inventory_note(request: Request, draft_id: str,
                             category: str = Form(...), instance_id: str = Form(...),
                             note: str = Form("")):
    from aose.engine import inventory_actions as _ia
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    try:
        _ia.set_note_thing(spec, category, instance_id, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["items"] = [i.model_dump() for i in spec.items]
    draft["magic_items"] = [m.model_dump() for m in spec.magic_items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/move")
async def wiz_inventory_move(request: Request, draft_id: str):
    """Single movement front door for every owned thing in the wizard."""
    from aose.engine import storage as _storage
    from aose.models.storage import StorageLocation
    from pydantic import ValidationError as _ValidationError
    draft = _load(request, draft_id)
    form = await request.form()
    category = form.get("category", "")
    ref_id = (form.get("item_id") or form.get("instance_id")
              or form.get("denom") or "")
    try:
        dest = StorageLocation(kind=form.get("dest_kind", "carried"),
                               id=form.get("dest_id") or None)
        src = (StorageLocation(kind=form.get("src_kind"),
                               id=form.get("src_id") or None)
               if form.get("src_kind") else None)
    except _ValidationError as exc:
        raise HTTPException(400, str(exc))
    raw = form.get("count")
    count = int(raw) if raw not in (None, "") else None
    spec = _draft_to_spec(draft, request.app.state.game_data)
    try:
        _storage.move_thing(spec, category, ref_id, dest,
                            count=count, src=src,
                            data=request.app.state.game_data)
    except (KeyError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    from aose.models.storage import StorageLocation as _SL2
    _carried2 = _SL2(kind="carried")
    draft.update({
        "items": [i.model_dump() for i in spec.items],
        "containers": [c.model_dump() for c in spec.containers],
        "coins": [s.model_dump() for s in spec.coins],
        "gems": [g.model_dump() for g in spec.gems],
        "jewellery": [j.model_dump() for j in spec.jewellery],
        "magic_items": [m.model_dump() for m in spec.magic_items],
        "spell_sources": [s.model_dump() for s in spec.spell_sources],
        "gold": sum(c.count for c in spec.coins
                    if c.denom == "gp" and c.location == _carried2),
    })
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment/remove-container")
async def equipment_remove_container(request: Request, draft_id: str,
                                     instance_id: str = Form(...),
                                     mode: str = Form(...)):
    from aose.engine.shop import sell_container as _sell_container
    from aose.models.storage import StorageLocation as _SLrc
    _carried_rc = _SLrc(kind="carried")
    draft = _load(request, draft_id)
    data = request.app.state.game_data
    spec = _draft_to_spec(draft, data)
    try:
        _sell_container(spec, instance_id, mode, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    draft["containers"] = [c.model_dump() for c in spec.containers]
    draft["gold"] = sum(c.count for c in spec.coins
                        if c.denom == "gp" and c.location == _carried_rc)
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/inventory/use-as-container")
async def wiz_use_as_container(request: Request, draft_id: str):
    from aose.engine import storage as _storage
    from aose.models.storage import StorageLocation
    draft = _load(request, draft_id)
    form = await request.form()
    owner_kind = form.get("owner_kind", "carried")
    owner_id = form.get("owner_id") or None
    item_id = form.get("item_id", "")
    spec = _draft_to_spec(draft, request.app.state.game_data)
    try:
        owner = StorageLocation(kind=owner_kind, id=owner_id)
        _storage.use_as_container(spec, owner, item_id, request.app.state.game_data)
    except (ValueError, _storage.StorageError) as e:
        raise HTTPException(400, str(e))
    draft["items"] = [i.model_dump() for i in spec.items]
    draft["containers"] = [c.model_dump() for c in spec.containers]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/ammo/load")
async def wiz_ammo_load(request: Request, draft_id: str,
                        weapon_key: str = Form(...), instance_id: str = Form(...)):
    """weapon_key is the weapon's instance_id; instance_id is the ammo instance_id."""
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    weapon_inst = next((i for i in spec.items if i.instance_id == weapon_key), None)
    if weapon_inst is None:
        raise HTTPException(400, f"Weapon {weapon_key!r} not found")
    weapon_inst.loaded_ammo_id = instance_id
    draft["items"] = [i.model_dump() for i in spec.items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/ammo/unload")
async def wiz_ammo_unload(request: Request, draft_id: str,
                          weapon_key: str = Form(...)):
    """weapon_key is the weapon's instance_id."""
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    weapon_inst = next((i for i in spec.items if i.instance_id == weapon_key), None)
    if weapon_inst is None:
        raise HTTPException(400, f"Weapon {weapon_key!r} not found")
    weapon_inst.loaded_ammo_id = None
    draft["items"] = [i.model_dump() for i in spec.items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/ammo/adjust")
async def wiz_ammo_adjust(request: Request, draft_id: str,
                          instance_id: str = Form(...), delta: int = Form(...)):
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    ammo_inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if ammo_inst is None:
        raise HTTPException(400, f"Ammo {instance_id!r} not found")
    ammo_inst.count = max(0, ammo_inst.count + delta)
    if ammo_inst.count == 0:
        for i in spec.items:
            if i.loaded_ammo_id == instance_id:
                i.loaded_ammo_id = None
        spec.items.remove(ammo_inst)
    draft["items"] = [i.model_dump() for i in spec.items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/ammo/remove")
async def wiz_ammo_remove(request: Request, draft_id: str,
                          instance_id: str = Form(...)):
    draft = _load(request, draft_id)
    spec = _draft_to_spec(draft, request.app.state.game_data)
    ammo_inst = next((i for i in spec.items if i.instance_id == instance_id), None)
    if ammo_inst is None:
        raise HTTPException(400, f"Ammo {instance_id!r} not found")
    for i in spec.items:
        if i.loaded_ammo_id == instance_id:
            i.loaded_ammo_id = None
    spec.items.remove(ammo_inst)
    draft["items"] = [i.model_dump() for i in spec.items]
    save_draft(draft_id, draft, _drafts_dir(request))
    return _redirect(f"/wizard/{draft_id}/equipment")


@router.post("/{draft_id}/equipment")
async def post_equipment_continue(request: Request, draft_id: str):
    """Advance from Equipment to Review.  Locks the gold roll even if the
    user didn't buy anything — they've explicitly chosen to stop shopping."""
    draft = _load(request, draft_id)
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
    from aose.models import CoinStack
    from aose.models.storage import StorageLocation as _SLdts
    _carried_dts = _SLdts(kind="carried")
    gold = draft.get("gold", 0)
    return CharacterSpec(
        name=draft["name"],
        abilities=_creation_abilities(draft, data),
        race_id=draft["race_id"],
        classes=classes,
        alignment=draft["alignment"],
        secondary_skills=list(draft.get("secondary_skill") or []),
        languages=list(draft.get("languages", [])),
        weapon_proficiencies=list((draft.get("proficiencies") or {}).get("weapons", [])),
        weapon_specialisations=list((draft.get("proficiencies") or {}).get("specialisations", [])),
        feature_choices=dict(draft.get("feature_choices", {})),
        items=[ItemInstance.model_validate(i) for i in draft.get("items", [])],
        containers=[
            ContainerInstance.model_validate(c) for c in draft.get("containers", [])
        ],
        magic_items=[
            MagicItemInstance.model_validate(m) for m in draft.get("magic_items", [])
        ],
        coins=([CoinStack(denom="gp", count=gold, location=_carried_dts)] if gold else []),
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
