from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aose.characters.storage import list_character_ids, load_character
from aose.sheet.view import build_sheet

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _character_summaries(characters_dir: Path):
    summaries = []
    for cid in list_character_ids(characters_dir):
        try:
            spec = load_character(cid, characters_dir)
        except Exception:
            continue
        summaries.append({"id": cid, "name": spec.name, "race_id": spec.race_id})
    return summaries


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    characters = _character_summaries(request.app.state.characters_dir)
    return templates.TemplateResponse(
        request, "index.html", {"characters": characters}
    )


@router.get("/character/{character_id}", response_class=HTMLResponse)
async def character_sheet(request: Request, character_id: str):
    try:
        spec = load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")
    sheet = build_sheet(spec, request.app.state.game_data)
    return templates.TemplateResponse(
        request, "sheet.html", {"sheet": sheet, "character_id": character_id}
    )
