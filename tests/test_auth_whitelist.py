from aose.web.auth.whitelist import Whitelist


def test_membership_is_normalised(tmp_path):
    f = tmp_path / "whitelist.txt"
    f.write_text("Alice@Gmail.com\n# a comment\n\nbob@example.org\n", encoding="utf-8")
    wl = Whitelist(f)
    assert wl.allows("alice@gmail.com")
    assert wl.allows("  BOB@EXAMPLE.ORG ")
    assert not wl.allows("mallory@evil.test")


def test_missing_file_allows_nobody(tmp_path):
    wl = Whitelist(tmp_path / "nope.txt")
    assert not wl.allows("anyone@example.com")
