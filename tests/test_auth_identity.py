import pytest

from aose.web.auth.identity import normalise_email, safe_uid


def test_normalise_lowercases_and_strips():
    assert normalise_email("  Alice@Gmail.COM ") == "alice@gmail.com"


def test_safe_uid_accepts_firebase_style_ids():
    assert safe_uid("abc123XYZ_-") == "abc123XYZ_-"


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "has space", "."])
def test_safe_uid_rejects_path_unsafe(bad):
    with pytest.raises(ValueError):
        safe_uid(bad)
