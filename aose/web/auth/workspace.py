from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request


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
    raise NotImplementedError("auth-on workspace resolution added in Task D2")
