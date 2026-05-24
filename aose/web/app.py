from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aose.data.loader import GameData

from .routes import router

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CHARACTERS_DIR = PROJECT_ROOT / "examples"


def create_app(
    data_dir: Path = DEFAULT_DATA_DIR,
    characters_dir: Path = DEFAULT_CHARACTERS_DIR,
) -> FastAPI:
    app = FastAPI(title="AOSE Character Builder")
    app.state.data_dir = data_dir
    app.state.characters_dir = characters_dir
    app.state.game_data = GameData.load(data_dir)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(router)
    return app


app = create_app()
