from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import Scope

from aose.data.loader import GameData

from .auth.config import AuthConfig
from .auth.middleware import WorkspaceAuthMiddleware
from .auth.routes import router as auth_router
from .auth.verify import build_verifier
from .auth.whitelist import Whitelist
from .routes import router
from .settings_routes import router as settings_router
from .wizard import router as wizard_router


class NoCacheStaticFiles(StaticFiles):
    """Serve static files with ``Cache-Control: no-cache``.

    This is a local-only single-user dev app run with ``uvicorn --reload``;
    CSS/JS change often. ``no-cache`` forces the browser to revalidate on each
    load, so an edited stylesheet is picked up on a normal refresh instead of
    being served stale from the disk cache (which previously required a manual
    hard-refresh to see overlay/CSS fixes).
    """

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CHARACTERS_DIR = PROJECT_ROOT / "characters"
DEFAULT_EXAMPLES_DIR = PROJECT_ROOT / "examples"
DEFAULT_DRAFTS_DIR = PROJECT_ROOT / "drafts"
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "settings.json"


def _bootstrap_characters(characters_dir: Path, examples_dir: Path) -> None:
    """If characters/ is empty, seed it from examples/ so the app has demo content."""
    characters_dir.mkdir(parents=True, exist_ok=True)
    if any(characters_dir.glob("*.json")):
        return
    if not examples_dir.exists():
        return
    for example in examples_dir.glob("*.json"):
        (characters_dir / example.name).write_bytes(example.read_bytes())


def create_app(
    data_dir: Path = DEFAULT_DATA_DIR,
    characters_dir: Path = DEFAULT_CHARACTERS_DIR,
    drafts_dir: Path = DEFAULT_DRAFTS_DIR,
    examples_dir: Path = DEFAULT_EXAMPLES_DIR,
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    seed_from_examples: bool = True,
    auth_config: "AuthConfig | None" = None,
    auth_verifier=None,
) -> FastAPI:
    app = FastAPI(title="AOSE Character Builder")
    app.state.data_dir = data_dir
    app.state.characters_dir = characters_dir
    app.state.drafts_dir = drafts_dir
    app.state.examples_dir = examples_dir
    app.state.settings_path = settings_path
    app.state.game_data = GameData.load(data_dir)
    if auth_config is None:
        auth_config = AuthConfig.from_env(PROJECT_ROOT)
    app.state.auth_config = auth_config

    if auth_config is not None:
        app.state.auth_whitelist = Whitelist(auth_config.whitelist_path)
        app.state.auth_verifier = auth_verifier or build_verifier(auth_config)

    if seed_from_examples and auth_config is None:
        _bootstrap_characters(characters_dir, examples_dir)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", NoCacheStaticFiles(directory=str(static_dir)), name="static")
    app.add_middleware(WorkspaceAuthMiddleware)

    if auth_config is not None:
        app.add_middleware(
            SessionMiddleware,
            secret_key=auth_config.session_secret,
            https_only=auth_config.cookie_secure,
            same_site="lax",
        )
        app.include_router(auth_router)

    app.include_router(router)
    app.include_router(wizard_router)
    app.include_router(settings_router)
    return app


app = create_app()
