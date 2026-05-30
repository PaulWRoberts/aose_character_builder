"""Tests for tools/validate_import.py — built slice by slice."""
from pathlib import Path

import pytest

from tools.validate_import import (
    validate_file,
    duplicate_ids_in_dir,
    load_game_data,
    iter_units,
    load_manifest,
    mark_validated,
    main,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_file_good_class(tmp_path):
    f = _write(tmp_path / "fighter.yaml", """
id: fighter
name: Fighter
prime_requisites: [STR]
hit_die: 1d8
weapons_allowed: all
armor_allowed: all
shields_allowed: true
""")
    assert validate_file(f, "class") == []


def test_validate_file_bad_class_extra_field(tmp_path):
    f = _write(tmp_path / "bad.yaml", """
id: bad
name: Bad
prime_requisites: [STR]
hit_die: 1d8
weapons_allowed: all
armor_allowed: all
shields_allowed: true
nonsense_field: 1
""")
    errors = validate_file(f, "class")
    assert errors
    assert any("nonsense_field" in e for e in errors)


def test_validate_file_list_of_items(tmp_path):
    f = _write(tmp_path / "items.yaml", """
- id: club
  item_type: weapon
  name: Club
  category: weapons
  cost_gp: 3
  weight_cn: 50
  damage: {default: "1d6", variable: "1d4"}
- id: torch
  item_type: gear
  name: Torch
  category: adventuring_gear
  cost_gp: 1
  weight_cn: 20
""")
    assert validate_file(f, "item") == []


# ---------------------------------------------------------------------------
# Slice 2: cross-file ID uniqueness + full loader check
# ---------------------------------------------------------------------------

def test_duplicate_ids_in_dir(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "- {id: x, item_type: gear, name: X, category: g, cost_gp: 1}\n",
        encoding="utf-8",
    )
    (tmp_path / "b.yaml").write_text(
        "- {id: x, item_type: gear, name: X2, category: g, cost_gp: 1}\n",
        encoding="utf-8",
    )
    dupes = duplicate_ids_in_dir(tmp_path)
    assert "x" in dupes
    assert {p.name for p in dupes["x"]} == {"a.yaml", "b.yaml"}


def test_duplicate_ids_clean(tmp_path):
    (tmp_path / "a.yaml").write_text("- {id: x}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("- {id: y}\n", encoding="utf-8")
    assert duplicate_ids_in_dir(tmp_path) == {}


def test_load_game_data_real_dir():
    # The shipped data/ must load cleanly.
    assert load_game_data() == []


# ---------------------------------------------------------------------------
# Slice 3: manifest read/write + unit iteration
# ---------------------------------------------------------------------------

_MANIFEST_TEXT = """
- unit: class/fighter
  type: class
  yaml: data/classes/fighter.yaml
  validated: false
- unit: spell/ose-advanced-arcane
  type: spell
  yaml: data/spells/ose_advanced_spells.yaml
  validated: true
"""


def test_load_and_filter_units(tmp_path):
    mpath = tmp_path / "manifest.yaml"
    mpath.write_text(_MANIFEST_TEXT, encoding="utf-8")
    manifest = load_manifest(mpath)

    assert [u["unit"] for u in iter_units(manifest)] == [
        "class/fighter", "spell/ose-advanced-arcane",
    ]
    assert [u["unit"] for u in iter_units(manifest, only_incomplete=True)] == [
        "class/fighter",
    ]
    assert [u["unit"] for u in iter_units(manifest, type_="spell")] == [
        "spell/ose-advanced-arcane",
    ]
    assert [u["unit"] for u in iter_units(manifest, unit="class/fighter")] == [
        "class/fighter",
    ]


def test_mark_validated_round_trips(tmp_path):
    mpath = tmp_path / "manifest.yaml"
    mpath.write_text(_MANIFEST_TEXT, encoding="utf-8")
    mark_validated(mpath, "class/fighter")
    reloaded = load_manifest(mpath)
    fighter = next(u for u in reloaded if u["unit"] == "class/fighter")
    assert fighter["validated"] is True


# ---------------------------------------------------------------------------
# Slice 4: CLI main()
# ---------------------------------------------------------------------------

def test_main_passes_on_clean_repo():
    # Bare run against the real (clean) repo manifest + data.
    assert main([]) == 0


def test_main_reports_bad_unit(tmp_path, monkeypatch, capsys):
    import tools.validate_import as vi

    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nname: X\n", encoding="utf-8")  # missing required class fields
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        f"- unit: class/x\n  type: class\n  yaml: {bad.as_posix()}\n  validated: false\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vi, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(vi, "load_game_data", lambda *a, **k: [])
    monkeypatch.setattr(vi, "all_duplicate_ids", lambda *a, **k: [])

    rc = main(["--unit", "class/x"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out
    assert "class/x" in out


def test_unresolved_spell_list_refs_flags_bad_reference(tmp_path):
    from tools.validate_import import unresolved_spell_list_refs
    (tmp_path / "spell_lists.yaml").write_text(
        "- {id: magic_user, name: Magic-User, caster_type: arcane}\n", encoding="utf-8")
    (tmp_path / "classes").mkdir()
    (tmp_path / "classes" / "bard.yaml").write_text(
        "id: bard\nname: Bard\nprime_requisites: [CHA]\nhit_die: 1d6\n"
        "weapons_allowed: all\narmor_allowed: []\nshields_allowed: false\n"
        "spell_lists: [made_up_list]\n", encoding="utf-8")
    errors = unresolved_spell_list_refs(tmp_path)
    assert any("made_up_list" in e for e in errors)


def test_unresolved_spell_list_refs_passes_real_data():
    from pathlib import Path
    from tools.validate_import import unresolved_spell_list_refs
    data_dir = Path(__file__).parent.parent / "data"
    assert unresolved_spell_list_refs(data_dir) == []
