from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from aose.web.auth.workspace import resolve_workspace

_PUBLIC_PREFIXES = ("/login", "/logout", "/static")


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/")
               for p in _PUBLIC_PREFIXES)


class WorkspaceAuthMiddleware(BaseHTTPMiddleware):
    """Resolve the per-request workspace and gate unauthenticated requests.

    Auth off: set ``request.state`` dirs from globals and pass through.
    Auth on: require a session ``uid`` for non-public paths (else redirect to
    ``/login``), then resolve the per-user workspace.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        config = getattr(request.app.state, "auth_config", None)
        is_public = _is_public(request.url.path)

        if config is not None and not is_public:
            uid = request.session.get("uid") if "session" in request.scope else None
            if not uid:
                return RedirectResponse(url="/login", status_code=303)

        if not (config is not None and is_public):
            # Skip workspace resolution for public auth routes (login/logout) —
            # they have no uid yet and don't need per-user storage dirs.
            try:
                ws = resolve_workspace(request)
            except NotImplementedError:
                return RedirectResponse(url="/login", status_code=303)

            request.state.characters_dir = ws.characters_dir
            request.state.drafts_dir = ws.drafts_dir
            request.state.settings_path = ws.settings_path

        response: Response = await call_next(request)
        return response
