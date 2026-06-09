"""Per-ability reference table rows (AOSE ability modifier tables).

`ability_table_row(ability, score, is_prime)` returns the relevant book table
row for the COMPUTED score as a list of (label, value) cells.
"""
from aose.engine.ability_mods import ability_table_row


def _cells(ability, score, is_prime=False):
    return dict(ability_table_row(ability, score, is_prime=is_prime))


# ── STR: Melee / Open Doors ───────────────────────────────────────────────
def test_str_low():
    c = _cells("STR", 3)
    assert c["Melee"] == "−3"
    assert c["Open Doors"] == "1-in-6"


def test_str_mid_none():
    c = _cells("STR", 10)
    assert c["Melee"] == "None"
    assert c["Open Doors"] == "2-in-6"


def test_str_high():
    c = _cells("STR", 18)
    assert c["Melee"] == "+3"
    assert c["Open Doors"] == "5-in-6"


def test_str_band_13_15():
    c = _cells("STR", 14)
    assert c["Melee"] == "+1"
    assert c["Open Doors"] == "3-in-6"


# ── INT: Spoken Languages / Literacy ──────────────────────────────────────
def test_int_broken_speech():
    c = _cells("INT", 3)
    assert c["Spoken Languages"] == "Native (broken speech)"
    assert c["Literacy"] == "Illiterate"


def test_int_basic_literacy():
    c = _cells("INT", 7)
    assert c["Spoken Languages"] == "Native"
    assert c["Literacy"] == "Basic"


def test_int_additional_languages():
    assert _cells("INT", 13)["Spoken Languages"] == "Native + 1 additional"
    assert _cells("INT", 16)["Spoken Languages"] == "Native + 2 additional"
    assert _cells("INT", 18)["Spoken Languages"] == "Native + 3 additional"


# ── DEX: AC / Missile / Initiative ────────────────────────────────────────
def test_dex_low():
    c = _cells("DEX", 3)
    assert c["AC"] == "−3"
    assert c["Missile"] == "−3"
    assert c["Initiative"] == "−2"


def test_dex_high_initiative_diverges():
    c = _cells("DEX", 16)
    assert c["AC"] == "+2"
    assert c["Missile"] == "+2"
    assert c["Initiative"] == "+1"
    assert _cells("DEX", 18)["Initiative"] == "+2"


# ── CHA: Reactions / Retainers ────────────────────────────────────────────
def test_cha_low():
    c = _cells("CHA", 3)
    assert c["NPC Reactions"] == "−2"
    assert c["Retainers Max"] == "1"
    assert c["Retainers Loyalty"] == "4"


def test_cha_high():
    c = _cells("CHA", 18)
    assert c["NPC Reactions"] == "+2"
    assert c["Retainers Max"] == "7"
    assert c["Retainers Loyalty"] == "10"


# ── WIS / CON single-column ───────────────────────────────────────────────
def test_wis_magic_saves():
    assert _cells("WIS", 18)["Magic Saves"] == "+3"
    assert _cells("WIS", 10)["Magic Saves"] == "None"


def test_con_hit_points():
    assert _cells("CON", 16)["Hit Points"] == "+2"
    assert _cells("CON", 5)["Hit Points"] == "−2"


# ── Prime requisite XP modifier (only when is_prime) ──────────────────────
def test_prime_req_xp_appended():
    c = _cells("STR", 14, is_prime=True)
    assert c["XP Modifier"] == "+5%"


def test_prime_req_xp_bands():
    assert _cells("STR", 4, is_prime=True)["XP Modifier"] == "−20%"
    assert _cells("STR", 7, is_prime=True)["XP Modifier"] == "−10%"
    assert _cells("STR", 10, is_prime=True)["XP Modifier"] == "None"
    assert _cells("STR", 18, is_prime=True)["XP Modifier"] == "+10%"


def test_no_xp_modifier_when_not_prime():
    assert "XP Modifier" not in _cells("STR", 14, is_prime=False)


# ── Out-of-range scores clamp to the nearest band ─────────────────────────
def test_score_above_18_uses_top_band():
    assert _cells("CON", 25)["Hit Points"] == "+3"


def test_score_below_3_uses_bottom_band():
    assert _cells("CON", 1)["Hit Points"] == "−3"


# ── STR Open Doors category bonus (gargantua) ─────────────────────────────
def test_open_doors_bump_one_category():
    c = _cells("STR", 12)
    assert c["Open Doors"] == "2-in-6"                      # raw band
    bumped = dict(ability_table_row("STR", 12, open_doors_category_bonus=1))
    assert bumped["Open Doors"] == "3-in-6"                 # next category up


def test_open_doors_bump_clamps_at_top():
    bumped = dict(ability_table_row("STR", 18, open_doors_category_bonus=1))
    assert bumped["Open Doors"] == "5-in-6"                 # already top band


def test_open_doors_bump_leaves_melee_untouched():
    bumped = dict(ability_table_row("STR", 12, open_doors_category_bonus=1))
    assert bumped["Melee"] == "None"                        # only Open Doors bumps
