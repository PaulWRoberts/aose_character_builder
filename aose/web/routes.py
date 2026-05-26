from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from aose.characters.storage import list_character_ids, load_character
from aose.sheet.view import build_sheet

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Read print CSS once at import time so routes don't hit the filesystem per request.
_PRINT_CSS = (STATIC_DIR / "print.css").read_text(encoding="utf-8")


def _character_summaries(characters_dir: Path):
    summaries = []
    for cid in list_character_ids(characters_dir):
        try:
            spec = load_character(cid, characters_dir)
        except Exception:
            continue
        summaries.append({"id": cid, "name": spec.name, "race_id": spec.race_id})
    return summaries


# ── Index ──────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    characters = _character_summaries(request.app.state.characters_dir)
    return templates.TemplateResponse(
        request, "index.html", {"characters": characters}
    )


# ── Character sheet ────────────────────────────────────────────────────────

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


# ── Print preview (browser print / Save as PDF) ────────────────────────────

@router.get("/character/{character_id}/print", response_class=HTMLResponse)
async def character_print(request: Request, character_id: str):
    """Return a standalone print-optimised HTML page.

    The page has ``onload="window.print()"`` so opening it in a browser
    immediately triggers the print dialog — choose *Save as PDF* there.
    """
    try:
        spec = load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")
    sheet = build_sheet(spec, request.app.state.game_data)
    html = templates.get_template("sheet_print.html").render(
        sheet=sheet, print_css=_PRINT_CSS, auto_print=True
    )
    return HTMLResponse(content=html)


# ── Server-side PDF (WeasyPrint, needs GTK3 on Windows) ───────────────────

@router.get("/character/{character_id}/pdf")
async def character_pdf(request: Request, character_id: str):
    """Download a server-generated PDF via WeasyPrint.

    Requires GTK3 native libraries on Windows — see ``aose/web/pdf.py`` for
    installation instructions.  Falls back gracefully with a 503 if
    WeasyPrint is unavailable.
    """
    from aose.web.pdf import import_error, is_available, render_pdf

    try:
        spec = load_character(character_id, request.app.state.characters_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")

    if not is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Server-side PDF is unavailable: WeasyPrint could not load GTK3 "
                f"native libraries ({import_error()}). "
                f"Use /character/{character_id}/print instead and choose "
                "'Save as PDF' in your browser's print dialog, OR install the "
                "GTK3 runtime from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"
            ),
        )

    sheet = build_sheet(spec, request.app.state.game_data)
    html = templates.get_template("sheet_print.html").render(
        sheet=sheet, print_css=_PRINT_CSS, auto_print=False
    )
    pdf_bytes = render_pdf(html)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{character_id}.pdf"'},
    )
