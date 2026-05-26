"""PDF generation via WeasyPrint (optional, needs GTK3 native libs on Windows).

See: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
"""

_WEASYPRINT_ERROR: str | None = None

try:
    from weasyprint import HTML as _WP_HTML  # type: ignore[import-not-found]
    _WEASYPRINT_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    _WP_HTML = None  # type: ignore[assignment]
    _WEASYPRINT_AVAILABLE = False
    _WEASYPRINT_ERROR = str(exc)


def is_available() -> bool:
    return _WEASYPRINT_AVAILABLE


def import_error() -> str:
    return _WEASYPRINT_ERROR or "unknown error"


def render_pdf(html_content: str) -> bytes:
    """Render an HTML string to PDF bytes using WeasyPrint.

    Raises RuntimeError if WeasyPrint is unavailable (missing native libs).
    """
    if not _WEASYPRINT_AVAILABLE:
        raise RuntimeError(
            f"WeasyPrint could not load native libraries: {_WEASYPRINT_ERROR}\n\n"
            "On Windows, install the GTK3 runtime:\n"
            "  https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
            "Then re-run: .venv\\Scripts\\python.exe -m pip install weasyprint\n\n"
            "Alternatively, use the /print route and 'Save as PDF' in your browser's print dialog."
        )
    return _WP_HTML(string=html_content).write_pdf()  # type: ignore[union-attr]
