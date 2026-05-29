"""Tests for tools/validate_import.py — built slice by slice."""
from pathlib import Path

import pytest

from tools.validate_import import validate_file, duplicate_ids_in_dir, load_game_data


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
