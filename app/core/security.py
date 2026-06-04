from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

SESSION_COOKIE = "az_session"


def create_access_token(
    subject: str,
    claims: dict | None = None,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload: dict = {"sub": subject, "iat": now, "exp": expire}
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
