"""Build flat, render-ready detail "entries" for the wizard's book-style
surfaces (modal + spell expander).

Pure presentation: turns a CharClass / Race / Spell model into a dict the
``book_entry`` macro renders. No engine imports, no formatting decisions in
templates. An entry is::

    {
        "kind":  "class" | "race" | "spell",
        "name":  str,
        "stats": [{"label": str, "value": str}, ...],   # the green-box block
        "features": [{"name": str, "text": str}, ...],   # markdown per section
        "body":  str | None,                              # spell description only
    }
"""

from aose.models.character_class import CharClass
from aose.models.race import Race
from aose.models.spell import Spell

_ALIGN = {"law": "Law", "neutral": "Neutral", "chaos": "Chaos"}


def _titlecase(value: str) -> str:
    return value.replace("_", " ").title()


def _fmt_reqs(reqs) -> str:
    return ", ".join(f"{ab.value} {v}" for ab, v in reqs.items()) or "None"


def _fmt_allowed(value) -> str:
    if value == "all":
        return "Any"
    return ", ".join(_titlecase(v) for v in value) or "None"


def _fmt_mods(mods) -> str:
    return ", ".join(f"{ab.value} {d:+d}" for ab, d in mods.items()) or "None"


def class_entry(cls: CharClass) -> dict:
    armour = _fmt_allowed(cls.armor_allowed)
    if cls.shields_allowed and armour != "Any":
        armour = f"{armour}, shields"
    align = ", ".join(_ALIGN[a] for a in cls.allowed_alignments) or "Any"
    stats = [
        {"label": "Requirements", "value": _fmt_reqs(cls.ability_requirements)},
        {"label": "Prime requisite",
         "value": ", ".join(a.value for a in cls.prime_requisites)},
        {"label": "Hit Dice", "value": cls.hit_die},
        {"label": "Maximum level", "value": str(cls.max_level)},
        {"label": "Armour", "value": armour},
        {"label": "Weapons", "value": _fmt_allowed(cls.weapons_allowed)},
        {"label": "Alignment", "value": align},
    ]
    return {
        "kind": "class",
        "name": cls.name,
        "stats": stats,
        "features": [{"name": f.name, "text": f.text} for f in cls.features],
        "body": None,
    }


def race_entry(race: Race) -> dict:
    if race.allowed_classes:
        classes = ", ".join(
            f"{_titlecase(cid)}"
            + (f" {race.class_level_caps[cid]}" if cid in race.class_level_caps else "")
            for cid in race.allowed_classes
        )
    else:
        classes = "Any"
    stats = [
        {"label": "Requirements", "value": _fmt_reqs(race.ability_requirements)},
        {"label": "Ability modifiers", "value": _fmt_mods(race.ability_modifiers)},
        {"label": "Languages",
         "value": ", ".join(_titlecase(l) for l in race.languages) or "None"},
    ]
    if race.infravision:
        stats.append({"label": "Infravision", "value": f"{race.infravision}'"})
    stats.append({"label": "Available classes", "value": classes})
    return {
        "kind": "race",
        "name": race.name,
        "stats": stats,
        "features": [{"name": f.name, "text": f.text} for f in race.features],
        "body": None,
    }


def spell_entry(spell: Spell) -> dict:
    stats = [
        {"label": "Level", "value": str(spell.level)},
        {"label": "Range", "value": spell.range},
        {"label": "Duration", "value": spell.duration},
    ]
    if spell.reversible:
        stats.append({"label": "Reversible",
                      "value": spell.reverse_name or "Yes"})
    return {
        "kind": "spell",
        "name": spell.name,
        "stats": stats,
        "features": [],
        "body": spell.description,
    }
