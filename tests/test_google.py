import pytest

import app.core.google as google_module
from app.core.google import GoogleAuthError, verify_google_id_token


def test_verify_ok(monkeypatch):
    monkeypatch.setattr(
        google_module.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "iss": "accounts.google.com",
            "sub": "1",
            "email": "a@b.com",
        },
    )
    claims = verify_google_id_token("token")
    assert claims["sub"] == "1"
    assert claims["email"] == "a@b.com"


def test_verify_bad_issuer(monkeypatch):
    monkeypatch.setattr(
        google_module.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {"iss": "evil.example.com"},
    )
    with pytest.raises(GoogleAuthError):
        verify_google_id_token("token")


def test_verify_underlying_failure(monkeypatch):
    def _boom(token, request, audience):
        raise ValueError("signature invalid")

    monkeypatch.setattr(google_module.google_id_token, "verify_oauth2_token", _boom)
    with pytest.raises(GoogleAuthError):
        verify_google_id_token("token")
