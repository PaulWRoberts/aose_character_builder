from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from aose.web.auth.identity import normalise_email, safe_uid
from aose.web.auth.verify import TokenError
from aose.web.auth.workspace import seed_user_workspace
from aose.web.templating import make_templates

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = make_templates(str(TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    cfg = request.app.state.auth_config
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "firebase_api_key": cfg.firebase_api_key,
            "firebase_auth_domain": cfg.firebase_auth_domain,
            "firebase_project_id": cfg.firebase_project_id,
            "use_emulator": cfg.use_emulator,
            "emulator_host": cfg.emulator_host,
        },
    )


@router.post("/login/session")
async def login_session(request: Request):
    verifier = request.app.state.auth_verifier
    whitelist = request.app.state.auth_whitelist
    body = await request.json()
    id_token = body.get("idToken", "")
    try:
        user = verifier.verify(id_token)
    except TokenError:
        return JSONResponse({"error": "invalid token"}, status_code=401)
    if not user.email_verified or not whitelist.allows(user.email):
        return JSONResponse({"error": "not invited"}, status_code=403)
    request.session["uid"] = user.uid
    request.session["email"] = normalise_email(user.email)
    # Eagerly seed the per-user workspace so it exists before the first page load.
    cfg = request.app.state.auth_config
    uid = safe_uid(user.uid)
    user_base = cfg.users_root / uid
    seed_user_workspace(user_base, user_base / "characters", getattr(request.app.state, "examples_dir", None))
    return JSONResponse({"ok": True})


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
