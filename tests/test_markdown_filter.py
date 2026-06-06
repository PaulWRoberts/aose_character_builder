from markupsafe import Markup

from aose.web.templating import render_markdown


def test_bold_renders_strong():
    out = render_markdown("This is **bold** text.")
    assert "<strong>bold</strong>" in out


def test_pipe_table_renders_table():
    md = (
        "| Level | CS |\n"
        "|---|---|\n"
        "| 1 | 87 |\n"
        "| 2 | 88 |\n"
    )
    out = render_markdown(md)
    assert "<table>" in out
    assert "<th>Level</th>" in out
    assert "<td>87</td>" in out


def test_blank_line_separates_paragraphs():
    out = render_markdown("First para.\n\nSecond para.")
    assert out.count("<p>") == 2


def test_none_and_empty_render_empty_markup():
    assert render_markdown(None) == Markup("")
    assert render_markdown("") == Markup("")


def test_return_type_is_markup():
    out = render_markdown("plain")
    assert isinstance(out, Markup)
