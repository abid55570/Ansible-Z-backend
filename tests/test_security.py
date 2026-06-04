import jwt
import pytest

from app.core.security import create_access_token, decode_access_token


def test_token_roundtrip():
    token = create_access_token("user-123", claims={"email": "a@b.com"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "a@b.com"


def test_expired_token_raises():
    token = create_access_token("u", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_invalid_token_raises():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-real-token")
