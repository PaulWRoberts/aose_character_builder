import pytest

from aose.web.auth.verify import FakeVerifier, TokenError, VerifiedUser


def test_fake_verifier_returns_mapped_user():
    v = FakeVerifier({"tok-a": VerifiedUser(uid="u-a", email="a@gmail.com", email_verified=True)})
    user = v.verify("tok-a")
    assert user.uid == "u-a" and user.email == "a@gmail.com" and user.email_verified


def test_fake_verifier_unknown_token_raises():
    v = FakeVerifier({})
    with pytest.raises(TokenError):
        v.verify("nope")
