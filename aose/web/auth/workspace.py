from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request

from aose.web.auth.identity import safe_uid


@dataclass(frozen=True)
class Workspace:
    """The three storage paths a request reads/writes through."""

    characters_dir: Path
    drafts_dir: Path
    settings_path: Path


def resolve_workspace(request: Request) -> Workspace:
    """Resolve the per-request workspace.

    Auth off (``app.state.auth_config is None``): mirror the global dirs.
    Auth on: derive ``users/<uid>/`` from the session (wired in Task D2).
    """
    state = request.app.state
    config = getattr(state, "auth_config", None)
    if config is None:
        return Workspace(
            characters_dir=state.characters_dir,
            drafts_dir=state.drafts_dir,
            settings_path=state.settings_path,
        )
    uid = safe_uid(request.session["uid"])  # gate guarantees presence when auth on
    user_base = config.users_root / uid
    characters_dir = user_base / "characters"
    drafts_dir = user_base / "drafts"
    settings_path = user_base / "settings.json"
    seed_user_workspace(user_base, characters_dir, getattr(state, "examples_dir", None))
    return Workspace(
        characters_dir=characters_dir,
        drafts_dir=drafts_dir,
        settings_path=settings_path,
    )


def seed_user_workspace(user_base: Path, characters_dir: Path, examples_dir) -> None:
    """Create dirs and seed examples on first login; no-op if user already exists."""
    if user_base.exists():
        return
    characters_dir.mkdir(parents=True, exist_ok=True)
    (user_base / "drafts").mkdir(parents=True, exist_ok=True)
    if examples_dir is not None and Path(examples_dir).exists():
        for example in Path(examples_dir).glob("*.json"):
            (characters_dir / example.name).write_bytes(example.read_bytes())
