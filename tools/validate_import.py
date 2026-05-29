"""Validate candidate import YAML against the real Pydantic models.

Run modes:
    python tools/validate_import.py                  # all incomplete manifest units
    python tools/validate_import.py --unit class/fighter
    python tools/validate_import.py --type spell
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from aose.models import CharClass, Item, Race, Spell

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANIFEST_PATH = ROOT / "import" / "manifest.yaml"

# Per-type Pydantic target. race-as-class and magic-item reuse class/item.
_MODEL = {"race": Race, "class": CharClass, "spell": Spell}
_ITEM_ADAPTER = TypeAdapter(Item)
_TYPE_ALIASES = {"race-as-class": "class", "magic-item": "item"}


def _canonical_type(type_: str) -> str:
    return _TYPE_ALIASES.get(type_, type_)


def _read_objects(path: Path) -> list[dict]:
    """A YAML file may hold one mapping or a list of mappings."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    return list(raw) if isinstance(raw, list) else [raw]


def validate_file(path: Path, type_: str) -> list[str]:
    """Return a list of human-readable validation errors ([] = valid)."""
    canon = _canonical_type(type_)
    errors: list[str] = []
    for i, obj in enumerate(_read_objects(path)):
        where = f"{path.name}[{i}]"
        try:
            if canon == "item":
                _ITEM_ADAPTER.validate_python(obj)
            else:
                _MODEL[canon].model_validate(obj)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"{where}: {loc}: {err['msg']}")
    return errors


def duplicate_ids_in_dir(directory: Path) -> dict[str, list[Path]]:
    """Map any id that appears in more than one *.yaml to the files holding it.

    The loader keys everything by id; a collision silently overwrites, so this
    is the safeguard now that multiple books share data/equipment and data/spells.
    """
    seen: dict[str, list[Path]] = {}
    if not directory.exists():
        return {}
    for path in sorted(directory.glob("*.yaml")):
        for obj in _read_objects(path):
            obj_id = obj.get("id") if isinstance(obj, dict) else None
            if obj_id is None:
                continue
            seen.setdefault(obj_id, [])
            if path not in seen[obj_id]:
                seen[obj_id].append(path)
    return {k: v for k, v in seen.items() if len(v) > 1}


def load_game_data(data_dir: Path = DATA_DIR) -> list[str]:
    """Run the full GameData.load to catch cross-reference problems."""
    from aose.data.loader import GameData

    try:
        GameData.load(data_dir)
    except Exception as exc:  # ValidationError, KeyError, etc.
        return [f"GameData.load failed: {exc}"]
    return []


def all_duplicate_ids(data_dir: Path = DATA_DIR) -> list[str]:
    """Cross-file uniqueness across every loaded directory."""
    errors: list[str] = []
    for sub in ("races", "classes", "spells", "equipment"):
        for obj_id, paths in duplicate_ids_in_dir(data_dir / sub).items():
            names = ", ".join(p.name for p in paths)
            errors.append(f"duplicate id '{obj_id}' in {sub}/: {names}")
    return errors


def load_manifest(path: Path = MANIFEST_PATH) -> list[dict]:
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _save_manifest(manifest: list[dict], path: Path = MANIFEST_PATH) -> None:
    path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def iter_units(
    manifest: list[dict],
    *,
    unit: str | None = None,
    type_: str | None = None,
    only_incomplete: bool = False,
):
    for u in manifest:
        if unit is not None and u.get("unit") != unit:
            continue
        if type_ is not None and u.get("type") != type_:
            continue
        if only_incomplete and u.get("validated") is True:
            continue
        yield u


def mark_validated(path: Path, unit: str, value: bool = True) -> None:
    manifest = load_manifest(path)
    for u in manifest:
        if u.get("unit") == unit:
            u["validated"] = value
    _save_manifest(manifest, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate import YAML.")
    parser.add_argument("--unit", help="validate a single manifest unit by name")
    parser.add_argument("--type", dest="type_", help="validate all units of a type")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    only_incomplete = args.unit is None and args.type_ is None
    units = list(iter_units(
        manifest, unit=args.unit, type_=args.type_, only_incomplete=only_incomplete,
    ))

    failed = False
    for u in units:
        name = u.get("unit", "<unnamed>")
        yaml_rel = u.get("yaml")
        if not yaml_rel:
            print(f"SKIP {name}: no yaml path yet")
            continue
        path = ROOT / yaml_rel if not Path(yaml_rel).is_absolute() else Path(yaml_rel)
        if not path.exists():
            print(f"FAIL {name}: missing file {yaml_rel}")
            failed = True
            continue
        errors = validate_file(path, u.get("type", ""))
        if errors:
            failed = True
            print(f"FAIL {name}:")
            for e in errors:
                print(f"    {e}")
        else:
            mark_validated(MANIFEST_PATH, name)
            print(f"OK   {name}")

    # Repo-wide checks always run.
    for e in load_game_data() + all_duplicate_ids():
        failed = True
        print(f"FAIL repo: {e}")

    print("FAILED" if failed else "ALL OK")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
