import pytest

from aose.characters.drafts import (
    delete_draft,
    load_draft,
    new_draft_id,
    save_draft,
)


def test_new_draft_id_unique():
    ids = {new_draft_id() for _ in range(100)}
    assert len(ids) == 100


def test_save_load_roundtrip(tmp_path):
    draft_id = "abc12345"
    save_draft(draft_id, {"name": "Bilbo", "abilities": {"STR": 10}}, tmp_path)
    loaded = load_draft(draft_id, tmp_path)
    assert loaded["name"] == "Bilbo"
    assert loaded["abilities"]["STR"] == 10


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_draft("nope", tmp_path)


def test_delete(tmp_path):
    save_draft("x", {"a": 1}, tmp_path)
    delete_draft("x", tmp_path)
    with pytest.raises(FileNotFoundError):
        load_draft("x", tmp_path)


def test_delete_nonexistent_is_noop(tmp_path):
    delete_draft("never-existed", tmp_path)
